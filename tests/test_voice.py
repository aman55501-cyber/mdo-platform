"""voice — WhatsApp voice notes transcribed on the VPS with faster-whisper, no API, zero LLM spend.

Nothing here touches the network or a model: faster_whisper is a fake module injected into sys.modules (a
WhisperModel that records its constructor arguments and returns canned segments), the clip is a few fake ogg
bytes, the voice dir is a temp dir. No model is ever downloaded in tests. Follows tests/test_mail.py: a scratch
VEGA_DB_PATH is set before mdo_server is imported; the endpoint tests wipe the media tables (the DB is shared by
every test module).
"""
from __future__ import annotations

import io
import json
import os
import sqlite3
import sys
import tempfile
import types
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("VEGA_DB_PATH", os.path.join(tempfile.mkdtemp(), "t.db"))
os.environ.setdefault("SHARE_MASTER_DATA_DIR", tempfile.mkdtemp())

import yaml  # noqa: E402

import mdo_agent as ag  # noqa: E402
import mdo_voice as mv  # noqa: E402
from mdo_cos import IST  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOT = {"id": "voice", "provider": "none", "model": "none"}
NOW = datetime(2026, 10, 9, 10, 0, tzinfo=IST)
OGG = b"OggS\x00\x02" + b"\x00" * 20 + b"OpusHead\x01\x01" + b"\x00" * 64          # a few fake ogg/opus bytes, not audio
MAUSAJI_JID = "919800000001@s.whatsapp.net"
WASHERY_JID = "120363111@g.us"
FAMILY_JID = "120363444@g.us"


# ── a fake faster_whisper: records how it was built, returns canned segments ──
class _Seg:
    def __init__(self, text):
        self.text = text


class _Info:
    def __init__(self, language, duration):
        self.language, self.duration = language, duration


