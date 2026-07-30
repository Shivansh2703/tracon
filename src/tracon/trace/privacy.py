"""Payload stripping for exported traces: timing and structure survive, content doesn't.

Sealed-access posture. Nothing a human typed or a tool returned is ever emitted —
only types, shapes, lengths, ids, and numbers. Identifying strings that must stay
join-able across sessions (paths, branch names, project dirs) are replaced with keyed
tokens: equal inputs map to equal tokens, and the key lives outside the export so the
tokens are not reversible from the artifact alone.
"""

from __future__ import annotations

import hashlib
import os
import secrets
from pathlib import Path

_SALT_ENV = "TRACON_SALT_FILE"
_DEFAULT_SALT_PATH = "~/.config/tracon/salt"
_SALT_BYTES = 32
_MIN_SALT_BYTES = 16


def _salt_path() -> Path:
    return Path(os.environ.get(_SALT_ENV, _DEFAULT_SALT_PATH)).expanduser()


def load_or_create_salt() -> bytes:
    """Machine-local tokenization key. Created once, never exported: tokens stay
    stable across export runs (joins work) without being dictionary-attackable
    from the trace files alone."""
    path = _salt_path()
    if path.exists():
        data = path.read_bytes().strip()
        if len(data) >= _MIN_SALT_BYTES:
            return data
    path.parent.mkdir(parents=True, exist_ok=True)
    salt = secrets.token_hex(_SALT_BYTES).encode()
    path.write_bytes(salt)
    path.chmod(0o600)
    return salt


class Tokenizer:
    """Keyed, cached string tokenization: ``t_<12 hex>``."""

    def __init__(self, salt: bytes | None = None) -> None:
        self._salt = salt if salt is not None else load_or_create_salt()
        self._cache: dict[str, str] = {}

    def token(self, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        cached = self._cache.get(value)
        if cached is None:
            digest = hashlib.blake2b(value.encode(), key=self._salt, digest_size=6)
            cached = self._cache[value] = f"t_{digest.hexdigest()}"
        return cached


def _type_code(value: object) -> str:
    # bool before int: bool is an int subclass
    if isinstance(value, bool):
        return "b"
    if isinstance(value, str):
        return f"s{len(value)}"
    if isinstance(value, int):
        return "i"
    if isinstance(value, float):
        return "f"
    if value is None:
        return "n"
    if isinstance(value, list):
        return f"a{len(value)}"
    if isinstance(value, dict):
        return f"o{len(value)}"
    return "?"


def args_shape(args: object) -> str:
    """Depth-1 structural fingerprint of a tool_use input — key names, value types,
    and sizes; never values. ``{"command": "ls -la", "description": "x"}`` →
    ``command:s6,description:s1``."""
    if not isinstance(args, dict):
        return _type_code(args)
    items = sorted((str(key), _type_code(value)) for key, value in args.items())
    return ",".join(f"{key}:{code}" for key, code in items)


def content_chars(content: object) -> int:
    """Char length of a message/tool_result content field (string, or list of
    blocks whose text-ish fields count), without retaining any of it."""
    if isinstance(content, str):
        return len(content)
    if isinstance(content, list):
        total = 0
        for block in content:
            if isinstance(block, str):
                total += len(block)
            elif isinstance(block, dict):
                for field in ("text", "thinking", "content"):
                    value = block.get(field)
                    if isinstance(value, str):
                        total += len(value)
        return total
    return 0
