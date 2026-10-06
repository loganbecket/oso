import json
import threading
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

import pytest

from oso import canvas_session, canvas_store, config as cfgmod, db, mastery, profile, readiness, secrets, sync, today
from oso.config import Config, Course
from oso.connectors.canvas_api import CanvasApi, SessionExpired

TZ = ZoneInfo("America/New_York")
NOW = datetime(2026, 11, 2, 8, 0, tzinfo=TZ)

STATE = {"cookie": "good", "hw4_score": 6.0, "comments": [], "rotate": False}


def canvas_data():
    return {
        "/api/v1/users/self": {"id": 7, "name": "Campbell"},
        "/api/v1/courses": [{"id": 1, "name": "General Physics", "course_code": "PHYS-110",
                             "enrollments": [{"type": "student", "computed_current_score": 81.5, "computed_current_grade": "B-"}]}],
        "/api/v1/courses/1/assignment_groups": [{"id": 10, "name": "Homework", "group_weight": 30}, {"id": 11, "name": "Exams", "group_weight": 50}],
        "/api/v1/courses/1/assignments": [
            {"id": 101, "name": "HW 4: Kinematics", "due_at": "2026-10-28T23:59:00Z", "points_possible": 10, "assignment_group_id": 10,
             "submission_types": ["online_upload"], "html_url": "https://x/101", "submission": {"score": STATE["hw4_score"]}},
            {"id": 102, "name": "HW 5: Forces", "due_at": "2026-10-31T23:59:00Z", "points_possible": 10, "assignment_group_id": 10,
             "submission_types": ["online_upload"], "html_url": "https://x/102"},
            {"id": 103, "name": "Exam 2", "due_at": "2026-11-05T14:00:00Z", "points_possible": 100, "assignment_group_id": 11,
             "submission_types": ["on_paper"], "html_url": "https://x/103"},
            {"id": 104, "name": "Quiz 3: Kinematics", "due_at": "2026-10-25T23:59:00Z", "points_possible": 4, "assignment_group_id": 10,
             "submission_types": ["online_quiz"], "quiz_id": 55, "html_url": "https://x/104"},
        ],
        "/api/v1/courses/1/students/submissions": [
            {"assignment_id": 101, "score": STATE["hw4_score"], "grade": str(STATE["hw4_score"]), "submitted_at": "2026-10-28T20:00:00Z",
             "graded_at": f"2026-10-30T12:00:{int(STATE['hw4_score']):02d}Z", "late": False, "missing": False, "excused": False,
             "submission_comments": STATE["comments"]},
            {"assignment_id": 102, "score": None, "submitted_at": None, "late": False, "missing": True, "excused": False, "submission_comments": []},
            {"assignment_id": 104, "score": 2.5, "submitted_at": "2026-10-25T20:00:00Z", "graded_at": "2026-10-25T20:05:00Z", "late": False,
             "missing": False, "excused": False, "submission_comments": [],
             "submission_history": [
                 {"attempt": 1, "submission_data": [{"question_id": 1, "correct": False, "points": 0}, {"question_id": 2, "correct": False, "points": 0},
                                                    {"question_id": 3, "correct": False, "points": 0}, {"question_id": 4, "correct": True, "points": 1}]},
                 {"attempt": 2, "submission_data": [{"question_id": 1, "correct": True, "points": 1}, {"question_id": 2, "correct": "partial", "points": 0.5},
                                                    {"question_id": 3, "correct": False, "points": 0}, {"question_id": 4, "correct": True, "points": 1}]},
             ]},
        ],
        "/api/v1/courses/1/files": [],
        "/api/v1/announcements": [],
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        cookies = dict(c.strip().split("=", 1) for c in (self.headers.get("Cookie") or "").split(";") if "=" in c)
        if cookies.get("canvas_session") != STATE["cookie"]:
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b'{"status":"unauthenticated"}')
            return
        path = urlparse(self.path).path
        data = canvas_data().get(path)
        if data is None:
            self.send_response(404)
            self.end_headers()
            return
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        if STATE["rotate"]:
            STATE["cookie"] = "good2"  # Canvas refreshes the session as it is used
            self.send_header("Set-Cookie", "canvas_session=good2; Path=/")
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture(scope="module")
def server():
    srv = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


@pytest.fixture
def env(tmp_path: Path, monkeypatch):
    STATE.update(cookie="good", hw4_score=6.0, comments=[], rotate=False)
    store = {}
    monkeypatch.setattr(secrets, "get", lambda name: store.get(name))
    monkeypatch.setattr(secrets, "set", lambda name, value: store.__setitem__(name, value))
    monkeypatch.setattr(secrets, "delete", lambda name: store.pop(name, None))
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr(cfgmod, "data_dir", lambda: data)
    monkeypatch.setattr(db, "data_dir", lambda: data)
    cfg = Config(vault=tmp_path / "vault", courses=[Course("PHYS-110", "Physics", "2026 Fall/Physics")])
    cfg.vault.mkdir()
    return cfg, store


