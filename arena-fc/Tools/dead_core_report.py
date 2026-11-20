#!/usr/bin/env python3
"""Arena FC - report core types that nothing in the game can reach.

The 2026 review found ~1,500 lines of fully implemented "Phase N" systems in
Scripts/Core (career mode, matchmaking, referees/VAR, fluid formations, crowd
density, ambient behaviour, match analysis, ...) that nothing ever instantiated:
they looked like shipped features in the docs and in code review, but had no
effect on the game.

This is a reachability check, not a keyword count.  Roots are every type the
game itself mentions (Godot scripts, tests, tools, server).  From there the
reference graph is followed *through the core*, so a career type reached from a
career screen keeps its own fixtures, table rows and transfer offers alive.  A
type that no root can reach - directly or transitively - is dead.

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
from collections import defaultdict, deque

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


def ident_re(name: str) -> re.Pattern[str]:
    # Word-boundary match so "Tactics" does not match "TacticsPressMult".
    return re.compile(rf"(?<![A-Za-z0-9_]){re.escape(name)}(?![A-Za-z0-9_])")


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


def split_types(source: str) -> list[tuple[str, str]]:
    """Return (type name, source block) pairs.  Blocks run to the next top-level
    declaration, which is enough for the flat namespace the core uses."""
    matches = list(TYPE_RE.finditer(source))
    blocks: list[tuple[str, str]] = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(source)
        blocks.append((m.group(1), source[m.start():end]))
    return blocks


def main() -> int:
    ci = "--ci" in sys.argv
    strict = "--strict" in sys.argv

    files = sorted(CORE.rglob("*.cs"))
    declared: dict[str, pathlib.Path] = {}
    blocks: list[tuple[str, str, pathlib.Path]] = []
    for path in files:
        source = path.read_text(encoding="utf-8", errors="ignore")
        for name, block in split_types(source):
            declared.setdefault(name, path)
            blocks.append((name, block, path))

    all_names = set(declared)
    # Graph: type -> types it mentions.
    edges: dict[str, set[str]] = defaultdict(set)
    for name, block, _ in blocks:
        for other in all_names:
            if other == name:
                continue
            if ident_re(other).search(block):
                edges[name].add(other)

    # Roots: anything the game outside the core mentions.
    consumer_chunks: list[str] = []
    for pattern in CONSUMER_GLOBS:
        for path in ROOT.glob(pattern):
            if CORE in path.parents:
                continue
            try:
                consumer_chunks.append(path.read_text(encoding="utf-8", errors="ignore"))
            except OSError:
                continue
    consumer_text = "\n".join(consumer_chunks)
    roots = {name for name in all_names if ident_re(name).search(consumer_text)}

    reached = set(roots)
    queue = deque(roots)
    while queue:
        current = queue.popleft()
        for nxt in edges.get(current, ()):
            if nxt not in reached:
                reached.add(nxt)
                queue.append(nxt)

    dead = sorted(
        ((name, declared[name]) for name in all_names - reached),
        key=lambda pair: (pair[1].as_posix(), pair[0]),
    )

    rel = lambda p: p.relative_to(ROOT).as_posix()
    if ci:
        for name, path in dead:
            print(f"::warning file={rel(path)}::{name} is unreachable from the game")
    else:
        print(f"Arena FC core: {len(all_names)} public types, "
              f"{len(dead)} unreachable from the game\n")
        by_file: dict[str, list[str]] = {}
        for name, path in dead:
            by_file.setdefault(rel(path), []).append(name)
        for file_name, names in by_file.items():
            print(f"  {file_name}")
            for name in names:
                print(f"      {name}")
    return 1 if (strict and dead) else 0


if __name__ == "__main__":
    raise SystemExit(main())
