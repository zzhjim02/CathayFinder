# -*- coding: utf-8 -*-
import os, sys
from pathlib import Path

# EXE运行时：基于EXE所在目录（项目根目录）
# 源码运行时：基于config.py的父目录的父目录
if getattr(sys, 'frozen', False):
    PROJECT_ROOT = Path(sys.executable).resolve().parent
else:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = PROJECT_ROOT / "data"
DB_DIR = DATA_DIR / "db"
EXPORT_DIR = PROJECT_ROOT / "export"
RECOVER_DIR = PROJECT_ROOT / "_recovered"

# 渠道优先级排序 (数值越小越优先；与 db_manager.DB_CONFIG 保持一致)
# 读秀 = 原「读秀」+ 原「读秀秒传码」两个库合并
PRIORITY_MAP = {
    "本地文件库": 5,
    "学术信息数据库": 10,
    "读秀": 20,
    "维基共享资源": 30,
    "Z-Library": 40,
    "中国地方志": 50,
    "奇点社科": 60,
    "游氏古籍": 70,
    "维基文库": 80,
    "华中师大近史所": 90,
    "维基百科": 100,
}

# 渠道颜色
CHANNEL_COLORS = {
    "本地文件库": "#1e7a6f",
    "学术信息数据库": "#8e44ad",
    "读秀": "#16a085",
    "维基共享资源": "#95a5a6",
    "Z-Library": "#e74c3c",
    "中国地方志": "#d35400",
    "奇点社科": "#7f8c8d",
    "游氏古籍": "#2c3e50",
    "维基文库": "#2980b9",
    "华中师大近史所": "#c0392b",
    "维基百科": "#27ae60",
}
