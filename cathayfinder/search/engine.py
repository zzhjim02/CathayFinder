# -*- coding: utf-8 -*-
"""CathayFinder 搜索引擎 - FTS5 全文检索 + 分页加载"""
import copy
import sqlite3, re, os, time
from dataclasses import dataclass
from typing import List, Optional
from ..data.db_manager import (DB_CONFIG, db_key_for_file, db_variants,
                              get_db)

# 渠道顺序（与 db_manager.DB_CONFIG 的 priority 一致）
# 「读秀」一个渠道 = duxiu.db + duxiu_md5.db（原读秀秒传码已并入）
DEFAULT_KEY_ORDER = [
    "local_files", "baidu_pan", "duxiu", "wiki_lib", "zlib", "difangzhi",
    "qidian", "youshi", "zhwikisource", "huazhong", "zhwiki",
]

DB_SEARCH_CONFIG = [
    {"name": k, "label": v["label"], "priority": v["priority"]}
    for k, v in sorted(DB_CONFIG.items(), key=lambda x: x[1].get("priority", 99))
]

PRIORITY_MAP = {c["name"]: c["priority"] for c in DB_SEARCH_CONFIG}
LABEL_MAP = {c["name"]: c["label"] for c in DB_SEARCH_CONFIG}
NAME_MAP = {c["label"]: c["name"] for c in DB_SEARCH_CONFIG}

PAGE_SIZE = 100       # 每页条数（GUI 展示）
DISPLAY_CAP = 2000    # 每个渠道至少取这么多
HARD_CAP = 5000       # 自动模式下每渠道最多取这么多（命中超过它就先取前 5000）
FETCH_PER_DB = DISPLAY_CAP
FETCH_INCREMENT = 5000  # 「再取更多」每点一次、每渠道再加这么多


class SearchConfig:
    def __init__(self):
        self.enabled_sources = set(DEFAULT_KEY_ORDER)

search_config = SearchConfig()


@dataclass
class SearchResult:
    source: str = ""
    ssid: str = ""
    title: str = ""
    author: str = ""
    publisher: str = ""
    isbn: str = ""
    year: str = ""
    pages: str = ""
    dxid: str = ""
    filename: str = ""
    filepath: str = ""
    account: str = ""
    extra: str = ""
    seed_id: str = ""
    name: str = ""

    def display_title(self):
        t = self.title or self.name or self.filename or ""
        if self.source in {"学术信息数据库", "游氏古籍"} and self.filename:
            return _display_path(t)
        return t

    def display_author(self):
        return self.author or ""

    def display_publisher(self):
        return self.publisher or ""


def _display_path(raw):
    if not raw:
        return ""
    cleaned = re.sub(r'^[:/\\]+', '', raw)
    parts = cleaned.replace('\\', '/').strip('/').split('/')
    noise = {'我的资源', 'OCR购买', 'OCR购买的资料处理前的文件备份',
             '百度网盘', '阿里云盘', '我的文件', '备份',
             '学术信息条目检索数据库-扩展'}
    meaningful = [p for p in parts if p not in noise]
    if len(meaningful) > 3:
        meaningful = meaningful[-3:]
    return ' / '.join(meaningful)


def _dedup_key(r):
    name = r.title or r.filename or r.name or ""
    fp = r.filepath or ""
    src = r.source or ""
    return f"text:{src}:{name}:{fp}"


# ─────────────────────────────────────────────────────────────────────
# 导出用去重：只针对「读秀」，按 8 位读秀 ID（SSID）合并重复记录。
# 只改导出结果，不动数据库、也不动界面上的原行；读秀以外的渠道
# （以及其他渠道里出现的任何记录）一律原样保留。
# ─────────────────────────────────────────────────────────────────────
_SSID8_RE = re.compile(r'^\d{8}$')

_MERGE_FIELDS = ('title', 'author', 'publisher', 'isbn', 'year', 'pages',
                 'dxid', 'filename', 'filepath', 'account', 'seed_id', 'name')


def _merge_row(keep, dup):
    """把 dup 合并进 keep：只补空字段，不覆盖任何已有内容。"""
    for f in _MERGE_FIELDS:
        if not getattr(keep, f, '') and getattr(dup, f, ''):
            setattr(keep, f, getattr(dup, f))
    if not (keep.extra or '').strip() and (dup.extra or '').strip():
        keep.extra = dup.extra


