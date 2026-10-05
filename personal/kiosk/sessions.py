"""Study-session decks (0.13): /s/{id}/<mode> pages built from the deck spec the study skill
writes into Meta/study-session-state.json, and the summary the Kiosk writes back on Finish.

The study skill is the only writer of the state file; the Kiosk only reads it. The summary goes to
Meta/events/study-skill/<session_id>-<mode>.json.
"""
import random
import re
from collections import Counter
from datetime import datetime, timezone

import store

STATE = store.META / "study-session-state.json"
EVENTS = store.META / "events" / "study-skill"
SESSION_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
FILTERS = ("due", "weak", "all")
PRIMARY_SHARE = 0.6        # interleaved decks: primary topic 60%, related topics share 40% (2.2f)
MAX_RUN = 3                # never more than 3 cards in a row from one topic
MAX_RELATED = 3


class NoSession(Exception):
    pass


def load_spec(session_id: str, mode: str) -> dict:
    """The kiosk block for this session, or NoSession if the link is stale or for another mode."""
    if not SESSION_ID.match(session_id):
        raise NoSession(session_id)
    state = store.read_json(STATE) or {}
    spec = state.get("kiosk") or {}
    if state.get("session_id") != session_id or spec.get("mode") != mode:
        raise NoSession(session_id)
    try:
        store.course_dir(spec.get("course") or "")
    except KeyError:
        raise NoSession(session_id)
    return spec


def topic_registry(course: str) -> dict:
    return (store.read_json(store.course_dir(course) / "topics.json") or {}).get("topics", {})


def expand(slugs, registry, with_subtopics, have) -> list[str]:
    """Topics plus (optionally) their subtopics, deduplicated, keeping only topics with a card file."""
    out = []
    for slug in slugs or []:
        group = [slug] + (list((registry.get(slug) or {}).get("subtopics") or []) if with_subtopics else [])
        out += [t for t in group if t in have and t not in out]
    return out


def _pool(course: str, topic: str, flt: str, now: datetime, fuzzy: set[str]) -> list[dict]:
    """One topic's cards for the deck, in review order: overdue first (oldest due first), then new.
    Fuzzy topics' cards count as due (store.due_at).
    "weak" keeps reviewed cards last rated Again/Hard or under 70% right, worst first."""
    state = store.load_review_state(course, topic)
    due, new, rest, weak = [], [], [], []
    for card in store.load_cards(course, topic):
        fs = store.card_fsrs(card, state)
        entry = state.get("cards", {}).get(card["id"]) or {}
        if flt == "weak":
            n, right = entry.get("times_reviewed", 0), entry.get("times_correct", 0)
            if fs and n and (entry.get("last_rating") in ("again", "hard") or right / n < 0.7):
                weak.append((right / n, card))
            continue
        if fs is None:
            new.append(card)
        elif due_key := store.due_at(card, fs, now, fuzzy):
            card["_due"] = due_key
            due.append(card)
        elif flt == "all":
            rest.append((fs["due"], card))
    if flt == "weak":
        return [c for _, c in sorted(weak, key=lambda x: x[0])]
    due.sort(key=lambda c: c["_due"])
    return due + new + [c for _, c in sorted(rest, key=lambda x: x[0])]


def _allocate(pools: list[list], limit: int | None) -> list[int]:
    """How many cards to take from each pool: pools[0] (primary) gets 60%, the rest split 40%.
    Anything a short pool can't fill goes to the others, primary first."""
    sizes = [len(p) for p in pools]
    if limit is None or limit >= sum(sizes):
        return sizes
    k = len(pools) - 1
    shares = [PRIMARY_SHARE * limit] + [(1 - PRIMARY_SHARE) * limit / k] * k if k else [limit]
    take = [min(s, int(share)) for s, share in zip(sizes, shares)]
    while sum(take) < limit:
        for j in range(len(pools)):
            if take[j] < sizes[j] and sum(take) < limit:
                take[j] += 1
    return take


