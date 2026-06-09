# -*- coding: UTF-8 -*-
"""小爆来咯 版本信息"""

from datetime import datetime

__version__ = "1.2.23"
__author__ = "小爆来咯"
__build_time__ = datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_version():
    return __version__


def get_author():
    return __author__


def get_version_with_prefix():
    return f"v{__version__}"


def get_build_info():
    return {
        "version": __version__,
        "version_display": f"v{__version__}",
        "author": __author__,
        "build_time": __build_time__,
    }
