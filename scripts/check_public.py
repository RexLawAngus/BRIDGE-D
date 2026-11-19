"""Fail if any private term leaks outside private/.

Terms come from private/forbidden.txt (one per line). The public repo has no
private/ directory, so this script is a no-op there.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / "private"
TERMS_FILE = PRIVATE / "forbidden.txt"

SKIP_DIRS = {".git", "__pycache__", "build", "dist", ".venv", "vendor"}
SKIP_SUFFIXES = {".pyc", ".png", ".jpg", ".jpeg", ".gif", ".pdf", ".zip"}


def main() -> int:
    if not TERMS_FILE.exists():
        print("no private/forbidden.txt; nothing to check")
        return 0
    terms = [
        line.strip()
        for line in TERMS_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    if not terms:
        print("no terms; nothing to check")
        return 0

    hits: list[tuple[Path, str]] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() in SKIP_SUFFIXES:
            continue
        if PRIVATE in path.parents:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for term in terms:
            if term in text:
                hits.append((path.relative_to(ROOT), term))

    if hits:
        print("private terms found outside private/:")
        for path, term in hits:
            print(f"  {path}: {term!r}")
        return 1
    print(f"ok: {len(terms)} terms checked, no leaks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
