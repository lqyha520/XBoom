# -*- coding: utf-8 -*-
"""成稿轻量后处理：提升可读性，清理常见 AI 排版问题"""

import re
from typing import Optional

from bs4 import BeautifulSoup, Comment

# 英文镜头/电影术语 → 中文（用于后处理兜底）
_SHOT_LABEL_REPLACEMENTS = [
    (re.compile(r"Cinematic\s+wide\s+shot[^<]*", re.I), "远景全景"),
    (re.compile(r"Medium\s+close-up[^<]*", re.I), "中景特写"),
    (re.compile(r"Action\s+shot[^<]*", re.I), "动态瞬间"),
    (re.compile(r"Macro\s+detail[^<]*", re.I), "细节微距"),
    (re.compile(r"Intimate\s+portrait[^<]*", re.I), "温情特写"),
    (re.compile(r"CINEMATIC\s*SHOTS?[^<]*", re.I), "镜头赏析"),
    (re.compile(r"\bVisual\s+Storytelling\b", re.I), "视觉叙事"),
    (re.compile(r"\bConceptual\b[^<]{0,20}", re.I), "意象构图"),
    (re.compile(r"\bEmotional\b[^<]{0,20}", re.I), "情感瞬间"),
]

_READABILITY_WRITING_RULES = """
【可读性与语言规范 — 必须遵守】
1. 全文使用自然中文，面向公众号读者，不要写成电影分镜脚本或摄影教程。
2. 禁止使用 Wide shot、Cinematic、Medium close-up 等英文镜头术语作为章节标题。
3. 小标题用中文概括观点（如「田野里的守护者」），每段不超过 150 字，单句尽量不超过 35 字。
4. 减少空洞形容词堆砌，每段至少包含一个具体事实、场景或观点。
"""


def get_readability_writing_rules() -> str:
    return _READABILITY_WRITING_RULES.strip()


def is_lifestyle_or_pet_topic(topic: str = "", content: str = "") -> bool:
    text = f"{topic} {content[:500]}"
    keywords = (
        "狗", "犬", "猫", "宠物", "田园", "动物", "生活", "美食", "旅行",
        "养生", "情感", "故事", "日常", "萌", "养宠",
    )
    return any(kw in text for kw in keywords)


# 注意：并非所有图片服务都支持专用 negative_prompt 字段或 `--no` 语法。
# 我们仍维护一份“禁字负面词库”，供 prompt 拼接/解析时复用（尽量覆盖常见出字场景）。
_NO_TEXT_NEG = (
    # 文字叠加形态（Z-Image Turbo对具体形态描述响应更好）
    "text overlay, written text, printed text, painted text, engraved text, floating text, "
    "text bubble, speech bubble, title card, headline, article title, chapter heading, page header, "
    "text caption, subtitle bar, lower third, "
    # 文字载体
    "text watermark, text logo, text signature, text stamp, text label, text tag, "
    "calligraphy text, brush writing, hand lettering, chalk writing, "
    "neon sign text, signboard text, poster text, banner text, billboard text, "
    "book title text, magazine cover text, newspaper headline, document text, "
    "screen text, UI text, menu text, "
    # 语言/字符
    "Chinese characters, Hanzi, Kanji, English letters, numbers, digits, "
    # 机器码
    "QR code, barcode, "
    # 错误形态
    "garbled text, gibberish text, text distortion, "
    # Z-Image Turbo特有质量约束（具体化描述比泛化词更有效）
    "deformed iris, double eyelashes, smudged pupils, "
    "extra fingers, fused fingers, malformed hands, "
    "bad anatomy, blurry face, duplicate features, "
    "color bleeding, oversaturated skin, grayish skin tone"
)

_SCENE_LABEL_RE = re.compile(
    r"^\s*(?:场景描述|画面描述|配图描述|生图提示|视觉分镜|镜头描述)[：:\s]",
    re.I | re.M,
)


def _looks_like_image_prompt(text: str) -> bool:
    """判断是否为误展示给读者的生图提示词"""
    if not text or len(text) < 50:
        return False
    lower = text.lower()
    markers = (
        "bad anatomy", "watermark", "16:9", "2.35:1", "8k", "unreal engine",
        "illustration style", "digital painting", "split diorama", "no text",
        "legible", "typography", "| bad", "octane render", "editorial illustration",
    )
    hits = sum(1 for m in markers if m in lower)
    zh_markers = (
        "镜头", "广角", "特写", "中景", "近景", "远景", "构图", "光影", "光线",
        "背景", "画面", "景深", "焦点", "8k", "电影感", "写实摄影",
    )
    zh_hits = sum(1 for m in zh_markers if m in text)
    return hits >= 2 or zh_hits >= 2 or ("|" in text and "bad" in lower)


