# -*- coding: utf-8 -*-
"""CathayFinder 数据层。

渠道与连接配置统一放在 db_manager 里（过去这里和 db_manager 各存了一份
DB_CONFIG，两份容易不一致，现已合并为一份，这里只做转发）。
"""
from .db_manager import (DB_CONFIG, db_key_for_file, db_variants,  # noqa: F401
                         get_db, close_all)

__all__ = ["DB_CONFIG", "db_key_for_file", "db_variants", "get_db", "close_all"]