def dedup_duxiu(results):
    """结果去重（仅读秀库，按 8 位读秀 ID/SSID）——屏幕显示与导出都用它。

    - 仅当 source == '读秀' 且 ssid 是 8 位数字时才做去重：同一 SSID 只留一条；
    - 读秀里 ssid 为空/非 8 位的记录、以及其余渠道的所有记录，一律原样保留，
      不会因为「拿不到 ID」而被丢掉；
    - 合并时只补空字段，不覆盖已有内容；秒传码只保留第一条，其余数量记在备注里；
    - 返回 (去重后的新列表, 被合并掉的条数)。界面上的原结果行不受影响。
    """
    out = []
    keep_idx = {}
    extra_md5 = {}
    merged = 0
    for r in results:
        sid = (r.ssid or '').strip()
        if r.source == "读秀" and _SSID8_RE.match(sid):
            i = keep_idx.get(sid)
            if i is None:
                keep_idx[sid] = len(out)
                extra_md5[sid] = 0
                out.append(copy.copy(r))
                continue
            _merge_row(out[i], r)
            if '秒传码' in (r.extra or ''):
                extra_md5[sid] = extra_md5.get(sid, 0) + 1
            merged += 1
        else:
            out.append(copy.copy(r))
    for sid, n in extra_md5.items():
        if n:
            keep = out[keep_idx[sid]]
            keep.extra = ((keep.extra + '  ') if keep.extra else '') + \
                         '（另有 %d 条同 ID 记录）' % n
    return out, merged


# ─────────────────────────────────────────────────────────────────────
# 读秀结果按 A→Z 排序（字母按字母，汉字按拼音；数字在前）
# ─────────────────────────────────────────────────────────────────────
try:                                    # pypinyin 可用则按拼音，否则退化为词典序
    from pypinyin import lazy_pinyin as _lazy_pinyin
except Exception:
    _lazy_pinyin = None

_LEAD_PUNCT = " \t\r\n([{【（〈《「『\"'“”‘’·•-—–_、,，.。:：;；!！?？/\\|+*#&@~"


def _name_of(r):
    return (getattr(r, 'title', '') or getattr(r, 'filename', '') or
            getattr(r, 'name', '') or '')


def alpha_key(r):
    """排序键：去掉开头的标点后，汉字转拼音、字母保留（小写比较）"""
    s = _name_of(r).strip()
    t = s.lstrip(_LEAD_PUNCT).strip() or s
    if not t:
        return ('\uffff', '\uffff')      # 空书名排最后
    low = t.lower()
    if _lazy_pinyin is not None:
        try:
            return (''.join(_lazy_pinyin(t)).lower(), low)
        except Exception:
            pass
    return (low, low)


def sort_duxiu(results):
    """只把「读秀」的条目按 A→Z（含汉字拼音）排列；
    其它渠道的条数和相对顺序完全不动。"""
    out = list(results)
    duxiu = [r for r in out if r.source == "读秀"]
    if len(duxiu) < 2:
        return out
    duxiu.sort(key=alpha_key)
    it = iter(duxiu)
    return [next(it) if r.source == "读秀" else r for r in out]


def tidy_results(results):
    """显示/导出前的统一整理：读秀按 8 位 SSID 去重 → 读秀按 A→Z
    → 全表按渠道分组（同一渠道必须连在一起，不允许 A 渠道、B 渠道、又回 A 渠道）。
    返回 (新列表, 被合并掉的条数)。"""
    rows, merged = dedup_duxiu(results)
    out = sort_duxiu(rows)
    out.sort(key=lambda r: PRIORITY_MAP.get(NAME_MAP.get(r.source, ""), 9999))
    return out, merged


# 兼容旧名字（导出功能也调这一份）
dedup_export = dedup_duxiu


