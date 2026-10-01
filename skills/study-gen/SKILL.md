---
name: study-gen
description: >
  Generate flashcards, quiz questions, practice problems and formula sheets from academic
  notes, filed per topic under 03-Resources/study/<course>/. Run by the 3 AM batch and after
  "process my uploads" on notes with type academic-notes or lecture-notes and no
  study_generated date.
context: fork
model: sonnet
effort: low
disable-model-invocation: true
---

## Paths and rules

Resolve `{{projects}}`, `{{resources}}`, `{{meta}}` from `Meta/vault-map.md` (this literal path); if absent use `01-Projects`, `03-Resources`, `Meta`. `S` = `{{resources}}/study/<course>`. Today: `date +%F`. Bash from the vault root, relative paths, one command per call, no `cd`. Create missing folders with `mkdir -p`.

Notes: the paths given; else every note with `type: academic-notes|lecture-notes|diagram` and no `study_generated:`. Skip a note whose `course` has no `S/topics.json`; report it.

## Per note

1. Read the note (summary plus the sections with content if it's over ~600 lines). List its 3-5 distinct topics (concepts, never "Lecture 7" or "Homework 3"). Find its diagrams: `S/diagrams/*/*.md` whose body links `[[<note title>]]`, plus the note itself if it is a diagram note.
2. Match each topic (Topic Matching Protocol below).
3. Before writing a topic, read `S/card-edits/<topic>.json` if it exists, and `S/card-edits/_stats.json` once per course. Never recreate an item marked `deleted` (look up its text in the topic file); avoid the flaw behind the course's top two deletion reasons; skip items already in the file.
4. Generate per topic: 3-6 cards, 2-4 multiple-choice questions, 1-2 practice problems when the topic has numbers, and every formula in the note.
5. Append to the files (create with the header if missing), then update `topics.json`: add the note to `source_notes`, recount `card_count`/`quiz_count`, set `last_updated`.
6. Add `study_generated: <today>` to the note's frontmatter.

## Formats

IDs continue the highest number used in the course (check cards, quizzes and card-edits): cards `<course>_NNN`, image cards `<course>_img_NNN`, MC `<course>_qNNN`, problems `<course>_pNNN`, course lowercased. Every item gets `source_note: "[[<note title>]]"` and `created: <today>`.

- `S/cards/<topic>.json`: `{"topic","course","cards":[{"id","question","answer","source_note","created"}]}`. One fact per card; the answer stands alone.
- `S/quizzes/<topic>.json`: `{"topic","course","quizzes":[...]}`. MC: `type: multiple_choice`, `question`, 4 `options` with plausible distractors, `correct_answer` (index), `explanation`. Problem: `type: practice_problem`, `question` with `{Var}` placeholders, `variable_ranges` `{"Var":[min,max]}` with realistic values, `solution_formula`, `solution_steps`.
- `S/formulas/<topic>.json`: `{"topic","course","formula_sheet":[{"name","formula","variables","display_latex"}]}`. `formula` and `solution_formula` use only `+ - * / ^`, `exp log sqrt sin cos pi`, `;` between steps. A formula used by several topics goes in each.

## Diagrams

For each diagram note: `stripped:` set → identification cards on the stripped image (identify, label, explain each stage, inputs/outputs) with `image_reveal` the original, plus analysis cards; null → analysis only (what does R1 do, what if C1 doubled, trace the path, calculate with the labelled values, redesign). Add one `reproduction` card ("Study this for 30 seconds, then draw it from memory", `answer: null`, `image` and `image_reveal` the original). Image cards add `image`, `image_reveal` (or null), `question_type` and `topic`; paths are relative to `S`, e.g. `diagrams/<topic>/<id>-stripped.png`. File them in the diagram's own topic.

## Topic Matching Protocol

1. Write 4-6 candidate names for the concept: formal, informal, abbreviations, how a student would say it.
2. Compare every candidate with every topic slug, `display_name` and alias in `topics.json`. On several hits take the most specific (subtopic over parent).
3. On a match, add the unmatched candidates to that topic's `aliases`.
4. If the concept only makes sense inside the matched topic, make it a subtopic: own file, `parent_topic` set, slug added to the parent's `subtopics`.
5. No match: `My-Brain-Is-Full-Crew/personal/scripts/topic-match.py "<c1>" "<c2>" ... --course <course>`. `match` → use it, add all candidates as aliases. `confirm` → read its first 3 cards and decide. `none` → step 6.
6. New topic: slug is the standard name, lowercase-hyphenated, no abbreviations; `display_name` formal; all candidates as aliases; `parent_topic` if it belongs under one; `related_topics` to adjacent topics (other courses as `COURSE/slug`); `source_notes`, counts, `last_updated`, `first_studied: null`, `times_studied: 0`, `last_studied: null`.

Always prefer an existing topic over a new one.

## Finish

Write one event per run to `{{meta}}/events/study-skill/evt_<YYYYMMDDTHHMMSS>_study-gen.json`:
`{"from":"study-gen","to":"study-skill","type":"new-material","summary":"<n> cards, <n> questions, <n> formulas from <notes>","refs":["<course>/<topic>",...],"timestamp":"<ISO>","priority":"normal"}`.

Report one line per note: topics (new ones marked), counts, skipped items.
