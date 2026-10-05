"""Grade standing and the what-if calculation.

Items carry a `weight`: the percentage of the course grade their category is worth (from the Canvas
assignment group or the syllabus). Items of the same kind with the same weight form one category.
Within a category, ungraded items are assumed to count the same as the graded ones, by item count.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict

from .db import EFFECTIVE


def summary(conn: sqlite3.Connection, course: str) -> dict:
    rows = conn.execute(
        f"""SELECT id, kind, grade_points, grade_max, {EFFECTIVE} FROM items
            WHERE deleted_at IS NULL AND merged_into IS NULL AND COALESCE(user_course, course_code) = ?""",
        (course,),
    ).fetchall()
    groups: dict[tuple[str, float], list] = defaultdict(list)
    unweighted = []
    for r in rows:
        if r["weight"] is None:
            unweighted.append(r)
        else:
            groups[(r["kind"], float(r["weight"]))].append(r)

    categories = []
    earned = 0.0
    locked = 0.0
    total_weight = sum(w for _, w in groups)
    for (kind, weight), items in sorted(groups.items(), key=lambda kv: -kv[0][1]):
        graded = [r for r in items if r["grade_points"] is not None and r["grade_max"]]
        score = (sum(r["grade_points"] for r in graded) / sum(r["grade_max"] for r in graded)) if graded else None
        frac = len(graded) / len(items) if items else 0.0
        if score is not None:
            earned += weight * score * frac
            locked += weight * frac
        categories.append(
            {
                "kind": kind,
                "weight": weight,
                "items": len(items),
                "graded": len(graded),
                "score_percent": round(score * 100, 1) if score is not None else None,
                "examples": [r["title"] for r in items[:3]],
            }
        )
    current = round(earned / locked * 100, 1) if locked else None
    return {
        "course": course,
        "current_percent": current,
        "weight_graded_so_far": round(locked, 1),
        "weight_remaining": round(max(total_weight - locked, 0.0), 1),
        "weights_sum_to": round(total_weight, 1),
        "categories": categories,
        "graded_items_without_weight": [
            {"title": r["title"], "points": r["grade_points"], "max": r["grade_max"]}
            for r in unweighted if r["grade_points"] is not None
        ],
        "assumption": "A category is items of one kind sharing a weight. Within it, ungraded items count the same as graded ones, by count.",
    }


def what_if(conn: sqlite3.Connection, course: str, target_percent: float) -> dict:
    s = summary(conn, course)
    remaining = s["weight_remaining"]
    locked = s["weight_graded_so_far"]
    earned = (s["current_percent"] or 0.0) / 100 * locked
    if remaining <= 0:
        return {**s, "target_percent": target_percent, "needed_average_percent": None,
                "note": "Nothing is left to grade; the course grade is what it is."}
    needed = (target_percent - earned) / remaining * 100
    note = None
    if needed > 100:
        note = f"Not reachable: even perfect scores on the rest give {round(earned + remaining, 1)}%."
    elif needed <= 0:
        note = "Already secured, even with zeros on the rest."
    return {**s, "target_percent": target_percent, "needed_average_percent": round(needed, 1), "note": note}