# ─────────────────────────────────────────────────────────────────────────
# 精准检索：索引是「逐字加空格」建的，因此把用户输入的每个词逐字展开成
# FTS5 短语（"布 罗 代 尔"），只有完整包含该字符串的记录才会命中。
# 不再使用 ' '.join(keyword) 那种「逐字 AND」的模糊匹配（会把
# 「动荡时代的企业责任」这类只含零散单字的记录也捞出来）。
# ─────────────────────────────────────────────────────────────────────────
_PUNCT_RE = re.compile(
    r"""[\s"'`~!@#$%^&*()\-_+=\[\]{}\\|;:,.<>/?，。、；：！？（）【】《》“”‘’·—…]+""",
    re.UNICODE)

_INDEX_CACHE = {}
_FTS_COL_CACHE = {}

# 可选的检索字段（界面上的下拉框用它）
SEARCH_FIELDS = [("all", "全部字段"), ("title", "书名"), ("author", "作者"),
                 ("publisher", "出版者/出版社"), ("ssid", "SSID")]
# 每个字段对应哪些列（FTS 里有的列才能做字段检索；title 顺带把文件名也算上）
FIELD_FTS_COLS = {"title": ("title", "filename", "name"),
                  "author": ("author",),
                  "publisher": ("publisher",)}


def _fts_cols_of(conn):
    """items_fts 的列名（缓存，按库文件路径区分）"""
    key = _conn_tag(conn)
    v = _FTS_COL_CACHE.get(key)
    if v is None:
        try:
            v = tuple(r[1] for r in conn.execute("PRAGMA table_info('items_fts')"))
        except Exception:
            v = ()
        _FTS_COL_CACHE[key] = v
    return v


def build_match_expr(keyword, cols=None):
    """把查询串转成 FTS5 精准查询式（每个词一个短语，词与词之间 AND）。
    传 cols 时只在这些列里找（如 author 列）。"""
    norm = _PUNCT_RE.sub(' ', keyword or '')
    parts = []
    for tok in norm.split():
        ph = '"%s"' % ' '.join(tok)
        if cols:
            parts.append('(' + ' OR '.join('{%s}:%s' % (c, ph) for c in cols) + ')')
        else:
            parts.append(ph)
    return ' '.join(parts)


def _conn_tag(conn):
    """用数据库文件路径当缓存的 key（不能用 id(conn)：连接关了再开会复用地址，
    缓存就会串库 —— 这会让「按作者/出版者」在关闭重开后搜不到东西）"""
    try:
        return conn.execute('PRAGMA database_list').fetchone()[2] or ''
    except Exception:
        return ''


def _has_index(conn, tbl, col):
    """该表该列有没有索引（有索引才做精确等值查询，避免全表扫描拖慢）"""
    key = (_conn_tag(conn), tbl, col)
    v = _INDEX_CACHE.get(key)
    if v is None:
        try:
            rows = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name=?"
                " AND sql IS NOT NULL", [tbl]).fetchall()
            v = any(col in (r[0] or '') for r in rows)
        except Exception:
            v = False
        _INDEX_CACHE[key] = v
    return v


def _field_lookup(cfg_cols, keyword, conn, tbl, col_names, limit, allow_like=True):
    """编号(SSID/DXID) / ISBN 精确等值命中；以及按渠道配置列做「完整包含」匹配
    （用于没建 FTS 的库）"""
    kw = (keyword or '').strip()
    if not kw:
        return []
    rows = []
    digits = re.sub(r'\D', '', kw)
    jobs = []
    # 纯数字 → 当编号查（精确等值，需该列有索引）
    if digits and digits == kw and 5 <= len(digits) <= 12:
        for col in ('ssid', 'dxid'):
            if col in col_names and _has_index(conn, tbl, col):
                jobs.append(('SELECT rowid, * FROM "%s" WHERE "%s"=? LIMIT ?' % (tbl, col),
                             [digits, limit]))
    # 10~13 位数字 → ISBN 精确命中（去掉连字符与空格后比对）
    if digits and 9 <= len(digits) <= 13 and 'isbn' in col_names and _has_index(conn, tbl, 'isbn'):
        jobs.append((
            'SELECT rowid, * FROM "%s" WHERE REPLACE(REPLACE(isbn,\'-\',\'\'),\' \',\'\') LIKE ? LIMIT ?' % tbl,
            ['%' + digits + '%', limit]))
    # 按渠道配置列做「完整包含」匹配（必须完整包含查询串，不做逐字分散匹配）
    if not rows and not jobs and allow_like:
        cols = [c for c in (cfg_cols or []) if c in col_names]
        toks = [t for t in _PUNCT_RE.sub(' ', kw).split() if t]
        if cols and toks:
            where = ' AND '.join(
                '(' + ' OR '.join('"%s" LIKE ?' % c for c in cols) + ')' for _ in toks)
            params = []
            for _t in toks:
                params.extend(['%' + _t + '%'] * len(cols))
            jobs.append(('SELECT rowid, * FROM "%s" WHERE %s LIMIT ?' % (tbl, where),
                         params + [limit]))
    for sql, params in jobs:
        try:
            rows.extend(conn.execute(sql, params).fetchall())
        except Exception:
            pass
    return rows


