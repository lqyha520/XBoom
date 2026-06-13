# -*- coding: utf-8 -*-
"""Normalize the PyInstaller onedir output name.

On some Windows consoles the onedir folder/exe can be created with a
mojibake (GBK-misdecoded) name instead of the expected UTF-8 name. This
script detects that case and renames the directory and inner executable
to the canonical name so downstream bundle checks succeed.

The canonical name is read directly from aiwritex_windows.spec (the
COLLECT/EXE name) so this helper never hard-codes the app name and can
never drift from the spec.

Exit code is 0 on success or no-op.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
SPEC = ROOT / "aiwritex_windows.spec"


def _canonical_name() -> str:
    text = SPEC.read_text(encoding="utf-8")
    names = re.findall(r"name='([^']+)'", text)
    if not names:
        raise SystemExit("[normalize] could not read app name from spec")
    # COLLECT name is the last name='...' in the spec.
    return names[-1]


def main() -> int:
    if not DIST.is_dir():
        print("[normalize] dist/ not found; nothing to do")
        return 0

    expected = _canonical_name()
    expected_dir = DIST / expected

    if expected_dir.is_dir():
        _fix_exe(expected_dir, expected)
        print("[normalize] dist output already canonical: %s" % expected)
        return 0

    subdirs = [p for p in DIST.iterdir() if p.is_dir() and p.name != "installer"]
    candidates = [p for p in subdirs if any(p.glob("*.exe"))]

    if not candidates:
        print("[normalize] no onedir candidate found under dist/")
        return 0

    if len(candidates) == 1:
        src = candidates[0]
        src.rename(expected_dir)
        print("[normalize] renamed onedir %r -> %r" % (src.name, expected))
        _fix_exe(expected_dir, expected)
        return 0

    print("[normalize] ambiguous onedir candidates: %s"
          % ", ".join(repr(p.name) for p in candidates))
    return 0


def _fix_exe(folder: Path, expected: str) -> None:
    expected_exe = folder / (expected + ".exe")
    if expected_exe.exists():
        return
    exes = list(folder.glob("*.exe"))
    if len(exes) == 1:
        exes[0].rename(expected_exe)
        print("[normalize] renamed exe %r -> %r" % (exes[0].name, expected + ".exe"))


if __name__ == "__main__":
    sys.exit(main())
