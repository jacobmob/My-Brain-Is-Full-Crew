"""The Kiosk (blueprint 0.13): local web app for studying, zero Claude tokens.

Run: uvicorn app:app --host 127.0.0.1 --port 8484   (personal/scripts/kiosk.sh)
"""
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

import fixes
import scheduler
import sessions
import store

HERE = Path(__file__).parent
app = FastAPI(title="Kiosk", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
templates = Jinja2Templates(directory=HERE / "templates")

PUBLIC = ("id", "course", "topic", "question", "answer", "image", "image_reveal", "source_note")


def public(card: dict) -> dict:
    return {k: card.get(k) for k in PUBLIC} | {"is_new": "_due" not in card}


@app.get("/")
def root():
    return RedirectResponse("/review")


@app.get("/health")
def health():
    return {"ok": True}


def page(request: Request, name: str, title: str):
    return templates.TemplateResponse(request, f"{name}.html", {"title": title, "page": name})


@app.get("/review")
def review_page(request: Request):
    return page(request, "review", "Review")


@app.get("/cards")
def cards_page(request: Request):
    return page(request, "cards", "Cards")


@app.get("/trash")
def trash_page(request: Request):
    return page(request, "trash", "Trash")


# ---------- study sessions (deck spec written by the study skill) ----------

@app.get("/s/{session_id}/flashcards")
def session_flashcards_page(request: Request, session_id: str):
    return templates.TemplateResponse(request, "review.html", {
        "title": "Flashcards", "page": "session",
        "deck_src": f"/api/s/{session_id}/flashcards", "session_id": session_id})


@app.get("/api/s/{session_id}/flashcards")
def session_flashcards(session_id: str):
    try:
        deck = sessions.build_deck(sessions.load_spec(session_id, "flashcards"))
    except sessions.NoSession:
        raise HTTPException(404, "This session isn't active. Ask Claude for a new link.")
    deck["cards"] = [public(c) for c in deck["cards"]]
    return deck


class Attempt(BaseModel):
    course: str
    topic: str
    id: str
    rating: str = Field(pattern="^(again|hard|good|easy)$")
    confidence: int = Field(ge=1, le=5)


class Removed(BaseModel):
    course: str
    topic: str
    id: str


class FinishIn(BaseModel):
    results: list[Attempt] = Field(default_factory=list, max_length=5000)
    removed: list[Removed] = Field(default_factory=list, max_length=1000)
    minutes: float = Field(ge=0, le=24 * 60)
    deck: int = Field(ge=0)


@app.post("/api/s/{session_id}/flashcards/finish")
def session_flashcards_finish(session_id: str, f: FinishIn):
    try:
        sessions.load_spec(session_id, "flashcards")
    except sessions.NoSession:
        raise HTTPException(404, "This session isn't active, so the summary wasn't saved.")
    summary = sessions.summarize(session_id, "flashcards", [a.model_dump() for a in f.results],
                                 [r.model_dump() for r in f.removed], f.minutes, f.deck)
    sessions.write_summary(summary)
    return summary


@app.get("/api/review/due")
def review_due(limit: int | None = None):
    cards = store.due_cards()
    if limit:
        cards = cards[:limit]
    return {"cards": [public(c) for c in cards]}


class ReviewIn(BaseModel):
    course: str
    topic: str
    id: str
    rating: str = Field(pattern="^(again|hard|good|easy)$")
    confidence: int = Field(ge=1, le=5)
    duration_ms: int | None = Field(default=None, ge=0)


@app.post("/api/review")
def review_card(r: ReviewIn):
    try:
        card = store.find_card(r.course, r.topic, r.id)
    except KeyError:
        card = None
    if card is None:
        raise HTTPException(404, "card not found")

    correct = r.rating != "again"
    result = {}

    def apply(entry):
        new_fsrs, applied, log = scheduler.review(
            store.card_fsrs(card, {"cards": {r.id: entry}}), r.rating, r.confidence, r.course, r.duration_ms)
        entry["fsrs"] = new_fsrs
        entry["times_reviewed"] = entry.get("times_reviewed", 0) + 1
        entry["times_correct"] = entry.get("times_correct", 0) + int(correct)
        entry["last_rating"] = applied
        entry.setdefault("confidence_history", []).append(
            {"date": store.today(), "confidence": r.confidence, "correct": correct})
        result.update(applied=applied, due=new_fsrs["due"], log=log)

    store.update_review_state(r.course, r.topic, r.id, apply)
    store.append_jsonl(store.review_log_path(r.course), result.pop("log") | {
        "course": r.course, "topic": r.topic, "id": r.id,
        "rating_given": r.rating, "rating_applied": result["applied"],
        "confidence": r.confidence,
    })
    return result


@app.get("/media/{course}/{path:path}")
def media(course: str, path: str):
    """Images referenced by cards, relative to the course folder (e.g. diagrams/<topic>/x.png)."""
    try:
        base = store.course_dir(course)
    except KeyError:
        raise HTTPException(404)
    f = (base / path).resolve()
    if not f.is_relative_to(base) or not f.is_file():
        raise HTTPException(404)
    return FileResponse(f)


# ---------- fixing bad cards ----------

def browse_row(card: dict, state: dict) -> dict:
    entry = state.get("cards", {}).get(card["id"]) or {}
    fs = store.card_fsrs(card, state)
    e = card["_edit"] or {}
    reviews = entry.get("times_reviewed", 0)
    return public(card) | {
        "is_new": fs is None, "status": card["status"],
        "reason": e.get("reason"), "note": e.get("note"),
        "changed": e.get("time") or e.get("date"),
        "reviews": reviews, "fails": reviews - entry.get("times_correct", 0),
        "due": fs["due"] if fs else None,
    }


def all_rows():
    for course in store.courses():
        for topic in store.topics(course):
            state = store.load_review_state(course, topic)
            for card in store.annotated_cards(course, topic):
                yield browse_row(card, state)


@app.get("/api/cards")
def cards_list():
    """Every card (deleted ones too, for /trash) with its status and review stats."""
    return {"cards": list(all_rows()), "reasons": store.DELETE_REASONS,
            "courses": {c: store.topics(c) for c in store.courses()}}


@app.get("/api/trash")
def trash_list():
    rows = [r for r in all_rows() if r["status"] == "deleted"]
    rows.sort(key=lambda r: store.parse_time(r["changed"]), reverse=True)
    return {"cards": rows}


class FixIn(BaseModel):
    reason: str | None = None
    note: str | None = Field(default=None, max_length=1000)
    question: str | None = Field(default=None, max_length=5000)
    answer: str | None = Field(default=None, max_length=5000)
    reset_schedule: bool = False


ACTIONS = {
    "delete": lambda c, t, i, b: fixes.delete(c, t, i, b.reason),
    "reason": lambda c, t, i, b: fixes.set_reason(c, t, i, b.reason),
    "edit": lambda c, t, i, b: fixes.edit(c, t, i, b.question or "", b.answer or "", b.reset_schedule),
    "flag": lambda c, t, i, b: fixes.flag(c, t, i, b.note),
    "restore": lambda c, t, i, b: fixes.restore(c, t, i),
}


def run_fix(action, course, topic, cid, body):
    if action not in ACTIONS:
        raise HTTPException(404, "unknown action")
    try:
        ACTIONS[action](course, topic, cid, body)
    except KeyError:
        raise HTTPException(404, "card not found")
    except ValueError as e:
        raise HTTPException(422, str(e))
    except fixes.Conflict as e:
        raise HTTPException(409, str(e))
    card = store.find_any_card(course, topic, cid)
    return browse_row(card, store.load_review_state(course, topic))


@app.post("/api/card/{course}/{topic}/{cid}/{action}")
def card_fix(course: str, topic: str, cid: str, action: str, body: FixIn | None = None):
    return run_fix(action, course, topic, cid, body or FixIn())


class Ref(BaseModel):
    course: str
    topic: str
    id: str


class BulkIn(FixIn):
    action: str = Field(pattern="^(delete|flag|restore)$")
    items: list[Ref] = Field(min_length=1, max_length=1000)


@app.post("/api/cards/bulk")
def cards_bulk(b: BulkIn):
    done, failed = [], []
    for it in b.items:
        try:
            done.append(run_fix(b.action, it.course, it.topic, it.id, b))
        except HTTPException as e:
            failed.append({"course": it.course, "topic": it.topic, "id": it.id, "error": e.detail})
    return {"cards": done, "failed": failed}
