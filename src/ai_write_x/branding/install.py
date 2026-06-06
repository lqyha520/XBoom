# -*- coding: UTF-8 -*-
"""安装包 / 安装目录 / 主程序文件名（全项目统一，与 Inno Setup、PyInstaller 一致）。"""

APP_SLUG = "XBoom"
APP_BRAND = "小爆来咯"

EXE_NAME = f"{APP_BRAND}.exe"
INSTALL_DIR_NAME = APP_BRAND


def _get_version() -> str:
    try:
        from src.ai_write_x.version import get_version
        return get_version()
    except Exception:
        return "0.0.0"


INSTALLER_NAME = f"{APP_BRAND}-Setup-v{_get_version()}.exe"
