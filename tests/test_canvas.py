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
        "/api/v1/courses/1/files": [{"id": 501, "display_name": "Syllabus.pdf", "url": "SERVER/dl/501", "updated_at": "2026-08-20T00:00:00Z", "size": 10},
                                     {"id": 502, "display_name": "Old notes.pdf", "url": "SERVER/dl/502", "updated_at": "2026-08-20T00:00:00Z", "size": 10}],
        "/api/v1/courses/1/modules": [
            {"id": 1, "name": "Week 1: Motion", "position": 1, "items": [
                {"type": "SubHeader", "title": "Readings"},
                {"type": "File", "title": "Lecture 1 slides", "content_id": 501},
                {"type": "Page", "title": "How to study", "page_url": "how-to-study"},
                {"type": "ExternalUrl", "title": "Worksheet", "external_url": "SERVER/ext/worksheet.pdf"},
                {"type": "ExternalUrl", "title": "Video", "external_url": "https://video.example/abc"},
                {"type": "File", "title": "Locked exam key", "content_id": 599},
                {"type": "Assignment", "title": "Lab 1", "content_id": 77}]},
            {"id": 2, "name": "Week 2: Forces", "position": 2, "items_url": "SERVER/api/v1/courses/1/modules/2/items"}],
        "/api/v1/courses/1/modules/2/items": [{"type": "File", "title": "Forces notes", "content_id": 503}],
        "/api/v1/courses/1/files/501": {"id": 501, "display_name": "Lecture 1 slides.pdf", "url": "SERVER/dl/501", "updated_at": "2026-08-20T00:00:00Z", "size": 10},
        "/api/v1/courses/1/files/503": {"id": 503, "display_name": "Forces notes.pdf", "url": "SERVER/dl/503", "updated_at": "2026-08-27T00:00:00Z", "size": 10},
        "/api/v1/courses/1/files/599": {"id": 599, "display_name": "Key.pdf", "locked_for_user": True},
        "/api/v1/courses/1/pages/how-to-study": {"title": "How to study", "updated_at": "2026-08-20T00:00:00Z", "body":
            "<p>Read <b>before</b> lecture.</p><p><a href='/courses/1/files/504/download?wrap=1'>Study guide</a> and "
            "<a class='instructure_file_link' data-api-endpoint='SERVER/api/v1/courses/1/files/505' href='SERVER/courses/1/files/505?verifier=x'>Formula sheet</a>, "
            "plus <a href='https://publisher.example/ch2.pdf'>chapter 2</a> and <a href='https://video.example/v'>a video</a>.</p>"},
        "/api/v1/courses/1/files/504": {"id": 504, "display_name": "Study guide.pdf", "url": "SERVER/dl/504", "updated_at": "2026-08-20T00:00:00Z", "size": 10},
        "/api/v1/courses/1/files/505": {"id": 505, "display_name": "Formula sheet.pdf", "url": "SERVER/dl/505", "updated_at": "2026-08-20T00:00:00Z", "size": 10},
        "/api/v1/courses/1/assignments/77": {"name": "Lab 1", "description": "<p>Use <a href='/courses/1/files/506/download'>the lab handout</a>.</p>", "due_at": "2026-09-01T00:00:00Z"},
        "/api/v1/courses/1/files/506": {"id": 506, "display_name": "Lab handout.pdf", "url": "SERVER/dl/506", "updated_at": "2026-08-20T00:00:00Z", "size": 10},
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
        if path.startswith(("/dl/", "/ext/")):
            body = f"%PDF-1.4 {path}".encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/pdf")
            self.end_headers()
            self.wfile.write(body)
            return
        data = canvas_data().get(path)
        if data is None:
            self.send_response(404)
            self.end_headers()
            return
        body = json.dumps(data).replace("SERVER", f"http://127.0.0.1:{self.server.server_port}").encode()
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


