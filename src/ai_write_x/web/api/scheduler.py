from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import traceback

from src.ai_write_x.database.db_manager import db_manager
from src.ai_write_x.core import task_status
from src.ai_write_x.core.scheduler import scheduler_service
from src.ai_write_x.utils import log

router = APIRouter(prefix="/api/scheduler", tags=["Scheduler"])

IMAGE_STYLES = {
    "auto", "premium_editorial", "documentary", "cinematic",
    "soft_illustration", "minimal_3d", "oriental",
}

class TaskCreate(BaseModel):
    topic: str
    execution_time: str # ISO format or YYYY-MM-DD HH:MM:SS
    platform: str = "wechat"
    is_recurring: bool = False
    interval_hours: int = 0
    article_count: int = 1
    use_ai_beautify: bool = True
    image_style: str = "auto"
    collection_mode: bool = False
    target_appid: Optional[str] = None
    target_account_id: Optional[str] = None
    post_action: str = "save"
    repeat_mode: Optional[str] = None

class TaskUpdate(BaseModel):
    status: Optional[str] = None
    topic: Optional[str] = None
    execution_time: Optional[str] = None
    platform: Optional[str] = None
    is_recurring: Optional[bool] = None
    interval_hours: Optional[int] = None
    target_appid: Optional[str] = None
    target_account_id: Optional[str] = None
    article_count: Optional[int] = None
    use_ai_beautify: Optional[bool] = None
    image_style: Optional[str] = None
    collection_mode: Optional[bool] = None
    post_action: Optional[str] = None
    repeat_mode: Optional[str] = None

@router.get("/tasks")
async def get_tasks():
    tasks = db_manager.get_all_tasks()
    return [{
        "id": str(t.id),
        "topic": t.topic or "",
        "platform": t.platform,
        "execution_time": t.execution_time.strftime("%Y-%m-%d %H:%M:%S"),
        "is_recurring": t.is_recurring,
        "interval_hours": t.interval_hours,
        "repeat_mode": getattr(t, "repeat_mode", "interval") if t.is_recurring else "once",
        "article_count": t.article_count,
        "use_ai_beautify": t.use_ai_beautify,
        "image_style": getattr(t, "image_style", "auto"),
        "collection_mode": getattr(t, "collection_mode", False),
        "target_appid": getattr(t, "target_appid", None),
        "target_account_id": getattr(t, "target_account_id", None),
        "post_action": getattr(t, "post_action", "publish"),
        "status": t.status,
        "last_run_at": t.last_run_at.strftime("%Y-%m-%d %H:%M:%S") if getattr(t, "last_run_at", None) else None,
        "created_at": t.created_at.strftime("%Y-%m-%d %H:%M:%S")
    } for t in tasks]

@router.post("/tasks")
async def create_task(data: TaskCreate):
    try:
        # 尝试解析时间
        try:
            exec_time = datetime.fromisoformat(data.execution_time.replace("Z", "+00:00"))
        except:
            exec_time = datetime.strptime(data.execution_time, "%Y-%m-%d %H:%M:%S")
        
        repeat_mode = data.repeat_mode or ("interval" if data.is_recurring else "once")
        if repeat_mode not in {"once", "daily", "interval"}:
            raise HTTPException(status_code=400, detail="Invalid repeat mode")
        if data.image_style not in IMAGE_STYLES:
            raise HTTPException(status_code=400, detail="Invalid image style")
        task = db_manager.add_scheduled_task(
            topic=data.topic,
            execution_time=exec_time,
            platform=data.platform,
            is_recurring=repeat_mode != "once",
            interval_hours=24 if repeat_mode == "daily" else data.interval_hours,
            article_count=data.article_count,
            use_ai_beautify=data.use_ai_beautify,
            image_style=data.image_style,
            collection_mode=data.collection_mode,
            target_appid=data.target_appid,
            target_account_id=data.target_account_id,
            post_action=data.post_action,
            repeat_mode=repeat_mode,
        )
        if task:
            return {"status": "success", "id": str(task.id)}
        raise HTTPException(status_code=500, detail="Failed to create task in DB")
    except Exception as e:
        log.print_log(f"创建定时任务失败: {e}", "error")
        raise HTTPException(status_code=400, detail=str(e))

