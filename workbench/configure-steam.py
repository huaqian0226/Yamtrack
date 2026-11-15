#!/usr/bin/env python3
"""Save Steam credentials locally, without echoing them or using argv."""
from pathlib import Path
from getpass import getpass
import os, re, subprocess
root = Path(__file__).resolve().parent / "yamtrack"
key = getpass("Steam Web API key (hidden): ").strip()
if not re.fullmatch(r"[0-9A-Fa-f]{32}", key):
    raise SystemExit("Expected a 32-character Steam Web API key; no changes made.")
p = root / ".env"
s = p.read_text()
assert re.search(r"^STEAM_API_KEY=.*$", s, flags=re.M)
s = re.sub(r"^STEAM_API_KEY=.*$", "STEAM_API_KEY=" + key, s, flags=re.M)
p.write_text(s)
os.chmod(p, 0o600)
subprocess.run(["/opt/homebrew/bin/docker", "compose", "up", "-d"], cwd=root, check=True)
print("Key saved locally. Enter your Steam ID 64 in Yamtrack Settings > Import Data.")
