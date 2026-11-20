#!/usr/bin/env python3
"""Arena FC - report pure-C# core types that no other file references.

The 2026 review found ~1,500 lines of fully implemented "Phase N" systems in
Scripts/Core (career mode, matchmaking, referees/VAR, fluid formations, crowd
density, ambient behaviour, match analysis, ...) that nothing ever instantiated:
they looked like shipped features in the docs and in code review, but had no
effect on the game.  This report makes that visible on every CI run.

Usage:
    python3 Tools/dead_core_report.py            # human-readable report
    python3 Tools/dead_core_report.py --ci       # GitHub annotations
    python3 Tools/dead_core_report.py --strict   # exit 1 when anything is dead

Exit status is 0 unless --strict is given.
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
CORE = ROOT / "Scripts" / "Core"
# Godot, tools, tests and the server are all consumers of the core.
CONSUMER_GLOBS = ("Scripts/**/*.cs", "Scripts/**/*.gd", "Web/**/*.gd", "Tests/**/*.cs",
                  "Tests/**/*.gd", "Server/**/*.cs", "Tools/**/*.py")

TYPE_RE = re.compile(
    r"^\s*(?:public|internal)\s+(?:sealed\s+|static\s+|abstract\s+|partial\s+|readonly\s+)*"
    r"(?:class|struct|enum|interface|record)\s+([A-Za-z_][A-Za-z0-9_]*)",
    re.MULTILINE,
)


def core_files() -> list[pathlib.Path]:
    return sorted(CORE.rglob("*.cs"))


def consumer_text(exclude: pathlib.Path) -> str:
    chunks: list[str] = []
    for pattern in CONSUMER_GLOBS:
        for path in ROOT.glob(pattern):
            if path == exclude:
                continue
            try:
                chunks.append(path.read_text(encoding="utf-8", errors="ignore"))
            except OSError:
                continue
    return "\n".join(chunks)


def main() -> int:
    ci = "--ci" in sys.argv
    strict = "--strict" in sys.argv
    dead: list[tuple[str, pathlib.Path]] = []
    total = 0

    for path in core_files():
        source = path.read_text(encoding="utf-8", errors="ignore")
        types = TYPE_RE.findall(source)
        if not types:
            continue
        others = consumer_text(path)
        for name in types:
            total += 1
            # Word-boundary match so "Tactics" does not match "TacticsPressMult".
            if re.search(rf"(?<![A-Za-z0-9_]){re.escape(name)}(?![A-Za-z0-9_])", others):
                continue
            dead.append((name, path))

    rel = lambda p: p.relative_to(ROOT).as_posix()
    if ci:
        for name, path in dead:
            print(f"::warning file={rel(path)}::{name} is never referenced outside its own file")
    else:
        print(f"Arena FC core: {total} public types, {len(dead)} unreferenced\n")
        by_file: dict[str, list[str]] = {}
        for name, path in dead:
            by_file.setdefault(rel(path), []).append(name)
        for file in sorted(by_file):
            print(f"  {file}")
            for name in sorted(by_file[file]):
                print(f"      {name}")
        if not dead:
            print("  (nothing dead - nice)")
    return 1 if (strict and dead) else 0


if __name__ == "__main__":
    raise SystemExit(main())
