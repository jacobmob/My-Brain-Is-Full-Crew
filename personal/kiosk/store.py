"""File layer for the Kiosk (0.13).

Card files are read-only here. The Kiosk writes only review-state/, card-edits/
and review-state/_logs/, always atomically (temp file + rename) or append-only.
"""
import json
import os
import tempfile
import threading
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

VAULT = Path(os.environ.get("KIOSK_VAULT", Path.home() / "brain-vault"))
STUDY = VAULT / "03-Resources" / "study"
META = VAULT / "Meta"

# One lock per file the Kiosk writes; uvicorn runs sync endpoints in a threadpool.
_locks = defaultdict(threading.Lock)


def lock_for(path: Path) -> threading.Lock:
    return _locks[str(path)]


def read_json(path: Path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def write_json_atomic(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False) + "\n"
    with lock_for(path), open(path, "a", encoding="utf-8") as f:
        f.write(line)
        f.flush()
        os.fsync(f.fileno())


# ---------- paths ----------

def courses() -> list[str]:
    return sorted(p.name for p in STUDY.iterdir() if p.is_dir() and (p / "cards").is_dir())


def course_dir(course: str) -> Path:
    d = (STUDY / course).resolve()
    if d.parent != STUDY.resolve() or not (d / "cards").is_dir():
        raise KeyError(course)
    return d


def topics(course: str) -> list[str]:
    return sorted(p.stem for p in (course_dir(course) / "cards").glob("*.json"))


def review_state_path(course: str, topic: str) -> Path:
    return course_dir(course) / "review-state" / f"{topic}.json"


def card_edits_path(course: str, topic: str) -> Path:
    return course_dir(course) / "card-edits" / f"{topic}.json"


def review_log_path(course: str) -> Path:
    return course_dir(course) / "review-state" / "_logs" / f"{course}.jsonl"


# ---------- cards + overlay ----------

OVERRIDE_FIELDS = {"front": "question", "back": "answer"}   # card-edits name -> card file name
DELETE_REASONS = ("wrong", "vague", "duplicate", "too easy", "not in my course")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def parse_time(s: str) -> datetime:
    """ISO timestamp or bare date (old entries) -> aware datetime."""
    t = datetime.fromisoformat(s)
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def load_edits(course: str, topic: str) -> dict:
    return (read_json(card_edits_path(course, topic)) or {}).get("edits", {})


def raw_cards(course: str, topic: str) -> list[dict]:
    if topic not in topics(course):
        raise KeyError(topic)
    return (read_json(course_dir(course) / "cards" / f"{topic}.json") or {}).get("cards", [])


def annotated_cards(course: str, topic: str) -> list[dict]:
    """Every card in the topic with the card-edits overlay applied and a "status":
    active, edited, deleted or flagged. Cards another card replaces are left out."""
    raw = raw_cards(course, topic)
    edits = load_edits(course, topic)
    replaced = {c["replaces"] for c in raw if c.get("replaces")}
    out = []
    for c in raw:
        cid = c.get("id")
        if not cid or cid in replaced:
            continue
        card = dict(c, course=course, topic=topic, status="active")
        e = edits.get(cid) or {}
        # A deleted or flagged card keeps any earlier edit under "previous"
        shown = e.get("previous") if e.get("action") in ("deleted", "flagged") else e
        if shown and shown.get("action") == "edited":
            for k, v in (shown.get("override") or {}).items():
                card[OVERRIDE_FIELDS.get(k, k)] = v
            card["status"] = "edited"
            if shown.get("reset_schedule"):
                card["_reset_since"] = shown.get("reset_time") or shown.get("date")
        if e.get("action") in ("deleted", "flagged"):
            card["status"] = e["action"]
        card["_edit"] = e or None
        out.append(card)
    return out


def load_cards(course: str, topic: str) -> list[dict]:
    """Cards that belong in decks: hides deleted, flagged (until rewritten) and replaced cards."""
    return [c for c in annotated_cards(course, topic) if c["status"] in ("active", "edited")]


def find_card(course: str, topic: str, card_id: str) -> dict | None:
    return next((c for c in load_cards(course, topic) if c["id"] == card_id), None)


def find_any_card(course: str, topic: str, card_id: str) -> dict | None:
    return next((c for c in annotated_cards(course, topic) if c["id"] == card_id), None)


# ---------- card edits (Kiosk is the only writer) ----------

def mutate_edits(course: str, topic: str, fn):
    """Read-modify-write the topic's card-edits file under its lock, then refresh _stats.json.
    fn(edits) mutates the edits dict in place and may return a value."""
    path = card_edits_path(course, topic)
    with lock_for(path):
        data = read_json(path) or {}
        edits = data.get("edits", {})
        result = fn(edits)
        write_json_atomic(path, {"topic": topic, "edits": edits})
    refresh_stats(course)
    return result


def refresh_stats(course: str) -> dict:
    """Rebuild card-edits/_stats.json from the topic overlays, so undo and restore keep it exact.
    The generator reads top_delete_reasons to avoid repeating the same flaw."""
    path = course_dir(course) / "card-edits" / "_stats.json"
    with lock_for(path):
        counts = {"deleted": 0, "flagged": 0, "edited": 0}
        reasons = defaultdict(int)
        for f in (course_dir(course) / "card-edits").glob("*.json"):
            if f.name.startswith("_"):
                continue
            for e in ((read_json(f) or {}).get("edits") or {}).values():
                action = e.get("action")
                if action in counts:
                    counts[action] += 1
                if action == "deleted":
                    reasons[e.get("reason") or "no reason"] += 1
        top = sorted((r for r in reasons if r != "no reason"), key=lambda r: -reasons[r])[:2]
        stats = {"course": course, "updated": now_iso(), **counts,
                 "deleted_by_reason": dict(sorted(reasons.items(), key=lambda kv: -kv[1])),
                 "top_delete_reasons": top}
        write_json_atomic(path, stats)
        return stats


# ---------- review state ----------

def load_review_state(course: str, topic: str) -> dict:
    return read_json(review_state_path(course, topic)) or {"topic": topic, "cards": {}, "quiz_attempts": {}}


def card_fsrs(card: dict, state: dict) -> dict | None:
    """Saved FSRS dict for a card, or None if it is new (or its schedule was reset by an edit)."""
    entry = state.get("cards", {}).get(card["id"])
    if not entry or not entry.get("fsrs"):
        return None
    reset = card.get("_reset_since")
    last = entry["fsrs"].get("last_review")
    if reset and (not last or parse_time(last) < parse_time(reset)):
        return None
    return entry["fsrs"]


def update_review_state(course: str, topic: str, card_id: str, fn) -> dict:
    """Read-modify-write one card's entry under the topic's lock. fn(entry) mutates entry."""
    path = review_state_path(course, topic)
    with lock_for(path):
        state = load_review_state(course, topic)
        state.setdefault("topic", topic)
        state.setdefault("quiz_attempts", {})
        entry = state.setdefault("cards", {}).setdefault(card_id, {
            "fsrs": None, "times_reviewed": 0, "times_correct": 0,
            "last_rating": None, "confidence_history": [],
        })
        fn(entry)
        write_json_atomic(path, state)
        return entry


def due_cards(now: datetime | None = None) -> list[dict]:
    """Every due card across all courses: overdue reviews first (oldest due first), then new cards."""
    now = now or datetime.now(timezone.utc)
    reviews, new = [], []
    for course in courses():
        for topic in topics(course):
            state = load_review_state(course, topic)
            for card in load_cards(course, topic):
                fs = card_fsrs(card, state)
                if fs is None:
                    new.append(card)
                elif datetime.fromisoformat(fs["due"]) <= now:
                    card["_due"] = fs["due"]
                    reviews.append(card)
    reviews.sort(key=lambda c: c["_due"])
    return reviews + new


def today() -> str:
    return date.today().isoformat()
