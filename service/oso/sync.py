"""Run every configured connector, merge the results, and rewrite Today.md."""

from __future__ import annotations

import logging
from datetime import datetime

from . import db, merge, secrets, today
from .config import Config
from .connectors import Connector
from .connectors.canvas_feed import CanvasFeed

log = logging.getLogger("oso")


def connectors(cfg: Config) -> list[Connector]:
    out: list[Connector] = []
    url = secrets.get(secrets.CANVAS_FEED_URL)
    if url:
        out.append(CanvasFeed(url, cfg.tz))
    return out


def run(cfg: Config, now: datetime | None = None) -> dict[str, dict[str, int] | str]:
    now = now or datetime.now(cfg.tz)
    results: dict[str, dict[str, int] | str] = {}
    with db.connect() as conn:
        for c in cfg.courses:
            db.upsert_course(conn, c.code, c.name, c.folder)
        for connector in connectors(cfg):
            run_id = db.record_sync(conn, connector.name)
            try:
                items = connector.fetch()
            except Exception as e:  # noqa: BLE001
                db.finish_sync(conn, run_id, ok=False, error=_plain(e))
                results[connector.name] = _plain(e)
                log.warning("%s failed: %s", connector.name, _plain(e))
                continue
            counts = merge.apply(conn, items, connector.name, now)
            db.finish_sync(conn, run_id, ok=True, items_seen=len(items))
            results[connector.name] = counts
            log.info("%s: %s", connector.name, counts)
        today.write(conn, cfg, now)
    return results


def _plain(e: Exception) -> str:
    """An error message a student can act on. No stack traces, no secrets."""
    name = type(e).__name__
    text = str(e)
    if "401" in text or "403" in text:
        return "the source rejected the login; it may need to be set up again"
    if "404" in text:
        return "the feed address no longer works; copy a fresh one from Canvas"
    if "ConnectionError" in name or "Timeout" in name or "timed out" in text:
        return "could not reach the source; check the internet connection"
    return text.split("\n")[0][:160] or name
