"""Reliable per-article checkpoints for batch content generation."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def normalize_checkpoint(value: Any) -> dict:
    raw = value if isinstance(value, dict) else {}
    topics = [str(item) for item in raw.get("topics", []) if str(item).strip()]
    completed = []
    for item in raw.get("completed", []):
        if not isinstance(item, dict):
            continue
        try:
            index = int(item.get("index"))
        except (TypeError, ValueError):
            continue
        topic = str(item.get("topic") or "")
        path = str(item.get("path") or "")
        if index < 0 or not path:
            continue
        completed.append({"index": index, "topic": topic, "path": path})
    completed.sort(key=lambda item: item["index"])
    return {"version": 1, "topics": topics, "completed": completed}


def with_topics(checkpoint: Any, topics: list[str]) -> dict:
    normalized = normalize_checkpoint(checkpoint)
    clean_topics = [str(topic) for topic in topics]
    if normalized["topics"] != clean_topics:
        normalized["topics"] = clean_topics
        normalized["completed"] = []
    return normalized

def valid_completed(checkpoint: Any, *, require_existing_paths: bool = True) -> list[dict]:
    normalized = normalize_checkpoint(checkpoint)
    topics = normalized["topics"]
    valid = []
    seen_indices = set()
    for item in normalized["completed"]:
        index = item["index"]
        if index in seen_indices or index >= len(topics):
            continue
        if item["topic"] and item["topic"] != topics[index]:
            continue
        if require_existing_paths and not Path(item["path"]).is_file():
            continue
        seen_indices.add(index)
        valid.append({**item, "topic": topics[index]})
    return valid


def mark_completed(checkpoint: Any, index: int, topic: str, path: str) -> dict:
    normalized = normalize_checkpoint(checkpoint)
    if index < 0 or index >= len(normalized["topics"]):
        raise IndexError("checkpoint index is outside the topic list")
    normalized["completed"] = [
        item for item in normalized["completed"] if item["index"] != index
    ]
    normalized["completed"].append(
        {"index": index, "topic": str(topic), "path": str(path)}
    )
    normalized["completed"].sort(key=lambda item: item["index"])
    return normalized
