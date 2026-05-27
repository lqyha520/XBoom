# -*- coding: utf-8 -*-
"""受限菜单 IP 白名单：启动时从 MySQL 拉取，按本机公网 IP 判断是否可见。"""

from __future__ import annotations

from typing import Any, Dict, Optional, Set

import httpx

from src.ai_write_x.config.config import Config
from src.ai_write_x.utils import log

# 受限菜单：工作台 / 知识库 / 任务监控 / 素材中心
RESTRICTED_MENU_VIEWS = frozenset(
    {"dashboard", "database-manager", "swarm-monitor", "preview-gallery"}
)

_PUBLIC_IP_SERVICES = (
    "https://myip.ipip.net/json",
    "https://api.ipify.org?format=json",
    "https://ipinfo.io/json",
)


def _menu_access_settings() -> Dict[str, Any]:
    config = Config.get_instance().config or {}
    merged: Dict[str, Any] = {
        "enabled": True,
        "mysql": {
            "host": "",
            "port": 3306,
            "database": "XBoom",
            "user": "",
            "password": "",
            "connect_timeout": 5,
        },
    }
    merged.update(config.get("menu_access") or {})
    mysql = merged.get("mysql") or {}
    if isinstance(mysql, dict):
        base = dict(merged["mysql"])
        base.update(mysql)
        merged["mysql"] = base
    return merged


def _parse_ip_from_json(data: dict) -> Optional[str]:
    if not isinstance(data, dict):
        return None
    ip = data.get("ip") or data.get("IP")
    if ip:
        return str(ip).strip()
    inner = data.get("data")
    if isinstance(inner, dict) and inner.get("ip"):
        return str(inner["ip"]).strip()
    return None


def detect_public_ip(timeout: float = 5.0) -> str:
    """获取当前机器公网出口 IP（桌面端菜单白名单用）。"""
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        for url in _PUBLIC_IP_SERVICES:
            try:
                response = client.get(url)
                if response.status_code != 200:
                    continue
                ip = _parse_ip_from_json(response.json())
                if ip:
                    return ip
            except Exception:
                continue
    return ""


def _load_whitelist_from_mysql(mysql_cfg: Dict[str, Any]) -> Set[str]:
    import pymysql

    host = str(mysql_cfg.get("host") or "").strip()
    if not host:
        return set()

    port = int(mysql_cfg.get("port") or 3306)
    database = str(mysql_cfg.get("database") or "XBoom").strip()
    user = str(mysql_cfg.get("user") or "").strip()
    password = str(mysql_cfg.get("password") or "")
    connect_timeout = max(1, min(int(mysql_cfg.get("connect_timeout") or 5), 30))

    connection = pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
        charset="utf8mb4",
        connect_timeout=connect_timeout,
        read_timeout=connect_timeout,
        write_timeout=connect_timeout,
        cursorclass=pymysql.cursors.DictCursor,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT ip FROM menu_ip_whitelist WHERE enabled = 1"
            )
            rows = cursor.fetchall() or []
        return {str(row["ip"]).strip() for row in rows if row.get("ip")}
    finally:
        connection.close()


class MenuIpAccessService:
    """单例：应用启动时 refresh，之后读缓存结果。"""

    _instance: Optional["MenuIpAccessService"] = None

    def __init__(self) -> None:
        self.allowed: bool = False
        self.public_ip: str = ""
        self.whitelist_ips: Set[str] = set()
        self.last_message: str = ""

    @classmethod
    def get_instance(cls) -> "MenuIpAccessService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def refresh(self) -> bool:
        """启动时调用：连 MySQL 拉白名单，再比对本机公网 IP。"""
        settings = _menu_access_settings()
        if not settings.get("enabled", True):
            self.allowed = False
            self.last_message = "menu_access.enabled=false，受限菜单已隐藏"
            log.print_log(f"[菜单白名单] {self.last_message}", "info")
            return False

        mysql_cfg = settings.get("mysql") or {}
        host = str(mysql_cfg.get("host") or "").strip()
        if not host:
            self.allowed = False
            self.last_message = "未配置 menu_access.mysql.host，受限菜单已隐藏"
            log.print_log(f"[菜单白名单] {self.last_message}", "warning")
            return False

        try:
            self.whitelist_ips = _load_whitelist_from_mysql(mysql_cfg)
        except Exception as exc:
            self.allowed = False
            self.whitelist_ips = set()
            self.last_message = f"MySQL 读取白名单失败: {exc}"
            log.print_log(f"[菜单白名单] {self.last_message}", "warning")
            return False

        self.public_ip = detect_public_ip()
        if not self.public_ip:
            self.allowed = False
            self.last_message = "无法获取本机公网 IP，受限菜单已隐藏"
            log.print_log(f"[菜单白名单] {self.last_message}", "warning")
            return False

        self.allowed = self.public_ip in self.whitelist_ips
        if self.allowed:
            self.last_message = (
                f"本机 IP {self.public_ip} 在白名单中（共 {len(self.whitelist_ips)} 条）"
            )
            log.print_log(f"[菜单白名单] {self.last_message}", "info")
        else:
            self.last_message = (
                f"本机 IP {self.public_ip} 不在白名单（库内 {len(self.whitelist_ips)} 条）"
            )
            log.print_log(f"[菜单白名单] {self.last_message}", "info")
        return self.allowed

    def is_restricted_menu_visible(self) -> bool:
        return self.allowed


def refresh_menu_ip_access_on_startup() -> None:
    MenuIpAccessService.get_instance().refresh()


def is_restricted_menu_visible() -> bool:
    return MenuIpAccessService.get_instance().is_restricted_menu_visible()