def _field_rows(cfg, keyword, conn, tbl, col_names, field, limit):
    """字段检索（书名/作者/出版者/SSID）：
    - author/publisher/title：优先用 items_fts 里对应的列做列过滤短语匹配；
      主 FTS 没这列时，再看有没有旁挂索引表 field_fts（小库/大库都可能补过）。
    - ssid：直接按编号等值/前缀查（有索引，很快）。
    返回行列表（行内含 rowid）。"""
    kw = (keyword or '').strip()
    if not kw:
        return []
    if field == 'ssid':
        if 'ssid' not in col_names:
            return []
        digits = re.sub(r'\D', '', kw)
        if not digits:
            return []
        # 只在 ssid 有索引的库上查（否则 1000 万行的全表扫描太慢）
        if not _has_index(conn, tbl, 'ssid'):
            return []
        out = []
        seen_ids = set()
        # 等值 + 前缀范围（都用得上索引；不用 LIKE，避免走全表扫描）
        jobs = [('SELECT rowid, * FROM "%s" WHERE "ssid"=? LIMIT ?' % tbl, [digits, limit]),
                ('SELECT rowid, * FROM "%s" WHERE "ssid">? AND "ssid"<? LIMIT ?' % tbl,
                 [digits, digits + '\uffff', limit])]
        for sql, args in jobs:
            try:
                for row in conn.execute(sql, args).fetchall():
                    if row[0] not in seen_ids:
                        seen_ids.add(row[0])
                        out.append(row)
            except Exception:
                pass
        return out
    cols = FIELD_FTS_COLS.get(field) or ()
    fts_cols = _fts_cols_of(conn)
    use = [c for c in cols if c in fts_cols]
    expr = build_match_expr(kw, use or None)
    if use:
        try:
            return list(conn.execute(
                'SELECT r.rowid, r.* FROM "%s" r INNER JOIN items_fts f'
                ' ON r.rowid = f.rowid WHERE items_fts MATCH ? LIMIT ?'
                % tbl, [expr, limit]).fetchall())
        except Exception:
            return []
    # 主 FTS 没这列 → 看旁挂索引表
    has_side = bool(conn.execute(
        "SELECT 1 FROM sqlite_master WHERE name='field_fts' LIMIT 1").fetchall())
    if has_side:
        side_cols = [r[1] for r in conn.execute("PRAGMA table_info('field_fts')")]
        use2 = [c for c in cols if c in side_cols]
        if use2:
            try:
                return list(conn.execute(
                    'SELECT r.rowid, r.* FROM "%s" r INNER JOIN field_fts f'
                    ' ON r.rowid = f.rowid WHERE field_fts MATCH ? LIMIT ?'
                    % tbl, [build_match_expr(kw, use2), limit]).fetchall())
            except Exception:
                return []
    return []


