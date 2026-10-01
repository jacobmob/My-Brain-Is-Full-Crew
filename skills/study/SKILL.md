---
name: study
description: >
  Run a study session: resolve the topic, build a Kiosk deck and send the link, then read the
  Kiosk's summary when the user says done. Triggers: "I want to study [topic]", "study time",
  "review [course]", "quiz me on", "teach me", "exam prep"; "done"/"finished" while a study
  session is running in this conversation.
---

# Study Skill

Runs inline on the session model. Built so far: **Flashcard Review**. For any other mode (quiz, Socratic, teach-back, derive-it, diagrams), say it isn't built yet and offer flashcards.

## Paths and rules

Resolve `{{resources}}` and `{{meta}}` from `Meta/vault-map.md` (this literal path); if absent use `03-Resources`, `Meta`. `S` = `{{resources}}/study/<course>`. `STATE` = `{{meta}}/study-session-state.json`. Bash from the vault root, relative paths, one command per call, no `cd`. Never generate cards and never read card or review-state files: the Kiosk does that.

## Orchestrator (always runs first)

1. **Resume?** If `STATE` exists, its `modes_completed` lacks a mode in `modes_planned`, and its `session_id` is from today, ask: resume it, or start fresh?
2. **Topic.** Take the topic (and course, if named) from the message; if none, ask. Find the course with `grep -il "<term>" {{resources}}/study/*/topics.json`, then read that `topics.json`. Match case-insensitively against each topic's slug, `display_name` and `aliases`. One match: use it. Several: list their display names and ask. None: say so and list the course's display names. "review [course]" with no topic: use every topic of that course.
3. **Interleave.** `first_studied` null: `interleave: false`, no related topics. Otherwise `interleave: true` and up to 3 of the topic's `related_topics`; tell the user: "You've studied this before, so I'll mix in related topics."
4. **Session ID.** `date +study_%Y%m%d_%H%M`.

## Mode: Flashcard Review

1. Check the Kiosk: `curl -s http://localhost:8484/health` must return `{"ok":true}`. If not, stop and tell the user: "The Kiosk is down. Start it with `My-Brain-Is-Full-Crew/personal/scripts/kiosk.sh` (boot.sh normally does)." Send no link.
2. Read `base_url` from `{{meta}}/kiosk.json`. Link = `<base_url>/s/<session_id>/flashcards`.
3. Write `STATE` (replace the file; keep earlier `mode_results` when resuming):

```json
{"session_id": "<id>", "topic": "<display name>", "course": "<course>",
 "interleave": false, "interleave_topics": [],
 "modes_planned": ["flashcards"], "modes_completed": [], "mode_results": {},
 "segment": 1, "timestamp": "<date -Iseconds>",
 "kiosk": {"mode": "flashcards", "course": "<course>", "topics": ["<slug>"],
           "include_subtopics": true, "interleave": false, "related_topics": [],
           "filter": "due", "limit": 25, "url": "<link>"}}
```

   `include_subtopics` is true when the topic has subtopics. `filter`: `due` by default, `weak` if the user asks for weak cards, `all` if they ask for everything. `limit`: 25 unless the user's time suggests otherwise (about 2 cards a minute).
4. Reply with only: "Switching to flashcards. Here's your deck: <link>. Tell me when you're done."
5. When the user says done, read `{{meta}}/events/study-skill/<session_id>-flashcards.json`. Missing: "I don't see a summary yet. Press Finish on the Kiosk page, then tell me." Don't guess results.
6. Update `STATE`: add `flashcards` to `modes_completed`; set `mode_results.flashcards` = `{cards_reviewed, cards_correct, cards_flagged_weak (weak_cards), overconfident, deleted, flagged, time_spent_min (minutes), by_topic}`; bump `timestamp`.
7. Move the event: `mkdir -p {{meta}}/events/processed`, then `mv {{meta}}/events/study-skill/<session_id>-flashcards.json {{meta}}/events/processed/`.
8. Update tracking in `S/topics.json` for the session's primary topic(s): set `first_studied` to today if null, add 1 to `times_studied`, set `last_studied` to today. Change nothing else.
9. Report in 2-4 lines: right first time (correct/reviewed), minutes, how many weak and overconfident cards (name the topics they came from using `by_topic`), and any cards deleted or flagged ("flagged cards get rewritten at 3 AM").
