"""Read and write the Lua literals that WoW stores in SavedVariables files.

Text is handled as latin-1 so every byte maps to one character: string
contents are re-decoded as UTF-8 when parsed, and files written back keep
every byte outside the replaced statement unchanged.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

_NUMBER = re.compile(r"-?(?:0[xX][0-9a-fA-F]+|(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)")
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_ESCAPES = {
    "n": "\n", "t": "\t", "r": "\r", "a": "\a", "b": "\b", "f": "\f", "v": "\v",
    "\\": "\\", '"': '"', "'": "'", "\n": "\n",
}


class LuaParseError(ValueError):
    pass


@dataclass(frozen=True)
class Statement:
    name: str
    start: int
    end: int
    value: Any


class _Parser:
    def __init__(self, text: str) -> None:
        self.s = text
        self.i = 0
        self.n = len(text)

    def error(self, msg: str) -> LuaParseError:
        line = self.s.count("\n", 0, self.i) + 1
        return LuaParseError(f"{msg} (line {line})")

    def skip(self) -> None:
        s = self.s
        while self.i < self.n:
            c = s[self.i]
            if c in " \t\r\n":
                self.i += 1
            elif s.startswith("--", self.i):
                nl = s.find("\n", self.i)
                self.i = self.n if nl < 0 else nl + 1
            else:
                break

    def statements(self) -> list[Statement]:
        out = []
        self.skip()
        while self.i < self.n:
            start = self.i
            m = _NAME.match(self.s, self.i)
            if not m:
                raise self.error("expected a variable name")
            self.i = m.end()
            self.skip()
            if not self.s.startswith("=", self.i):
                raise self.error(f"expected '=' after {m.group()}")
            self.i += 1
            self.skip()
            value = self.value()
            out.append(Statement(m.group(), start, self.i, value))
            self.skip()
            if self.s.startswith(";", self.i):
                self.i += 1
                self.skip()
        return out

    def value(self) -> Any:
        if self.i >= self.n:
            raise self.error("unexpected end of file")
        c = self.s[self.i]
        if c == "{":
            return self.table()
        if c in "\"'":
            return self.string()
        m = _NUMBER.match(self.s, self.i)
        if m:
            self.i = m.end()
            return _to_number(m.group())
        m = _NAME.match(self.s, self.i)
        if m:
            word = m.group()
            self.i = m.end()
            if word == "true":
                return True
            if word == "false":
                return False
            if word == "nil":
                return None
            if word in ("inf", "nan"):
                return math.inf if word == "inf" else math.nan
            raise self.error(f"unexpected word {word!r}")
        raise self.error(f"unexpected character {c!r}")

    def string(self) -> str:
        quote = self.s[self.i]
        self.i += 1
        parts: list[str] = []
        s = self.s
        while True:
            if self.i >= self.n:
                raise self.error("unterminated string")
            c = s[self.i]
            if c == quote:
                self.i += 1
                break
            if c == "\\":
                nxt = s[self.i + 1 : self.i + 2]
                if nxt and nxt in "0123456789":
                    digits = re.match(r"[0-9]{1,3}", s[self.i + 1 : self.i + 4])
                    assert digits is not None
                    parts.append(chr(int(digits.group()) & 0xFF))
                    self.i += 1 + len(digits.group())
                elif nxt in _ESCAPES:
                    parts.append(_ESCAPES[nxt])
                    self.i += 2
                else:
                    raise self.error(f"bad escape \\{nxt}")
            elif c == "\n":
                raise self.error("newline in string")
            else:
                parts.append(c)
                self.i += 1
        return "".join(parts).encode("latin-1").decode("utf-8", "replace")

    def table(self) -> Any:
        self.i += 1  # {
        result: dict[Any, Any] = {}
        index = 1
        while True:
            self.skip()
            if self.i >= self.n:
                raise self.error("unterminated table")
            if self.s[self.i] == "}":
                self.i += 1
                break
            if self.s[self.i] == "[":
                self.i += 1
                self.skip()
                key = self.value()
                self.skip()
                if not self.s.startswith("]", self.i):
                    raise self.error("expected ']'")
                self.i += 1
                self._expect_equals()
                result[key] = self.value()
            else:
                m = _NAME.match(self.s, self.i)
                after = self.i
                if m:
                    after = m.end()
                    while after < self.n and self.s[after] in " \t\r\n":
                        after += 1
                if m and self.s.startswith("=", after) and not self.s.startswith("==", after):
                    self.i = after + 1
                    self.skip()
                    result[m.group()] = self.value()
                else:
                    result[index] = self.value()
                    index += 1
            self.skip()
            if self.i < self.n and self.s[self.i] in ",;":
                self.i += 1
        return _maybe_list(result)

    def _expect_equals(self) -> None:
        self.skip()
        if not self.s.startswith("=", self.i):
            raise self.error("expected '='")
        self.i += 1
        self.skip()


def _to_number(text: str) -> int | float:
    neg = text.startswith("-")
    body = text[1:] if neg else text
    if body[:2] in ("0x", "0X"):
        value: int | float = int(body, 16)
    elif re.fullmatch(r"\d+", body):
        value = int(body)
    else:
        value = float(body)
    return -value if neg else value


def _maybe_list(table: dict[Any, Any]) -> Any:
    """Return a list when the keys are exactly 1..n, otherwise the dict."""
    if table and all(isinstance(k, int) and not isinstance(k, bool) for k in table):
        if sorted(table) == list(range(1, len(table) + 1)):
            return [table[k] for k in range(1, len(table) + 1)]
    return table


def as_list(value: Any) -> list[Any]:
    """Normalise a parsed Lua table that should be an array (empty tables parse as {})."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        int_keys = sorted(k for k in value if isinstance(k, int) and not isinstance(k, bool))
        return [value[k] for k in int_keys]
    return []


