import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from caravan.luadata import parse_savedvariables
from caravan.sync.__main__ import load_env_file
from caravan.sync.service import ApiClient, ApiError, SyncService, write_schedule
from caravan.sync.wow import find_savedvariables

SV = '\nTheCaravanDB = {\n["lastCharacter"] = "Roland-Ironvale",\n["members"] = {\n["Roland-Ironvale"] = {\n["level"] = 14,\n},\n},\n}\n'
SCHEDULE = {"version": 1, "generated_at": 1, "sessions": [{"id": 1, "title": "Run", "start": 2, "duration": 60,
                                                          "going": ["Arda"], "late": [], "out": []}]}


class FakeApi:
    def __init__(self):
        self.snapshots = []
        self.schedule = SCHEDULE
        self.fail = False
        self.schedule_calls = 0

    def post_snapshot(self, snap):
        if self.fail:
            raise ApiError("offline")
        self.snapshots.append(snap)

    def get_schedule(self):
        self.schedule_calls += 1
        if self.fail:
            raise ApiError("offline")
        return self.schedule


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


@pytest.fixture
def sv_file(tmp_path):
    path = tmp_path / "SavedVariables" / "TheCaravan.lua"
    path.parent.mkdir()
    path.write_text(SV, encoding="latin-1")
    return path


def touch(path, delta):
    st = path.stat()
    os.utime(path, (st.st_atime, st.st_mtime + delta))


def make(sv_file, running):
    api, clock = FakeApi(), Clock()
    state = {"running": running}
    svc = SyncService(sv_file, api, lambda: state["running"], schedule_every=300, clock=clock)
    return svc, api, state, clock


def test_uploads_snapshot_once_per_file_change(sv_file):
    svc, api, _, _ = make(sv_file, running=True)
    svc.tick()
    svc.tick()
    assert len(api.snapshots) == 1
    assert api.snapshots[0]["members"]["Roland-Ironvale"]["level"] == 14
    touch(sv_file, 5)
    svc.tick()
    assert len(api.snapshots) == 2


def test_failed_upload_is_retried_after_a_backoff(sv_file):
    svc, api, _, clock = make(sv_file, running=True)
    api.fail = True
    svc.tick()
    api.fail = False
    svc.tick()
    assert api.snapshots == []
    clock.t += 61
    svc.tick()
    assert len(api.snapshots) == 1


def test_schedule_retried_after_failed_fetch_when_game_closes(sv_file):
    svc, api, state, clock = make(sv_file, running=True)
    svc.tick()
    state["running"] = False
    api.fail = True
    svc.tick()
    api.fail = False
    clock.t += 61
    svc.tick()
    sv = parse_savedvariables(sv_file.read_text(encoding="latin-1"))
    assert sv["TheCaravanSchedule"]["sessions"][0]["title"] == "Run"


def test_never_writes_schedule_while_game_runs(sv_file):
    svc, api, _, _ = make(sv_file, running=True)
    before = sv_file.read_bytes()
    svc.tick()
    assert sv_file.read_bytes() == before and api.schedule_calls == 0


def test_writes_schedule_when_game_closes_without_reuploading(sv_file):
    svc, api, state, _ = make(sv_file, running=True)
    svc.tick()
    state["running"] = False
    touch(sv_file, 5)  # the client saved on exit
    svc.tick()
    sv = parse_savedvariables(sv_file.read_text(encoding="latin-1"))
    assert sv["TheCaravanSchedule"]["sessions"][0]["title"] == "Run"
    assert sv["TheCaravanDB"]["members"]["Roland-Ironvale"]["level"] == 14
    assert len(api.snapshots) == 2
    svc.tick()
    assert len(api.snapshots) == 2
    assert sv_file.with_name("TheCaravan.lua.bak").exists()


def test_schedule_rechecked_on_interval_and_unchanged_schedule_not_rewritten(sv_file):
    svc, api, _, clock = make(sv_file, running=False)
    svc.tick()
    mtime = sv_file.stat().st_mtime
    svc.tick()
    assert api.schedule_calls == 1
    clock.t += 301
    svc.tick()
    assert api.schedule_calls == 2 and sv_file.stat().st_mtime == mtime


def test_schedule_written_even_before_addon_saved_anything(tmp_path):
    path = tmp_path / "SavedVariables" / "TheCaravan.lua"
    path.parent.mkdir()
    svc = SyncService(path, FakeApi(), lambda: False)
    assert svc.download_schedule() is True
    assert parse_savedvariables(path.read_text(encoding="latin-1"))["TheCaravanSchedule"]["version"] == 1


def test_unreadable_file_is_left_alone(sv_file):
    sv_file.write_text("TheCaravanDB = {", encoding="latin-1")
    svc, api, _, _ = make(sv_file, running=False)
    svc.tick()
    assert api.snapshots == [] and sv_file.read_text(encoding="latin-1") == "TheCaravanDB = {"


def test_write_schedule_replaces_existing(sv_file):
    write_schedule(sv_file, SCHEDULE)
    write_schedule(sv_file, {"sessions": []})
    text = sv_file.read_text(encoding="latin-1")
    assert text.count("TheCaravanSchedule") == 1


def test_find_savedvariables(tmp_path):
    root = tmp_path / "_forever_"
    (root / "WTF" / "Account" / "SavedVariables").mkdir(parents=True)
    with pytest.raises(FileNotFoundError, match="expected one account"):
        find_savedvariables(root)
    (root / "WTF" / "Account" / "123#1").mkdir()
    assert find_savedvariables(root) == root / "WTF" / "Account" / "123#1" / "SavedVariables" / "TheCaravan.lua"
    (root / "WTF" / "Account" / "456#1").mkdir()
    with pytest.raises(FileNotFoundError):
        find_savedvariables(root)
    assert find_savedvariables(root, "456#1").parent.parent.name == "456#1"
    with pytest.raises(FileNotFoundError):
        find_savedvariables(tmp_path / "missing")


def test_load_env_file(tmp_path):
    path = tmp_path / "sync.env"
    path.write_text('# comment\nCARAVAN_API_URL="http://bot.lan:8787"\nCARAVAN_API_TOKEN=abc\n\n')
    assert load_env_file(path) == {"CARAVAN_API_URL": "http://bot.lan:8787", "CARAVAN_API_TOKEN": "abc"}
    assert load_env_file(tmp_path / "none") == {}


def test_api_client_against_a_real_server():
    seen = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            seen["auth"] = self.headers["Authorization"]
            self._reply(SCHEDULE)

        def do_POST(self):
            seen["body"] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            self._reply({"stored": 1})

        def _reply(self, obj):
            body = json.dumps(obj).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        client = ApiClient(f"http://127.0.0.1:{server.server_port}/", "tok")
        assert client.get_schedule() == SCHEDULE and seen["auth"] == "Bearer tok"
        assert client.post_snapshot({"a": 1}) == {"stored": 1} and seen["body"] == {"a": 1}
    finally:
        server.shutdown()
    with pytest.raises(ApiError):
        ApiClient("http://127.0.0.1:1", "tok", timeout=1).get_schedule()
