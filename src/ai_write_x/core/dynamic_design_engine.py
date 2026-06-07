# -*- coding: utf-8 -*-
import json
import random
import re
from typing import Dict, Any, List, Optional
from src.ai_write_x.utils.path_manager import PathManager
import src.ai_write_x.utils.log as lg

class DynamicDesignEngine:
    """动态设计引擎 - 积木化排版系统"""
    
    _instance = None
    
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self.design_elements = {}
        self.color_system = {}
        self.load_config()

    def load_config(self):
        """加载设计元素和色彩系统配置"""
        try:
            config_dir = PathManager.get_config_dir()
            bundled_config_dir = PathManager.get_base_dir() / "config"
            design_path = config_dir / "design_elements.json"
            color_path = config_dir / "color_system.json"
            if not design_path.exists():
                design_path = bundled_config_dir / "design_elements.json"
            if not color_path.exists():
                color_path = bundled_config_dir / "color_system.json"
            
            if design_path.exists():
                with open(design_path, "r", encoding="utf-8") as f:
                    self.design_elements = json.load(f)
            
            if color_path.exists():
                with open(color_path, "r", encoding="utf-8") as f:
                    self.color_system = json.load(f)
                    
            lg.print_log("DynamicDesignEngine config loaded successfully", "success")
        except Exception as e:
            lg.print_log(f"DynamicDesignEngine config load failed: {e}", "error")

    def select_palette(self, content: str, topic: str = "") -> Dict[str, str]:
        """根据内容和话题选择色彩方案；统一品牌模式下固定为配置中的品牌色。"""
        from src.ai_write_x.core.brand_style import get_brand_colors, is_unified_brand_style

        if is_unified_brand_style():
            brand = get_brand_colors()
            return {
                "primary": brand["primary"],
                "accent": brand["secondary"],
                "background": brand["bg"],
                "text": brand["text"],
            }

        if not self.color_system:
            return {}
            
        palettes = self.color_system.get("color_palettes", {})
        rules = self.color_system.get("selection_rules", {})
        mapping = rules.get("keyword_mapping", {})
        fallback = rules.get("fallback", "news")
        
        # 1. 关键词特征提取
        text_to_scan = (topic + " " + content[:1000]).lower()
        
        selected_key = None
        for keywords, palette_name in mapping.items():
            keyword_list = keywords.split("/")
            if any(kw.lower() in text_to_scan for kw in keyword_list):
                selected_key = palette_name
                break
        
        # 2. 随机化因子 (如果有的话)
        if random.random() < rules.get("randomization_factor", 0.0):
            selected_key = random.choice(list(palettes.keys()))
            
        # 3. 兜底
        if not selected_key or selected_key not in palettes:
            selected_key = fallback
            
        return palettes.get(selected_key, palettes.get(fallback, {}))

    def get_wechat_system_template(self, content: str, topic: str = "") -> str:
        """生成微信公众号专用的系统提示词"""
        from src.ai_write_x.core.brand_style import get_brand_style_prompt, is_unified_brand_style

        palette = self.select_palette(content, topic)
        unified = is_unified_brand_style()
        
        # 提取颜色变量
        p_color = palette.get("primary", "#4a5568")
        a_color = palette.get("accent", "#718096")
        b_color = palette.get("background", "#f7fafc")
        t_color = palette.get("text", "#2d3748")
        
        # 将 RGB 转换
        def hex_to_rgb_str(hex_color):
            hex_color = hex_color.lstrip('#')
            if len(hex_color) == 6:
                r, g, b = struct.unpack('BBB', bytes.fromhex(hex_color))
                return f"{r}, {g}, {b}"
            return "74, 85, 104"

        import struct
        p_rgb = hex_to_rgb_str(p_color)

        # 构建元素库描述
        elements_desc = ""
        for category, items in self.design_elements.items():
            elements_desc += f"\n### {category.upper()}\n"
            if isinstance(items, dict):
                for name, info in items.items():
                    html = info.get("html", info) if isinstance(info, dict) else info
                    desc = info.get("description", "") if isinstance(info, dict) else ""
                    # 替换基础占位符
                    html_preview = html.replace("{{primary_color}}", p_color)\
                                       .replace("{{accent_color}}", a_color)\
                                       .replace("{{bg_color}}", b_color)\
                                       .replace("{{primary_rgb}}", p_rgb)
                    elements_desc += f"- **{name}**: `{html_preview}` ({desc})\n"

        brand_block = get_brand_style_prompt() if unified else ""

        if unified:
            layout_rules = """
## 【排版逻辑 — 统一公众号版式】
1. **固定母体框架**：全文统一使用 `gold_price_v1` 或 `card` 类白色正文卡片结构，**禁止**因话题切换为 `golden_intro_v2`、`magazine_style` 等其他 DNA。
2. **布局稳定**：顶部标题区 + 白色正文卡片 + 章节小标题左侧色条（使用品牌主色），各篇文章版式保持一致。
3. **黄金开头**：正文第一行必须是纯文本金句；第一段文字前禁止放配图占位符。
4. **视觉节奏**：每 300-500 字使用 `<h2>`；金句用 `quote_highlight` 或 `quote_box`。
5. **禁止**：红绿撞色、每篇随机换紫/橙/绿主色、负数 margin 导致文字压图。
"""
            task_core = "本次任务核心：**统一品牌公众号排版**（全站版式一致，仅允许间距/圆角微调）。"
        else:
            layout_rules = """
## 【排版逻辑与突变指令 (V20.2 绝不越界)】
1. **DNA 继承与多样化**：
   - 严肃/财经话题：优先使用 `gold_price_v1`。
   - 情感/爆款话题：**必须使用** `golden_intro_v2`。
   - 文艺/生活话题：尝试 `magazine_style`。
2. **黄金开头极致前置 (绝对命令)**：
   - **正文第一行必须是纯文本金句**。
   - **严禁在第一段文字前放置任何 `<img>`、`div.img-placeholder` 或 `V-SCENE` 占位符**。
3. **视觉布局严禁重叠**：
   - **严禁使用负数 margin**，所有元素保持正常文档流。
4. **色彩与对比度优先**：
   - 浅色背景上文字使用 `#333333` 或 `#000000`。
5. **视觉节奏 (Rhythm)**：
   - 每 300-500 字必须使用一次 `<h2>` 标题装饰。
"""
            task_core = "本次任务核心：**基底 DNA 继承与视觉突变**。"

        template = f"""<|start_header_id|>system<|end_header_id|>
# 微信公众号动态排版设计规范 - 元素积木系统 (V19.6 V-TEMPLATE)

## 【核心任务】
你是一位顶级视觉艺术总监。你的任务是将文章内容转换为**可直接发布**的精美 HTML。
{task_core}
{brand_block}

## 【本次选定的色彩方案】
- **主色调 (Primary)**: `{p_color}`
- **强调色 (Accent)**: `{a_color}`
- **背景底色 (Background)**: `{b_color}`
- **文字主色 (Text)**: `{t_color}`

## 【设计元素库】
重点参考 `STRUCTURAL_DNA` 类别的组件，将其作为整篇文章的母体框架：
{elements_desc}
{layout_rules}

## 【强制规范】
- **100% 内联样式**：严禁使用 `class` 或 `<style>` 标签。
- **严禁 Markdown**：禁止输出 `**`、`##` 等符号，必须完全使用纯净的 HTML 标签进行排版。
- **图像占位符强制规范**：必须使用 `<div class="img-placeholder" data-img-prompt="..." data-aspect-ratio="16:9"></div>`。
- **输出格式**：仅输出 ```html ``` 代码块。直接从最外层容器开始输出。

现在请开始处理：
<|eot_id|>"""
        return template
