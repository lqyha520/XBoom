# -*- coding: utf-8 -*-
"""Small helpers for local operations scripts.

Operations scripts are often copied into ad-hoc maintenance flows. Keeping
secret lookup here makes the "no hardcoded credentials" rule easy to follow.
"""

from __future__ import annotations

import os


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"Missing {name}")
    return value


def env_or_default(name: str, default: str) -> str:
    value = os.environ.get(name, "").strip()
    return value or default
