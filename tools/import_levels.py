#!/usr/bin/env python3
"""Load a levels JSON (data/levels_import_*.json, or data/option_levels_import_*.json) into the running backend.
Run on the VPS:  docker compose exec -T backend python tools/import_levels.py data/levels_import_2026-10-09.json
Uses MDO_AUTH_TOKEN from the container environment; prints one line per outcome."""
import json, os, sys, urllib.request
path = sys.argv[1] if len(sys.argv) > 1 else "data/levels_import_2026-10-09.json"
base = os.environ.get("MDO_SELF_INTERNAL", "http://127.0.0.1:8501")
doc = json.load(open(path, encoding="utf-8"))
hdrs = {"Content-Type": "application/json", "X-MDO-Key": os.environ.get("MDO_AUTH_TOKEN", "")}
rows = [r for r in doc.get("levels") or [] if r.get("buy_level") or r.get("sell_level")]
if rows:
    req = urllib.request.Request(base + "/api/levels", data=json.dumps(rows).encode(), method="POST", headers=hdrs)
    with urllib.request.urlopen(req, timeout=60) as r:
        print("levels import:", len(rows), "rows →", r.status, r.read()[:200].decode(errors="replace"))
# option levels (data/option_levels_import_*.json, key "options") → POST /api/levels/options (mdo_option_levels)
opts = [o for o in doc.get("options") or [] if o.get("alert_below") or o.get("alert_above")]
if opts:
    req = urllib.request.Request(base + "/api/levels/options", data=json.dumps(opts).encode(), method="POST", headers=hdrs)
    with urllib.request.urlopen(req, timeout=60) as r:
        print("option levels import:", len(opts), "rows →", r.status, r.read()[:200].decode(errors="replace"))
if not rows and not opts:
    print("nothing to import in", path)
