#!/usr/bin/env python3
"""Pre-download the Godot/.NET toolchain so builds can run offline afterwards.

Called by Tools/build.py automatically, but handy to run once in the background:
    python3 Tools/bootstrap_toolchain.py
"""
import importlib.util
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location("afcbuild", Path(__file__).with_name("build.py"))
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)

print("BOOTSTRAP: .NET 9 SDK", flush=True)
print("  ->", b.ensure_dotnet(), flush=True)
print("BOOTSTRAP: Godot mono editor", flush=True)
print("  ->", b.ensure_editor(True, None), flush=True)
print("BOOTSTRAP: Godot standard editor", flush=True)
print("  ->", b.ensure_editor(False, None), flush=True)
print("BOOTSTRAP: mono export templates", flush=True)
print("  ->", b.ensure_templates(True), flush=True)
print("BOOTSTRAP: standard export templates", flush=True)
print("  ->", b.ensure_templates(False), flush=True)
print("BOOTSTRAP_DONE", flush=True)
