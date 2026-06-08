# -*- coding: utf-8 -*-
"""API regression tests for scheduler cancellation boundaries."""

from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient


def _client_with_registered_token(client: TestClient, token: str = "scheduler-token") -> dict[str, str]:
    client.get("/", params={"token": token})
    return {"X-App-Client-Token": token}


def test_scheduler_cancel_endpoint_delegates_to_scheduler_service(monkeypatch):
    from src.ai_write_x.web.app import allowed_tokens, app
    from src.ai_write_x.web.api import scheduler as scheduler_api

    calls = []

    def fake_request_cancel(task_id):
        calls.append(task_id)
        return True, "Cancel requested"

    monkeypatch.setattr(scheduler_api.scheduler_service, "request_cancel", fake_request_cancel)

    allowed_tokens.clear()
    with TestClient(app) as client:
        headers = _client_with_registered_token(client)
        response = client.post("/api/scheduler/tasks/task-123/cancel", headers=headers)

    assert response.status_code == 200
    assert response.json() == {"status": "success", "message": "Cancel requested"}
    assert calls == ["task-123"]


def test_scheduler_cancel_endpoint_returns_404_for_missing_task(monkeypatch):
    from src.ai_write_x.web.app import allowed_tokens, app
    from src.ai_write_x.web.api import scheduler as scheduler_api

    monkeypatch.setattr(
        scheduler_api.scheduler_service,
        "request_cancel",
        lambda task_id: (False, "Task not found"),
    )

    allowed_tokens.clear()
    with TestClient(app) as client:
        headers = _client_with_registered_token(client)
        response = client.post("/api/scheduler/tasks/missing/cancel", headers=headers)

    assert response.status_code == 404


def test_scheduler_rejects_delete_and_status_change_for_running_task(monkeypatch):
    from src.ai_write_x.web.app import allowed_tokens, app
    from src.ai_write_x.web.api import scheduler as scheduler_api
    from src.ai_write_x.database import models

    running_task = SimpleNamespace(status="running")
    monkeypatch.setattr(models.ScheduledTask, "get_by_id", staticmethod(lambda task_id: running_task))
    monkeypatch.setattr(scheduler_api.db_manager, "delete_task", lambda task_id: True)

    allowed_tokens.clear()
    with TestClient(app) as client:
        headers = _client_with_registered_token(client)
        delete_response = client.delete("/api/scheduler/tasks/task-123", headers=headers)
        update_response = client.put(
            "/api/scheduler/tasks/task-123",
            headers=headers,
            json={"status": "disabled"},
        )

    assert delete_response.status_code == 409
    assert update_response.status_code == 409
