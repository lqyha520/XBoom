# -*- coding: utf-8 -*-
"""Clean local generated files without touching source or user data by default."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _is_inside_root(path: Path) -> bool:
    try:
        path.resolve().relative_to(ROOT.resolve())
        return True
    except ValueError:
        return False


def _add_existing(targets: set[Path], path: Path) -> None:
    if path.exists() and _is_inside_root(path):
        targets.add(path)


def collect_targets(include_build: bool = False) -> list[Path]:
    targets: set[Path] = set()

    for relative in [".pytest_cache", "htmlcov", ".dbg"]:
        _add_existing(targets, ROOT / relative)

    if include_build:
        for relative in ["build", "dist"]:
            _add_existing(targets, ROOT / relative)

    for directory in ROOT.rglob("__pycache__"):
        if ".git" not in directory.parts:
            _add_existing(targets, directory)

    for pyc_file in ROOT.rglob("*.pyc"):
        if ".git" not in pyc_file.parts:
            _add_existing(targets, pyc_file)

    return sorted(targets, key=lambda item: str(item).lower())


def clean_targets(targets: list[Path], dry_run: bool = True) -> None:
    if not targets:
        print("No generated workspace files found.")
        return

    action = "Would remove" if dry_run else "Removing"
    for target in targets:
        relative = target.relative_to(ROOT)
        print(f"{action}: {relative}")
        if dry_run:
            continue
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Clean generated local workspace files.")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually remove files. Without this flag the command is a dry run.",
    )
    parser.add_argument(
        "--include-build",
        action="store_true",
        help="Also include build/ and dist/ artifacts.",
    )
    args = parser.parse_args(argv)

    targets = collect_targets(include_build=args.include_build)
    clean_targets(targets, dry_run=not args.apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
