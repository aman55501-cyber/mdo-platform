#!/usr/bin/env python3
"""Load the Share Master seed files (the CoS's transcribed pf/*.json) into the running backend.

The files are NOT in the repo or the image — they hold the family's holdings. Three shapes:
  HDFC-derived   {"holder": "Aditi", "holdings": [{code, ticker, name, qty, avg, cmp, cur, pl_pct}, ...]}
  Angel-derived  {"holder": "Aditi Investments", "broker": "Angel One", "holdings": [{isin, name, qty, value, cmp, ticker}, ...]}
        → POST /api/share-master/portfolio/import   (replaces that holder's uploaded holdings)
  positions_*.json  {"positions": [{account, instrument, side, qty, avg, ltp, pl, product}, ...], "as_of": "..."}
        → POST /api/share-master/positions/import   (replace-all per account)
Anything else (e.g. live_noprice.json) is skipped and said. One line per file with the HTTP status.

Two ways to run, both on the VPS, inside the backend container (X-MDO-Key = MDO_AUTH_TOKEN from the
container env, base http://127.0.0.1:8501):

  a directory already copied into the container:
    docker compose cp /root/pf backend:/tmp/pf
    docker compose exec -T backend python tools/import_share_master.py /tmp/pf

  --stdin: one document per call, piped from the host (no copy step); env DOC first, else stdin:
    cd /docker/sharecfo/mdo-platform && for f in pf/*.json; do docker compose exec -T -e DOC="$(cat "$f")" -e DOC_NAME="$f" backend python tools/import_share_master.py --stdin; done; docker compose exec -T backend python tools/import_share_master.py --refresh

The directory mode ends with POST /api/share-master/refresh so the workbook in the vault reflects the
import; --stdin does not (one refresh after the loop, via --refresh, prices the whole book once).
Same style as tools/import_levels.py. Exit code 1 when any file failed.
"""
import glob
import json
import math
import os
import sys
import urllib.error
import urllib.request

base = os.environ.get("MDO_SELF_INTERNAL", "http://127.0.0.1:8501")
key = os.environ.get("MDO_AUTH_TOKEN", "")


def finite(obj):
    """Python's json.load accepts Infinity/NaN (a pl_pct on bonus shares with avg cost 0); strict JSON
    does not. Those become null — the API then shows the cell as n/a, never a number."""
    if isinstance(obj, float) and not math.isfinite(obj):
        return None
    if isinstance(obj, dict):
        return {k: finite(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [finite(v) for v in obj]
    return obj


def post(path: str, body: dict, timeout: int = 240) -> tuple[int, dict]:
    """(http status, parsed reply). 0 = no HTTP reply at all (connection refused, timeout)."""
    req = urllib.request.Request(base + path, data=json.dumps(finite(body), allow_nan=False).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "X-MDO-Key": key})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        raw = e.read()[:400].decode(errors="replace")
        try:
            detail = json.loads(raw)
        except ValueError:
            detail = {"detail": raw}
        return e.code, detail if isinstance(detail, dict) else {"detail": detail}
    except Exception as e:
        return 0, {"detail": f"{type(e).__name__}: {str(e)[:200]}"}


def _detail(res: dict) -> str:
    d = res.get("detail", res)
    return (json.dumps(d) if not isinstance(d, str) else d)[:200]


def load_doc(doc: dict, name: str) -> tuple[str, bool]:
    """Route one document to its endpoint. Returns (the line to print, ok)."""
    if not isinstance(doc, dict):
        return f"{name}: skipped (not a JSON object)", True
    if isinstance(doc.get("holdings"), list):
        holder = str(doc.get("holder") or os.path.basename(name).split("_")[0].title()).strip()
        broker = str(doc.get("broker") or "")
        status, res = post("/api/share-master/portfolio/import",
                           {"holder": holder, "broker": broker, "holdings": finite(doc["holdings"]), "as_of": doc.get("as_of")})
        kind = f"holdings {holder}" + (f" ({broker})" if broker else "")
        if status != 200:
            return f"{name}: {kind} → HTTP {status} {_detail(res)}", False
        unv = res.get("unverified") or []
        return (f"{name}: {kind} → HTTP {status}, {res.get('count')} stored, {len(unv)} unverified"
                + (f" ({', '.join(unv[:8])}{' …' if len(unv) > 8 else ''})" if unv else "")
                + f", resolved {res.get('resolved_by')}, NSE list {res.get('nse_list')}"), True
    if isinstance(doc.get("positions"), list):
        status, res = post("/api/share-master/positions/import",
                           {"positions": doc["positions"], "as_of": doc.get("as_of") or "", "source": str(doc.get("source") or "manual")[:30]})
        if status != 200:
            return f"{name}: positions → HTTP {status} {_detail(res)}", False
        return (f"{name}: positions → HTTP {status}, {res.get('stored')} stored for {res.get('accounts')}, "
                f"{len(res.get('rejected') or [])} rejected, P&L {(res.get('summary') or {}).get('pl')}"), True
    return f"{name}: skipped (neither holdings nor positions)", True


def refresh() -> bool:
    status, res = post("/api/share-master/refresh", {})
    if status != 200:
        print(f"refresh → HTTP {status} {_detail(res)}")
        return False
    v = res.get("vault") or {}
    s = (res.get("summary") or {}).get("total") or {}
    print(f"refresh → HTTP {status}, {s.get('n')} holdings, "
          f"workbook {'saved ' + v.get('path', '') if v.get('saved') else 'NOT saved: ' + str(v.get('error'))}"
          + (f", ltp n/a: {', '.join(res['ltp_missing'][:8])}" if res.get("ltp_missing") else ""))
    return True


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:] if not a.startswith("--")]
    flags = {a for a in argv[1:] if a.startswith("--")}
    if "--refresh" in flags and not args and "--stdin" not in flags:
        return 0 if refresh() else 1
    if "--stdin" in flags:
        raw = os.environ.get("DOC") or sys.stdin.read()
        name = os.environ.get("DOC_NAME") or "<stdin>"
        try:
            doc = json.loads(raw or "")
        except ValueError as e:
            print(f"{name}: unreadable ({e})")
            return 1
        line, ok = load_doc(doc, name)
        print(line)
        if "--refresh" in flags:
            ok = refresh() and ok
        return 0 if ok else 1
    folder = args[0] if args else "pf"
    files = sorted(glob.glob(os.path.join(folder, "*.json")))
    if not files:
        print(f"share-master import: no *.json in {folder}")
        return 1
    rc = 0
    for path in files:
        name = os.path.basename(path)
        try:
            with open(path, encoding="utf-8") as f:
                doc = json.load(f)
        except (OSError, ValueError) as e:
            print(f"{name}: unreadable ({e})")
            rc = 1
            continue
        line, ok = load_doc(doc, name)
        print(line)
        if not ok:
            rc = 1
    if "--no-refresh" not in flags and not refresh():
        rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv))