def test_base_url_from_feed_and_cookie_trimming(env):
    cfg, store = env
    assert canvas_session.base_url() is None
    store[secrets.CANVAS_FEED_URL] = "https://tamu.instructure.com/feeds/calendars/user_abc.ics"
    assert canvas_session.base_url() == "https://tamu.instructure.com"
    canvas_session.save({"canvas_session": "s" * 1500, "_csrf_token": "t", "tracker": "x" * 2000})
    assert set(canvas_session.load()) == {"canvas_session", "_csrf_token"}


def test_verify(env, server):
    assert canvas_session.verify(server, {"canvas_session": "good"})
    assert not canvas_session.verify(server, {"canvas_session": "old"})


def test_read_and_store(env, server):
    cfg, _ = env
    api = CanvasApi(server, None, cfg, cookies={"canvas_session": "good"})
    items = api.fetch()
    assert {i.title for i in items} == {"HW 4: Kinematics", "HW 5: Forces", "Exam 2", "Quiz 3: Kinematics"}
    assert next(i for i in items if i.title == "Exam 2").kind == "exam" and next(i for i in items if i.title == "HW 4: Kinematics").weight == 30
    with db.connect() as conn:
        c = canvas_store.save(conn, api, now="2026-11-01T12:00:00+00:00")
        assert c["new_grades"] == 2 and c["new_comments"] == 0 and c["submissions"] == 3 and c["quiz_questions"] == 4
        s = canvas_store.info(conn, cfg, "PHYS-110")
        assert s["current_score"] == 81.5 and s["current_grade"] == "B-" and s["missing"] == ["HW 5: Forces"]
        assert s["recent_scores"][0] == {"name": "HW 4: Kinematics", "score": 6.0, "points": 10.0, "graded_at": "2026-10-30T12:00:06Z"}
        # nothing new on a second read
        assert canvas_store.save(conn, api.__class__(server, None, cfg, cookies={"canvas_session": "good"}) if False else api, now="2026-11-01T12:15:00+00:00")["new_grades"] == 0
        # a regrade and a comment show up as events
        STATE.update(hw4_score=8.0, comments=[{"id": 900, "author_name": "Dr. Lee", "comment": "Watch the sign on g.", "created_at": "2026-11-01T13:00:00Z"}])
        api.fetch()
        c = canvas_store.save(conn, api, now="2026-11-01T13:30:00+00:00")
        assert c["new_grades"] == 1 and c["new_comments"] == 1
        events = [r["text"] for r in canvas_store.recent_events(conn, datetime(2026, 11, 1, 14, 0, tzinfo=TZ))]
        assert "HW 4: Kinematics graded: 8/10" in events and "New comment on HW 4: Kinematics from Dr. Lee" in events
        assert canvas_store.info(conn, cfg, "PHYS-110", "comments")["comments"][0]["comment"] == "Watch the sign on g."
        assert "HW 5: Forces (due 2026-10-31): not graded, missing" in canvas_store.raw_dump(conn, cfg)


def test_expired_session(env, server):
    cfg, _ = env
    with pytest.raises(SessionExpired):
        CanvasApi(server, None, cfg, cookies={"canvas_session": "stale"}).fetch()


def test_topics_profile_and_readiness(env, server):
    cfg, _ = env
    api = CanvasApi(server, None, cfg, cookies={"canvas_session": "good"})
    api.fetch()
    with db.connect() as conn:
        canvas_store.save(conn, api)
        profile.set_topics(conn, cfg, "PHYS-110", [{"name": "Kinematics", "exams": ["Exam 2"]}, {"name": "Forces", "exams": ["Exam 2"]}])
        assert [u["name"] for u in canvas_store.info(conn, cfg, "PHYS-110", "untagged")["untagged"]] == ["Quiz 3: Kinematics", "HW 4: Kinematics", "HW 5: Forces", "Exam 2"]
        assert canvas_store.tag(conn, cfg, [{"canvas_id": 101, "topics": ["kinematics"]}, {"canvas_id": 102, "topics": ["Forces"]},
                                            {"canvas_id": 103, "topics": []}, {"canvas_id": 104, "topics": []}]) == 4
        assert canvas_store.untagged_count(conn, cfg) == 0
        assert canvas_store.topic_average(conn, "PHYS-110", ["Kinematics", "Forces"]) == (60.0, 1)
        ev = [e for e in mastery.evidence(conn, "PHYS-110") if e["source"].startswith("canvas")]
        assert ev == [{"topic": "Kinematics", "credit": 0.6, "mistake": None, "at": "2026-10-30T12:00:06Z", "source": "canvas 101"}]
        sync._apply_grades(conn, api)
        from oso import merge

        merge.apply(conn, api.fetch(), "canvas_api", NOW)
        [f] = readiness.flags(conn, cfg, NOW)
        assert f["exam"] == "Exam 2"
        assert "graded work on its topics averages 60% (1 assignment)" in f["reasons"] and "missing: HW 5: Forces" in f["reasons"]
        text = today.render(conn, cfg, NOW)
        assert "## Missing work\n- **Physics**: HW 5: Forces is marked missing in Canvas." in text


