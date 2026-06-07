# -*- coding: utf-8 -*-
"""Regression tests for local quality gate wiring."""

from __future__ import annotations

from pathlib import Path


def test_quick_gate_includes_security_regressions():
    from scripts import run_quick_tests

    assert "tests/test_web_security.py" in run_quick_tests.CORE_TESTS


def test_clean_workspace_defaults_to_dry_run():
    source = Path("scripts/clean_workspace.py")

    assert source.exists()
    text = source.read_text(encoding="utf-8")
    assert "--apply" in text
    assert "dry_run" in text
