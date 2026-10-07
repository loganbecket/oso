"""Run every configured connector, merge the results, keep the vault derived files current, and rewrite Today.md."""

from __future__ import annotations

import logging
from datetime import datetime

from . import alerts, backup, books, canvas_session, canvas_store, convert, dashboard, db, drive, filing, handwriting, instructions, mastery, merge, reader, search, sites, secrets, skillsync, today, update
from .config import Config
from .connectors import Connector
from .connectors.canvas_api import CanvasApi, SessionExpired
from .connectors.canvas_feed import CanvasFeed
from .connectors.remarkable_usb import NotConnected, RemarkableUsb

log = logging.getLogger("oso")


def connectors(cfg: Config, conn=None) -> list[Connector]:
    from . import canvas_session

    out: list[Connector] = []
    url = secrets.get(secrets.CANVAS_FEED_URL)
    if url:
        out.append(CanvasFeed(url, cfg.tz))
    base = secrets.get(secrets.CANVAS_BASE_URL)
    token = secrets.get(secrets.CANVAS_TOKEN)
    if base and token:
        out.append(CanvasApi(base, token, cfg))
    elif conn is not None and canvas_session.status(conn) == "connected":
        # Read Canvas with his own signed-in session; skipped while it waits for him to sign in again.
        out.append(CanvasApi(canvas_session.base_url() or "", None, cfg, cookies=canvas_session.load()))
    return out


def run(cfg: Config, now: datetime | None = None) -> dict[str, object]:
    from . import lock

    with lock.held() as got:  # never at the same time as the folder watcher taking in files
        if not got:
            return {"skipped": "another Oso task was still running"}
        return _run(cfg, now)


def ingest(cfg: Config, now: datetime | None = None) -> dict[str, object]:
    """The local part of a check, for files that just arrived (watch.py): no Canvas, calendar, tablet, or
    update check. Each step only does what is new."""
    from . import lock

    now = now or datetime.now(cfg.tz)
    results: dict[str, object] = {}
    with lock.held() as got:
        if not got:
            return {"skipped": "another Oso task was still running"}
        with db.connect() as conn:
            results["filed"] = _safe(lambda: filing.file_clippings(cfg, conn), 0)
            results["converted"] = len(_safe(lambda: convert.convert_vault(cfg), []))
            results["books"] = _safe(lambda: books.process(cfg, conn), {})
            results["handwriting_queued"] = _safe(lambda: handwriting.queue_new(conn, cfg), 0)
            results["search"] = _safe(lambda: search.update(cfg), {})
            results["read_by_claude"] = _safe(lambda: reader.run(cfg, conn, now), {})
            results["search_after_reading"] = _safe(lambda: search.update(cfg), {})
            results["profiles"] = len(_safe(lambda: mastery.write_all(conn, cfg, now), []))
            _safe(lambda: today.write(conn, cfg, now), None)
    return results


