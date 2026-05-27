# -*- coding: utf-8 -*-
"""menu_ip_whitelist 表增删改查。"""

from __future__ import annotations

import ipaddress
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.ai_write_x.core.menu_ip_access import _menu_access_settings


def validate_ip(ip: str) -> str:
    value = (ip or "").strip()
    if not value:
        raise ValueError("IP 不能为空")
    try:
        ipaddress.ip_address(value)
    except ValueError as exc:
        raise ValueError(f"无效的 IP 地址: {value}") from exc
    return value


def _mysql_cfg() -> Dict[str, Any]:
    settings = _menu_access_settings()
    mysql_cfg = settings.get("mysql") or {}
    host = str(mysql_cfg.get("host") or "").strip()
    if not host:
        raise RuntimeError("未配置 menu_access.mysql.host")
    return mysql_cfg


def _connect():
    import pymysql

    mysql_cfg = _mysql_cfg()
    return pymysql.connect(
        host=str(mysql_cfg.get("host") or "").strip(),
        port=int(mysql_cfg.get("port") or 3306),
        user=str(mysql_cfg.get("user") or "").strip(),
        password=str(mysql_cfg.get("password") or ""),
        database=str(mysql_cfg.get("database") or "XBoom").strip(),
        charset="utf8mb4",
        connect_timeout=max(1, min(int(mysql_cfg.get("connect_timeout") or 5), 30)),
        read_timeout=30,
        write_timeout=30,
        cursorclass=pymysql.cursors.DictCursor,
    )


def _row_to_dict(row: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(row)
    for key in ("created_at", "updated_at"):
        val = out.get(key)
        if isinstance(val, datetime):
            out[key] = val.strftime("%Y-%m-%d %H:%M:%S")
    out["enabled"] = bool(out.get("enabled"))
    return out


def list_whitelist_entries() -> List[Dict[str, Any]]:
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, ip, remark, enabled, created_at, updated_at
                FROM menu_ip_whitelist
                ORDER BY id ASC
                """
            )
            return [_row_to_dict(r) for r in (cur.fetchall() or [])]
    finally:
        conn.close()


def get_whitelist_entry(entry_id: int) -> Optional[Dict[str, Any]]:
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, ip, remark, enabled, created_at, updated_at
                FROM menu_ip_whitelist WHERE id = %s
                """,
                (entry_id,),
            )
            row = cur.fetchone()
            return _row_to_dict(row) if row else None
    finally:
        conn.close()


def create_whitelist_entry(ip: str, remark: str = "", enabled: bool = True) -> Dict[str, Any]:
    ip_val = validate_ip(ip)
    remark_val = (remark or "").strip()[:128]
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO menu_ip_whitelist (ip, remark, enabled)
                VALUES (%s, %s, %s)
                """,
                (ip_val, remark_val, 1 if enabled else 0),
            )
            new_id = cur.lastrowid
        conn.commit()
        item = get_whitelist_entry(int(new_id))
        if not item:
            raise RuntimeError("创建成功但无法读取记录")
        return item
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def update_whitelist_entry(
    entry_id: int,
    *,
    ip: Optional[str] = None,
    remark: Optional[str] = None,
    enabled: Optional[bool] = None,
) -> Dict[str, Any]:
    existing = get_whitelist_entry(entry_id)
    if not existing:
        raise LookupError("记录不存在")

    fields: List[str] = []
    params: List[Any] = []
    if ip is not None:
        fields.append("ip = %s")
        params.append(validate_ip(ip))
    if remark is not None:
        fields.append("remark = %s")
        params.append((remark or "").strip()[:128])
    if enabled is not None:
        fields.append("enabled = %s")
        params.append(1 if enabled else 0)

    if not fields:
        return existing

    params.append(entry_id)
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE menu_ip_whitelist SET {', '.join(fields)} WHERE id = %s",
                params,
            )
        conn.commit()
        updated = get_whitelist_entry(entry_id)
        if not updated:
            raise RuntimeError("更新成功但无法读取记录")
        return updated
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def delete_whitelist_entry(entry_id: int) -> bool:
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM menu_ip_whitelist WHERE id = %s", (entry_id,))
            deleted = cur.rowcount > 0
        conn.commit()
        return deleted
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def is_mysql_configured() -> bool:
    try:
        cfg = _mysql_cfg()
        return bool(str(cfg.get("host") or "").strip())
    except RuntimeError:
        return False
