# Brain System -- Specs Summary

*Revised 2026-09-28: built on your fork of My-Brain-Is-Full-Crew, our task picker renamed Distributor, study and dashboards moved to the Kiosk (now with card delete/edit/flag), campaign manager handles multiple campaigns, email triage cost now counted, Windows host via WSL2.*
*Revised 2026-09-30: tools and models refreshed -- local vision and text models (Qwen) replace Tesseract and Phi-3, Marker handles documents, FSRS-6 replaces SM-2, Granite Speech replaces Whisper, notebooklm-py replaces the old NotebookLM skill, Trello and video downloads are scripts, Kokoro voice is local. The vault pins Sonnet, because Claude Code on Pro now defaults to Opus.*

## THE SYSTEM AT A GLANCE

**What it is:** A personal operating system for a CompEng undergrad, run entirely through Claude Code as the sole interface, on a Windows desktop with everything inside WSL2 Ubuntu except Tailscale and Ollama. An Obsidian vault stores all data. The base is your GitHub fork of My-Brain-Is-Full-Crew (8 core agents, 14 skills). On top of it sit our own agents, skills, scripts, and the Kiosk, a small local web app where studying and dashboards happen without spending tokens.

**You talk. Everything else happens behind the scenes.**

**Naming:** "the dispatcher" is upstream's router (the vault's `CLAUDE.md`). It decides which agent or skill handles a message. The **Distributor** is our agent that picks your next task.

---

## WHERE THINGS LIVE

| What | Where | Survives upstream updates? |
|------|-------|---------------------------|
| Core agents, upstream skills, dispatcher | Fork `main`, installed into the vault's `.claude/` and `CLAUDE.md` | Replaced on update (that's the point) |
| Our agents (Distributor, Ingestion, Decomposer) | Fork `jacob` branch, `agents/` + registry rows between the MBIFC markers | Yes |
| Our skills (Study, Schedule, Habits, Campaign, ...) | Fork `jacob` branch, `skills/<name>/` | Yes (new folders never conflict) |
| Our triggers and tool list | The `JACOB` block in the fork's `DISPATCHER.md` | Yes (merged like any branch change) |
| Scripts and the Kiosk | Fork `personal/scripts/`, `personal/kiosk/` | Yes |
| Permissions for unattended runs | Vault `.claude/settings.local.json` | Yes (never overwritten) |
| Your data | The vault at `~/brain-vault` in the WSL2 Linux filesystem (Git-backed), never on `C:` | Yes |
| Startup | Windows Task Scheduler runs `boot.sh` in WSL at every boot | Yes |
| Local models | Ollama on Windows (`qwen3-vl:8b-instruct`, `qwen3.5:9b`, `qwen3-embedding:0.6b`); Python tools in the WSL venv `~/.venvs/brain` (Marker, Surya, Granite Speech, fsrs, Kokoro) | Yes |
| Default Claude model | `"model": "sonnet"` in `.claude/settings.local.json` (Sonnet 5.5); agents and forked skills pin Haiku 4.5 where the work is mechanical | Yes |

---

## EVERY COMPONENT AND WHAT IT DOES

### Agents (subprocesses the dispatcher calls)