def parse_statements(text: str) -> list[Statement]:
    return _Parser(text).statements()


def parse_savedvariables(text: str) -> dict[str, Any]:
    return {st.name: st.value for st in parse_statements(text)}


def read_savedvariables(path) -> dict[str, Any]:
    with open(path, encoding="latin-1", newline="") as fh:
        return parse_savedvariables(fh.read())


def _quote(s: str) -> str:
    out = ['"']
    for byte in s.encode("utf-8"):
        ch = chr(byte)
        if ch == '"':
            out.append('\\"')
        elif ch == "\\":
            out.append("\\\\")
        elif ch == "\n":
            out.append("\\n")
        elif byte < 32 or byte == 127:
            out.append(f"\\{byte:03d}")
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def _key(k: Any) -> str:
    if isinstance(k, bool):
        raise TypeError("boolean table keys are not supported")
    if isinstance(k, int):
        return f"[{k}]"
    if isinstance(k, str):
        return f"[{_quote(k)}]"
    raise TypeError(f"unsupported key type {type(k).__name__}")


def to_lua(value: Any, indent: int = 0) -> str:
    """Serialise a JSON-like value as a Lua literal (latin-1 text, UTF-8 bytes)."""
    pad = "\t" * (indent + 1)
    if value is None:
        return "nil"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            raise ValueError("NaN and infinity can't be written to SavedVariables")
        return repr(value)
    if isinstance(value, str):
        return _quote(value)
    if isinstance(value, (list, tuple)):
        if not value:
            return "{}"
        items = "".join(f"{pad}{to_lua(v, indent + 1)}, -- [{i}]\n" for i, v in enumerate(value, 1))
        return "{\n" + items + "\t" * indent + "}"
    if isinstance(value, dict):
        if not value:
            return "{}"
        items = "".join(f"{pad}{_key(k)} = {to_lua(v, indent + 1)},\n" for k, v in value.items())
        return "{\n" + items + "\t" * indent + "}"
    raise TypeError(f"unsupported value type {type(value).__name__}")


def replace_statement(text: str, name: str, value: Any) -> str:
    """Return text with the top-level `name = ...` statement set to value.

    Every other byte of the file stays as it was. The statement is appended
    when it isn't present yet.
    """
    rendered = f"{name} = {to_lua(value)}"
    for st in parse_statements(text):
        if st.name == name:
            return text[: st.start] + rendered + text[st.end :]
    sep = "" if not text or text.endswith("\n") else "\n"
    return f"{text}{sep}{rendered}\n"
