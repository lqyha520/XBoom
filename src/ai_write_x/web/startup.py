"""Startup profile policy for optional background services."""

from __future__ import annotations

import os


STARTUP_PROFILE_ENV = "AIWRITEX_STARTUP_PROFILE"
SKIP_STARTUP_ENV = "AIWRITEX_SKIP_STARTUP_TASKS"
DEFAULT_STARTUP_PROFILE = "lean"

STARTUP_GROUPS = {
    "network": {"usage_stats", "menu_ip_access", "newshub"},
    "heavy": {
        "global_tools",
        "scavenger",
        "semantic_cache",
        "dashboard_render",
        "newshub",
    },
    "background": {
        "global_tools",
        "scavenger",
        "scheduler",
        "usage_stats",
        "menu_ip_access",
        "periodic_cleanup",
        "batch_processor",
        "semantic_cache",
        "websocket_manager",
        "dashboard_render",
        "newshub",
    },
}

PROFILE_SKIPPED_TASKS = {
    "full": frozenset(),
    "lean": frozenset(
        {
            "global_tools",
            "scavenger",
            "periodic_cleanup",
            "batch_processor",
            "semantic_cache",
            "websocket_manager",
            "dashboard_render",
            "newshub",
        }
    ),
    "minimal": frozenset(STARTUP_GROUPS["background"]),
}


def get_startup_profile(value: str | None = None) -> str:
    """Return a supported profile name, falling back to the lean default."""
    raw = value if value is not None else os.environ.get(STARTUP_PROFILE_ENV, "")
    profile = str(raw or DEFAULT_STARTUP_PROFILE).strip().lower()
    return profile if profile in PROFILE_SKIPPED_TASKS else DEFAULT_STARTUP_PROFILE


def should_skip_startup_task(
    name: str,
    *,
    profile: str | None = None,
    explicit_skip: str | None = None,
) -> bool:
    """Apply profile defaults and the existing explicit skip override."""
    task_name = name.strip().lower()
    selected_profile = get_startup_profile(profile)
    if task_name in PROFILE_SKIPPED_TASKS[selected_profile]:
        return True

    raw = explicit_skip
    if raw is None:
        raw = os.environ.get(SKIP_STARTUP_ENV, "")
    skipped = {item.strip().lower() for item in str(raw or "").split(",") if item.strip()}
    if "all" in skipped or task_name in skipped:
        return True
    return any(task_name in STARTUP_GROUPS.get(group, set()) for group in skipped)
