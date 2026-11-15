"""Moves data between the addon's SavedVariables file and the bot.

Upload: when the file changes (logout, /reload, exit), post a snapshot.
Download: fetch the schedule and write it into the file, but only while the
game is closed, because the client rewrites the file from memory on exit.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..luadata import LuaParseError, parse_savedvariables, replace_statement
from ..schema import SCHEDULE_VAR, schedule_signature, snapshot_from_savedvariables

log = logging.getLogger(__name__)


class ApiError(Exception):
    pass


class ApiClient:
    def __init__(self, base_url: str, token: str, timeout: float = 10) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            self.base_url + path, data=data, method=method,
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read())
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise ApiError(f"{method} {path} failed: {exc}") from exc

    def post_snapshot(self, snapshot: dict[str, Any]) -> Any:
        return self._request("POST", "/snapshot", snapshot)

    def get_schedule(self) -> dict[str, Any]:
        return self._request("GET", "/schedule")


def _read(path: Path) -> str:
    with open(path, encoding="latin-1", newline="") as fh:
        return fh.read()


def write_schedule(path: Path, schedule: dict[str, Any]) -> None:
    """Set the schedule statement in the SavedVariables file, leaving the rest untouched."""
    text = _read(path) if path.exists() else ""
    new_text = replace_statement(text, SCHEDULE_VAR, schedule)
    if path.exists():
        shutil.copy2(path, path.with_name(path.name + ".bak"))
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="latin-1", newline="") as fh:
        fh.write(new_text)
    os.replace(tmp, path)


class SyncService:
    def __init__(
        self,
        sv_path: Path,
        api: ApiClient,
        is_running: Callable[[], bool],
        schedule_every: float = 300,
        retry_delay: float = 60,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.sv_path = sv_path
        self.api = api
        self.is_running = is_running
        self.schedule_every = schedule_every
        self.retry_delay = retry_delay
        self.clock = clock
        self.uploaded_mtime: float | None = None
        self.last_schedule_check = float("-inf")
        self.schedule_due = False
        self.retry_at = float("-inf")
        self.was_running: bool | None = None

    def tick(self) -> None:
        running = self.is_running()
        if self.was_running and not running:
            self.schedule_due = True
        self.was_running = running
        self.upload_if_changed()
        if not running and (self.schedule_due or self.clock() - self.last_schedule_check >= self.schedule_every):
            self.download_schedule()

    def _api_available(self) -> bool:
        return self.clock() >= self.retry_at

    def _api_failed(self, what: str, exc: ApiError) -> None:
        log.warning("%s failed, retrying in %ds: %s", what, self.retry_delay, exc)
        self.retry_at = self.clock() + self.retry_delay

    def upload_if_changed(self) -> bool:
        try:
            mtime = self.sv_path.stat().st_mtime
        except FileNotFoundError:
            return False
        if mtime == self.uploaded_mtime:
            return False
        try:
            sv = parse_savedvariables(_read(self.sv_path))
            snapshot = snapshot_from_savedvariables(sv, int(mtime))
        except (LuaParseError, ValueError) as exc:
            log.warning("skipping unreadable SavedVariables: %s", exc)
            self.uploaded_mtime = mtime
            return False
        if not self._api_available():
            return False
        try:
            self.api.post_snapshot(snapshot)
        except ApiError as exc:
            self._api_failed("snapshot upload", exc)
            return False
        self.uploaded_mtime = mtime
        log.info("uploaded snapshot with %d members", len(snapshot["members"]))
        return True

    def download_schedule(self) -> bool:
        """Fetch the schedule and write it if it changed. Call only while the game is closed."""
        if not self._api_available():
            return False
        try:
            schedule = self.api.get_schedule()
        except ApiError as exc:
            self._api_failed("schedule download", exc)
            return False
        self.last_schedule_check = self.clock()
        self.schedule_due = False
        if not self.sv_path.parent.is_dir():
            log.warning("SavedVariables folder %s is missing", self.sv_path.parent)
            return False
        current = None
        if self.sv_path.exists():
            try:
                current = parse_savedvariables(_read(self.sv_path)).get(SCHEDULE_VAR)
            except LuaParseError as exc:
                log.warning("not touching unreadable SavedVariables: %s", exc)
                return False
        if current is not None and schedule_signature(current) == schedule_signature(schedule):
            return False
        before = self.sv_path.stat().st_mtime if self.sv_path.exists() else None
        write_schedule(self.sv_path, schedule)
        if before is None or before == self.uploaded_mtime:
            # Only the schedule changed, so the member data is already uploaded.
            self.uploaded_mtime = self.sv_path.stat().st_mtime
        log.info("wrote %d sessions into %s", len(schedule.get("sessions", [])), self.sv_path.name)
        return True
