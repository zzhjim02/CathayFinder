# -*- coding: utf-8 -*-
"""Database manager for CathayFinder."""
import sqlite3
from pathlib import Path
from ..config import DB_DIR

# 渠道定义。priority 数值越小越优先（GUI 渠道顺序、结果排序都用它）
# 一个渠道可以挂多个库：extra_dbs（如「读秀」= duxiu.db + 读秀秒传码 duxiu_md5.db）
DB_CONFIG = {
    # 「学术信息数据库」= 个人百度网盘 + 个人阿里网盘（两个库同属一个渠道）
    "baidu_pan": {"db": "baidu_pan.db", "label": "学术信息数据库", "priority": 10,
                  "cols": ["filename", "filepath", "title", "name"],
                  "extra_dbs": [{"db": "aliyun.db",
                                 "cols": ["filename", "filepath", "title", "name"]}]},
    "duxiu": {"db": "duxiu.db", "label": "读秀", "priority": 20,
              "cols": ["title", "author", "publisher"],
              "extra_dbs": [{"db": "duxiu_md5.db",
                             "cols": ["name", "filepath", "ssid"]}]},
    # 维基共享资源（预留）：当前挂「数字图书馆备份项目」库；将来导入维基共享
    # 资源总目录后，直接在 extra_dbs 里加一项即可并入本渠道。
    # 「维基共享资源」= 数字图书馆备份项目 wiki_lib.db + 总目录里的书刊文件 commons_books.db
    "wiki_lib": {"db": "wiki_lib.db", "label": "维基共享资源", "priority": 30,
                 "cols": ["title", "author"],
                 "extra_dbs": [{"db": "commons_books.db",
                                "cols": ["title", "author"]}]},
    "zlib": {"db": "zlib.db", "label": "Z-Library", "priority": 40,
             "cols": ["title", "author", "publisher"]},
    "difangzhi": {"db": "difangzhi.db", "label": "中国地方志", "priority": 50,
                  "cols": ["title", "author"]},
    "qidian": {"db": "qidian.db", "label": "奇点社科", "priority": 60,
               "cols": ["title", "author"]},
    "youshi": {"db": "youshi.db", "label": "游氏古籍", "priority": 70,
               "cols": ["filename", "filepath"]},
    "zhwikisource": {"db": "zhwikisource.db", "label": "维基文库", "priority": 80,
                     "cols": ["title"]},
    "huazhong": {"db": "huazhong.db", "label": "华中师大近史所", "priority": 90,
                 "cols": ["title", "author"]},
    "zhwiki": {"db": "zhwiki.db", "label": "维基百科", "priority": 100,
               "cols": ["title"]},
    # 本地文件库：由 CathayIndex 工具扫描本地文件夹生成（默认放同一个库目录）
    "local_files": {"db": "local_files.db", "label": "本地文件库", "priority": 5,
                    "cols": ["title", "filename", "filepath", "account"]},
}

_conn_cache = {}


def _resolve(key):
    """key 'duxiu' 或 'duxiu@0'（extra_dbs 下标）→ (db 文件名, 匹配列)"""
    base, _, idx = key.partition("@")
    cfg = DB_CONFIG.get(base)
    if not cfg:
        return None, []
    if idx == "":
        return cfg["db"], list(cfg.get("cols", []))
    try:
        ex = cfg.get("extra_dbs", [])[int(idx)]
    except (IndexError, ValueError):
        return None, []
    return ex["db"], list(ex.get("cols", []))


def db_variants(key):
    """渠道 key → [(连接key, 匹配列), ...]（主库 + 附加库）"""
    cfg = DB_CONFIG.get(key)
    if not cfg:
        return []
    out = [(key, list(cfg.get("cols", [])))]
    for i in range(len(cfg.get("extra_dbs", []))):
        out.append(("%s@%d" % (key, i),
                    list(cfg["extra_dbs"][i].get("cols", []))))
    return out


def db_key_for_file(fname):
    """按数据库文件名反查连接 key（'duxiu_md5.db' → 'duxiu@0'）"""
    for k, v in DB_CONFIG.items():
        if v["db"] == fname:
            return k
        for i, ex in enumerate(v.get("extra_dbs", [])):
            if ex["db"] == fname:
                return "%s@%d" % (k, i)
    return None


def channel_db_files(key):
    """这个渠道用到的全部库文件（Path 列表）"""
    cfg = DB_CONFIG.get(key) or {}
    names = [cfg.get("db")] + [d.get("db") for d in cfg.get("extra_dbs", [])]
    return [DB_DIR / n for n in names if n]


def channel_available(key):
    """渠道能不能用：至少要有一个库文件存在且不是 0 字节。

    用户可以自己删掉某个库文件（比如 duxiu.db）——删掉后本函数返回 ok=False，
    界面上该渠道会置灰、不再参与搜索（搜索本身也会自动跳过不存在的库）。
    返回 (ok, 缺失/空文件的路径列表)；一个渠道挂多个库时，只要还剩下一个能用的
    就仍然可用（例如只删了读秀秒传码库，读秀照样能查，只是没有秒传码）。
    """
    files = channel_db_files(key)
    missing = []
    for p in files:
        try:
            if (not p.exists()) or p.stat().st_size == 0:
                missing.append(str(p))
        except Exception:
            missing.append(str(p))
    return (len(missing) < len(files), missing)


def get_db(key):
    if key in _conn_cache:
        try:
            _conn_cache[key].execute("SELECT 1")
            return _conn_cache[key]
        except Exception:
            pass
    fname, _cols = _resolve(key)
    if not fname:
        return None
    p = DB_DIR / fname
    if not p.exists():
        return None
    try:
        c = sqlite3.connect(str(p), check_same_thread=False)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA synchronous=OFF")
        c.execute("PRAGMA cache_size=-65536")
        _conn_cache[key] = c
        return c
    except Exception:
        return None


def close_all():
    for c in _conn_cache.values():
        try:
            c.close()
        except Exception:
            pass
    _conn_cache.clear()
