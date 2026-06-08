# -*- coding: utf-8 -*-
"""Report likely mojibake in user-facing text files.

This is intentionally advisory by default. Use ``--fail`` when you want CI or a
release gate to fail on suspicious text.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DEFAULT_PATHS = [
    "README.md",
    "docs",
    "src/ai_write_x/web",
    "src/ai_write_x/core",
    "src/ai_write_x/config",
]

TEXT_SUFFIXES = {".md", ".py", ".html", ".js", ".css", ".yaml", ".yml", ".json", ".toml"}
SKIP_PARTS = {
    ".git",
    ".pytest_cache",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    ".local_secrets",
}
MOJIBAKE_MARKERS = (
    "锛",
    "鍚",
    "鑾",
    "鐢",
    "瀹",
    "绋",
    "鈥",
    "馃",
    "鏂",
    "涓",
)


@dataclass(frozen=True)
class Finding:
    path: Path
    line_number: int
    marker: str
    line: str


def _iter_files(paths: list[str]) -> list[Path]:
    files: list[Path] = []
    for item in paths:
        path = ROOT / item
        if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES:
            files.append(path)
        elif path.is_dir():
            for child in path.rglob("*"):
                if not child.is_file() or child.suffix.lower() not in TEXT_SUFFIXES:
                    continue
                if any(part in SKIP_PARTS for part in child.relative_to(ROOT).parts):
                    continue
                files.append(child)
    return sorted(set(files))


def scan_file(path: Path) -> list[Finding]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        return [Finding(path, 0, "decode-error", "not valid utf-8")]

    findings: list[Finding] = []
    for line_number, line in enumerate(lines, start=1):
        for marker in MOJIBAKE_MARKERS:
            if marker in line:
                findings.append(Finding(path, line_number, marker, line.strip()[:160]))
                break
    return findings


def scan_paths(paths: list[str]) -> list[Finding]:
    findings: list[Finding] = []
    for path in _iter_files(paths):
        findings.extend(scan_file(path))
    return findings


def _safe_print(text: str) -> None:
    encoding = sys.stdout.encoding or "utf-8"
    safe = text.encode(encoding, errors="replace").decode(encoding, errors="replace")
    print(safe)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report likely mojibake in text files.")
    parser.add_argument("paths", nargs="*", default=DEFAULT_PATHS)
    parser.add_argument("--fail", action="store_true", help="Return a non-zero exit code when findings exist.")
    parser.add_argument("--limit", type=int, default=80, help="Maximum findings to print.")
    args = parser.parse_args(argv)

    findings = scan_paths(args.paths)
    for finding in findings[: args.limit]:
        relative = finding.path.relative_to(ROOT)
        _safe_print(f"{relative}:{finding.line_number}: marker={finding.marker} {finding.line}")

    if len(findings) > args.limit:
        _safe_print(f"... {len(findings) - args.limit} more findings")

    _safe_print(f"Encoding audit findings: {len(findings)}")
    return 1 if args.fail and findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
