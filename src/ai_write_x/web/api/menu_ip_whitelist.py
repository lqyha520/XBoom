# -*- coding: utf-8 -*-
"""受限菜单 IP 白名单 CRUD API（仅白名单 IP 可访问）。"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.ai_write_x.core import menu_ip_whitelist_store as store
from src.ai_write_x.core.menu_ip_access import (
    MenuIpAccessService,
    detect_public_ip,
    is_restricted_menu_visible,
)
from src.ai_write_x.utils import log

router = APIRouter(prefix="/api/menu-ip-whitelist", tags=["menu-ip-whitelist"])


def _require_whitelist_admin():
    if not is_restricted_menu_visible():
        raise HTTPException(status_code=403, detail="仅限白名单 IP 访问此功能")
    if not store.is_mysql_configured():
        raise HTTPException(status_code=503, detail="未配置 menu_access.mysql，无法管理白名单")


def _refresh_access_cache() -> None:
    try:
        MenuIpAccessService.get_instance().refresh()
    except Exception as exc:
        log.print_log(f"[菜单白名单] 缓存刷新失败: {exc}", "warning")


class WhitelistCreate(BaseModel):
    ip: str = Field(..., min_length=1, max_length=45)
    remark: str = Field(default="", max_length=128)
    enabled: bool = True


class WhitelistUpdate(BaseModel):
    ip: Optional[str] = Field(default=None, max_length=45)
    remark: Optional[str] = Field(default=None, max_length=128)
    enabled: Optional[bool] = None


@router.get("/status")
async def get_status(_: None = Depends(_require_whitelist_admin)):
    svc = MenuIpAccessService.get_instance()
    return {
        "public_ip": svc.public_ip or detect_public_ip(),
        "allowed": svc.allowed,
        "message": svc.last_message,
        "whitelist_count": len(svc.whitelist_ips),
    }


@router.get("")
async def list_entries(_: None = Depends(_require_whitelist_admin)):
    try:
        return {"items": store.list_whitelist_entries()}
    except Exception as exc:
        log.print_log(f"[菜单白名单] 列表加载失败: {exc}", "error")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{entry_id}")
async def get_entry(entry_id: int, _: None = Depends(_require_whitelist_admin)):
    try:
        item = store.get_whitelist_entry(entry_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if not item:
        raise HTTPException(status_code=404, detail="记录不存在")
    return item


@router.post("")
async def create_entry(body: WhitelistCreate, _: None = Depends(_require_whitelist_admin)):
    try:
        item = store.create_whitelist_entry(body.ip, body.remark, body.enabled)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        err = str(exc)
        if "Duplicate" in err or "uk_ip" in err:
            raise HTTPException(status_code=409, detail="该 IP 已存在") from exc
        log.print_log(f"[菜单白名单] 创建失败: {exc}", "error")
        raise HTTPException(status_code=500, detail=err) from exc
    _refresh_access_cache()
    return {"status": "success", "item": item}


@router.put("/{entry_id}")
async def update_entry(
    entry_id: int,
    body: WhitelistUpdate,
    _: None = Depends(_require_whitelist_admin),
):
    try:
        item = store.update_whitelist_entry(
            entry_id,
            ip=body.ip,
            remark=body.remark,
            enabled=body.enabled,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        err = str(exc)
        if "Duplicate" in err or "uk_ip" in err:
            raise HTTPException(status_code=409, detail="该 IP 已存在") from exc
        log.print_log(f"[菜单白名单] 更新失败: {exc}", "error")
        raise HTTPException(status_code=500, detail=err) from exc
    _refresh_access_cache()
    return {"status": "success", "item": item}


@router.delete("/{entry_id}")
async def delete_entry(entry_id: int, _: None = Depends(_require_whitelist_admin)):
    try:
        deleted = store.delete_whitelist_entry(entry_id)
    except Exception as exc:
        log.print_log(f"[菜单白名单] 删除失败: {exc}", "error")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="记录不存在")
    _refresh_access_cache()
    return {"status": "success"}


@router.post("/refresh-cache")
async def refresh_cache(_: None = Depends(_require_whitelist_admin)):
    _refresh_access_cache()
    svc = MenuIpAccessService.get_instance()
    return {
        "status": "success",
        "allowed": svc.allowed,
        "public_ip": svc.public_ip,
        "message": svc.last_message,
    }
