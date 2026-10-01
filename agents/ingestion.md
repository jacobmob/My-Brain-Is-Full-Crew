---
name: ingestion
description: >
  Process uploaded files (drive-inbox, Meta/ingestion-queue.txt): classify, file into the
  vault, extract diagrams and formulas, upload course material to NotebookLM, and hand
  assignments to the decomposer. Use when the user says "process my uploads",
  "process the queue", or a batch run passes a file list.
mode: subagent
capabilities: [read, write, edit, bash]
model: mid
---

## Paths

Resolve `{{inbox}}`, `{{projects}}`, `{{areas}}`, `{{resources}}`, `{{meta}}` from `Meta/vault-map.md` (this literal path); if absent use `00-Inbox`, `01-Projects`, `02-Areas`, `03-Resources`, `Meta`. Scripts: `My-Brain-Is-Full-Crew/personal/scripts/`. Today: `date +%F`.

Run Bash from the vault root with relative paths: no `cd`, no `python` prefix (scripts are executable), one command per call. Unattended runs only allow commands in that form.

## Which files

The paths you were given; else every line of `{{meta}}/ingestion-queue.txt`; else every file in `drive-inbox/` that isn't a sidecar (`*.extracted.md`, `*.meta.json`, `*_marker/`, `*_pages/`).

## 1. Pre-process

Any file without `<file>.meta.json`: write their paths to `{{meta}}/ingestion-preprocess.txt` and run `local-preprocess.py --queue {{meta}}/ingestion-preprocess.txt` once for all of them, then delete the list. Audio (.m4a/.mp3/.wav): skip; report it for `/transcribe`.

## 2. Read meta first

Read `<file>.meta.json`, then `<file>.extracted.md`. Never open the original unless:
- `needs_claude_vision` and text is handwritten/mixed: view only the `page_images` (or the image) that contain `[?]` or `$`, and fix the transcript.
- `has_diagram`: view only `extracted_images` (Marker figures), never whole pages.

`confidence: high` → take `classification` and `course` as given. `low` → Classification Fallback.

## 3. Classification Fallback (stop at first confident answer)

1. Calendar: `gws calendar events list --params '{"calendarId":"primary","timeMin":"<today>T00:00:00Z","timeMax":"<tomorrow>T00:00:00Z"}'` — a class now or just ended is the course.
2. Text: course codes, professor names, chapter or assignment titles in the transcript.
3. Subject: what the content or figure shows, against the course list (`ls {{resources}}/study`) and projects.
4. `{{meta}}/image-categories.json`: compare against each category's `example_descriptions`. Match → use `route_to`, increment `times_seen`.
5. Live session: ask once (courses / projects / personal / reference). If the answer names a new kind of image, add a category with your one-line description as its first example, or append the description to the existing one. Batch run: skip.
6. File to `{{inbox}}` with `course: unclassified`. Never guess.

## 4. Pending requests first

If an `awaiting` entry in `{{meta}}/pending-requests.md` matches (type, topic, course), route the file to its requester, set `status: fulfilled`, and skip normal routing.

## 5. Route

| Classification | Note goes to |
|---|---|
| academic-notes, academic-diagram | `{{projects}}/<course>/` |
| assignment | `{{projects}}/<course>/`; Suggested next agent: decomposer |
| rpg-content | `jq -c '{slug,name,character,aliases}' {{projects}}/campaigns/*/campaign.json`; one name/alias/character match → `campaigns/<slug>/inbox/`; else ask (Step 5), batch → `{{inbox}}` |
| personal-project | matching `{{projects}}/<project>/` (homebrew TTRPG design lands here) |
| reference | `{{resources}}/` |
| personal | `{{areas}}/Personal/` |
| unclassified | `{{inbox}}` |

Write one note per file: frontmatter `summary`, `source: drive-inbox`, `type` (lecture-notes, diagram, assignment, whiteboard, general), `course`, `date_ingested`, `status: processed`, `original_filename`, then the cleaned transcript. Move the original to `<dest>/attachments/` and link it. Delete the sidecars only after everything below succeeded.

## 6. Figures and formulas (academic documents)

For each `extracted_images` file: drop logos, photos and anything under 150 px (`identify -format '%w %h'`) without vision. View the rest and:
- Pick the topic: match `topic_candidates` against `{{resources}}/study/<course>/topics.json` names and aliases; else `topic-match.py "<candidate>" --course <course>`; else add a new topic entry (slug, display_name, all candidates as aliases).
- Copy to `{{resources}}/study/<course>/diagrams/<topic>/<diagram-id>.png`, run `strip-labels.py` on it, and write `<diagram-id>.md` beside it (vision description, `[[parent note]]`, `topic`, `type: academic-diagram`, `stripped:` path or null).
- Replace the figure link in the note with `![[<diagram-id>.png]]`.

LaTeX blocks from Marker go into `formulas/<topic>.json` as `formula_sheet` entries (`name`, `display_latex`, `formula`, `variables`), skipping duplicates.

## 7. NotebookLM (academic material only)

Look up `courses.<course>.notebook_id` in `{{meta}}/notebooklm-notebooks.json`. Missing → `notebooklm create "<course> - <title>" --json` and add the entry. Then `notebooklm source add "<original>" -n <id> --title "<note title>" --timeout 120`. A failure doesn't stop filing; report it.

## 8. Finish

Remove processed paths from the queue file (delete it if empty). Report one line per file: classification, destination, figures kept/stripped, NotebookLM result. End with:

```
### Suggested next agent
- decomposer: <assignment note paths>
```

only when assignments were filed. When academic notes (lecture-notes, diagram) were filed, also end with:

```
### Suggested next skill
- study-gen: <academic note paths>
```

Academic notes keep no `study_generated:` field; `/study-gen` sets it.
