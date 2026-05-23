# -*- coding: utf-8 -*-
"""全站统一品牌视觉：配色、排版约束（供 HTML 包装 / 换模板 / 模块化模板共用）"""

from typing import Dict

from src.ai_write_x.config.config import Config


def get_page_design() -> dict:
    try:
        return Config.get_instance().config.get("page_design") or {}
    except Exception:
        return {}


def is_unified_brand_style() -> bool:
    """是否启用统一品牌风格（默认开启）"""
    return bool(get_page_design().get("unified_brand_style", True))


def get_brand_colors() -> Dict[str, str]:
    """从 page_design 读取品牌色，带合理默认值"""
    pd = get_page_design()
    accent = pd.get("accent") or {}
    typo = pd.get("typography") or {}
    card = pd.get("card") or {}
    container = pd.get("container") or {}

    primary = accent.get("primary_color") or "#3a7bd5"
    secondary = accent.get("secondary_color") or "#2563a8"
    return {
        "primary": primary,
        "secondary": secondary,
        "accent": accent.get("accent_color") or primary,
        "highlight_bg": accent.get("highlight_bg") or "#f0f7ff",
        "text": typo.get("text_color") or "#333333",
        "heading": typo.get("heading_color") or "#2c3e50",
        "bg": container.get("background_color") or "#f5f7fa",
        "card_bg": card.get("background_color") or "#ffffff",
    }


def get_brand_style_prompt() -> str:
    """注入到 LLM 排版/设计提示词中的统一配色约束"""
    if not is_unified_brand_style():
        return ""
    c = get_brand_colors()
    return f"""
【品牌统一视觉 — 必须严格遵守】
- 主色 primary: {c['primary']}（标题装饰、重点强调、章节条）
- 辅色 secondary: {c['secondary']}（副标题、次要装饰，与主色同色系）
- 正文色: {c['text']}，标题色: {c['heading']}
- 页面背景: {c['bg']}，卡片/区块背景: {c['card_bg']}
- 引用/高亮块背景: {c['highlight_bg']}

禁止事项：
- 禁止因话题改用大红、大绿、大紫等另一套主色（避免账号内文章风格割裂）
- 禁止同一篇文章内主色与辅色来自完全不同色相（如红配绿）
- 装饰元素只能使用上述色值的深浅变化或 rgba 透明度变体
"""


def get_brand_design_scheme():
    """供 ModularTemplateBuilder 使用的固定 DesignScheme"""
    from src.ai_write_x.core.adaptive_template_engine import DesignScheme

    c = get_brand_colors()
    return DesignScheme(
        name="品牌统一",
        primary_color=c["primary"],
        secondary_color=c["secondary"],
        accent_color=c["accent"],
        bg_color=c["bg"],
        text_color=c["text"],
        style_features=["统一品牌", "公众号"],
    )