def test_messy_real_canvas_data_is_skipped_not_fatal(env, server, monkeypatch):
    cfg, _ = env
    real = canvas_data

    def messy():
        d = real()
        d["/api/v1/courses"][0]["enrollments"].append(None)
        d["/api/v1/courses/1/assignments"].append(None)
        d["/api/v1/courses/1/assignments"].append({"id": 105, "name": None, "points_possible": None, "submission": None})
        d["/api/v1/courses/1/students/submissions"].append(None)
        d["/api/v1/courses/1/students/submissions"][0]["submission_comments"] = [None, {"id": 901, "comment": "ok"}]
        d["/api/v1/courses/1/students/submissions"][2]["submission_history"].append(None)
        return d

    monkeypatch.setattr(__import__(__name__), "canvas_data", messy)
    api = CanvasApi(server, None, cfg, cookies={"canvas_session": "good"})
    api.fetch()
    with db.connect() as conn:
        c = canvas_store.save(conn, api)
        assert c["submissions"] == 3 and c["new_comments"] == 1


def test_forbidden_is_not_signed_out():
    import requests as rq

    from oso.connectors.canvas_api import _signed_out

    def resp(code, body):
        r = rq.Response()
        r.status_code = code
        r._content = body.encode()
        return r

    assert _signed_out(resp(401, '{"status":"unauthenticated","errors":[{"message":"user authorization required"}]}'))
    assert not _signed_out(resp(401, '{"status":"unauthorized","errors":[{"message":"user not authorized to perform that action"}]}'))
    assert not _signed_out(resp(404, "{}"))



def test_modules_files_pages_and_links(env, server):
    cfg, _ = env
    api = CanvasApi(server, None, cfg, cookies={"canvas_session": "good"})
    api.fetch()
    counts = api.mirror()
    assert counts["module_files"] == 6 and counts["module_pages"] == 2 and counts["files"] == 1  # Syllabus.pdf came via the module
    mods = cfg.vault / "Courses" / "2026 Fall" / "Physics" / "Canvas" / "Modules"
    assert (mods / "01 Week 1 Motion" / "Lecture 1 slides.pdf").read_bytes().startswith(b"%PDF")
    assert (mods / "01 Week 1 Motion" / "worksheet.pdf").exists() and (mods / "02 Week 2 Forces" / "Forces notes.pdf").exists()
    assert not list(mods.rglob("Key.pdf"))
    page = (mods / "01 Week 1 Motion" / "How to study.md").read_text(encoding="utf-8")
    assert "type: canvas-page" in page and "Read before lecture." in page
    index = (mods / "Modules.md").read_text(encoding="utf-8")
    assert "## Week 1: Motion" in index and "### Readings" in index and "Locked exam key (locked or unavailable)" in index
    week1 = mods / "01 Week 1 Motion"
    for name in ("Study guide.pdf", "Formula sheet.pdf", "Lab handout.pdf"):
        assert (week1 / name).read_bytes().startswith(b"%PDF"), name
    assert "## Files linked here" in page and "Formula sheet.pdf]]" in page
    lab = (week1 / "Assignment - Lab 1.md").read_text(encoding="utf-8")
    assert "type: canvas-assignment" in lab and "Lab handout.pdf]]" in lab and "due: '2026-09-01" in lab
    assert "[Video](https://video.example/abc)" in index and "[[Courses/2026 Fall/Physics/Canvas/Modules/01 Week 1 Motion/How to study|How to study]]" in index
    assert (cfg.vault / "Courses/2026 Fall/Physics/Canvas/Old notes.pdf").exists() and not (cfg.vault / "Courses/2026 Fall/Physics/Canvas/Syllabus.pdf").exists()
    with db.connect() as conn:
        canvas_store.record_new_files(conn, api.new_files, now="2026-11-01T12:00:00+00:00")
        assert [r["text"] for r in canvas_store.recent_events(conn, datetime(2026, 11, 1, 9, 0, tzinfo=TZ))] == ["Downloaded 7 files from Canvas modules and files"]
        again = api.mirror()
        assert again["module_files"] == 0 and again["files"] == 0 and api.new_files == []  # unchanged: nothing downloaded twice
