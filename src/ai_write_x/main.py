# -*- coding: utf-8 -*-
"""Package entry points for AIWriteX/XBoom.

The desktop launcher historically lives at the repository root in ``main.py``.
This module keeps installed console scripts working without duplicating that
startup logic.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import Callable


class EntryPointError(RuntimeError):
    """Raised when a console entry point cannot be resolved."""


def _repo_root_main() -> Callable[[], None]:
    root_main = Path(__file__).resolve().parents[2] / "main.py"
    if not root_main.exists():
        raise EntryPointError(f"Cannot find root launcher: {root_main}")

    spec = importlib.util.spec_from_file_location("ai_write_x_root_main", root_main)
    if spec is None or spec.loader is None:
        raise EntryPointError(f"Cannot load root launcher: {root_main}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    runner = getattr(module, "run", None)
    if not callable(runner):
        raise EntryPointError("Root launcher does not expose run().")
    return runner


def run() -> None:
    """Start the desktop application."""
    _repo_root_main()()


def train() -> None:
    raise EntryPointError("The train console command is not implemented for this app.")


def replay() -> None:
    raise EntryPointError("The replay console command is not implemented for this app.")


def test() -> None:
    root = Path(__file__).resolve().parents[2]
    subprocess.run([sys.executable, "scripts/run_quick_tests.py"], cwd=root, check=True)
