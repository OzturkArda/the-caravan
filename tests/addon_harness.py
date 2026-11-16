"""Runs copies of the addon in embedded Lua 5.1 with a fake WoW client."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from lupa import lua51

ROOT = Path(__file__).resolve().parents[1]
ADDON_DIR = ROOT / "addon" / "TheCaravan"
STUB = Path(__file__).with_name("wow_stub.lua")


def _xml_files(xml_path: Path) -> list[Path]:
    files = []
    for kind, name in re.findall(r'<(Script|Include) file="([^"]+)"', xml_path.read_text()):
        path = xml_path.parent / name.replace("\\", "/")
        files.extend(_xml_files(path) if kind == "Include" else [path])
    return files


def load_order() -> list[Path]:
    """Lua files in the order the game loads them, read from the TOC and XML."""
    files: list[Path] = []
    for line in (ADDON_DIR / "TheCaravan.toc").read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        path = ADDON_DIR / line.replace("\\", "/")
        files.extend(_xml_files(path) if path.suffix == ".xml" else [path])
    return files


def to_py(value: Any) -> Any:
    if lua51.lua_type(value) != "table":
        return value
    d = {k: to_py(v) for k, v in value.items()}
    if d and all(isinstance(k, int) for k in d) and sorted(d) == list(range(1, len(d) + 1)):
        return [d[k] for k in range(1, len(d) + 1)]
    return d


class Client:
    def __init__(
        self, name: str, realm: str = "Ironvale", db: Any = None, schedule: Any = None, sv_text: str | None = None
    ) -> None:
        self.lua = lua51.LuaRuntime(unpack_returned_tuples=True)
        self.g = self.lua.globals()
        self.lua.execute(STUB.read_text())
        self.W = self.g.WOW
        self.W.player.name = name
        self.W.realm = realm
        self.full_name = f"{name}-{realm}"
        if db is not None:  # a Lua table from this runtime, or plain Python data (e.g. another client's, via to_py)
            self.g.TheCaravanDB = self.lua.table_from(db, recursive=True) if isinstance(db, dict) else db
        if schedule is not None:
            self.g.TheCaravanSchedule = self.lua.table_from(schedule, recursive=True)
        ns = self.lua.table()
        for path in load_order():
            self.W.loadFile(str(path), "TheCaravan", ns)
        self.addon = ns.Caravan
        if sv_text is not None:  # the client runs the SavedVariables file after loading the addon
            self.lua.execute(sv_text)
        self.fire("ADDON_LOADED", "TheCaravan")
        self.W.loggedIn = True
        self.fire("PLAYER_LOGIN")
        self.fire("PLAYER_ENTERING_WORLD", True, False)

    def fire(self, event: str, *args: Any) -> None:
        self.W.fire(event, *args)

    def slash(self, text: str) -> None:
        self.g.SlashCmdList["ACECONSOLE_CARAVAN"](text)

    def call(self, method: str, *args: Any) -> Any:
        return getattr(self.addon, method)(self.addon, *args)

    def set_group(self, *others: "Client") -> None:
        group = self.lua.table()
        for i, other in enumerate(others, 1):
            realm = None if other.W.realm == self.W.realm else other.W.realm
            group[i] = self.lua.table_from({"name": other.W.player.name, "realm": realm})
        self.W.group = group
        self.fire("GROUP_ROSTER_UPDATE")

    def take_outbox(self) -> list[Any]:
        out = self.W.outbox
        msgs = [out[i] for i in range(1, len(out) + 1)]
        self.W.outbox = self.lua.table()
        return msgs

    def member(self, full_name: str) -> Any:
        return to_py(self.g.TheCaravanDB.members[full_name])

    @property
    def prints(self) -> list[str]:
        return list(to_py(self.W.prints) or [])

    @property
    def errors(self) -> list[str]:
        return list(to_py(self.W.errors) or [])


def run(clients: list[Client], seconds: float) -> int:
    """Advance every client's clock, delivering group messages between them."""
    delivered = 0
    for _ in range(int(seconds * 10)):
        for c in clients:
            c.W.advance(0.1)
        for sender in clients:
            for msg in sender.take_outbox():
                for receiver in clients:
                    if receiver is not sender:
                        receiver.fire("CHAT_MSG_ADDON", msg.prefix, msg.text, msg.channel, sender.full_name)
                        delivered += 1
    return delivered
