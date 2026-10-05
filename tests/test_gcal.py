from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from oso import db, gcal, merge
from oso.config import Config, Course
from oso.db import Item

TZ = ZoneInfo("America/New_York")
NOW = datetime(2026, 10, 5, 8, 0, tzinfo=TZ)


class FakeResp:
    def __init__(self, data, ok=True):
        self._data, self.ok = data, ok

    def json(self):
        return self._data

    def raise_for_status(self):
        if not self.ok:
            raise RuntimeError("http error")


class FakeSession:
    def __init__(self):
        self.posts = []

    def get(self, url):
        return FakeResp({}, ok=url.endswith("/cal-1"))

    def post(self, url, json):
        self.posts.append((url, json))
        if url.endswith("/calendars"):
            return FakeResp({"id": "cal-1"})
        return FakeResp({"id": f"ev-{len(self.posts)}"})


def test_deliver_creates_events_once_and_respects_quiet_hours(tmp_path: Path, monkeypatch):
    store = {}
    monkeypatch.setattr(gcal.secrets, "get", lambda k: store.get(k))
    monkeypatch.setattr(gcal.secrets, "set", lambda k, v: store.__setitem__(k, v))
    cfg = Config(vault=tmp_path / "vault", courses=[Course("MATH-101-001", "Calculus I", "Calculus I")])
    with db.connect(tmp_path / "t.sqlite") as conn:
        hw = Item(source="canvas_feed", external_id="a1", kind="assignment", title="Homework 1",
                  due_at=NOW + timedelta(days=2), course_code="MATH-101-001", url="https://canvas/a1")
        merge.apply(conn, [hw], "canvas_feed", NOW)
        hw.due_at = NOW + timedelta(days=4)
        merge.apply(conn, [hw], "canvas_feed", NOW)

        quiet = Config(vault=cfg.vault, courses=cfg.courses, quiet_hours="07:00-09:00")
        s = FakeSession()
        assert gcal.deliver(conn, quiet, NOW, session=s) == 0

        s = FakeSession()
        assert gcal.deliver(conn, cfg, NOW, session=s) == 1
        cal_post, ev_post = s.posts
        assert cal_post[1]["summary"] == "Oso"
        body = ev_post[1]
        assert body["summary"].startswith("Oso: Calculus I: Homework 1 moved from")
        assert body["start"]["dateTime"].startswith((NOW + timedelta(days=4)).isoformat()[:16])
        assert [r["minutes"] for r in body["reminders"]["overrides"]] == [1440, 120]
        assert body["source"]["url"] == "https://canvas/a1"

        s2 = FakeSession()
        assert gcal.deliver(conn, cfg, NOW, session=s2) == 0
        assert s2.posts == []
