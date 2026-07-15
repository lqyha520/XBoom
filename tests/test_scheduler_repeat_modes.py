from datetime import datetime
from types import SimpleNamespace

from src.ai_write_x.core.scheduler import SchedulerService
from src.ai_write_x.core import task_status


def test_daily_repeat_keeps_the_original_clock_time():
    planned = datetime(2026, 7, 14, 9, 0, 0)
    finished = datetime(2026, 7, 14, 9, 30, 0)

    assert SchedulerService._next_daily_execution(planned, finished) == datetime(2026, 7, 15, 9, 0, 0)


def test_daily_repeat_uses_today_when_the_fixed_time_is_still_ahead():
    planned = datetime(2026, 7, 13, 9, 0, 0)
    now = datetime(2026, 7, 14, 8, 30, 0)

    assert SchedulerService._next_daily_execution(planned, now) == datetime(2026, 7, 14, 9, 0, 0)


def test_repeat_mode_preserves_legacy_task_behavior():
    assert SchedulerService._repeat_mode(SimpleNamespace(is_recurring=False, repeat_mode="daily")) == "once"
    assert SchedulerService._repeat_mode(SimpleNamespace(is_recurring=True, repeat_mode="daily")) == "daily"
    assert SchedulerService._repeat_mode(SimpleNamespace(is_recurring=True, repeat_mode="unknown")) == "interval"


def test_preflight_disabled_recurring_task_is_not_reenabled(monkeypatch):
    planned = datetime(2026, 7, 16, 9, 0, 0)
    task = SimpleNamespace(
        status=task_status.DISABLED,
        last_run_at=None,
        updated_at=None,
        execution_time=planned,
        is_recurring=True,
        repeat_mode="daily",
        interval_hours=24,
        saved=0,
    )
    task.save = lambda: setattr(task, "saved", task.saved + 1)
    from src.ai_write_x.database.models import ScheduledTask
    monkeypatch.setattr(ScheduledTask, "get_by_id", staticmethod(lambda _task_id: task))

    SchedulerService()._finalize_task("00000000-0000-0000-0000-000000000001", task_status.DISABLED)

    assert task.status == task_status.DISABLED
    assert task.execution_time == planned
    assert task.saved == 1