_CONTENT_CONTAINER_RE = re.compile(r"rich|article|content|post|media", re.I)

_META_ENDING_LABEL_RE = re.compile(
    r"^\s*(?:第?[一二三四五六七八九十百\d]+(?:部分|节)?[、.．:：]\s*)?"
    r"(?:结尾|结语|总结|写在最后|最后的话|结论|收尾|尾声|后记|内容创作)"
    r"(?:[：:\-—|]\s*)?",
    re.I,
)

_META_COMMENT_RE = re.compile(
    r"(?:结尾|结语|总结|写在最后|最后的话|结论|收尾|尾声|后记|内容创作|"
    r"下一次汇报|准备怎么开始|本文将|接下来我们将)",
    re.I,
)

_META_PARAGRAPH_PATTERNS = [
    re.compile(r"你的下一次.{0,12}汇报.{0,12}准备怎么开始", re.I),
    re.compile(r"^(?:以上就是|本文将|本文主要|接下来我们将|接下来，让我们|在本文中|希望本文)", re.I),
    re.compile(r"^(?:总而言之|综上所述|总之|由此可见)[，,：:\s]", re.I),
]

_META_LABEL_ONLY_RE = re.compile(
    r"^\s*(?:第?[一二三四五六七八九十百\d]+(?:部分|节)?[、.．:：]\s*)?"
    r"(?:结尾|结语|总结|写在最后|最后的话|结论|收尾|尾声|后记|内容创作)"
    r"\s*[：:：\-—]?\s*$",
    re.I,
)


def _strip_meta_heading_prefix(text: str) -> tuple[str, bool]:
    stripped = (text or "").strip()
    if not stripped:
        return text, False
    cleaned = _META_ENDING_LABEL_RE.sub("", stripped, count=1).strip()
    return cleaned, cleaned != stripped


def _is_meta_template_paragraph(text: str) -> bool:
    stripped = re.sub(r"\s+", " ", (text or "").strip())
    if not stripped:
        return False
    if _META_LABEL_ONLY_RE.match(stripped):
        return True
    for pattern in _META_PARAGRAPH_PATTERNS:
        if pattern.search(stripped):
            return True
    if stripped.startswith("#") and "内容创作" in stripped and len(stripped) < 80:
        return True
    return False


def _is_protected_content_tag(tag) -> bool:
    """正文容器或其内部段落，避免被误删"""
    if tag.name in {"article", "section", "main", "body"}:
        return True
    for node in [tag, *list(tag.parents)]:
        if getattr(node, "name", None) in {"article", "section", "main", "body"}:
            return True
        classes = " ".join(node.get("class") or []) if hasattr(node, "get") else ""
        if classes and _CONTENT_CONTAINER_RE.search(classes):
            return True
    return False


def strip_leaked_prompt_text(html: str) -> str:
    """移除正文中误展示的生图提示（保留正文与 img-placeholder）"""
    if not html or not html.strip():
        return html

    html = re.sub(
        r"<(?:p|em|i|blockquote|div)[^>]*>\s*(?:场景描述|画面描述)[：:][\s\S]*?</(?:p|em|i|blockquote|div)>",
        "",
        html,
        flags=re.I,
    )

    if "<" not in html:
        lines = []
        for line in html.splitlines():
            stripped = line.strip()
            if _SCENE_LABEL_RE.match(stripped):
                continue
            if _looks_like_image_prompt(stripped):
                continue
            lines.append(line)
        return re.sub(r"\n{3,}", "\n\n", "\n".join(lines))

    soup = BeautifulSoup(html, "html.parser")
    for tag in list(soup.find_all(["p", "em", "i", "blockquote", "div", "span"])):
        text = tag.get_text(" ", strip=True)
        if not text:
            continue
        is_protected = _is_protected_content_tag(tag)
        if _SCENE_LABEL_RE.match(text) or text.startswith("场景描述"):
            tag.decompose()
            continue
        # 仅删除“纯提示词泄漏”的短块；长正文块即使含英文技术词也保留
        if (
            _looks_like_image_prompt(text)
            and len(text) < (220 if is_protected else 120)
            and "img-placeholder" not in (tag.get("class") or [])
        ):
            tag.decompose()

    return soup.decode(formatter=None)