def count_matches(cfg, keyword, conn, cols=None, match_expr=None, field='all'):
    """这个库里命中多少条（只数不取；用于给用户一个准确的总数）"""
    kw = (keyword or '').strip()
    if not kw:
        return 0
    try:
        orig_tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
            " AND name NOT LIKE '%_fts%' AND name NOT LIKE 'sqlite%'").fetchall()
        if not orig_tables:
            return 0
        tbl = orig_tables[0][0]
        col_names = [c[1] for c in conn.execute(
            'PRAGMA table_info("%s")' % tbl).fetchall()]
    except Exception:
        return 0

    has_fts = bool(conn.execute(
        "SELECT 1 FROM sqlite_master WHERE name='items_fts' LIMIT 1").fetchall())
    if field != 'all':
        # 字段检索：总数也按字段数（列过滤 / 编号）
        try:
            return len(_field_rows(cfg, keyword, conn, tbl, col_names, field, -1))
        except Exception:
            return 0
    if has_fts and match_expr:
        try:
            n = conn.execute('SELECT COUNT(*) FROM items_fts'
                             ' WHERE items_fts MATCH ?', [match_expr]).fetchone()[0]
            if n:
                return n           # 文本命中已包含主体，编号/ISBN 只在其为 0 时再算
        except Exception:
            pass

    total = 0
    cfg_cols = (list(cols) if cols is not None
                else DB_CONFIG.get(cfg.get('name'), {}).get('cols', []))
    digits = re.sub(r'\D', '', kw)
    sqls = []
    if digits and digits == kw and 5 <= len(digits) <= 12:
        for col in ('ssid', 'dxid'):
            if col in col_names and _has_index(conn, tbl, col):
                sqls.append(('SELECT COUNT(*) FROM "%s" WHERE "%s"=?'
                             % (tbl, col), [digits]))
    if (digits and 9 <= len(digits) <= 13 and 'isbn' in col_names
            and _has_index(conn, tbl, 'isbn')):
        sqls.append((
            "SELECT COUNT(*) FROM \"%s\" WHERE"
            " REPLACE(REPLACE(isbn,'-',''),' ','') LIKE ?" % tbl,
            ['%' + digits + '%']))
    if not has_fts:
        cs = [c for c in (cfg_cols or []) if c in col_names]
        toks = [t for t in _PUNCT_RE.sub(' ', kw).split() if t]
        if cs and toks:
            where = ' AND '.join(
                '(' + ' OR '.join('"%s" LIKE ?' % c for c in cs) + ')' for _ in toks)
            params = []
            for _t in toks:
                params.extend(['%' + _t + '%'] * len(cs))
            sqls.append(('SELECT COUNT(*) FROM "%s" WHERE %s' % (tbl, where),
                         params))
    for sql, params in sqls:
        try:
            total += conn.execute(sql, params).fetchone()[0] or 0
        except Exception:
            pass
    return total


def query_db(cfg, keyword, conn, source_label, fetch_limit=500, cols=None, field='all'):
    """单库检索：FTS5 短语精准匹配（完整包含查询串）+ 编号/ISBN 精确命中。
    没建 FTS 的库自动退回按列「完整包含」匹配。
    field 不为 all 时只查指定字段（书名/作者/出版者/SSID）。"""
    orig_tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
        " AND name NOT LIKE '%_fts%' AND name NOT LIKE 'sqlite%'"
    ).fetchall()
    if not orig_tables:
        return []
    orig_tbl = orig_tables[0][0]
    try:
        col_names = [c[1] for c in conn.execute(
            'PRAGMA table_info("%s")' % orig_tbl).fetchall()]
    except Exception:
        return []

    # zhwiki 损坏检测
    if source_label == "维基百科":
        try:
            valid = conn.execute(
                'SELECT COUNT(*) FROM "%s"'
                " WHERE title!='0' AND title!='!' AND title!='' AND title IS NOT NULL"
                % orig_tbl
            ).fetchone()[0]
            if valid < 1000:
                return []
        except Exception:
            pass

    has_fts = bool(conn.execute(
        "SELECT 1 FROM sqlite_master WHERE name='items_fts' LIMIT 1").fetchall())
    match_expr = build_match_expr(keyword)

    if field != 'all':                       # 指定字段检索
        rows = _field_rows(cfg, keyword, conn, orig_tbl, col_names, field,
                           -1 if fetch_limit is None or fetch_limit < 0 else fetch_limit)
        return _rows_to_results(rows, col_names, source_label)

    rows = []
    if has_fts and match_expr:
        try:
            fts_cols = conn.execute("PRAGMA table_info('items_fts')").fetchall()
            n_cols = max(len(fts_cols) - 1, 1)
        except Exception:
            n_cols = 1
        weights = ', '.join(['1.0'] * n_cols) if n_cols > 1 else ''
        if weights:
            sql = ('SELECT r.rowid, r.* FROM "%s" r'
                   ' INNER JOIN items_fts f ON r.rowid = f.rowid'
                   ' WHERE items_fts MATCH ?'
                   ' ORDER BY bm25(items_fts, %s) LIMIT ?' % (orig_tbl, weights))
        else:
            sql = ('SELECT r.rowid, r.* FROM "%s" r'
                   ' INNER JOIN items_fts f ON r.rowid = f.rowid'
                   ' WHERE items_fts MATCH ? LIMIT ?' % orig_tbl)
        try:
            rows = list(conn.execute(sql, [match_expr, fetch_limit]).fetchall())
        except Exception:
            rows = []

    cfg_cols = (list(cols) if cols is not None
                else DB_CONFIG.get(cfg.get('name'), {}).get('cols', []))
    if has_fts:
        # 有 FTS：只补编号/ISBN 精确命中（走索引，避免全表扫描）
        extra = _field_lookup(cfg_cols, keyword, conn, orig_tbl, col_names,
                              fetch_limit, allow_like=False)
        if extra:
            seen_ids = set(r[0] for r in rows)
            for r in extra:
                if r[0] not in seen_ids:
                    seen_ids.add(r[0])
                    rows.append(r)
    else:
        # 没建 FTS 的库：按渠道列做「完整包含」匹配
        rows = _field_lookup(cfg_cols, keyword, conn, orig_tbl, col_names,
                             fetch_limit, allow_like=True)
    if fetch_limit is not None and fetch_limit >= 0:
        rows = rows[:fetch_limit]

    return _rows_to_results(rows, col_names, source_label)


