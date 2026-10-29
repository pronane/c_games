"""Regenerate HELP.md from sforge/helptext.py (the same text the Help tab and `forge.py help` show)."""
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, ROOT)
from sforge import helptext
open(os.path.join(ROOT, "HELP.md"), "w", encoding="utf-8").write(helptext.markdown())
print("wrote HELP.md")
