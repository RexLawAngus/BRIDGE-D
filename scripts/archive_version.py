"""Archive the committed source of the current version.

Usage:
    python scripts/archive_version.py
    python scripts/archive_version.py --base /path/to/archive --date 20261119

Reads the version from pyproject.toml, runs the public-leak guard, and exports
`git archive HEAD` into <base>/v<version>-<date>. The archive contains only
committed files, so private/ and generated artifacts never enter it.

Archive base resolution order:
    1. --base
    2. BRIDGE_D_ARCHIVE_DIR environment variable
    3. the path in a git-ignored .archive-dir file
    4. ./releases
"""

from __future__ import annotations

import argparse
import io
import json
import os
import subprocess
import sys
import tarfile
import tomllib
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def default_base() -> Path:
    env = os.environ.get("BRIDGE_D_ARCHIVE_DIR")
    if env:
        return Path(env)
    marker = ROOT / ".archive-dir"
    if marker.exists():
        value = marker.read_text(encoding="utf-8").strip()
        if value:
            return Path(value)
    return ROOT / "releases"


def current_version() -> str:
    with (ROOT / "pyproject.toml").open("rb") as fh:
        return str(tomllib.load(fh)["project"]["version"])


def git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default=None)
    parser.add_argument("--date", default=date.today().strftime("%Y%m%d"))
    args = parser.parse_args()

    version = current_version()
    base = Path(args.base) if args.base else default_base()
    destination = base / f"v{version}-{args.date}"
    if destination.exists():
        print(f"refusing to overwrite existing archive: {destination}")
        return 1

    print("running public-leak guard ...")
    guard = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_public.py")], cwd=ROOT
    )
    if guard.returncode != 0:
        print("guard failed; archive aborted")
        return 1

    print(f"exporting HEAD to {destination} ...")
    archive = subprocess.run(
        ["git", "archive", "--format=tar", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    )
    destination.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tar:
        tar.extractall(destination, filter="data")

    metadata = {
        "name": "BRIDGE-D",
        "version": version,
        "commit": git("rev-parse", "HEAD"),
        "archived_at": date.today().isoformat(),
        "files": sum(1 for path in destination.rglob("*") if path.is_file()),
    }
    (destination / "RELEASE.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(metadata, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