| # | Agent | What It Does | Trigger |
|---|-------|-------------|---------|
| 1 | **Architect** (upstream, Opus tier) | Vault structure, onboarding, templates, custom agent creation | `/onboarding`, `/defrag`, `/create-agent`; rarely |
| 2 | **Scribe** (upstream) | Captures messy thoughts into clean notes with frontmatter | "save this", brain dumps, "remind me that" |
| 3 | **Sorter** (upstream) | Files inbox notes, updates MOCs | Via `/inbox-triage` in the 3 AM batch, or "triage the inbox" |
| 4 | **Seeker** (upstream) | Searches the vault, answers with citations | Questions about your stuff |
| 5 | **Connector** (upstream) | Finds links between notes across courses and projects | Manual ("find connections") |
| 6 | **Librarian** (upstream, Opus tier) | Vault health, duplicates, broken links | `/vault-audit` monthly |
| 7 | **Transcriber** (upstream) | Turns transcripts into structured notes | `/transcribe` on local Granite Speech transcripts |
| 8 | **Postman** (upstream) | Gmail + Calendar via `gws` CLI | `/email-triage` 2x daily, "check my email" |
| 9 | **Ingestion** (ours) | Reads each upload's local `.meta.json` (runs `local-preprocess.py` if missing), routes it, extracts and strips diagrams, uploads course material to NotebookLM. Sonnet (`mid`). `/study-gen` runs after it on new academic notes | 3 AM batch; urgent files immediately; "process my uploads" |
| 10 | **Decomposer** (ours) | Breaks assignments into subtasks with effort/time/dependency metadata | Assignment detected, or "break down this assignment" |
| 11 | **Distributor** (ours) | Picks your next task from available time + energy | "what should I do", "done", "I'm stuck" |

### Upstream skills we use as-is

| Skill | What We Use It For |
|-------|-------------------|
| `/onboarding` | First setup; fills `Meta/user-profile.md` (including email VIPs) |
| `/email-triage` | Email scoring, with our tier config layered on (one marked paragraph in the fork) |
| `/inbox-triage` | Filing vault notes (Step 3 of the 3 AM batch) |
| `/deadline-radar` | Deadline grouping (feeds morning briefing and exam mode) |
| `/weekly-agenda` | Week overview; its aggregation feeds our week-ahead plan |
| `/transcribe` | Lecture Notes mode on local Granite Speech transcripts |
| `/vault-audit`, `/deep-clean`, `/tag-garden`, `/defrag` | Monthly maintenance |
| `/create-agent`, `/manage-agent` | Available; our agents are written directly in the fork instead |

### Our skills (invoked on demand or by cron)

| # | Skill | What It Does | Source |
|---|-------|-------------|--------|
| 12 | **Study** (`/study`) | Session orchestrator: brain dump, Socratic, teach-back, calibration; sends flashcards, quizzes, derive-it and diagram drills to the Kiosk | Custom build |
| 13 | **Campaign Manager** (`/campaign`) | Multiple campaigns from a registry. GM: debrief, world sim, session prep, dormant threads. Player: recaps, character sheet, level-ups, quests, NPCs met, pre-session refresher | Custom build |
| 14 | **Grade Tracker** (`/grades`) | Scores per course, projects final grades, alerts the Distributor when borderline | Custom build |
| 15 | **Habit Tracker** (`/habits`) | Creation, tracking, streaks, adaptation, proactive suggestions; dashboard in the Kiosk | Custom build |
| 16 | **Dynamic Scheduler** (`/schedule`) | Time-blocked daily plans, real-time rescheduling, week-ahead plan; writes `today.json`, a script pushes it | Custom build |
| 17 | **Exam Countdown** (`/exam-mode`) | 7-day coordinated review across Distributor, Study and Morning Briefing | Custom build |
| 18 | **Morning Briefing** (`/morning-briefing`) | Schedule, top tasks, deadlines, health, habits, exam countdowns, campaign refresher on game days | Custom build |
| 19 | **Pre-Lecture** (`/pre-lecture`) | Refresher before each class | Custom build |
| 20 | **Weekly Synthesis** (`/weekly-synthesis`) | Cross-course connections, missed-class detection | Custom build |
| 21 | **Explain My Week** (`/explain-my-week`) | Weekly summary: academics, habits, health, productivity | Custom build |
| 22 | **Research Radar** / **Grad Tracker** | New papers in quantum hardware; target programs | Custom build |

### Third-party skills (installed into `.claude/skills/`, listed in the JACOB block)

