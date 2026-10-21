# -*- coding: utf-8 -*-
"""本地文件库索引器（引擎）—— 原 CathayIndex，现已并进 CathayFinder 主程序。

把某个文件夹（含它的子文件夹、孙文件夹……）里的文件目录做成一个 SQLite 库，
库名固定为「本地文件库」。库结构与 CathayFinder 其他库完全一致
（items 表 + contentless FTS5 的 items_fts 表），所以建好的库可以直接被
CathayFinder 当做一个新渠道来检索（渠道名：本地文件库）。

并进来之后跟原来那个独立小工具有两点不同：
  · CathayFinder 的位置不用再问用户了 —— 默认就是**本程序自己**（PROJECT_ROOT），
    库直接写进 <本程序>\\data\\db\\local_files.db，建完就能在「本地文件库」渠道搜；
  · 设置（用户另外指定的输出目录）记在程序目录下的 cathayindex_settings.json。

命令行（调试用）：
    python -m cathayfinder.index.fileindex --cli "D:\\我的书" [--out 库文件路径]
                      [--mode full|inc] [--ext pdf,epub,txt] [--keep-hidden]
    python -m cathayfinder.index.fileindex --selftest
"""
import os
import re
import sqlite3
import sys
import time

try:                       # 作为包被 import 时拿 CathayFinder 的路径配置
    from ..config import PROJECT_ROOT, DB_DIR
except ImportError:        # 直接当脚本跑（python fileindex.py ...）
    PROJECT_ROOT = None
    DB_DIR = None

APP_TITLE = "CathayIndex · 本地文件库索引工具"
APP_VERSION = "v1.0.0"
LIB_LABEL = "本地文件库"                 # 库/渠道名称
LIB_FILENAME = "local_files.db"          # 装进 CathayFinder 库目录时用的文件名
LOCAL_DB_NAME = "本地文件库.db"           # 放在别处时的默认文件名

# 建索引时跳过的目录（系统/回收站/版本库/临时目录等）
SKIP_DIRS = {
    "$RECYCLE.BIN", "System Volume Information", "$WinREAgent", "Config.Msi",
    "Recovery", "found.000", "found.001", ".git", ".svn", ".hg", "__pycache__",
    "node_modules", ".cache", ".tmp", "Temp", "tmp", "MSOCache",
}

# 与 CathayFinder 的引擎保持一致：标点/空白在索引里一律去掉，然后逐字加空格，
# 这样查询 "布罗代尔" 会被展开成短语 "布 罗 代 尔" 去精准匹配。
_PUNCT_RE = re.compile(
    r"""[\s"'`~!@#$%^&*()\-_+=\[\]{}\\|;:,.<>/?，。、；：！？（）【】《》“”‘’·—…]+""",
    re.UNICODE)

BATCH = 2000


# ───────────────────────────── 小工具 ─────────────────────────────

def fts_text(*parts):
    """把文本转成 FTS 索引文本（去标点 + 逐字加空格）"""
    s = ' '.join(p for p in parts if p)
    s = _PUNCT_RE.sub('', s)
    return ' '.join(s)


def human(n):
    n = float(n or 0)
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if n < 1024 or unit == 'TB':
            return ('%.0f %s' % (n, unit)) if unit == 'B' else ('%.1f %s' % (n, unit))
        n /= 1024


def norm_ext(name):
    e = os.path.splitext(name)[1].lower()
    return e[1:] if e.startswith('.') else e


def _app_root():
    """CathayFinder 的程序目录：打包后是 exe 所在目录，源码运行时是项目根。"""
    if PROJECT_ROOT is not None:
        return str(PROJECT_ROOT)
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def tool_settings_path():
    return os.path.join(_app_root(), 'cathayindex_settings.json')


def load_tool_settings():
    """读工具自己的设置（记住用户选过的 CathayFinder 位置）"""
    import json
    try:
        with open(tool_settings_path(), 'r', encoding='utf-8') as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def save_tool_settings(patch):
    import json
    d = load_tool_settings()
    d.update(patch or {})
    try:
        with open(tool_settings_path(), 'w', encoding='utf-8') as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    return d