def clean_meta_template_phrases(html: str) -> str:
    """移除“结尾/写在最后/内容创作”等模板标签和元提示残留。"""
    if not html or not html.strip():
        return html

    if "<" not in html:
        cleaned_lines = []
        for line in html.splitlines():
            stripped = line.strip()
            if _is_meta_template_paragraph(stripped):
                continue
            cleaned, changed = _strip_meta_heading_prefix(stripped)
            if changed:
                if cleaned and len(cleaned) >= 6 and not _is_meta_template_paragraph(cleaned):
                    prefix = line[: len(line) - len(line.lstrip())]
                    cleaned_lines.append(prefix + cleaned)
                continue
            cleaned_lines.append(line)
        return re.sub(r"\n{3,}", "\n\n", "\n".join(cleaned_lines)).strip()

    soup = BeautifulSoup(html, "html.parser")

    for comment in list(soup.find_all(string=lambda text: isinstance(text, Comment))):
        if _META_COMMENT_RE.search(str(comment)):
            comment.extract()

    for tag in list(soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])):
        text = tag.get_text(" ", strip=True)
        if not text:
            continue
        if _is_meta_template_paragraph(text):
            tag.decompose()
            continue
        cleaned, changed = _strip_meta_heading_prefix(text)
        if changed:
            if cleaned and len(cleaned) >= 6 and not _is_meta_template_paragraph(cleaned):
                tag.clear()
                tag.append(cleaned)
            else:
                tag.decompose()

    for tag in list(soup.find_all(["p", "div", "span", "blockquote", "li", "em", "strong"])):
        if tag.find(["img", "video", "audio", "table"]):
            continue
        if tag.name in {"div", "blockquote", "li"} and tag.find(["p", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "li"]):
            continue
        text = tag.get_text(" ", strip=True)
        if not text:
            continue
        if _is_meta_template_paragraph(text):
            tag.decompose()
            continue
        cleaned, changed = _strip_meta_heading_prefix(text)
        if changed and cleaned and len(cleaned) >= 8:
            tag.clear()
            tag.append(cleaned)

    return re.sub(r"\n{3,}", "\n\n", soup.decode(formatter=None)).strip()


def strip_unprocessed_visual_markers(html: str) -> str:
    """移除未成功替换的 V-SCENE / 空占位符（生图完成后调用）"""
    if not html:
        return html
    html = re.sub(r"\[\[V-SCENE:.*?\]\]", "", html, flags=re.DOTALL | re.I)
    html = re.sub(r"\[IMG_PROMPT:.*?\]", "", html, flags=re.DOTALL | re.I)
    html = re.sub(r"\[图片解析[:：].*?\]", "", html, flags=re.DOTALL | re.I)

    if "<" in html:
        soup = BeautifulSoup(html, "html.parser")
        for ph in soup.find_all(class_="img-placeholder"):
            ph.decompose()
        return soup.decode(formatter=None)
    return re.sub(r"\n{3,}", "\n\n", html)


def append_no_text_negative(neg: str = "") -> str:
    base = neg.strip() if neg else ""
    for token in _NO_TEXT_NEG.split(", "):
        if token not in base:
            base = f"{base}, {token}" if base else token
    return base


def polish_html_output(html: str) -> str:
    """清理包装后 HTML：术语、泄露提示词、多余空白"""
    if not html or not html.strip():
        return html

    html = strip_leaked_prompt_text(html)
    html = clean_meta_template_phrases(html)

    for pattern, replacement in _SHOT_LABEL_REPLACEMENTS:
        html = pattern.sub(replacement, html)

    html = re.sub(r"\n{4,}", "\n\n", html)
    return html


