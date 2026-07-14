from datetime import datetime
from types import SimpleNamespace

from src.ai_write_x.core.scheduler import SchedulerService


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
