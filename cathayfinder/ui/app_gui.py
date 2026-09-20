# -*- coding: utf-8 -*-
"""CathayFinder GUI - FTS5 全文检索 + 增量加载"""
import sys, os, csv, io, json, subprocess
from pathlib import Path
from urllib.parse import unquote, quote

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QLabel, QTableWidget, QTableWidgetItem,
    QHeaderView, QSplitter, QTextEdit, QCheckBox, QGroupBox,
    QMessageBox, QFileDialog, QStatusBar, QProgressBar,
    QAbstractItemView, QGridLayout, QDialog, QDialogButtonBox, QComboBox,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt5.QtGui import QFont, QColor, QPalette, QCursor, QIcon
from PyQt5.QtWidgets import QToolTip

from ..search.engine import (
    search, search_more, search_all, search_config,
    DB_SEARCH_CONFIG, FETCH_PER_DB, FETCH_INCREMENT, tidy_results,
    PRIORITY_MAP, NAME_MAP, SEARCH_FIELDS,
)
from ..data.db_manager import channel_available, channel_db_files, close_all
from ..config import CHANNEL_COLORS

PAGE_SIZE = 100
DEFAULT_OFF_SOURCES = set()   # 默认全部勾选（含「维基共享资源」）
AUTO_MAX_ROUNDS = 20        # 一次搜索里最多自动加载多少批（防止某些库很大时死循环）

# ── 导出字段（用户可自己勾选要写进文件的字段，不勾的不出现） ──
EXPORT_FIELDS = [
    ("source", "渠道"),
    ("title", "书名"),
    ("filename", "文件名"),
    ("filepath", "目录/路径"),
    ("author", "作者"),
    ("publisher", "出版者"),
    ("year", "年份"),
    ("isbn", "ISBN"),
    ("ssid", "SSID"),
    ("pages", "页数"),
    ("extra", "备注"),
]
FIELD_LABEL = dict(EXPORT_FIELDS)
DEFAULT_EXPORT_FIELDS = [k for k, _ in EXPORT_FIELDS]


