#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CathayFinder - 综合性图书检索引擎"""

import sys
import os

# Ensure the project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

if __name__ == "__main__":
    if "--selftest" in sys.argv:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:                      # 控制台有可能是 GBK，避免 emoji 把打印弄崩
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
        lines = []
        try:
            lines.append("frozen=%s" % getattr(sys, "frozen", False))
            lines.append("python=%s" % sys.version.split()[0])
            from cathayfinder.ui.app_gui import icon_path
            _ip = icon_path()
            icon_ok = bool(_ip)
            lines.append("icon=%s" % (_ip or "缺失"))
            from PyQt5.QtWidgets import QApplication
            from cathayfinder.ui.app_gui import SearchApp
            app = QApplication([])
            w = SearchApp()
            lines.append("gui=OK 渠道数=%d" % len(w.source_group.checkboxes))
            # 「操作」列自检：本地文件库行有「打开所在文件夹」按钮，读秀行有「打开网页」按钮
            from PyQt5.QtWidgets import QPushButton
            from cathayfinder.search.engine import SearchResult
            probe = [
                SearchResult(source="本地文件库", title="甲.pdf", filename="甲.pdf",
                             filepath=r"C:\Windows\notepad.exe", extra="1 B"),
                SearchResult(source="读秀", title="乙", ssid="14296873"),
                SearchResult(source="学术信息数据库", title="丙", filepath="/x/丙.pdf"),
            ]
            w.meta = {"cap": 2000, "totals": {"本地文件库": {"total": 1, "loaded": 1},
                                              "读秀": {"total": 9, "loaded": 1},
                                              "学术信息数据库": {"total": 3, "loaded": 1}}}
            w.results = probe
            w.total_pages = 1
            w.current_page = 0
            w.show_page()
            cols = [w.table.horizontalHeaderItem(i).text()
                    for i in range(w.table.columnCount())]
            acts = []
            for i in range(w.table.rowCount()):
                cw = w.table.cellWidget(i, 6)
                acts.append([b.text() for b in cw.findChildren(QPushButton)] if cw else [])
            w.detail.show_result(probe[1])
            dbtns = [b.text() for b in w.detail.btn_lay.parentWidget().findChildren(QPushButton)]
            lines.append("action-col=列%d 表头%s 行按钮%s 读秀详情按钮%s"
                         % (w.table.columnCount(), cols[-1], acts, dbtns))
            # 详情页的渠道说明（学术信息数据库 / 华中师大近史所 / 读秀）
            from cathayfinder.ui.app_gui import CHANNEL_NOTES
            note_bad = []
            for src, txt in CHANNEL_NOTES.items():
                rr = SearchResult(source=src, title="样例", ssid="14296873",
                                  filepath=r"C:\Windows\notepad.exe")
                w.detail.show_result(rr)
                if txt not in w.detail.text.toPlainText():
                    note_bad.append(src)
            lines.append("notes=%s" % ("OK" if not note_bad else "FAIL" + str(note_bad)))
            from cathayfinder.search import engine as E
            for kw in ("布罗代尔", "年鉴学派"):
                res, _seen, meta = E.search(kw)
                cnt = {}
                for r in res:
                    cnt[r.source] = cnt.get(r.source, 0) + 1
                lines.append("search[%s]=已载%d 条 命中%d 条 %s"
                             % (kw, len(res),
                                sum(t['total'] for t in meta['totals'].values()),
                                sorted(cnt.items(), key=lambda x: -x[1])))
                lines.append("  各渠道(已载/命中)=%s"
                             % {k: '%d/%d' % (v['loaded'], v['total'])
                                for k, v in sorted(
                                    meta['totals'].items(),
                                    key=lambda x: E.PRIORITY_MAP.get(
                                        E.NAME_MAP.get(x[0], ''), 9999))})
            # 导出用去重自检：仅「读秀」按 8 位 SSID 去重，其它渠道一条不能少
            res, _seen2, meta2 = E.search("布罗代尔")
            rows, merged = E.dedup_export(res)
            seen = set()
            dups = 0
            for r in rows:
                sid = (r.ssid or '').strip()
                if r.source == "读秀" and len(sid) == 8 and sid.isdigit():
                    if sid in seen:
                        dups += 1
                    seen.add(sid)
            other_before = len([r for r in res if r.source != "读秀"])
            other_after = len([r for r in rows if r.source != "读秀"])
            lines.append("export-dedup=读秀 %d→%d 条（并掉 %d），其它渠道 %d→%d，重复SSID=%d"
                         % (len([r for r in res if r.source == "读秀"]),
                            len([r for r in rows if r.source == "读秀"]),
                            merged, other_before, other_after, dups))
            # 屏幕列表去重自检（走真实 on_search_done）
            w.on_search_done(res, _seen2, meta2)
            d2 = 0
            s8 = set()
            for r in w.results:
                sid = (r.ssid or '').strip()
                if r.source == "读秀" and len(sid) == 8 and sid.isdigit():
                    if sid in s8:
                        d2 += 1
                    s8.add(sid)
            o2 = len([r for r in w.results if r.source != "读秀"])
            dkeys = [E.alpha_key(r) for r in w.results if r.source == "读秀"]
            ordered = all(dkeys[i] <= dkeys[i + 1] for i in range(len(dkeys) - 1))
            lines.append("display-dedup=读秀 %d→%d 条，其它渠道 %d，重复SSID=%d，标签=%s"
                         % (len([r for r in res if r.source == "读秀"]),
                            len([r for r in w.results if r.source == "读秀"]),
                            o2, d2, w.count_label.text()))
            lines.append("pinyin=%s" % ("可用" if E._lazy_pinyin is not None else "降级(词典序)"))
            # 导出字段可选自检：只勾部分字段时，文件里就只有那几列（其余字段不出现）
            import csv as _csv3
            import tempfile as _tf3
            from cathayfinder.ui import app_gui as _G3
            _fpath3 = os.path.join(_tf3.gettempdir(), "_cf_field_test.csv")
            _rows3 = list(w.results[:3])
            _n3 = _G3._write_export(_fpath3, "csv", _rows3, "布罗代尔", 0,
                                    ["title", "ssid"])
            with open(_fpath3, encoding="utf-8-sig", newline="") as _fh3:
                _head3 = next(_csv3.reader(_fh3))
            _pref3 = all(k in dict(_G3.EXPORT_FIELDS) for k in _G3.load_export_fields())
            fields_ok = (_head3 == ["书名", "SSID"] and _n3 == len(_rows3) and _pref3)
            _n4 = _G3._write_export(_fpath3, "txt", _rows3, "布罗代尔", 0, ["title"])
            with open(_fpath3, encoding="utf-8") as _fh4:
                _only_title = ("SSID" not in _fh4.read())
            fields_ok = fields_ok and _only_title
            lines.append("export-fields=可选%d 个字段；只勾书名+SSID→表头%s 行数%d；只勾书名时无其它字段=%s"
                         % (len(_G3.EXPORT_FIELDS), _head3, _n3, _only_title))
            # 库文件被删 → 置灰 + 不勾选（搜索也会跳过）
            from cathayfinder.data.db_manager import channel_available as _avail
            _ok_bogus, _miss_bogus = _avail("no_such_channel")
            _G4 = _G3
            _orig_avail = _G4.channel_available
            _G4.channel_available = lambda k: ((False, ["fake_zhwiki.db"])
                                               if k == "zhwiki" else _orig_avail(k))
            w.source_group.refresh_availability()
            _cb = w.source_group.checkboxes["zhwiki"]
            gray_ok = (not _cb.isEnabled()) and (not _cb.isChecked())
            _G4.channel_available = _orig_avail
            w.source_group.refresh_availability()
            back_ok = w.source_group.checkboxes["zhwiki"].isEnabled()
            dbmiss_ok = (not _ok_bogus) and gray_ok and back_ok
            lines.append("db-missing=不存在渠道 ok=%s；缺失时置灰+未勾选=%s；放回后恢复=%s"
                         % (_ok_bogus, gray_ok, back_ok))
            # 导出不限量自检：全量取回（cap<=0）→ 去重后条数应 >= 屏幕上那份
            res_all, _seen3, meta_all = E.search("布罗代尔", cap=-1)
            rows_all, merged_all = E.tidy_results(res_all)
            per_all = {}
            for r in res_all:
                per_all[r.source] = per_all.get(r.source, 0) + 1
            export_all_ok = bool(meta_all.get("unlimited")) and len(res_all) > len(w.results)
            lines.append(
                "export-all=不限量取回 %d 条（去重后 %d，合并 %d） vs 屏幕 %d 条；unlimited=%s 渠道=%s"
                % (len(res_all), len(rows_all), merged_all, len(w.results),
                   meta_all.get("unlimited"), sorted(per_all.items())))
            # 字段检索自检：书名 / 作者 / 出版者 / SSID（只看指定字段）
            def _check_field(kw, fld, getter):
                rr, _ss, _mm = E.search(kw, field=fld)
                bad = [r for r in rr if kw not in (getter(r) or "")]
                return len(rr), len(bad)

            n_t, bad_t = _check_field("布罗代尔", "title",
                                      lambda r: (r.title or "") + (r.filename or "") + (r.name or ""))
            n_a, bad_a = _check_field("布罗代尔", "author", lambda r: r.author)
            n_p, bad_p = _check_field("中华书局", "publisher", lambda r: r.publisher)
            n_s, bad_s = _check_field("14296873", "ssid", lambda r: r.ssid)
            fields_ok2 = (n_a > 0 and n_p > 0 and n_s > 0 and n_t > 0
                          and not (bad_t or bad_a or bad_p or bad_s))
            lines.append(
                "field-search=书名%d条(越界%d) 作者%d条(越界%d) 出版者%d条(越界%d) SSID%d条(越界%d)"
                % (n_t, bad_t, n_a, bad_a, n_p, bad_p, n_s, bad_s))
            keys = [E.PRIORITY_MAP.get(E.NAME_MAP.get(r.source, ""), 9999)
                    for r in w.results]
            grouped = all(keys[i] <= keys[i + 1] for i in range(len(keys) - 1))
            runs = []
            for r in w.results:
                if not runs or runs[-1] != r.source:
                    runs.append(r.source)
            lines.append("grouped-by-channel=%s 渠道顺序:%s" % (grouped, runs))
            lines.append("count-label=%s" % w.count_label.text())
            lines.append("duxiu-sort=按A→Z有序:%s 前3条:%s"
                         % (ordered,
                            [ (E._name_of(r))[:18] for r in w.results if r.source == "读秀"][:3]))
            if (dups or other_before != other_after or d2 or o2 != other_before
                    or not ordered or not grouped or w.table.columnCount() != 7
                    or acts[0] != ["📂 打开所在文件夹"] or acts[1] != ["📋 复制SSID"]
                    or acts[2] != [] or dbtns != ["📋 复制 SSID"]
                    or note_bad or not export_all_ok or not fields_ok
                    or not dbmiss_ok or not icon_ok or not fields_ok2):
                lines.append("result=FAIL")
            else:
                lines.append("result=OK")
        except Exception as e:
            import traceback
            lines.append("ERROR %r" % (e,))
            lines.append(traceback.format_exc())
            lines.append("result=FAIL")
        with open(os.path.join(
                os.path.dirname(sys.executable) if getattr(sys, "frozen", False)
                else PROJECT_ROOT, "_selftest.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        print("\n".join(lines))
        raise SystemExit(0)

    from cathayfinder.ui.app_gui import run
    run()