def extract_plain_text(html_or_md: str, max_len: int = 1500) -> str:
    """从 HTML/Markdown 提取纯文本摘要"""
    if not html_or_md:
        return ""
    text = html_or_md
    if "<" in text and ">" in text:
        soup = BeautifulSoup(text, "html.parser")
        for tag in soup(["script", "style", "svg"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text[:max_len]


def _split_content_blocks(text: str) -> list:
    """将优化结果拆成可回填的文本块"""
    if not text or not text.strip():
        return []
    text = text.strip()
    if "<" in text and ">" in text:
        soup = BeautifulSoup(text, "html.parser")
        blocks = []
        for tag in soup.find_all(["p", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "li"]):
            t = tag.get_text(strip=True)
            if t:
                blocks.append(t)
        if blocks:
            return blocks
    parts = re.split(r"\n\s*\n+", text)
    blocks = [p.strip() for p in parts if p.strip()]
    return blocks or [text]


def _normalize_block_for_tag(text: str, tag_name: str) -> str:
    t = text.strip()
    if tag_name and tag_name.startswith("h"):
        t = re.sub(r"^#+\s*", "", t)
    return t


def _set_tag_text(tag, text: str) -> None:
    tag.clear()
    text = _normalize_block_for_tag(text, tag.name or "p")
    if "<" in text and ">" in text:
        frag = BeautifulSoup(text, "html.parser")
        for child in list(frag.children):
            tag.append(child)
    else:
        tag.append(text)


def merge_optimized_preserving_images(original: str, optimized: str) -> str:
    """
    将 LLM 优化后的正文写回原文 HTML 骨架，保留已有 <img> 位置与模板结构。
    若优化结果已包含全部原图，则直接返回优化结果。
    """
    original = (original or "").strip()
    optimized = (optimized or "").strip()
    if not original:
        return optimized
    if not optimized:
        return original
    if "<" not in original.lower():
        return optimized

    soup = BeautifulSoup(original, "html.parser")
    imgs = soup.find_all("img")
    if not imgs:
        return optimized

    orig_srcs = [img.get("src", "") for img in imgs if img.get("src")]
    if "<" in optimized:
        opt_soup = BeautifulSoup(optimized, "html.parser")
        opt_srcs = [img.get("src", "") for img in opt_soup.find_all("img")]
        if orig_srcs and all(s in opt_srcs for s in orig_srcs):
            return polish_html_output(optimized)

    blocks = _split_content_blocks(optimized)
    if not blocks:
        return original

    text_tags = []
    for tag in soup.find_all(["p", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "li"]):
        if tag.find_parent(["script", "style", "svg"]):
            continue
        if tag.find("img") and len(tag.get_text(strip=True)) < 15:
            continue
        txt = tag.get_text(strip=True)
        if txt and len(txt) >= 3:
            text_tags.append(tag)

    if not text_tags:
        return optimized if "<" in optimized else original

    bi = 0
    for tag in text_tags:
        if bi >= len(blocks):
            tag.decompose()
            continue
        _set_tag_text(tag, blocks[bi])
        bi += 1

    if bi < len(blocks):
        host = (
            soup.find("article")
            or soup.find(class_=re.compile(r"rich|article|content|post", re.I))
            or soup.body
            or soup
        )
        for j in range(bi, len(blocks)):
            p = soup.new_tag("p")
            p.append(blocks[j])
            host.append(p)

    return polish_html_output(soup.decode(formatter=None))


def convert_scene_description_paragraphs_to_placeholders(html: str) -> str:
    """将 HTML 中误排版的「场景描述」段落转为可生图的 img-placeholder"""
    if not html or "<" not in html:
        return html

    soup = BeautifulSoup(html, "html.parser")
    changed = False
    for p in list(soup.find_all("p")):
        text = p.get_text(" ", strip=True)
        if not text:
            continue
        if not (_SCENE_LABEL_RE.match(text) or text.startswith("场景描述") or text.startswith("画面描述")):
            continue
        prompt_body = re.sub(
            r"^(?:场景描述|画面描述|配图描述)[：:\s]*",
            "",
            text,
            flags=re.I,
        ).strip()
        if len(prompt_body) < 20:
            continue

        ratio = "16:9"
        ratio_m = re.search(r"\|\s*([\d\.:]+)\s*$", prompt_body)
        if ratio_m:
            ratio = ratio_m.group(1).strip()
            prompt_body = prompt_body[: ratio_m.start()].strip()

        parts = [x.strip() for x in prompt_body.split("|") if x.strip()]
        pos_prompt = parts[0] if parts else prompt_body
        if len(pos_prompt) < 15:
            continue

        ph = soup.new_tag(
            "div",
            attrs={
                "class": "img-placeholder",
                "data-img-prompt": pos_prompt[:800],
                "data-aspect-ratio": ratio,
            },
        )
        ph.string = "配图生成中"
        p.replace_with(ph)
        changed = True

    return soup.decode(formatter=None) if changed else html


def clean_article_visual_leaks(html: str) -> str:
    """清理正文中的场景描述、泄露生图提示与未处理占位符"""
    if not html:
        return html
    html = strip_leaked_prompt_text(html)
    html = clean_meta_template_phrases(html)
    html = strip_unprocessed_visual_markers(html)
    return polish_html_output(html)


def normalize_title_candidate(raw: str) -> str:
    """清理标题候选中的说明、推荐标记等"""
    if not raw:
        return ""
    title = raw.strip()
    title = re.sub(r"^[《》\"'「」『』]+|[《》\"'「」『』]+$", "", title)
    for sep in ("说明：", "说明:", "——", "--"):
        if sep in title:
            title = title.split(sep, 1)[0].strip()
    title = title.replace("[⭐推荐]", "").replace("⭐推荐", "").strip()
    title = re.sub(r"^(悬念型|数字型|冲突型|情绪型|实用型)[：:]\s*", "", title)
    title = re.sub(r"\s+", " ", title)
    return title
