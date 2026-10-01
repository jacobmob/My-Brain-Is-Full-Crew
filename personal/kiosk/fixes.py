"""Fixing bad cards (0.13): delete, edit, flag, restore.

Every change lands in card-edits/<topic>.json (and _stats.json); card files are never touched.
A deleted or flagged card keeps any earlier edit under "previous", so restore brings it back.
"""
from datetime import datetime

import store


class Conflict(Exception):
    pass


EVENTS = store.META / "events" / "study-skill"


def _require(course, topic, cid):
    try:
        card = store.find_any_card(course, topic, cid)
    except KeyError:
        card = None
    if card is None:
        raise KeyError(cid)
    return card


def _stamp():
    return {"date": store.today(), "time": store.now_iso()}


def _withdraw_event(entry):
    """Un-flagging before the 3 AM batch picked the event up: remove it so nothing gets rewritten."""
    if entry and entry.get("event"):
        (EVENTS / entry["event"]).unlink(missing_ok=True)


def _kept_edit(prev):
    """The edit to keep under "previous" when a card is deleted or flagged."""
    if prev and prev.get("action") in ("deleted", "flagged"):
        prev = prev.get("previous")
    return prev if prev and prev.get("action") == "edited" else None


def _check_reason(reason):
    if reason is not None and reason not in store.DELETE_REASONS:
        raise ValueError(f"reason must be one of {store.DELETE_REASONS}")


def delete(course, topic, cid, reason=None):
    _check_reason(reason)
    _require(course, topic, cid)

    def fn(edits):
        prev = edits.get(cid)
        if prev and prev.get("action") == "deleted":
            return prev
        if prev and prev.get("action") == "flagged":
            _withdraw_event(prev)
        entry = {"action": "deleted", "reason": reason, **_stamp()}
        if kept := _kept_edit(prev):
            entry["previous"] = kept
        edits[cid] = entry
        return entry

    return store.mutate_edits(course, topic, fn)


def set_reason(course, topic, cid, reason):
    _check_reason(reason)
    _require(course, topic, cid)

    def fn(edits):
        e = edits.get(cid)
        if not e or e.get("action") != "deleted":
            raise Conflict("card is not deleted")
        e["reason"] = reason
        return e

    return store.mutate_edits(course, topic, fn)


def edit(course, topic, cid, question, answer, reset_schedule=False):
    _require(course, topic, cid)
    original = next(c for c in store.raw_cards(course, topic) if c.get("id") == cid)
    question, answer = question.strip(), answer.strip()
    if not question or not answer:
        raise ValueError("question and answer can't be empty")

    def fn(edits):
        prev = edits.get(cid)
        if prev and prev.get("action") in ("deleted", "flagged"):
            raise Conflict(f"card is {prev['action']}")
        override = {}
        if question != original.get("question"):
            override["front"] = question
        if answer != original.get("answer"):
            override["back"] = answer
        stamp = _stamp()
        # An earlier reset stays in force: dropping it would bring back the pre-edit schedule.
        reset_time = stamp["time"] if reset_schedule else (prev or {}).get("reset_time")
        if not override and not reset_time:
            edits.pop(cid, None)           # edited back to the original
            return None
        entry = {"action": "edited", **stamp, "reset_schedule": bool(reset_time), "override": override}
        if reset_time:
            entry["reset_time"] = reset_time
        edits[cid] = entry
        return entry

    return store.mutate_edits(course, topic, fn)


def flag(course, topic, cid, note=None):
    card = _require(course, topic, cid)
    note = (note or "").strip() or None

    def fn(edits):
        prev = edits.get(cid)
        if prev and prev.get("action") == "deleted":
            raise Conflict("card is deleted")
        if prev and prev.get("action") == "flagged":
            _withdraw_event(prev)          # re-flag: replace the event with the new note
        now = datetime.now()
        name = f"evt_{now:%Y%m%dT%H%M%S}_kiosk_card-flagged_{cid}.json"
        event = {
            "from": "kiosk", "to": "study-skill", "type": "card-flagged",
            "summary": f"Rewrite {course} card {cid}" + (f": {note}" if note else ""),
            "refs": [f"{course}/{topic}"],
            "timestamp": now.isoformat(timespec="seconds"), "priority": "normal",
            "course": course, "topic": topic, "card_id": cid,
            "card_file": f"03-Resources/study/{course}/cards/{topic}.json",
            "note": note, "question": card["question"], "answer": card["answer"],
        }
        EVENTS.mkdir(parents=True, exist_ok=True)
        store.write_json_atomic(EVENTS / name, event)
        entry = {"action": "flagged", "note": note, **_stamp(), "event": name}
        if kept := _kept_edit(prev):
            entry["previous"] = kept
        edits[cid] = entry
        return entry

    return store.mutate_edits(course, topic, fn)


def restore(course, topic, cid):
    """Undo a delete, flag or edit: remove the entry, or put back the edit it was hiding."""
    _require(course, topic, cid)

    def fn(edits):
        e = edits.get(cid)
        if not e:
            return None
        if e.get("action") == "flagged":
            _withdraw_event(e)
        if e.get("previous"):
            edits[cid] = e["previous"]
        else:
            edits.pop(cid)
        return edits.get(cid)

    return store.mutate_edits(course, topic, fn)