def looks_like_cathayfinder(d):
    """判断这个目录本身是不是 CathayFinder（程序目录 / 安装目录）"""
    if not d or not os.path.isdir(d):
        return False
    if os.path.isdir(os.path.join(d, 'data', 'db')):
        return True
    try:
        lows = [n.lower() for n in os.listdir(d)]
    except OSError:
        return False
    # 安装版：目录里有 CathayFinder*.exe；源码版：有 main.py + cathayfinder 包
    if any(n.startswith('cathayfinder') and n.endswith('.exe') for n in lows):
        return True
    return 'main.py' in lows and 'cathayfinder' in lows


def find_cathayfinder_dir():
    """CathayFinder 在哪：并进主程序后**默认就是本程序自己**。

    只有用户另外指定了输出目录（想把库放别处）时才用那个目录；都没指定就
    回退到"按老办法扫一遍常见安装位置"（给单独跑这个模块调试时用）。
    """
    import glob
    remembered = (load_tool_settings().get('cathayfinder_dir') or '').strip()
    here = os.path.dirname(os.path.abspath(__file__))
    cands = [remembered, _app_root(), here, os.path.dirname(here),
             os.path.dirname(_app_root()),
             r"D:\我的软件创作库\CathayFinder-DEV"]
    for pat in (r"D:\我的软件创作库\*CathayFinder*",
                r"D:\Program Files\*CathayFinder*",
                r"C:\Program Files\*CathayFinder*"):
        cands += sorted(glob.glob(pat))
    for c in cands:
        c = (c or '').strip().strip('"')
        if looks_like_cathayfinder(c):
            return os.path.abspath(c)
    return None


def cathayfinder_db_path(cf_dir):
    r"""由 CathayFinder 目录推出库文件路径：<它>\data\db\local_files.db"""
    return os.path.join(os.path.abspath(cf_dir), 'data', 'db', LIB_FILENAME)


def find_cathayfinder_db_dir():
    """CathayFinder 的库目录（data/db），找不到返回 None"""
    d = find_cathayfinder_dir()
    if d:
        db = os.path.join(d, 'data', 'db')
        if os.path.isdir(db):
            return db
        return None
    here = os.path.dirname(os.path.abspath(__file__))
    c = os.path.join(here, 'data', 'db')
    return c if os.path.isdir(c) else None


def default_db_path():
    """默认库文件：本程序自己的库目录 data\\db\\local_files.db。"""
    if DB_DIR is not None and str(DB_DIR):
        return os.path.join(str(DB_DIR), LIB_FILENAME)
    d = find_cathayfinder_dir()
    if d:
        return cathayfinder_db_path(d)
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, LOCAL_DB_NAME)


def _clean_root(p):
    p = os.path.abspath(p)
    return p.rstrip('\\/')


# ───────────────────────────── 扫描 ─────────────────────────────

def iter_files(root, exts=None, skip_hidden=True, skip_paths=None):
    """递归列出 root 下的所有文件（生成 (filepath, filename, size, mtime)）"""
    exts = set(e.lower().lstrip('.') for e in exts) if exts else None
    skip = set(os.path.normcase(p) for p in (skip_paths or []))
    stack = [_clean_root(root)]
    seen_dirs = set()
    while stack:
        d = stack.pop()
        try:
            key = os.path.normcase(os.path.realpath(d))
        except OSError:
            key = os.path.normcase(d)
        if key in seen_dirs:          # 防目录环（软链接/交接点）
            continue
        seen_dirs.add(key)
        try:
            with os.scandir(d) as it:
                for ent in it:
                    name = ent.name
                    try:
                        if ent.is_dir(follow_symlinks=False):
                            if name in SKIP_DIRS:
                                continue
                            if skip_hidden and (name.startswith('.') or name.startswith('$')):
                                continue
                            stack.append(ent.path)
                        elif ent.is_file(follow_symlinks=False):
                            if skip and os.path.normcase(ent.path) in skip:
                                continue
                            if skip_hidden and name.startswith('.'):
                                continue
                            if exts and norm_ext(name) not in exts:
                                continue
                            st = ent.stat()
                            yield (ent.path, name, st.st_size,
                                   time.strftime('%Y-%m-%d %H:%M',
                                                 time.localtime(st.st_mtime)))
                    except OSError:
                        continue
        except (OSError, PermissionError):
            continue


