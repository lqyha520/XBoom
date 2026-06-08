"""Shared task status constants for web-facing background work."""

IDLE = "idle"
RUNNING = "running"
COMPLETED = "completed"
FAILED = "failed"
STOPPED = "stopped"
CANCEL_REQUESTED = "cancel_requested"
CANCELLED = "cancelled"
ENABLED = "enabled"
DISABLED = "disabled"

TERMINAL_STATUSES = {COMPLETED, FAILED, STOPPED, CANCELLED}
ACTIVE_STATUSES = {RUNNING, CANCEL_REQUESTED}
SCHEDULER_VISIBLE_STATUSES = {
    ENABLED,
    DISABLED,
    RUNNING,
    CANCEL_REQUESTED,
    CANCELLED,
    COMPLETED,
    FAILED,
}
