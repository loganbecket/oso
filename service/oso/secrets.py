"""Secrets live in the operating system's credential store: Windows Credential Manager, the macOS Keychain, or the Linux Secret Service.

Windows keeps at most 2560 bytes per entry, two bytes per character, so a long value (the Canvas sign-in) is split
across several entries: the named entry holds a marker with the number of parts, and the parts follow it."""

from __future__ import annotations

import keyring

SERVICE = "oso"

CANVAS_FEED_URL = "canvas_feed_url"
CANVAS_BASE_URL = "canvas_base_url"
CANVAS_TOKEN = "canvas_token"

PART = 1000  # characters per entry, safely under Windows' 1280
MARKER = "oso-parts:"


def _part(name: str, i: int) -> str:
    return f"{name}#{i}"


def _parts(stored: str | None) -> int:
    if stored and stored.startswith(MARKER) and stored[len(MARKER):].isdigit():
        return int(stored[len(MARKER):])
    return 0


def get(name: str) -> str | None:
    stored = keyring.get_password(SERVICE, name)
    n = _parts(stored)
    if not n:
        return stored
    pieces = [keyring.get_password(SERVICE, _part(name, i)) for i in range(n)]
    return None if any(p is None for p in pieces) else "".join(pieces)


def set(name: str, value: str) -> None:  # noqa: A001
    old = _parts(keyring.get_password(SERVICE, name))
    if len(value) <= PART and not value.startswith(MARKER):
        keyring.set_password(SERVICE, name, value)
        n = 0
    else:
        pieces = [value[i:i + PART] for i in range(0, len(value), PART)]
        for i, piece in enumerate(pieces):
            keyring.set_password(SERVICE, _part(name, i), piece)
        n = len(pieces)
        keyring.set_password(SERVICE, name, f"{MARKER}{n}")
    for i in range(n, old):
        _delete(_part(name, i))


def _delete(name: str) -> None:
    try:
        keyring.delete_password(SERVICE, name)
    except keyring.errors.PasswordDeleteError:
        pass


def delete(name: str) -> None:
    for i in range(_parts(keyring.get_password(SERVICE, name))):
        _delete(_part(name, i))
    _delete(name)
