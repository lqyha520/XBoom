# -*- coding: utf-8 -*-
"""Run the full local release readiness gate without publishing anything."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_command(command: list[str]) -> bool:
    print(f"\n$ {' '.join(command)}")
    result = subprocess.run(command, cwd=ROOT)
    return result.returncode == 0


def main() -> int:
    commands = [
        [sys.executable, "scripts/preflight_check.py", "--release"],
        [sys.executable, "scripts/release_check.py"],
        [sys.executable, "scripts/audit_text_encoding.py", "README.md", "docs", "--fail"],
        [sys.executable, "scripts/run_quick_tests.py", "--skip-smoke"],
    ]

    for command in commands:
        if not run_command(command):
            print("\nRelease gate failed.")
            return 1

    print("\nRelease gate passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
