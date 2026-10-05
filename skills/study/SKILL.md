---
name: study
description: >
  Run a time-bounded study session: time and energy intake, a 2-minute brain dump, Kiosk
  flashcards and quizzes, self-assessment, then log it and queue remediation cards.
  Triggers: "I want to study [topic]", "study time", "review [course]", "quiz me on",
  "teach me", "exam prep"; "next", "done"/"finished" while a study session is running.
---

# Study Skill

Runs inline on the session model. Built modes: **flashcards** and **quiz** (Kiosk). Socratic, teach-back, derive-it and diagrams aren't built: never plan them; if asked, say so and offer the built ones.

## Paths and rules

Resolve `{{resources}}`, `{{meta}}`, `{{daily}}` from `Meta/vault-map.md` (this literal path); if absent use `03-Resources`, `Meta`, `07-Daily`. `S` = `{{resources}}/study/<course>`. `STATE` = `{{meta}}/study-session-state.json` (fields: `state.md` beside this file; read it once per session). `LOG` = `My-Brain-Is-Full-Crew/personal/scripts/study-log.py`. Bash from the vault root, relative paths, one command per call, no `cd`. Never generate questions and never read card, quiz or review-state files: the Kiosk does that. Write `STATE` whole, keeping every field already there.

## Orchestrator (always runs first)

0. **Continue or resume.** "next"/"done"/"finished": read `STATE`, continue at the step its `step` field names; ask nothing. A new study request while `STATE` is not `logged` and has `modes_completed` or a summary in `{{meta}}/events/study-skill/<session_id>-*.json`: offer to finish it (record any summaries, step 8) or drop it, before starting fresh.
1. **Topic.** From the message, else ask. Find the course with `grep -il "<term>" {{resources}}/study/*/topics.json`, read that `topics.json`, match case-insensitively on slug, `display_name`, `aliases`. Several matches: ask. None: list the course's display names. "review [course]": every topic.
2. **Time and energy.** From the message ("30 minutes", "energy 3"); else from `{{meta}}/states/distributor.md` if written today; else ask both in one line. Session ID: `date +study_%Y%m%d_%H%M`; `started`: `date -Iseconds`.
3. **Interleave.** `first_studied` null: off. Else on, with up to 3 `related_topics`; say "You've studied this before, so I'll mix in related topics."
4. **Plan.** Run `LOG pace` (actual/planned minute ratio per mode). Mode minutes = budget − 3 (brain dump) − 3 (self-assessment). Under 20: one mode (computational topic, i.e. `S/formulas/<slug>.json` exists: quiz; else flashcards; energy 1-2: flashcards). 20 or more: flashcards, then quiz, time split evenly. Items: flashcards `limit` = 2 × minutes ÷ pace; quiz `limit` = minutes ÷ 1.5 ÷ pace. Write `STATE` (`step: brain_dump`) and tell the user the plan in one line.
5. **Brain dump.** "Take two minutes: tell me everything you remember about <topic>. Don't look anything up." Then evaluate: for each `source_notes` entry find the file (`find . -name "<title>.md" -not -path "./.claude/*"`) and read only its frontmatter (`head -30 <file>`) for `summary:`; never the body. Name 2-4 gaps and strong areas against those summaries, score 0-1, reply in 3-4 lines. Score below 0.5: set flashcards `filter: all` (don't trust the card schedule). Save to `brain_dump_evaluation`, `step: next_mode`.
6. **Mode Transition Protocol** (before every mode):
   1. Save `STATE` first.
   2. After a conversational part (brain dump, short-answer questions) end with: "Type /compact, then say next." You can't run it yourself. Skip after Kiosk modes.
   3. On "next": announce "Switching to <mode>." and run it.
7. **Kiosk modes** (below), in plan order. When all are done, go to 8.
8. **Self-assessment.** "We covered <topics>. What still feels fuzzy? Anything you want to come back to?" Map the answer to topic slugs (`fuzzy_topics`) and short phrases (`fuzzy_areas`); "nothing" is fine. Save, `step: log`.
9. **Log.** Invoke the `study-log` skill with the session ID. Relay its 1-2 lines plus, from `STATE`: minutes planned vs used per mode, and fuzzy topics "come back as due until <fuzzy_until>".
10. **Remediation.** If there are brain dump gaps, `weak_cards`, `overconfident`, `weak_items`, `gave_up` or fuzzy areas: start the subagent in `remediation.md` (beside this file) in the background and say "Remediation cards are being written; they'll be in your next session." Set `step: done`.

## Kiosk modes (flashcards, quiz)

1. `curl -s http://localhost:8484/health` must return `{"ok":true}`; else stop: "The Kiosk is down. Start it with `My-Brain-Is-Full-Crew/personal/scripts/kiosk.sh`." Send no link.
2. Link = `<base_url from {{meta}}/kiosk.json>/s/<session_id>/<mode>`.
3. Set `STATE.kiosk` = `{mode, course, topics: [slugs], include_subtopics (true if subtopics), interleave, related_topics, filter, limit, url}`; `step: kiosk_<mode>`. `filter`: flashcards `due` (`all` after a weak brain dump; `weak` if asked); quiz `all` (or `weak`). `due` also includes new cards. Quiz only: `"kinds": [...]` if the user wants one kind.
4. Reply only: "Switching to <flashcards|a quiz>. Here's your link: <link>. Tell me when you're done."
5. On done: read `{{meta}}/events/study-skill/<session_id>-<mode>.json`. Missing: "I don't see a summary yet. Press Finish on the Kiosk page, then tell me." Never guess.
6. Add the mode to `modes_completed`; `mode_results.<mode>` with `planned_min` from `mode_plan`, `time_spent_min` from `minutes`, and: flashcards `{cards_reviewed, cards_correct, cards_flagged_weak (weak_cards), overconfident, deleted, flagged, by_topic}`; quiz `{answered, correct, by_type, weak_items, gave_up, extra_practice, broken, by_topic}`. `segment` +1, `step: next_mode`.
7. `mkdir -p {{meta}}/events/processed`, then `mv` the event there.
8. Report in 2-3 lines: right first time, minutes vs planned, weak/overconfident or missed/gave-up counts by topic, deleted/flagged cards ("rewritten at 3 AM"), `broken` IDs. Then go straight to the next mode, or to the self-assessment (`step: self_assessment`).

Short-answer and "explain why" questions (only if asked) are conversational: ask from the topic's source notes, one at a time, judge each before the next.
