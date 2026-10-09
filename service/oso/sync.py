"""Run every configured connector, merge the results, keep the vault derived files current, and rewrite Today.md."""

from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime

from . import alerts, backup, books, canvas_session, canvas_store, classes, convert, dashboard, db, drive, filing, handwriting, instructions, mastery, merge, reader, rules, search, sites, secrets, skillsync, today, update
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
            results["filed"] = _safe(lambda: filing.file_clippings(cfg, conn), 0, conn, "filing clippings")
            results["converted"] = len(_safe(lambda: convert.convert_vault(cfg), [], conn, "converting files"))
            results["books"] = _safe(lambda: books.process(cfg, conn), {}, conn, "books")
            results["handwriting_queued"] = _safe(lambda: handwriting.queue_new(conn, cfg), 0, conn, "handwriting")
            results["search"] = _safe(lambda: search.update(cfg), {}, conn, "search")
            results["read_by_claude"] = _safe(lambda: reader.run(cfg, conn, now), {}, conn, "reading pages")
            results["search_after_reading"] = _safe(lambda: search.update(cfg), {}, conn, "search")
            results["profiles"] = len(_safe(lambda: mastery.write_all(conn, cfg, now), [], conn, "profiles"))
            _safe(lambda: _write_today(conn, cfg, now), None, conn, "Today.md")
    return results


def _write_today(conn, cfg: Config, now: datetime) -> None:
    """Today.md, or a one-line stand-in when building it fails, so a bad value never hides the whole page."""
    try:
        today.write(conn, cfg, now)
    except Exception as e:  # noqa: BLE001
        _record_failure("today")
        from . import vault

        vault.write_file(cfg.vault / "Today.md",
                         f"# Today\n\nOso couldn't build today's page ({plain_error(e)}). The next check will try again.\n")
        raise


def _run(cfg: Config, now: datetime | None = None) -> dict[str, object]:
    now = now or datetime.now(cfg.tz)
    results: dict[str, object] = {}
    with db.connect() as conn:
        for c in cfg.courses:
            db.upsert_course(conn, c.code, c.name, c.folder)

        if canvas_session.status(conn) == "needs_sign_in":
            _safe(lambda: canvas_session.reconnect_quietly(conn), False, conn, "canvas sign-in")  # at most hourly, only with a stored login
        for connector in connectors(cfg, conn):
            run_id = db.record_sync(conn, connector.name)
            try:
                with _step(conn, connector.name):
                    items = connector.fetch()
                    counts = merge.apply(conn, items, connector.name, now, urgent_days=cfg.urgent_days, cfg=cfg)
                    if isinstance(connector, CanvasApi):
                        counts["grades"] = _apply_grades(conn, connector)
                        counts.update(canvas_store.save(conn, connector))
                        counts.update(connector.mirror())
                        canvas_store.record_new_files(conn, connector.new_files)
                        _store_announcements(conn, connector)
                        if connector.uses_session:
                            canvas_session.mark_connected(conn)
                            if connector.cookies() and connector.cookies() != canvas_session.load():
                                canvas_session.save(connector.cookies())  # Canvas refreshed the session
            except SessionExpired:
                db.finish_sync(conn, run_id, ok=False, error=canvas_session.SIGN_IN_LINE)
                results[connector.name] = "needs sign-in"
                first = canvas_session.mark_expired(conn)
                # With his username and password stored, sign in again quietly; otherwise ask him once.
                if not canvas_session.reconnect_quietly(conn) and first and cfg.canvas_notify and canvas_session.login() is None:
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
            conn.commit()  # what this source said is kept even if a later step fails

        results.update(_read_messages(conn, cfg, now))
        _safe(lambda: filing.retire_inbox(cfg), 0, conn, "clippings")
        results["alerts"] = _safe(lambda: alerts.write_inbox(conn, cfg, now), 0, conn, "alerts")
        results["classes"] = _safe(lambda: classes.extend(conn, cfg, now), 0, conn, "class times")
        results["rules"] = _safe(lambda: rules.run(cfg, conn, now), {}, conn, "rules")
        results["calendar"] = _deliver_calendar(conn, cfg, now)
        results["tasks"] = _tasks(conn, cfg, now)
        results["filed"] = _safe(lambda: filing.file_clippings(cfg, conn), 0, conn, "filing clippings")
        results["drive_mirrored"] = _safe(lambda: drive.mirror(cfg), 0, conn, "Drive")
        results["sites"] = _safe(lambda: sites.check(cfg, conn, now), {}, conn, "instructor websites")
        results["converted"] = len(_safe(lambda: convert.convert_vault(cfg), [], conn, "converting files"))
        results["books"] = _safe(lambda: books.process(cfg, conn), {}, conn, "books")
        results["search"] = _safe(lambda: search.update(cfg), {}, conn, "search")
        results["profiles"] = len(_safe(lambda: mastery.write_all(conn, cfg, now), [], conn, "profiles"))
        results["remarkable"] = _pull_tablet(conn, cfg)
        results["handwriting_queued"] = _safe(lambda: handwriting.queue_new(conn, cfg), 0, conn, "handwriting")
        results["read_by_claude"] = _safe(lambda: reader.run(cfg, conn, now), {}, conn, "reading pages")
        results["update"] = _safe(lambda: update.check_daily(conn, cfg, now), None, conn, "update check")
        results["skill_conflicts"] = len(_safe(lambda: skillsync.sync(cfg), [], conn, "command updates"))
        results["backup"] = _safe(lambda: backup.run(cfg, conn, now), {}, conn, "backup")
        conn.commit()
        _safe(lambda: _write_today(conn, cfg, now), None, conn, "Today.md")
        _safe(lambda: dashboard.write(conn, cfg, now), None, conn, "Dashboard.md")
        _safe(lambda: instructions.write(cfg), None, conn, "vault instructions")
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