def _rows_to_results(rows, col_names, source_label):
    """把数据库行转成 SearchResult（含各渠道的显示修整）"""
    results = []
    for row in rows:
        rd = dict(zip(col_names, row[1:])) if col_names and len(row) > 1 else {}

        # 维基文库 tab 前缀
        if source_label == "维基文库":
            raw = rd.get("title", "")
            if raw and "\t" in raw:
                rd["title"] = raw.split("\t", 1)[-1]

        # wiki_lib URL 编码修复
        if source_label == "维基共享资源":
            raw = rd.get("title", "")
            if raw and '%' in raw:
                try:
                    from urllib.parse import unquote
                    rd["title"] = unquote(raw)
                except Exception:
                    pass

        def gv(key, default=""):
            try:
                return rd[key] if rd[key] is not None else default
            except (KeyError, IndexError):
                return default

        r = SearchResult(
            source=source_label,
            ssid=gv("ssid"),
            title=gv("title"),
            author=gv("author"),
            publisher=gv("publisher"),
            isbn=gv("isbn"),
            year=gv("year"),
            pages=gv("pages"),
            dxid=gv("dxid"),
            filename=gv("filename"),
            filepath=gv("filepath"),
            account=gv("account"),
            extra=gv("extra"),
            seed_id=gv("seed_id"),
            name=gv("name"),
        )

        # 秒传码库：把 md5/分片/大小显示到“备注”里
        if "md5" in col_names:
            bits = []
            if rd.get("md5"):
                bits.append("秒传码:" + str(rd["md5"]))
            if rd.get("slice_md5"):
                bits.append("分片:" + str(rd["slice_md5"]))
            if rd.get("size"):
                bits.append("大小:" + str(rd["size"]))
            if bits:
                r.extra = ((r.extra + "  ") if r.extra else "") + "  ".join(bits)

        if r.source in {"学术信息数据库", "游氏古籍"} and r.filename:
            last = r.filename.rstrip('/').rsplit('/', 1)[-1]
            if not r.title:
                r.title = last

        results.append(r)

    return results


def _enrich_md5(results):
    """给带 SSID 的读秀结果补上「秒传码 / 大小」"""
    need = [r for r in results if r.ssid and r.source == "读秀"]
    if not need:
        return
    conn = get_db(db_key_for_file("duxiu_md5.db"))
    if not conn:
        return
    for r in need:
        try:
            row = conn.execute(
                "SELECT md5, size FROM items WHERE ssid=? LIMIT 1", [r.ssid]).fetchone()
        except Exception:
            row = None
        if row and row["md5"]:
            bits = ["秒传码:" + str(row["md5"])]
            if row["size"]:
                bits.append("大小:" + str(row["size"]))
            r.extra = ((r.extra + "  ") if r.extra else "") + "  ".join(bits)