def test_check_marks_expiry_once_and_recovers(env, server, monkeypatch):
    cfg, store = env
    for name, value in (("_pull_tablet", lambda conn, cfg: "not connected"), ("_deliver_calendar", lambda conn, cfg, now: "not connected")):
        monkeypatch.setattr(sync, name, value)
    monkeypatch.setattr(sync.update, "check_daily", lambda conn, cfg, now: None)
    monkeypatch.setattr(sync.search, "update", lambda cfg: {})
    notices = []
    monkeypatch.setattr(canvas_session, "notify_sign_in", lambda: notices.append(1))
    store[secrets.CANVAS_BASE_URL] = server
    canvas_session.save({"canvas_session": "good"})
    STATE["rotate"] = True

    results = sync.run(cfg, NOW)
    assert isinstance(results["canvas_api"], dict), results["canvas_api"]
    assert results["canvas_api"]["new_grades"] == 2
    assert canvas_session.load() == {"canvas_session": "good2"}  # the refreshed session was saved
    STATE.update(cookie="good3")  # Canvas ends the session
    assert sync.run(cfg, NOW)["canvas_api"] == "needs sign-in"
    assert notices == [1]
    with db.connect() as conn:
        assert canvas_session.status(conn) == "needs_sign_in"
        assert canvas_session.SIGN_IN_LINE in today.render(conn, cfg, NOW)
    assert "canvas_api" not in sync.run(cfg, NOW)  # skipped until he signs in; no second notification
    assert notices == [1]
    # he signs in again
    canvas_session.save({"canvas_session": "good3"})
    with db.connect() as conn:
        canvas_session.mark_connected(conn)
        assert canvas_session.status(conn) == "connected" and len(canvas_session.lifetimes(conn)) == 1
    STATE["rotate"] = False
    assert isinstance(sync.run(cfg, NOW)["canvas_api"], dict)


def test_cookies_taken_only_for_the_canvas_host_and_connect_needs_an_address(env):
    from http.cookies import SimpleCookie

    jar1, jar2 = SimpleCookie(), SimpleCookie()
    jar1["canvas_session"] = "abc"
    jar1["canvas_session"]["domain"] = "tamu.instructure.com"
    jar2["sso"] = "zzz"
    jar2["sso"]["domain"] = ".sso.tamu.edu"

    class FakeWindow:
        def get_cookies(self):
            return [jar1, jar2]

    assert canvas_session._cookies_from(FakeWindow(), "tamu.instructure.com") == {"canvas_session": "abc"}
    with db.connect() as conn:
        assert "doesn't know your Canvas address" in canvas_session.connect(conn)



def test_quiz_questions_from_the_latest_attempt(env, server):
    cfg, _ = env
    api = CanvasApi(server, None, cfg, cookies={"canvas_session": "good"})
    api.fetch()
    with db.connect() as conn:
        canvas_store.save(conn, api)
        assert canvas_store.quiz_questions(conn, 104) == {"questions": 4, "right": 2, "partly_right": 1, "wrong": 1, "attempt": 2, "attempts": 2}
        assert "Quiz 3: Kinematics (due 2026-10-25): 2.5/4, 2 of 4 questions right (attempt 2 of 2)" in canvas_store.raw_dump(conn, cfg)
        profile.set_topics(conn, cfg, "PHYS-110", [{"name": "Kinematics"}])
        canvas_store.tag(conn, cfg, [{"canvas_id": 104, "topics": ["Kinematics"]}])
        ev = [e for e in mastery.evidence(conn, "PHYS-110") if e["source"] == "canvas 104"]
        assert sorted(e["credit"] for e in ev) == [0.0, 0.5, 1.0, 1.0]  # one result per question, not one for the whole quiz
        # a quiz whose results are hidden from students still counts once, by its score
        conn.execute("DELETE FROM canvas_quiz_questions")
        ev = [e for e in mastery.evidence(conn, "PHYS-110") if e["source"] == "canvas 104"]
        assert [e["credit"] for e in ev] == [0.625]
