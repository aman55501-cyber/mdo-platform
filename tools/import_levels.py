#!/usr/bin/env python3
"""Load a levels JSON (data/levels_import_*.json) into the running backend.
Run on the VPS:  docker compose exec -T backend python tools/import_levels.py data/levels_import_2026-10-09.json
Uses MDO_AUTH_TOKEN from the container environment; prints one line per outcome."""
import json, os, sys, urllib.request
path = sys.argv[1] if len(sys.argv) > 1 else "data/levels_import_2026-10-09.json"
base = os.environ.get("MDO_SELF_INTERNAL", "http://127.0.0.1:8501")
doc = json.load(open(path, encoding="utf-8"))
rows = [r for r in doc["levels"] if r.get("buy_level") or r.get("sell_level")]
req = urllib.request.Request(base + "/api/levels", data=json.dumps(rows).encode(), method="POST",
                             headers={"Content-Type": "application/json", "X-MDO-Key": os.environ.get("MDO_AUTH_TOKEN", "")})
with urllib.request.urlopen(req, timeout=60) as r:
    print("levels import:", len(rows), "rows →", r.status, r.read()[:200].decode(errors="replace"))