def count_files(root, exts=None, skip_hidden=True):
    """快速估算文件数（不读元数据，只为了进度条有个分母）"""
    exts = set(e.lower().lstrip('.') for e in exts) if exts else None
    stack = [root]
    seen = set()
    n = 0
    while stack:
        d = stack.pop()
        try:
            key = os.path.normcase(os.path.realpath(d))
        except OSError:
            key = os.path.normcase(d)
        if key in seen:
            continue
        seen.add(key)
        try:
            with os.scandir(d) as it:
                for ent in it:
                    try:
                        if ent.is_dir(follow_symlinks=False):
                            if ent.name not in SKIP_DIRS and not (
                                    skip_hidden and (ent.name.startswith('.')
                                                     or ent.name.startswith('$'))):
                                stack.append(ent.path)
                        elif ent.is_file(follow_symlinks=False):
                            if skip_hidden and ent.name.startswith('.'):
                                continue
                            if exts and norm_ext(ent.name) not in exts:
                                continue
                            n += 1
                    except OSError:
                        continue
        except (OSError, PermissionError):
            continue
    return n


# ───────────────────────────── 建库 ─────────────────────────────

_SCHEMA = """
CREATE TABLE items (
    filename TEXT, filepath TEXT, account TEXT, title TEXT,
    ext TEXT, size INTEGER, mtime TEXT, extra TEXT
);
CREATE INDEX idx_lf_path ON items(filepath);
CREATE INDEX idx_lf_fn   ON items(filename);
CREATE VIRTUAL TABLE items_fts USING fts5(title, filename, filepath, account, content="", contentless_delete=1);
"""


def _open(out_db, rebuild):
    tmp = out_db + '.building'
    if rebuild:
        for p in (tmp, tmp + '-journal', tmp + '-wal', tmp + '-shm'):
            if os.path.exists(p):
                os.remove(p)
        conn = sqlite3.connect(tmp)
        conn.execute("PRAGMA journal_mode=OFF")
        conn.execute("PRAGMA synchronous=OFF")
        conn.executescript(_SCHEMA)
        return conn, tmp
    conn = sqlite3.connect(out_db)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=OFF")
    have = conn.execute("SELECT name FROM sqlite_master WHERE name='items'").fetchall()
    if not have:
        conn.executescript(_SCHEMA)
    return conn, out_db


def _fts_row(conn, rid, title, filename, filepath, account):
    conn.execute(
        "INSERT INTO items_fts(rowid, title, filename, filepath, account)"
        " VALUES (?,?,?,?,?)",
        (rid, fts_text(title), fts_text(filename), fts_text(filepath),
         fts_text(account)))


