"""Site access — read the Hotel ANS and Vedanta site networks over the VPN sidecars.

The tunnels already exist as one container per site (`vpn-hotel`, `vpn-vedanta`), each
running an OpenVPN client plus an HTTP proxy on :8888 that is never published to the
host. Nothing in the backend read them until now: `HOTEL_PROXY_URL` and
`VEDANTA_PROXY_URL` were passed into the container and used by no code. This module is
that missing layer.

Two things it deliberately does NOT do:

  * **It invents no site hostnames.** The addresses and services inside those LANs have
    not been discovered yet (see `docs/PLAN_VPN_SITE_ACCESS.md` — discovery is its
    Phase 3). Sources are therefore *configured*, not hardcoded: set `MDO_SITE_SOURCES`
    to a JSON array, or drop a `site_sources.json` next to this file. With nothing
    configured the module reports "no sources configured" — never a guessed URL and
    never a fabricated number.

  * **It never writes to a site system.** v1 is read-only by the standing decision in
    that plan (R9). Only GET is issued, and `SAFE_METHODS` is the single place that
    would have to change.

Why a proxy rather than routes: the tunnel is confined to the sidecar's network
namespace, so a route pushed by the site gateway cannot take the VPS off the internet.
The backend simply sends its request to `http://vpn-hotel:8888` as an HTTP proxy.

Accuracy discipline: every reading carries where it came from and how old it is. A site
that cannot be reached returns an explicit error — the caller shows a gap, never a
stale number dressed up as current.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

IST = timezone(timedelta(hours=5, minutes=30))

# Read-only by standing decision. Widening this list is a separate risk review.
SAFE_METHODS = ("GET",)

SITES: dict[str, dict] = {
    "hotel": {
        "label": "Hotel ANS International",
        "proxy_env": "HOTEL_PROXY_URL",
        "default_proxy": "http://vpn-hotel:8888",
        "domain": "hotel",
    },
    "vedanta": {
        "label": "VWLR — Vedanta washery",
        "proxy_env": "VEDANTA_PROXY_URL",
        "default_proxy": "http://vpn-vedanta:8888",
        "domain": "vwlr",
    },
}


def _now() -> datetime:
    return datetime.now(IST)


def proxy_url(site: str) -> str:
    cfg = SITES.get(site)
    if not cfg:
        return ""
    return os.environ.get(cfg["proxy_env"], "").strip() or cfg["default_proxy"]


def _timeout() -> int:
    try:
        return int(os.environ.get("MDO_SITE_TIMEOUT", "").strip() or 12)
    except ValueError:
        return 12


# ── Configured sources ─────────────────────────────────────────────────────
# Each source: {"site": "hotel", "key": "occupancy", "url": "http://10.x.x.x/api/...",
#               "label": "...", "format": "json|text", "json_path": "a.b.c"}
# `json_path` is optional and only extracts; it never computes or infers a value.

def _sources_path() -> Path:
    return Path(os.environ.get("MDO_SITE_SOURCES_FILE", "").strip()
                or Path(__file__).with_name("site_sources.json"))


def load_sources() -> list[dict]:
    """Configured site sources, from env JSON first, then the optional file."""
    raw = os.environ.get("MDO_SITE_SOURCES", "").strip()
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                return [s for s in data if isinstance(s, dict)]
        except ValueError:
            pass
    p = _sources_path()
    if p.exists():
        try:
            data = json.loads(p.read_text() or "[]")
            if isinstance(data, list):
                return [s for s in data if isinstance(s, dict)]
        except (ValueError, OSError):
            pass
    return []


def sources_for(site: str) -> list[dict]:
    return [s for s in load_sources() if s.get("site") == site]


# ── Fetching ───────────────────────────────────────────────────────────────

def fetch_through(site: str, url: str, method: str = "GET", timeout: int | None = None) -> dict:
    """One read from a site host, through that site's tunnel.

    Always returns a dict; failures are reported, never raised into a caller that
    might then show a stale number as if it were fresh.
    """
    if method.upper() not in SAFE_METHODS:
        return {"ok": False, "error": f"{method} blocked — site access is read-only in v1",
                "site": site, "url": url}
    px = proxy_url(site)
    if not px:
        return {"ok": False, "error": f"unknown site {site!r}", "site": site, "url": url}

    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({"http": px, "https": px}))
    started = _now()
    try:
        with opener.open(urllib.request.Request(url, method=method.upper()),
                         timeout=timeout or _timeout()) as r:
            body = r.read(1_000_000)
            status = r.status
        text = body.decode("utf-8", "replace")
        out: dict[str, Any] = {
            "ok": 200 <= status < 300,
            "status": status,
            "site": site,
            "url": url,
            "via": px,
            "fetched_at": started.isoformat(timespec="seconds"),
            "elapsed_ms": int((_now() - started).total_seconds() * 1000),
        }
        try:
            out["json"] = json.loads(text)
        except ValueError:
            out["text"] = text[:20_000]
        return out
    except urllib.error.HTTPError as e:
        # The tunnel worked; the site host answered with an error. Worth distinguishing.
        return {"ok": False, "status": e.code, "site": site, "url": url, "via": px,
                "error": f"site host returned HTTP {e.code}", "reachable": True,
                "fetched_at": started.isoformat(timespec="seconds")}
    except Exception as e:
        return {"ok": False, "site": site, "url": url, "via": px,
                "error": f"{type(e).__name__}: {e}"[:300], "reachable": False,
                "fetched_at": started.isoformat(timespec="seconds")}


def _dig(data: Any, path: str) -> Any:
    """Walk a dotted path. Returns None when absent — never a substitute value."""
    cur = data
    for part in [p for p in path.split(".") if p]:
        if isinstance(cur, dict):
            cur = cur.get(part)
        elif isinstance(cur, list) and part.isdigit() and int(part) < len(cur):
            cur = cur[int(part)]
        else:
            return None
    return cur


def read_source(source: dict) -> dict:
    """Fetch one configured source and extract its value, if a path was given."""
    site, url = source.get("site", ""), source.get("url", "")
    if not site or not url:
        return {"ok": False, "error": "source needs both 'site' and 'url'", "source": source}
    res = fetch_through(site, url)
    out = {"key": source.get("key", ""), "label": source.get("label", ""),
           "site": site, **res}
    path = source.get("json_path")
    if res.get("ok") and path:
        value = _dig(res.get("json"), path)
        out["value"] = value
        if value is None:
            out["ok"] = False
            out["error"] = f"json_path {path!r} not present in the response"
    return out


def read_site(site: str) -> dict:
    """Every configured source for one site."""
    srcs = sources_for(site)
    if not srcs:
        return {"site": site, "label": SITES.get(site, {}).get("label", site),
                "configured": False,
                "note": ("no sources configured for this site — set MDO_SITE_SOURCES or "
                         "site_sources.json once the site's hosts are discovered"),
                "readings": []}
    readings = [read_source(s) for s in srcs]
    return {"site": site, "label": SITES.get(site, {}).get("label", site),
            "configured": True,
            "ok": all(r.get("ok") for r in readings),
            "readings": readings,
            "read_at": _now().isoformat(timespec="seconds")}


# ── Tunnel health ──────────────────────────────────────────────────────────

def tunnel_status(site: str) -> dict:
    """Is this site's tunnel carrying traffic right now?

    Probed by asking the sidecar's proxy to reach a configured probe URL. Without a
    probe URL we can still say whether the proxy itself answers, which distinguishes
    "sidecar down" from "tunnel down" — a distinction worth having at 3am.
    """
    cfg = SITES.get(site)
    if not cfg:
        return {"site": site, "up": False, "error": f"unknown site {site!r}"}
    px = proxy_url(site)
    probe = os.environ.get(f"{site.upper()}_PROBE_URL", "").strip()

    if probe:
        res = fetch_through(site, probe, timeout=8)
        return {"site": site, "label": cfg["label"], "proxy": px, "probe": probe,
                "up": bool(res.get("ok") or res.get("reachable")),
                "detail": res.get("error") or f"HTTP {res.get('status')}",
                "checked_at": _now().isoformat(timespec="seconds")}

    # No probe target configured: test that the proxy port answers at all.
    host_port = px.split("://", 1)[-1]
    host, _, port = host_port.partition(":")
    import socket
    try:
        with socket.create_connection((host, int(port or 8888)), timeout=5):
            reachable = True
            detail = "proxy answering; no probe URL set, tunnel state not confirmed"
    except Exception as e:
        reachable = False
        detail = f"proxy unreachable — {type(e).__name__}: {e}"[:200]
    return {"site": site, "label": cfg["label"], "proxy": px, "probe": None,
            "up": reachable, "detail": detail,
            "checked_at": _now().isoformat(timespec="seconds")}


def all_tunnels() -> dict:
    return {"sites": [tunnel_status(s) for s in SITES],
            "checked_at": _now().isoformat(timespec="seconds")}


# ── Raw TCP reachability ───────────────────────────────────────────────────
# Not every site system speaks HTTP. The hotel runs IDS Next FortuneNext, a SQL
# Server application, so its data lives behind TCP/1433 — an HTTP proxy cannot
# carry that. The sidecar publishes plain TCP forwards for those cases; this
# checks whether one is actually answering.

def tcp_reachable(host: str, port: int, timeout: float = 5.0) -> dict:
    """Can we open a TCP connection? Says nothing about auth or contents."""
    import socket
    started = _now()
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return {"ok": True, "host": host, "port": int(port),
                    "checked_at": started.isoformat(timespec="seconds")}
    except Exception as e:
        return {"ok": False, "host": host, "port": int(port),
                "error": f"{type(e).__name__}: {e}"[:200],
                "checked_at": started.isoformat(timespec="seconds")}


def tcp_forwards(site: str) -> list[dict]:
    """Forwards configured for a site, parsed from the same listen:host:port string
    the sidecar is given, so the two can never drift apart."""
    raw = os.environ.get(f"{site.upper()}_TCP_FORWARDS", "").strip()
    out = []
    for rule in [r.strip() for r in raw.split(",") if r.strip()]:
        parts = rule.split(":")
        if len(parts) != 3 or not parts[0].isdigit() or not parts[2].isdigit():
            out.append({"rule": rule, "valid": False,
                        "error": "expected listen:host:port"})
            continue
        out.append({"rule": rule, "valid": True, "listen_port": int(parts[0]),
                    "target_host": parts[1], "target_port": int(parts[2])})
    return out


def tcp_status(site: str) -> list[dict]:
    """Probe every configured forward for a site through its sidecar."""
    cfg = SITES.get(site)
    if not cfg:
        return []
    # The sidecar hostname is the proxy URL's host, minus the HTTP port.
    host = proxy_url(site).split("://", 1)[-1].partition(":")[0]
    results = []
    for fwd in tcp_forwards(site):
        if not fwd.get("valid"):
            results.append({**fwd, "ok": False})
            continue
        probe = tcp_reachable(host, fwd["listen_port"])
        results.append({**fwd, **probe, "via": f"{host}:{fwd['listen_port']}"})
    return results


# ── Feed integration ───────────────────────────────────────────────────────

async def publish_tunnel_alerts(db, feed) -> list[dict]:
    """A dead tunnel means the site data behind it is silently absent — which is
    exactly the failure that makes a dashboard lie. Publish it as a finding.

    Only sites with at least one configured source are alerted on: a tunnel nothing
    reads through is not yet load-bearing.
    """
    published = []
    for site, cfg in SITES.items():
        if not sources_for(site):
            continue
        st = tunnel_status(site)
        if st.get("up"):
            continue
        item = await feed.publish(
            db,
            key=f"site.tunnel.down.{site}",
            title=f"{cfg['label']} — site link is down",
            severity="critical",
            source="mdo_sites.tunnel_check",
            domain=cfg["domain"],
            body=(f"The VPN sidecar for {cfg['label']} is not carrying traffic, so every "
                  f"reading from that site is missing rather than merely stale. "
                  f"Detail: {st.get('detail')}"),
            evidence=[{"proxy": st.get("proxy"), "detail": st.get("detail"),
                       "checked_at": st.get("checked_at")}],
        )
        if item:
            published.append(item)
    return published