def _tasks(conn, cfg: Config, now: datetime) -> str | dict:
    """Things to do picked out of messages join his tasks, and the list is matched with Google Tasks."""
    from . import tasks

    _safe(lambda: tasks.import_actions(conn, cfg, now), 0, conn, "tasks from messages")
    if not tasks.connected():
        return "not connected"
    run_id = db.record_sync(conn, "google_tasks")
    try:
        counts = tasks.sync(conn, cfg, now)
    except Exception as e:  # noqa: BLE001
        db.finish_sync(conn, run_id, ok=False, error=plain_error(e))
        return plain_error(e)
    db.finish_sync(conn, run_id, ok=True, items_seen=counts["from_google"])
    return counts


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


def _store_announcements(conn, connector: CanvasApi) -> None:
    """New Canvas announcements join school email and GroupMe, so Claude reads them for class changes."""
    from . import messages

    messages.ensure(conn)
    for rec in getattr(connector, "new_announcements", []):
        messages.store(conn, rec)


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
    results["rules_on_messages"] = _safe(lambda: rules.on_messages(cfg, conn, now), 0, conn, "rules on messages")  # before reading drops their text
    if results or _safe(lambda: messages.waiting(conn), 0):
        results["messages"] = _safe(lambda: messages.read_new(conn, cfg, now), {}, conn, "reading messages")
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


@contextmanager
def _step(conn: sqlite3.Connection | None, name: str):
    """One step's writes stand or fall together: a failure rolls back what the step half-did, and nothing else."""
    if conn is None:
        yield
        return
    point = "step_" + "".join(ch if ch.isalnum() else "_" for ch in name)
    conn.execute(f"SAVEPOINT {point}")
    try:
        yield
    except BaseException:
        try:
            conn.execute(f"ROLLBACK TO {point}")
        except sqlite3.OperationalError:
            pass  # the step committed on its own; nothing left to roll back
        raise
    finally:
        try:
            conn.execute(f"RELEASE {point}")
        except sqlite3.OperationalError:
            pass


def _safe(fn, default, conn: sqlite3.Connection | None = None, name: str | None = None):
    """Run one step of a check. A failure is logged, rolled back, and (with a connection and a name) written down
    where Today.md and the health check will show it, until the step next succeeds."""
    try:
        with _step(conn, name or "step"):
            result = fn()
    except Exception as e:  # noqa: BLE001
        log.warning("%s failed: %s", name or "step", plain_error(e))
        if conn is not None and name:
            _record_failure(name)
            try:
                db.note_step_failure(conn, name, plain_error(e))
            except sqlite3.Error:
                pass
        return default
    if conn is not None and name:
        try:
            db.clear_step_failure(conn, name)
        except sqlite3.Error:
            pass
    return result


def plain_error(e: Exception) -> str:
    """An error message a student can act on. No stack traces, no secrets."""
    import re

    import requests

    name = type(e).__name__
    text = str(e)
    if re.search(r"\b40[13]\b", text):
        return "the source rejected the login; it may need to be set up again"
    if re.search(r"\b404\b", text):
        return "the address no longer works; copy a fresh one from Canvas"
    if isinstance(e, (requests.ConnectionError, requests.Timeout)) or "ConnectionError" in name or "Timeout" in name or "timed out" in text:
        return "could not reach the source; check the internet connection"
    # Never an address: a feed URL is a secret, and these sentences end up in Today.md.
    text = re.sub(r"https?://\S+", "(address)", text)
    text = re.sub(r"(?i)\burl: ?\S+", "url: (address)", text)
    return text.split("\n")[0][:160] or name
