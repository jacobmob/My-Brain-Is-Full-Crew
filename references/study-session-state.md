# Study session state (`{{meta}}/study-session-state.json`)

One session at a time. The study skill writes it; the Kiosk reads `kiosk`; `study-log.py` sets `logged`.

```json
{"session_id": "study_20261005_1400", "course": "EE202",
 "topic": "<display name>", "topics": ["<primary slug>"],
 "started": "<date -Iseconds>", "time_budget_min": 30, "energy_level": 3,
 "interleave": false, "interleave_topics": [],
 "modes_planned": ["flashcards", "quiz"], "mode_plan": {"flashcards": 12, "quiz": 12},
 "modes_completed": [], "mode_results": {},
 "brain_dump_evaluation": {"gaps_identified": [], "strong_areas": [], "dump_quality_score": 0.6},
 "fuzzy_topics": [], "fuzzy_areas": [],
 "segment": 1, "step": "brain_dump", "self_assessment_complete": false, "logged": false,
 "timestamp": "<date -Iseconds>",
 "kiosk": {"mode": "flashcards", "course": "EE202", "topics": ["<slug>"], "include_subtopics": false,
           "interleave": false, "related_topics": [], "filter": "due", "limit": 24, "url": "<link>"}}
```

- `step`: `brain_dump` → `next_mode` → `kiosk_<mode>` → ... → `self_assessment` → `log` → `done`. After /compact, "next" or "done" resumes here.
- `mode_plan`: planned minutes per mode. `mode_results.<mode>.time_spent_min` is the Kiosk's `minutes`.
- `fuzzy_topics`: slugs from the self-assessment; `study-log.py log` sets their `fuzzy_until` (today + 3) and `fuzzy_areas` in topics.json, and the Kiosk treats their cards as due once a day until then.
- Time tracking: `study-log.py log` appends `{session_id, session_date, course, topic, topics, modes_used, planned_minutes, actual_minutes, modes: {mode: {planned_min, actual_min}}, energy_level, dump_quality_score, fuzzy_topics}` to `{{meta}}/study-sessions.json`. `study-log.py pace` turns it into per-mode ratios.
