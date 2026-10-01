---
name: study
description: >
  Run a study session: resolve the topic, build a Kiosk deck and send the link, then read the
  Kiosk's summary when the user says done. Triggers: "I want to study [topic]", "study time",
  "review [course]", "quiz me on", "teach me", "exam prep"; "done"/"finished" while a study
  session is running in this conversation.
---

# Study Skill

Runs inline on the session model. Built so far: **Flashcard Review** and **Quiz / Practice Problems**. For any other mode (Socratic, teach-back, derive-it, diagrams), say it isn't built yet and offer flashcards or a quiz.

## Paths and rules

Resolve `{{resources}}` and `{{meta}}` from `Meta/vault-map.md` (this literal path); if absent use `03-Resources`, `Meta`. `S` = `{{resources}}/study/<course>`. `STATE` = `{{meta}}/study-session-state.json`. Bash from the vault root, relative paths, one command per call, no `cd`. Never generate questions and never read card, quiz or review-state files: the Kiosk does that.

## Orchestrator (always runs first)

1. **Resume?** If `STATE` exists, its `modes_completed` lacks a mode in `modes_planned`, and its `session_id` is from today, ask: resume it, or start fresh?
2. **Topic.** Take the topic (and course, if named) from the message; if none, ask. Find the course with `grep -il "<term>" {{resources}}/study/*/topics.json`, then read that `topics.json`. Match case-insensitively against each topic's slug, `display_name` and `aliases`. One match: use it. Several: list their display names and ask. None: say so and list the course's display names. "review [course]" with no topic: use every topic of that course.
3. **Mode.** "quiz me", "practice problems", "test me" → `quiz`; otherwise `flashcards`.
4. **Interleave.** `first_studied` null: `interleave: false`, no related topics. Otherwise `interleave: true` and up to 3 of the topic's `related_topics`; tell the user: "You've studied this before, so I'll mix in related topics."
5. **Session ID.** `date +study_%Y%m%d_%H%M`.

## Kiosk modes (flashcards, quiz)

1. Check the Kiosk: `curl -s http://localhost:8484/health` must return `{"ok":true}`. If not, stop: "The Kiosk is down. Start it with `My-Brain-Is-Full-Crew/personal/scripts/kiosk.sh` (boot.sh normally does)." Send no link.
2. Read `base_url` from `{{meta}}/kiosk.json`. Link = `<base_url>/s/<session_id>/<mode>`.
3. Write `STATE` (replace the file; keep earlier `mode_results` and `modes_completed` when resuming):

```json
{"session_id": "<id>", "topic": "<display name>", "course": "<course>",
 "interleave": false, "interleave_topics": [],
 "modes_planned": ["<mode>"], "modes_completed": [], "mode_results": {},
 "segment": 1, "timestamp": "<date -Iseconds>",
 "kiosk": {"mode": "<mode>", "course": "<course>", "topics": ["<slug>"],
           "include_subtopics": true, "interleave": false, "related_topics": [],
           "filter": "due", "limit": 25, "url": "<link>"}}
```

   `include_subtopics`: true when the topic has subtopics. `filter`: flashcards `due` (default), `weak`, or `all`; quiz `all` (default) or `weak`. `limit`: flashcards 25, quiz 12, or fit the user's time (about 2 cards or 1 question a minute). Quiz only: add `"kinds": ["practice_problem"]` or `["multiple_choice"]` if the user asks for just one kind.
4. Reply with only: "Switching to <flashcards|a quiz>. Here's your link: <link>. Tell me when you're done."
5. When the user says done, read `{{meta}}/events/study-skill/<session_id>-<mode>.json`. Missing: "I don't see a summary yet. Press Finish on the Kiosk page, then tell me." Don't guess results.
6. Update `STATE`: add the mode to `modes_completed`; bump `timestamp`; set `mode_results.<mode>`:
   - flashcards: `{cards_reviewed, cards_correct, cards_flagged_weak (weak_cards), overconfident, deleted, flagged, time_spent_min (minutes), by_topic}`
   - quiz: `{answered, correct, by_type, weak_items, gave_up, extra_practice, broken, time_spent_min (minutes), by_topic}`
7. Move the event: `mkdir -p {{meta}}/events/processed`, then `mv {{meta}}/events/study-skill/<session_id>-<mode>.json {{meta}}/events/processed/`.
8. Update tracking in `S/topics.json` for the session's primary topic(s): set `first_studied` to today if null, add 1 to `times_studied`, set `last_studied` to today. Change nothing else.
9. Report in 2-4 lines. Flashcards: right first time (correct/reviewed), minutes, weak and overconfident counts (name their topics from `by_topic`), deleted or flagged cards ("flagged cards get rewritten at 3 AM"). Quiz: right first time overall and per kind (`by_type`), minutes, missed and gave-up counts by topic, extra practice done, and any `broken` IDs (bad formulas).

## Mode: Quiz / Practice Problems

Multiple choice and practice problems run in the Kiosk (above). Short-answer and "explain why" questions are conversational: ask them here from the topic's source notes, one at a time, judging each answer before the next.
