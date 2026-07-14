"""公众号账号列表接口。

账号的创建、编辑、删除和凭证检测统一在“设置 → 微信公众号”完成；
这里仅保留内容生成和定时任务用于选择目标账号的只读接口。
"""

from fastapi import APIRouter

from src.ai_write_x.core.account_profiles import AccountProfileService


router = APIRouter(prefix="/api/accounts", tags=["WeChat accounts"])


@router.get("")
async def list_accounts():
    return {"status": "success", "data": AccountProfileService().list_public()}
