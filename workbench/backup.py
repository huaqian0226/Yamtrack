#!/usr/bin/env python3
"""Create a private consistent backup, with no plaintext passwords or .env."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import subprocess, tarfile, os, sqlite3
ROOT = Path(__file__).resolve().parent
KNOWLEDGE = Path(os.environ["WORKBENCH_KNOWLEDGE_DIR"])
DOCKER = "/opt/homebrew/bin/docker"
os.umask(0o077)
out = ROOT / "backups" / datetime.now(ZoneInfo("Europe/London")).strftime("%Y%m%d-%H%M%S")
out.mkdir(parents=True, exist_ok=False)
services = ["yamtrack", "yamtrack-redis", "games-silverbullet"]
try:
    subprocess.run([DOCKER, "stop", *services], check=True, stdout=subprocess.DEVNULL)
    with tarfile.open(out / "data.tar.gz", "w:gz") as tar:
        for source, target in [(ROOT / "yamtrack/db", "yamtrack-db"), (ROOT / "silverbullet/data", "silverbullet-data"), (ROOT / "silverbullet/library", "silverbullet-library"), (KNOWLEDGE, "knowledge")]:
            tar.add(source, arcname=target)
    for db in (ROOT / "yamtrack/db").glob("*.sqlite3"):
        with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as conn:
            assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    print(out / "data.tar.gz")
finally:
    subprocess.run([DOCKER, "start", *services], check=True, stdout=subprocess.DEVNULL)