def _mix(pools: list[list], rng: random.Random) -> list[dict]:
    """Shuffle pools together, keeping each pool's order and never more than MAX_RUN in a row
    from one pool unless nothing else is left. Picks are weighted by cards remaining, so the
    split stays even across the deck."""
    queues = [list(p) for p in pools if p]
    out, last, run = [], None, 0
    while any(queues):
        open_ = [j for j, q in enumerate(queues) if q and not (j == last and run >= MAX_RUN)]
        if not open_:
            open_ = [j for j, q in enumerate(queues) if q]
        j = rng.choices(open_, weights=[len(queues[x]) for x in open_])[0]
        run = run + 1 if j == last else 1
        last = j
        out.append(queues[j].pop(0))
    return out


def build_deck(spec: dict, now: datetime | None = None, rng: random.Random | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    rng = rng or random.Random()
    course = spec["course"]
    flt = spec.get("filter") if spec.get("filter") in FILTERS else "due"
    limit = spec.get("limit")
    limit = limit if isinstance(limit, int) and limit > 0 else None
    registry = topic_registry(course)
    have = set(store.topics(course))
    subs = bool(spec.get("include_subtopics"))
    fuzzy = store.fuzzy_topics(course)

    primary = expand(spec.get("topics"), registry, subs, have)
    related = []
    if spec.get("interleave"):
        named = [t for t in (spec.get("related_topics") or []) if t not in primary][:MAX_RELATED]
        related = [t for t in expand(named, registry, subs, have) if t not in primary]

    # The primary topic and its subtopics form one pool, in due order across them.
    main = [c for t in primary for c in _pool(course, t, flt, now, fuzzy)]
    main.sort(key=lambda c: (0, c["_due"]) if "_due" in c else (1, ""))
    pools = [main] + [_pool(course, t, flt, now, fuzzy) for t in related]
    take = _allocate(pools, limit)
    pools = [p[:n] for p, n in zip(pools, take)]
    cards = _mix(pools, rng) if related else pools[0]

    names = {t: (registry.get(t) or {}).get("display_name") or t for t in primary + related}
    return {"cards": cards, "course": course, "topics": primary, "related_topics": related,
            "interleave": bool(related), "filter": flt, "topic_names": names}


def summarize(session_id: str, mode: str, results: list[dict], removed: list[dict],
              minutes: float, deck_size: int) -> dict:
    """The compact summary Claude reads. results: every rating in order ({course, topic, id, rating,
    confidence}). removed: cards deleted or flagged during the session. A card's first rating
    decides whether it was right; deleted and flagged cards are never weak."""
    gone = {}
    for r in removed:
        try:
            card = store.find_any_card(r["course"], r["topic"], r["id"])
        except KeyError:
            continue
        if card and card["status"] in ("deleted", "flagged"):      # still removed (not undone)
            gone[r["id"]] = card["status"]

    first = {}
    for r in results:
        first.setdefault(r["id"], r)
    by_topic = {}
    for r in first.values():
        seen, right = by_topic.get(r["topic"], (0, 0))
        by_topic[r["topic"]] = [seen + 1, right + (r["rating"] != "again")]
    weak = [cid for cid, r in first.items() if r["rating"] == "again" and cid not in gone]
    over = list(dict.fromkeys(r["id"] for r in results
                              if r["rating"] == "again" and r["confidence"] >= 4 and r["id"] not in gone))
    reviewed = len(first)
    correct = sum(r["rating"] != "again" for r in first.values())
    statuses = Counter(gone.values())
    return {
        "from": "kiosk", "to": "study-skill", "type": "session-summary",
        "session_id": session_id, "mode": mode,
        "summary": f"{mode}: {correct}/{reviewed} right first time"
                   + (f", {statuses['deleted']} deleted" if statuses["deleted"] else "")
                   + (f", {statuses['flagged']} flagged" if statuses["flagged"] else ""),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "deck": deck_size, "reviewed": reviewed, "correct": correct,
        "weak_cards": weak, "overconfident": over,
        "deleted": [c for c, s in gone.items() if s == "deleted"],
        "flagged": [c for c, s in gone.items() if s == "flagged"],
        "minutes": max(1, round(minutes)) if reviewed else round(minutes),
        "by_topic": by_topic,
    }


def write_summary(summary: dict) -> str:
    name = f"{summary['session_id']}-{summary['mode']}.json"
    store.write_json_atomic(EVENTS / name, summary)
    return name
