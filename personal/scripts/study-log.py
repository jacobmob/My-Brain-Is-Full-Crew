#!/home/jacob/.venvs/brain/bin/python
"""study-log.py -- the JSON bookkeeping of a study session (blueprint 2.2k). Zero tokens.

  study-log.py log    Read Meta/study-session-state.json and
                      - update tracking in <course>/topics.json for the session's topics
                        (first_studied, times_studied, last_studied); topics in fuzzy_topics get
                        fuzzy_until = today + 3 days and fuzzy_areas (the Kiosk treats their
                        cards as due until then)
                      - append the session to Meta/study-sessions.json (time tracking)
                      - set logged: true in the state file
                      Prints a JSON summary. Safe to rerun: a logged session is not counted twice.
  study-log.py pace   Per-mode actual/planned minute ratio from past sessions (1.0 until a mode
                      has 3 sessions), for planning the next one.

Run from the vault root (or set BRAIN_VAULT).
"""
import json
import os
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

VAULT = Path(os.environ.get("BRAIN_VAULT", Path.cwd()))
META = VAULT / "Meta"
STUDY = VAULT / "03-Resources" / "study"
STATE = META / "study-session-state.json"
SESSIONS = META / "study-sessions.json"
FUZZY_DAYS = 3
PACE_MIN_SESSIONS = 3


def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    os.replace(tmp, path)


def minutes_since(iso):
    try:
        start = datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return None
    now = datetime.now(start.tzinfo) if start.tzinfo else datetime.now()
    return max(0, round((now - start).total_seconds() / 60))


def log():
    state = read_json(STATE)
    if not state:
        sys.exit("no study-session-state.json")
    course, sid = state["course"], state["session_id"]
    today = date.today().isoformat()
    history = read_json(SESSIONS, [])
    already = state.get("logged") or any(s.get("session_id") == sid for s in history)

    slugs = state.get("topics") or (state.get("kiosk") or {}).get("topics") or []
    fuzzy = set(state.get("fuzzy_topics") or [])
    fuzzy_until = (date.today() + timedelta(days=FUZZY_DAYS)).isoformat()
    topics_path = STUDY / course / "topics.json"
    registry = read_json(topics_path)
    if registry is None:
        sys.exit(f"no {topics_path}")
    touched, missing = [], []
    for slug in dict.fromkeys(slugs + sorted(fuzzy)):
        t = registry["topics"].get(slug)
        if t is None:
            missing.append(slug)
            continue
        if not already and slug in slugs:
            t["first_studied"] = t.get("first_studied") or today
            t["times_studied"] = (t.get("times_studied") or 0) + 1
            t["last_studied"] = today
        if slug in fuzzy:
            t["fuzzy_until"] = fuzzy_until
            t["fuzzy_areas"] = state.get("fuzzy_areas") or []
        touched.append(slug)
    write_json(topics_path, registry)

    results = state.get("mode_results") or {}
    plan = state.get("mode_plan") or {}
    modes = {m: {"planned_min": plan.get(m, r.get("planned_min")), "actual_min": r.get("time_spent_min")}
             for m, r in results.items()}
    entry = {
        "session_id": sid, "session_date": today, "course": course,
        "topic": state.get("topic"), "topics": slugs,
        "modes_used": state.get("modes_completed") or list(results),
        "planned_minutes": state.get("time_budget_min"),
        "actual_minutes": minutes_since(state.get("started")),
        "modes": modes, "energy_level": state.get("energy_level"),
        "dump_quality_score": (state.get("brain_dump_evaluation") or {}).get("dump_quality_score"),
        "fuzzy_topics": sorted(fuzzy),
    }
    if not already:
        history.append(entry)
        write_json(SESSIONS, history)
    state["logged"] = True
    state["self_assessment_complete"] = True
    state["timestamp"] = datetime.now().astimezone().isoformat(timespec="seconds")
    write_json(STATE, state)
    print(json.dumps({"already_logged": bool(already), "topics_updated": touched,
                      "missing_topics": missing,
                      "fuzzy_until": fuzzy_until if fuzzy else None, "session": entry}, indent=1))


def pace():
    ratios = {}
    for s in read_json(SESSIONS, []):
        for mode, m in (s.get("modes") or {}).items():
            if m.get("planned_min") and m.get("actual_min") is not None:
                ratios.setdefault(mode, []).append(m["actual_min"] / m["planned_min"])
    out = {mode: round(sum(r) / len(r), 2) if len(r) >= PACE_MIN_SESSIONS else 1.0
           for mode, r in ratios.items()}
    print(json.dumps({"pace": out, "sessions": {m: len(r) for m, r in ratios.items()}}))


if __name__ == "__main__":
    {"log": log, "pace": pace}.get(sys.argv[1] if len(sys.argv) > 1 else "", lambda: sys.exit(__doc__))()
