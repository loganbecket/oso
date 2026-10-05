"""Run every configured connector, merge the results, keep the vault derived files current, and rewrite Today.md."""

from __future__ import annotations

import logging
from datetime import datetime

from . import alerts, convert, dashboard, db, drive, handwriting, index, merge, secrets, today
from .config import Config
from .connectors import Connector
from .connectors.canvas_api import CanvasApi
from .connectors.canvas_feed import CanvasFeed
from .connectors.remarkable_usb import NotConnected, RemarkableUsb

log = logging.getLogger("oso")


def connectors(cfg: Config) -> list[Connector]:
    out: list[Connector] = []
    url = secrets.get(secrets.CANVAS_FEED_URL)
    if url:
        out.append(CanvasFeed(url, cfg.tz))
    base = secrets.get(secrets.CANVAS_BASE_URL)
    token = secrets.get(secrets.CANVAS_TOKEN)
    if base and token:
        out.append(CanvasApi(base, token, cfg))
    return out


def run(cfg: Config, now: datetime | None = None) -> dict[str, object]:
    now = now or datetime.now(cfg.tz)
    results: dict[str, object] = {}
    with db.connect() as conn:
        for c in cfg.courses:
            db.upsert_course(conn, c.code, c.name, c.folder)

        for connector in connectors(cfg):
            run_id = db.record_sync(conn, connector.name)
            try:
                items = connector.fetch()
                counts = merge.apply(conn, items, connector.name, now)
                if isinstance(connector, CanvasApi):
                    counts["grades"] = _apply_grades(conn, connector)
                    counts.update(connector.mirror())
            except Exception as e:  # noqa: BLE001
                db.finish_sync(conn, run_id, ok=False, error=plain_error(e))
                results[connector.name] = plain_error(e)
                log.warning("%s failed: %s", connector.name, plain_error(e))
                continue
            db.finish_sync(conn, run_id, ok=True, items_seen=len(items))
            results[connector.name] = counts
            log.info("%s: %s", connector.name, counts)

        results["alerts"] = _safe(lambda: alerts.write_inbox(conn, cfg, now), 0)
        results["drive_mirrored"] = _safe(lambda: drive.mirror(cfg), 0)
        results["converted"] = len(_safe(lambda: convert.convert_vault(cfg), []))
        results["remarkable"] = _pull_tablet(conn, cfg)
        results["handwriting_queued"] = _safe(lambda: handwriting.queue_new(conn, cfg), 0)
        results["index"] = _safe(lambda: index.rebuild(conn, cfg), {})
        today.write(conn, cfg, now)
        _safe(lambda: dashboard.write(conn, cfg, now), None)
    return results


def _pull_tablet(conn, cfg: Config) -> str | int:
    """Pull notebooks over USB if the tablet is plugged in. Not being plugged in is normal, not a failure."""
    tablet = RemarkableUsb(cfg)
    run_id = db.record_sync(conn, tablet.name)
    try:
        n = tablet.pull(conn)
    except NotConnected:
        db.finish_sync(conn, run_id, ok=True, error="not connected", items_seen=0)
        return "not connected"
    except Exception as e:  # noqa: BLE001
        db.finish_sync(conn, run_id, ok=False, error=plain_error(e))
        return plain_error(e)
    db.finish_sync(conn, run_id, ok=True, items_seen=n)
    return n


def _apply_grades(conn, connector: CanvasApi) -> int:
    n = 0
    for ext, (points, maximum) in connector.grades.items():
        conn.execute(
            "UPDATE items SET grade_points = ?, grade_max = ?, status = 'done' WHERE source = ? AND external_id = ?",
            (points, maximum, connector.name, ext),
        )
        n += 1
    return n


def _safe(fn, default):
    try:
        return fn()
    except Exception as e:  # noqa: BLE001
        log.warning("step failed: %s", plain_error(e))
        return default


def plain_error(e: Exception) -> str:
    """An error message a student can act on. No stack traces, no secrets."""
    name = type(e).__name__
    text = str(e)
    if "401" in text or "403" in text:
        return "the source rejected the login; it may need to be set up again"
    if "404" in text:
        return "the address no longer works; copy a fresh one from Canvas"
    if "ConnectionError" in name or "Timeout" in name or "timed out" in text:
        return "could not reach the source; check the internet connection"
    return text.split("\n")[0][:160] or name
