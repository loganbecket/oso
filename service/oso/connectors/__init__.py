"""Connectors pull items from outside sources. Each exposes `name` and `fetch() -> list[Item]`."""

from __future__ import annotations

from typing import Protocol

from ..db import Item


class Connector(Protocol):
    name: str

    def fetch(self) -> list[Item]: ...
