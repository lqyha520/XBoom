# -*- coding: utf-8 -*-
"""Run the fast local quality gate for XBoom development."""

from __future__ import annotations

import argparse
import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE_TESTS = [
    "tests/test_quality_gate.py",
    "tests/test_scheduler_api.py",
    "tests/test_core_basic.py",
    "tests/test_database.py",
    "tests/test_runtime_paths.py",
    "tests/test_web_security.py",
]


def run_command(command: list[str]) -> bool:
    print(f"\n$ {' '.join(command)}")
    result = subprocess.run(command, cwd=ROOT)
    return result.returncode == 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run XBoom quick checks and core tests.")
    parser.add_argument(
        "--release",
        action="store_true",
        help="Use release preflight rules before running smoke/core tests.",
    )
    parser.add_argument(
        "--skip-smoke",
        action="store_true",
        help="Skip the startup smoke check.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="Per-test timeout in seconds when pytest-timeout is installed.",
    )
    args = parser.parse_args(argv)

    preflight = [sys.executable, "scripts/preflight_check.py"]
    if args.release:
        preflight.append("--release")

    commands = [preflight]
    if args.release:
        commands.append([sys.executable, "scripts/release_check.py"])
    if not args.skip_smoke:
        commands.append([sys.executable, "scripts/startup_smoke_check.py"])
    pytest_command = [
        sys.executable,
        "-m",
        "pytest",
        *CORE_TESTS,
        "--tb=short",
        "-q",
        "--no-cov",
    ]
    if importlib.util.find_spec("pytest_timeout") is not None:
        pytest_command.extend(["--timeout", str(args.timeout)])
    commands.append(pytest_command)

    for command in commands:
        if not run_command(command):
            print("\nQuick test gate failed.")
            return 1

    print("\nQuick test gate passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
