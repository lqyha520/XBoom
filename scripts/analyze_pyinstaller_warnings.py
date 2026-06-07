# -*- coding: utf-8 -*-
"""Summarize and gate PyInstaller missing-module warnings for XBoom."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WARN_FILE = ROOT / "build" / "aiwritex_windows" / "warn-aiwritex_windows.txt"

WARNING_RE = re.compile(r"^(?P<kind>missing|excluded) module named (?P<module>.+?) - imported by (?P<importers>.+)$")

# Platform, Python 2 compatibility, REPL, notebook, test, and optional scientific
# modules that routinely appear in PyInstaller warnings on Windows builds.
IGNORED_EXACT = {
    "_dummy_thread",
    "_frozen_importlib_external",
    "_manylinux",
    "_posixshmem",
    "_posixsubprocess",
    "_scproxy",
    "_typeshed",
    "_winreg",
    "black",
    "fcntl",
    "grp",
    "java",
    "jupyter_ai",
    "jupyter_ai_magics",
    "multiprocessing.AuthenticationError",
    "multiprocessing.BufferTooShort",
    "multiprocessing.TimeoutError",
    "multiprocessing.get_context",
    "multiprocessing.get_start_method",
    "multiprocessing.set_start_method",
    "numpy.random.RandomState",
    "numpy_distutils",
    "posix",
    "pwd",
    "pyimod02_importers",
    "pyodide_js",
    "readline",
    "resource",
    "setuptools._vendor.backports.zstd",
    "sitecustomize",
    "termios",
    "trove_classifiers",
    "unicodedata2",
    "urllib.quote",
    "urllib.unquote",
    "urllib.urlencode",
    "urllib.urlopen",
    "usercustomize",
    "vms_lib",
    "yapf",
}
IGNORED_PREFIXES = (
    "Cython.",
    "java.",
    "numpy._core.",
    "numpy_distutils.",
    "prompt_toolkit.filters.",
    "pygments.lexers.",
    "yapf.",
)

# These look like modules to PyInstaller but are pydantic public attributes used
# by type-heavy libraries. They are not actual modules that should be bundled.
ATTRIBUTE_LIKE_MODULES = {
    "pydantic.BaseModel",
}

# If these are absent, advertised application features are silently degraded in
# the packaged app. Keep this list intentionally short and feature-oriented.
REQUIRED_FEATURE_MODULES = {
    "feedparser": "NewsHub RSS parsing",
    "asyncpg": "scraper PostgreSQL storage",
}

OPTIONAL_FEATURE_MODULES = {
    "email_validator": "optional pydantic e-mail field validation",
    "uvloop": "optional Unix event loop acceleration",
}


@dataclass(frozen=True)
class WarningEntry:
    kind: str
    module: str
    importers: str


def _print(message: str) -> None:
    safe = message.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(
        sys.stdout.encoding or "utf-8"
    )
    print(safe)


def normalize_module(raw: str) -> str:
    return raw.strip().strip("'\"")


def parse_warning_file(path: Path) -> list[WarningEntry]:
    entries: list[WarningEntry] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = WARNING_RE.match(line.strip())
        if not match:
            continue
        entries.append(
            WarningEntry(
                kind=match.group("kind"),
                module=normalize_module(match.group("module")),
                importers=match.group("importers"),
            )
        )
    return entries


def is_ignored(module: str) -> bool:
    return (
        module in IGNORED_EXACT
        or module in ATTRIBUTE_LIKE_MODULES
        or any(module.startswith(prefix) for prefix in IGNORED_PREFIXES)
    )


def analyze(entries: list[WarningEntry]) -> tuple[list[WarningEntry], list[WarningEntry], list[WarningEntry]]:
    required: list[WarningEntry] = []
    optional: list[WarningEntry] = []
    review: list[WarningEntry] = []

    seen: set[tuple[str, str]] = set()
    for entry in entries:
        key = (entry.kind, entry.module)
        if key in seen:
            continue
        seen.add(key)

        if entry.kind == "excluded" or is_ignored(entry.module):
            continue
        if entry.module in REQUIRED_FEATURE_MODULES:
            required.append(entry)
        elif entry.module in OPTIONAL_FEATURE_MODULES:
            optional.append(entry)
        else:
            review.append(entry)
    return required, optional, review


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Analyze PyInstaller warning output.")
    parser.add_argument("warn_file", nargs="?", type=Path, default=DEFAULT_WARN_FILE)
    parser.add_argument(
        "--fail-on-review",
        action="store_true",
        help="Also fail on warnings that are not classified as required or ignored.",
    )
    args = parser.parse_args(argv)

    warn_file = args.warn_file.resolve()
    if not warn_file.exists():
        _print(f"[FAIL] PyInstaller warning file not found: {warn_file}")
        return 1

    entries = parse_warning_file(warn_file)
    required, optional, review = analyze(entries)

    _print(f"[OK] Parsed {len(entries)} PyInstaller warning entries from {warn_file.name}")

    if optional:
        _print("[WARN] Optional feature modules are missing:")
        for entry in optional:
            _print(f"  - {entry.module}: {OPTIONAL_FEATURE_MODULES[entry.module]}")

    if review:
        _print("[WARN] Unclassified missing modules remain for review:")
        for entry in review[:25]:
            _print(f"  - {entry.module}")
        if len(review) > 25:
            _print(f"  ... and {len(review) - 25} more")

    if required:
        _print("[FAIL] Required packaged feature modules are missing:")
        for entry in required:
            _print(f"  - {entry.module}: {REQUIRED_FEATURE_MODULES[entry.module]}")
        return 1

    if args.fail_on_review and review:
        _print("[FAIL] Unclassified PyInstaller warnings must be triaged before release.")
        return 1

    _print("PyInstaller warning analysis passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
