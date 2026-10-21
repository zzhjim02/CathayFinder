# -*- coding: utf-8 -*-
"""「本地文件库索引」页签 —— 原 CathayIndex 工具，现已并进 CathayFinder 主程序。

干嘛用的：把你自己的文件夹（子文件夹、孙文件夹……）里的文件目录做成库
「本地文件库」，建完就能在 CathayFinder 的「本地文件库」渠道里搜到它们。

界面照搬原来那个独立工具的：拖入/选择文件夹 → 开始建库 → 进度与日志 →
顺手搜一下验证。只是从 tkinter 换成了 PyQt5，好跟主程序长成一个样子。
"""
import os
import subprocess

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QListWidget,
    QLineEdit, QGroupBox, QRadioButton, QCheckBox, QProgressBar, QTextEdit,
    QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog, QMessageBox,
    QAbstractItemView,
)

from ..index import fileindex as IDX


class _DropList(QListWidget):
    """能接住拖进来的文件夹的列表。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.DropOnly)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
        else:
            super().dragEnterEvent(e)

    def dragMoveEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
        else:
            super().dragMoveEvent(e)

    def dropEvent(self, e):
        if not e.mimeData().hasUrls():
            super().dropEvent(e)
            return
        paths = [u.toLocalFile() for u in e.mimeData().urls()]
        self.parent()._add(paths) if isinstance(self.parent(), LocalIndexTab) else None
        e.acceptProposedAction()


class BuildWorker(QThread):
    """后台建库：索引引擎是纯 Python + sqlite，跑在线程里界面才不卡。"""

    log = pyqtSignal(str)
    progress = pyqtSignal(int, int)          # 已索引, 总数
    done = pyqtSignal(object)                # 统计 dict
    failed = pyqtSignal(str)

    def __init__(self, opts, parent=None):
        super().__init__(parent)
        self.opts = opts

    def run(self):
        o = self.opts
        try:
            st = IDX.build(
                o['roots'], o['out_db'], exts=o['exts'] or None,
                skip_hidden=o['skip_hidden'], mode=o['mode'],
                clean_deleted=o['clean_deleted'],
                progress=lambda d, t, n: self.progress.emit(int(d), int(t)),
                log=lambda s: self.log.emit(str(s)))
            self.done.emit(st)
        except Exception as e:
            self.failed.emit(str(e))


class LocalIndexTab(QWidget):
    """主程序里的「本地文件库索引」页签。

    on_db_changed: 建完库回调（主界面用它去刷新渠道可用性，让「本地文件库」
    渠道不用重启就亮起来）。
    """

    def __init__(self, parent=None, on_db_changed=None):
        super().__init__(parent)
        self.roots = []
        self.working = False
        self.worker = None
        self.on_db_changed = on_db_changed
        self._build_ui()

    # ── 界面 ──────────────────────────────────────────────
    def _build_ui(self):
        v = QVBoxLayout(self)

        tip = QLabel(
            '把文件夹拖进下面的框（或点「添加文件夹」）。子文件夹、孙文件夹里的文件\n'
            '都会收进库「%s」。默认就写进本程序自己的库目录，建完直接在「检索」页\n'
            '勾上「%s」渠道就能搜。' % (IDX.LIB_LABEL, IDX.LIB_LABEL))
        tip.setStyleSheet('color:#2f4858;')
        v.addWidget(tip)

        # 根文件夹
        box = QGroupBox('要建库的文件夹')
        hb = QHBoxLayout(box)
        self.lst = _DropList(self)
        hb.addWidget(self.lst, 1)
        bb = QVBoxLayout()
        for txt, slot in (('添加文件夹', self.add_folder),
                          ('移除选中', self.remove_sel),
                          ('清空', self.clear_all)):
            b = QPushButton(txt)
            b.clicked.connect(slot)
            bb.addWidget(b)
        bb.addStretch(1)
        hb.addLayout(bb)
        v.addWidget(box, 2)

        # 参数
        opt = QGroupBox('参数')
        og = QVBoxLayout(opt)

        r1 = QHBoxLayout()
        r1.addWidget(QLabel('库写到哪儿（默认就是本程序）：'))
        self.ed_out = QLineEdit(IDX.find_cathayfinder_dir() or '')
        self.ed_out.textChanged.connect(self._refresh_db_label)
        r1.addWidget(self.ed_out, 1)
        b1 = QPushButton('浏览…')
        b1.clicked.connect(self.pick_out_dir)
        r1.addWidget(b1)
        b2 = QPushButton('用本程序')
        b2.setToolTip('改回本程序自己的库目录')
        b2.clicked.connect(self.auto_out_dir)
        r1.addWidget(b2)
        og.addLayout(r1)

        self.lbl_db = QLabel('')
        self.lbl_db.setStyleSheet('color:#2f4858;')
        og.addWidget(self.lbl_db)

        r2 = QHBoxLayout()
        r2.addWidget(QLabel('方式：'))
        self.rb_full = QRadioButton('全量重建')
        self.rb_inc = QRadioButton('增量更新（只加新增/变化的）')
        self.rb_full.setChecked(True)
        r2.addWidget(self.rb_full)
        r2.addWidget(self.rb_inc)
        r2.addSpacing(16)
        r2.addWidget(QLabel('只收这些扩展名：'))
        self.ed_ext = QLineEdit('')
        self.ed_ext.setPlaceholderText('留空=全部文件，例：pdf,epub,azw3,djvu,txt')
        r2.addWidget(self.ed_ext, 1)
        og.addLayout(r2)

        r3 = QHBoxLayout()
        self.cb_hidden = QCheckBox('跳过隐藏文件夹与系统目录'
                                   '（$RECYCLE.BIN、System Volume Information 等）')
        self.cb_hidden.setChecked(True)
        self.cb_clean = QCheckBox('增量时清理已不存在的记录')
        self.cb_clean.setChecked(True)
        r3.addWidget(self.cb_hidden)
        r3.addWidget(self.cb_clean)
        r3.addStretch(1)
        og.addLayout(r3)

        v.addWidget(opt)

        # 动作
        act = QHBoxLayout()
        self.btn = QPushButton('开始建库')
        self.btn.setFixedHeight(34)
        self.btn.clicked.connect(self.start)
        act.addWidget(self.btn)
        self.pb = QProgressBar()
        self.pb.setRange(0, 1)
        self.pb.setValue(0)
        act.addWidget(self.pb, 1)
        self.lbl_stat = QLabel('就绪')
        self.lbl_stat.setStyleSheet('color:#2f4858;')
        act.addWidget(self.lbl_stat)
        v.addLayout(act)

        # 日志
        lg = QGroupBox('日志')
        lh = QVBoxLayout(lg)
        self.txt = QTextEdit()
        self.txt.setReadOnly(True)
        self.txt.setFixedHeight(120)
        lh.addWidget(self.txt)
        v.addWidget(lg, 1)

        # 迷你检索
        sf = QGroupBox('建好之后，在这儿试搜一下（和 CathayFinder 同一套匹配）')
        sv = QVBoxLayout(sf)
        sr = QHBoxLayout()
        self.ed_kw = QLineEdit()
        self.ed_kw.returnPressed.connect(self.do_search)
        sr.addWidget(self.ed_kw, 1)
        b3 = QPushButton('搜索')
        b3.clicked.connect(self.do_search)
        sr.addWidget(b3)
        b4 = QPushButton('打开所在文件夹')
        b4.clicked.connect(self.open_sel)
        sr.addWidget(b4)
        sv.addLayout(sr)
        self.tv = QTableWidget(0, 3)
        self.tv.setHorizontalHeaderLabels(['文件名', '大小 / 修改时间', '路径'])
        self.tv.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.tv.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.tv.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.tv.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tv.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tv.doubleClicked.connect(self.open_sel)
        sv.addWidget(self.tv, 1)
        v.addWidget(sf, 2)

        self._refresh_db_label()

    # ── 文件夹 ────────────────────────────────────────────
    def add_folder(self):
        d = QFileDialog.getExistingDirectory(self, '选择要建库的文件夹')
        if d:
            self._add([d])

    def _add(self, paths):
        n = 0
        for p in paths or []:
            p = os.path.abspath(p)
            if os.path.isdir(p) and p not in self.roots:
                self.roots.append(p)
                self.lst.addItem(p)
                n += 1
        if n:
            self.log('已添加 %d 个文件夹' % n)

    def remove_sel(self):
        rows = sorted({i.row() for i in self.lst.selectedIndexes()}, reverse=True)
        for i in rows:
            self.lst.takeItem(i)
            try:
                del self.roots[i]
            except IndexError:
                pass

    def clear_all(self):
        self.lst.clear()
        self.roots = []

    # ── 参数 ──────────────────────────────────────────────
    def out_dir(self):
        d = (self.ed_out.text() or '').strip().strip('"')
        return os.path.abspath(d) if d else ''

    def db_path(self):
        d = self.out_dir()
        return IDX.cathayfinder_db_path(d) if d else IDX.default_db_path()

    def _refresh_db_label(self):
        self.lbl_db.setText('→ 库文件：%s' % self.db_path())

    def pick_out_dir(self):
        d = QFileDialog.getExistingDirectory(
            self, '选择 CathayFinder 所在的文件夹（里面有 CathayFinder.exe / data\\db）')
        if not d:
            return
        d = os.path.abspath(d)
        if not IDX.looks_like_cathayfinder(d):
            if QMessageBox.question(
                    self, '确认位置',
                    '这个文件夹里没看到 CathayFinder.exe / data\\db：\n%s\n\n'
                    '确认就用它吗？（会在里面新建 data\\db\\）' % d,
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No) != QMessageBox.Yes:
                return
        self.ed_out.setText(d)
        IDX.save_tool_settings({'cathayfinder_dir': d})

    def auto_out_dir(self):
        IDX.save_tool_settings({'cathayfinder_dir': ''})
        d = IDX.find_cathayfinder_dir()
        self.ed_out.setText(d or '')
        self.log('已改回本程序的库目录：%s' % (d or '（没找到）'))

    # ── 日志 ──────────────────────────────────────────────
    def log(self, s):
        self.txt.append(str(s))

    # ── 建库 ──────────────────────────────────────────────
    def read_opts(self):
        return dict(
            roots=list(self.roots),
            out_db=self.db_path(),
            mode='inc' if self.rb_inc.isChecked() else 'full',
            exts=[e.strip() for e in self.ed_ext.text().replace('，', ',').split(',')
                  if e.strip()],
            skip_hidden=bool(self.cb_hidden.isChecked()),
            clean_deleted=bool(self.cb_clean.isChecked()),
        )

    def start(self):
        if self.working:
            return
        o = self.read_opts()
        if not o['roots']:
            QMessageBox.information(self, '建库', '先添加至少一个文件夹')
            return
        self.working = True
        self.btn.setEnabled(False)
        self.pb.setRange(0, 1)
        self.pb.setValue(0)
        self.lbl_stat.setText('准备中…')
        self.log('—' * 60)
        w = BuildWorker(o, self)
        w.log.connect(self.log)
        w.progress.connect(self._on_progress)
        w.done.connect(self._finish)
        w.failed.connect(self._fail)
        w.finished.connect(self._cleanup)
        self.worker = w
        w.start()

    def _on_progress(self, done, total):
        if total:
            self.pb.setRange(0, int(total))
            self.pb.setValue(int(done))
            self.lbl_stat.setText('已索引 %d / %d' % (done, total))

    def _cleanup(self):
        self.working = False
        self.btn.setEnabled(True)
        self.worker = None

    def _fail(self, msg):
        self.lbl_stat.setText('出错')
        self.log('出错：%s' % msg)
        QMessageBox.critical(self, '建库失败', str(msg))

    def _finish(self, st):
        self.pb.setValue(self.pb.maximum())
        self.lbl_stat.setText('完成：新增 %d / 共 %d' % (st['added'], st['total']))
        self.log('库文件：%s（%s）' % (st['db'], IDX.human(st['db_size'])))
        self.log('一共收录 %d 个文件（新增 %d，更新 %d，清理 %d，耗时 %.1f 秒）'
                 % (st['total'], st['added'], st['updated'], st['deleted'],
                    st['elapsed']))
        if os.path.basename(os.path.dirname(os.path.abspath(st['db']))) == 'db':
            self.log('★ 库已放进 CathayFinder 的库目录，「%s」渠道现在就能用了。'
                     % IDX.LIB_LABEL)
        # 让主界面重新认一遍库文件：渠道不用重启就亮起来
        if callable(self.on_db_changed):
            try:
                self.on_db_changed()
            except Exception:
                pass
        QMessageBox.information(self, '建库完成',
                                '收录 %d 个文件\n库文件：%s' % (st['total'], st['db']))

    # ── 迷你检索 ──────────────────────────────────────────
    def do_search(self):
        kw = self.ed_kw.text().strip()
        if not kw:
            return
        db = self.db_path()
        self.tv.setRowCount(0)
        rows = IDX.search_db(db, kw, limit=200)
        self.tv.setRowCount(len(rows))
        for i, (name, path, extra) in enumerate(rows):
            self.tv.setItem(i, 0, QTableWidgetItem(name))
            self.tv.setItem(i, 1, QTableWidgetItem(extra or ''))
            it = QTableWidgetItem(path)
            it.setData(Qt.UserRole, path)
            self.tv.setItem(i, 2, it)
        self.log('搜索「%s」→ %d 条' % (kw, len(rows)))

    def open_sel(self, _idx=None):
        r = self.tv.currentRow()
        if r < 0:
            return
        it = self.tv.item(r, 2)
        path = it.data(Qt.UserRole) if it is not None else ''
        if not path:
            return
        try:
            if os.path.isfile(path):
                subprocess.Popen(['explorer', '/select,',
                                  os.path.normpath(path)])
            elif os.path.isdir(path):
                os.startfile(path)
        except Exception as e:
            QMessageBox.warning(self, '打开', str(e))
