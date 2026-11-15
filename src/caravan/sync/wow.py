"""Locating the Forever client's files and telling whether the game is running."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from ..schema import SV_FILENAME

MAC_ROOT = Path("/Applications/World of Warcraft/_forever_")
WINDOWS_ROOT = Path(r"C:\Program Files (x86)\World of Warcraft\_forever_")


def default_root() -> Path:
    return WINDOWS_ROOT if sys.platform == "win32" else MAC_ROOT


def find_savedvariables(root: Path, account: str | None = None) -> Path:
    """Path of the addon's account-wide SavedVariables file.

    The file may not exist yet (the addon writes it on first logout), but the
    account folder must. With several accounts, pass `account` (the folder
    name under WTF/Account).
    """
    accounts_dir = root / "WTF" / "Account"
    if not accounts_dir.is_dir():
        raise FileNotFoundError(f"no WTF/Account folder under {root}; log in once first")
    accounts = sorted(p for p in accounts_dir.iterdir() if p.is_dir() and p.name != "SavedVariables")
    if account:
        accounts = [p for p in accounts if p.name == account]
        if not accounts:
            raise FileNotFoundError(f"account folder {account!r} not found in {accounts_dir}")
    if len(accounts) != 1:
        names = ", ".join(p.name for p in accounts) or "none"
        raise FileNotFoundError(f"expected one account folder, found: {names}; set CARAVAN_WOW_ACCOUNT")
    return accounts[0] / "SavedVariables" / SV_FILENAME


def wow_is_running() -> bool:
    """True while any WoW game client runs (the launcher alone doesn't count)."""
    if sys.platform == "win32":
        out = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True).stdout.lower()
        return any(name in out for name in ('"wow.exe"', '"wowclassic.exe"', '"wowforever.exe"'))
    result = subprocess.run(
        ["pgrep", "-f", "World of Warcraft.app/Contents/MacOS/"], capture_output=True, text=True
    )
    return result.returncode == 0