def search(keyword, cap=None, field='all'):
    """搜索入口：把每个渠道的结果一次取回（按渠道分组）。

    field: 'all'=全部字段（默认）；'title'/'author'/'publisher'/'ssid'=只查该字段。

    自动模式（cap=None）：每个渠道命中 ≤ HARD_CAP 条就全取，超过就取前
    HARD_CAP 条，同时给出库内命中总数；cap=N 时每渠道最多取 N 条；
    **cap<=0 表示不限量，把命中全部取回**（导出用）。

    返回 (results, seen_keys, meta)
    meta = {'cap', 'keyword', 'field', 'hard_cap', 'unlimited',
            'totals': {渠道: {'total': 库内命中, 'loaded': 实际取回, 'limit': 取值上限}}}
    """
    if not keyword or not keyword.strip():
        return [], set(), {'cap': 0, 'totals': {}, 'keyword': '', 'field': field}
    keyword = keyword.strip()

    unlimited = (cap is not None and cap <= 0)   # 不限量
    auto = (cap is None)

    match_expr = build_match_expr(keyword)
    all_results = []
    seen = set()
    totals = {}

    for cfg in DB_SEARCH_CONFIG:
        name = cfg["name"]
        label = cfg["label"]
        if name not in search_config.enabled_sources:
            continue

        # 一个渠道可能由多个库组成（如「读秀」= duxiu + 读秀秒传码）
        for ckey, cols in db_variants(name):
            conn = get_db(ckey)
            if not conn:
                continue
            try:
                n = count_matches(cfg, keyword, conn, cols, match_expr, field)
            except Exception:
                n = 0
            if n:
                t = totals.setdefault(label, {'total': 0, 'loaded': 0, 'limit': 0})
                t['total'] += n
            if unlimited:
                limit = -1          # SQLite LIMIT -1 = 不限量
            elif auto:
                # 命中不多就一次全取；命中很多才取前 HARD_CAP 条（另给准确总数）
                limit = max(DISPLAY_CAP, min(n or 0, HARD_CAP))
            else:
                limit = max(DISPLAY_CAP, cap)
            if limit:
                t = totals.setdefault(label, {'total': 0, 'loaded': 0, 'limit': 0})
                t['limit'] += limit
            try:
                results = query_db(cfg, keyword, conn, label,
                                   fetch_limit=limit, cols=cols, field=field)
            except Exception:
                results = []
            for r in results:
                dk = _dedup_key(r)
                if dk not in seen:
                    seen.add(dk)
                    all_results.append(r)

    # 读秀结果补秒传码；再按渠道优先级排序（同一渠道聚在一起）
    _enrich_md5(all_results)
    all_results.sort(key=lambda r: PRIORITY_MAP.get(NAME_MAP.get(r.source, ""), 9999))
    for r in all_results:
        t = totals.setdefault(r.source, {'total': 0, 'loaded': 0, 'limit': 0})
        t['loaded'] += 1

    meta = {'cap': cap, 'totals': totals, 'keyword': keyword, 'field': field,
            'hard_cap': HARD_CAP, 'unlimited': unlimited}
    return all_results, seen, meta


def search_all(keyword, field='all'):
    """导出专用：不限量，把命中的全部取回（cap<=0）"""
    return search(keyword, cap=-1, field=field)


def search_more(keyword, existing_seen, cap=None, field='all'):
    """把每个渠道的上限再抬高一档，多取一批（结果依旧按渠道分组）

    直接重跑一次搜索(cap 更大)，再把已有的剔掉；因为 bm25 排序是确定的，
    大 cap 的结果集必然包含小 cap 的，所以不会有重复/丢行。
    """
    base = cap or HARD_CAP
    new_cap = base + FETCH_INCREMENT
    all_results, seen, meta = search(keyword, cap=new_cap, field=field)
    fresh = []
    for r in all_results:
        dk = _dedup_key(r)
        if dk not in existing_seen:
            existing_seen.add(dk)
            fresh.append(r)
    return fresh, existing_seen, meta