def _app_dir():
    """程序目录（打包后 = exe 所在目录；源码运行 = 项目根），用于存用户的导出字段偏好"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    here = os.path.abspath(__file__)                    # …/cathayfinder/ui/app_gui.py
    return os.path.dirname(os.path.dirname(os.path.dirname(here)))   # 项目根


def _fields_path():
    return os.path.join(_app_dir(), "cathayfinder_settings.json")


def load_export_fields():
    """读上次勾选的导出字段（没存过就给默认全选）"""
    try:
        with open(_fields_path(), encoding="utf-8") as f:
            d = json.load(f)
        fs = [k for k in (d.get("export_fields") or []) if k in FIELD_LABEL]
        return fs or list(DEFAULT_EXPORT_FIELDS)
    except Exception:
        return list(DEFAULT_EXPORT_FIELDS)


def save_export_fields(fields):
    try:
        with open(_fields_path(), "w", encoding="utf-8") as f:
            json.dump({"export_fields": list(fields)}, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _field_value(r, key):
    """取一个字段的导出值"""
    try:
        if key == "title":
            return r.display_title() or ""
        v = getattr(r, key, "") or ""
        return str(v)
    except Exception:
        return ""


class ExportOptionsDialog(QDialog):
    """导出前选字段：勾上的字段才会写进文件，没勾的字段直接不出现"""

    def __init__(self, parent=None, selected=None):
        super().__init__(parent)
        self.setWindowTitle("导出选项")
        sel = set(selected or DEFAULT_EXPORT_FIELDS)
        lay = QVBoxLayout(self)
        tip = QLabel("勾选要写进文件的字段（按这里的顺序输出）；没勾的字段不会出现在导出的文件里。")
        tip.setStyleSheet("color:#555;")
        tip.setWordWrap(True)
        lay.addWidget(tip)
        grid = QGridLayout()
        self.boxes = {}
        for i, (key, label) in enumerate(EXPORT_FIELDS):
            cb = QCheckBox(label)
            cb.setChecked(key in sel)
            self.boxes[key] = cb
            grid.addWidget(cb, i // 3, i % 3)
        lay.addLayout(grid)
        row = QHBoxLayout()
        b_all = QPushButton("全选")
        b_all.clicked.connect(lambda: [b.setChecked(True) for b in self.boxes.values()])
        b_none = QPushButton("全不选")
        b_none.clicked.connect(lambda: [b.setChecked(False) for b in self.boxes.values()])
        row.addWidget(b_all)
        row.addWidget(b_none)
        row.addStretch()
        lay.addLayout(row)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("导出")
        bb.button(QDialogButtonBox.Cancel).setText("取消")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def selected_fields(self):
        return [k for k, _ in EXPORT_FIELDS if self.boxes[k].isChecked()]


def _write_export(fp, fmt, rows, keyword="", merged=0, fields=None):
    """把（已去重 + 已排序的）结果写成文件；返回写出的条数

    fmt 支持 md / csv / txt / html；CSV 用 utf-8-sig 便于 Excel 直接打开。
    fields：要导出的字段 key 列表（不传 = 全部字段）。没勾的字段不会出现在文件里。
    """
    fields = [k for k in (fields or DEFAULT_EXPORT_FIELDS) if k in FIELD_LABEL]
    cols = [(k, FIELD_LABEL[k]) for k in fields]
    lines = []
    if fmt == "md":
        lines.append(f"# CathayFinder 搜索结果 ({len(rows)} 条)\n")
        for r in rows:
            parts = [f"- **{_field_value(r, 'title') or _field_value(r, 'filename') or '（无题）'}**"]
            for k, lab in cols:
                if k in ("title",):
                    continue
                v = _field_value(r, k)
                if v:
                    parts.append(f"{lab}: {v}")
            lines.append(" ".join(parts))
    elif fmt == "csv":
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        w.writerow([lab for _k, lab in cols])
        for r in rows:
            w.writerow([_field_value(r, k) for k, _lab in cols])
        lines = [buf.getvalue()]
    elif fmt == "txt":
        lines.append(f"CathayFinder 搜索结果 ({len(rows)} 条)\n{'='*50}")
        for r in rows:
            lines.append("\n%s" % (_field_value(r, "title") or _field_value(r, "filename") or "（无题）"))
            for k, lab in cols:
                if k in ("title",):
                    continue
                v = _field_value(r, k)
                if v:
                    lines.append(f"  {lab}: {v}")
    elif fmt == "html":
        lines.append("<!DOCTYPE html><html><meta charset='utf-8'><body>")
        lines.append(f"<h1>CathayFinder ({len(rows)} 条)</h1>"
                     "<table border=1><tr>"
                     + "".join(f"<th>{lab}</th>" for _k, lab in cols) + "</tr>")
        for r in rows:
            lines.append("<tr>" + "".join(
                "<td>%s</td>" % _field_value(r, k) for k, _lab in cols) + "</tr>")
        lines.append("</table></body></html>")
    if not lines:
        return 0
    if fmt == "csv":
        with open(fp, "w", encoding="utf-8-sig", newline="") as f:
            f.write(lines[0])
    else:
        with open(fp, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
    return len(rows)


class ExportWorker(QThread):
    """导出专用：把命中的**全部**结果取回（不限量）→ 读秀去重 + A→Z 排序 → 按勾选字段写文件

    不动作界面上的列表（列表仍是分渠道限量取的那一份）。
    """
    done = pyqtSignal(bool, str)

    def __init__(self, keyword, fmt, path, fallback_rows, fields=None, field='all'):
        super().__init__()
        self.keyword = (keyword or "").strip()
        self.fmt = fmt
        self.path = path
        self.fallback_rows = list(fallback_rows or [])
        self.fields = list(fields) if fields else list(DEFAULT_EXPORT_FIELDS)
        self.field = field or 'all'

    def run(self):
        try:
            if self.keyword:
                res, _seen, _meta = search_all(self.keyword, field=self.field)
            else:
                res = self.fallback_rows
            rows, merged = tidy_results(res)
            n = _write_export(self.path, self.fmt, rows, self.keyword, merged,
                              self.fields)
            note = f"（读秀按 SSID 去重，合并了 {merged} 条）" if merged else ""
            fl = "、".join(FIELD_LABEL.get(k, k) for k in self.fields)
            self.done.emit(True, "已导出全部 %s 条%s\n字段：%s\n%s"
                           % (format(n, ','), note, fl, self.path))
        except MemoryError:
            self.done.emit(False, "内存不足，取全部结果失败。可用更具体的查询词，或先取消几个渠道再导出。")
        except Exception as e:
            self.done.emit(False, "%r" % (e,))


class SearchWorker(QThread):
    finished = pyqtSignal(list, set, dict)  # results, seen_keys, meta

    def __init__(self, keyword, cap=None, field='all'):
        super().__init__()
        self.keyword = keyword
        self.cap = cap
        self.field = field

    def run(self):
        try:
            results, seen, meta = search(self.keyword, cap=self.cap, field=self.field)
            self.finished.emit(results, seen, meta)
        except Exception:
            self.finished.emit([], set(), {})


class LoadMoreWorker(QThread):
    finished = pyqtSignal(list, set, dict)  # 新增结果, seen_keys, meta

    def __init__(self, keyword, existing_seen, cap, field='all'):
        super().__init__()
        self.keyword = keyword
        self.field = field
        self.existing_seen = existing_seen
        self.cap = cap

    def run(self):
        try:
            new_results, seen, meta = search_more(
                self.keyword, self.existing_seen, self.cap, field=self.field
            )
            self.finished.emit(new_results, seen, meta)
        except Exception:
            self.finished.emit([], set(), {})


def _clean_path(fp):
    if not fp:
        return ""
    parts = fp.replace("\\", "/").split("/")
    meaningful = [p for p in parts if p and not p.startswith(":")]
    return "/".join(meaningful[-3:]) if len(meaningful) > 3 else "/".join(meaningful)


def _open_in_explorer(path):
    """在资源管理器里定位这个文件（文件不在就打开它上一级目录）

    坑：explorer 的 /select 必须写成  explorer /select,"整条路径" ——
    引号只能包住路径本身、不能包住 /select, 前缀。用参数列表传（Python 会
    给整个 /select,路径 加引号）时，只要路径里有空格，explorer 就会把
    「我的文档」打开。所以这里用字符串命令 + 只给路径加引号。
    """
    try:
        raw = str(path or '').strip()
        if not raw:
            QMessageBox.information(None, "打开所在文件夹", "这条记录没有路径信息。")
            return
        p = os.path.abspath(raw)
        if os.path.isfile(p):
            subprocess.Popen('explorer /select,"%s"' % p)
        elif os.path.isdir(p):
            subprocess.Popen('explorer "%s"' % p)
        else:
            d = os.path.dirname(p)
            if d and os.path.isdir(d):
                subprocess.Popen('explorer "%s"' % d)
            else:
                QMessageBox.information(None, "打开所在文件夹",
                                        "文件已不在（可能被移动或删除）：\n%s" % p)
    except Exception as e:
        QMessageBox.warning(None, "打开失败", str(e))


def _open_web(url):
    try:
        import webbrowser
        webbrowser.open(url)
    except Exception:
        pass


def _copy_text(txt, tip="已复制"):
    """复制到剪贴板，并在鼠标旁弹一下提示"""
    try:
        QApplication.clipboard().setText(str(txt))
        QToolTip.showText(QCursor.pos(), "%s：%s" % (tip, txt))
    except Exception:
        pass


# 各渠道在详情页里的固定说明（按用户要求写死）
CHANNEL_NOTES = {
    "学术信息数据库": "个人资料（百度网盘 / 阿里云盘），如需获取，请联系软件作者",
    "华中师大近史所": "华中师范大学中国近代史研究所实体藏书",
    "读秀": "请在某宝上，搜索“读秀 百度网盘共享群”，购买任何群的入群资格，即可下载。"
            "（极少数图书可能无法下载）",
}


def _row_url(r):
    """该结果对应的外部网页（没有则 None）

    读秀不再给网页按钮（改为「复制 SSID」），见 CHANNEL_NOTES / _actions_for。
    """
    if r.source == "维基文库" and r.title:
        return "https://zh.wikisource.org/wiki/%s" % quote(r.title)
    if r.source == "维基共享资源" and r.title:
        t = unquote(r.title) if '%' in r.title else r.title
        if t.lower().startswith("file:"):
            t = t[5:]
        return "https://commons.wikimedia.org/wiki/File:%s" % quote(t)
    return None


class DetailPanel(QWidget):
    """右侧详情：上面是文字信息，下面是可点的操作按钮"""

    def __init__(self):
        super().__init__()
        self.setMaximumWidth(520)
        self.setMinimumWidth(320)
        self.current_result = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self.text = QTextEdit()
        self.text.setReadOnly(True)
        lay.addWidget(self.text, 1)
        self.btn_bar = QWidget()
        self.btn_lay = QHBoxLayout(self.btn_bar)
        self.btn_lay.setContentsMargins(2, 0, 2, 2)
        self.btn_lay.setSpacing(6)
        lay.addWidget(self.btn_bar)

    def _clear_btns(self):
        while self.btn_lay.count():
            it = self.btn_lay.takeAt(0)
            w = it.widget()
            if w:
                w.setParent(None)
                w.deleteLater()

    def _add_btn(self, label, slot):
        b = QPushButton(label)
        b.setFixedHeight(24)
        b.clicked.connect(slot)
        self.btn_lay.addWidget(b)

    def show_result(self, r):
        self.current_result = r
        lines = []
        lines.append(f"<b>渠道：</b>{r.source}")
        title = r.display_title()
        if title:
            lines.append(f"<b>书名：</b>{title}")
        if r.author:
            lines.append(f"<b>作者：</b>{r.author}")
        if r.publisher:
            lines.append(f"<b>出版：</b>{r.publisher}")
        if r.year:
            lines.append(f"<b>年份：</b>{r.year}")
        if r.isbn:
            lines.append(f"<b>ISBN：</b>{r.isbn}")
        if r.ssid:
            lines.append(f"<b>SSID：</b>{r.ssid}")
        if r.pages:
            lines.append(f"<b>页数：</b>{r.pages}")
        if r.filename:
            lines.append(f"<b>文件名：</b>{r.filename}")
        if r.filepath:
            fp = r.filepath if r.source == "本地文件库" else _clean_path(r.filepath)
            lines.append(f"<b>文件路径：</b>{fp}")
        if r.extra:
            lines.append(f"<b>备注：</b>{r.extra}")
        note = CHANNEL_NOTES.get(r.source)
        if note:
            lines.append("<br><span style='color:#b45309;'>📌 %s</span>" % note)
        if not lines:
            lines.append("无详细信息")

        self.text.setHtml("<br>".join(lines))

        # 操作按钮（真按钮，不再是详情里的链接）
        self._clear_btns()
        if r.source == "本地文件库" and r.filepath:
            self._add_btn("📂 打开所在文件夹",
                          lambda: _open_in_explorer(r.filepath))
        if r.source == "读秀" and r.ssid:
            self._add_btn("📋 复制 SSID",
                          lambda: _copy_text(r.ssid, "已复制 SSID"))
        url = _row_url(r)
        if url:
            self._add_btn("🌐 打开网页", lambda: _open_web(url))

    # 旧版的超链接点击已废弃（改用按钮）

    def mouseReleaseEvent(self, e):
        super().mouseReleaseEvent(e)


class SourceCheckGroup(QGroupBox):
    def __init__(self):
        super().__init__("搜索范围")
        self.checkboxes = {}
        self.labels = {}
        self._auto_disabled = set()   # 因为库文件缺失而被自动置灰的渠道
        layout = QGridLayout()
        row = col = 0
        for cfg in DB_SEARCH_CONFIG:
            name = cfg["name"]
            label = cfg["label"]
            self.labels[name] = label
            cb = QCheckBox(label)
            cb.setChecked(name not in DEFAULT_OFF_SOURCES)
            cb.toggled.connect(self._on_toggle)
            self.checkboxes[name] = cb
            layout.addWidget(cb, row, col)
            col += 1
            if col >= 3:
                col = 0
                row += 1
        btn_layout = QHBoxLayout()
        sa = QPushButton("全选")
        sa.clicked.connect(lambda: [c.setChecked(True)
                                    for c in self.checkboxes.values() if c.isEnabled()])
        ds = QPushButton("全不选")
        ds.clicked.connect(lambda: [c.setChecked(False) for c in self.checkboxes.values()])
        rf = QPushButton("🔄 检测数据库")
        rf.setToolTip("重新检查每个渠道的库文件；删掉的库会自动置灰并跳过")
        rf.clicked.connect(self.refresh_availability)
        btn_layout.addWidget(sa)
        btn_layout.addWidget(ds)
        btn_layout.addWidget(rf)
        layout.addLayout(btn_layout, row + 1, 0, 1, 3)
        self.setLayout(layout)
        self.refresh_availability()

    def refresh_availability(self):
        """库文件被用户手动删掉的渠道 → 置灰 + 不勾选（搜索也会跳过它）"""
        for name, cb in self.checkboxes.items():
            ok, missing = channel_available(name)
            label = self.labels[name]
            if not ok:
                cb.setChecked(False)
                cb.setEnabled(False)
                cb.setText("%s（库文件缺失）" % label)
                cb.setToolTip("这个渠道的库文件已经被删除，软件会自动跳过它：\n"
                              + "\n".join(missing)
                              + "\n\n（想恢复：把库文件放回 data\\db 目录后点「🔄 检测数据库」）")
                self._auto_disabled.add(name)
            else:
                cb.setEnabled(True)
                cb.setText(label)
                tip = "库文件：\n" + "\n".join(str(p) for p in channel_db_files(name))
                if missing:      # 一个渠道挂多库时，缺的那部分提示一下
                    tip += "\n\n⚠ 缺少（不影响本渠道其它库）：\n" + "\n".join(missing)
                cb.setToolTip(tip)
                if name in self._auto_disabled:   # 库文件放回来了 → 恢复默认勾选
                    cb.setChecked(name not in DEFAULT_OFF_SOURCES)
                    self._auto_disabled.discard(name)
        self._on_toggle()

    def _on_toggle(self):
        enabled = set()
        for name, cb in self.checkboxes.items():
            if cb.isChecked():
                enabled.add(name)
        search_config.enabled_sources = enabled


def icon_path():
    """程序图标：打包后在 _MEIPASS 里，源码运行时在项目根。"""
    cand = []
    if getattr(sys, "frozen", False):
        cand.append(os.path.join(getattr(sys, "_MEIPASS", "") or "", "app.ico"))
    cand.append(os.path.join(_app_dir(), "app.ico"))
    cand.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.ico"))
    for p in cand:
        try:
            if p and os.path.isfile(p):
                return p
        except Exception:
            pass
    return ""


def _apply_icon(win):
    try:
        p = icon_path()
        if not p:
            return False
        ic = QIcon(p)
        win.setWindowIcon(ic)
        app = QApplication.instance()
        if app is not None:
            app.setWindowIcon(ic)
        return True
    except Exception:
        return False


class SearchApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.results = []         # 所有已获取结果
        self.seen = set()          # 去重 key 集合
        self.fetch_per_db = FETCH_PER_DB  # 当前每库取多少
        self.current_page = 0
        self.total_pages = 0
        self.kw = ""
        self.meta = {}             # 上一次搜索的统计（各渠道命中总数/已载数）
        self.loading_more = False  # 是否正在自动/手动加载下一批
        self.more_available = False
        self.auto_rounds = 0       # 自动加载的批次数（防跑飞）
        self.field = 'all'         # 当前检索字段（全部/书名/作者/出版者/SSID）
        self.icon_ok = _apply_icon(self)
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("CathayFinder - 综合性图书检索引擎 (FTS5)")
        self.setMinimumSize(1200, 750)
        self.setFont(QFont("Microsoft YaHei", 9))

        central = QWidget()
        self.setCentralWidget(central)
        main = QVBoxLayout(central)

        # Search bar
        sr = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入关键词...（可只搜书名 / 作者 / 出版者 / SSID）")
        self.search_input.setFont(QFont("Microsoft YaHei", 11))
        self.search_input.returnPressed.connect(self.do_search)
        self.field_combo = QComboBox()
        self.field_combo.setFont(QFont("Microsoft YaHei", 10))
        self.field_combo.setFixedHeight(32)
        for _key, _lab in SEARCH_FIELDS:
            self.field_combo.addItem("搜" + _lab if _key != "all" else "全部字段", _key)
        self.field_combo.setToolTip(
            "选择在哪个字段里找：\n"
            "全部字段 = 书名/文件名/作者/出版者里只要有就算命中（默认）\n"
            "书名 / 作者 / 出版者（出版社）= 只看这个字段\n"
            "SSID = 读秀/网盘的编号（支持前缀）：只查编号列，很快\n"
            "注：某个渠道没有这个字段时，该渠道不会出结果")
        self.search_btn = QPushButton("🔍 搜索")
        self.search_btn.setFont(QFont("Microsoft YaHei", 10))
        self.search_btn.setFixedHeight(32)
        self.search_btn.clicked.connect(self.do_search)
        sr.addWidget(self.search_input, 1)
        sr.addWidget(self.field_combo)
        sr.addWidget(self.search_btn)
        main.addLayout(sr)

        # Source checkboxes
        self.source_group = SourceCheckGroup()
        main.addWidget(self.source_group)

        # Splitter
        sp = QSplitter(Qt.Horizontal)
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(
            ["渠道", "书名/文件名", "作者", "出版者", "年份", "SSID", "操作"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeToContents)
        self.table.verticalHeader().setDefaultSectionSize(32)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.itemClicked.connect(self.on_item_clicked)
        self.table.cellDoubleClicked.connect(self.on_cell_double_clicked)
        # 自动加载：清到表格底部就自动取下一批（不用点按钮）
        self.table.verticalScrollBar().valueChanged.connect(self._on_scroll)
        sp.addWidget(self.table)

        self.detail = DetailPanel()
        sp.addWidget(self.detail)
        sp.setSizes([800, 350])
        main.addWidget(sp, 1)

        # Pagination + Load More
        pg = QHBoxLayout()
        self.load_more_btn = QPushButton("⬇ 加载更多")
        self.load_more_btn.clicked.connect(self.load_more)
        self.load_more_btn.setEnabled(False)
        self.load_more_btn.hide()
        pg.addStretch()
        pg.addWidget(self.load_more_btn)
        self.prev_btn = QPushButton("◀ 上一页")
        self.prev_btn.clicked.connect(self.prev_page)
        self.prev_btn.setEnabled(False)
        self.page_label = QLabel("第 0/0 页")
        self.page_label.setAlignment(Qt.AlignCenter)
        self.next_btn = QPushButton("下一页 ▶")
        self.next_btn.clicked.connect(self.next_page)
        self.next_btn.setEnabled(False)
        self.count_label = QLabel("")
        self.count_label.setAlignment(Qt.AlignCenter)
        pg.addWidget(self.prev_btn)
        pg.addWidget(self.page_label)
        pg.addWidget(self.next_btn)
        pg.addWidget(self.count_label)
        pg.addStretch()
        main.addLayout(pg)

        # Source stats
        self.source_stats_label = QLabel("")
        self.source_stats_label.setAlignment(Qt.AlignCenter)
        self.source_stats_label.setWordWrap(True)
        main.addWidget(self.source_stats_label)

        # 计数明细：命中 = 显示 + 重复合并 + 上限外未取
        self.count_detail_label = QLabel("")
        self.count_detail_label.setAlignment(Qt.AlignCenter)
        self.count_detail_label.setWordWrap(True)
        self.count_detail_label.setStyleSheet("color:#666; font-size:11px;")
        main.addWidget(self.count_detail_label)

        # Export
        ex = QHBoxLayout()
        for label, fmt in [("📄 导出 Markdown", "md"), ("📄 导出 CSV", "csv"),
                           ("📄 导出 Text", "txt"), ("📄 导出 HTML", "html")]:
            btn = QPushButton(label)
            btn.clicked.connect(lambda _, f=fmt: self.export(f))
            ex.addWidget(btn)
        hint = QLabel("导出前会先让你勾选要哪些字段（书名 / 文件名 / 目录 / SSID …），不勾的不写进文件")
        hint.setStyleSheet("color:#666; font-size:11px;")
        ex.addWidget(hint)
        main.addLayout(ex)

        # Status bar
        self.sb = QStatusBar()
        self.setStatusBar(self.sb)
        self.sb.showMessage("就绪")
        self.pb = QProgressBar()
        self.pb.setMaximumWidth(200)
        self.pb.hide()
        self.sb.addPermanentWidget(self.pb)

    def _skipped_note(self):
        """库文件被删掉的渠道（已自动跳过）提示"""
        gone = [self.source_group.labels.get(k, k)
                for k in self.source_group.checkboxes
                if not channel_available(k)[0]]
        return "（已跳过库文件缺失的渠道：%s）" % "、".join(gone) if gone else ""

    def do_search(self):
        kw = self.search_input.text().strip()
        if not kw:
            return
        self.source_group.refresh_availability()   # 库文件被删掉的渠道自动置灰/跳过
        self.kw = kw
        self.field = self.field_combo.currentData() or 'all'   # 检索字段
        self.results = []
        self.seen = set()
        self.meta = {}
        self.fetch_per_db = FETCH_PER_DB
        self.current_page = 0
        self.table.setRowCount(0)
        self.page_label.setText("第 0/0 页")
        self.count_label.setText("搜索中...")
        self.source_stats_label.setText("")
        self.load_more_btn.hide()
        self.search_btn.setEnabled(False)
        self.pb.show()
        self.pb.setRange(0, 0)
        self.sb.showMessage(f"搜索: {kw}" + ("（限定字段：%s）" % dict(SEARCH_FIELDS).get(
            self.field, '') if self.field != 'all' else ""))

        self.worker = SearchWorker(kw, field=self.field)
        self.worker.finished.connect(self.on_search_done)
        self.worker.start()

    def _dedup_rows(self):
        """屏幕列表整理：读秀按 8 位 SSID 去重 + 读秀按 A→Z（含汉字拼音）排序；
        其它渠道与无合规 SSID 的记录不动"""
        old = len(self.results)
        self.results, merged = tidy_results(self.results)
        self.total_pages = max(1, (len(self.results) + PAGE_SIZE - 1) // PAGE_SIZE)
        if self.current_page >= self.total_pages:
            self.current_page = self.total_pages - 1
        return merged, old - len(self.results)

    def _refresh_stats(self):
        """各渠道：已载 / 命中总数（按渠道优先级排列，不按条数乱排）"""
        stats = {}
        for r in self.results:
            stats[r.source] = stats.get(r.source, 0) + 1
        totals = (self.meta or {}).get('totals', {})
        items = []
        for src in sorted(stats, key=lambda s: PRIORITY_MAP.get(NAME_MAP.get(s, ""), 9999)):
            tot = (totals.get(src) or {}).get('total', stats[src])
            if tot and tot > stats[src]:
                items.append(f'{src}: {stats[src]:,} / {tot:,}')
            else:
                items.append(f'{src}: {stats[src]:,}')
        self.source_stats_label.setText(" | ".join(items))

    def _update_counts(self):
        """顶部计数：显示多少条 / 多少页；明细行把「库内命中」与「显示」的差额算清
        库内命中 = 显示 + 同书重复合并 + 同渠道重复记录 + 渠道上限外未取"""
        totals = (self.meta or {}).get('totals', {})
        raw = sum((t or {}).get('total', 0) for t in totals.values())
        got = sum((t or {}).get('loaded', 0) for t in totals.values())
        eff = sum(min((t or {}).get('limit', 0), (t or {}).get('total', 0))
                  for t in totals.values())   # 实际能取到的上限（不能超过库内命中）
        shown = len(self.results)
        capd = max(0, raw - eff)          # 被每渠道上限挡在外面的
        same_db = max(0, eff - got)       # 同一渠道内完全相同的记录
        same_book = max(0, got - shown)   # 读秀同书（同 SSID）合并

        self.count_label.setText(f"共 {shown:,} 条 · {self.total_pages} 页")
        if not raw:
            self.count_detail_label.setText("")
            return
        parts = [f"显示 {shown:,}"]
        dedupe = same_db + same_book
        if dedupe:
            extra = f"（含读秀同书合并 {same_book:,}）" if same_book else ""
            parts.append(f"重复记录已去掉 {dedupe:,}{extra}")
        if capd:
            parts.append(f"渠道上限外未取 {capd:,}（点「再取更多」继续）")
        self.count_detail_label.setText(
            f"库内命中 {raw:,} 条 ＝ " + " ＋ ".join(parts))

    def _capped(self):
        """还有渠道不在上限内（取值上限 < 库内命中）才需要「再取更多」"""
        return bool(self._cut_sources())

    def _cut_sources(self):
        """哪些渠道真被上限挡住了（实际能取的 < 库内命中），各命中多少"""
        totals = (self.meta or {}).get('totals', {})
        cut = [(k, v.get('total', 0), min(v.get('limit', 0), v.get('total', 0)))
               for k, v in totals.items()
               if min((v or {}).get('limit', 0), v.get('total', 0)) < v.get('total', 0)]
        cut.sort(key=lambda x: -x[1])
        return cut

    def on_search_done(self, results, seen, meta=None):
        self.results = results
        self.seen = seen
        self.meta = meta or {}
        close_all()          # 用完就放掉数据库文件，方便你随时手动删某个库
        merged, _gone = self._dedup_rows()
        self.current_page = 0
        self.pb.hide()
        self.search_btn.setEnabled(True)

        self._refresh_stats()
        self._update_counts()

        filled = self._capped()
        cut = self._cut_sources()
        note = self._skipped_note()
        if cut:
            self.sb.showMessage(
                f"已载入 {len(self.results):,} 条，按渠道分组；"
                + "、".join(f"{k} 只取了前 {n:,} 条（共 {t:,} 条）" for k, t, n in cut[:3])
                + "，点「再取更多」继续取" + note)
        else:
            self.sb.showMessage(
                f"已载入 {len(self.results):,} 条，按渠道分组；各渠道命中已全部取完"
                + (f"（读秀去重 {merged} 条）" if merged else "") + note)
        self.load_more_btn.setText(
            f"⬇ 再取更多（每渠道 +{FETCH_INCREMENT:,} 条）" if filled else "✅ 已取完")
        self.load_more_btn.show()
        self.load_more_btn.setEnabled(filled)
        self.loading_more = False
        self.more_available = filled
        self.auto_rounds = 0
        self.show_page()

    def show_page(self):
        if not self.results:
            self.table.setRowCount(0)
            self.page_label.setText("第 0/0 页")
            self.prev_btn.setEnabled(False)
            self.next_btn.setEnabled(False)
            return
        start = self.current_page * PAGE_SIZE
        end = min(start + PAGE_SIZE, len(self.results))
        page = self.results[start:end]

        self.table.setRowCount(len(page))
        for i, r in enumerate(page):
            si = QTableWidgetItem(r.source)
            color = CHANNEL_COLORS.get(r.source)
            if color:
                si.setForeground(QColor(color))
            self.table.setItem(i, 0, si)

            td = r.display_title()[:200]
            if r.source in ("学术信息数据库", "游氏古籍", "本地文件库") and r.filepath:
                td = _clean_path(r.filepath)
            self.table.setItem(i, 1, QTableWidgetItem(td))
            self.table.setItem(i, 2, QTableWidgetItem(r.author[:60] if r.author else ""))
            self.table.setItem(i, 3, QTableWidgetItem(r.publisher[:60] if r.publisher else ""))
            self.table.setItem(i, 4, QTableWidgetItem(r.year[:20] if r.year else ""))
            self.table.setItem(i, 5, QTableWidgetItem(r.ssid[:30] if r.ssid else ""))
            self.table.setCellWidget(i, 6, self._actions_for(r))

        self.page_label.setText(
            f"第 {self.current_page+1}/{self.total_pages} 页（{start+1}-{end}）"
        )
        self.prev_btn.setEnabled(self.current_page > 0)
        self.next_btn.setEnabled(self.current_page < self.total_pages - 1)
        QTimer.singleShot(0, self._auto_load_if_needed)

    # ---------- 自动加载更多（无限滚动） ----------
    def _on_scroll(self, _v=None):
        sb = self.table.verticalScrollBar()
        if sb.maximum() > 0 and sb.value() >= sb.maximum() - 2:
            self._auto_load_if_needed()
    def _auto_load_if_needed(self):
        """在「最后一页」且「已滚到底」时，自动取下一批（无需点按钮）

        其它页即使滚到底也不取（避免看旧页时列表被改）。
        最多自动跑 AUTO_MAX_ROUNDS 轮，之后仍可手动点按钮；
        用户手动翻页时 auto_rounds 会归零，再翻到最后一页还能继续自动取。
        """
        if not self.more_available or self.loading_more or not self.results:
            return
        if self.auto_rounds >= AUTO_MAX_ROUNDS:
            return
        if self.current_page < self.total_pages - 1:
            return  # 不在最后一页：不自动取
        sb = self.table.verticalScrollBar()
        rows_h = self.table.rowCount() * max(
            1, self.table.verticalHeader().defaultSectionSize())
        fits = rows_h <= max(1, self.table.viewport().height())
        at_bottom = ((sb.maximum() <= 0 and fits)
                     or (sb.maximum() > 0 and sb.value() >= sb.maximum() - 2))
        if at_bottom:
            self.auto_rounds += 1
            self.load_more()

    def _actions_for(self, r):
        """结果行右侧的「操作」列（没有可做的事就留空）"""
        acts = []
        if r.source == "本地文件库" and r.filepath:
            acts.append(("📂 打开所在文件夹", lambda: _open_in_explorer(r.filepath)))
        if r.source == "读秀" and r.ssid:
            acts.append(("📋 复制SSID", lambda: _copy_text(r.ssid, "已复制 SSID")))
        url = _row_url(r)
        if url:
            acts.append(("🌐 打开网页", lambda: _open_web(url)))
        if not acts:
            return None
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(2, 1, 2, 1)
        lay.setSpacing(4)
        for label, slot in acts:
            b = QPushButton(label)
            b.setFixedHeight(24)
            b.setFont(QFont("Microsoft YaHei", 8))
            b.clicked.connect(slot)
            lay.addWidget(b)
        return w

    def on_item_clicked(self, item):
        row = item.row()
        idx = self.current_page * PAGE_SIZE + row
        if idx < len(self.results):
            self.detail.show_result(self.results[idx])

    def on_cell_double_clicked(self, row, col):
        idx = self.current_page * PAGE_SIZE + row
        if idx < len(self.results):
            self.detail.show_result(self.results[idx])

    def prev_page(self):
        if self.current_page > 0:
            self.current_page -= 1
            self.auto_rounds = 0
            self.show_page()
            self.table.scrollToTop()

    def next_page(self):
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            self.auto_rounds = 0
            self.show_page()
            self.table.scrollToTop()

    def load_more(self):
        if self.loading_more:
            return
        self.loading_more = True
        self.load_more_btn.setEnabled(False)
        self.load_more_btn.setText("加载中...")
        self.pb.show()
        self.pb.setRange(0, 0)
        self.sb.showMessage(f"再取更多（每渠道 +{FETCH_INCREMENT:,} 条）...")

        self.lm_worker = LoadMoreWorker(self.kw, self.seen, (self.meta or {}).get('cap'),
                                        field=getattr(self, 'field', 'all'))
        self.lm_worker.finished.connect(self.on_more_done)
        self.lm_worker.start()

    def on_more_done(self, new_results, seen, meta=None):
        old_len = len(self.results)
        self.results.extend(new_results)
        self.seen = seen
        self.meta = meta or self.meta
        self.loading_more = False
        close_all()          # 用完就放掉数据库文件
        merged, _gone = self._dedup_rows()

        self.pb.hide()
        self._refresh_stats()
        self._update_counts()

        added = len(self.results) - old_len
        filled = self._capped()
        cnt = self.count_label.text()
        if added:
            cnt += f"（本轮新增 +{added}）"
        self.count_label.setText(cnt)
        cut = self._cut_sources()
        if cut:
            self.sb.showMessage(
                f"已载入 {len(self.results):,} 条，按渠道分组"
                + (f"（本轮新增 +{added}）" if added else "")
                + "；" + "、".join(
                    f"{k} 只取了前 {n:,} 条（共 {t:,} 条）" for k, t, n in cut[:3]))
        else:
            self.sb.showMessage(
                f"已载入 {len(self.results):,} 条，按渠道分组"
                + (f"（本轮新增 +{added}）" if added else "")
                + "；各渠道命中已全部取完")

        self.load_more_btn.setText(
            f"⬇ 再取更多（每渠道 +{FETCH_INCREMENT:,} 条）" if filled else "✅ 已取完")
        self.load_more_btn.setEnabled(filled)
        self.more_available = filled
        self.show_page()

    def export(self, fmt):
        """导出：先弹「导出选项」让用户勾要哪些字段，再把命中的**全部**结果写出去（不限 5,000）"""
        if not self.results:
            QMessageBox.information(self, "导出", "无结果")
            return
        if getattr(self, 'exp_worker', None) is not None and self.exp_worker.isRunning():
            QMessageBox.information(self, "导出", "上一次导出还在进行中，请稍等一下")
            return
        dlg = ExportOptionsDialog(self, load_export_fields())
        if dlg.exec_() != QDialog.Accepted:
            return
        fields = dlg.selected_fields()
        if not fields:
            QMessageBox.information(self, "导出", "至少要勾一个字段。")
            return
        save_export_fields(fields)
        fp, _ = QFileDialog.getSaveFileName(
            self, "导出（全部结果）", str(Path.home() / f"搜索结果.{fmt}"), f"*.{fmt}"
        )
        if not fp:
            return
        # 取全部 + 写文件放到后台线程（大词可能要几十秒，不让界面卡住）
        self.sb.showMessage("正在取全部命中结果（不限 5,000 条）并按勾选字段导出…")
        self.exp_worker = ExportWorker(self.kw, fmt, fp, self.results, fields,
                                       field=getattr(self, 'field', 'all'))
        self.exp_worker.done.connect(self.on_export_done)
        self.exp_worker.start()

    def on_export_done(self, ok, msg):
        close_all()          # 导出完也放掉数据库文件
        if ok:
            QMessageBox.information(self, "导出成功", msg)
            self.sb.showMessage(msg.replace("\n", "　"))
        else:
            QMessageBox.warning(self, "导出失败", msg)
            self.sb.showMessage("导出失败：" + msg)


def run():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    p = QPalette()
    p.setColor(QPalette.Window, QColor(240, 240, 240))
    p.setColor(QPalette.WindowText, Qt.black)
    app.setPalette(p)
    w = SearchApp()
    w.show()
    sys.exit(app.exec_())
