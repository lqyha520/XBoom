# -*- coding: utf-8 -*-
"""问题反馈 API"""

import platform
import base64
from datetime import datetime
from typing import Optional
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.ai_write_x.version import get_version

router = APIRouter(prefix="/api/feedback", tags=["feedback"])


class FeedbackRequest(BaseModel):
    """反馈请求模型"""
    type: str = Field(..., description="反馈类型: bug/feature/question/other")
    description: str = Field(..., min_length=10, max_length=1000, description="问题描述")
    reproduce_steps: Optional[str] = Field(None, description="复现步骤（Bug时）")
    contact: Optional[str] = Field(None, description="联系方式")
    screenshots: Optional[list[str]] = Field(default=[], description="截图base64列表")


class FeedbackResponse(BaseModel):
    """反馈响应模型"""
    success: bool
    message: str
    feedback_id: Optional[str] = None


FEISHU_WEBHOOK_URL = "https://open.feishu.cn/open-apis/bot/v2/hook/e6df0dee-828f-43ed-8ca0-c3b920ff022c"
IMGBB_API_KEY = "34e0e957cb1bbbe35cd6397aa437e31c"


def _upload_screenshot_to_imgbb(screenshot_base64: str) -> Optional[str]:
    """上传截图到 ImgBB 图床，返回图片 URL"""
    if not IMGBB_API_KEY:
        return None
    try:
        response = httpx.post(
            "https://api.imgbb.com/1/upload",
            data={"key": IMGBB_API_KEY, "image": screenshot_base64},
            timeout=15
        )
        
        result = response.json()
        if result.get("success"):
            return result["data"]["url"]
        else:
            print(f"上传图片失败: {result.get('error', {}).get('message', 'Unknown error')}")
            return None
    except Exception as e:
        print(f"上传截图到图床失败: {e}")
        return None


def _get_system_info() -> dict:
    """采集系统信息"""
    return {
        "version": get_version(),
        "platform": platform.system(),
        "platform_version": platform.version(),
        "python_version": platform.python_version(),
        "machine": platform.machine(),
    }


def _send_to_feishu(webhook_url: str, feedback_data: dict, screenshot_urls: list[str] = None) -> bool:
    """发送反馈到飞书机器人（包含截图链接）"""
    
    type_map = {
        "bug": "🐛 Bug反馈",
        "feature": "💡 功能建议", 
        "question": "❓ 使用问题",
        "other": "📝 其他反馈"
    }
    
    type_label = type_map.get(feedback_data["type"], "📝 反馈")
    sys_info = feedback_data["system_info"]
    
    # 构建飞书消息卡片
    content_lines = [
        f"**{type_label}**",
        "",
        f"**问题描述：**",
        feedback_data["description"],
    ]
    
    if feedback_data.get("reproduce_steps"):
        content_lines.extend([
            "",
            "**复现步骤：**",
            feedback_data["reproduce_steps"]
        ])
    
    # 添加截图链接
    if screenshot_urls:
        content_lines.extend(["", "**截图：**"])
        for i, url in enumerate(screenshot_urls, 1):
            content_lines.append(f"📷 截图{i}：{url}")
    elif feedback_data.get("screenshot_count") and feedback_data["screenshot_count"] > 0:
        content_lines.extend([
            "",
            f"**截图数量：** {feedback_data['screenshot_count']} 张（已保存到本地）"
        ])
    
    if feedback_data.get("contact"):
        content_lines.extend([
            "",
            f"**联系方式：** {feedback_data['contact']}"
        ])
    
    content_lines.extend([
        "",
        "---",
        f"**系统信息：**",
        f"版本：{sys_info['version']}",
        f"操作系统：{sys_info['platform']} {sys_info['platform_version']}",
        f"Python：{sys_info['python_version']}",
        f"提交时间：{feedback_data['timestamp']}"
    ])
    
    message = {
        "msg_type": "post",
        "content": {
            "post": {
                "zh_cn": {
                    "title": f"【小爆来咯】{type_label}",
                    "content": [
                        [{"tag": "text", "text": line}] 
                        for line in content_lines
                    ]
                }
            }
        }
    }
    
    try:
        response = httpx.post(webhook_url, json=message, timeout=10)
        response.raise_for_status()
        return True
    except Exception as e:
        print(f"发送飞书消息失败: {e}")
        return False


def _save_local_backup(feedback_data: dict, screenshots: list[str] = None) -> str:
    """本地备份反馈数据（包含截图）"""
    feedback_dir = Path("feedback")
    feedback_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    feedback_id = f"feedback_{timestamp}"
    
    # 保存截图
    screenshot_paths = []
    if screenshots:
        screenshots_dir = feedback_dir / feedback_id
        screenshots_dir.mkdir(exist_ok=True)
        
        for i, screenshot_base64 in enumerate(screenshots):
            try:
                img_data = base64.b64decode(screenshot_base64)
                img_path = screenshots_dir / f"screenshot_{i+1}.png"
                with open(img_path, "wb") as f:
                    f.write(img_data)
                screenshot_paths.append(str(img_path))
            except Exception as e:
                print(f"保存截图 {i+1} 失败: {e}")
    
    # 保存反馈数据（包含截图路径）
    feedback_data_copy = feedback_data.copy()
    feedback_data_copy["screenshot_paths"] = screenshot_paths
    
    file_path = feedback_dir / f"{feedback_id}.json"
    import json
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(feedback_data_copy, f, ensure_ascii=False, indent=2)
    
    return feedback_id


@router.post("/submit", response_model=FeedbackResponse)
async def submit_feedback(req: FeedbackRequest):
    """提交问题反馈"""
    
    # 组装反馈数据
    feedback_data = {
        "type": req.type,
        "description": req.description,
        "reproduce_steps": req.reproduce_steps,
        "contact": req.contact,
        "screenshot_count": len(req.screenshots) if req.screenshots else 0,
        "system_info": _get_system_info(),
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    
    # 上传截图到图床
    screenshot_urls = []
    if req.screenshots:
        for screenshot_base64 in req.screenshots:
            url = _upload_screenshot_to_imgbb(screenshot_base64)
            if url:
                screenshot_urls.append(url)
    
    # 本地备份（包含截图）
    feedback_id = _save_local_backup(feedback_data, req.screenshots)
    
    # 发送到飞书
    success = _send_to_feishu(FEISHU_WEBHOOK_URL, feedback_data, screenshot_urls)
    if success:
        return FeedbackResponse(
            success=True,
            message="反馈已提交，感谢您的宝贵意见！",
            feedback_id=feedback_id
        )
    else:
        return FeedbackResponse(
            success=False,
            message="发送失败，但已本地保存。请联系开发者。",
            feedback_id=feedback_id
        )


@router.get("/webhook-status")
async def check_webhook_status():
    """检查飞书 Webhook 配置状态（开发者专用接口）"""
    return {
        "configured": bool(FEISHU_WEBHOOK_URL),
        "webhook_url": FEISHU_WEBHOOK_URL[:30] + "..." if len(FEISHU_WEBHOOK_URL) > 30 else FEISHU_WEBHOOK_URL
    }
