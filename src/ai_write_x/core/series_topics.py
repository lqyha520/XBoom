# -*- coding: UTF-8 -*-
"""通用系列选题规划与范围校验。"""

from __future__ import annotations

import json
import re
from typing import Callable, Iterable, Sequence


class SeriesTopicPlanningError(RuntimeError):
    """系列子话题无法通过范围审核。"""


def normalize_series_name(value: str) -> str:
    """从用户输入中提取稳定的系列名称。"""
    text = re.sub(r"\s+", " ", str(value or "")).strip().strip("《》\"'“”‘’")
    separator_positions = [pos for pos in (text.find("："), text.find(":")) if pos >= 0]
    if separator_positions:
        prefix = text[: min(separator_positions)].strip()
        if prefix:
            text = prefix
    return text[:80]


def sanitize_subtopic(value: str, series_name: str) -> str:
    """清理模型输出格式，仅移除当前系列自身的前缀。"""
    text = str(value or "").strip()
    text = re.sub(r"^\s*(?:[-*•]+|\d+[.)、：:]?)\s*", "", text)
    text = text.strip().strip("《》\"'“”‘’")

    normalized_series = normalize_series_name(series_name)
    for separator in ("：", ":"):
        prefix = f"{normalized_series}{separator}"
        if normalized_series and text.casefold().startswith(prefix.casefold()):
            text = text[len(prefix):].strip()
            break

    return re.sub(r"\s+", " ", text).strip()


def compose_series_title(series_name: str, subtopic: str) -> str:
    series = normalize_series_name(series_name)
    cleaned = sanitize_subtopic(subtopic, series)
    return f"{series}：{cleaned}"


def filter_recent_topics_for_series(
    topics: Iterable[str],
    series_name: str,
    *,
    limit: int = 20,
) -> list[str]:
    """只保留同一系列的历史选题，避免跨领域历史污染提示词。"""
    series = normalize_series_name(series_name).casefold()
    if not series:
        return []

    matched: list[str] = []
    seen: set[str] = set()
    for raw_topic in topics or []:
        topic = str(raw_topic or "").strip()
        if not topic:
            continue
        prefix = normalize_series_name(topic).casefold()
        if prefix != series:
            continue
        key = topic.casefold()
        if key in seen:
            continue
        seen.add(key)
        matched.append(topic)
        if len(matched) >= limit:
            break
    return matched


def _extract_json_payload(text: str):
    cleaned = str(text or "").strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    for start_char, end_char in (("{", "}"), ("[", "]")):
        start = cleaned.find(start_char)
        end = cleaned.rfind(end_char)
        if start >= 0 and end > start:
            try:
                return json.loads(cleaned[start : end + 1])
            except json.JSONDecodeError:
                continue
    return None


def parse_topic_candidates(text: str, series_name: str) -> list[str]:
    """兼容 JSON、Markdown 列表和纯文本行。"""
    payload = _extract_json_payload(text)
    if isinstance(payload, dict):
        raw_topics = payload.get("topics") or payload.get("data") or []
    elif isinstance(payload, list):
        raw_topics = payload
    else:
        raw_topics = [line for line in str(text or "").splitlines() if line.strip()]

    topics: list[str] = []
    seen: set[str] = set()
    for item in raw_topics:
        if isinstance(item, dict):
            item = item.get("title") or item.get("topic") or ""
        topic = sanitize_subtopic(str(item or ""), series_name)
        key = topic.casefold()
        if not topic or key in seen:
            continue
        seen.add(key)
        topics.append(topic)
    return topics


def _has_valid_structure(topics: Sequence[str], count: int, series_name: str) -> bool:
    if len(topics) != count:
        return False
    series = normalize_series_name(series_name).casefold()
    seen: set[str] = set()
    for topic in topics:
        cleaned = sanitize_subtopic(topic, series_name)
        key = cleaned.casefold()
        if len(cleaned) < 4 or len(cleaned) > 120 or key == series or key in seen:
            return False
        seen.add(key)
    return True


