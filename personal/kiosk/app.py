"""The Kiosk (blueprint 0.13): local web app for studying, zero Claude tokens.

Run: uvicorn app:app --host 127.0.0.1 --port 8484   (personal/scripts/kiosk.sh)
"""
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

import scheduler
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


@app.get("/review")
def review_page(request: Request):
    return templates.TemplateResponse(request, "review.html", {"title": "Review"})


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