def fake_whisper(transcripts: dict[str, str], fail: set[str] | None = None, built: list | None = None):
    """transcripts: file basename → text; fail: basenames whose transcription raises."""
    mod = types.ModuleType("faster_whisper")

    class WhisperModel:
        def __init__(self, name, **kwargs):
            self.name, self.kwargs = name, kwargs
            if built is not None:
                built.append((name, kwargs))

        def transcribe(self, path, language=None, beam_size=5, vad_filter=False, **kw):
            base = os.path.basename(path)
            if fail and base in fail:
                raise RuntimeError(f"decode failed for {base}")
            text = transcripts.get(base, "")
            words = text.split(" ")
            half = max(1, len(words) // 2)
            segs = [_Seg(" " + " ".join(words[:half]) + " "), _Seg(" ".join(words[half:]))] if text else []
            return iter(segs), _Info("hi" if "hai" in text or "karo" in text else "en", 7.5)
    mod.WhisperModel = WhisperModel
    return mod


# ── pure helpers ─────────────────────────────────────────────────────────────
def test_config_paths_and_names(monkeypatch):
    for k in ("VOICE_MODEL", "VOICE_MAX_PER_RUN", "VOICE_BUDGET_S", "VOICE_MAX_MB", "VOICE_DIR", "VOICE_MODEL_DIR"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("VEGA_DB_PATH", "/data/vega_data.db")
    assert mv.model_name() == "small" and mv.max_per_run() == 20 and mv.budget_s() == 480 and mv.max_bytes() == 20 * 1024 * 1024
    assert mv.voice_dir() == "/data/voice" and mv.model_dir() == "/data/whisper-models"
    monkeypatch.setenv("VOICE_MODEL", "base")
    monkeypatch.setenv("VOICE_MAX_PER_RUN", "5")
    monkeypatch.setenv("VOICE_BUDGET_S", "60")
    monkeypatch.setenv("VOICE_MAX_MB", "x")
    monkeypatch.setenv("VOICE_DIR", "/mnt/v")
    assert mv.model_name() == "base" and mv.max_per_run() == 5 and mv.budget_s() == 60 and mv.max_bytes() == 20 * 1024 * 1024
    assert mv.voice_dir() == "/mnt/v"
    assert mv.ext_for("audio/ogg; codecs=opus") == ".ogg" and mv.ext_for("audio/mpeg") == ".mp3" and mv.ext_for("audio/mp4") == ".m4a"
    assert mv.ext_for("") == ".bin" and mv.ext_for("audio/opus") == ".ogg"
    assert mv.safe_id("3EB0/ABC?DEF 12") == "3EB0_ABC_DEF_12" and mv.safe_id("") == "msg" and mv.safe_id("..") == "msg"
    # the IST day of the message decides the folder (a 20:30 UTC clip is the next IST day)
    assert mv.media_rel_path("2026-10-09T20:30:00Z", "3EB0ABC", "audio/ogg; codecs=opus") == "2026-10-10/3EB0ABC.ogg"
    assert mv.media_rel_path("2026-10-09T04:30:00+00:00", "M1", "audio/mpeg") == "2026-10-09/M1.mp3"
    assert mv.media_rel_path("garbage", "M1", "audio/ogg").endswith("/M1.ogg")
    body = mv.transcript_body({"account": "2", "chat_jid": WASHERY_JID, "chat_name": "Washery Civil Update", "sender": "Ravi",
                               "received_at": "2026-10-09T04:30:00+00:00", "message_id": "M9", "from_me": 0}, "pump band hai")
    assert body == {"account": "2", "group": "Washery Civil Update", "sender": "Ravi", "text": "[voice transcript] pump band hai",
                    "timestamp": "2026-10-09T04:30:00+00:00", "jid": WASHERY_JID, "chat_jid": WASHERY_JID, "chat_kind": "group",
                    "from_me": 0, "wa_msg_id": "M9:voice"}
    assert mv.transcript_body({"chat_jid": MAUSAJI_JID, "message_id": "M1"}, "x")["chat_kind"] == "dm"
    assert mv.heartbeat_line(3, 2, 1, "small", 4.26) == "voice: 3 transcribed, 2 pending, 1 failed, model small, avg 4s/clip"
    assert mv.heartbeat_line(0, 0, 0, "base", 0) == "voice: 0 transcribed, 0 pending, 0 failed, model base, avg 0s/clip"


def test_whisper_availability_and_model_load_use_cpu_int8_and_the_data_volume(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "faster_whisper", None)
    assert mv.whisper_available() is False
    built = []
    monkeypatch.setitem(sys.modules, "faster_whisper", fake_whisper({}, built=built))
    assert mv.whisper_available() is True
    monkeypatch.setenv("VOICE_MODEL_DIR", str(tmp_path / "models"))
    m = mv.load_model("small")
    assert built == [("small", {"device": "cpu", "compute_type": "int8", "download_root": str(tmp_path / "models")})]
    assert os.path.isdir(tmp_path / "models")
    res = mv.transcribe_file(m, "/nowhere/x.ogg")
    assert res == {"text": "", "language": "en", "duration": 7.5}


# ── endpoints + the run ──────────────────────────────────────────────────────
def _client():
    from fastapi.testclient import TestClient
    import mdo_server
    return TestClient(mdo_server.app)


def _wipe():
    db = sqlite3.connect(os.environ["VEGA_DB_PATH"])
    for t in ("wa_media", "wa_media_runs", "whatsapp_messages", "wa_chats"):
        db.execute(f"DELETE FROM {t}")
    db.commit(); db.close()


def _setup(monkeypatch, whisper=None):
    c = _client()
    c.get("/api/wa/media/stats")                       # opens the DB and creates the tables
    _wipe()
    vdir = tempfile.mkdtemp()
    monkeypatch.setenv("VOICE_DIR", vdir)
    monkeypatch.setenv("VOICE_MODEL_DIR", tempfile.mkdtemp())
    for k in ("VOICE_MODEL", "VOICE_MAX_PER_RUN", "VOICE_BUDGET_S", "VOICE_MAX_MB"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("WA_INTEL_ENABLED", "1")
    monkeypatch.setitem(sys.modules, "faster_whisper", whisper if whisper is not None else None)
    return c, vdir


def _post_media(c, message_id, jid, name, sender, when, account="1", data=OGG, mimetype="audio/ogg; codecs=opus", seconds=7, **extra):
    fields = {"account": account, "chat_jid": jid, "chat_name": name, "sender": sender, "message_id": message_id,
              "mimetype": mimetype, "duration_seconds": str(seconds), "timestamp": when, "from_me": "0",
              "chat_kind": "group" if jid.endswith("@g.us") else "dm", **extra}
    return c.post("/api/wa/media", data=fields, files={"file": (f"{message_id}.ogg", io.BytesIO(data), "audio/ogg")})


def test_media_endpoint_stores_the_clip_once_and_respects_the_personal_gate(monkeypatch):
    c, vdir = _setup(monkeypatch)
    when = (NOW - timedelta(minutes=5)).isoformat()
    r = _post_media(c, "3EB0AAA111", WASHERY_JID, "Washery Civil Update", "Ravi", when).json()
    assert r["stored"] is True and r["status"] == "pending" and r["path"] == "2026-10-09/3EB0AAA111.ogg"
    assert open(os.path.join(vdir, "2026-10-09", "3EB0AAA111.ogg"), "rb").read() == OGG
    # the same message id again (history replay) is a duplicate, not a second file
    r2 = _post_media(c, "3EB0AAA111", WASHERY_JID, "Washery Civil Update", "Ravi", when).json()
    assert r2["stored"] is False and r2["reason"] == "duplicate" and r2["id"] == r["id"]
    # a personal chat stores nothing — not even the file
    db = sqlite3.connect(os.environ["VEGA_DB_PATH"])
    db.execute("INSERT INTO wa_chats (jid, account, name, kind, classification) VALUES (?,?,?,?,?)",
               (FAMILY_JID, "1", "Family Jokes", "group", "personal"))
    db.commit(); db.close()
    r3 = _post_media(c, "3EB0FAM001", FAMILY_JID, "Family Jokes", "Cousin", when).json()
    assert r3["stored"] is False and r3["reason"] == "personal"
    assert not os.path.exists(os.path.join(vdir, "2026-10-09", "3EB0FAM001.ogg"))
    # guards: no message id, an empty file, a file over the cap
    assert _post_media(c, "", WASHERY_JID, "Washery Civil Update", "Ravi", when).status_code == 400
    assert _post_media(c, "3EB0EMPTY", WASHERY_JID, "Washery Civil Update", "Ravi", when, data=b"").status_code == 400
    monkeypatch.setenv("VOICE_MAX_MB", "1")
    assert _post_media(c, "3EB0BIG", WASHERY_JID, "Washery Civil Update", "Ravi", when, data=b"x" * (1024 * 1024 + 1)).status_code == 413
    assert c.post("/api/wa/media", json={"message_id": "x"}).status_code == 400          # not multipart → 400, never 500
    st = c.get("/api/wa/media/stats").json()
    assert st["counts"] == {"pending": 1, "done": 0, "failed": 0} and st["installed"] is False and st["model"] == "small"
    rec = c.get("/api/wa/media/recent?status=pending").json()
    assert rec["count"] == 1 and rec["items"][0]["message_id"] == "3EB0AAA111" and rec["items"][0]["duration"] == 7.0
    assert rec["items"][0]["bytes"] == len(OGG) and rec["items"][0]["chat_kind"] == "group" and rec["items"][0]["mimetype"].startswith("audio/ogg")
    assert c.get("/api/wa/media/recent?status=nope").status_code == 400


def test_transcription_writes_tagged_text_into_the_message_store_and_heartbeats(monkeypatch):
    built = []
    whisper = fake_whisper({"3EB0AAA111.ogg": "pump band hai, loader 4 ko bhejo", "3EB0BBB222.ogg": "TCS lelo 3500 target 3800",
                            "3EB0CCC333.ogg": ""}, fail={"3EB0DDD444.mp3"}, built=built)        # audio/mpeg → .mp3
    c, vdir = _setup(monkeypatch, whisper)
    t = lambda m: (NOW - timedelta(minutes=m)).isoformat()
    _post_media(c, "3EB0AAA111", WASHERY_JID, "Washery Civil Update", "Ravi", t(30))
    _post_media(c, "3EB0BBB222", MAUSAJI_JID, "Bantu Mausaji", "Bantu Mausaji", t(20), account="2", seconds=12)
    _post_media(c, "3EB0CCC333", WASHERY_JID, "Washery Civil Update", "Sunil", t(10), seconds=2)
    _post_media(c, "3EB0DDD444", WASHERY_JID, "Washery Civil Update", "Ravi", t(5), mimetype="audio/mpeg")
    r = c.post("/api/wa/media/transcribe", json={"now": NOW.isoformat()}).json()
    assert r["installed"] is True and r["model"] == "small" and r["transcribed"] == 3 and r["failed"] == 1 and r["pending"] == 0
    assert r["status"] == "warning" and r["line"] == "voice: 3 transcribed, 0 pending, 1 failed, model small, avg 0s/clip"
    assert built[0] == ("small", {"device": "cpu", "compute_type": "int8", "download_root": os.environ["VOICE_MODEL_DIR"]})
    items = {i["message_id"]: i for i in r["items"]}
    assert items["3EB0AAA111"]["transcript"] == "pump band hai, loader 4 ko bhejo" and items["3EB0AAA111"]["language"] == "hi"
    assert items["3EB0BBB222"]["store_msg_id"] and items["3EB0CCC333"]["transcript"] == "" and items["3EB0CCC333"]["store_msg_id"] is None
    assert items["3EB0DDD444"]["status"] == "failed" and "decode failed" in items["3EB0DDD444"]["error"]
    # the message store: one text row per transcript, tagged, voice=1, same chat/sender/timestamp, dedupe key <id>:voice
    msgs = c.get("/api/whatsapp/messages?limit=50").json()["messages"]
    voice = [m for m in msgs if m["text"].startswith("[voice transcript]")]
    assert len(voice) == 2 and all(m["voice"] == 1 for m in voice)
    by = {m["wa_msg_id"]: m for m in voice}
    assert by["3EB0AAA111:voice"]["text"] == "[voice transcript] pump band hai, loader 4 ko bhejo"
    assert by["3EB0AAA111:voice"]["group_name"] == "Washery Civil Update" and by["3EB0AAA111:voice"]["sender"] == "Ravi"
    assert by["3EB0AAA111:voice"]["jid"] == WASHERY_JID and by["3EB0AAA111:voice"]["chat_kind"] == "group" and by["3EB0AAA111:voice"]["timestamp"] == t(30)
    assert by["3EB0BBB222:voice"]["account"] == "2" and by["3EB0BBB222:voice"]["chat_kind"] == "dm" and by["3EB0BBB222:voice"]["group_name"] == "Bantu Mausaji"
    assert all(m["voice"] == 0 for m in msgs if not m["text"].startswith("[voice transcript]"))
    # the sweep's view of the Mausaji chat sees the transcript like any text (wa_chats upserted through the same gate)
    chats = {ch["jid"]: ch for ch in c.get("/api/wa/chats").json()["chats"]}
    assert chats[MAUSAJI_JID]["name"] == "Bantu Mausaji" and chats[MAUSAJI_JID]["kind"] == "dm"
    # the Morning card: the last transcripts with chat and sender; the run state
    st = c.get("/api/wa/media/stats").json()
    assert st["counts"] == {"pending": 0, "done": 3, "failed": 1} and st["state"]["line"] == r["line"] and st["state"]["transcribed"] == 3
    assert [x["message_id"] for x in st["transcripts"]] == ["3EB0CCC333", "3EB0BBB222", "3EB0AAA111"]
    assert st["transcripts"][2]["chat_name"] == "Washery Civil Update" and st["transcripts"][2]["sender"] == "Ravi"
    assert st["transcripts"][0]["error"] == "no speech detected" and st["transcripts"][1]["transcript"] == "TCS lelo 3500 target 3800"
    # a second run: nothing pending, the zero heartbeat, no model built again
    r2 = c.post("/api/wa/media/transcribe", json={"now": (NOW + timedelta(minutes=10)).isoformat()}).json()
    assert r2["transcribed"] == 0 and r2["line"] == "voice: 0 transcribed, 0 pending, 0 failed, model small, avg 0s/clip" and len(built) == 1
    # a failed row is not retried blindly; a transcript already stored is never duplicated
    assert c.get("/api/wa/media/recent?status=failed").json()["count"] == 1
    assert len([m for m in c.get("/api/whatsapp/messages?limit=50").json()["messages"] if m["text"].startswith("[voice transcript]")]) == 2


def test_limit_and_time_budget_leave_the_rest_pending(monkeypatch):
    whisper = fake_whisper({f"M{i}.ogg": f"clip {i} karo" for i in range(1, 8)})
    c, vdir = _setup(monkeypatch, whisper)
    for i in range(1, 8):
        _post_media(c, f"M{i}", WASHERY_JID, "Washery Civil Update", "Ravi", (NOW - timedelta(minutes=60 - i)).isoformat())
    r = c.post("/api/wa/media/transcribe", json={"now": NOW.isoformat(), "limit": 3}).json()
    assert r["transcribed"] == 3 and r["pending"] == 4 and [i["message_id"] for i in r["items"]] == ["M1", "M2", "M3"]   # oldest first
    assert r["line"] == "voice: 3 transcribed, 4 pending, 0 failed, model small, avg 0s/clip"
    # the clock moves 5 s per reading: the budget (10 s) is spent after the first clip, the rest stay pending
    clock = {"t": 0.0}

    def monotonic():
        clock["t"] += 5.0
        return clock["t"]
    monkeypatch.setattr(mv, "_mono", monotonic)
    r = c.post("/api/wa/media/transcribe", json={"now": NOW.isoformat(), "budget_s": 10}).json()
    assert r["transcribed"] == 1 and r["pending"] == 3 and r["note"] == "time budget 10s reached"
    assert r["line"] == "voice: 1 transcribed, 3 pending, 0 failed, model small, avg 5s/clip · time budget 10s reached"
    monkeypatch.setenv("VOICE_MODEL", "base")
    r = c.post("/api/wa/media/transcribe", json={"now": NOW.isoformat()}).json()
    assert r["model"] == "base" and r["line"] == "voice: 3 transcribed, 0 pending, 0 failed, model base, avg 5s/clip"


def test_not_installed_is_a_warning_line_never_a_crash_and_the_bot_exits_zero(monkeypatch):
    c, vdir = _setup(monkeypatch)                      # faster_whisper = None in sys.modules → ImportError
    _post_media(c, "3EB0AAA111", WASHERY_JID, "Washery Civil Update", "Ravi", NOW.isoformat())
    r = c.post("/api/wa/media/transcribe", json={"now": NOW.isoformat()}).json()
    assert r["installed"] is False and r["status"] == "warning" and r["transcribed"] == 0 and r["pending"] == 1
    assert r["line"] == "voice: faster-whisper not installed — nothing transcribed · 1 pending"
    assert c.get("/api/wa/media/recent?status=pending").json()["count"] == 1      # the clip waits for the install
    hb = []
    monkeypatch.setattr(ag, "heartbeat", lambda bot, cad, status, summary, checks=None: hb.append((bot, cad, status, summary)))

    def fake_api(path, method="GET", body=None, timeout=30):
        assert path == "/api/wa/media/transcribe" and method == "POST" and timeout >= 500
        r = c.post(path, json=body)
        assert r.status_code == 200
        return r.json()
    monkeypatch.setattr(ag, "api", fake_api)
    monkeypatch.setattr(ag, "RUN_ARGS", [])
    assert ag.run_voice(BOT, "none", "hourly", now=NOW) == 0
    assert hb[-1] == ("voice", "hourly", "warning", "voice: faster-whisper not installed — nothing transcribed · 1 pending")
    # a model that fails to load is an error heartbeat with the reason, still exit 0
    bad = types.ModuleType("faster_whisper")

    class WhisperModel:
        def __init__(self, *a, **k):
            raise OSError("no space left on device")
    bad.WhisperModel = WhisperModel
    monkeypatch.setitem(sys.modules, "faster_whisper", bad)
    assert ag.run_voice(BOT, "none", "hourly", now=NOW) == 0
    assert hb[-1][2] == "error" and hb[-1][3] == ("voice: 0 transcribed, 1 pending, 0 failed, model small, avg 0s/clip"
                                                  " · model small failed to load: OSError: no space left on device")
    # installed and quiet: the zero line, clean
    monkeypatch.setitem(sys.modules, "faster_whisper", fake_whisper({"3EB0AAA111.ogg": "theek hai"}))
    assert ag.run_voice(BOT, "none", "hourly", now=NOW) == 0
    assert hb[-1][2] == "clean" and hb[-1][3] == "voice: 1 transcribed, 0 pending, 0 failed, model small, avg 0s/clip"
    assert ag.run_voice(BOT, "none", "hourly", now=NOW + timedelta(minutes=10)) == 0
    assert hb[-1] == ("voice", "hourly", "clean", "voice: 0 transcribed, 0 pending, 0 failed, model small, avg 0s/clip")
    assert ag.CUSTOM_BOTS["voice"] is ag.run_voice


# ── wiring: fleet.yaml, cron, .env.example, Dockerfile, the bridge, the Morning card ──
def test_fleet_cron_env_image_bridge_and_morning_card_wiring():
    fleet = yaml.safe_load(open(os.path.join(ROOT, "fleet.yaml"), encoding="utf-8"))
    bot = next(b for b in fleet["bots"] if b["id"] == "voice")
    assert bot["provider"] == "none" and bot["model"] == "none" and bot["enabled"] is True
    assert bot["cadence"] == "every 10 min 07:00-22:00 IST"
    assert "transcribed" in bot["heartbeat"] and "faster-whisper not installed" in bot["heartbeat"]
    assert set(bot["serves"]) <= {o["id"] for o in yaml.safe_load(open(os.path.join(ROOT, "agenda.yaml"), encoding="utf-8"))["objectives"]}
    assert any("no llm" in r.lower() and "no api" in r.lower() for r in bot["charter"]["rules"])
    doc = open(os.path.join(ROOT, "DEPLOY_HOSTINGER.md"), encoding="utf-8").read()
    block = doc[doc.index("# MDO fleet — one line per bot"):]
    block = block[:block.index("```")]
    lines = [l for l in block.splitlines() if "mdo_agent.py voice" in l]
    assert len(lines) == 3
    assert lines[0].startswith("30-59/10 1 * * *") and lines[1].startswith("*/10 2-15 * * *") and lines[2].startswith("0-30/10 16 * * *")
    env = open(os.path.join(ROOT, ".env.example"), encoding="utf-8").read()
    assert "\nVOICE_MODEL=small\n" in env and env.index("# ── Chief of Staff") < env.index("VOICE_MODEL=")
    assert "faster-whisper" in open(os.path.join(ROOT, "requirements_server.txt"), encoding="utf-8").read()
    if not os.path.exists(os.path.join(ROOT, "Dockerfile")):   # the backend image ships no Dockerfile, bridge or frontend source
        return
    dockerfile = open(os.path.join(ROOT, "Dockerfile"), encoding="utf-8").read()
    assert "ffmpeg" in [l for l in dockerfile.splitlines() if l.startswith("RUN apt-get")][0]
    bridge = open(os.path.join(ROOT, "whatsapp_bridge", "index.js"), encoding="utf-8").read()
    assert '"/api/wa/media"' in bridge and "audioMessage" in bridge and "duration_seconds" in bridge and "multipart/form-data" in bridge
    pkg = json.load(open(os.path.join(ROOT, "whatsapp_bridge", "package.json"), encoding="utf-8"))
    assert tuple(int(x) for x in pkg["version"].split(".")) >= (2, 2, 0)
    page_path = os.path.join(ROOT, "mdo-app", "app", "morning", "page.tsx")
    if not os.path.exists(page_path):            # the backend image ships no frontend source; checked in the repo run
        return
    page = open(page_path, encoding="utf-8").read()
    assert "<VoiceCard />" in page and "function VoiceCard()" in page and "api.voice.stats()" in page
    assert "q.isLoading && <div" in page.split("function VoiceCard()")[1]      # loading state before any table (Directive 17)
    api_ts = open(os.path.join(ROOT, "mdo-app", "lib", "api.ts"), encoding="utf-8").read()
    assert "/api/wa/media/stats" in api_ts and "/api/wa/media/recent?" in api_ts