def build(roots, out_db=None, exts=None, skip_hidden=True, mode="full",
          clean_deleted=True, progress=None, log=None):
    """建库。mode: 'full' 全量重建 / 'inc' 增量更新（只加新增与变化的，逐个记住 mtime）
    progress(done, total, note) 可选；log(text) 可选。
    返回统计 dict。"""
    roots = [r for r in (roots or []) if r and os.path.isdir(r)]
    if not roots:
        raise ValueError("没有可索引的文件夹")
    out_db = out_db or default_db_path()
    os.makedirs(os.path.dirname(out_db) or '.', exist_ok=True)
    rebuild = (mode != 'inc')
    if (not rebuild) and (not os.path.exists(out_db)):
        rebuild = True

    t0 = time.time()
    out_db = os.path.abspath(out_db)
    skip_paths = [out_db, out_db + '.building', out_db + '.bak'] + \
                 [out_db + s for s in ('-journal', '-wal', '-shm')]
    total = 0
    for r in roots:
        total += count_files(r, exts, skip_hidden)
    if log:
        log('共 %d 个文件待索引（%d 个根文件夹），库：%s' % (total, len(roots), out_db))
        log('模式：%s' % ('全量重建' if rebuild else '增量更新'))

    conn, real = _open(out_db, rebuild)
    old = {}
    if not rebuild:
        try:
            for p, s, m in conn.execute("SELECT filepath, size, mtime FROM items"):
                old[p] = (s, m)
        except Exception:
            old = {}
        if log:
            log('库里已有 %d 条记录' % len(old))

    added = updated = deleted = skipped = errors = 0
    done = 0
    seen_paths = set()
    try:
        for root in roots:
            account = os.path.basename(_clean_root(root)) or _clean_root(root)
            pending = 0
            for path, name, size, mtime in iter_files(root, exts, skip_hidden,
                                                      skip_paths):
                seen_paths.add(path)
                cur = old.get(path)
                if cur is not None and cur[0] == size and cur[1] == mtime:
                    skipped += 1
                    done += 1
                    if progress and done % 500 == 0:
                        progress(done, total, name)
                    continue
                try:
                    if cur is None:
                        rid = conn.execute(
                            "INSERT INTO items(filename,filepath,account,title,ext,size,mtime,extra)"
                            " VALUES (?,?,?,?,?,?,?,?)",
                            (name, path, account, name, norm_ext(name), size, mtime,
                             '%s  %s' % (human(size), mtime))).lastrowid
                        added += 1
                    else:
                        conn.execute(
                            "UPDATE items SET filename=?, account=?, title=?, ext=?,"
                            " size=?, mtime=?, extra=? WHERE filepath=?",
                            (name, account, name, norm_ext(name), size, mtime,
                             '%s  %s' % (human(size), mtime), path))
                        rid = conn.execute(
                            "SELECT rowid FROM items WHERE filepath=?", (path,)).fetchone()[0]
                        conn.execute("DELETE FROM items_fts WHERE rowid=?", (rid,))
                        updated += 1
                    _fts_row(conn, rid, name, name, path, account)
                    pending += 1
                    if pending >= BATCH:
                        conn.commit()
                        pending = 0
                except Exception:
                    errors += 1
                done += 1
                if progress and done % 500 == 0:
                    progress(done, total, name)
            conn.commit()

        if (not rebuild) and clean_deleted and old:
            gone = [p for p in old if p not in seen_paths]
            for p in gone:
                row = conn.execute("SELECT rowid FROM items WHERE filepath=?", (p,)).fetchone()
                if row:
                    conn.execute("DELETE FROM items_fts WHERE rowid=?", (row[0],))
                    conn.execute("DELETE FROM items WHERE rowid=?", (row[0],))
                    deleted += 1
            conn.commit()
            if log and deleted:
                log('清理已不存在的记录：%d 条' % deleted)

        conn.execute("INSERT INTO items_fts(items_fts) VALUES('optimize')")
        conn.commit()
    finally:
        conn.close()

    if rebuild and real != out_db:
        if os.path.exists(out_db):
            try:
                os.replace(out_db, out_db + '.bak')
            except OSError:
                pass
        os.replace(real, out_db)

    st = {'total': total, 'added': added, 'updated': updated, 'deleted': deleted,
          'skipped': skipped, 'errors': errors, 'db': out_db,
          'db_size': os.path.getsize(out_db) if os.path.exists(out_db) else 0,
          'elapsed': time.time() - t0, 'mode': 'full' if rebuild else 'inc'}
    if log:
        log('完成：新增 %d，更新 %d，清理 %d，未变 %d，出错 %d；耗时 %.1f 秒；库 %s'
            % (added, updated, deleted, skipped, errors, st['elapsed'], human(st['db_size'])))
    return st


# ───────────────────────────── 搜索（自带小检索，便于即时验证） ─────────────────────────────

def _match_expr(keyword):
    return ' '.join('"%s"' % ' '.join(tok)
                    for tok in _PUNCT_RE.sub(' ', keyword or '').split())


def search_db(db, keyword, limit=200):
    """返回 [(filename, filepath, extra), ...]（与 CathayFinder 同一套精准匹配）"""
    from urllib.parse import quote
    if not os.path.exists(db):
        return []
    expr = _match_expr(keyword)
    if not expr:
        return []
    uri = 'file:%s?mode=ro' % quote(db.replace('\\', '/'), safe='/\\:')
    conn = sqlite3.connect(uri, uri=True)
    try:
        rows = conn.execute(
            'SELECT i.filename, i.filepath, i.extra FROM items i'
            ' INNER JOIN items_fts f ON i.rowid = f.rowid'
            ' WHERE items_fts MATCH ? LIMIT ?', (expr, limit)).fetchall()
    except Exception:
        rows = []
    finally:
        conn.close()
    return rows


# ───────────────────────────── 自检 ─────────────────────────────

