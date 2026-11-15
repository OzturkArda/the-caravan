"""deploy/merge_bot_env.py, which configure-bot.sh runs on the bot machine."""

import base64
import importlib.util
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "deploy" / "merge_bot_env.py"
_spec = importlib.util.spec_from_file_location("merge_bot_env", SCRIPT)
assert _spec and _spec.loader
merge_bot_env = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(merge_bot_env)
merge, has_value = merge_bot_env.merge, merge_bot_env.has_value

EXAMPLE = [
    "# The token",
    "DISCORD_TOKEN=",
    "DISCORD_GUILD_ID=",
    "CARAVAN_API_TOKEN=",
    "# Levels above the rest",
    "# (0 = off)",
    "LEVEL_GAP=3",
    "",
    "ALERTS_CHANNEL_ID=",
]


def test_sets_values_and_keeps_other_lines():
    lines = ["# The token", "DISCORD_TOKEN=", "DISCORD_GUILD_ID=", "CARAVAN_API_TOKEN=secret",
             "LEVEL_GAP=5", "ALERTS_CHANNEL_ID="]
    out, added, changed = merge(lines, EXAMPLE, {"DISCORD_TOKEN": "a.b.c", "DISCORD_GUILD_ID": "123"})
    assert out == ["# The token", "DISCORD_TOKEN=a.b.c", "DISCORD_GUILD_ID=123", "CARAVAN_API_TOKEN=secret",
                   "LEVEL_GAP=5", "ALERTS_CHANNEL_ID="]
    assert added == [] and changed == ["DISCORD_TOKEN", "DISCORD_GUILD_ID"]


def test_empty_update_keeps_current_value():
    out, _, changed = merge(["DISCORD_TOKEN=old"], ["DISCORD_TOKEN="], {"DISCORD_TOKEN": ""})
    assert out == ["DISCORD_TOKEN=old"] and changed == []


def test_adds_template_keys_with_their_comments():
    lines = ["DISCORD_TOKEN=", "DISCORD_GUILD_ID=", "CARAVAN_API_TOKEN=x"]
    out, added, _ = merge(lines, EXAMPLE, {})
    assert added == ["LEVEL_GAP", "ALERTS_CHANNEL_ID"]
    assert out[3:] == ["# Levels above the rest", "# (0 = off)", "LEVEL_GAP=3", "ALERTS_CHANNEL_ID="]


def test_missing_file_becomes_the_template_plus_updates():
    out, added, _ = merge([], EXAMPLE, {"SESSIONS_CHANNEL_ID": "42"})
    assert added == ["DISCORD_TOKEN", "DISCORD_GUILD_ID", "CARAVAN_API_TOKEN", "LEVEL_GAP", "ALERTS_CHANNEL_ID"]
    assert out[-1] == "SESSIONS_CHANNEL_ID=42" and "# The token" in out


def test_has_value():
    assert has_value(["DISCORD_TOKEN=a.b.c"], "DISCORD_TOKEN")
    assert not has_value(["DISCORD_TOKEN=", "# DISCORD_TOKEN=x"], "DISCORD_TOKEN")


def test_piped_run_writes_file_without_exposing_values(tmp_path):
    """Runs the file the way configure-bot.sh does: prefix lines plus the script on stdin."""
    example = "# The token\nDISCORD_TOKEN=\nLEVEL_GAP=3\n"
    (tmp_path / ".config/caravan").mkdir(parents=True)
    (tmp_path / ".config/caravan/bot.env").write_text("DISCORD_TOKEN=\nCARAVAN_API_TOKEN=keep\n")
    program = (
        'UPDATES = {"DISCORD_TOKEN": "aa.bb.cc", "DISCORD_GUILD_ID": "", "SESSIONS_CHANNEL_ID": ""}\n'
        f'EXAMPLE_B64 = "{base64.b64encode(example.encode()).decode()}"\n' + SCRIPT.read_text()
    )
    run = subprocess.run([sys.executable, "-"], input=program, capture_output=True, text=True, check=True,
                         env={"HOME": str(tmp_path), "PATH": "/usr/bin:/bin"})
    assert run.stdout.splitlines() == ["bot.env: set DISCORD_TOKEN; added LEVEL_GAP", "TOKEN_SET"]
    path = tmp_path / ".config/caravan/bot.env"
    assert path.read_text() == "DISCORD_TOKEN=aa.bb.cc\nCARAVAN_API_TOKEN=keep\nLEVEL_GAP=3\n"
    assert path.stat().st_mode & 0o777 == 0o600
    assert "aa.bb.cc" not in run.stdout
