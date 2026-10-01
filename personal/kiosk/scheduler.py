"""FSRS-6 scheduling, as in blueprint 0.13."""
import json
from datetime import date, datetime, timezone

from fsrs import Card, Rating, Scheduler

import store

RATINGS = {"again": Rating.Again, "hard": Rating.Hard, "good": Rating.Good, "easy": Rating.Easy}


def load_params():
    """Personal parameters from optimize-fsrs.py once they exist; FSRS-6 defaults until then."""
    data = store.read_json(store.STUDY / "fsrs-params.json")
    if isinstance(data, dict):
        data = data.get("parameters")
    return tuple(data) if data else None


def exam_mode_retention(course):
    """0.95 while an exam countdown (2.7) is active for this course, else None."""
    data = store.read_json(store.META / "exam-countdown.json") or {}
    for c in data.get("active_countdowns", []):
        if c.get("course") == course and c.get("exam_date", "") >= date.today().isoformat():
            return 0.95
    return None


def scheduler_for(course):
    """Default 90% target recall; exam mode (2.7) raises it for one course."""
    target = exam_mode_retention(course) or 0.9
    params = load_params()
    if params:
        return Scheduler(parameters=params, desired_retention=target)
    return Scheduler(desired_retention=target)


def review(saved_state, rating, confidence, course, duration_ms=None):
    """saved_state: this card's FSRS dict (None if new). confidence: 1-5, asked before reveal.

    Returns (new fsrs dict, applied rating, review log dict).
    """
    card = Card.from_json(json.dumps(saved_state)) if saved_state else Card()
    if rating in ("good", "easy") and confidence <= 2:
        rating = "hard"                  # right but unsure -> comes back sooner
    card, log = scheduler_for(course).review_card(
        card, RATINGS[rating], datetime.now(timezone.utc), duration_ms)
    return json.loads(card.to_json()), rating, json.loads(log.to_json())
