# -*- coding: UTF-8 -*-
"""批量操作 API - 优化批量删除、批量发布性能"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List
from pathlib import Path
import asyncio

from src.ai_write_x.config.config import Config
from src.ai_write_x.utils.path_manager import PathManager
from src.ai_write_x.utils import log

router = APIRouter(prefix="/api/batch", tags=["batch"])


class BatchDeleteRequest(BaseModel):
    paths: List[str]


class BatchDeleteResponse(BaseModel):
    success_count: int
    fail_count: int
    errors: List[dict]


@router.post("/delete", response_model=BatchDeleteResponse)
async def batch_delete_articles(request: BatchDeleteRequest):
    """批量删除文章 - 一次性处理多个"""
    success_count = 0
    fail_count = 0
    errors = []
    
    for path in request.paths:
        try:
            file_path = Path(path)
            stem = file_path.stem
            dir_path = file_path.parent
            
            deleted_any = False
            for ext in ['.html', '.md', '.txt', '.design.json', '.source.txt']:
                target_file = dir_path / f"{stem}{ext}"
                if target_file.exists():
                    target_file.unlink()
                    deleted_any = True
            
            if deleted_any:
                success_count += 1
            else:
                fail_count += 1
                errors.append({"path": path, "error": "文件不存在"})
                
        except Exception as e:
            fail_count += 1
            errors.append({"path": path, "error": str(e)})
    
    return BatchDeleteResponse(
        success_count=success_count,
        fail_count=fail_count,
        errors=errors
    )


class BatchPublishRequest(BaseModel):
    paths: List[str]
    platform_keys: List[str]


class BatchPublishResponse(BaseModel):
    success_count: int
    fail_count: int
    results: List[dict]


@router.post("/publish", response_model=BatchPublishResponse)
async def batch_publish_articles(request: BatchPublishRequest):
    """批量发布文章到平台"""
    success_count = 0
    fail_count = 0
    results = []
    
    config = Config.get_instance()
    credentials = config.wechat_credentials
    
    if not credentials:
        raise HTTPException(status_code=400, detail="未配置微信账号")
    
    from src.ai_write_x.tools.wx_publisher import pub2wx
    
    for path in request.paths:
        try:
            file_path = Path(path)
            if not file_path.exists():
                results.append({"path": path, "status": "failed", "error": "文件不存在"})
                fail_count += 1
                continue
            
            # 读取文章内容
            content = file_path.read_text(encoding='utf-8')
            title = file_path.stem
            
            # 发布到配置的第一个账号
            cred = credentials[0]
            message, _, success = pub2wx(
                title=title,
                digest="",
                article=content,
                appid=cred.get("appid", ""),
                appsecret=cred.get("appsecret", ""),
                author=cred.get("author", "AIWriteX"),
                mode="publish"
            )
            
            if success:
                success_count += 1
                results.append({"path": path, "status": "success", "message": message})
            else:
                fail_count += 1
                results.append({"path": path, "status": "failed", "error": message})
                
        except Exception as e:
            fail_count += 1
            results.append({"path": path, "status": "failed", "error": str(e)})
    
    return BatchPublishResponse(
        success_count=success_count,
        fail_count=fail_count,
        results=results
    )
