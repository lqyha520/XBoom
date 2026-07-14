from src.ai_write_x.core.task_state_store import TaskStateStore
from src.ai_write_x.core.generation_checkpoint import (
    mark_completed,
    valid_completed,
    with_topics,
)
import asyncio
import pytest
from fastapi import HTTPException


def test_task_state_store_writes_and_loads_atomic_json(tmp_path):
    store = TaskStateStore(tmp_path)
    store.save(
        "main_generate",
        {
            "status": "running",
            "metadata": {"request": {"topic": "测试话题", "article_count": 2}},
            "progress": {"current": 1, "total": 2},
        },
    )

    state = store.load("main_generate")
    assert state["status"] == "running"
    assert state["metadata"]["request"]["topic"] == "测试话题"
    assert state["progress"] == {"current": 1, "total": 2}
    assert list(tmp_path.glob("*.tmp")) == []


def test_running_task_is_marked_interrupted_without_losing_request(tmp_path):
    store = TaskStateStore(tmp_path)
    store.save(
        "main_generate",
        {
            "status": "running",
            "metadata": {"request": {"topic": "可恢复话题"}},
            "progress": {"current": 1, "total": 3},
        },
    )

    interrupted = store.mark_running_interrupted()
    state = store.load("main_generate")

    assert interrupted == ["main_generate"]
    assert state["status"] == "interrupted"
    assert state["metadata"]["request"]["topic"] == "可恢复话题"
    assert state["progress"] == {"current": 1, "total": 3}
    assert state["finished_at"] > 0


def test_terminal_task_is_not_reclassified_as_interrupted(tmp_path):
    store = TaskStateStore(tmp_path)
    store.save("main_generate", {"status": "completed", "metadata": {}})

    assert store.mark_running_interrupted() == []
    assert store.load("main_generate")["status"] == "completed"


def test_clear_removes_persisted_task(tmp_path):
    store = TaskStateStore(tmp_path)
    store.save("main_generate", {"status": "interrupted"})
    store.clear("main_generate")
    assert store.load("main_generate") is None


def test_generation_checkpoint_skips_only_existing_completed_files(tmp_path):
    first = tmp_path / "first.html"
    first.write_text("done", encoding="utf-8")
    missing = tmp_path / "missing.html"

    checkpoint = with_topics({}, ["话题一", "话题二", "话题三"])
    checkpoint = mark_completed(checkpoint, 0, "话题一", str(first))
    checkpoint = mark_completed(checkpoint, 1, "话题二", str(missing))

    completed = valid_completed(checkpoint)
    assert [item["index"] for item in completed] == [0]
    assert completed[0]["topic"] == "话题一"


def test_changing_topic_plan_invalidates_old_completion_checkpoint(tmp_path):
    article = tmp_path / "article.html"
    article.write_text("done", encoding="utf-8")
    checkpoint = with_topics({}, ["旧话题"])
    checkpoint = mark_completed(checkpoint, 0, "旧话题", str(article))

    changed = with_topics(checkpoint, ["新话题"])
    assert changed["completed"] == []


def test_duplicate_topics_are_tracked_by_index(tmp_path):
    first = tmp_path / "first.html"
    second = tmp_path / "second.html"
    first.write_text("one", encoding="utf-8")
    second.write_text("two", encoding="utf-8")
    checkpoint = with_topics({}, ["同一话题", "同一话题"])
    checkpoint = mark_completed(checkpoint, 0, "同一话题", str(first))
    checkpoint = mark_completed(checkpoint, 1, "同一话题", str(second))

    assert [item["index"] for item in valid_completed(checkpoint)] == [0, 1]


def test_recovery_endpoint_passes_checkpoint_into_new_generation(tmp_path, monkeypatch):
    from src.ai_write_x.web.api import generate as generate_api

    article = tmp_path / "done.html"
    article.write_text("done", encoding="utf-8")
    checkpoint = with_topics({}, ["已完成话题", "剩余话题"])
    checkpoint = mark_completed(checkpoint, 0, "已完成话题", str(article))

    previous_store = generate_api.task_manager.state_store
    store = TaskStateStore(tmp_path / "state")
    generate_api.task_manager.state_store = store
    store.save(
        "main_generate",
        {
            "status": "interrupted",
            "metadata": {
                "request": {"topic": "系列主题", "article_count": 2},
                "checkpoint": checkpoint,
            },
        },
    )
    captured = {}

    async def fake_generate(request):
        captured["checkpoint"] = request.resume_checkpoint
        return {"status": "success"}

    monkeypatch.setattr(generate_api, "generate_content", fake_generate)
    try:
        result = asyncio.run(
            generate_api.restart_interrupted_generation(
                generate_api.RecoverGenerateRequest(confirm=True)
            )
        )
    finally:
        generate_api.task_manager.state_store = previous_store

    assert result == {"status": "success"}
    assert captured["checkpoint"]["topics"] == ["已完成话题", "剩余话题"]
    assert captured["checkpoint"]["completed"][0]["index"] == 0


def test_failed_validation_does_not_delete_recovery_checkpoint(tmp_path, monkeypatch):
    from src.ai_write_x.web.api import generate as generate_api

    previous_store = generate_api.task_manager.state_store
    store = TaskStateStore(tmp_path / "state")
    generate_api.task_manager.state_store = store
    store.save(
        "main_generate",
        {
            "status": "interrupted",
            "metadata": {"request": {"topic": "仍需恢复"}},
        },
    )

    class InvalidConfig:
        error_message = "API KEY 缺失"

        @staticmethod
        def validate_config():
            return False

    monkeypatch.setattr(generate_api.Config, "get_instance", lambda: InvalidConfig())
    try:
        with pytest.raises(HTTPException):
            asyncio.run(generate_api.generate_content(generate_api.GenerateRequest(topic="测试")))
        assert store.load("main_generate")["status"] == "interrupted"
    finally:
        generate_api.task_manager.state_store = previous_store