notebooklm-py (teng-lin; CLI + skill) · Deep Research (sanjay3290/ai-skills, runs on Gemini's quota) · Learn This, YouTube Transcript, Article Extractor, Unblock Action (michalparkola/tapestry-skills) · Ideation (NeoLabHQ). Video downloads and Trello are now scripts (yt-dlp, Trello API), not skills.

### Local services (zero Claude tokens)

| Service | What It Does | Reached From |
|---------|-------------|--------------|
| **Kiosk** (FastAPI in WSL, port 8484) | `/review` (standalone FSRS-6 review), `/s/{id}/flashcards`, `/quiz`, `/derive`, `/diagrams`, `/cards` (browse, search, bulk fix), `/trash`, `/habits`, `/health`, `/today`, `/upload`. Delete, edit or flag any bad card, with undo. Writes review state, card edits and session summaries back to the vault | Phone/iPad/laptop at `https://<desktop>.<tailnet>.ts.net` (`tailscale serve` on Windows) |
| **Remote Control keep-alive** | tmux loop running `claude remote-control --name "My Brain"`, restarts on exit; `boot.sh` starts it at boot | Claude app on phone/iPad |
| **Ollama** (Windows app) | `qwen3-vl:8b-instruct` reads images, handwriting and handwritten PDFs (the thinking `qwen3-vl:8b` looped on dense handwriting); `qwen3.5:9b` classifies and summarizes, with thinking off; `qwen3-embedding:0.6b` matches topics. All on the 4070 Ti, one at a time | Scripts in WSL via `localhost:11434` |

### Data pipelines and scripts (zero Claude tokens)

| # | Script | What It Does | Trigger |
|---|--------|-------------|---------|
| 23 | **Oura collector** | Sleep, readiness, HRV, activity via REST API | Wake detection (7 AM fallback) |
| 24 | **Samsung Health export** | Health Connect -> Drive `Brain-Health/` via Tasker/MacroDroid; rclone pulls it before the merge | Daily |
| 25 | **Health merge** | Combines both, calculates `predicted_energy` | After collectors |
| 26 | **Wake detection** (`check-wake.sh`) | Polls Oura every 10 min, fires the morning pipeline once | Cron, 5 AM-5 PM |
| 27 | **Calendar sync** (`calendar-sync.sh`) | `gws` -> local calendar cache; flags exams and new invites as events | Cron, every 4 hours |
| 28 | **Schedule push** (`push-schedule.sh`) | Diffs `today.json` vs `pushed.json`, pushes future changes to the "Brain Schedule" calendar | After every schedule change |
| 29 | **Local pre-processing** | PDFs routed first (note-app Creator, text-layer density, then a page-1 vision check): typed documents -> Marker, handwritten PDFs -> rendered per page and read by `qwen3-vl:8b-instruct`; images -> `qwen3-vl:8b-instruct`; `qwen3.5:9b` classifies (course limited to real course folders) -> `.extracted.md` + `.meta.json` (with `pdf_route`, `page_images`) beside each upload | 3 AM batch; urgent files on arrival |
| 30 | **Summary filler** (`summarize-missing.py`) | Adds `summary:` to long notes that lack one, via `qwen3.5:9b` | 3 AM batch |
| 31 | **Drive pull + file watcher** | rclone moves new files from Drive into `drive-inbox/` every 2 min; inotifywait queues them or processes urgent ones immediately | cron + inotifywait |
| 32 | **Event watcher** | Watches `Meta/events/scheduler/`, starts a reschedule | inotifywait |
| 33 | **Trello poll + push** | Phone card changes -> `Meta/events/distributor/`; changed task notes -> Trello cards | Cron, every 5 min |
| 34 | **Git backup** | Commits and pushes the vault | Cron, every 6 hours |
| 35 | **Cron scheduler** | Runs everything in `schedule.conf` | Cron |
| 36 | **Processed-event cleanup** | Clears `Meta/events/processed/` | Weekly |
| 37 | **Speech-to-text** (`transcribe-local.sh`) | Granite Speech 4.1 2B with the course's keyword list -> transcript | 3 AM batch |
| 38 | **Label stripper** (`strip-labels.py`) | `surya_detect` boxes + ImageMagick + a local check -> stripped diagrams | During ingestion |
| 39 | **FSRS optimizer** (`optimize-fsrs.py`) | Fits the scheduler to your own review history | Monthly |
| 40 | **Week-summary voice** (`speak.py`, optional) | Kokoro reads Explain My Week aloud -> mp3 | Sunday night |

### Scheduled routines

| Routine | When | What Happens |
|---------|------|-------------|
| **3 AM Batch** | 3:00 AM daily | Process queued uploads (Ingestion), generate study material for new notes (once per note), rewrite cards you flagged in the Kiosk, `/inbox-triage` files the inbox, summary filler runs |
| **Morning pipeline** | Wake detection (7 AM fallback) | Health merge -> `/schedule` writes `today.json` -> `push-schedule.sh` -> Morning Briefing |
| **Email Triage** | 7:30 AM and 4:00 PM | `/email-triage` with tier config; Tier 1 items alert the Distributor |
| **Pre-Lecture Prep** | 30 min before each class | Refresher on last lecture, upcoming assignments |
| **Weekly Synthesis** | Friday 5:00 PM | Cross-course connections, concept mapping, missed-class detection |
| **Week-Ahead Plan** | Sunday 7:00 PM | Rolling 7-day lookahead |
| **Explain My Week** | Sunday 7:30 PM | Weekly review |
| **Research Radar** | Sunday 8:00 PM | New papers in quantum hardware and your interest areas |
| **Vault Audit** | Monthly | `/vault-audit` (Opus tier, so not weekly) |

---

## HOW THEY INTERACT -- DATA FLOW MAP

```
YOU (phone/iPad/laptop/desktop)
 |
 |-- voice/text via Remote Control or terminal
 |-- studying and dashboards in the Kiosk (browser, over Tailscale)
 |-- files via Google Drive "Brain-Inbox/" (rclone pulls them) or Kiosk /upload
 |-- tasks via Trello app on phone
 |
 v
CLAUDE CODE (Windows desktop, inside WSL2, working in the vault)
 |
 |-- The dispatcher (CLAUDE.md) routes: our JACOB-block triggers and
 |   upstream skills first, then agents
 |-- Agents hand off inside a session with "### Suggested next agent"
 |-- Work that finishes OUTSIDE a session leaves a JSON event in
 |     Meta/events/{distributor,ingestion,scheduler,study-skill,habits}/
 |
 v
THE FLOW:

[File arrives in Drive]
  -> rclone pulls it into drive-inbox/ within 2 min (0 tokens)
  -> File watcher (0 tokens) queues it; local pre-processing (Marker, local
     vision model for images and handwritten PDFs) writes .extracted.md + .meta.json
  -> Urgent (due this week, tagged urgent)? Ingestion runs now. Otherwise 3 AM.
  -> Ingestion reads .meta.json first, classifies, routes:
       course folder            (academic notes, diagrams)
       Decomposer               (assignments, via Suggested next agent)
       Granite Speech -> /transcribe (audio)
       campaign inbox           (RPG content, matched by campaign aliases)
       NotebookLM               (course material)
  -> Generation subagent makes cards/quizzes/formulas per topic,
     marks the note study_generated, leaves an event for the study skill
  -> Anything left in the inbox is filed by /inbox-triage in the batch

[You say "I have 30 min at energy 2"]
  -> Distributor reads task frontmatter (NOT full notes)
  -> Filters: time <= 30 min, effort <= 2
  -> Checks grade alerts and the calendar cache
  -> Returns single best task; Trello updated

[You say "study circuits"]
  -> Study orchestrator: time/energy, 2-min brain dump, evaluates it
  -> Picks modes: e.g. Kiosk flashcards (15 min) + Socratic (15 min)
  -> Writes a deck spec, sends a Kiosk link (~150 tokens)
  -> You review on your phone; the Kiosk runs FSRS and saves review state
  -> Kiosk writes a session summary; orchestrator reads it (~300 tokens)
  -> Socratic in chat, then "what's still fuzzy?"
  -> Logs the session; remediation cards generated in the background

[You open /review with no Claude session]
  -> Due cards across all courses, FSRS updates saved. 0 tokens.
  -> Bad card? Delete it (undo for 10 s, restorable from /trash), fix it
     inline, or flag it and the 3 AM batch rewrites it (~300 tokens)
  -> The generator reads your deletions, so the same bad card doesn't come back

[You complete a task on Trello]
  -> Trello poller (0 tokens) writes an event for the Distributor
  -> Distributor marks the vault task done, checks what it unblocks
  -> /schedule updates today.json; push-schedule.sh updates the calendar

[You wake up]
  -> Wake detection fires once; health merge writes predicted_energy
  -> /schedule reads calendar cache + tasks + health + habits
  -> Writes today.json; push-schedule.sh fills the "Brain Schedule" calendar
  -> Morning Briefing writes the daily note; /today in the Kiosk shows it

[You say "I have dinner at 6"]
  -> /schedule adds it to the cache and today.json as immovable
  -> Moves/shrinks/drops flexible blocks
  -> push-schedule.sh pushes the changes (Claude never calls the calendar)

[You say "I went to the gym" or tap it on Kiosk /habits]
  -> Habit Tracker updates habits.json (Kiosk taps are merged from a log)
  -> Streak increments; today.json marks the block done

[Exam detected 7 days away]
  -> calendar-sync.sh spots the exam keyword, writes an event
  -> /exam-mode builds the 7-day review plan
  -> Distributor boosts the exam course; briefing shows a countdown
  -> Scheduler blocks more study time each day; Day 7 is a timed Kiosk exam

[Game day]
  -> Morning briefing adds the campaign refresher (player) or a prep check (GM)
  -> After the session: "session debrief" or "Orben recap" -> /campaign
     picks the campaign from its registry and updates only that folder

[Sunday evening]
  -> Week-ahead plan, Explain My Week, Research Radar
```

---

## EXAMPLE DAY -- TOKEN COST WALKTHROUGH

**Tuesday. You have 3 classes. One assignment due Thursday. Yesterday you uploaded 3 photos of whiteboard notes.**

| Time | What Happens | Model | Est. Tokens | Notes |
|------|-------------|-------|-------------|-------|
| 3:00 AM | Batch: Ingestion on yesterday's 3 photos | Sonnet (reads local transcripts) | ~3,000 | The local vision model already transcribed and classified them; Claude reads the text and looks only at pages with `[?]` words or diagrams |
| 3:05 AM | Batch: study material generation | Sonnet (subagent) | ~6,200 | Cards/quizzes/formulas per topic, once per note. NotebookLM upload is Python (0) |
| 3:10 AM | Batch: `/inbox-triage` + summary filler | Haiku + Ollama | ~1,500 | Summary filler is local (0) |
| 7:00 AM | Health merge + schedule generation (on wake) | Haiku | ~3,500 | Merge is Python (0). Push is a script (0) |
| 7:01 AM | Morning Briefing | Haiku | ~3,000 | Local caches only |
| 7:01 AM | Pre-lecture prep for 9 AM class | Haiku | ~2,000 | Reads 2-3 note summaries |
| 7:30 AM | Email triage | Haiku | ~3,000 | Sender + subject first; full body only for Tier 1 |
| 8:30 AM | "what should I do for 20 min at energy 3" | Haiku | ~2,000 | Task frontmatter only |
| 8:50 AM | "done" | Haiku | ~1,000 | Status update + dependency check |
| 8:51 AM | Schedule update | Haiku | ~1,000 | Calendar and Trello pushes are scripts (0) |
| 12:00 PM | Drop 3 more photos into Drive | -- | 0 | Queued for tonight |
| 12:30 PM | "lunch with friends until 1:30" | Haiku | ~1,500 | Reschedule; script pushes |
| 1:00 PM | Pre-lecture prep for 2 PM class | Haiku | ~2,000 | |
| 3:30 PM | "study circuits for 30 min, energy 3" | Sonnet + Haiku + Kiosk | ~5,000 | Brain dump eval (Sonnet ~3,000) + Kiosk flashcards (~450 to launch and read the summary, 0 during review) + self-assessment and `/study-log` (Haiku, ~1,000) + orchestration |
| 4:00 PM | Email triage | Haiku | ~3,000 | |
| 5:30 PM | "I went to the gym" | Haiku | ~500 | Or tap it on Kiosk /habits for 0 |
| 9:00 PM | "what should I work on, 45 min, energy 4" | Haiku | ~2,000 | Returns an assignment subtask |
| 9:45 PM | "done with methods section" | Haiku | ~1,000 | Unblocks next subtask |
| 9:46 PM | Schedule update | Haiku | ~1,000 | |
| Anytime | Kiosk `/review` on the bus | -- | 0 | |

**DAILY TOTAL: ~42,200 tokens** (~31,500 during the day + ~10,700 in the 3 AM batch)

How it moved: the 2026-09-28 revision removed evening triage (-2,000) and started counting the two scheduled email checks (+6,000), for ~45,200. The 2026-09-30 refresh moved photo and handwriting reading to the local vision model (-3,000).

**Breakdown by category:**
- 3 AM batch (ingestion + study generation + inbox filing): ~10,700
- Morning routine (health + schedule + briefing + 2 pre-lectures): ~10,500
- Task management (Distributor + rescheduling): ~9,500
- Email triage (2 runs): ~6,000
- Study session: ~5,000
- Habit tracking: ~500
- Kiosk, local models, speech-to-text, calendar and Trello sync, health merge, summaries, git backup: 0

Light days (no study session, no uploads, minimal rescheduling) run ~22,000. Heavy days (1-hour Socratic study + campaign prep + multiple reschedules + research radar) can hit ~66,000.

---

## PRO PLAN TOKEN BUDGET ANALYSIS

**What the limits actually are (checked 2026-09-30):** Anthropic doesn't publish token numbers for any plan. Pro has a 5-hour rolling limit and a weekly limit, shared between the Claude app and Claude Code, and `/status` in Claude Code shows where you stand. On May 6, 2026, Anthropic doubled Claude Code's 5-hour limits for Pro and Max and removed the peak-hour reduction. This doc's planning figure, ~44,000 tokens per 5-hour window, dates from before that change, so treat it as a conservative floor. The percentages below use it. Measure your real burn in week 1.

**One setting matters more than everything below:** Claude Code on Pro now defaults to Opus 5.5. The vault pins Sonnet 5.5 in `settings.local.json` (blueprint 0.12). Without that line, every Remote Control message would run on the most expensive model.

| Scenario | Daily Tokens | vs. the 44k floor | Verdict |
|----------|-------------|--------------------:|---------|
| Light day | ~22,000 | ~50% of one window | Comfortable |
| Normal day (example above) | ~42,200 | Batch ~24% in its own window; daytime ~31,500 split across 2-3 windows | Fine as long as the day is spread out |
| Heavy day | ~66,000 | ~150% of one window | Needs 2-3 windows |
| Standalone Kiosk review from phone | 0 | 0% | Free |
| 30-min study session (brain dump + Kiosk + self-assessment) | ~5,000 | ~11% | Negligible |
| 1-hour study session (Kiosk + Socratic) | ~22,000 | ~50% | Major chunk but leaves room |
| Weekly total (5 normal + 2 light days) | ~255,000 | -- | Watch the weekly limit in exam weeks |

**Honest assessment on Pro ($20/mo):**

A normal day is ~42,200 tokens, but it never lands in one window. The 3 AM batch (~10,700) runs alone, in a window you're asleep for. The day splits into morning (~15,500: health, schedule, briefing, pre-lecture, email, first tasks), afternoon (~12,000: reschedule, pre-lecture, study, email, gym) and evening (~4,000). Each fits in its own window with room to spare, and more so after the May doubling.

The weekly total (~255,000) is the real pressure point. Exam weeks with lots of new material will be the tightest. If you hit the weekly cap regularly, the levers in order:
1. Drop the 4 PM email check (~21,000/week).
2. Run the NotebookLM card-generation experiment (blueprint 4.1). If NotebookLM's cards survive the Kiosk's deletion stats, card generation, the biggest line, moves to Google's quota.
3. Max 5x ($100/mo): 5x Pro's per-session capacity.

**Key insight:** the biggest single cost is still study material generation (~6,000 tokens per note). It runs only in the 3 AM batch and only once per note (`study_generated:`), so it never competes with your daytime work.

**Mitigation strategies already built into the system:**

- Vault default pinned to Sonnet; Haiku for agents and forked skills doing mechanical work; Opus-tier upstream agents (Architect, Librarian) run monthly
- Grep-before-read and frontmatter-first patterns cut file reading by ~80%
- Local pre-processing: Marker for typed documents, a local vision model for images, handwriting and handwritten PDFs, a local text model for classification. Claude reads a small `.extracted.md`, not the file
- Local speech-to-text, local topic matching, local label stripping
- 3 AM batch: one invocation, shared context, a window you'd never otherwise use
- Pre-generated study materials, once per note
- The Kiosk for every repetitive interaction (flashcards, quizzes, formula practice, diagram drills, dashboards): 0 tokens per interaction, and standalone review needs no Claude at all
- One-shot skills run forked (`context: fork`), so their working context never piles up in your session
- External data cached by scripts (calendar, health, Trello); Claude never calls those APIs to read, and pushes are scripts too
- Pre-computed values (predicted energy, streaks, grade projections)
- Our agents written lean (~500 words); upstream files trimmed only where measurement shows a cost
- You type `/compact` between study modes when the skill asks (it can't run it itself)
- Event-driven triggers (0 tokens when idle) instead of polling

---

## WHAT COSTS ZERO TOKENS

These run without touching Claude at all:

- The Kiosk: all review, quizzes, formula practice, diagram drills, deleting and editing cards, habit check-ins, dashboards (`/habits`, `/health`, `/today`) and phone uploads
- Git backup (cron + bash)
- Drive pull (rclone) and file watcher (inotifywait), and the 3 AM queue filling up all day
- Event watcher on `Meta/events/` (inotifywait) and processed-event cleanup
- Boot-time startup (Task Scheduler -> `boot.sh`)
- Trello polling and pushing (curl scripts)
- Scheduled triggers (cron)
- Remote Control keep-alive (tmux loop)
- Lecture speech-to-text (Granite Speech, local) and video audio downloads (yt-dlp)
- NotebookLM source uploads (notebooklm-py CLI)
- Apple Shortcuts for iPad/phone file drops
- Oura collection, Samsung Health export, health merge, wake detection
- Calendar cache sync and schedule push (`gws` scripts)
- Stripped image generation (surya_detect + ImageMagick + local check)
- Document conversion to Markdown with LaTeX equations and cut-out figures (Marker)
- Local vision and text models: reading images and handwriting, classification, summaries (including the nightly summary filler), topic matching
- FSRS scheduling and its monthly optimizer
- Week-summary audio (Kokoro)
- Habit streak and task-duration ratio calculations (JSON math in scripts)

This is by design: Claude only runs when there's actual work that needs reasoning, never for monitoring, waiting, data collection, API plumbing, or repetitive interactions the Kiosk can handle.