def selftest():
    import tempfile
    lines = []
    try:
        lines.append('%s %s' % (APP_TITLE, APP_VERSION))
        lines.append('python=%s' % sys.version.split()[0])
        cf = find_cathayfinder_dir()
        lines.append('CathayFinder 位置=%s' % (cf or '（未找到，需在界面上指一下）'))
        lines.append('库文件将写入=%s' % default_db_path())
        root = tempfile.mkdtemp(prefix='_lf_')
        a = os.path.join(root, '甲乙', '丙丁')
        os.makedirs(a, exist_ok=True)
        for n in ('布罗代尔 十五至十八世纪的物质文明.pdf', '年鉴学派管窥.epub',
                  'notes.txt'):
            with open(os.path.join(root if n.endswith('.txt') else a, n), 'w',
                      encoding='utf-8') as f:
                f.write('x')
        with open(os.path.join(a, '地中海考古.djvu'), 'w', encoding='utf-8') as f:
            f.write('y')
        dbdir = tempfile.mkdtemp(prefix='_lfdb_')
        db = os.path.join(dbdir, '本地文件库.db')
        st = build([root], db, mode='full')
        lines.append('建库：新增 %d / 共 %d（%s）' % (st['added'], st['total'], human(st['db_size'])))
        r1 = search_db(db, '布罗代尔')
        r2 = search_db(db, '年鉴学派')
        r3 = search_db(db, '地中海')
        r4 = search_db(db, '不存在的书名xyz')
        lines.append('搜索 布罗代尔 → %d 条 %s' % (len(r1), r1[0][0] if r1 else ''))
        lines.append('搜索 年鉴学派 → %d 条 %s' % (len(r2), r2[0][0] if r2 else ''))
        lines.append('搜索 地中海   → %d 条 %s' % (len(r3), r3[0][0] if r3 else ''))
        lines.append('搜索 不存在的书名 → %d 条（应为 0）' % len(r4))
        st2 = build([root], db, mode='inc')
        lines.append('增量重跑：新增 %d 更新 %d 未变 %d（应为 0/0/4）'
                     % (st2['added'], st2['updated'], st2['skipped']))
        ok = (len(r1) == 1 and len(r2) == 1 and len(r3) == 1 and len(r4) == 0
              and st['added'] == 4 and st2['added'] == 0 and st2['updated'] == 0)
        lines.append('result=%s' % ('OK' if ok else 'FAIL'))
        import shutil
        shutil.rmtree(root, ignore_errors=True)
        shutil.rmtree(dbdir, ignore_errors=True)
    except Exception as e:
        import traceback
        lines.append('ERROR %r' % (e,))
        lines.append(traceback.format_exc())
        lines.append('result=FAIL')
    # 打包成单文件 exe 后，模块目录是临时解压出来的（甚至根本没有真实目录），
    # 往那儿写会 FileNotFoundError —— 写不下就退到临时目录，别把自检搞崩。
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), '_selftest.txt')
    try:
        with open(out, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
    except OSError:
        try:
            import tempfile
            out = os.path.join(tempfile.gettempdir(), 'cathayindex_selftest.txt')
            with open(out, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines))
        except OSError:
            pass
    return '\n'.join(lines)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if '--selftest' in argv:
        print(selftest())
        return 0
    if '--cli' in argv:
        args = argv[argv.index('--cli') + 1:]
        roots, opts = [], {}
        i = 0
        while i < len(args):
            a = args[i]
            if a == '--out':
                opts['out_db'] = args[i + 1]; i += 2; continue
            if a == '--cathayfinder':
                opts['out_db'] = cathayfinder_db_path(args[i + 1]); i += 2; continue
            if a == '--mode':
                opts['mode'] = args[i + 1]; i += 2; continue
            if a == '--ext':
                opts['exts'] = [e for e in args[i + 1].split(',') if e]
                i += 2; continue
            if a == '--keep-hidden':
                opts['skip_hidden'] = False; i += 1; continue
            if a == '--no-clean':
                opts['clean_deleted'] = False; i += 1; continue
            roots.append(a); i += 1
        st = build(roots, progress=lambda d, t, n: print('  %d/%d %s' % (d, t, n), flush=True),
                   log=lambda s: print(s, flush=True), **opts)
        print(st)
        return 0
    print(__doc__)
    print('库名：%s' % LIB_LABEL)
    print('CathayFinder 位置：%s' % (find_cathayfinder_dir() or '（未找到）'))
    print('库文件：%s' % default_db_path())
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