def _run(cfg: Config, now: datetime | None = None) -> dict[str, object]:
    now = now or datetime.now(cfg.tz)
    results: dict[str, object] = {}
    with db.connect() as conn:
        for c in cfg.courses:
            db.upsert_course(conn, c.code, c.name, c.folder)

        for connector in connectors(cfg, conn):
            run_id = db.record_sync(conn, connector.name)
            try:
                items = connector.fetch()
                counts = merge.apply(conn, items, connector.name, now, urgent_days=cfg.urgent_days)
                if isinstance(connector, CanvasApi):
                    counts["grades"] = _apply_grades(conn, connector)
                    counts.update(canvas_store.save(conn, connector))
                    counts.update(connector.mirror())
                    canvas_store.record_new_files(conn, connector.new_files)
                    if connector.uses_session:
                        canvas_session.mark_connected(conn)
                        if connector.cookies() and connector.cookies() != canvas_session.load():
                            canvas_session.save(connector.cookies())  # Canvas refreshed the session
            except SessionExpired:
                db.finish_sync(conn, run_id, ok=False, error=canvas_session.SIGN_IN_LINE)
                results[connector.name] = "needs sign-in"
                if canvas_session.mark_expired(conn) and cfg.canvas_notify:
                    canvas_session.notify_sign_in()
                continue
            except Exception as e:  # noqa: BLE001
                db.finish_sync(conn, run_id, ok=False, error=plain_error(e))
                results[connector.name] = plain_error(e)
                log.warning("%s failed: %s", connector.name, plain_error(e))
                _record_failure(connector.name)
                continue
            db.finish_sync(conn, run_id, ok=True, items_seen=len(items))
            results[connector.name] = counts
            log.info("%s: %s", connector.name, counts)

        results.update(_read_messages(conn, cfg, now))
        _safe(lambda: filing.retire_inbox(cfg), 0)
        results["alerts"] = _safe(lambda: alerts.write_inbox(conn, cfg, now), 0)
        results["calendar"] = _deliver_calendar(conn, cfg, now)
        results["filed"] = _safe(lambda: filing.file_clippings(cfg, conn), 0)
        results["drive_mirrored"] = _safe(lambda: drive.mirror(cfg), 0)
        results["sites"] = _safe(lambda: sites.check(cfg, conn, now), {})
        results["converted"] = len(_safe(lambda: convert.convert_vault(cfg), []))
        results["books"] = _safe(lambda: books.process(cfg, conn), {})
        results["search"] = _safe(lambda: search.update(cfg), {})
        results["profiles"] = len(_safe(lambda: mastery.write_all(conn, cfg, now), []))
        results["remarkable"] = _pull_tablet(conn, cfg)
        results["handwriting_queued"] = _safe(lambda: handwriting.queue_new(conn, cfg), 0)
        results["read_by_claude"] = _safe(lambda: reader.run(cfg, conn, now), {})
        results["update"] = _safe(lambda: update.check_daily(conn, cfg, now), None)
        results["skill_conflicts"] = len(_safe(lambda: skillsync.sync(cfg), []))
        results["backup"] = _safe(lambda: backup.run(cfg, conn, now), {})
        today.write(conn, cfg, now)
        _safe(lambda: dashboard.write(conn, cfg, now), None)
        _safe(lambda: instructions.write(cfg), None)
    return results


def _record_failure(name: str) -> None:
    """Keep the technical detail of a failure in a log file (never shown to the student), so it can be fixed."""
    import traceback

    from .config import data_dir

    try:
        with (data_dir() / "errors.log").open("a", encoding="utf-8") as f:
            f.write(f"\n--- {datetime.now().isoformat(timespec='seconds')} {name}\n{traceback.format_exc()}")
    except OSError:
        pass


def _deliver_calendar(conn, cfg: Config, now: datetime) -> str | int:
    from . import gcal

    if not gcal.connected():
        return "not connected"
    from . import happenings

    run_id = db.record_sync(conn, "google_calendar")
    try:
        session = gcal._session()
        n = gcal.deliver(conn, cfg, now, session=session)
        # Events from email and GroupMe go on the Oso calendar, and the whole calendar is read back for the schedule.
        happenings.sync_calendar(conn, cfg, now, session, gcal.ensure_calendar(session, cfg))
    except Exception as e:  # noqa: BLE001
        db.finish_sync(conn, run_id, ok=False, error=plain_error(e))
        return plain_error(e)
    db.finish_sync(conn, run_id, ok=True, items_seen=n)
    return n


def _read_messages(conn, cfg: Config, now: datetime) -> dict[str, object]:
    """New school email and GroupMe messages, then Claude picking out what matters in them."""
    from . import groupme, mail, messages

    results: dict[str, object] = {}
    for name, module in (("school_email", mail), ("groupme", groupme)):
        if not module.connected():
            continue
        run_id = db.record_sync(conn, name)
        try:
            counts = module.fetch(conn, cfg, now)
        except Exception as e:  # noqa: BLE001
            db.finish_sync(conn, run_id, ok=False, error=plain_error(e))
            results[name] = plain_error(e)
            _record_failure(name)
            continue
        db.finish_sync(conn, run_id, ok=True, items_seen=int(counts.get("kept", 0)))
        results[name] = counts
        conn.commit()
    if results:
        results["messages"] = _safe(lambda: messages.read_new(conn, cfg, now), {})
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
