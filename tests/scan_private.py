"""Scan a folder for private information before publishing (paths, user names, keys, e-mail addresses).

The local user name is taken from the environment at run time, so it never appears in this file.
Usage: python scan_private.py <folder>
"""
import getpass
import os
import pathlib
import re
import sys

PATTERNS = {
    "desktop path": r"[/\\]Desktop[/\\]",
    "key file": r"api keys\.txt",
    "API key": r"sk-[A-Za-z0-9_\-]{10,}",
    "e-mail": r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.(?:com|kr|net|org)",
    "network drive": r"\bZ:[/\\]",
    "user folder": r"C:[/\\]Users[/\\]",
}
user = os.environ.get("USERNAME") or os.environ.get("USER") or getpass.getuser()
if user:
    PATTERNS["user name"] = re.escape(user)
me = pathlib.Path(__file__).resolve()
hits = []
for p in pathlib.Path(sys.argv[1]).rglob("*"):
    if p.is_file() and p.resolve() != me and p.name != me.name:
        t = p.read_text(encoding="utf-8", errors="ignore")
        for name, pat in PATTERNS.items():
            for m in re.finditer(pat, t, re.I):
                hits.append((str(p), name, t[max(0, m.start() - 30):m.end() + 30].replace("\n", " ")))
for h in hits:
    print(h)
print(f"{len(hits)} hits")
sys.exit(1 if hits else 0)