@router.put("/tasks/{task_id}")
async def update_task(task_id: str, data: TaskUpdate):
    from src.ai_write_x.database.models import ScheduledTask
    try:
        task = ScheduledTask.get_by_id(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        if task.status in task_status.ACTIVE_STATUSES and data.status and data.status != task.status:
            raise HTTPException(status_code=409, detail="Task is running; cancel this run before changing status")
        if data.status:
            task.status = data.status
        if data.topic is not None:
            task.topic = data.topic
        if data.platform:
            task.platform = data.platform
        if data.is_recurring is not None:
            task.is_recurring = data.is_recurring
        if data.interval_hours is not None:
            task.interval_hours = data.interval_hours
        if data.repeat_mode is not None:
            if data.repeat_mode not in {"once", "daily", "interval"}:
                raise HTTPException(status_code=400, detail="Invalid repeat mode")
            task.repeat_mode = data.repeat_mode
            task.is_recurring = data.repeat_mode != "once"
            if data.repeat_mode == "daily":
                task.interval_hours = 24
        if "target_appid" in data.model_fields_set:
            task.target_appid = data.target_appid
        if "target_account_id" in data.model_fields_set:
            task.target_account_id = data.target_account_id
        if data.article_count is not None:
            task.article_count = data.article_count
        if data.use_ai_beautify is not None:
            task.use_ai_beautify = data.use_ai_beautify
        if data.image_style is not None:
            if data.image_style not in IMAGE_STYLES:
                raise HTTPException(status_code=400, detail="Invalid image style")
            task.image_style = data.image_style
        if data.collection_mode is not None:
            task.collection_mode = data.collection_mode
        if data.post_action is not None:
            if data.post_action not in {"none", "save", "publish"}:
                raise HTTPException(status_code=400, detail="Invalid post action")
            task.post_action = data.post_action
        if data.execution_time:
            try:
                task.execution_time = datetime.fromisoformat(data.execution_time.replace("Z", "+00:00"))
            except:
                task.execution_time = datetime.strptime(data.execution_time, "%Y-%m-%d %H:%M:%S")
        
        task.updated_at = datetime.now()
        task.save()
        return {"status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=404, detail="Task not found or update failed")

@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str):
    from src.ai_write_x.database.models import ScheduledTask

    task = ScheduledTask.get_by_id(task_id)
    if task and task.status in task_status.ACTIVE_STATUSES:
        raise HTTPException(status_code=409, detail="Task is running; cancel this run before deleting")
    if db_manager.delete_task(task_id):
        return {"status": "success"}
    raise HTTPException(status_code=404, detail="Task not found")

@router.post("/tasks/{task_id}/cancel")
async def cancel_task(task_id: str):
    success, message = scheduler_service.request_cancel(task_id)
    if success:
        return {"status": "success", "message": message}
    if message == "Task not found":
        raise HTTPException(status_code=404, detail=message)
    return {"status": "idle", "message": message}

@router.get("/logs")
async def get_logs(limit: int = 50):
    logs = db_manager.get_recent_task_logs(limit)
    return [{
        "id": l.id,
        "task_id": l.task_id,
        "status": l.status,
        "message": l.message,
        "article_id": l.article_id,
        "run_time": l.run_time.strftime("%Y-%m-%d %H:%M:%S")
    } for l in logs]

@router.get("/verify-platform")
async def verify_platform(platform: str):
    """验证发布平台连接性（微信公众号复用配置中心的凭证校验）"""
    if platform != "wechat":
        return {"success": True, "message": f"{platform} 暂不支持连接性检测"}

    try:
        from src.ai_write_x.config.config import Config
        from src.ai_write_x.web.api.config import WechatCredentialTest, test_wechat_credential

        config = Config.get_instance()
        creds = config.wechat_credentials or []
        cred = next(
            (c for c in creds if (c.get("appid") or "").strip() and (c.get("appsecret") or "").strip()),
            None,
        )
        if not cred:
            return {
                "success": False,
                "message": "未配置微信公众号 AppID / AppSecret，请先在「配置 → 发布平台」填写并保存",
            }

        result = await test_wechat_credential(
            WechatCredentialTest(appid=cred["appid"].strip(), appsecret=cred["appsecret"].strip())
        )
        status = result.get("status", "error")
        # warning = 凭证有效但未认证，仍可定时生成；发布可能仅草稿
        ok = status in ("success", "warning")
        return {"success": ok, "message": result.get("message", "验证失败")}
    except Exception as e:
        log.print_log(f"[Scheduler] 公众号连接检测异常: {e}", "error")
        return {"success": False, "message": f"检测异常: {str(e)}"}


@router.get("/wechat-credentials")
async def get_wechat_credentials():
    """获取已配置的微信公众号凭证列表（脱敏）"""
    try:
        from src.ai_write_x.core.account_profiles import AccountProfileService
        return [
            {
                "account_id": item.get("account_id"),
                "appid": item.get("appid", ""),
                "author": item.get("author") or item.get("name") or "",
                "name": item.get("name") or item.get("author") or "",
                "draft_only": item.get("draft_only", False),
                "status": item.get("status"),
                "enabled": item.get("enabled", True),
            }
            for item in AccountProfileService().list_public()
            if item.get("appid")
        ]
    except Exception as e:
        log.print_log(f"[Scheduler] 获取凭证列表失败: {e}", "error")
        return []
