"""Merge Discord settings into ~/.config/caravan/bot.env on the bot machine.

deploy/configure-bot.sh pipes this file to `python3 -` over ssh, after lines
that define UPDATES (key -> value, empty = keep) and EXAMPLE_B64 (the local
deploy/bot.env.example). Values travel on stdin, never on a command line.
Keys the template has gained since bot.env was made are added with their
comments, so the file keeps up with new settings. Standard library only.
"""

import base64
import os
import pathlib
import tempfile


def env_key(line: str) -> str | None:
    text = line.strip()
    if not text or text.startswith("#") or "=" not in text:
        return None
    return text.split("=", 1)[0].strip()


def merge(lines: list[str], example: list[str], updates: dict[str, str]) -> tuple[list[str], list[str], list[str]]:
    """Return (new lines, keys added from the template, keys set from updates)."""
    out = list(lines)
    present = {env_key(line) for line in out}
    added: list[str] = []
    comments: list[str] = []
    for line in example:
        key = env_key(line)
        if key is None:
            comments = comments + [line] if line.lstrip().startswith("#") else []
            continue
        if key not in present:
            out += comments + [line]
            added.append(key)
        comments = []
    changed: list[str] = []
    for key, value in updates.items():
        if not value:
            continue
        for i, line in enumerate(out):
            if env_key(line) == key:
                out[i] = f"{key}={value}"
                break
        else:
            out.append(f"{key}={value}")
        changed.append(key)
    return out, added, changed


def has_value(lines: list[str], key: str) -> bool:
    return any(env_key(line) == key and line.split("=", 1)[1].strip() for line in lines)


def main(updates: dict[str, str], example_b64: str) -> None:
    path = pathlib.Path.home() / ".config/caravan/bot.env"
    example = base64.b64decode(example_b64).decode().splitlines()
    lines = path.read_text().splitlines() if path.exists() else []
    out, added, changed = merge(lines, example, updates)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".bot.env.")  # created 0600
    with os.fdopen(fd, "w") as f:
        f.write("\n".join(out) + "\n")
    os.replace(tmp, path)
    print(f"bot.env: set {', '.join(changed) or 'nothing'}" + (f"; added {', '.join(added)}" if added else ""))
    print("TOKEN_SET" if has_value(out, "DISCORD_TOKEN") else "TOKEN_MISSING")


if __name__ == "__main__" and "UPDATES" in globals():
    main(globals()["UPDATES"], globals()["EXAMPLE_B64"])
