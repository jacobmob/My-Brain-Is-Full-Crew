#!/home/jacob/.venvs/brain/bin/python
"""canvas-ics-sync.py -- zero Claude tokens (blueprint 0.5)

Downloads the Canvas calendar feed, creates a task note in 01-Projects/<code>/
for each new assignment event, and updates `due:` when a due date changes.
The feed URL is read from ~/.config/brain/canvas-feed-url and is never
written to the vault or the log.
"""
import json
import os
import re
import sys
import urllib.request
from datetime import date, datetime
from pathlib import Path

from icalendar import Calendar
from markdownify import markdownify

VAULT = Path(os.environ.get("BRAIN_VAULT", Path.home() / "brain-vault"))
FEED_FILE = Path.home() / ".config/brain/canvas-feed-url"
PROFILE = VAULT / "Meta/user-profile.md"
SEEN = VAULT / "Meta/canvas-seen.json"
EVENTS = VAULT / "Meta/events/distributor"
PROJECTS = VAULT / "01-Projects"


def log(msg):
    print(f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}", flush=True)


def fetch_feed():
    url = FEED_FILE.read_text().strip()
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            return r.read()
    except Exception as e:
        # Never echo the exception text: it can contain the URL.
        raise SystemExit(f"feed download failed ({type(e).__name__})")


def course_codes():
    """Course codes from the Routing hints section of user-profile.md."""
    text = PROFILE.read_text()
    section = text.split("## Routing hints", 1)[-1]
    return re.findall(r"^- \*\*([A-Z]+\d+(?:-\d+)?)\*\*", section, re.M)


def map_course(summary_course, codes):
    """'2026FA_ELEC_ENG_302-0_SEC20' -> 'EE302' via number match on profile codes."""
    m = re.search(r"_(\d+)-(\d+)_SEC", summary_course)
    if not m:
        return None
    num, part = m.groups()
    for key in (f"{num}-{part}", num):
        hits = [c for c in codes if re.sub(r"^[A-Z]+", "", c) == key]
        if len(hits) == 1:
            return hits[0]
    return None


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def due_of(ev):
    d = ev.decoded("DTSTART")
    return d.isoformat() if isinstance(d, (date, datetime)) else str(d)


def description_md(ev):
    html = str(ev.get("X-ALT-DESC", "")).strip()
    if html:  # icalendar leaves X- properties TEXT-escaped
        html = re.sub(r"\\([;,\\])", r"\1", html).replace("\\n", "\n")
        return markdownify(html).replace("\xa0", " ").strip()
    return str(ev.get("DESCRIPTION", "")).strip()


def load_seen():
    return json.loads(SEEN.read_text()) if SEEN.exists() else {}


def save_seen(seen):
    tmp = SEEN.with_suffix(".tmp")
    tmp.write_text(json.dumps(seen, indent=2, sort_keys=True) + "\n")
    tmp.replace(SEEN)


def find_note(uid, rec):
    p = VAULT / rec.get("note", "")
    if rec.get("note") and p.exists():
        return p
    for f in PROJECTS.rglob("*.md"):  # note was moved: find it by canvas_uid
        if f"canvas_uid: {uid}" in f.read_text()[:600]:
            return f
    return None


def write_note(code, title, due, url, uid, body):
    folder = PROJECTS / code
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{code}-{slugify(title)}.md"
    if path.exists():
        return None
    q = json.dumps
    front = "\n".join([
        "---",
        f"summary: {q(f'{code} {title}')}",
        "type: task",
        "task_type: assignment",
        f"course: {code}",
        "status: ready",
        f"due: {due}",
        f"canvas_url: {q(url)}",
        f"canvas_uid: {uid}",
        "breakdown: pending",
        "---",
    ])
    content = body or f"[Open in Canvas]({url})"
    path.write_text(f"{front}\n\n# {code} {title}\n\n{content}\n")
    return path


def emit_event(code, title, due, ref):
    EVENTS.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    evt = {
        "from": "canvas-sync",
        "to": "distributor",
        "type": "new-assignment",
        "summary": f"New Canvas assignment: {code} {title} (due {due}), breakdown pending",
        "refs": [ref],
        "timestamp": now.isoformat(timespec="seconds"),
        "priority": "normal",
    }
    name = f"evt_{now:%Y%m%dT%H%M%S}_canvas-sync_{slugify(code + '-' + title)}.json"
    (EVENTS / name).write_text(json.dumps(evt, indent=2) + "\n")


def update_due(path, due):
    text = path.read_text()
    new, n = re.subn(r"^due: .*$", f"due: {due}", text, count=1, flags=re.M)
    if n:
        path.write_text(new)
    return bool(n)


def main():
    cal = Calendar.from_ical(fetch_feed())
    codes = course_codes()
    seen = load_seen()
    created = updated = skipped = 0

    for ev in cal.walk("VEVENT"):
        uid = str(ev.get("UID", ""))
        if not uid.startswith("event-assignment-"):
            continue  # office hours and other calendar events
        m = re.match(r"^(.*?)\s*\[([^\]]+)\]\s*$", str(ev.get("SUMMARY", "")))
        if not m:
            log(f"WARN no course tag in summary for {uid}; skipped")
            skipped += 1
            continue
        title, course_name = m.group(1).strip(), m.group(2)
        code = map_course(course_name, codes)
        if not code:
            log(f"WARN no course code for {course_name!r} ({uid}); skipped, will retry")
            skipped += 1
            continue
        due = due_of(ev)
        url = str(ev.get("URL", ""))

        if uid in seen:
            if seen[uid]["due"] == due:
                continue
            note = find_note(uid, seen[uid])
            if note and update_due(note, due):
                log(f"UPDATED {code} {title}: due {seen[uid]['due']} -> {due}")
                seen[uid]["due"] = due
                save_seen(seen)
                updated += 1
            else:
                log(f"WARN due changed for {uid} but note not found; left alone")
            continue

        path = write_note(code, title, due, url, uid, description_md(ev))
        if path is None:
            log(f"WARN {code}-{slugify(title)}.md already exists; not overwritten, "
                f"{uid} not tracked")
            skipped += 1
            continue
        emit_event(code, title, due, path.stem)
        seen[uid] = {"due": due, "note": str(path.relative_to(VAULT)),
                     "first_seen": datetime.now().isoformat(timespec="seconds")}
        save_seen(seen)
        log(f"CREATED {path.relative_to(VAULT)} (due {due})")
        created += 1

    log(f"done: {created} created, {updated} updated, {skipped} skipped")


if __name__ == "__main__":
    sys.exit(main())
