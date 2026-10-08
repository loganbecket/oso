"""Tasks: his checklist in Oso and in Google Tasks, kept the same both ways; things to do from messages joining it;
pop-up reminders at a moment; and the briefing's Tasks section with today's free time."""

from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from oso import classes, config as cfgmod, db, happenings, messages, secrets, tasks, today
from oso.config import Config, Course

TZ = ZoneInfo("America/Chicago")
NOW = datetime(2026, 10, 8, 7, 0, tzinfo=TZ)  # a Thursday


@pytest.fixture
def env(tmp_path: Path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr(cfgmod, "data_dir", lambda: data)
    monkeypatch.setattr(db, "data_dir", lambda: data)
    monkeypatch.setattr(cfgmod, "config_path", lambda: data / "config.toml")
    store: dict[str, str] = {}
    monkeypatch.setattr(secrets, "get", lambda name: store.get(name))
    monkeypatch.setattr(secrets, "set", lambda name, value: store.__setitem__(name, value))
    monkeypatch.setattr(secrets, "delete", lambda name: store.pop(name, None))
    cfg = Config(vault=tmp_path / "vault", timezone="America/Chicago", quiet_hours="23:00-07:00",
                 courses=[Course("PHYS-110", "Physics", "2026 Fall/Physics")])
    cfg.vault.mkdir()
    cfgmod.save(cfg)
    with db.connect() as conn:
        messages.ensure(conn)
        tasks.ensure(conn)
        yield cfg, conn, store


class Resp:
    def __init__(self, body=None, status=200):
        self._body, self.status_code, self.ok = body or {}, status, status < 400

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class FakeTasks:
    """Google Tasks with one list, as the API shows it."""

    def __init__(self):
        self.lists, self.items, self.n = [], {}, 0

    def get(self, url, params=None):
        if url.endswith("/users/@me/lists"):
            return Resp({"items": self.lists})
        if "/users/@me/lists/" in url:
            lid = url.rsplit("/", 1)[1]
            return Resp({"id": lid}) if any(l["id"] == lid for l in self.lists) else Resp(status=404)
        return Resp({"items": list(self.items.values())})

    def post(self, url, json=None):
        self.n += 1
        if url.endswith("/users/@me/lists"):
            self.lists.append({"id": "L1", "title": json["title"]})
            return Resp({"id": "L1"})
        tid = f"g{self.n}"
        self.items[tid] = {"id": tid, **{k: v for k, v in json.items() if v is not None}, "updated": "2026-10-08T12:00:00.000Z"}
        return Resp(self.items[tid])

    def patch(self, url, json=None):
        tid = url.rsplit("/", 1)[1]
        if tid not in self.items:
            return Resp(status=404)
        self.items[tid].update({k: v for k, v in json.items() if v is not None})
        return Resp(self.items[tid])

    def delete(self, url):
        self.items.pop(url.rsplit("/", 1)[1], None)
        return Resp(status=204)

    def phone(self, tid, **change):
        """He changes something on his phone, later than anything Oso did."""
        self.items[tid].update(change, updated=(datetime.now(ZoneInfo("UTC")) + timedelta(minutes=1)).isoformat().replace("+00:00", "Z"))


def test_tasks_go_to_google_and_what_he_does_there_comes_back(env):
    cfg, conn, store = env
    g = FakeTasks()
    laundry = tasks.add(conn, "Do laundry", "2026-10-11")
    tasks.add(conn, "Get an oil change", notes="Jiffy Lube on Valley Mills")
    assert tasks.add(conn, "do laundry") is None  # already on the list
    tasks.sync(conn, cfg, NOW, session=g)
    assert g.lists == [{"id": "L1", "title": "Oso"}] and store[tasks.LIST_ID] == "L1"
    by_title = {t["title"]: t for t in g.items.values()}
    assert by_title["Do laundry"]["due"] == "2026-10-11T00:00:00.000Z" and by_title["Do laundry"]["status"] == "needsAction"
    assert by_title["Get an oil change"]["notes"] == "Jiffy Lube on Valley Mills"
    gid = by_title["Do laundry"]["id"]
    g.phone(gid, status="completed")
    g.items["g9"] = {"id": "g9", "title": "Register to vote", "status": "needsAction", "due": "2026-10-13T00:00:00.000Z",
                     "updated": (datetime.now(ZoneInfo("UTC")) + timedelta(minutes=1)).isoformat().replace("+00:00", "Z")}
    tasks.sync(conn, cfg, NOW + timedelta(minutes=15), session=g)
    rows = {r["title"]: r for r in tasks.listing(conn, include_done=True)}
    assert rows["Do laundry"]["status"] == "done" and rows["Register to vote"]["due"] == "2026-10-13"
    assert rows["Register to vote"]["source"] == "google"
    assert conn.execute("SELECT status FROM tasks WHERE id = ?", (laundry,)).fetchone()[0] == "done"
    g.phone("g9", deleted=True)
    tasks.sync(conn, cfg, NOW + timedelta(minutes=30), session=g)
    assert "Register to vote" not in [t["title"] for t in tasks.listing(conn)]


def test_changes_in_oso_go_out(env):
    cfg, conn, _ = env
    g = FakeTasks()
    tasks.add(conn, "Do laundry")
    tasks.sync(conn, cfg, NOW, session=g)
    assert "Checked off" in tasks.change(conn, "laundry", done=True)
    tasks.sync(conn, cfg, NOW, session=g)
    [item] = g.items.values()
    assert item["status"] == "completed"
    tasks.change(conn, "laundry", done=False, due="2026-10-12")
    tasks.sync(conn, cfg, NOW, session=g)
    assert item["status"] == "needsAction" and item["due"] == "2026-10-12T00:00:00.000Z"
    tasks.change(conn, "laundry", delete=True)
    tasks.sync(conn, cfg, NOW, session=g)
    assert g.items == {}


def test_things_to_do_from_messages_become_tasks(env):
    cfg, conn, _ = env
    hid = happenings.add(conn, "action", "Pay IM football dues", "2026-10-09", all_day=True, source="groupme", channel="IM Football",
                         note="Dues are $20 on Fusion.")
    assert tasks.import_actions(conn, cfg, NOW) == 1
    assert tasks.import_actions(conn, cfg, NOW) == 0
    [t] = tasks.listing(conn)
    assert t["title"] == "Pay IM football dues" and t["due"] == "2026-10-09" and t["source"] == "groupme"
    assert "Dues are $20" in t["notes"] and "GroupMe, IM Football" in t["notes"]
    happenings.change(conn, hid, NOW, canceled=True)
    tasks.import_actions(conn, cfg, NOW)
    assert tasks.listing(conn) == []


def test_briefing_shows_tasks_and_free_time_and_no_longer_lists_actions_twice(env):
    cfg, conn, _ = env
    classes.set_times(conn, cfg, "PHYS-110", [{"days": "TR", "starts": "9:30", "ends": "10:45"}], "2026-08-24", "2026-12-04", [], NOW)
    tasks.add(conn, "Pay IM football dues", "2026-10-06")
    tasks.add(conn, "Do laundry", "2026-10-11")
    tasks.add(conn, "Get an oil change")
    tasks.add(conn, "Renew passport", "2026-11-30")
    tasks.change(conn, tasks.add(conn, "Buy stamps"), done=True)
    happenings.add(conn, "action", "Register for spring classes", "2026-10-08", all_day=True, source="email")
    text = today.render(conn, cfg, NOW)
    block = text[text.index("## Tasks"):].split("\n\n")[0]
    assert "- Pay IM football dues (overdue, was due Tue Oct 06)" in block
    assert "- Do laundry (by Sun Oct 11)" in block and "- Get an oil change (whenever)" in block
    assert "And 1 more due after this week." in block and "Checked off since yesterday: Buy stamps." in block
    assert "Free time left today: 7 AM–9:30 AM, 10:45 AM–11 PM." in block
    assert "To do" not in text  # things to do are tasks now, not schedule lines


def test_reminder_at_a_moment_pops_up(env, monkeypatch):
    cfg, conn, _ = env
    from oso import mcp_server

    monkeypatch.setattr(mcp_server, "_cfg", lambda: cfg)
    monkeypatch.setattr(happenings, "push", lambda *a: None)
    out = mcp_server.add_to_calendar("Swing by the mail room", "2026-10-08T10:45", "2026-10-08T11:00", remind=True)
    with db.connect() as c2:
        h = dict(c2.execute("SELECT * FROM happenings WHERE id = ?", (out["happening"],)).fetchone())
    body = happenings.event_body(h, cfg)
    assert body["reminders"] == {"useDefault": False, "overrides": [{"method": "popup", "minutes": 0}]}
    assert "reminders" not in happenings.event_body({**h, "remind": 0}, cfg)


def test_task_tools(env, monkeypatch):
    cfg, conn, _ = env
    from oso import mcp_server

    monkeypatch.setattr(mcp_server, "_cfg", lambda: cfg)
    assert mcp_server.add_task("Get an oil change", "2026-10-11")["added"]
    assert not mcp_server.add_task("get an oil change")["added"]
    assert [t["title"] for t in mcp_server.list_tasks()] == ["Get an oil change"]
    assert mcp_server.change_task("oil", done=True) == 'Checked off "Get an oil change".'
    assert mcp_server.list_tasks() == [] and mcp_server.list_tasks(include_done=True)[0]["status"] == "done"
    assert "no task like" in mcp_server.change_task("groceries", done=True)
