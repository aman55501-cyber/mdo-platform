"""Housekeeping backups — daily snapshots, the weekly bundle, the off-site door.

Pure-function tests run mdo_housekeeping against a scratch database in tmp_path
(no network: MDO_AUTH_TOKEN is blanked so _report only logs). The API tests
follow tests/test_sessions.py: a scratch VEGA_DB_PATH is set before mdo_server
is imported, so nothing here can touch a real database.
"""
from __future__ import annotations

import gzip
import os
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("VEGA_DB_PATH", os.path.join(tempfile.mkdtemp(), "t.db"))

import mdo_housekeeping as hk  # noqa: E402
from mdo_cos import IST  # noqa: E402

HAVE_OPENSSL = shutil.which("openssl") is not None
TODAY = datetime.now(IST).strftime("%Y%m%d")


@pytest.fixture
def world(tmp_path, monkeypatch):
    """A scratch database with rows, an empty backups dir, a one-file vault, no token, no passphrase."""
    db = tmp_path / "vega_data.db"
    c = sqlite3.connect(db)
    c.execute("CREATE TABLE t (x INTEGER)")
    c.executemany("INSERT INTO t VALUES (?)", [(i,) for i in range(500)])
    c.commit()
    c.close()
    vault = tmp_path / "vault" / "memory"
    vault.mkdir(parents=True)
    (vault / "entity-registry.md").write_text("# entities\n", encoding="utf-8")
    monkeypatch.setattr(hk, "DB_PATH", str(db))
    monkeypatch.setattr(hk, "BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setattr(hk, "ARCHIVE_DIR", str(tmp_path / "archive"))
    monkeypatch.setattr(hk, "VAULT_DIR", str(tmp_path / "vault"))
    monkeypatch.setattr(hk, "KEY", "")
    monkeypatch.delenv("VEDANTA_DB_PATH", raising=False)
    monkeypatch.delenv("VAULT_BACKUP_PASSPHRASE", raising=False)
    reports: list[tuple] = []
    monkeypatch.setattr(hk, "_report", lambda status, summary, findings=None, cadence="weekly":
                        reports.append((status, summary, findings or [], cadence)))
    return {"db": db, "backups": tmp_path / "backups", "vault": tmp_path / "vault", "reports": reports}


def _rows_in_gz(gz_path) -> int:
    raw = str(gz_path) + ".check"
    with gzip.open(gz_path, "rb") as src, open(raw, "wb") as dst:
        shutil.copyfileobj(src, dst)
    c = sqlite3.connect(raw)
    try:
        assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        return c.execute("SELECT COUNT(*) FROM t").fetchone()[0]
    finally:
        c.close()
        os.remove(raw)


# ── daily snapshots ──────────────────────────────────────────────────────────
def test_daily_snapshot_is_a_valid_gzipped_database(world):
    assert hk.run_daily() == 0
    gz = world["backups"] / f"vega-{TODAY}.db.gz"
    assert gz.is_file()
    assert oct(gz.stat().st_mode & 0o777) == "0o600"
    assert _rows_in_gz(gz) == 500
    assert hk.verify_snapshot(str(gz)) is True
    # one heartbeat line, daily cadence, clean (unless the test box itself is low on disk)
    status, summary, findings, cadence = world["reports"][-1]
    assert cadence == "daily"
    assert "daily: vega" in summary and "snapshot ok" in summary and "1 kept" in summary and "disk" in summary
    assert not [f for f in findings if "snapshot" in f["title"]]
    # no temp files left behind
    assert sorted(p.name for p in world["backups"].iterdir() if not p.name.startswith(".")) == [gz.name]


def test_retention_keeps_fourteen_newest(world):
    world["backups"].mkdir()
    for i in range(1, 21):                       # 20 older snapshots (2001..2020), oldest first
        (world["backups"] / f"vega-20{i:02d}0101.db.gz").write_bytes(b"old")
    (world["backups"] / "vedanta-20260101.db.gz").write_bytes(b"other db, untouched")
    hk.run_daily()
    kept = sorted(p.name for p in world["backups"].glob("vega-*.db.gz"))
    assert len(kept) == 14
    assert kept[-1] == f"vega-{TODAY}.db.gz"
    assert "vega-20010101.db.gz" not in kept and "vega-20070101.db.gz" not in kept   # 21 files, 14 kept → 7 oldest go
    assert "vega-20080101.db.gz" in kept
    assert (world["backups"] / "vedanta-20260101.db.gz").exists()
    assert "14 kept" in world["reports"][-1][1]


def test_failed_integrity_check_discards_snapshot_and_prunes_nothing(world, monkeypatch):
    world["backups"].mkdir()
    for i in range(1, 21):
        (world["backups"] / f"vega-20{i:02d}0101.db.gz").write_bytes(b"old")
    monkeypatch.setattr(hk, "_integrity_ok", lambda path: False)
    hk.run_daily()
    assert len(list(world["backups"].glob("vega-*.db.gz"))) == 20          # nothing pruned
    assert not (world["backups"] / f"vega-{TODAY}.db.gz").exists()         # bad copy discarded
    status, summary, findings, cadence = world["reports"][-1]
    assert status == "warning" and "FAILED" in summary
    assert any(f["level"] == "critical" and "snapshot failed" in f["title"] for f in findings)


def test_vedanta_db_is_snapshotted_only_when_set_and_present(world, monkeypatch, tmp_path):
    assert [n for n, _ in hk.db_paths()] == ["vega"]
    monkeypatch.setenv("VEDANTA_DB_PATH", str(tmp_path / "missing.db"))
    assert [n for n, _ in hk.db_paths()] == ["vega"]
    v = tmp_path / "vedanta_crm.db"
    sqlite3.connect(v).close()
    monkeypatch.setenv("VEDANTA_DB_PATH", str(v))
    assert [n for n, _ in hk.db_paths()] == ["vega", "vedanta"]
    hk.run_daily()
    assert (world["backups"] / f"vedanta-{TODAY}.db.gz").is_file()
    assert "vedanta" in world["reports"][-1][1]


def test_daily_dry_run_writes_nothing(world):
    hk.run_daily(dry=True)
    assert not list(world["backups"].glob("*.db.gz"))
    assert "DRY RUN" in world["reports"][-1][1]


# ── weekly bundle ────────────────────────────────────────────────────────────
def test_bundle_skipped_without_passphrase_and_says_so(world):
    hk.run_daily()
    note = hk.backup_bundle(dry=False)
    assert "SKIPPED" in note and "VAULT_BACKUP_PASSPHRASE" in note
    assert not list(world["backups"].glob("*.enc"))
    assert not list(world["backups"].glob("*.tmp"))


@pytest.mark.skipif(not HAVE_OPENSSL, reason="openssl not installed")
def test_bundle_holds_vault_and_latest_snapshots_and_keeps_eight(world, monkeypatch):
    monkeypatch.setenv("VAULT_BACKUP_PASSPHRASE", "test-passphrase")
    world["backups"].mkdir()
    for i in range(1, 11):                       # 10 older bundles (2001..2010)
        (world["backups"] / f"weekly-20{i:02d}0101.tar.enc").write_bytes(b"old")
    (world["backups"] / "vega-20260101.db.gz").write_bytes(b"stale snapshot, not the latest")
    hk.run_daily()
    note = hk.backup_bundle(dry=False)
    assert "weekly-" in note and "AES-256" in note and "8 kept" in note, note
    enc = world["backups"] / f"weekly-{TODAY}.tar.enc"
    assert enc.is_file() and oct(enc.stat().st_mode & 0o777) == "0o600"
    bundles = sorted(p.name for p in world["backups"].glob("weekly-*.tar.enc"))
    assert len(bundles) == 8 and bundles[-1] == enc.name and "weekly-20010101.tar.enc" not in bundles
    # decrypt with the documented command and look inside
    tar_path = str(enc)[:-4]
    subprocess.run(["openssl", "enc", "-d", "-aes-256-cbc", "-pbkdf2", "-pass", "env:VAULT_BACKUP_PASSPHRASE",
                    "-in", str(enc), "-out", tar_path], check=True,
                   env={**os.environ, "VAULT_BACKUP_PASSPHRASE": "test-passphrase"})
    with tarfile.open(tar_path) as tar:
        names = tar.getnames()
        tar.extract(f"db/vega-{TODAY}.db.gz", path=str(world["backups"] / "x"),
                    **({"filter": "data"} if hasattr(tarfile, "data_filter") else {}))
    assert "vault/memory/entity-registry.md" in names
    assert f"db/vega-{TODAY}.db.gz" in names
    assert "db/vega-20260101.db.gz" not in names                           # only the newest per database
    assert _rows_in_gz(world["backups"] / "x" / "db" / f"vega-{TODAY}.db.gz") == 500
    # a wrong passphrase must not decrypt
    bad = subprocess.run(["openssl", "enc", "-d", "-aes-256-cbc", "-pbkdf2", "-pass", "pass:wrong",
                          "-in", str(enc), "-out", tar_path + ".bad"], capture_output=True)
    assert bad.returncode != 0
    assert not list(world["backups"].glob("*.tmp"))


def test_bundle_with_nothing_to_back_up_is_named_not_silent(world):
    shutil.rmtree(world["vault"])
    assert "nothing to back up" in hk.backup_bundle(dry=False)


@pytest.mark.skipif(not HAVE_OPENSSL, reason="openssl not installed")
def test_weekly_run_snapshots_then_bundles(world, monkeypatch):
    monkeypatch.setenv("VAULT_BACKUP_PASSPHRASE", "test-passphrase")
    assert hk.run() == 0
    assert (world["backups"] / f"vega-{TODAY}.db.gz").is_file()
    assert (world["backups"] / f"weekly-{TODAY}.tar.enc").is_file()
    status, summary, findings, cadence = world["reports"][-1]
    assert cadence == "weekly"
    assert "vega snapshot ok" in summary and "bundle:" in summary and "weekly-" in summary
    assert "archived 0 rows" in summary


def test_weekly_run_without_passphrase_is_a_warning(world):
    hk.run()
    status, summary, findings, cadence = world["reports"][-1]
    assert status == "warning" and "SKIPPED" in summary


# ── off-site door: /api/vault/backup/* ───────────────────────────────────────
@pytest.fixture
def api(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import mdo_server
    bdir = tmp_path / "backups"
    bdir.mkdir()
    monkeypatch.setenv("BACKUP_DIR", str(bdir))
    monkeypatch.setenv("VAULT_TOKEN", "vault-test-token")
    return TestClient(mdo_server.app), bdir


def test_backup_endpoints_require_the_vault_token(api):
    client, bdir = api
    (bdir / f"weekly-{TODAY}.tar.enc").write_bytes(b"enc")
    assert client.get("/api/vault/backup/list").status_code == 403
    assert client.get("/api/vault/backup/latest", headers={"X-Vault-Token": "wrong"}).status_code == 403
    assert client.get("/api/vault/backup/latest").status_code == 403
    # the app key is not the vault token
    assert client.get("/api/vault/backup/latest", headers={"X-MDO-Key": "vault-test-token"}).status_code == 403


def test_backup_list_and_latest_serve_only_enc_files(api):
    client, bdir = api
    h = {"X-Vault-Token": "vault-test-token"}
    (bdir / "weekly-20260901.tar.enc").write_bytes(b"older")
    (bdir / "weekly-20260908.tar.enc").write_bytes(b"newest-bundle")
    (bdir / "vega-20260908.db.gz").write_bytes(b"raw snapshot")
    (bdir / "vega-20260908.db").write_bytes(b"raw db")
    (bdir / ".housekeeping.lock").write_bytes(b"")
    (bdir / "notes.txt").write_bytes(b"txt")
    listed = client.get("/api/vault/backup/list", headers=h)
    assert listed.status_code == 200
    names = [b["name"] for b in listed.json()]
    assert names == ["weekly-20260908.tar.enc", "weekly-20260901.tar.enc"]
    assert all(set(b) == {"name", "bytes", "created"} for b in listed.json())
    latest = client.get("/api/vault/backup/latest", headers=h)
    assert latest.status_code == 200
    assert latest.content == b"newest-bundle"
    assert "weekly-20260908.tar.enc" in latest.headers["content-disposition"]
    assert latest.headers["content-type"].startswith("application/octet-stream")
    # every call is audited, bad token included
    client.get("/api/vault/backup/latest", headers={"X-Vault-Token": "wrong"})
    audit = client.get("/api/vault/audit", headers=h).json()["audit"]
    actions = [(a["action"], a["ok"]) for a in audit[:4]]
    assert ("backup-latest", 0) in actions and ("backup-latest", 1) in actions and ("backup-list", 1) in actions


def test_backup_latest_404_when_no_bundle(api):
    client, bdir = api
    h = {"X-Vault-Token": "vault-test-token"}
    (bdir / "vega-20260908.db.gz").write_bytes(b"a snapshot is not a bundle")
    (bdir / "vault-2026-09-01.tar.gz.enc").write_bytes(b"old vault-only file")
    r = client.get("/api/vault/backup/latest", headers=h)
    assert r.status_code == 404
    assert "no weekly bundle yet" in r.json()["detail"]
    assert [b["name"] for b in client.get("/api/vault/backup/list", headers=h).json()] == ["vault-2026-09-01.tar.gz.enc"]