def _call_chat(chat: Callable, prompt: str, temperature: float) -> str:
    return str(chat([{"role": "user", "content": prompt}], temperature=temperature) or "").strip()


def plan_series_topics(
    chat: Callable,
    series_name: str,
    count: int,
    *,
    seed_topic: str = "",
    recent_topics: Iterable[str] = (),
    used_topics: Iterable[str] = (),
    max_review_attempts: int = 2,
) -> list[str]:
    """生成并审核任意领域的系列子话题，审核失败时停止而不是带病写作。"""
    series = normalize_series_name(series_name)
    count = max(1, int(count or 1))
    if not series:
        raise SeriesTopicPlanningError("合集模式缺少有效的系列名称")

    scoped_recent = filter_recent_topics_for_series(
        list(recent_topics or []) + list(used_topics or []),
        series,
        limit=30,
    )
    excluded = "、".join(scoped_recent) if scoped_recent else "无"
    seed_direction = sanitize_subtopic(seed_topic, series)
    if seed_direction.casefold() == series.casefold():
        seed_direction = ""
    direction_text = seed_direction or "由你在系列范围内选择最有价值的不同切入点"
    generation_prompt = f"""你是通用内容系列选题策划器。
系列范围：{series}
本次方向：{direction_text}
需要生成：{count} 个互不重复的子话题
同系列已用选题：{excluded}

规则：
1. 每个子话题必须是“{series}”的直接下位主题，不能借用其他领域的话题。
2. 不要输出系列前缀，不要输出序号，不要解释。
3. 话题需要具体、可独立写成一篇文章，并且彼此切入点不同。
4. 严格输出 JSON：{{"topics":["子话题1","子话题2"]}}，数组数量必须等于 {count}。
"""

    try:
        generated = _call_chat(chat, generation_prompt, 0.8)
    except Exception as exc:
        raise SeriesTopicPlanningError(f"系列子话题生成失败：{exc}") from exc
    candidates = parse_topic_candidates(generated, series)

    last_issue = "候选数量或格式不正确"
    for attempt in range(max(1, max_review_attempts)):
        review_prompt = f"""你是独立的“系列范围审计器”，适用于任何内容领域。
系列范围：{series}
本次方向：{direction_text}
目标数量：{count}
候选子话题：{json.dumps(candidates, ensure_ascii=False)}
同系列已用选题：{excluded}

请逐条进行语义审核，并直接修复不合格项：
- 必须是“{series}”的直接子话题；仅仅标题里出现系列名不算合格。
- 不得属于另一个无关领域，不得带其他系列前缀。
- 不得与已用选题或候选项重复。
- 修复后的话题不带“{series}”前缀，数量必须严格等于 {count}。

valid 表示“修复后的 topics 是否全部合格”，不是评价原候选。
严格输出 JSON：{{"valid":true,"topics":["..."],"issues":[]}}
"""
        try:
            reviewed_text = _call_chat(chat, review_prompt, 0.2)
        except Exception as exc:
            last_issue = f"范围审核调用失败：{exc}"
            continue

        payload = _extract_json_payload(reviewed_text)
        reviewed_topics = parse_topic_candidates(reviewed_text, series)
        valid = isinstance(payload, dict) and payload.get("valid") is True
        if valid and _has_valid_structure(reviewed_topics, count, series):
            return [compose_series_title(series, topic) for topic in reviewed_topics]

        if reviewed_topics:
            candidates = reviewed_topics
        issues = payload.get("issues") if isinstance(payload, dict) else None
        last_issue = f"第 {attempt + 1} 次范围审核未通过"
        if issues:
            last_issue += f"：{issues}"

    raise SeriesTopicPlanningError(
        f"系列“{series}”的子话题连续 {max(1, max_review_attempts)} 次未通过范围审核；{last_issue}"
    )
