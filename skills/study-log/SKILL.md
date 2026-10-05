---
name: study-log
description: >
  Bookkeeping at the end of a study session: run study-log.py (topics.json tracking, fuzzy_until,
  Meta/study-sessions.json time log) and append the session summary to today's daily note.
  Called by the study skill with a session ID; not a user trigger.
context: fork
model: haiku
effort: low
---

Resolve `{{meta}}`, `{{daily}}` from `Meta/vault-map.md` (this literal path); if absent use `Meta`, `07-Daily`. Bash from the vault root, relative paths, one command per call, no `cd`.

1. Run `My-Brain-Is-Full-Crew/personal/scripts/study-log.py log`. It updates topics.json and `{{meta}}/study-sessions.json` and prints JSON. If it fails, or its `session.session_id` isn't the ID you were given, stop and report the error. Never edit those JSON files yourself.
2. Read `{{meta}}/study-session-state.json`.
3. Today's note is `{{daily}}/<date +%F>.md`. If it already contains the session ID, skip to 4. If it doesn't exist, create it with frontmatter `type: daily`, `date: "<today>"`, `tags: [daily]`. Append:

```markdown

## Study: <topic> (<session_id>)
- Time: <actual_minutes> of <planned_minutes> min, energy <energy_level>
- Brain dump: <dump_quality_score>. Gaps: <gaps_identified>. Strong: <strong_areas>
- <mode>: <correct>/<reviewed or answered> right first time, <time_spent_min> of <planned_min> min (one line per mode)
- Fuzzy: <fuzzy_areas, or "nothing"> (due again until <fuzzy_until>)
```

Use the script's `session` for times and `fuzzy_until`; the state file for the rest. Leave out lines with no data.

4. Reply in at most 2 lines: topics updated, minutes used vs planned, fuzzy_until if any, and the daily note path. If `already_logged` was true, say so.
