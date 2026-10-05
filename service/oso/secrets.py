"""Secrets live in the operating system's credential store (Windows Credential Manager on Windows)."""

from __future__ import annotations

import keyring

SERVICE = "oso"

CANVAS_FEED_URL = "canvas_feed_url"


def get(name: str) -> str | None:
    return keyring.get_password(SERVICE, name)


def set(name: str, value: str) -> None:  # noqa: A001
    keyring.set_password(SERVICE, name, value)


def delete(name: str) -> None:
    try:
        keyring.delete_password(SERVICE, name)
    except keyring.errors.PasswordDeleteError:
        pass
