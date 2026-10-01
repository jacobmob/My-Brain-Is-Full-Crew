# Brain System Master Blueprint

> **Base system:** My Brain Is Full Crew (gnekt/My-Brain-Is-Full-Crew), customized through your own GitHub fork
> **Interface:** Claude Code (single conversational interface, no direct Obsidian interaction)
> **Host:** Windows desktop (RTX 4070 Ti, 64 GB RAM), always on, sleep disabled. Everything runs inside WSL2 Ubuntu except Tailscale and Ollama (0.0)
> **Access:** Remote Control from phone/iPad/laptop for conversation + the Kiosk (local web app over Tailscale) for studying and dashboards + Drive sync for file ingestion

**Revision note (2026-09-28):** Rechecked against the current upstream repo (23 commits, 8 core agents + 14 skills). Changes in this revision:
- Our task-picker agent is renamed **Distributor** (the repo now has its own "dispatcher" -- the CLAUDE.md router).
- Upstream removed `Meta/agent-messages.md`. In-session handoffs now use the repo's own protocol. Our folder queue is narrowed to background events and moved to `Meta/events/` (0.10).
- All customizations live in a fork, because `updateme.sh` overwrites core files and a hook blocks editing them at runtime (0.1, 0.12).
- Email and calendar now use the `gws` CLI instead of MCP (0.2).
- We build on upstream skills where they overlap: email-triage, inbox-triage, deadline-radar, weekly-agenda, transcribe, vault-audit.
- Study interactions and dashboards move from HTML artifacts to a local web app, the **Kiosk** (0.13).
- The campaign manager now handles multiple campaigns, as GM or player (3.1).
- Claude never touches Google Calendar directly: scripts sync it and push schedule changes (3.10). Exam detection moved into the sync script (2.7).
- Scheduled email triage (2x daily) is now actually scheduled and priced (0.2, 0.7).
- The desktop is Windows: new host setup section (0.0) for WSL2, boot-time startup, networking and Drive sync.
- The Kiosk can delete, edit and flag bad cards, with undo and a trash page (0.13).
- **Tools and models refresh (2026-09-30):** local models replace Tesseract and Phi-3, and now read handwriting (0.11); Marker replaces the pile of document extractors; FSRS-6 replaces SM-2 (0.13); Granite Speech 4.1 replaces Whisper (2.3); notebooklm-py replaces the old NotebookLM skill (4.1); Trello and video downloads move to scripts (3.3, 3.5); local Kokoro voice replaces paid TTS (3.11). On the Claude side, Claude Code on Pro now defaults to Opus, so the vault pins Sonnet (0.12), and skills pin their own model with `context: fork` (0.12, 2.2k).

**Naming note:** "the dispatcher" (lowercase) always means the repo's CLAUDE.md router. "Distributor" is our task picker (1.3).

---

## PHASE 0 -- INFRASTRUCTURE & BASE SYSTEM

Everything else depends on this. Do this first.

---

### 0.0 -- Prepare the Windows Desktop (WSL2)

**Type:** One-time host setup
**Existing resource:** WSL2 (built into Windows), Task Scheduler, Tailscale's `serve` command
**Model:** N/A
**Token tip:** N/A. But getting this right is what lets every zero-token script actually run while you sleep.

**Why WSL2:** the repo's installer, updater and hooks are bash scripts that need `jq`, and this blueprint leans on cron and inotify everywhere. WSL2 is a real Ubuntu running inside Windows, with access to your GPU. Think of Windows as the building and WSL2 as the workshop inside it. Windows keeps the front door (Tailscale), the power (no sleep, restart after updates) and the GPU-heavy Ollama. Everything else runs in the workshop.

**What runs where:**

| Windows | WSL2 (Ubuntu) |
|---------|---------------|
| Tailscale (publishes the Kiosk with `tailscale serve`) | Claude Code, Remote Control, the vault, your fork |
| Ollama (native app, full GPU) | cron, inotify watchers, everything in `personal/scripts/` |
| Task Scheduler (starts WSL at boot) | The Kiosk, gws, rclone, Marker, Surya, ImageMagick, ffmpeg |
| Power and update settings | Speech-to-text and Kokoro voice (use the GPU through the Windows driver) |
| Obsidian (optional, for browsing) | Git backup |

**Three rules that head off most WSL problems:**
1. **The vault lives in Linux** (`~/brain-vault`), never under `/mnt/c`. Linux access to Windows drives is several times slower, and inotify never sees changes Windows makes there.
2. **Windows never writes into the vault.** Drive files come in through rclone running inside WSL (0.3), not Google Drive for Desktop.
3. **Mirrored networking**, so `localhost` means the same machine on both sides: WSL reaches Ollama at `localhost:11434`, and Windows (and Tailscale) reaches the Kiosk at `localhost:8484`.

**Steps:**

- [ ] Check you're on Windows 11 22H2 or later (mirrored networking needs it). In an admin PowerShell: `wsl --install -d Ubuntu`, reboot, create your Linux user.
- [ ] Create `C:\Users\<you>\.wslconfig`:
  ```ini
  [wsl2]
  networkingMode=mirrored
  ```
  The default memory cap (half your RAM, 32 GB) is plenty.
- [ ] Inside Ubuntu, create `/etc/wsl.conf` so cron starts with the system:
  ```ini
  [boot]
  systemd=true
  ```
  Then run `wsl --shutdown` in PowerShell and reopen Ubuntu.
- [ ] Put the Linux clock on your time zone, so cron times are Chicago time: `sudo timedatectl set-timezone America/Chicago`
- [ ] Install the Linux toolchain in one go:
  ```bash
  sudo apt update && sudo apt install -y git jq tmux cron inotify-tools rclone \
    poppler-utils imagemagick ffmpeg espeak-ng python3-pip python3-venv
  ```
  Install Node 18+ with nvm; Ubuntu's own Node package is often too old.
- [ ] Browser sign-ins from WSL (`claude` -> `/login`, `gws auth login`, `rclone config`): if no browser opens, paste the printed URL into a Windows browser. The sign-in's return trip to `localhost` reaches WSL through mirrored networking.
- [ ] GPU: install only the normal NVIDIA driver on Windows. Don't install a Linux GPU driver inside WSL. Check with `nvidia-smi` in Ubuntu.
- [ ] Ollama: install the Windows app. The models to pull are listed in 0.11. From Ubuntu, check `curl -s localhost:11434/api/tags` lists them.
- [ ] Tailscale: install the Windows app only, not inside WSL. In the Tailscale admin console, turn on MagicDNS and HTTPS certificates (the Kiosk uses both, 0.13).
- [ ] Power: Settings -> System -> Power, sleep "Never"; `powercfg /hibernate off`; set Windows Update active hours around your day. A forced update restart is fine once the boot task below exists.
- [ ] Obsidian (optional): open `\\wsl.localhost\Ubuntu\home\<you>\brain-vault` as a vault for browsing. It's slower over that path, and Claude Code is the interface anyway.

**Starting everything at boot (set this up once 0.9 exists; add the Kiosk and watchers as they come online):**

- [ ] `personal/scripts/boot.sh` starts each long-running piece in its own tmux session and skips any that are already running:
  ```bash
  #!/bin/bash
  # boot.sh -- start long-running services; safe to run twice
  S=~/brain-vault/My-Brain-Is-Full-Crew/personal/scripts
  start() { tmux has-session -t "$1" 2>/dev/null || tmux new -d -s "$1" "$2"; }
  start brain    "$S/remote-control.sh"                                  # 0.9
  start kiosk    "$S/kiosk.sh"                                           # 0.13
  start watchers "$S/watch-drive-inbox.sh & $S/watch-events.sh; wait"    # 0.3, 0.10
  ```
- [ ] Task Scheduler -> Create Task:
  - Trigger: **At startup**. General: **Run whether user is logged on or not**.
  - Action: program `wsl.exe`, arguments `-d Ubuntu -u <linux-user> -- bash -lc "~/brain-vault/My-Brain-Is-Full-Crew/personal/scripts/boot.sh; exec sleep infinity"`
  - Settings: restart every minute on failure; untick "Stop the task if it runs longer than 3 days".
  - `sleep infinity` holds a WSL session open. Without one, WSL shuts the Linux side down shortly after the last session closes, taking cron, the Kiosk and Remote Control with it.
  - If WSL won't start from this task before you sign in (it depends on the Windows build), change the trigger to **At log on** and turn on automatic sign-in.
- [ ] Test: reboot and open nothing. From your phone, check that the Remote Control session appears, the Kiosk loads over Tailscale, and a test cron job wrote its log line.

---

### 0.1 -- Install & Configure My Brain Is Full Crew

**Type:** Base system setup + customization strategy
**Existing resource:** gnekt/My-Brain-Is-Full-Crew -- install from **your fork**, not the upstream repo directly
**Model:** N/A (setup only)
**Token tip:** N/A

**What the current repo installs (Claude Code platform):**

```
your-vault/
  CLAUDE.md                 <- the dispatcher: routing rules for skills + agents
  .claude/agents/           <- 8 core agents (+ your custom agents)
  .claude/skills/           <- 14 skills (onboarding, email-triage, inbox-triage,
                               deadline-radar, weekly-agenda, transcribe, vault-audit,
                               deep-clean, defrag, tag-garden, meeting-prep,
                               create-agent, manage-agent, contact-sync)
  .claude/references/       <- agents-registry.md, agent-orchestration.md, templates
  .claude/hooks/            <- protect-system-files, validate-frontmatter, notify
  .claude/settings.json     <- hook wiring (overwritten on update)
  .mcp.json                 <- read-only Gmail/Calendar MCP fallback
  Meta/scripts/             <- "orchestra" named scripts (permission-allowlisted)
  Meta/states/              <- one post-it file per agent (max 30 lines, overwritten each run)
  Meta/vault-map.md         <- maps folder roles to your actual folder names
  Meta/user-profile.md      <- the single profile every agent reads
  My-Brain-Is-Full-Crew/    <- the repo clone (your fork)
```

**How the repo routes work (read this before adding anything):**
- The main Claude Code session is the **dispatcher**. It checks the **skill** routing table first, then the **agent** table. Custom agents are checked last.
- **Skills** run in the main conversation and keep multi-turn state -- use them for conversational features. **Agents** run as one-shot subprocesses with their own context -- use them for quick, self-contained jobs.
- Agents never call each other. An agent ends its output with `### Suggested next agent`, and the dispatcher decides whether to chain the next one (max 3 agents per request, no repeats).
- The dispatcher refuses any tool, skill or MCP server that isn't defined in the project files. Everything we add must be registered (0.12).

**Why a fork (the key constraint):**
- `updateme.sh` overwrites core agents, repo skills, references, hooks, `settings.json` and `CLAUDE.md`. It backs up the old CLAUDE.md as `CLAUDE_ORIGINAL.md`, then replaces it.
- The `protect-system-files` hook blocks Claude from editing CLAUDE.md, core agents, skills or core references during a session.
- So any edit made inside the vault is either blocked or lost on the next update.
- **Solution:** fork the repo on GitHub, make every customization in your fork, install from the fork, and merge upstream updates with git. This keeps a single source of truth and uses the repo's own installer and updater.

**What lives where:**

| Change | Where it goes | Why |
|--------|---------------|-----|
| Your custom agents (Distributor, Ingestion, Decomposer) | Fork: `agents/*.md` (source format: `capabilities:` list, not `tools:`) | Installed and updated like core agents; no merge conflicts (new files) |
| Your custom skills (Study, Scheduler, Habits, Campaign Manager, Grade Tracker, etc.) | Fork: `skills/<name>/SKILL.md` | Same -- new folders never conflict |
| Routing rows, trigger phrases, allowed tools/MCPs | Fork: `DISPATCHER.md` (becomes CLAUDE.md), inside a clearly marked block | One file, one marked block = small merge surface |
| Registry rows for custom agents | Fork: `references/agents-registry.md`, between the `MBIFC:CUSTOM_AGENTS` markers | Updater preserves this block |
| Permissions allowlist + your own hooks | Vault: `.claude/settings.local.json` | `settings.json` is overwritten on update; `settings.local.json` is not |
| Personal context (school, courses, VIPs, routing hints) | Vault: `Meta/user-profile.md` | Every agent reads it; survives updates; no core edits needed |
| Zero-token scripts (cron jobs, preprocess, sync) | Fork: `personal/scripts/` (run in place from the clone) | Version-controlled with everything else |
| The Kiosk web app (0.13) | Fork: `personal/kiosk/` | Same |

**Rule for editing core files (agents/skills that upstream owns):** avoid it. When you must (e.g., trimming a hot agent in 0.8, or the one-paragraph hook into `/email-triage` in 0.2), keep the edit small and mark it with `<!-- JACOB: ... -->` comments so upstream merges stay easy.

**Steps:**

- [ ] Prerequisites (all installed in 0.0): Node.js 18+ (for Claude Code and `gws`), `jq` (the installer's build step requires it), git, Python 3. Obsidian is optional.
- [ ] Do 0.0 first. Every command from here on runs in the Ubuntu (WSL2) terminal unless it says Windows.
- [ ] Install Claude Code CLI (`npm install -g @anthropic-ai/claude-code`); Remote Control needs v2.1.51 or later
- [ ] Fork `gnekt/My-Brain-Is-Full-Crew` on GitHub, then clone **your fork** into the vault:
  ```bash
  cd ~/brain-vault
  git clone https://github.com/<you>/My-Brain-Is-Full-Crew.git
  cd My-Brain-Is-Full-Crew
  git remote add upstream https://github.com/gnekt/My-Brain-Is-Full-Crew.git
  git checkout -b jacob          # all your work lives on this branch
  ```
- [ ] Run the installer: `bash scripts/launchme.sh --platform claude-code`
- [ ] Open Claude Code inside your vault folder and say "Initialize my vault" (routes to the `/onboarding` skill)
- [ ] During onboarding, set up your folders. The repo writes them to `Meta/vault-map.md`, so names can be anything:
  - `01-Projects/` -- one subfolder per course (EE225, COMP_ENG_393, etc.), one per personal project (radio-mesh, etc.), plus `01-Projects/campaigns/` for tabletop campaigns (3.1)
  - `02-Areas/` -- Academics, Grad School Prep, Tabletop RPGs, Personal, Health
  - `03-Resources/` -- Reference material, research papers, textbook notes, lecture recordings
  - `04-Archive/` -- Completed courses, finished projects
  - `05-People/` -- Professors, lab contacts, grad school targets, players and party members
  - `06-Meetings/` -- Office hours, study groups, advising
  - `07-Daily/` -- Daily notes and journals
- [ ] Verify the vault structure and `Meta/vault-map.md` were created
- [ ] Test basic operations: "Save this note: test note about vault setup" -> Scribe captures it -> "triage the inbox" -> the `/inbox-triage` skill files it

**Personalization without editing core agents (replaces the old "edit architect/sorter/scribe/seeker" steps):**

- [ ] Add your academic context to `Meta/user-profile.md` (CompEng undergrad at Northwestern, quantum hardware research track, course list with codes). All agents read this file.
- [ ] Add a "Routing hints" section to `Meta/user-profile.md`: course code -> folder (e.g., anything mentioning EE225 goes to `{{projects}}/EE225/`). The Sorter and `/inbox-triage` read the profile.
- [ ] Task frontmatter (`effort`, `time_est`, `priority`, `status`, `course`, `type`) is owned by **our** agents. The Decomposer writes it on every task it creates. For Scribe-captured to-dos that lack these fields, the Distributor assumes defaults (`effort: 2`, `time_est: 15min`, `priority: medium`) and the 3 AM batch fills in real values. No Scribe edit needed.
- [ ] "Summary first" reading: our agents and skills always check the `summary:` frontmatter field before loading full notes (see Global Token Rules). Core agents are left as-is unless 0.8 measurement shows one is expensive.
- [ ] All our agent/skill prompts refer to folders with the repo's **vault-role tokens** (`{{inbox}}`, `{{projects}}`, `{{areas}}`, `{{resources}}`, `{{meta}}`, `{{daily}}`, ...), resolved from `Meta/vault-map.md`. Never hard-code `00-Inbox/`. Paths written as `03-Resources/...` elsewhere in this blueprint mean `{{resources}}/...`.

**Updating later:**

```bash
cd ~/brain-vault/My-Brain-Is-Full-Crew
git fetch upstream && git merge upstream/main   # resolve conflicts in your marked blocks
bash scripts/updateme.sh --platform claude-code
```

**Optional:** the installer also supports Codex CLI (`--platform codex-cli`). If your local/cloud router command should send some vault jobs to Codex, install both platforms into the same vault.

---

### 0.2 -- Connect Email Accounts (3) & Google Calendar

**Type:** `gws` CLI (Gmail + Calendar) + mail forwarding + tier config layered onto the upstream `/email-triage` skill
**Existing resource:** Upstream Postman agent and `/email-triage` skill. Both use the Google Workspace CLI (`gws`) for full Gmail/Calendar read/write, with the hosted MCP servers as a **read-only** fallback. Setup guide: `My-Brain-Is-Full-Crew/docs/gws-setup-guide.md`.
**Model:** Haiku for triage (sender + subject classification is trivial). Sonnet only for Tier 1 emails that need full-body parsing.
**Token tip:** Triage reads sender + subject line FIRST (a few tokens each), applies tier rules, and only reads the full body of Tier 1 and Tier 2 emails. For an inbox of 19 emails, it might fully read 3-4 and skip the rest. That's ~3,000 tokens instead of ~19,000.

**What upstream already does (don't rebuild it):** `/email-triage` ("check my email") scores each email (VIP +3, known contact +2, urgency, deadlines). VIPs come from `{{meta}}/user-profile.md`. It saves important emails as notes, discards newsletters and promotions, and remembers its last scan in `Meta/states/postman.md`. Our only additions are the three-tier config below (so club newsletters get their event info extracted instead of discarded) and the extra accounts.

**Account setup:**

| Account | Connection Method | Notes |
|---------|------------------|-------|
| Hub Gmail account (the one `gws` signs into) | `gws` CLI, full read/write Gmail + Calendar | Prefer a personal Gmail as the hub if you have one: the university account goes away after graduation |
| Northwestern Google Workspace | `gws` if Northwestern allows it (see risk below); otherwise forward to the hub, or use the read-only MCP | University Workspace admins often block unverified OAuth apps -- test this first |
| Hotmail/Outlook | Forward to the hub with an Outlook rule, labelled `hotmail-forward` | `gws` doesn't speak Outlook. An Outlook MCP is the alternative, but it must be registered in the dispatcher (0.12) |
| Custom domain via Zoho | Forward to the hub with a Zoho filter, labelled `zoho-forward` | Same as before |

**University account risk:** `gws` authenticates through an OAuth app **you** create in Google Cloud ("External", unverified). Many universities restrict which third-party apps can access Workspace accounts. If sign-in fails with an admin-policy error on the Northwestern account:
1. **Forward** university mail to the hub account (label `nu-forward`), and share the university calendar with the hub account (or subscribe to its ICS feed), OR
2. Keep the hosted **read-only MCP** for the university account. You lose archive/label/delete but keep reading and calendar reads.

**Steps:**

- [ ] Install `gws`: `npm install -g @googleworkspace/cli`, then follow `docs/gws-setup-guide.md` (Cloud project, OAuth consent screen, **only** the listed scopes). Also enable the Gmail, Calendar and Drive APIs in the project, and **publish** the OAuth app: in Testing status Google expires the sign-in every 7 days, which silently breaks the 3 AM jobs. The same project issues rclone's Drive client (0.3).
- [ ] Test Gmail and Calendar on the hub account: `gws calendar events list --params '{"calendarId": "primary", "maxResults": 3}'`
- [ ] Try `gws auth login` with the Northwestern account. If blocked, use a fallback from the risk box above.
- [ ] **Outlook/Hotmail:** create a forwarding rule to the hub; add a Gmail filter on the hub that applies the label `hotmail-forward` to forwarded mail
- [ ] **Zoho:** auto-forward to the hub; Gmail filter applies `zoho-forward`
- [ ] Add VIP contacts (professors, advisors, lab contacts) to `Meta/user-profile.md` -- this is what upstream `/email-triage` reads for the +3 VIP score
- [ ] Create the tier config `Meta/email-config.json` (below). Vault file, survives updates.
- [ ] **Fork edit (small, marked):** add one paragraph to `skills/email-triage/SKILL.md` in your fork -- "If `{{meta}}/email-config.json` exists, apply its tier rules after priority scoring: Tier 2 senders/keywords are NOT discarded as newsletters; extract events/dates/action items into one concise note. Tier 3 is skipped without reading the body." Wrap it in `<!-- JACOB: tier config -->` comments.
- [ ] Remove the hosted Gmail/Calendar entries from `.mcp.json` once `gws` works (per the setup guide), unless you're keeping them as the university fallback
- [ ] Schedule `/email-triage` twice a day (07:30 and 16:00 in `schedule.conf`, 0.7): `cd ~/brain-vault && claude --model haiku --print "/email-triage"`. Tier 1 results write an event to `Meta/events/distributor/`. Say "check my email" any other time.
- [ ] Test: "check my email" -> confirm all forwarded sources appear with their labels
- [ ] Test triage: send yourself a test email from a Tier 3 sender -> confirm it's skipped; send a club-style newsletter -> confirm event details are extracted
- [ ] Test: "What's on my calendar today?" -> Postman answers via `gws`

**Email triage config file -- `Meta/email-config.json`:**

```json
{
  "accounts": [
    {
      "type": "gws-hub",
      "address": "<hub gmail address>",
      "label": "hub",
      "priority": "high",
      "notes": "The account gws signs into. Every other source arrives here, identified by its Gmail label."
    },
    {
      "type": "gws-or-forwarded",
      "address": "jacob@u.northwestern.edu",
      "label": "university",
      "forward_tag": "nu-forward",
      "priority": "high",
      "notes": "Direct via gws if Northwestern allows it; otherwise forwarded to the hub. Most Tier 1 content comes from here."
    },
    {
      "type": "forwarded",
      "address": "jacob@hotmail.com",
      "label": "personal",
      "forward_tag": "hotmail-forward",
      "priority": "low",
      "notes": "Outlook rule forwards to the hub. Mostly personal/commercial. Very few Tier 1 emails."
    },
    {
      "type": "forwarded",
      "address": "jacob@yourdomain.com",
      "label": "custom",
      "forward_tag": "zoho-forward",
      "priority": "medium",
      "notes": "Custom domain. Zoho forwards to the hub."
    }
  ],

  "tier1_always_surface": {
    "description": "Create vault note + alert Distributor. Read full email body.",
    "senders": [
      "hosseini@northwestern.edu",
      "razeghi@northwestern.edu",
      "grayson@northwestern.edu",
      "khalili@northwestern.edu",
      "shahriar@northwestern.edu"
    ],
    "sender_domains": [
      "canvas.northwestern.edu",
      "registrar.northwestern.edu"
    ],
    "subject_keywords": [
      "assignment", "due date", "grade", "exam", "quiz", "midterm", "final",
      "office hours changed", "class cancelled", "class canceled",
      "lab report", "deadline", "submission", "regrade",
      "research position", "research opportunity",
      "recommendation letter", "application"
    ]
  },

  "tier2_capture_info": {
    "description": "Extract key info (dates, events, action items) into vault note. Don't alert Distributor.",
    "sender_domains": [
      "listserv.northwestern.edu",
      "studentorgs.northwestern.edu"
    ],
    "subject_keywords": [
      "club meeting", "event", "workshop", "seminar", "colloquium",
      "hackathon", "career fair", "info session",
      "IEEE", "ACM", "SWE", "research talk"
    ],
    "processing_rule": "For newsletters and club emails: extract ONLY event names, dates, times, locations, and action items. Discard everything else. Create a single concise vault note."
  },

  "tier3_ignore": {
    "description": "Skip entirely. Don't read body. Don't create note.",
    "sender_domains": [
      "ebay.com", "marketing.ebay.com", "ebay.co.uk",
      "venmo.com", "paypal.com",
      "nytimes.com", "email.nytimes.com",
      "store.northwestern.edu", "bfrb.northwestern.edu",
      "spotify.com", "youtube.com",
      "linkedin.com", "notifications.linkedin.com",
      "facebookmail.com", "instagram.com",
      "donotreply@", "noreply@", "no-reply@",
      "marketing.", "promo.", "offers.", "deals.",
      "news.patreon.com"
    ],
    "subject_keywords": [
      "unsubscribe", "weekly digest", "sale", "% off", "limited time",
      "your receipt", "payment received", "shipping confirmation",
      "verify your email", "password reset",
      "happy holidays", "happy spring break", "happy thanksgiving"
    ]
  }
}
```

**Tier logic the `/email-triage` fork paragraph applies (runs after upstream's own priority scoring; the VIP list in `user-profile.md` doubles as Tier 1 senders):**

```
Email Triage Protocol:
1. Load Meta/email-config.json at start of each email check
2. For each unread email across all sources (identify source by Gmail label):
   a. Read ONLY sender address + subject line (DO NOT read body yet)
   b. Check sender against tier1 senders/domains -> if match: Tier 1
   c. Check sender against tier3 domains -> if match: Tier 3, SKIP entirely
   d. Check subject against tier1 keywords -> if match: Tier 1
   e. Check subject against tier3 keywords -> if match: Tier 3, SKIP
   f. Check sender/subject against tier2 rules -> if match: Tier 2
   g. Default for university account: Tier 2
   h. Default for personal/custom accounts: Tier 3

3. For Tier 1 emails: Read full body. Create vault note with:
   - summary in frontmatter
   - action items extracted
   - deadlines highlighted
   - Write a background event to Meta/events/distributor/ if action is needed
     (in-session, also end output with "### Suggested next agent: distributor")

4. For Tier 2 emails: Read first 3 sentences of body only. Create concise vault note with:
   - extracted dates/events/action items only
   - No full email content

5. For Tier 3 emails: Do nothing. Move on.

Token budget per email check: aim for <4,000 tokens total across all accounts.
```

**Iteration:**

- [ ] After Canvas iCal feed is set up (0.5), verify assignment deadlines appear through calendar
- [ ] After 1 week: review which emails Postman is classifying incorrectly. Add senders/domains to the appropriate tier in the config file. This is a living document -- tune it over the first few weeks.
- [ ] Add a "weekly email digest" mode: once per week, Postman generates a summary of Tier 2 emails you might have missed, grouped by source. Low token cost since it reads cached vault notes, not re-reads emails.

---

### 0.3 -- Connect Google Drive (File Sync Pipeline)

**Type:** rclone pull inside WSL + file watcher script (no MCP needed)
**Existing resource:** `rclone` (installed in 0.0)
**Model:** Haiku (for the watcher/classifier -- it's simple triage work)
**Token tip:** rclone checks Drive every 2 minutes (zero tokens), and `inotifywait` triggers the agent only when a file actually lands -- Claude never polls

**Why no Drive MCP:** the pipeline only needs the files on local disk. Local sync keeps Drive out of Claude's tool list (fewer tokens per session, one less thing to register with the dispatcher).

**Steps:**

- [ ] Create a dedicated Drive folder: `Brain-Inbox/`
- [ ] Connect rclone to the hub Google account once: `rclone config` -> new remote `gdrive`, type `drive`, scope `drive`
- [ ] Pull new files every 2 minutes with cron (zero tokens):
  ```
  */2 * * * * rclone move gdrive:Brain-Inbox ~/brain-vault/drive-inbox --exclude "*.partial" -q
  ```
  `move` empties the Drive folder, so it works like a mail slot. Drive keeps the originals in its trash for 30 days, and ingestion files them into the vault.
- [ ] Why not Google Drive for Desktop: it syncs to the Windows side, and inotify inside WSL can't see files Windows writes (0.0, rule 2). rclone writes straight into the Linux filesystem, so the watcher fires instantly.
- [ ] Write a file watcher script (bash) that queues files for 3 AM batch processing by default, with immediate processing only for time-sensitive files. This saves ~10,000-15,000 tokens/day compared to processing every file on arrival.

```bash
#!/bin/bash
# watch-drive-inbox.sh
# QUEUE by default, IMMEDIATE only for time-sensitive files
# 3 AM batch processes everything else while you sleep, in its own usage window
# Zero tokens until either an urgent file arrives or 3 AM cron fires

WATCH_DIR="$HOME/brain-vault/drive-inbox"
QUEUE="$HOME/brain-vault/Meta/ingestion-queue.txt"

inotifywait -m -q -e close_write -e moved_to --format '%w%f' "$WATCH_DIR" | while read -r event; do
  FILENAME=$(basename "$event")
  case "$FILENAME" in *.partial|.*) continue ;; esac   # skip rclone temp files and hidden files

  # Check if file is time-sensitive (needs same-day processing)
  if echo "$FILENAME" | grep -qiE "assignment|urgent|due|exam|quiz"; then
    # Immediate processing for urgent files.
    # Unattended runs can't answer permission prompts -- tools must be allowlisted
    # in .claude/settings.local.json (0.12) or passed with --allowedTools.
    # --permission-mode acceptEdits lets it write notes (Write/Edit); Bash still follows the allowlist.
    cd "$HOME/brain-vault" && claude --model haiku --permission-mode acceptEdits --print "Process urgent file: $event using the ingestion agent."
  else
    # Queue everything else for 3 AM batch
    echo "$event" >> "$QUEUE"
  fi
done
```

**3 AM batch cron (processes everything queued during the day):**

```bash
# Add to crontab: 0 3 * * * /path/to/batch-triage.sh
#!/bin/bash
# batch-triage.sh -- processes all queued files in ONE session
# Runs at 3 AM, in a usage window you'd otherwise never use
# One Claude invocation for all files instead of one per file

VAULT="$HOME/brain-vault"
SCRIPTS="$VAULT/My-Brain-Is-Full-Crew/personal/scripts"
PY="$HOME/.venvs/brain/bin/python"   # the venv with Marker, Ollama client, fsrs (0.11)
QUEUE="$VAULT/Meta/ingestion-queue.txt"
cd "$VAULT"   # CLAUDE.md (the dispatcher) and .claude/ only load from the vault root

# Step 1: Ingest queued uploads (skipped if queue is empty)
if [ -f "$QUEUE" ] && [ -s "$QUEUE" ]; then
  FILE_COUNT=$(wc -l < "$QUEUE")
  echo "Processing $FILE_COUNT queued files..."

  # Local GPU work first, one job at a time (zero tokens -- 0.11):
  # speech-to-text for audio (2.3), then Marker + the local models
  grep -iE '\.(m4a|mp3|wav)$' "$QUEUE" | while read -r f; do "$SCRIPTS/transcribe-local.sh" "$f"; done
  "$PY" "$SCRIPTS/local-preprocess.py" --queue "$QUEUE"

  # Single Claude invocation processes all pre-processed files
  claude --model sonnet --permission-mode acceptEdits --print \
    "Use the ingestion agent on every file listed in Meta/ingestion-queue.txt \
     as one batch. For each file, read its .meta.json first (from local \
     pre-processing). Run the full ingestion pipeline including study material \
     generation using the Topic Taxonomy system. Delete the queue file when done."

  # Cleanup
  [ -f "$QUEUE" ] && rm "$QUEUE"
fi

# Step 1b: Add summary: frontmatter to long notes that lack one (local Ollama, zero tokens -- 0.8)
"$PY" "$SCRIPTS/summarize-missing.py" --vault "$VAULT"

# Step 2: Generate study materials for academic notes that arrived another way
# (Scribe captures, /transcribe lecture notes). Catches anything with
# type: academic-notes | lecture-notes and no study_generated date.
# Zero-token grep first -- only calls Claude if something is pending.
PENDING=$(grep -rlE "^type: (academic-notes|lecture-notes)" "$VAULT" --include=*.md \
            --exclude-dir=.claude --exclude-dir=My-Brain-Is-Full-Crew --exclude-dir=Templates \
          | xargs -r grep -L "^study_generated:" 2>/dev/null)
if [ -n "$PENDING" ]; then
  claude --model sonnet --permission-mode acceptEdits --print \
    "/study-gen -- Topic Matching Protocol -- for these notes, \
     then add study_generated: <today> to each note's frontmatter: $PENDING"
fi

# Step 2b: Rewrite study items you flagged in the Kiosk (skipped if none)
FLAGGED=$(grep -l '"type": *"card-flagged"' "$VAULT"/Meta/events/study-skill/*.json 2>/dev/null)
if [ -n "$FLAGGED" ]; then
  claude --model sonnet --permission-mode acceptEdits --print \
    "Rewrite the flagged study items in these events, following each note. Write each \
     rewrite as a new item with replaces: <old id> in the same topic file, then move \
     the events to Meta/events/processed/: $FLAGGED"
fi

# Step 3: File whatever is sitting in the vault inbox (replaces the old 5 PM
# evening triage). Uses the upstream /inbox-triage skill.
if [ -n "$(ls -A "$VAULT/00-Inbox" 2>/dev/null)" ]; then
  claude --model haiku --permission-mode acceptEdits --print "triage the inbox"
fi
```

**Why the batch runs three steps:** notes reach the vault three ways -- uploads (Step 1), Scribe captures and `/transcribe` lecture notes (Step 2), and anything left in `00-Inbox` (Step 3). Step 2b handles cards you flagged in the Kiosk. Each step exits for free when there's nothing to do. The `study_generated:` frontmatter flag means every academic note gets exactly one generation pass, however it arrived.

**On-demand processing:** If you need study materials from today's lecture before tonight's study session, say **"process my uploads"** and Claude runs Steps 1-2 immediately instead of waiting for 3 AM. (Don't use "triage my inbox" for this: upstream routes that phrase to `/inbox-triage`, which only files existing vault notes.)

**Token savings:** Processing 5 notes individually = 5 Claude invocations x ~6,000 tokens = ~30,000 tokens. Processing 5 notes in one 3 AM batch = ~15,000-20,000 tokens (shared context, single agent prompt load, and it spends a 5-hour window you're asleep for). Savings: ~10,000-15,000 tokens/day.

- [ ] Test: drop multiple files into Drive -> verify they queue (check ingestion-queue.txt) -> wait for 3 AM or say "process my uploads" -> verify all process in one batch
- [ ] Test urgent file: drop a file named "assignment-ee225.pdf" -> verify it processes immediately, bypassing the queue

**Iteration (later):**

- [ ] Add Apple Shortcut on iPad: share sheet -> upload to `Brain-Inbox/` (one tap)
- [ ] Add Apple Shortcut on phone: same

---

### 0.4 -- Connect Slack (Optional Input Channel)

**Type:** MCP integration
**Existing resource:** Slack MCP servers exist for Claude Code
**Model:** Haiku for message ingestion
**Token tip:** Only pull messages from a specific channel (e.g., `#brain-inbox`), not your entire workspace. Every connected MCP server adds its tool definitions to every session, so skip this if Drive + the Kiosk upload page (0.13) cover your quick captures.

**Steps:**

- [ ] Create a personal Slack workspace (free) or use a dedicated channel in an existing one
- [ ] Install Slack MCP connector and register it in the dispatcher's allowed tools (0.12) -- otherwise the dispatcher treats it as nonexistent
- [ ] Configure to watch a single `#brain-inbox` channel
- [ ] Test: send a message with a thought/note -> confirm it gets ingested into vault

**Why Slack over Drive for quick inputs:** share sheet on iPad/phone is faster for text + images than Drive. Drive is better for large files (PDFs, recordings). Use both.

---

### 0.5 -- Canvas Assignment Ingestion

**Type:** MCP integration + fallback scraper
**Existing resource:** canvas-week-plan@vishalsachdev/canvas-mcp (try first; still actively maintained as of September 2026)
**Model:** Sonnet for parsing assignment details
**Token tip:** Run once daily (morning), not continuously

**Steps:**

- [ ] **Try API access first:** Go to Canvas -> Account -> Settings -> scroll to "Approved Integrations" or look for "+ New Access Token." If available, generate a token and configure the Canvas MCP with it. Register the Canvas MCP in the dispatcher's allowed tools (0.12).
- [ ] **If API is blocked, set up iCal feed:** Canvas -> Calendar -> Calendar Feed (link at bottom of page). Subscribe to this URL in Google Calendar (on the `gws` hub account). Assignment names and due dates then flow into the calendar cache (3.10), `/deadline-radar`, and Postman. No API key needed.
- [ ] **This is still an open question -- test it in the first week.** Whichever method works decides how much of the Decomposer's input is automatic.
- [ ] **For full assignment details (rubrics, descriptions):** Either:
  - Use browser automation (Puppeteer/Chrome MCP) to scrape the assignments page after SSO login -- run daily
  - Manually screenshot/export assignment pages from iPad when you get a complex assignment and drop into Drive `Brain-Inbox/`
- [ ] **If Canvas MCP works:** Configure `canvas-week-plan` to pull assignments and feed them to the Decomposer agent (Phase 1)
- [ ] Test: confirm assignment names and due dates appear in your system through whatever method works

**Iteration:**

- [ ] Once Decomposer agent exists (1.2), connect Canvas output directly to it for auto-decomposition of new assignments

---

### 0.6 -- Git Backup System

**Type:** Hook + cron job (NOT a /loop -- zero tokens)
**Existing resource:** Standard git, no special tool needed
**Model:** None -- this is pure bash, no AI involved
**Token tip:** Zero tokens. This is a bash cron job, not an agent.

**Steps:**

- [ ] Initialize git in your vault: `cd ~/brain-vault && git init`
- [ ] Create a private GitHub/GitLab repo
- [ ] Add remote: `git remote add origin <your-repo-url>`
- [ ] Create auto-commit script:

```bash
#!/bin/bash
# auto-backup.sh -- runs via cron, zero AI tokens
cd ~/brain-vault
git add -A
git diff --cached --quiet || git commit -m "auto-backup $(date +%Y-%m-%d-%H%M)"
git push origin main --quiet
```

- [ ] Add to crontab: `0 */6 * * * /path/to/auto-backup.sh` (every 6 hours)
- [ ] Add `.gitignore` for large files you don't need backed up (audio recordings, etc.), plus:
  - `My-Brain-Is-Full-Crew/` -- it's its own git repo (your fork), pushed separately
  - `.claude/` except `.claude/settings.local.json` -- everything else is reinstalled by `launchme.sh`/`updateme.sh` from the fork
  - `drive-inbox/` -- transient; files are filed into the vault, and Drive's trash keeps originals for 30 days
- [ ] Test: make a change, wait for cron, verify it appears on GitHub

---

### 0.7 -- Event-Driven Trigger System

**Type:** Bash scripts + hooks (NOT /loop for most things)
**Existing resource:** Background event inbox (0.10) for work that happens outside a conversation; upstream's `### Suggested next agent` chaining for work inside one
**Model:** None for the triggers themselves
**Token tip:** This is the single most important token optimization. Every trigger that uses inotify/cron instead of /loop saves hundreds of API calls per day.

**Steps:**

- [ ] `inotifywait` comes from `inotify-tools` (installed in 0.0). It only works on the Linux filesystem, which is why the vault lives there.
- [ ] Create two watcher scripts (both started by `boot.sh`, 0.0) that monitor:
  - `drive-inbox/` for new files -> queues them (or processes urgent ones) per 0.3
  - `Meta/events/*/` for new JSON events -> triggers the consuming agent/skill (see 0.10)
  - (No watcher on `00-Inbox/` -- filing happens in the 3 AM batch, Step 3)
- [ ] All cron-invoked `claude --print` runs must `cd` into the vault first (CLAUDE.md only loads from the vault root) and need their tools allowlisted in `.claude/settings.local.json` (0.12) -- unattended runs can't answer permission prompts
- [ ] For scheduled tasks that genuinely need timers, create a minimal schedule file:

```
# schedule.conf -- only things that MUST run on a timer
03:00      batch-triage        (uploads + study generation + inbox filing; replaces 5 PM evening triage)
07:00      morning-fallback    (schedule + briefing, only if wake detection hasn't fired -- 3.9)
07:30      email-triage        (/email-triage, Haiku, <4,000 tokens -- 0.2)
16:00      email-triage
FRI-17:00  weekly-synthesis
SUN-19:00  week-ahead-plan
SUN-19:30  explain-my-week
SUN-20:00  research-radar
```

- [ ] Write a scheduler script that reads this file and triggers the appropriate agent at the specified time (via cron, not /loop)
- [ ] Reserve `/loop` ONLY for interactive recurring tasks you're actively monitoring

---

### 0.8 -- Keep Prompts Lean (Measure First, Trim Only What's Hot)

**Type:** Measurement + lean authoring of our own agents/skills + selective, marked trims of upstream files in the fork
**Existing resource:** Upstream already moved its heavy multi-step workflows out of agents and into skills, which load only when triggered
**Model:** N/A
**Token tip:** Every word in an agent prompt loads on every invocation of that agent. But upstream files you rarely trigger cost nothing, and every edit to an upstream file is a future merge conflict. So measure before cutting.

**Sizes today (lines, current upstream):** Postman agent 1,281, onboarding skill 1,160 (runs once), transcribe skill 547, email-triage skill 474, architect/scribe/sorter/seeker/connector agents ~350-500 each, CLAUDE.md (dispatcher) 330 -- **CLAUDE.md loads in every session**.

**Steps:**

- [ ] Write **our own** agents and skills lean from day one: target <500 words each, behavior only, no personality text
- [ ] Put the global reading rules in the dispatcher block of your fork's `DISPATCHER.md` (0.12) so the main session follows them. Add them to each of our agent prompts too, since subagents don't see CLAUDE.md:
  - "Before loading any file, grep for the relevant section; only view matching line ranges unless the file is under 50 lines."
  - "Check YAML frontmatter (especially `summary:`) first; load full content only if the frontmatter doesn't answer the question."
- [ ] After 2 weeks of real use, run `/context` during typical sessions and check `/status` for how much of your plan's usage a normal day takes. Only trim an upstream agent/skill if it shows up as a real cost (the likely candidate is Postman, if you use it directly rather than through `/email-triage`).
- [ ] Trim in the fork, on the `jacob` branch, wrapped in `<!-- JACOB: trimmed -->` markers so upstream merges stay manageable. Test the trimmed agent against the same inputs before and after.

**Summary caching without editing Scribe/Transcriber:**

- [ ] Add a zero-token nightly script, `personal/scripts/summarize-missing.py`, to the 3 AM batch. It finds notes over 200 words with no `summary:` field (excluding `.claude/`, the repo clone and Templates) and writes a 2-3 sentence `summary:` using the local text model, `qwen3.5:9b` (0.11). Uploads already get summaries from local pre-processing. Scribe captures and `/transcribe` output get theirs overnight. No core agent edits, and no Claude tokens.

---

### 0.9 -- Enable Remote Control

**Type:** Configuration + keep-alive
**Existing resource:** Built into Claude Code (v2.1.51+). Upstream guide: `My-Brain-Is-Full-Crew/docs/mobile-access.md`
**Model:** N/A
**Token tip:** Remote Control itself doesn't cost extra tokens -- it's just a different input surface for the same session. Studying and dashboards don't go through it at all; they use the Kiosk (0.13).

**The catch:** the session only lives as long as its terminal process. Close the terminal, reboot, or lose network for about 10 minutes, and the session is gone until you restart it. So run it inside `tmux` with an auto-restart loop, started at boot.

**Steps:**

- [ ] Authenticate once from the vault: `cd ~/brain-vault && claude` -> `/login`, accept the workspace trust dialog
- [ ] Create `personal/scripts/remote-control.sh`:
  ```bash
  #!/bin/bash
  # Keeps a Remote Control session alive; restarts it if it exits.
  cd ~/brain-vault
  while true; do
    claude remote-control --name "My Brain"
    sleep 10
  done
  ```
- [ ] `boot.sh` starts it in a detached tmux session named `brain`, and the Task Scheduler task runs `boot.sh` at every Windows startup (0.0)
- [ ] On phone: install the Claude app, sign in with the same account; the session appears under Code with a green dot (or scan the QR code: attach with `tmux attach -t brain`, press space)
- [ ] On iPad: Claude app or claude.ai/code in the browser. Split-screen Claude + the Kiosk for study sessions.
- [ ] Test: reboot the desktop -> confirm the session comes back on its own
- [ ] Use iOS dictation (keyboard mic button) for voice input on phone
- [ ] Check if you have access to `/voice` on the terminal for voice mode at desk

---

### 0.10 -- Background Event Inbox (`Meta/events/`)

**Type:** Folder-based queue for work that happens OUTSIDE a conversation
**Existing resource:** Upstream removed `Meta/agent-messages.md`. Inside a session, agents now hand off through the dispatcher: an agent ends its output with `### Suggested next agent`, and the main session chains up to 3 agents per request. Each agent keeps a post-it at `Meta/states/{agent}.md` (max 30 lines, overwritten each run) for continuity between runs.
**Model:** N/A (structural, no AI involved)
**Token tip:** Each consumer only lists its own folder (a few bytes) instead of reading a shared log. Producers are mostly zero-token scripts.

**Why we still need a queue:** the upstream dispatcher only chains agents while you're in a conversation. Several of our producers run with nobody in the session -- the 3 AM batch, the Trello poller, the health merge, calendar sync, the Kiosk, post-session remediation. Their results need somewhere to wait until the consuming agent next runs. That's all this folder is for.

**Rules:**
- **In a session:** use upstream's protocol (`### Suggested next agent`). Never write events for work the dispatcher can chain right now.
- **Outside a session:** the producer writes one JSON file per event into the consumer's folder.
- **Never reference `Meta/agent-messages.md`.** Upstream's Librarian renames any leftover copy to `-DEPRECATED`. The new folder name (`events/`) avoids confusion with it.
- **One writer per file:** each event is its own file, so producers never collide.

**Structure:**

```
Meta/events/
  distributor/        <- new tasks (Decomposer batch runs), Trello completions,
                         grade alerts, study recommendations, email deadlines
  ingestion/          <- Trello-created to-dos, Kiosk uploads (drawings for diagram modes)
  scheduler/          <- calendar-cache changes from the 4-hour sync (3.10)
  study-skill/        <- "new material ready" from the 3 AM batch, Kiosk session results
  habits/             <- workout auto-detections from the health merge (3.9)
  processed/          <- consumers move handled events here
```

**Event format (JSON):**

```json
{
  "from": "decomposer",
  "to": "distributor",
  "type": "new-tasks",
  "summary": "Decomposed EE225 Lab 3 into 6 subtasks, all status: ready",
  "refs": ["EE225-lab3-write-methods", "EE225-lab3-collect-data"],
  "timestamp": "2026-03-29T14:30:00",
  "priority": "normal"
}
```

Filename: `evt_[timestamp]_[producer].json`

**Steps:**

- [ ] Create the folders: `mkdir -p Meta/events/{distributor,ingestion,scheduler,study-skill,habits,processed}`
- [ ] In each of **our** agents/skills that consumes events, add: "At start, list `{{meta}}/events/<my-name>/`. Process each JSON file (oldest first), then move it to `{{meta}}/events/processed/`." Core upstream agents need no changes.
- [ ] Producers (write one JSON file per event):
  - 3 AM batch / ingestion -> `study-skill/` (new material ready); Decomposer runs in the batch -> `distributor/` (new tasks)
  - Trello poller -> `distributor/` (card done), `ingestion/` (new card from phone)
  - Health merge -> `habits/` (workout detected)
  - Calendar sync -> `scheduler/` (immovable event changed)
  - Kiosk -> `study-skill/` (session results, cards flagged for rewrite), `ingestion/` (uploaded drawing for a pending diagram request)
  - Grade Tracker / study recommendations / email tier 1 deadlines, when run unattended -> `distributor/`
- [ ] Add `Meta/events/processed/` to a weekly cleanup cron (delete files older than 7 days) -- zero tokens: `find Meta/events/processed -mtime +7 -delete`
- [ ] Test: run the Trello poller with a card moved to Done -> confirm an event appears in `distributor/` -> ask "what should I do?" -> confirm the Distributor consumes it and moves it to `processed/`

**Integrate with event-driven triggers (0.7):** most consumers just read their folder the next time they run -- no trigger needed. Only the scheduler folder triggers immediately, because a changed class or meeting should reshuffle today's plan:

```bash
# watch-events.sh (started by boot.sh):
inotifywait -m -q -e close_write -e moved_to --format '%w%f' "$HOME/brain-vault/Meta/events/scheduler/" | while read -r event; do
  sleep 5   # debounce bursts from one sync
  cd "$HOME/brain-vault" && claude --model haiku --print \
    "Scheduler: apply pending events in Meta/events/scheduler/ to today's plan."
done
```

---

### 0.11 -- Local Pre-Processing Pipeline (Marker + Local Vision Model)

**Type:** Local scripts and local models on the 4070 Ti -- zero Claude tokens
**Existing resource:** Marker (documents to Markdown, equations as LaTeX), Ollama with `qwen3-vl:8b-instruct` (reads images, handwriting and handwritten PDFs) and `qwen3.5:9b` (text jobs), Surya text detection (label boxes), `qwen3-embedding:0.6b` (topic matching)
**Model:** Local only -- this section exists specifically to AVOID using Claude tokens
**Token tip:** This is the single biggest token optimization in the system. Local models now read handwriting well enough for a first pass, which the old Tesseract plan couldn't do at all.

**What changed in the 2026-09-30 revision, and why:**

| Job | Before | Now | Why |
|-----|--------|-----|-----|
| Read images: printed text, whiteboards, handwriting | Tesseract (printed only); handwriting always went to Claude | `qwen3-vl:8b-instruct` | On socOCRbench's handwriting set Qwen3-VL 8B scored 0.48, against 0.13 for Tesseract and 0.54 for Claude Sonnet 4.6. The `-instruct` tag, not the default thinking `qwen3-vl:8b`, which looped on dense handwriting |
| Handwritten PDFs (OneNote, Nebo, MyScript exports, scans) | Marker, which reads them poorly | Rendered per page (`pdftoppm -r 150`) and read by `qwen3-vl:8b-instruct` | Marker is built for typed documents; the vision model handles handwriting. See PDF routing below |
| PDF, PPTX, DOCX, XLSX to text | pdftotext, python-pptx, python-docx, openpyxl | Marker (typed PDFs only) | One tool. Keeps layout and tables, writes equations as LaTeX, and saves figures as separate images |
| Classify, course, topic candidates, summary | `phi3:mini` | `qwen3.5:9b` | A 2026 model versus Phi-3 from 2024, far better at following a schema; fits in VRAM with room to spare |
| Label boxes for stripped diagrams | Claude vision estimating coordinates | `surya_detect` | Pixel-accurate text-line boxes, zero tokens |
| Semantic topic match (Topic Matching Step 5) | Claude reading sample cards | `qwen3-embedding:0.6b` | Zero tokens |

**What still needs Claude:**

- Understanding diagrams and schematics (what a circuit does, not just its labels)
- Handwritten pages where the local model marked too many words as unsure (`[?]`), and handwritten math until you've tested it (see Setup)
- Study material generation (flashcards, quizzes, practice problems)
- Anything requiring reasoning, evaluation, or generation

**GPU budget (12 GB VRAM):** only one big model fits at a time, like a single workbench that gets cleared between jobs. The 3 AM batch runs GPU work in sequence: speech-to-text (2.3), then Marker, then the Ollama models. Marker (through Surya 2) runs its models in a vLLM server inside Docker; `local-preprocess.py` converts every queued document in one Marker run, so that server starts once and exits before Ollama loads anything. On Windows, set the system environment variables `OLLAMA_MAX_LOADED_MODELS=1` and `OLLAMA_KEEP_ALIVE=2m`, then restart Ollama, so a finished model frees VRAM for the next step. Marker and the speech model run in WSL and release VRAM when their process exits.

**PDF routing (handwritten vs typed), checked before Marker runs, cheapest first:**

| Check | Result |
|-------|--------|
| 1. `pdfinfo` Creator/Producer names a note-taking app (`HANDWRITTEN_PDF_APPS`: OneNote, MyScript, Nebo) | vision model |
| 2. `pdftotext` text layer under 100 chars/page (`TEXT_LAYER_HANDWRITTEN`) | vision model (handwritten or scanned) |
| 2. Text layer 500+ chars/page (`TEXT_LAYER_TYPED`) | Marker |
| 3. In between: the vision model looks at page 1 at 100 dpi (then unloads, `keep_alive=0`, so Marker gets the GPU) | handwritten/mixed -> vision model, else Marker |

A vision-routed PDF is rendered to `<stem>_pages/page-N.png` and each page is read in two calls: the transcript as plain Markdown (asked inside a JSON string, the model loops on escaped LaTeX backslashes), then a small structured call for `text_type` and `has_diagram`. The page images stay, and `.meta.json` lists them as `page_images`, so Claude checks `[?]` words and math against the one page involved. The decision is recorded as `pdf_route` (e.g. `"vision -- made by OneNote"`).

**Ollama settings that matter:** `think=False` on `qwen3.5:9b` (it thinks by default and can spend the whole output budget before answering, leaving structured output empty); `num_ctx 16384` (the 4096 default cuts off page images); `num_predict 4096`, `repeat_penalty 1.05`, `temperature 0`. The classifier's `course` field is an enum of the real folders in `03-Resources/study/` (or null), so it can't invent a course code. Transcripts that come back wrapped in a code fence are unwrapped.

**Pre-processing script -- runs BEFORE Claude sees anything:**

```python
#!/home/<you>/.venvs/brain/bin/python
# local-preprocess.py -- zero Claude tokens
# For each queued file: extract text (Marker for documents, the local vision
# model for images), classify locally, and write <file>.extracted.md + <file>.meta.json

import sys, re, json, subprocess, shutil, tempfile
from pathlib import Path
import ollama

VAULT = Path.home() / "brain-vault"
VISION, TEXT = "qwen3-vl:8b-instruct", "qwen3.5:9b"  # the thinking qwen3-vl:8b loops on dense handwriting
DOCS = {".pdf", ".pptx", ".docx", ".xlsx", ".html", ".epub"}
IMAGES = {".png", ".jpg", ".jpeg", ".webp"}
# Handwritten PDFs are read page by page by the vision model instead of Marker. Checks, cheapest first:
HANDWRITTEN_PDF_APPS = ("OneNote", "MyScript", "Nebo")  # 1. Creator/Producer is a note-taking app
TEXT_LAYER_HANDWRITTEN = 100    # 2. under this many text-layer chars/page: handwritten (or scanned)
TEXT_LAYER_TYPED = 500          #    at least this many: typed. In between: 3. vision model checks page 1
LOCAL_HANDWRITING = True        # False = all handwriting goes to Claude vision (old behavior)
TRUST_HANDWRITTEN_MATH = False  # flip to True once your own equations transcribe correctly
UNSURE_LIMIT = 0.02             # more than 2% of words marked [?] -> Claude checks the image

READ_PROMPT = ("Transcribe all text in this image exactly, as Markdown. Write math as LaTeX "
               "($...$). Write [?] in place of any word you cannot read confidently.")
# The transcript is asked for as plain Markdown: inside a JSON string (with every LaTeX
# backslash escaped) the vision model falls into repeat loops. Type and diagram are a second call.
TYPE_PROMPT = "Is the text in this image typed, handwritten, mixed, or is there none? Does it contain a diagram, schematic, graph or chart?"
TYPE_SCHEMA = {"type": "object", "required": ["text_type", "has_diagram"],
    "properties": {"text_type": {"enum": ["typed", "handwritten", "mixed", "none"]},
                   "has_diagram": {"type": "boolean"}}}
OPTIONS = {"temperature": 0, "num_ctx": 16384, "num_predict": 4096, "repeat_penalty": 1.05}

CLASSIFY_PROMPT = """Classify this file for a CompEng student's notes vault.
Known course codes: {courses}. Filename: {name}
Text:
{text}"""
CLASSIFY_SCHEMA = {"type": "object",
    "required": ["classification", "course", "summary", "topic_candidates"],
    "properties": {
        "classification": {"enum": ["academic-notes", "academic-diagram", "assignment", "rpg-content",
                                    "personal-project", "reference", "personal", "unclassified"]},
        "course": {"type": ["string", "null"]},
        "summary": {"type": "string"},
        "topic_candidates": {"type": "array", "items": {"type": "string"}}}}

def ask(model, prompt, schema, image=None, **kw):
    msg = {"role": "user", "content": prompt}
    if image:
        msg["images"] = [image]
    if model == TEXT:
        kw["think"] = False  # qwen3.5 thinks by default and can fill the output budget before answering
    r = ollama.chat(model=model, messages=[msg], format=schema, options=OPTIONS, **kw)
    return json.loads(r["message"]["content"])

def convert_documents(paths):
    """Run Marker ONCE over every queued document. Marker's model server (vLLM in
    Docker) starts once, converts everything, and shuts down -- freeing the GPU
    before the Ollama steps. Calling marker_single per file would restart it each time."""
    if not paths:
        return {}
    stage, out = Path(tempfile.mkdtemp()), Path(tempfile.mkdtemp())
    for p in paths:
        (stage / p.name).symlink_to(p)
    subprocess.run(["marker", str(stage), "--output_dir", str(out)], check=True)
    results = {}
    for p in paths:
        dest = p.parent / f"{p.stem}_marker"
        shutil.move(str(out / p.stem), dest)
        md = next(dest.rglob("*.md")).read_text(errors="ignore")
        figs = [str(f) for f in dest.rglob("*") if f.suffix.lower() in {".png", ".jpg", ".jpeg"}]
        results[p] = (md, {"text_type": "typed", "has_diagram": bool(figs), "extracted_images": figs})
    return results

def read_image(path):
    msg = {"role": "user", "content": READ_PROMPT, "images": [str(path)]}
    transcript = ollama.chat(model=VISION, messages=[msg], options=OPTIONS)["message"]["content"]
    transcript = re.sub(r"^```(?:markdown|md)?\s*\n(.*?)\n?```$", r"\1", transcript.strip(), flags=re.S)
    r = ask(VISION, TYPE_PROMPT, TYPE_SCHEMA, image=str(path))
    return transcript, {"text_type": r["text_type"], "has_diagram": r["has_diagram"],
                        "extracted_images": []}

def pdf_route(path):
    """Return ("vision" | "marker", reason). Runs before Marker, so check 3 unloads its model."""
    info = subprocess.run(["pdfinfo", str(path)], capture_output=True, text=True).stdout
    made_by = " ".join(l for l in info.splitlines() if l.startswith(("Creator:", "Producer:")))
    app = next((a for a in HANDWRITTEN_PDF_APPS if a.lower() in made_by.lower()), None)
    if app:
        return "vision", f"made by {app}"
    pages = int(next((l.split()[1] for l in info.splitlines() if l.startswith("Pages:")), 1))
    text = subprocess.run(["pdftotext", str(path), "-"], capture_output=True, text=True).stdout
    per_page = len("".join(text.split())) // max(1, pages)
    if per_page < TEXT_LAYER_HANDWRITTEN:
        return "vision", f"text layer {per_page} chars/page"
    if per_page >= TEXT_LAYER_TYPED:
        return "marker", f"text layer {per_page} chars/page"
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["pdftoppm", "-r", "100", "-png", "-f", "1", "-l", "1", "-singlefile",
                        str(path), f"{tmp}/p1"], check=True)
        r = ask(VISION, TYPE_PROMPT, TYPE_SCHEMA, image=f"{tmp}/p1.png", keep_alive=0)
    route = "vision" if r["text_type"] in ("handwritten", "mixed") else "marker"
    return route, f"text layer {per_page} chars/page, page 1 looks {r['text_type']}"

def read_pdf_pages(path):
    """Render each page to <stem>_pages/page-N.png and read it with the vision model.
    The page images stay, so Claude can check [?] words and math against the page."""
    pages = path.parent / f"{path.stem}_pages"
    pages.mkdir(exist_ok=True)
    subprocess.run(["pdftoppm", "-r", "150", "-png", str(path), str(pages / "page")], check=True)
    images = sorted(pages.glob("page-*.png"))
    texts, types, has_diagram = [], set(), False
    for img in images:
        text, info = read_image(img)
        texts.append(f"<!-- {img.name} -->\n{text}")
        types.add(info["text_type"])
        has_diagram |= info["has_diagram"]
    types.discard("none")
    text_type = types.pop() if len(types) == 1 else "mixed" if types else "none"
    return "\n\n".join(texts), {"text_type": text_type, "has_diagram": has_diagram,
                                "extracted_images": [], "page_images": [str(i) for i in images]}

def needs_claude_vision(text, info):
    if info["has_diagram"]:
        return True                              # Claude describes diagrams
    if info["text_type"] in ("handwritten", "mixed"):
        if not LOCAL_HANDWRITING:
            return True
        unsure = text.count("[?]") / max(1, len(text.split()))
        if unsure > UNSURE_LIMIT or ("$" in text and not TRUST_HANDWRITTEN_MATH):
            return True
    return False

def preprocess(path, courses, converted, routes):
    ext = path.suffix.lower()
    if path in converted:
        text, info = converted[path]
    elif ext == ".pdf":
        text, info = read_pdf_pages(path)
    elif ext in IMAGES:
        text, info = read_image(path)
    else:
        text, info = path.read_text(errors="ignore"), {"text_type": "typed", "has_diagram": False,
                                                        "extracted_images": []}
    schema = json.loads(json.dumps(CLASSIFY_SCHEMA))
    schema["properties"]["course"] = {"enum": [*courses, None]}  # only real course folders, or none
    c = ask(TEXT, CLASSIFY_PROMPT.format(courses=courses, name=path.name, text=text[:4000]), schema)
    Path(f"{path}.extracted.md").write_text(text)
    meta = {"original_file": str(path), "extracted_text_path": f"{path}.extracted.md",
            **info, **({"pdf_route": routes[path]} if path in routes else {}), **c, "unsure_words": text.count("[?]"),
            "needs_claude_vision": needs_claude_vision(text, info),
            "confidence": "low" if c["classification"] == "unclassified" else "high"}
    Path(f"{path}.meta.json").write_text(json.dumps(meta, indent=2))

def main():
    queue = Path(sys.argv[2]) if len(sys.argv) > 2 else VAULT / "Meta/ingestion-queue.txt"
    if not queue.exists():
        return print("No files to process")
    courses = sorted(p.name for p in (VAULT / "03-Resources/study").iterdir() if p.is_dir())
    files = [Path(l.strip()) for l in queue.read_text().splitlines() if l.strip()]
    files = [f for f in files if f.exists()]
    # Pass 0: decide which PDFs are handwritten (vision model) and which are typed (Marker)
    routes = {f: " -- ".join(pdf_route(f)) for f in files if f.suffix.lower() == ".pdf"}
    # Pass 1: every typed document through Marker at once (GPU: vLLM server, then released)
    converted = convert_documents([f for f in files if f.suffix.lower() in DOCS
                                   and not routes.get(f, "").startswith("vision")])
    # Pass 2: images, handwritten PDFs and classification through Ollama (GPU: one model at a time)
    for f in files:
        preprocess(f, courses, converted, routes)
        print(f"  pre-processed: {f.name}")

if __name__ == "__main__":
    main()
```

Structured output (`format=` a JSON schema) makes Ollama return valid JSON every time, so there's no parsing guesswork.

**How Claude uses pre-processed data (modified ingestion behavior):**

When the ingestion agent (1.1) processes a file, it checks for a `.meta.json` file first:

```
Modified Ingestion Step 2 (Visual Classification):
1. Check if [filename].meta.json exists
   - If yes: use classification, course, summary and topic_candidates from it.
     If confidence is "high", skip Claude classification entirely.
     If "low" (the local model said unclassified), fall through to Claude.
   - If no: run local-preprocess.py on it first (--queue with a temp
     list of every such file, one run), then continue as above

2. Check needs_claude_vision:
   - false: read [filename].extracted.md only. Claude never opens the
     original image or document. Cheapest path.
   - true, handwriting: read .extracted.md, then look only at the page
     images that hold [?] words or handwritten math (page_images for a
     vision-routed PDF, the image itself for a photo).
   - true, diagrams: read .extracted.md for the text, and use vision only
     on the figures Marker cut out (extracted_images), never whole pages.
```

**Token savings from local pre-processing:**

| Scenario | Without Local Pre-Processing | With Local Pre-Processing | Savings |
|----------|------------------------------|--------------------------|---------|
| 3 typed lecture PDFs (20 pages each) | ~45,000 tokens | ~15,000 tokens | 67% |
| 5 photos of whiteboard (typed text) | ~10,000 tokens | ~2,000 tokens | 80% |
| 1 PPTX slide deck (30 slides) | ~20,000 tokens | ~8,000 tokens | 60% |
| 5 handwritten note photos | ~10,000 tokens | ~3,000 tokens if your handwriting tests well (Claude reads transcripts, checks only flagged pages) | ~70% |
| Daily total (typical mix) | ~40,000 tokens on ingestion | ~12,000 tokens on ingestion | ~70% |

**Setup:**

- [ ] Create one Python environment for all the local tools (in WSL) with `uv`, pinned to Python 3.12 so Ubuntu's own Python version never matters: `uv venv --python 3.12 ~/.venvs/brain && uv pip install --python ~/.venvs/brain ollama "marker-pdf[full]" surya-ocr yt-dlp`. Marker brings in PyTorch with CUDA.
- [ ] Give Marker its GPU model server: Docker Engine inside Ubuntu (`docker.io`, not Docker Desktop, which only runs after you sign in to Windows), your user in the `docker` group, and NVIDIA Container Toolkit (`nvidia-ctk runtime configure --runtime=docker`). Test with `docker run --rm --runtime=nvidia --gpus all ubuntu nvidia-smi`. Exact commands are in the install guide, Stage 5. The text detector behind `surya_detect` still runs in-process, so the label stripper doesn't need this. (yt-dlp comes from pip, not apt, because YouTube breaks old versions; update it monthly.) Point every script's first line at `~/.venvs/brain/bin/python`.
- [ ] Pull the local models from a Windows terminal: `ollama pull qwen3-vl:8b-instruct`, `ollama pull qwen3.5:9b`, `ollama pull qwen3-embedding:0.6b` (about 14 GB of disk together)
- [ ] Set `OLLAMA_MAX_LOADED_MODELS=1` and `OLLAMA_KEEP_ALIVE=2m` as Windows system environment variables, then restart Ollama
- [ ] Save `local-preprocess.py` to `personal/scripts/` in your fork (`~/brain-vault/My-Brain-Is-Full-Crew/personal/scripts/`)
- [ ] Update the 3 AM batch script to run `local-preprocess.py` before invoking Claude (already shown in 0.3 batch-triage.sh)
- [ ] Update ingestion agent prompt (1.1) to check for `.meta.json` before running classification
- [ ] **Handwriting test -- do this before trusting it.** Photograph 10 pages of your own notes, including at least 2 pages of equations. Run `local-preprocess.py` on them and compare each `.extracted.md` with the page.
  - Transcripts usable, `[?]` only on genuinely messy words: keep the defaults.
  - Text fine but equations wrong: leave `TRUST_HANDWRITTEN_MATH = False`, so Claude checks math pages.
  - Mostly wrong: set `LOCAL_HANDWRITING = False`, and handwriting goes to Claude vision as before.
- [ ] Test: drop a typed PDF -> verify `.meta.json` and `.extracted.md` are created locally, with equations as LaTeX -> verify Claude reads the Markdown instead of the full PDF
- [ ] Test: drop a slide deck with circuit figures -> verify Marker saved the figures as separate images and `needs_claude_vision` is true
- [ ] Test: drop a OneNote or Nebo PDF export -> verify `pdf_route` starts with `vision`, `<stem>_pages/` holds one PNG per page, and Marker never ran on it

**VRAM and RAM:** `qwen3-vl:8b-instruct` and `qwen3.5:9b` each need roughly 7-9 GB of VRAM when loaded, so they take turns (the environment variables above handle it). Marker's models and the speech model (2.3) run one at a time in the same batch. With 64 GB of system RAM, nothing here is tight on the CPU side.

---

### 0.12 -- Register Our Agents, Skills and Tools with the dispatcher

**Type:** One marked block in your fork's `DISPATCHER.md` + registry rows + `.claude/settings.local.json`
**Existing resource:** Upstream dispatcher (`DISPATCHER.md` in the repo, installed as the vault's `CLAUDE.md`)
**Model:** N/A
**Token tip:** CLAUDE.md loads in **every** session, so keep this block tight: routing rows and one-line rules, no explanations.

**Why this is required:** the dispatcher's top rule is "if something is not defined in this project's files, IT DOES NOT EXIST", and it refuses unlisted tools, skills and MCP servers. Custom agents are only consulted after all 8 core agents, so phrases like "what should I do" could otherwise land on Seeker or Scribe. Nothing we build works until it's registered here.

**Custom agent source format (fork `agents/*.md`):** same frontmatter as the core agents -- `capabilities: [read, write, edit, bash]` (closed set: read, write, edit, bash, webfetch, websearch, notebook, task, todo) and `model: low | mid | high` (the build maps these to haiku / sonnet / opus). Upstream sets Architect and Librarian to `high` (Opus) -- if 0.8 measurement shows them being called often, change them to `mid` in the fork.

| Our agent | capabilities | model |
|-----------|-------------|-------|
| distributor | read, write, edit, bash | low |
| ingestion | read, write, edit, bash | mid |
| decomposer | read, write, edit | mid |

**The marked block (add near the top of your fork's `DISPATCHER.md`, right after the "ABSOLUTE CONSTRAINT" section):**

```markdown
<!-- JACOB:START personal extensions -->
## Personal extensions -- defined in this project, valid to use

### Extra skills (same priority as the skill table)
| Skill | Triggers |
|-------|----------|
| /study | "I want to study [topic]", "study time", "review [course]", "quiz me on", "teach me", "exam prep" |
| /schedule | "schedule my day", "plan my day", "plan my week", "schedule my week", "reschedule", "I have [event] at [time]", "I'm not doing that" |
| /habits | "I want to start [habit]", "I went to the gym", "I didn't [habit] today", "show my habits", "habit check" |
| /campaign | "session debrief", "prep for next session", "what would [NPC] do", "update my character", "level up", "quest log", "what do I need to remember for [campaign]", any campaign name or alias from `01-Projects/campaigns/*/campaign.json` |
| /grades | "I got [score] on", "what do I need on the final", "grade projection" |
| /exam-mode | "exam mode for [course]", "start exam countdown" |
| /morning-briefing | "morning briefing", "what does today look like" |
| /pre-lecture | "prep me for [course] lecture" (also fired by cron) |
| /weekly-synthesis | "weekly synthesis", "what did I learn this week", "connect my courses" |
| /explain-my-week | "explain my week", "how did my week go", "week summary" |
| /research-radar | "research radar", "new papers in [area]" |
| /grad-tracker | "grad school tracker", "update my target programs" |

### Extra agents -- check THESE triggers BEFORE the core agent table
| Agent | Triggers |
|-------|----------|
| distributor | "what should I do", "I have [N] minutes", "energy [N]", "done", "finished", "I'm stuck", "next task" |
| ingestion | "process my uploads", "process the queue", batch-run file lists |
| decomposer | "break down this assignment", "decompose", new assignment files |

### Extra tools that exist in this project
- CLI: gws, rclone, marker_single, surya_detect, yt-dlp, python scripts in My-Brain-Is-Full-Crew/personal/scripts/, Ollama API (http://localhost:11434), the Kiosk (http://localhost:8484)
- Installed third-party skills: notebooklm (notebooklm-py), deep-research, learn-this, youtube-transcript, article-extractor, unblock-action, create-ideas
- MCP servers (only if connected): Canvas, Trello (official), Slack, Outlook

### Rules for the main session
- Grep before reading; check frontmatter `summary:` before loading full notes.
- Background work that finishes outside a session lands in Meta/events/<consumer>/ -- consumers read their own folder.
- Study reviews, quizzes and dashboards happen in the Kiosk; send links, don't render them in chat.
<!-- JACOB:END -->
```

Also in your fork's `DISPATCHER.md` skill table: remove "plan my week" from `/weekly-agenda`'s triggers (it now goes to `/schedule`). Leave "weekly agenda" and "what's this week" with `/weekly-agenda`.

**Trigger collisions with upstream (resolved):**

| Phrase | Upstream sends it to | Our decision |
|--------|---------------------|--------------|
| "weekly review" | `/vault-audit` | Leave it. Our weekly features use "explain my week" and "weekly synthesis". |
| "triage my inbox" / "triage the inbox" | `/inbox-triage` (files vault notes) | Leave it. Processing Drive uploads uses "process my uploads". |
| "plan my week" | `/weekly-agenda` | Move to `/schedule` (the fork edit above). `/schedule` reads `/weekly-agenda`'s aggregation logic as input. |
| "check my email" | `/email-triage` | Keep. Our tier config plugs into it (0.2). |
| "deadlines" / "deadline radar" | `/deadline-radar` | Keep. Exam mode and the morning briefing use its output. |
| "lecture notes" / "transcribe" | `/transcribe` | Keep. Our lecture pipeline (2.3) feeds it local Granite Speech transcripts. |
| "to-dos" / "remind me that" | Scribe | Keep for capture. "What should I do" and "done" go to the Distributor via the priority rows above. |
| "meeting prep" | `/meeting-prep` | Declined feature -- leave installed, unused. |

**Registry rows (so the dispatcher can chain our agents):** in your fork's `references/agents-registry.md`, add one row per custom agent **between** the `<!-- MBIFC:CUSTOM_AGENTS_START -->` and `<!-- MBIFC:CUSTOM_AGENTS_END -->` markers (the updater preserves that block), and mirror them in `references/agents.md`.

**Third-party skills (NotebookLM, deep-research, Tapestry, Trello, etc.):** install them into the vault's `.claude/skills/` with their own installers (e.g., `npx skills add sanjay3290/ai-skills --skill deep-research -a claude-code`, or `notebooklm skill install` for notebooklm-py). The updater only replaces upstream's own skill folders, so these survive updates. They just need the "Extra tools" line above so the dispatcher will use them.

**Permissions -- `.claude/settings.local.json` (not overwritten by updates):**

```json
{
  "model": "sonnet",
  "permissions": {
    "allow": [
      "Bash(gws:*)",
      "Bash(python3 My-Brain-Is-Full-Crew/personal/scripts/*:*)",
      "Bash(My-Brain-Is-Full-Crew/personal/scripts/*:*)",
      "Bash(Meta/scripts/*:*)",
      "Bash(marker_single:*)",
      "Bash(surya_detect:*)",
      "Bash(pdftoppm:*)",
      "Bash(convert:*)",
      "Bash(yt-dlp:*)",
      "Bash(curl -s http://localhost:11434/*:*)",
      "Bash(curl -s http://localhost:8484/*:*)",
      "Bash(notebooklm source add *)",
      "Bash(notebooklm create *)",
      "Bash(pdfinfo *)",
      "Bash(identify *)",
      "Bash(jq *)",
      "Bash(date *)",
      "Bash(mkdir -p *)",
      "Bash(mv drive-inbox/*)",
      "Bash(cp drive-inbox/*)",
      "Bash(rm drive-inbox/*)",
      "Bash(rm -r drive-inbox/*)",
      "Bash(rm Meta/ingestion-*)"
    ]
  }
}
```

Cron-invoked `claude --print` runs can't answer permission prompts, so anything a batch job needs must be on this list (or passed per-run with `--allowedTools`). Start narrow and add entries as batch logs show denials. Bash rules don't cover the Write and Edit tools: batch runs that create or edit notes pass `--permission-mode acceptEdits` (0.3), which auto-approves file edits inside the vault and leaves Bash on this allowlist. The ingestion entries (1.1) assume the agent runs commands from the vault root with relative paths, no `cd`: file moves and deletes are limited to `drive-inbox/` and `Meta/ingestion-*`, and NotebookLM to `source add` and `create`.

**Why `"model": "sonnet"` is in there:** Claude Code on the Pro plan now defaults to Opus 5.5. Every Remote Control message and every session you open would otherwise run on the most expensive model. This line makes Sonnet 5.5 the vault's default; cron jobs still pick their own with `--model`.

**Pinning models per skill and agent (answers the old "can a skill switch models?" question):**
- **Agents:** the `model:` field in agent frontmatter always applies (our table above: `low` = Haiku 4.5, `mid` = Sonnet 5.5).
- **One-shot skills** (morning briefing, pre-lecture, weekly synthesis, explain my week, grades, schedule generation): add `context: fork`, `model: haiku` (or `sonnet`) and `effort: low` to the frontmatter. The skill runs in its own subagent on that model and hands back a result. Its working context never lands in your main session either.
- **Conversational skills** (study, campaign, habit creation) have to run inline, and inline `model:` pins are unreliable right now: the docs say they last only for the current turn, and open bug reports show them ignored when Claude invokes the skill itself (anthropics/claude-code #79654, #85658). So these run on the session's Sonnet, and hand cheap bookkeeping to a forked Haiku helper (2.2k).
- **Effort:** Sonnet 5.5 and Opus 5.5 default to `medium` effort. Mechanical skills set `effort: low`; nothing in this system needs more than `medium`.

**Steps:**

- [ ] Add the marked block to your fork's `DISPATCHER.md`; remove "plan my week" from `/weekly-agenda`'s trigger list
- [ ] Add registry rows for distributor, ingestion and decomposer between the MBIFC markers
- [ ] Create `.claude/settings.local.json` with the allowlist
- [ ] Run `bash scripts/updateme.sh --platform claude-code` from the fork to install
- [ ] Routing tests (from your phone over Remote Control):
  - "what should I do, 20 minutes, energy 2" -> distributor (not seeker/scribe)
  - "plan my week" -> /schedule; "weekly agenda" -> /weekly-agenda
  - "weekly review" -> /vault-audit (expected); "explain my week" -> /explain-my-week
  - "process my uploads" -> ingestion; "triage the inbox" -> /inbox-triage
- [ ] Run one cron-style `claude --print` job from the vault and confirm no tool was denied

---

### 0.13 -- The Kiosk (Local Web App for Studying and Dashboards)

**Type:** Small local web app (FastAPI + static HTML/JS) in your fork at `personal/kiosk/`. It runs inside WSL on the desktop (started by `boot.sh`, 0.0), and you reach it from phone/iPad over Tailscale.
**Replaces:** the HTML artifacts the previous revision planned for flashcards, quizzes, derive-it, diagram Directions B/C, the habit dashboard and the health dashboard
**Model:** None -- zero Claude tokens per interaction. Claude writes a small "deck spec" and sends you a link.
**Token tip:** Artifacts cost ~1,500 tokens each just to template. The Kiosk builds every page from files already on disk, so starting a flashcard mode costs ~150 tokens (write the spec, send the link). Standalone review at `/review` costs nothing because Claude isn't involved.

**Why the artifacts had to go:**
1. **Nothing saved your results.** The artifact plan never had a way to write review schedules back to the vault; it fell back to "ask the user for a summary."
2. **Uncertain rendering.** A Claude Code session viewed through Remote Control isn't guaranteed to render interactive HTML artifacts on your phone.
3. **No Claude, no studying.** If you'd hit your usage limit, the artifact couldn't even be generated.

The old plan was like mailing someone a paper quiz and asking them to read you their answers. The Kiosk is a quiz kiosk in the lobby: it keeps the deck, records every score itself, and hands Claude a one-line summary when you're done.

**How a study mode flows through it:**

```
Study skill (Claude)                    Kiosk (desktop :8484)                  You (phone/iPad browser)
1. writes deck spec into
   Meta/study-session-state.json
2. replies with a link  ─────────────────────────────────────────────────────► opens https://<desktop>.<tailnet>.ts.net/s/<id>/flashcards
                                        3. reads spec + card/quiz/formula JSON
                                        4. serves the page                      5. flip, rate, answer
                                        6. writes FSRS state after every card
                                        7. on Finish: writes a compact summary
                                           to Meta/events/study-skill/<id>.json
8. you say "done" -> skill reads the summary (~300 tokens) -> next mode
```

**Pages:**

| Route | Purpose | Reads | Writes |
|-------|---------|-------|--------|
| `/review` | Standalone: every due card across all courses. No Claude involved at all. | `cards/*`, `review-state/*` | `review-state/*` |
| `/s/{id}/flashcards` | Session deck built from the spec (topics, interleave flag, due/weak filter) | spec, `cards/*`, `review-state/*` | `review-state/*`, session summary |
| `/s/{id}/quiz` | Multiple choice + practice problems with randomized values | spec, `quizzes/*` | quiz attempts, session summary |
| `/s/{id}/derive` | Formula sheet panel (KaTeX) beside randomized problems | spec, `formulas/*`, `quizzes/*` | same |
| `/s/{id}/diagrams` | Direction B (stripped image -> reveal labeled), Direction C timed display + upload box for your drawing | spec, `diagrams/*`, image cards | drawing -> `Meta/uploads/` + event to `Meta/events/ingestion/`; summary |
| `/cards` | Browse and search every card, question, formula and diagram item by course/topic; sort by most-failed; bulk delete or flag | `cards/*`, `quizzes/*`, `formulas/*`, `card-edits/*`, `review-state/*` | `card-edits/*` |
| `/trash` | Everything you deleted, newest first; restore with one tap | `card-edits/*` | `card-edits/*` |
| `/upload` | Camera/file upload straight into `drive-inbox/` -- quick capture from any device | -- | `drive-inbox/` |
| `/habits` | Streaks, 30-day grid, trends | `habits.json` | (iteration: one-tap check-ins -> `Meta/habit-checkins.jsonl`) |
| `/health` | Sleep, HRV, stress, activity trends (30/90 days) | `Meta/health/health-history.json` | -- |
| `/today` | Today's schedule + morning briefing, phone-friendly | `today.json`, today's daily note | -- |

**Single-writer rule (no race conditions):** every file has exactly one writer.
- Card content (`cards/[topic].json`, `quizzes/`, `formulas/`) -- written only by the generation and remediation subagents
- Review state (`review-state/[topic].json`) and card edits (`card-edits/[topic].json`) -- written only by the Kiosk, atomically (write a temp file, then rename)
- Habit check-ins (iteration) -- append-only `Meta/habit-checkins.jsonl`; the habit tracker merges them into `habits.json`
- So the 3 AM batch can add new cards to a topic while you're reviewing it, and nothing collides.

**Fixing bad cards (0 tokens, from any page):**

Every card, quiz question, practice problem, formula and diagram question has a small menu (on iPad or desktop: `D` delete, `E` edit, `F` flag):

| Action | What happens | Cost |
|--------|-------------|------|
| **Delete** | Gone from every deck immediately. A 10-second Undo appears, and `/trash` can restore it any time later. Optional one-tap reason: wrong, vague, duplicate, too easy, not in my course. | 0 |
| **Edit** | Fix it in place: front/back, question/choices/answer, or formula, with a live KaTeX preview. Review history is kept; tick "reset schedule" if you changed what the card asks. | 0 |
| **Flag for rewrite** | For cards that are broken but worth saving, when you don't want to fix them yourself. Hidden until the 3 AM batch rewrites it. Optional note: "the answer uses the wrong time constant." | ~300 tokens per card, overnight |

Deleting or flagging a card mid-session removes it from that session's `weak_cards`, so bad cards never trigger remediation.

**How edits stay single-writer:** the Kiosk never touches card files. It records every change in its own per-topic file and applies it whenever it builds a deck, like tracing paper laid over a printed page: the page (card file) stays as generated, and what you see is page plus overlay.

**Card-edits format -- `03-Resources/study/[course]/card-edits/[topic-slug].json`:**

```json
{
  "topic": "rc-transient-analysis",
  "edits": {
    "ee225_014": {"action": "deleted", "reason": "vague", "date": "2026-09-28"},
    "ee225_022": {"action": "edited", "date": "2026-09-28", "reset_schedule": false,
                  "override": {"front": "What is the time constant of a series RC circuit?", "back": "tau = RC"}},
    "ee225_031": {"action": "flagged", "note": "answer uses the wrong time constant", "date": "2026-09-28"}
  }
}
```

- **Undo and restore** just remove the entry.
- **Flagged rewrites:** the Kiosk also writes a `card-flagged` event to `Meta/events/study-skill/`. Step 2b of the 3 AM batch (0.3) rewrites all flagged items in one call. Each rewrite goes into the card file as a **new** item with `"replaces": "ee225_031"` and a fresh schedule. The Kiosk hides any item that something else replaces.
- **Generation learns from it:** before writing cards for a topic, the generation subagent reads that topic's overlay and won't recreate a deleted card. The Kiosk also keeps deletion counts by reason per course in `card-edits/_stats.json`; the generator reads the top two reasons for the course (~50 tokens) and adjusts, e.g. "a third of deleted EE225 cards were 'vague': make each front ask exactly one thing."

**Review-state format -- `03-Resources/study/[course]/review-state/[topic-slug].json`:**

```json
{
  "topic": "rc-transient-analysis",
  "cards": {
    "ee225_001": {
      "fsrs": {"state": 2, "step": null, "stability": 8.4, "difficulty": 5.1,
               "due": "2026-10-04T14:00:00+00:00", "last_review": "2026-09-28T14:00:00+00:00"},
      "times_reviewed": 3, "times_correct": 2, "last_rating": "good",
      "confidence_history": [{"date": "2026-09-28", "confidence": 3, "correct": true}]
    }
  },
  "quiz_attempts": {
    "ee225_q001": [{"date": "2026-09-28", "correct": true, "time_sec": 22}]
  }
}
```

A card with no entry here is **new** (due now). Deleting a review-state file resets that topic's schedule without touching the cards. The Kiosk counts a card as due when its `fsrs.due` time has passed.

**Scheduler: FSRS-6 (Kiosk server, Python) -- replaces the modified SM-2 from the previous revision.**

SM-2 is the 1980s algorithm behind classic Anki: every card gets an "ease" number, and intervals grow by multiplying. FSRS (Free Spaced Repetition Scheduler) instead models each card's memory directly, with a *stability* (how long the memory lasts) and a *difficulty*, and schedules the next review for the moment your recall chance drops to a target you choose. Think of SM-2 as watering every plant on a fixed calendar, and FSRS as checking each plant's soil. Anki has shipped FSRS since version 23.10, and the FSRS project's benchmarks show it predicts forgetting far better than SM-2, which means fewer reviews for the same recall. The `fsrs` Python package (6.3.2, August 2026) implements FSRS-6.

```python
# pip install fsrs   (inside ~/.venvs/brain)
from fsrs import Scheduler, Card, Rating

RATINGS = {"again": Rating.Again, "hard": Rating.Hard, "good": Rating.Good, "easy": Rating.Easy}

def scheduler_for(course):
    """Default 90% target recall; exam mode (2.7) raises it for one course."""
    target = exam_mode_retention(course) or 0.9            # e.g. 0.95 during an exam countdown
    return Scheduler(parameters=load_params(), desired_retention=target)

def review(saved_state, rating, confidence, course):
    """saved_state: this card's FSRS JSON (None if new). confidence: 1-5, asked before reveal."""
    card = Card.from_json(saved_state) if saved_state else Card()
    if rating in ("good", "easy") and confidence <= 2:
        rating = "hard"                  # right but unsure -> comes back sooner (keeps the old SM-2 tweak's intent)
    card, log = scheduler_for(course).review_card(card, RATINGS[rating])
    append_review_log(course, log.to_json())               # feeds the optimizer below
    return card.to_json()
```

- **Near misses:** the old "close but wrong keeps a medium interval" rule is gone. FSRS's relearning step handles a lapse on a well-known card gently by itself.
- **Personal tuning (zero tokens):** after about a month of reviews, a monthly cron job runs `optimize-fsrs.py`: `pip install "fsrs[optimizer]"`, then `Optimizer(review_logs).compute_optimal_parameters()` fits the 21 parameters to *your* memory. It saves them to `03-Resources/study/fsrs-params.json`, and `load_params()` reads them (defaults until then).
- **Review logs:** every review is appended to `review-state/_logs/[course].jsonl` (append-only, Kiosk-written), so the optimizer has your full history.

**Deck spec (what the study skill writes before sending a link) -- added to `Meta/study-session-state.json`:**

```json
"kiosk": {
  "mode": "flashcards",
  "course": "EE225",
  "topics": ["rc-transient-analysis"],
  "include_subtopics": true,
  "interleave": true,
  "related_topics": ["rl-transient-analysis", "thevenin-norton"],
  "filter": "due",
  "limit": 25,
  "url": "https://<desktop>.<tailnet>.ts.net/s/study_20260928_1400/flashcards"
}
```

The Kiosk does the 60/40 primary/related split and the "no more than 3 in a row from one topic" shuffle itself (2.2f).

**Session summary (what the Kiosk writes on Finish -- all Claude ever reads):**

```json
{"session_id": "study_20260928_1400", "mode": "flashcards", "reviewed": 18, "correct": 13,
 "weak_cards": ["ee225_042", "ee225_051"], "overconfident": ["ee225_063"],
 "deleted": ["ee225_014"], "flagged": ["ee225_031"],
 "minutes": 14, "by_topic": {"rc-transient-analysis": [10, 8], "rl-transient-analysis": [8, 5]}}
```

**Safety:**
- Evaluate generated `solution_formula` strings with a safe expression evaluator (`simpleeval` server-side, or `expr-eval` in the browser) -- never `eval()`. The formulas are generated text.
- Bind uvicorn to `127.0.0.1:8484` inside WSL. Nothing listens on your LAN, and there's no router port forwarding.
- Tailscale on Windows publishes it to your tailnet only: `tailscale serve --bg 8484`. That proxies `https://<desktop>.<tailnet>.ts.net` to `localhost:8484`, which mirrored networking (0.0) routes into WSL. Only your signed-in devices can reach it, and no Windows firewall rule is needed.
- Deleting is soft: the card files are never changed, so nothing in the Kiosk can destroy generated material.

**Access from phone and iPad:**
- Install Tailscale (free personal plan) on the desktop (Windows app), phone and iPad; sign into the same account
- The Kiosk is at `https://<desktop>.<tailnet>.ts.net` over Wi-Fi or cellular. The HTTPS certificate also lets the phone treat it as an installable app and makes the offline mode (iteration) possible, since service workers need HTTPS
- Add `/review` and `/today` to your Home Screen (a small PWA manifest gives them app icons)
- iPad: split view with the Claude app (conversation) on one side and the Kiosk on the other

**Setup steps:**

- [ ] Install Tailscale on desktop (Windows), phone, iPad; run `tailscale serve --bg 8484` once in a Windows terminal (the setting persists across reboots)
- [ ] Create `personal/kiosk/` in your fork: `app.py` (FastAPI), `templates/` (one page per route), `static/` (JS, KaTeX vendored locally so it works offline on LAN)
- [ ] Implement the file layer first: read cards/quizzes/formulas/diagrams, apply the `card-edits/` overlay, read/write review-state and card-edits atomically, append review logs, write session summaries to `Meta/events/study-skill/`
- [ ] `~/.venvs/brain/bin/pip install fastapi uvicorn fsrs simpleeval`
- [ ] Implement `/review` first, with delete/edit/flag and Undo from the start. It's useful on day one, even before the study skill exists.
- [ ] Then `/cards` and `/trash`, `/s/{id}/flashcards`, `/s/{id}/quiz`, `/s/{id}/derive`, `/s/{id}/diagrams`, then `/habits`, `/health`, `/today`, `/upload`
- [ ] `personal/scripts/kiosk.sh` runs `uvicorn app:app --host 127.0.0.1 --port 8484` in a restart loop; `boot.sh` starts it (0.0)
- [ ] Add `curl -s http://localhost:8484/*` to the allowlist (0.12) so skills can check the Kiosk is up before sending a link
- [ ] Test: review 5 cards on your phone over cellular -> confirm `review-state/` updated on the desktop -> confirm each card's `fsrs.due` moved forward and `_logs/` grew by 5 lines
- [ ] Test editing: delete a card -> Undo -> delete again -> restore from `/trash`; edit a card -> it shows the new text in the next deck; flag one -> after the 3 AM batch a replacement appears and the original is hidden

**Iteration:**

- [ ] Offline mode: a service worker caches today's due deck and syncs results when the phone reconnects
- [ ] One-tap habit check-ins on `/habits` (append-only log, merged by the habit tracker)
- [ ] A "Tell Claude I'm done" button that copies the session summary line for pasting into chat, for when you're not in a live session

---

## PHASE 1 -- CORE CUSTOM AGENTS

These are the pieces that make the system uniquely yours. Build these before class starts if possible.

---

### 1.1 -- Ingestion Pipeline Agent

**Type:** Custom agent -- fork `agents/<name>.md` (source format, see 0.12), registered in the dispatcher block + registry
**Existing resource:** None -- custom build; local pre-processing (0.11) does the heavy lifting before it runs
**Model:** `mid` (Sonnet 5.5). Classification and reading are already done locally (0.11): `qwen3.5:9b` classifies, `qwen3-vl:8b-instruct` reads images and handwritten PDFs, Marker converts typed documents
**Token tip:** Claude reads `<file>.meta.json` and `<file>.extracted.md`, never the original, except the specific page images with `[?]` words or handwritten math and the figures Marker cut out. A file with no `.meta.json` gets `local-preprocess.py` run on it first.
**Required premade skills:** notebooklm-py CLI (4.1); vision through the Read tool

**Core behavior:**

- Watches for new files arriving in the inbox (triggered by event system, not polling)
- For each new file:

  **Step 1: Determine file type** (image, PDF, audio, text)

  **Step 2: Read `.meta.json` first** (0.11, "How Claude uses pre-processed data"). `confidence: high` means the local classification stands; `low` falls to the fallback chain. Visual categories the chain distinguishes:
  - handwritten notes, diagram/schematic, screenshot, assignment, whiteboard photo, textbook page, graph/chart, photo, personal/non-academic content

  **Step 3: Content classification and routing** -- determine what category this file belongs to using the Smart Classification Fallback Chain (below), then route accordingly:

  | Classification | Route | Generates Study Materials? |
  |---------------|-------|--------------------------|
  | `academic-notes` | File to course folder, trigger study material generation | Yes -- flashcards, quizzes, practice problems |
  | `academic-diagram` | File to course folder + extract to `diagrams/`, trigger image-aware study material generation | Yes -- identification, analysis, and reproduction questions |
  | `assignment` | Route to Decomposer agent | No -- Decomposer handles task breakdown |
  | `rpg-content` | Match the file against each campaign's `aliases` and `character` in `01-Projects/campaigns/*/campaign.json` (3.1) and file to that campaign's `inbox/`. One match: file it. Several or none: ask which campaign (Step 5 of the fallback chain). Homebrew TTRPG design work is `personal-project`, not a campaign | No |
  | `personal-project` | File to relevant project folder (radio-mesh, etc.) | No |
  | `reference` | File to `03-Resources/` general | No |
  | `personal` | File to `02-Areas/Personal/` | No |
  | `unclassified` | File to `00-Inbox/`, ask user or wait for the 3 AM batch (`/inbox-triage`) | No |

  **Critical rule:** Only trigger the study material generation subagent (step 10) for files classified as `academic-notes` or `academic-diagram`. All other classifications skip step 10 entirely.

  **Step 4: Check pending requests** -- check `Meta/pending-requests.md` for open requests (e.g., study skill asked for a diagram). If match found: route to requesting agent, close the request. This overrides the normal routing.

  **Step 5: For audio files:** transcribe locally with Granite Speech (zero tokens), then run the upstream `/transcribe` skill in Lecture Notes mode on the transcript (2.3)

  **Step 6: For documents with embedded content (PDFs, PPTX, DOCX, XLSX):** run the Document Image Extraction Pipeline (see below) to pull out embedded diagrams, charts, formulas, and images before processing text content

  **Step 7: For PDFs that look like assignments:** hand off to Decomposer agent

  **Step 8: Auto-upload to NotebookLM:** If the file is academic course material, look up `courses.<course>.notebook_id` in `Meta/notebooklm-notebooks.json` and run `notebooklm source add "<original file>" -n <notebook_id> --title "<note title>" --timeout 120` (4.1). No entry for the course: `notebooklm create "<course> - <title>" --json` and record it. An upload failure is reported but doesn't stop filing.

  **Step 9: Hand off** -- use upstream's protocol: end the output with `### Suggested next agent` (e.g., `decomposer` for an assignment), and the dispatcher chains it. This works in a live session and inside the 3 AM `claude --print` run alike. Notes left in `{{inbox}}` are filed by `/inbox-triage` (3 AM batch, Step 3), so ingestion doesn't need to chain the Sorter.

  **Step 10: Auto-generate study materials with topic-aware filing** (ONLY for `academic-notes` and `academic-diagram` classifications). Generation is its own skill, `/study-gen` (fork `skills/study-gen/SKILL.md`, `model: sonnet`), not something ingestion starts: in Claude Code an agent can't launch another agent. The 3 AM batch's Step 2 (and "process my uploads") runs `/study-gen` right after ingestion on every academic note without a `study_generated:` date, so the effect is the same. `/study-gen` uses the **Topic Taxonomy System** (below) to file each generated card into the correct topic.
      - Reads the new note (or its summary if the note is long)
      - Identifies ALL distinct topics covered in the note (a single lecture may cover 3-5 topics)
      - For each topic found: generates 3-6 flashcards, 2-4 MC quiz questions, and 1-2 practice problems
      - Also extracts any formulas/equations from the note and saves to per-topic formula sheet files (`[course]/formulas/[topic-slug].json`) for the derive-it mode (2.2i)
      - **For images/diagrams:** runs image-aware generation (see Image-Aware Study Material Generation below)
      - Files each card/question/formula into the correct topic file using the Topic Matching Protocol
      - Before writing a topic's cards, reads that topic's `card-edits/` overlay (0.13) and the course's top deletion reasons, so it doesn't recreate cards you deleted or repeat the same flaw
      - Writes a `new-material` event to `Meta/events/study-skill/` (the next study session or recommendation run picks it up)
      - Adds `study_generated: <date>` to the source note's frontmatter so nothing gets generated twice
      - Cost: ~5,000-8,000 tokens per note, but runs once per note in the background, never during a study session

**Smart Classification Fallback Chain:**

When determining what a file is and where it belongs, the ingestion agent follows this chain in order. Each step is cheaper than the next. Stop as soon as you get a confident match.

```
Step 1: Calendar context (cheapest -- reads today's schedule)
  - If you have EE225 class right now or just had it -> course: EE225
  - If no classes today or file doesn't match any class -> continue

Step 2: Visual text extraction (read text visible in the image)
  - Look for: course numbers, textbook titles, professor names, 
    chapter headers, page numbers, assignment titles
  - "Chapter 5: RC Circuits" -> EE225
  - "Prof. Hosseini" -> match to known professor list
  - If no readable text or no match -> continue

Step 3: Subject matter classification via vision
  - "This is a circuit schematic" -> check course list for circuits course
  - "This is a sorting algorithm visualization" -> COMP_ENG_303
  - "This is an occult diagram" -> not academic
  - "This is a D&D/RPG map" -> rpg-content (campaign picked by the rpg-content row: aliases, then ask)
  - If matches a course: assign course
  - If matches a non-academic category: assign category
  - If unclear -> continue

Step 4: Check dynamic category registry (Meta/image-categories.json)
  - Has the system seen similar images before?
  - If this looks like images that were previously categorized -> 
    use that category
  - If no match -> continue

Step 5: Ask the user
  - Push a short message: "New image received. Couldn't determine 
    context. What's this for?"
  - Options: [course list] / [project list] / "personal" / "reference"
  - Cost: ~500 tokens for the question + your answer
  - If user doesn't respond within reasonable time -> step 6

Step 6: File to inbox as unclassified
  - File to 00-Inbox/ with course: unclassified
  - `/inbox-triage` handles it in the 3 AM batch (Step 3)
  - Never guess wrong and bury something in the wrong folder
```

**Dynamic Category Learning (`Meta/image-categories.json`):**

When the system encounters images it can't classify automatically but you tell it what they are, it learns that category for future recognition. Over time, repeated corrections build up pattern recognition.

```json
{
  "categories": {
    "occult-diagrams": {
      "display_name": "Occult/Esoteric Diagrams",
      "route_to": "02-Areas/Personal/occult-reference/",
      "generates_study_materials": false,
      "example_descriptions": [
        "circular diagram with pentagrams and Hebrew letters",
        "sigil with concentric geometric shapes and symbols",
        "alchemical diagram with planetary symbols"
      ],
      "times_seen": 7,
      "first_seen": "2026-04-05",
      "auto_created": true
    },
    "rpg-maps": {
      "display_name": "RPG/D&D Maps",
      "route_to": "01-Projects/campaigns/{campaign}/maps/",
      "route_note": "campaign resolved from campaign.json aliases; ask if ambiguous",
      "generates_study_materials": false,
      "example_descriptions": [
        "top-down building floor plan with grid overlay",
        "city district map with labeled locations"
      ],
      "times_seen": 4,
      "first_seen": "2026-04-10",
      "auto_created": true
    }
  }
}
```

When the ingestion agent asks you "what's this?" and you say "that's an occult diagram, file it under personal":
1. It checks if a matching dynamic category exists
2. If yes: increments `times_seen`, routes to the stored path
3. If no: creates a new category entry with a vision-generated description as the first example
4. Future images that look similar (checked via vision comparison against `example_descriptions`) match automatically without asking you

After a category reaches 3+ `example_descriptions`, the system should reliably auto-classify similar images without asking. The descriptions are natural language that Claude's vision can compare against: "does this new image look like 'circular diagram with pentagrams and Hebrew letters'?"

**Document Image Extraction Pipeline (Step 6):**

When the ingestion agent processes a document that may contain embedded images, diagrams, charts, or formulas, most of the work is already done locally by Marker (0.11) before Claude runs.

```
What Marker already did (0.11, zero tokens):
- Handwritten PDFs never reach Marker (0.11 PDF routing): the vision
  model reads them page by page, and the page images are listed as
  page_images. They have no extracted_images; a page with a drawn
  diagram is flagged has_diagram, and Claude looks at that page image.
- Typed .pdf / .pptx / .docx / .xlsx / .html -> one Markdown file per document,
  with tables kept, equations written as LaTeX, and every figure saved
  as its own image next to the Markdown (listed in meta.json as
  extracted_images). Each slide or page keeps its heading, so figures
  stay attached to the right context.
- .png/.jpg/standalone images -> read by the local vision model instead
  (0.11); skip this pipeline, already an image.

What the ingestion agent still does, per extracted figure:
1. Skip decorations cheaply: logos, photos of the professor, and tiny
   icons (under ~150 px) are dropped without vision.
2. Use vision on the remaining figures only (never whole pages) to
   describe what each diagram, schematic, graph or chart shows
3. Determine which topic it relates to (Topic Matching Protocol)
4. Save the image to:
   03-Resources/study/[course]/diagrams/[topic-slug]/[diagram-id].png
5. Create a stripped/label-removed version (see Stripped Image Generation)
   Save as: [diagram-id]-stripped.png
6. Create a vault note for the diagram with:
   - description from vision
   - link to parent document note
   - topic tag
   - type: academic-diagram
7. Formulas: copy the LaTeX blocks from Marker's Markdown into the
   per-topic formula sheets (no vision needed -- Marker already wrote
   them as LaTeX)
8. The generation subagent (step 10) processes all extracted content
   (text + diagrams + formulas) using text-aware AND image-aware
   generation to create study materials

Required tools (installed in 0.0 and 0.11):
- Marker (marker_single), Surya (surya_detect), ImageMagick
```

**Stripped Image Generation:**

For diagrams that contain labels (component values, node names, signal names), generate a stripped version with labels obscured. Used for identification and recall questions.

```
Stripped Image Generation (personal/scripts/strip-labels.py, zero tokens):
1. surya_detect finds every text line in the diagram and returns
   pixel-exact bounding boxes (component values like "R1 = 1k",
   node names, signal labels)
2. Pad each box by a few pixels, then use ImageMagick to paint
   background-colored rectangles over each one:
   convert original.png -fill white \
     -draw "rectangle x1,y1 x2,y2" \
     -draw "rectangle x3,y3 x4,y4" \
     stripped.png
3. Verify locally with qwen3-vl:8b-instruct: "Is any text still readable in
   this image? Is the circuit/diagram structure still intact?"
   (structured yes/no answer)
4. If verification fails (label partially visible, or structure
   damaged), fall back to the original only
   (skip identification questions, use only analysis questions)
Claude never sees this step. Previously Claude vision had to guess
pixel coordinates, which it does poorly.
```

**Image-Aware Study Material Generation (addition to step 10 subagent):**

When the generation subagent receives a note classified as `academic-diagram` or processes extracted diagrams from a PDF, it generates image-specific study materials in addition to text-based cards.

```
Image-Aware Generation Protocol:

For each diagram/image in the note:
1. Check if a stripped version exists
   - If yes: generate both identification AND analysis questions
   - If no (stripping failed, or diagram has no labels): 
     generate analysis questions only

2. Generate questions using the STRIPPED image (identification/recall):
   - "Identify this type of circuit/diagram/system"
   - "Label all components in this diagram"
   - "Explain what this circuit/system does"
   - "What is the function of each stage in this block diagram?"
   - "Draw this diagram from memory" (Direction C -- reproduction)
   - "What are the input and output signals?"
   - "Identify the feedback loop in this system"
   (This list is not exhaustive -- adapt to the diagram type)

3. Generate questions using the LABELED/ORIGINAL image (analysis/higher-order):
   - "What does the component labeled R1 do in this circuit?"
   - "If C1 were doubled, how would the output change?"
   - "What kind of component is R2?"
   - "Trace the signal path from input to output"
   - "What would happen if Q2 failed open?"
   - "What kind of circuit/system is this?"
   - "Calculate the gain/frequency/time constant using the labeled values"
   - "Redesign this circuit to achieve [different specification]"
   - "What are the limitations of this design?"
   (This list is not exhaustive -- adapt to the diagram type)

4. Save cards with image references:
```

Card JSON format with image fields:

```json
{
  "id": "ee225_img_001",
  "question": "Label all components in this circuit and identify the filter type.",
  "answer": "R1 (1k ohm resistor), C1 (10uF capacitor). Low-pass RC filter with cutoff at ~16 Hz.",
  "image": "diagrams/rc-filters/filter-001-stripped.png",
  "image_reveal": "diagrams/rc-filters/filter-001-original.png",
  "question_type": "identification",
  "source_note": "[[EE225 Lecture 5]]",
  "topic": "rc-filters"
},
{
  "id": "ee225_img_002",
  "question": "If the capacitor labeled C1 in this circuit were doubled to 20uF, what happens to the cutoff frequency?",
  "answer": "Cutoff frequency halves: fc = 1/(2*pi*RC). Doubling C halves fc from ~16 Hz to ~8 Hz.",
  "image": "diagrams/rc-filters/filter-001-original.png",
  "image_reveal": null,
  "question_type": "analysis",
  "source_note": "[[EE225 Lecture 5]]",
  "topic": "rc-filters"
},
{
  "id": "ee225_img_003",
  "question": "Study this circuit for 30 seconds, then draw it from memory.",
  "answer": null,
  "image": "diagrams/rc-filters/filter-001-original.png",
  "image_reveal": "diagrams/rc-filters/filter-001-original.png",
  "question_type": "reproduction",
  "source_note": "[[EE225 Lecture 5]]",
  "topic": "rc-filters"
}
```

The Kiosk's `/s/{id}/diagrams` page (0.13) renders differently based on `question_type`:
- `identification`: shows `image` (stripped), flips to `image_reveal` (labeled original) as answer
- `analysis`: shows `image` (labeled original) alongside the question, answer is text
- `reproduction`: shows `image` briefly (timed display), then hides it and shows an upload box. You draw from memory and upload straight from the page (no Drive round trip). The study skill then compares the drawing using vision (Direction C from 2.2h).

**Topic Taxonomy System:**

Study materials are organized by TOPIC, not by source note. A single lecture might produce cards filed into 3 different topic buckets. A topic that appears across 5 different lectures has all its cards in one place.

**Directory structure:**

```
03-Resources/study/
  EE225/
    topics.json              # master topic registry for this course
    cards/
      mosfet-operating-regions.json
      rc-transient-analysis.json
      kirchhoffs-laws.json
      thevenin-norton.json
    quizzes/
      mosfet-operating-regions.json
      rc-transient-analysis.json
      ...
    formulas/
      mosfet-operating-regions.json
      rc-transient-analysis.json
      kirchhoffs-laws.json
      ...
    diagrams/
      mosfet-operating-regions/
        mosfet-regions-001.png
        mosfet-regions-001-stripped.png
      rc-transient-analysis/
        rc-filter-001.png
        rc-filter-001-stripped.png
        rc-step-response-graph-001.png
      ...
  COMP_ENG_303/
    topics.json
    cards/
      spatial-partitioning.json
      sorting-algorithms.json
      graph-traversal.json
    quizzes/
      ...
    formulas/
      ...
    diagrams/
      ...
```

**Topic registry format -- `topics.json`:**

```json
{
  "course": "COMP_ENG_303",
  "topics": {
    "sorting-algorithms": {
      "display_name": "Sorting Algorithms",
      "aliases": [
        "sorting", "sorts", "sort algorithms",
        "algorithmic ordering", "data arrangement",
        "ordering algorithms", "array sorting",
        "comparison sorts", "exchange-based ordering"
      ],
      "subtopics": ["bubble-sort", "merge-sort", "quicksort", "insertion-sort"],
      "related_topics": ["complexity-analysis", "data-structures"],
      "source_notes": ["[[CE303 Lecture 5]]", "[[CE303 Lecture 7]]"],
      "card_count": 15,
      "quiz_count": 6,
      "last_updated": "2026-04-03",
      "first_studied": null,
      "times_studied": 0,
      "last_studied": null
    },
    "bubble-sort": {
      "display_name": "Bubble Sort",
      "aliases": ["bubble sorting", "naive sort", "simple exchange sort"],
      "parent_topic": "sorting-algorithms",
      "related_topics": ["insertion-sort"],
      "source_notes": ["[[CE303 Lecture 5]]"],
      "card_count": 6,
      "quiz_count": 3,
      "last_updated": "2026-04-03",
      "first_studied": null,
      "times_studied": 0,
      "last_studied": null
    }
  }
}
```

**Topic Matching Protocol (generation subagent prompt):**

```
## Topic Matching Protocol

For each card/question you generate, assign it to the correct topic:

### Step 1: Generate candidate topic names
For the concept being tested, generate 4-6 alternate phrasings of what 
this topic could be called. Include the formal name, informal/colloquial 
name, abbreviations, and how a student would casually describe it.

Example -- card tests "time complexity of bubble sort":
Candidates: ["bubble sort", "bubble sorting", "bubble sort algorithm", 
             "simple exchange sort", "naive sorting", "sorting"]

Example -- card tests "Thevenin equivalent circuit":
Candidates: ["thevenin equivalent", "thevenin's theorem", 
             "thevenin circuit", "equivalent circuit", 
             "source transformation", "circuit simplification"]

Example -- card about "spatial partitioning using BSP trees":
Candidates: ["spatial partitioning", "space partitioning", "BSP", 
             "BSP trees", "binary space partitioning", 
             "spatial subdivision"]

### Step 2: Match ALL candidates against topic registry
Check EVERY candidate against topic names AND alias arrays in 
topics.json. If ANY candidate matches ANY topic name or alias, 
assign to that topic.

Also check if any candidate matches a subtopic or parent topic.
Choose the most specific match: if "bubble sort" matches both 
"bubble-sort" (subtopic) and "sorting-algorithms" (parent via 
alias "sorting"), assign to "bubble-sort".

### Step 3: Grow the alias list on every match
When a match is found, add ALL unmatched candidates from Step 1 
to the matched topic's alias list. This makes the registry smarter 
with every card generated.

Example: candidates ["exchange-based ordering", "sorting", 
"comparison sorting", "sort methods"] matched "sorting-algorithms" 
via the alias "sorting". Add "exchange-based ordering", 
"comparison sorting", and "sort methods" to the alias list.

### Step 4: Subtopic check (if match found but specificity unclear)
If the concept is more specific than the matched topic, check if 
it should be a subtopic. Decision rule: if the concept only makes 
sense IN THE CONTEXT OF the parent topic, it's a subtopic.

"Bubble sort" only makes sense in context of sorting -> subtopic.
"Time complexity" makes sense across many contexts -> peer topic.

Subtopic cards go in their own file. When the study skill loads 
the parent topic, it also loads all subtopic cards. Studying 
"sorting" includes bubble sort cards, but studying "bubble sort" 
gives you only those specific cards.

### Step 5: Semantic fuzzy match (local embeddings -- zero tokens)
Only if Steps 1-3 find no match for ANY candidate. Run
personal/scripts/topic-match.py "<candidate>" --course <course>.
It embeds the candidate with qwen3-embedding:0.6b (Ollama) and
compares it against every topic's display_name + aliases (embeddings
cached in [course]/topics.embeddings.json, refreshed when topics.json
changes). Cosine similarity >= 0.85: treat as a match, and add all
candidates as aliases. 0.75-0.85: read the first 3 cards of that one
topic to confirm. Below 0.75: no match.

This should rarely fire -- Step 1's multi-candidate generation 
catches 95%+ of cases before reaching here.

### Step 6: Create new topic (only if Steps 1-5 all fail)
When creating a new topic:
- Use the most common/standard phrasing as the slug
- Set display_name to the formal name
- Add ALL candidates from Step 1 as initial aliases
- Check if it should be a subtopic of an existing topic
- Add related_topics links to conceptually adjacent topics
- Add to topics.json

### Rules:
- A topic is a CONCEPT, not a source or context. These are NOT topics:
  "Lecture 7 material", "Exam prep", "Homework 3", "Things I got wrong"
- Use consistent topic slugs: lowercase, hyphens, no abbreviations
  ("rc-transient-analysis" not "RC_trans" or "rc analysis")
- Cross-course topics: keep in respective course folders but add 
  cross-references in related_topics (e.g., "EE225/fourier-transform")
- Always prefer appending to an existing topic over creating a new one
```

**How the study skill uses the hierarchy:**

When you say "study sorting":
1. Looks up "sorting" -> matches `sorting-algorithms` via aliases
2. Loads `cards/sorting-algorithms.json` (15 cards)
3. Sees `subtopics: ["bubble-sort", "merge-sort", "quicksort", "insertion-sort"]`
4. Loads ALL subtopic card files too (total ~41 cards)
5. Full deck covers sorting holistically from all lectures that touched the topic

When you say "study bubble sort" specifically:
1. Loads only `cards/bubble-sort.json` (6 cards)
2. Doesn't load parent or sibling topics unless interleaving mode requests them

When the interleaving engine (2.2f) runs:
1. Reads `related_topics` to find conceptually adjacent topics for mixing
2. Can also find cross-course connections (Fourier in EE225 + linear algebra)

**Frontmatter template it generates:**

```yaml
---
summary: "[auto-generated 2-3 sentence summary]"
source: drive-inbox | slack | manual
type: lecture-notes | diagram | assignment | whiteboard | audio-transcript | general
course: EE225 | COMP_ENG_393 | etc.
date_ingested: 2026-03-29
status: processed
original_filename: "032.pdf"
---
```

**Pending request system:**

```yaml
# Meta/pending-requests.md
- id: req_001
  type: diagram
  topic: "RC circuit transient response"
  course: EE225
  requested_by: study-skill
  requested_at: 2026-03-29T14:30:00
  status: awaiting
```

**Steps:**

- [x] Write the agent prompt (.md file)
- [x] Add to `.claude/agents/` directory
- [x] Create `Meta/pending-requests.md` template
- [x] Create the topic taxonomy directory structure: `mkdir -p 03-Resources/study/{EE225,COMP_ENG_303,...}/{cards,quizzes,formulas,diagrams}` for each course
- [x] Create initial `topics.json` for each course (can be empty `{"course": "EE225", "topics": {}}`)
- [x] Create initial `Meta/image-categories.json` (can be empty `{"categories": {}}`)
- [x] Write the generation subagent prompt that includes the Topic Matching Protocol AND the Image-Aware Generation Protocol (this is a separate .md file the ingestion agent spawns as a subagent)
- [ ] ImageMagick and poppler-utils are already installed in WSL (0.0); Marker and Surya in the venv (0.11)
- [ ] Document extraction is Marker, installed in 0.11 -- nothing extra here
- [ ] Test with: drop a photo of handwritten notes into Drive -> confirm classification and vault note creation
- [ ] Test with: study skill requests a diagram -> drop an image -> confirm it routes correctly
- [ ] Test with: drop a PDF assignment -> confirm handoff to Decomposer
- [ ] Test topic matching: drop a note covering 2+ topics -> confirm cards are split into separate topic files
- [ ] Test alias growth: drop a second note mentioning an existing topic with different phrasing -> confirm it matches the existing topic and aliases expand
- [ ] Test subtopic creation: drop a note about a specific subtopic (e.g., "bubble sort") -> confirm it creates a subtopic under the parent ("sorting-algorithms") rather than a new peer topic
- [ ] Test image classification: drop a non-academic image -> confirm it does NOT generate study materials and routes to correct non-academic folder
- [ ] Test smart classification chain: drop an image with no calendar context -> confirm it tries vision text extraction, then subject matter classification, then asks you
- [ ] Test dynamic category learning: classify 3 similar images manually -> confirm the 4th auto-classifies without asking
- [ ] Test PDF image extraction: drop a PDF with embedded diagrams -> confirm diagrams are extracted as separate image files in `diagrams/[topic]/`
- [ ] Test stripped image generation: confirm labeled diagrams produce a stripped version with labels obscured
- [ ] Test image-aware card generation: drop a circuit diagram -> confirm it generates both identification questions (using stripped image) and analysis questions (using labeled original)

**Iteration:**

- [ ] Handwriting OCR is now handled locally in 0.11; revisit the `UNSURE_LIMIT` threshold after a few weeks based on how often Claude had to re-check pages
- [ ] Add audio transcription handoff (detect .m4a, .mp3, .wav -> trigger Transcriber)
- [ ] Add support for multiple files in batch (e.g., 5 photos of whiteboard from a single lecture)
- [x] **NotebookLM mapping file:** `Meta/notebooklm-notebooks.json` maps course codes (the folder names in `03-Resources/study/`) to NotebookLM notebook IDs. When a new course has no notebook, ingestion creates one with `notebooklm create` and adds it. Format:

```json
{
  "updated": "2026-09-30",
  "courses": {
    "EE202": {
      "title": "Introduction to Electrical Engineering",
      "notebook_id": "6c64aa82-6765-4e39-82a1-fed2aba4b4b9",
      "notebook_title": "EE202 - Introduction to Electrical Engineering"
    }
  }
}
```

- [ ] **Auto-generation refinement:** Test the full pipeline: drop a lecture note -> confirm cards and quizzes appear in the correct per-topic JSON files within a few minutes. Verify the topic registry updated. Verify the quiz JSON format in `03-Resources/study/[course]/quizzes/[topic-slug].json`:

```json
{
  "topic": "mosfet-operating-regions",
  "course": "EE225",
  "quizzes": [
    {
      "id": "ee225_q001",
      "type": "multiple_choice",
      "question": "Which condition indicates a MOSFET is in the triode region?",
      "options": ["Vds < Vgs - Vt", "Vds > Vgs - Vt", "Vgs < Vt", "Vds = 0"],
      "correct_answer": 0,
      "explanation": "In triode region, the channel is not pinched off, so Vds must be less than Vgs - Vt.",
      "source_note": "[[EE225 Lecture 3]]",
      "created": "2026-04-01"
    },
    {
      "id": "ee225_p001",
      "type": "practice_problem",
      "question": "Given R = {R} ohms and C = {C} farads, find the time constant and voltage across the capacitor at t = {t} seconds after a step input of {V} volts.",
      "variable_ranges": {"R": [100, 10000], "C": [0.000001, 0.001], "t": [0.001, 0.1], "V": [1, 12]},
      "solution_formula": "tau = R * C; Vc = V * (1 - exp(-t / tau))",
      "solution_steps": ["1. Calculate tau = R * C", "2. Apply Vc(t) = V(1 - e^(-t/tau))", "3. Substitute values"],
      "source_note": "[[EE225 Lecture 5]]",
      "created": "2026-04-01"
    }
  ]
}
```

Note: the practice problem above would be in `quizzes/rc-transient-analysis.json`, NOT in `quizzes/mosfet-operating-regions.json` -- even though both come from EE225, the Topic Matching Protocol in step 10 files them by concept, not by course. The MC question about MOSFETs goes to the MOSFET topic, the RC problem goes to the RC topic. Each quiz file is per-topic, same as cards.

- [ ] **Topic matching test:** Drop a note that covers 2-3 topics -> verify cards are split across the correct topic files, not all dumped into one. Drop a second note that mentions an existing topic -> verify new cards are APPENDED to the existing topic file and aliases grew.

---

### 1.2 -- Decomposer Agent

**Type:** Custom agent -- fork `agents/<name>.md` (source format, see 0.12), registered in the dispatcher block + registry
**Existing resource:** None -- custom build
**Model:** Sonnet (needs reasoning for task breakdown, but not Opus-level)
**Token tip:** Load only the assignment description/rubric, not surrounding course materials. Output structured frontmatter, not prose.
**Required premade skills:** None

**Core behavior:**

- Receives assignment information (from Canvas MCP, manual upload, or ingestion pipeline)
- Parses the assignment into:
  1. Overall deliverable and due date
  2. Discrete subtasks in dependency order
  3. Estimated time per subtask
  4. Estimated effort level (1-5) per subtask
  5. Which subtasks can be done at low energy vs. require high focus
- Creates linked task notes in the vault, one per subtask
- Sets intermediate deadlines working backward from the due date (with buffer)
- Identifies the "first available task" (no unmet dependencies, ready to start)
- No hand-off needed for the Distributor to find the new tasks -- it scans task frontmatter every time it runs. In a live session, end output with `### Suggested next agent: distributor` only if you want the first task offered right away. When run unattended (3 AM batch), write a `new-tasks` event to `Meta/events/distributor/` so the next Distributor run can mention them.

**Task note template it generates:**

```yaml
---
summary: "Write the methods section for EE225 Lab 3 report"
type: task
course: EE225
parent_assignment: "[[EE225 Lab 3 Report]]"
effort: 3
time_est: 45min
priority: high
status: ready | blocked | in-progress | done
depends_on:
  - "[[EE225-lab3-collect-data]]"
  - "[[EE225-lab3-process-matlab]]"
blocks:
  - "[[EE225-lab3-write-results]]"
due_date: 2026-04-05
intermediate_deadline: 2026-04-02
energy_type: high-focus
tags: [writing, lab-report]
---

## Task: Write Methods Section

**What:** Describe the experimental setup, equipment used, and procedure followed for the RC circuit transient analysis experiment.

**Acceptance criteria:**
- Describes equipment with model numbers
- Procedure is reproducible from description alone
- Includes circuit diagram reference
- 300-500 words

**Context:** The data collection and MATLAB processing must be done first. Reference the processed figures.
```

**Steps:**

- [ ] Write the agent prompt (.md file)
- [ ] Add to `.claude/agents/` directory
- [ ] Create task note template in `Templates/`
- [ ] Test with: manually create a fake assignment with rubric -> trigger Decomposer -> verify task tree is correct
- [ ] Test with: a real assignment from one of your courses
- [ ] Verify the Distributor (1.3) can read the generated task metadata

**Iteration:**

- [ ] Add intelligence about YOUR working patterns (e.g., you write better in the morning, code better at night -- adjust effort estimates accordingly)
- [ ] Add "redecompose" capability -- if you finish a subtask and realize the remaining plan is wrong, you can say "redecompose from here" and it adjusts
- [ ] Connect to grade tracker (2.4) -- assignments for courses where you're borderline get tighter deadlines and higher priority

---

### 1.3 -- Distributor Agent

**Type:** Custom agent -- fork `agents/<name>.md` (source format, see 0.12), registered in the dispatcher block + registry
**Existing resource:** Kipi System's friction-ordering and ADHD-friendly patterns (port concepts, not code)
**Model:** Haiku (this is a filtering/ranking task, not a reasoning task -- keep it cheap)
**Token tip:** This agent should NEVER read full notes. It reads ONLY frontmatter metadata across task notes. Use `grep -r "^---" -A 20` to extract frontmatter blocks efficiently. This is the most frequently called agent so every token matters.
**Required premade skills:** None

**Core behavior:**

- When you say "I have [X minutes] at [Y/5] energy" or just "what should I do":
  1. Scans all task notes with `status: ready` by reading only their frontmatter
  2. Filters by time (<= your available time)
  3. Filters by effort (<= your energy level)
  4. Ranks remaining tasks by: priority > due date proximity > whether it unblocks other tasks
  5. Returns the SINGLE best task with brief context
  6. If no tasks fit your constraints, suggests non-academic tasks (campaign prep, personal projects, a quick Kiosk flashcard review)

- When you say "done" or "finished": marks current task as done, checks if this unblocks any dependent tasks, updates their status to `ready`, logs actual duration to `Meta/task-timing.json` (see below), and offers the next task

- At the start of every run: reads its post-it (`Meta/states/distributor.md`, upstream's per-agent state file) and its event folder (`Meta/events/distributor/` -- Trello completions, new tasks from the batch, grade alerts, study recommendations). At the end of every run: overwrites the post-it with the current task, its path, `task_started_at`, and the energy level you reported (max 30 lines, per upstream's post-it protocol).

- Missing frontmatter: Scribe-captured to-dos may lack `effort`/`time_est`/`priority`. Assume `effort: 2`, `time_est: 15min`, `priority: medium` for ranking; the 3 AM batch fills in real values.

**Task Duration Tracking:**

Every time you start a task (Distributor assigns it), `task_started_at` goes into the Distributor's post-it (it's a subprocess, so it keeps no memory between runs -- the post-it is its memory). When you say "done," it reads the start time back, calculates actual duration, and stores the ratio of actual vs estimated time. This data improves future estimates across the entire system.

```json
{
  "timing_history": [
    {
      "task_path": "01-Projects/ee225/lab3-methods.md",
      "type": "writing",
      "course": "EE225",
      "estimated_min": 45,
      "actual_min": 62,
      "ratio": 1.38,
      "energy_at_start": 3,
      "date": "2026-04-10"
    }
  ],
  "averages_by_type": {
    "writing": {"avg_ratio": 1.25, "samples": 12},
    "coding": {"avg_ratio": 1.40, "samples": 8},
    "reading": {"avg_ratio": 0.85, "samples": 15},
    "problem-set": {"avg_ratio": 1.55, "samples": 6},
    "study-session": {"avg_ratio": 1.10, "samples": 20}
  }
}
```

**How other components use this data:**
- **Decomposer:** Reads `averages_by_type` when estimating subtask durations. If you consistently take 1.4x longer on coding tasks, future coding estimates are inflated by 1.4x.
- **Dynamic Scheduler:** Uses corrected estimates for block durations. A "45 min" writing task becomes a 56-min block if your writing ratio is 1.25.
- **Distributor itself:** If you ask "what can I do in 30 minutes?" and your coding ratio is 1.4x, a task estimated at 30 min of coding is actually ~42 min for you -- Distributor filters it out.

**Token cost:** ~200 extra tokens per "done" invocation (reading task-timing.json, updating one entry). Negligible since Distributor already runs on that turn.

- ADHD-friendly language (from Kipi):
  - Never says "overdue" -- says "carried forward"
  - Never says "you forgot" -- says "not yet started"
  - Acknowledges effort: "That's 3 tasks today" regardless of what's left
  - Quick wins first at low energy, deep work when energy is high

**Steps:**

- [ ] Write the agent prompt (.md file) -- keep it under 500 words
- [ ] Add to `.claude/agents/` directory
- [ ] Ensure Scribe and Decomposer both generate the frontmatter format the Distributor reads
- [ ] Test with: create 5 fake tasks with varying effort/time/priority -> "I have 20 minutes at energy 2" -> verify it picks correctly
- [ ] Test with: "done" -> verify task status updates and next task is offered
- [ ] Test with: no tasks fit -> verify it suggests non-academic alternatives

**Iteration (add these features in order, each depends on previous):**

- [ ] **Rest detection:** Track energy self-reports over time. If energy has been <=2 for the last 3 check-ins, suggest taking a break instead of assigning a task. ("You've been running low all day. Nothing is due tomorrow. Consider stopping.")
- [ ] **Time-of-day awareness:** Read current time. Weight certain task types differently (writing tasks in morning, coding in afternoon/evening, low-effort admin in late evening)
- [ ] **Grade tracker integration (requires 2.4):** When grade projections show you're borderline in a course, automatically boost priority for that course's tasks
- [ ] **Weekly velocity tracking:** Track how many tasks you complete per week, average time per task type. Use this to improve time estimates on future task decompositions.
- [ ] **Calendar awareness:** Read today's calendar. If you have class in 30 minutes, don't suggest a 45-minute task. If you have a 2-hour gap, suggest a deep focus task.

---

## PHASE 2 -- ACADEMIC FEATURES

Build these in the first 2 weeks of the quarter as you settle into your routine.

---

### 2.1 -- Pre-Lecture Prep (Scheduled Notification)

**Type:** Small custom skill `/pre-lecture` (fork `skills/pre-lecture/SKILL.md`) fired by cron. It isn't a Seeker mode: Seeker is a core agent, so edits to it are blocked at runtime and overwritten on update.
**Existing resource:** Calendar cache (3.10) for class times; note summaries in frontmatter
**Model:** Haiku (simple retrieval + summary)
**Token tip:** Generate the prep note once and cache it. Don't regenerate if you check it multiple times. Use frontmatter summaries, not full notes.
**Required premade skills:** None

**Core behavior:**

- Runs 30 minutes before each class (triggered by cron reading your calendar, not /loop)
- Pulls your notes from the previous lecture on that course (using grep for course tag + date sort)
- Generates a 2-minute refresher: key concepts, unresolved questions you flagged, any assignment due soon for that class
- Pushes to your phone via one of:
  - Trello card (using Trello automation)
  - Slack message to your `#brain-inbox`
  - Just available via Remote Control when you check in

**Steps:**

- [ ] Write a cron script that reads the local calendar cache (`Meta/schedule/calendar-cache.json`, zero tokens) and fires `/pre-lecture <course>` 30 min before any class event
- [ ] Write the `/pre-lecture` skill: "Find the most recent 2-3 notes for [course] (grep the course tag, sort by date), read only their frontmatter summaries, and write a brief refresher to `{{daily}}/`. Include any assignment due within 3 days and any weak areas the study skill flagged."
- [ ] Test with: manually trigger for one of your courses -> verify output is concise and useful
- [ ] Add to cron schedule

**Iteration:**

- [ ] Add: if there's an assignment due within 3 days for that course, mention it in the prep
- [ ] Add: if study skill has flagged weak areas in this course, remind you of them

---

### 2.2 -- Study Skill (Comprehensive Learning System)

**Type:** Custom skill -- fork `skills/study/SKILL.md`, registered in the dispatcher block (0.12)
**Existing resources to integrate:**
  - notebooklm-py (teng-lin/notebooklm-py, 4.1) -- for managing notebooks, adding sources, and generating conceptual questions from course-specific notebooks
  - michalparkola/tapestry-skills "Learn This" -- for learning new concepts
  - BirgerMoell/study-buddy-skill -- for inspiration on flashcard generation (but customized since you don't use Studium)
**Model:** Sonnet for Socratic dialogue, teach-back, brain dump evaluation, and question generation (at ingestion time). The Kiosk (0.13) for flashcard review, MC quizzes, formula practice and diagram recognition (zero tokens per interaction). Haiku for session logging via a forked helper skill (2.2k).
**Token tip:** Cards, quizzes, and practice problems are pre-generated at ingestion time and stored in per-topic JSON files. During a session the skill only writes a deck spec and sends a Kiosk link (~150 tokens); the Kiosk builds the page from disk. Only Socratic dialogue, teach-back, brain dump evaluation and short-answer evaluation spend Sonnet tokens during the session.
**Required premade skills:** notebooklm-py (4.1), for conceptual question generation from course-specific notebooks

**Sub-features (build in this order):**

#### 2.2a -- Flashcard Generator & FSRS Spaced Repetition Engine

**What it does:** Takes lecture notes/documents, generates Q&A flashcard pairs, stores them with spaced repetition metadata, and runs review sessions using the FSRS-6 algorithm.

**Implementation:**

- Cards stored in per-topic JSON files under `03-Resources/study/[course]/cards/[topic-slug].json`:

```json
{
  "topic": "mosfet-operating-regions",
  "course": "EE225",
  "cards": [
    {
      "id": "ee225_001",
      "question": "What condition must be met for a MOSFET to be in saturation?",
      "answer": "Vds > Vgs - Vt (drain-source voltage exceeds gate-source voltage minus threshold voltage)",
      "source_note": "[[EE225 Lecture 3]]",
      "created": "2026-04-01"
    }
  ]
}
```

**Content and schedule live in separate files.** This file holds card *content* only, written by the generation/remediation subagents. Your review schedule (FSRS stability, difficulty, due date, confidence history) lives in `review-state/[topic-slug].json`, written only by the Kiosk (0.13). One writer per file means new cards can be added at 3 AM while you're mid-review, with no collisions.

Cards from different lectures that cover the same topic all end up in the same file. When you say "study MOSFET operating regions," the skill loads this one file and gets every card on that topic regardless of which lecture it came from. See the Topic Taxonomy System in section 1.1 for how cards are matched to topics at generation time.

- Scheduling uses FSRS-6 with one tweak: a card you got right but rated low confidence counts as Hard, so it comes back sooner. FSRS's own relearning step replaces the old "near miss" rule. (Implemented in the Kiosk server -- code in 0.13.)

**Review delivery: the Kiosk (not conversational, not an artifact).**

Flashcard review happens in the Kiosk's browser page, NOT as a back-and-forth conversation with Claude. Two ways in:
- **Standalone:** open `/review` from your Home Screen -- every due card across all courses. Claude isn't involved at all: zero tokens, and it works even when you've hit your usage limit.
- **In a study session:** the study skill writes a deck spec (topics, interleave flag, filter) and sends a `/s/{id}/flashcards` link (~150 tokens).

The page includes:
- Card display with tap/click to flip
- Confidence prompt (1-5) before the reveal (feeds calibration tracking, 2.2g)
- Self-rating buttons (Again / Hard / Good / Easy) -- the server updates `review-state/` after every card, so nothing is lost if you close the tab
- Progress bar showing cards remaining
- Finish screen with accuracy and weak cards; a compact summary goes to `Meta/events/study-skill/` for the study skill to read

**Token cost comparison:**
- Conversational review of 20 cards: ~16,000 tokens (each card is a round trip to Claude)
- Kiosk review of 20 cards in a session: ~150 tokens (deck spec + link) + ~300 (reading the summary) + 0 per card
- Kiosk review from `/review`: 0

**Card generation is separate from card review -- and happens automatically at ingestion time.**

- **Generation (background, at ingestion):** When new course material enters the vault, the `/study-gen` skill (1.1, step 10) generates flashcards right after ingestion and saves them to the card JSON file. This costs ~5,000-8,000 tokens per note but runs once in the background. By the time you sit down to study, cards already exist.
- **Review (interactive, at study time):** The Kiosk loads pre-made cards from the JSON files and your schedule from `review-state/` -> you review. Zero generation cost during the study session.
- **Remediation generation (after study, not during):** If the orchestrator detects you're weak on a concept (brain dump gaps, repeated wrong answers, low confidence), it flags the topic. AFTER the study session ends, a subagent generates 5-10 targeted remediation cards for that specific weakness and saves them for next time. This keeps the interactive study session lean -- you never wait for card generation mid-session.

**Token cost comparison for a study session with 20 cards:**

| Approach | Generation Cost | Review Cost | Total During Session |
|----------|----------------|-------------|---------------------|
| Generate + review in session (old) | ~5,000 | ~16,000 (conversational) | ~21,000 |
| Pre-generated, conversational review | 0 (already done) | ~16,000 | ~16,000 |
| Pre-generated, artifact review (previous revision) | 0 (already done) | ~4,000 (artifact) | ~4,000 |
| Pre-generated, Kiosk review (current) | 0 (already done) | ~450 (spec + summary) | ~450 |

Pre-generation + the Kiosk = ~98% cheaper than the naive approach, and results actually persist.

**Steps:**

- [ ] Write the card generation prompt (used by ingestion pipeline's subagent, NOT the study skill itself). This prompt tells the subagent how to read a note and produce well-formed flashcards in the JSON format.
- [ ] Define the JSON card format (already specified above)
- [ ] Build the Kiosk's `/review` and `/s/{id}/flashcards` pages (0.13); FSRS runs server-side and writes `review-state/` after every card
- [ ] Study skill: write the deck spec, send the link, then read the session summary from `Meta/events/study-skill/` when you say "done"
- [ ] Write the remediation card generation prompt (triggered by orchestrator after sessions where weak areas are identified). Saves new targeted cards to the JSON file for next session.
- [ ] Test full pipeline: drop a lecture note into Drive -> ingestion processes it -> cards auto-generated in JSON -> start study session -> Kiosk loads pre-made cards -> review -> `review-state/` updates persist
- [ ] Test remediation flow: study session identifies weak area -> session ends -> remediation subagent generates targeted cards -> next study session includes them
- [ ] Test from the phone: start a session over Remote Control -> tap the Kiosk link -> review over cellular (Tailscale) -> say "done" -> skill reads the summary

#### 2.2b -- Quiz Generator (Multiple Choice, Short Answer, Practice Problems)

**What it does:** Generates course-appropriate practice questions that go beyond flashcard recall.

- Multiple choice with plausible distractors
- Short answer requiring explanation
- Practice problems with novel values (for math/circuits/signals courses)
- "Which method applies?" discrimination questions (for interleaving)

**Delivery: hybrid -- the Kiosk for MC/auto-checkable, conversational for open-ended.**

Multiple-choice quizzes and formula-based problems with known answers run on the Kiosk's `/s/{id}/quiz` page (same flow as flashcards -- deck spec + link, zero tokens per question). The page auto-checks answers, shows explanations on click, and logs attempts to `review-state/`.

Short-answer and open-ended "explain why" questions must be conversational (Sonnet) because Claude needs to evaluate your free-form response.

Practice problems with novel numerical values: the Kiosk generates random values from `variable_ranges` and checks your answer against `solution_formula` using a safe expression evaluator (never `eval`). For example, an RC circuit problem where R and C are randomized but the solution formula (tau = RC) is baked into the JS. This means unlimited practice problems at zero token cost per problem.

**Steps:**

- [ ] Quiz generation is handled by the ingestion pipeline subagent (same as flashcards -- step 10 in 1.1). The subagent generates MC questions and practice problems with solution formulas at ingestion time and saves to per-topic files in `[course]/quizzes/[topic-slug].json`.
- [ ] Build the Kiosk's `/s/{id}/quiz` page that reads from the per-topic quiz JSON file. For MC: renders questions with clickable options, shows explanation on answer. For practice problems: randomizes values from `variable_ranges`, auto-checks against `solution_formula`, shows step-by-step solution.
- [ ] Short-answer evaluation stays conversational (Sonnet) -- these can't be auto-checked
- [ ] Test with: drop lecture notes -> verify quiz JSON auto-populates -> start study session -> Kiosk quiz page loads pre-made questions
- [ ] Test novel value generation: same practice problem template with different numbers each time (all in the Kiosk, 0 tokens)

#### 2.2c -- Socratic Dialogue Mode

**What it does:** Guided discovery conversation where the system asks probing questions to lead you to understanding, rather than telling you answers.

- Uses notebooklm-py (4.1) to generate deep conceptual questions from the course-specific notebook. Reads `Meta/notebooklm-notebooks.json` to find the correct notebook for the topic being studied, then asks that notebook directly.
- Follows up with "why?" and "how?" questions (elaborative interrogation)
- If you're stuck, gives hints rather than answers
- Tracks which concepts you struggled with and flags them for future review

**Steps:**

- [ ] Add Socratic mode to the study skill
- [ ] Integrate notebooklm-py -- study skill reads the notebook mapping file, selects the correct notebook for the topic, and runs `notebooklm ask` against it to generate source-grounded conceptual questions (check `notebooklm --help` for the exact notebook-selection flag)
- [ ] Test with: "teach me about [topic] Socratically" -> verify it asks questions rather than lecturing
- [ ] Verify questions are grounded in YOUR course material (from the notebook), not generic knowledge

#### 2.2d -- "Teach It Back" Mode (Feynman Technique)

**What it does:** Asks you to explain a concept as if teaching a first-year student, then critiques your explanation.

- Points out gaps, inaccuracies, oversimplifications
- Asks follow-up questions about weak points in your explanation
- "You said X, but what happens when Y condition applies?"

**Steps:**

- [ ] Add teach-back mode to the study skill
- [ ] Test with: "let me teach you about [topic]" -> verify it identifies gaps in your explanation

#### 2.2e -- Generation Effect Prompting

**What it does:** Before showing you new material, asks you to PREDICT or GENERATE an answer first.

- "Before I show you how a JK flip-flop works, based on what you know about SR latches, what problem do you think it solves?"
- Getting it wrong then seeing the answer produces stronger memory than just reading

**Steps:**

- [ ] Add prediction prompts before new material in all study modes
- [ ] Track prediction accuracy over time as a metacognition metric

#### 2.2f -- Interleaving (Session-Level Strategy, NOT a Standalone Mode)

**What it is:** Interleaving is NOT a mode you select alongside flashcards or Socratic. It's a **session-level strategy flag** that changes how EVERY mode in the session behaves. When active, all modes pull from multiple related topics and shuffle them together instead of focusing on one topic.

**The rule is simple:**

- **First time studying a topic:** Single-topic mode. Deep dive to build the foundation. The orchestrator sets `first_studied` date in `topics.json`.
- **Every subsequent time studying that topic:** Interleaved mode automatically. The orchestrator reads `first_studied`, sees it's not null, and activates interleaving for the session.

No manual decision needed. The system tracks it.

**Tracking in `topics.json`:**

Add `first_studied` and `times_studied` fields to each topic entry:

```json
{
  "sorting-algorithms": {
    "display_name": "Sorting Algorithms",
    "aliases": ["sorting", "sorts", ...],
    "subtopics": ["bubble-sort", "merge-sort", ...],
    "related_topics": ["complexity-analysis", "data-structures"],
    "source_notes": ["[[CE303 Lecture 5]]"],
    "card_count": 15,
    "quiz_count": 6,
    "last_updated": "2026-04-03",
    "first_studied": "2026-04-05",
    "times_studied": 3,
    "last_studied": "2026-04-12"
  }
}
```

When `first_studied` is `null`: single-topic session. Orchestrator sets it after the session.
When `first_studied` has a date: interleaved session. Orchestrator loads `related_topics` and pulls cards/quizzes from those topics too.

**How each mode behaves when interleaving is active:**

| Mode | Single-Topic Behavior | Interleaved Behavior |
|------|----------------------|---------------------|
| Flashcards (Kiosk) | Loads cards from `cards/[topic].json` + subtopics | Loads cards from `cards/[topic].json` + 2-3 `related_topics` card files. Shuffles all together. No more than 3 consecutive cards from same topic. |
| Quiz (Kiosk) | Loads quizzes from `quizzes/[topic].json` | Loads quizzes from `quizzes/[topic].json` + related topic quiz files. Mixes MC questions and practice problems across topics. |
| Derive-it (Kiosk) | Loads formulas + problems for one topic | Loads formulas + problems from related topics. Displays combined formula sheet. Problems alternate between topics -- forces you to pick the RIGHT formula, not just apply the only one available. |
| Socratic dialogue | Deep dive on one concept at a time | Jumps between related concepts every 3-4 exchanges. "Good, you understand RC time constants. Now -- how does that compare to RL time constants? What's different about the energy storage?" |
| Teach-it-back | "Explain [topic] to me" | "Explain [topic A] to me, and while you're at it, tell me how it relates to [topic B]." Tests your ability to connect concepts. |
| Brain dump | "Tell me everything about [topic]" | Same -- brain dump is always single-topic since it's measuring YOUR recall, not testing discrimination. Interleaving starts after the dump. |
| Practice problems | Novel problems from one topic's formula set | Novel problems that mix formulas from multiple topics. You have to identify which approach applies before solving. |
| Diagram - Direction B (Kiosk) | Shows diagrams from one topic's `diagrams/` folder | Shows diagrams from primary + related topics. Mixes identification and analysis questions across different circuit/system types. Forces visual discrimination. |
| Diagram - Direction A/C (conversational) | Draw/reproduce one type of diagram | "Draw an RC filter" then "Now draw an RL filter from memory." Alternates between related diagram types to test visual recall across concepts. |

**For Kiosk modes:** interleaving is essentially free. The skill lists the related topics in the deck spec; the Kiosk loads the extra topic files and shuffles them. Zero extra tokens.

**For conversational modes (Socratic, teach-back):** interleaving costs the same tokens -- same number of turns, but the content spans multiple topics.

**Orchestrator prompt addition:**

```
## Interleaving Strategy

At session start, after topic selection:
1. Look up the topic in [course]/topics.json
2. Check the `first_studied` field
3. If null: this is the FIRST TIME studying this topic
   - Set session_state.interleave = false
   - Run all modes in single-topic mode
   - After session: set first_studied to today's date, increment times_studied
4. If not null: this is a REPEAT session
   - Set session_state.interleave = true
   - Read related_topics from topics.json
   - For Kiosk modes: put the primary topic + up to 3 related topics in
     the deck spec (interleave: true); the Kiosk mixes them
   - For conversational modes: instruct Claude to jump between related 
     concepts every 3-4 exchanges
   - After session: increment times_studied, update last_studied

The Kiosk applies these mixing rules for interleaved decks:
- Primary topic: 60% of cards/questions
- Related topics: 40% split among them
- Never more than 3 consecutive items from the same topic
- Label each item with its topic so the page can show 
  "Topic: RC Circuits" vs "Topic: RL Circuits" during review
```

**Steps:**

- [ ] Add `first_studied`, `times_studied`, and `last_studied` fields to topic registry format
- [ ] Add interleaving strategy logic to orchestrator prompt (check first_studied, set flag)
- [ ] Kiosk: build decks from multiple topic files when the spec says `interleave: true` (flashcards, quiz, derive-it with a combined formula sheet, diagrams)
- [ ] Add interleaving instructions to Socratic and teach-back mode sections in the skill prompt
- [ ] Test first-time study: "study sorting" when first_studied is null -> verify single-topic, verify first_studied gets set
- [ ] Test repeat study: "study sorting" again -> verify interleaving activates, verify cards from related topics appear
- [ ] Test Kiosk mixing: verify no more than 3 consecutive cards from same topic and roughly a 60/40 split
- [ ] Test Socratic interleaving: verify it jumps between related concepts

#### 2.2g -- Calibration Tracking

**What it does:** Before revealing if you're right, asks you to rate your confidence (1-5). Tracks the gap between confidence and accuracy over time.

- If consistently overconfident on a topic: increases review frequency even for "correct" answers
- If consistently underconfident: notes that you know more than you think
- Generates weekly calibration report

**Steps:**

- [ ] Add confidence prompt to all review modes
- [ ] Track in card JSON: `confidence_history: [{date, confidence, correct}]`
- [ ] Generate calibration score per topic

#### 2.2h -- Diagram Interaction Mode (Dual Coding -- Three Directions)

**What it does:** Three distinct modes of visual learning that test different cognitive skills. Uses both stripped (unlabeled) and labeled versions of diagrams from the `diagrams/` directory.

**Direction A -- Recall (you draw from memory):**
- System says: "Draw an RC low-pass filter from memory."
- Writes a pending request to `Meta/pending-requests.md`
- You draw on iPad/paper and upload it from the Kiosk's upload box (the request ID travels with the file, so no filename/timing guessing), or via Drive as a fallback
- System uses vision to evaluate your drawing against the original
- Points out errors: "your capacitor is in series but should be in parallel"
- **Delivery:** Conversational (Sonnet). Needs vision to evaluate your drawing.

**Direction B -- Recognition and Interpretation (system shows diagram, you answer):**
- Uses BOTH stripped and labeled versions of diagrams from `diagrams/[topic]/`

  **Using STRIPPED/unlabeled images (identification and recall questions):**
  - "Identify this type of circuit"
  - "Label all components in this diagram"
  - "Explain what this circuit/system does"
  - "What are the input and output signals?"
  - "Identify the feedback loop in this system"
  - "What is the function of each stage in this block diagram?"
  - After answering, the labeled original is revealed as the answer
  - **Delivery:** Kiosk `/s/{id}/diagrams`. Shows stripped image, takes text input or MC choices, reveals labeled original. Zero tokens per question.

  **Using LABELED/original images (higher-order analysis questions):**
  - "What does the component labeled R1 do in this circuit?"
  - "If C1 were doubled, how would the output change?"
  - "What kind of component is R2?"
  - "What kind of circuit/system is this?"
  - "Trace the signal path from input to output and explain each stage"
  - "What would happen if Q2 failed open?"
  - "Calculate the gain/frequency/time constant using the labeled values"
  - "Redesign this circuit to achieve [different specification]"
  - **Delivery:** Kiosk for MC and short-answer with known answers. Conversational (Sonnet) for open-ended analysis that needs Claude to evaluate your reasoning.

**Direction C -- Reproduction (study then reproduce from memory):**
- The Kiosk shows you a diagram (labeled original) for a timed display (30-60 seconds)
- The page hides the diagram after the timer and shows an upload box: "Now draw it from memory."
- You draw on iPad/paper and upload from that box (saved to `Meta/uploads/`, event to `Meta/events/ingestion/` tagged with the request ID)
- System compares your reproduction to the original via vision
- Points out what you got right, what you missed, what you got wrong
- **Delivery:** Hybrid. Kiosk for the timed display and upload. Conversational (Sonnet + vision) for evaluating your reproduction against the original.

**The Kiosk page renders differently based on `question_type` field in card JSON:**

| question_type | Image Shown | Answer Behavior |
|--------------|-------------|-----------------|
| `identification` | Stripped (labels removed) | Flips to labeled original as answer |
| `analysis` | Labeled original | Text answer revealed |
| `reproduction` | Labeled original (timed, then hidden) | User draws and uploads for vision comparison |

**Steps:**

- [ ] Build the Kiosk's `/s/{id}/diagrams` page: loads diagram images from `diagrams/[topic]/` alongside image-tagged cards from `cards/[topic].json`
- [ ] The page handles `identification` and `analysis` question types differently (stripped vs labeled image)
- [ ] Add Direction A recall mode (conversational, existing design from before)
- [ ] Add Direction C reproduction mode: timed Kiosk display + upload box + vision comparison
- [ ] Integrate with the pending request system from ingestion (1.1) for Directions A and C. Kiosk uploads carry the request ID; Drive uploads fall back to timing + vision matching.
- [ ] Test Direction B on the Kiosk: load a topic with diagram images -> verify stripped images show for identification questions, labeled for analysis
- [ ] Test Direction C: timed display -> draw -> upload -> verify vision comparison catches errors
- [ ] Test full loop for Direction A: skill requests diagram -> you draw on iPad -> upload from the Kiosk -> skill evaluates via vision (repeat once via Drive to test the fallback)

#### 2.2i -- "Derive It, Don't Memorize It" Mode

**What it does:** Engineering-specific mode. Gives you a formula sheet and a problem, then asks you to solve it. Tests APPLICATION, not recall -- mirrors exam conditions where you have the formulas but need to know when and how to use them.

**Delivery: the Kiosk** (`/s/{id}/derive`, same flow as flashcards and quizzes). The page displays the formula sheet for the topic alongside practice problems with randomized values, and auto-checks your numerical answers against the solution formula. Zero tokens per problem during review.

**Formula sheets are per-topic, stored alongside cards and quizzes:**

```
03-Resources/study/EE225/
  formulas/
    rc-transient-analysis.json
    mosfet-operating-regions.json
    kirchhoffs-laws.json
    thevenin-norton.json
```

**Formula sheet format -- `formulas/[topic-slug].json`:**

```json
{
  "topic": "rc-transient-analysis",
  "course": "EE225",
  "formula_sheet": [
    {
      "name": "Time constant",
      "formula": "tau = R * C",
      "variables": {"R": "resistance (ohms)", "C": "capacitance (farads)", "tau": "time constant (seconds)"},
      "display_latex": "\\tau = RC"
    },
    {
      "name": "Capacitor charging voltage",
      "formula": "Vc = V * (1 - exp(-t / tau))",
      "variables": {"V": "source voltage", "t": "time", "tau": "time constant"},
      "display_latex": "V_C(t) = V_s(1 - e^{-t/\\tau})"
    },
    {
      "name": "Capacitor discharging voltage",
      "formula": "Vc = V0 * exp(-t / tau)",
      "variables": {"V0": "initial voltage", "t": "time", "tau": "time constant"},
      "display_latex": "V_C(t) = V_0 e^{-t/\\tau}"
    }
  ]
}
```

**How it connects to the topic taxonomy:**

- Formula sheets are auto-generated by the same ingestion subagent that creates cards and quizzes (step 10 in 1.1). When the subagent processes a note with formulas, it extracts them and files them into the correct per-topic formula file using the Topic Matching Protocol.
- The generation subagent prompt includes: "When a note contains formulas, equations, or derivations, extract them as formula sheet entries with both an evaluable formula (plain math grammar: + - * / ^, exp, log, sqrt, sin, cos, pi -- what the Kiosk's safe evaluator understands) and LaTeX display format. File to the matching topic's formula JSON."
- Practice problems in `quizzes/[topic].json` reference formulas from `formulas/[topic].json` -- the Kiosk loads both and displays the formula sheet alongside the problem.
- If a formula applies to multiple topics (e.g., Ohm's law appears in many circuit topics), it goes in each relevant topic's formula file. Duplication is fine here -- each topic's formula sheet should be self-contained for the Kiosk page.

**Session flow for derive-it mode:**

1. Orchestrator selects derive-it mode for a computational topic
2. Loads `formulas/[topic].json` and `quizzes/[topic].json` (filtering for `type: practice_problem`)
3. Writes a deck spec and sends the Kiosk link; the page displays:
   - Formula sheet panel (always visible, shows all formulas for the topic)
   - Problem panel (shows one problem at a time with randomized values)
   - Answer input field
   - "Check" button that auto-evaluates using `solution_formula`
   - Step-by-step solution reveal after checking
4. All interaction happens in the Kiosk. Zero tokens per problem.
5. The Kiosk writes a session summary to `Meta/events/study-skill/`; the orchestrator reads it when you say "done".

**Steps:**

- [ ] Add formula sheet JSON format to the generation subagent prompt
- [ ] Update ingestion subagent to extract formulas from notes and file them per-topic
- [ ] Build the Kiosk's `/s/{id}/derive` page: formula sheet + practice problems side by side
- [ ] The page loads from both `formulas/[topic].json` and `quizzes/[topic].json`
- [ ] Render LaTeX with KaTeX (vendored into `personal/kiosk/static/` so it works without internet)
- [ ] Test: drop a note with formulas -> confirm formula sheet JSON created in correct topic folder
- [ ] Test: run derive-it mode -> verify formula sheet displays alongside problems with randomized values
- [ ] Test: verify auto-checking works against solution formulas

#### 2.2j -- [REPLACED BY THE KIOSK (0.13)]

The Anki-style review interface is now the Kiosk's `/review` and `/s/{id}/flashcards` pages, with FSRS running server-side and review state written to `review-state/`. The earlier artifact plan (React artifact + `window.storage`) is dropped: artifact storage can't write back to the vault, and every artifact cost tokens to generate.

#### 2.2k -- Study Session Orchestrator (Session Wrapper)

**What it does:** Wraps all study modes (2.2a-2.2j) into a coherent, time-bounded study session. This is the entry point for all studying -- you never invoke individual modes directly.

**Trigger:** "I want to study [topic]" or "study time" or "review for [course]" or Distributor assigns a study task

**Architecture: Single skill, NOT subagents per mode.**

The study skill is ONE .md prompt file containing all modes as sections. The orchestrator logic is at the top, and each mode is a set of behavioral instructions the same Claude instance follows. Think of it as one agent wearing different hats. This avoids cold-start overhead of spinning up separate subagents per mode.

Prompt structure:

```markdown
# Study Skill

## Orchestrator (always runs first)
[session setup, brain dump, mode selection logic, state loading/saving]

## Mode: Flashcard Review
When in flashcard mode:
- Look up the session topic in [course]/topics.json to find the topic slug
  (also check aliases and subtopics)
- If the topic has subtopics, set include_subtopics: true (the Kiosk
  picks due cards itself)
- Check the Kiosk is up (curl -s http://localhost:8484/health-check)
- Write the deck spec to Meta/study-session-state.json (kiosk block:
  mode, course, topics, interleave, related_topics, filter: due, limit)
- Send the link: https://<desktop>.<tailnet>.ts.net/s/<session_id>/flashcards
- Wait for the user to say "done"; then read the Kiosk's summary from
  Meta/events/study-skill/<session_id>-flashcards.json
- Record results in session state; move the event to processed/
- Do NOT generate new cards and do NOT read card files yourself --
  the Kiosk does all of that

## Mode: Socratic Dialogue
When in Socratic mode:
- Query NotebookLM for conceptual questions using --notebook-id from mapping file
- Ask probing questions, never give direct answers
- Follow up with "why?" and "how?" (elaborative interrogation)
- Max 8 exchanges per concept, then move to next concept
- If student is stuck after 3 hints, reveal and move on

## Mode: Quiz / Practice Problems
When in quiz mode:
- Look up the session topic in [course]/topics.json (same as flashcards)
- Write a deck spec with mode: quiz and send the /s/<session_id>/quiz link
- The Kiosk loads [course]/quizzes/[topic-slug].json (+ subtopics),
  randomizes practice-problem values from variable_ranges, and checks
  answers against solution_formula
- Wait for "done", then read the Kiosk summary
- Short-answer questions (if selected): run conversationally in Sonnet, NOT in the Kiosk

## Mode: Derive It (Formula Application)
When in derive-it mode:
- Look up the session topic in [course]/topics.json
- Write a deck spec with mode: derive and send the /s/<session_id>/derive link
- The Kiosk loads [course]/formulas/[topic-slug].json and the
  practice_problem items from [course]/quizzes/[topic-slug].json
  (+ subtopics), and displays:
  - Formula sheet panel (always visible) with LaTeX-rendered equations
  - Problem panel with randomized values from variable_ranges
  - Answer input + auto-check against solution_formula
  - Step-by-step solution reveal after check
- This mode is specifically for computational/engineering topics
  where the skill being tested is knowing WHEN and HOW to apply
  formulas, not memorizing them

## Mode: Teach-It-Back
[...]

## Mode: Diagram Interaction (Three Directions)
When in diagram mode:
- Look up the session topic in [course]/topics.json
- Check if diagrams exist in [course]/diagrams/[topic-slug]/
- If no diagrams exist for this topic: skip diagram mode, announce why
- Select direction based on orchestrator's mode plan:
  
  Direction B (Kiosk -- identification + analysis):
  - Write a deck spec with mode: diagrams, direction: B
  - The Kiosk loads diagram images from [course]/diagrams/[topic-slug]/
    and image-tagged cards (question_type: identification or analysis),
    plus related-topic folders if interleaving is active
  - Stripped images for identification, labeled for analysis
  
  Direction A (conversational -- recall):
  - Ask user to draw a specific diagram from memory
  - Write pending request to Meta/pending-requests.md; send the Kiosk
    upload link (/s/<session_id>/diagrams?upload=<request_id>)
  - Wait for the drawing (Kiosk upload, or Drive as fallback)
  - Evaluate via vision against original in diagrams/ folder
  
  Direction C (hybrid -- reproduction):
  - Write a deck spec with mode: diagrams, direction: C; send the link
  - The Kiosk shows the labeled diagram for 30-60 sec, hides it, and
    shows an upload box ("draw from memory")
  - User uploads from that box (request ID attached)
  - Evaluate reproduction via vision against original

## Session End Protocol
- Run self-assessment
- Save session state to Meta/study-session-state.json
- Log session to Meta/study-sessions.json
- Check for periodic study recommendations (2.2l)
- If weak areas identified: spawn subagent to generate remediation cards (saves to JSON for next session)
```

**Model per mode: a Sonnet session, a forked Haiku helper, and the Kiosk.**

The study session runs on the vault's default model, Sonnet 5.5 (0.12). A skill can't reliably switch the model of a live conversation, and it can't run built-in commands like `/model` or `/compact` itself (0.12). So instead of hopping between models, the cheap bookkeeping goes to a small forked helper skill, `/study-log` (`context: fork`, `model: haiku`, `effort: low`). It writes the session log, updates `topics.json` tracking and files the self-assessment results. The Kiosk modes cost almost nothing whatever model the session is on.

**Mode delivery matrix:**

| Mode | Delivery | Model | Why |
|------|----------|-------|-----|
| Session planning | Conversational | Sonnet (short) | A few lines of logic; not worth a model switch |
| Brain dump evaluation | Conversational | Sonnet | Needs to evaluate your knowledge against notes |
| Flashcard review | **Kiosk** | N/A (local web app) | Zero tokens per card; ~150 to send the link |
| Multiple-choice quiz | **Kiosk** | N/A (local web app) | Zero tokens per question |
| Formula practice / derive-it (2.2i) | **Kiosk** | N/A (local web app) | Per-topic formula sheet + randomized practice problems, auto-checked with a safe evaluator. Formula sheet panel always visible alongside problems. |
| Short-answer evaluation | Conversational | Sonnet | Needs to evaluate free-form responses |
| Socratic dialogue | Conversational | Sonnet | Inherently conversational, needs reasoning |
| Teach-it-back | Conversational | Sonnet | Needs to critique your explanation |
| Diagram - Direction B identification | **Kiosk** | N/A (local web app) | Shows stripped image, takes answer, reveals labeled original. Zero tokens. |
| Diagram - Direction B analysis (MC/short) | **Kiosk** | N/A (local web app) | Shows labeled image alongside questions. Auto-checkable answers. |
| Diagram - Direction B analysis (open-ended) | Conversational | Sonnet | Needs Claude to evaluate free-form analysis |
| Diagram - Direction A recall (draw from memory) | Conversational | Sonnet | Needs vision to evaluate uploaded drawing |
| Diagram - Direction C reproduction | Hybrid (Kiosk + conversational) | Sonnet | Timed display + upload box in the Kiosk, then vision comparison of the uploaded drawing |
| Self-assessment | Conversational, then `/study-log` | Sonnet asks, Haiku records | Two or three short questions; the forked helper does the writing |

**Mode transition protocol (add to skill prompt):**

```
## Mode Transition Protocol
Before starting each mode:
1. Save progress to Meta/study-session-state.json (so nothing is lost
   if the conversation gets compacted)
2. After a conversational mode (brain dump, Socratic, teach-back), end
   your message with: "Type /compact, then say next." (You can't run
   /compact yourself.) Skip this after Kiosk modes -- they barely add
   to the conversation.
3. Announce: "Switching to [mode]."

For Kiosk modes:
- Write the deck spec to the kiosk block of Meta/study-session-state.json
- Tell the user: "Here are your flashcards: <link>. Tell me when you're done."
- When the user says done, read Meta/events/study-skill/<session_id>-<mode>.json
  (if it's missing, the user hasn't pressed Finish -- ask them to)
- Record results in session state
- Proceed to next mode
```

**Session flow (Sonnet session + Kiosk + forked helper):**

```
[Start session -- vault default: Sonnet 5.5]
  1. Plan session, select modes (a few lines)
  2. Brain dump evaluation (needs reasoning)
  -> you type /compact
  3. Write flashcard deck spec + send Kiosk link (~150 tokens)
     User reviews in the Kiosk (0 tokens)
     User says done, skill reads the summary (~300 tokens)
  4. Socratic dialogue (15 min, conversational)
  -> you type /compact
  5. Write quiz deck spec + send Kiosk link (~150 tokens)
     User answers in the Kiosk (0 tokens)
     User says done, skill reads the summary (~300 tokens)
  6. Self-assessment: two or three questions
  7. /study-log (forked, Haiku): session log, topics.json, state
[End session]
```

**Phone and iPad:** conversational modes (brain dump, Socratic, teach-back) happen in the Claude app over Remote Control. Kiosk modes open in the phone's browser over Tailscale, on Wi-Fi or cellular. On iPad, put the two side by side in split view. The Kiosk doesn't depend on Remote Control at all, so `/review` works even if the Remote Control session is down.

**Session state file (persists between segments and across sessions):**

```json
{
  "session_id": "study_20260329_1400",
  "topic": "RC circuit transient analysis",
  "course": "EE225",
  "time_budget_min": 60,
  "energy_level": 3,
  "interleave": true,
  "interleave_topics": ["rl-transient-analysis", "thevenin-norton"],
  "brain_dump_evaluation": {
    "gaps_identified": ["time constant derivation", "initial conditions for RL circuits"],
    "strong_areas": ["Kirchhoff's laws", "series/parallel identification"],
    "dump_quality_score": 0.6
  },
  "modes_planned": ["flashcards", "socratic", "practice_problems"],
  "modes_completed": ["flashcards"],
  "mode_results": {
    "flashcards": {
      "cards_reviewed": 15,
      "cards_correct": 11,
      "cards_flagged_weak": ["ee225_042", "ee225_051", "ee225_063"],
      "time_spent_min": 14,
      "planned_min": 15
    }
  },
  "segment": 2,
  "fuzzy_areas": [],
  "self_assessment_complete": false,
  "timestamp": "2026-03-29T14:18:00"
}
```

This file is loaded at the start of each mode (after /compact) so the skill remembers what happened even though the conversation history was compressed. It's also used if a session is interrupted -- you can resume later by loading the state file.

**Session flow (detailed):**

1. **Topic selection:** If you specify a topic, use it. If not, ask: "What topic(s) will this session cover?" Can also accept multiple topics for interleaving.
2. **Context check:** Read your available time and energy level (from Distributor state, or ask if not already set).
3. **Brain dump (2 minutes):** "Tell me everything you remember about [topic] right now. Don't look anything up -- just dump what's in your head." This serves double duty:
   - Retrieval practice for you
   - Real-time assessment for the system -- if your brain dump is shaky but your flashcard scores say you're solid, the system distrusts the card scores and increases review intensity
   - The system evaluates your brain dump against actual course content and notes where gaps are
4. **Interleaving check (automatic, no user input):** Read `first_studied` for this topic from `topics.json`.
   - If null: single-topic session. Set `session_state.interleave = false`.
   - If not null: interleaved session. Set `session_state.interleave = true`. Load `related_topics` list. All Kiosk modes will pull from related topics too (via the deck spec). Announce: "You've studied this before, so I'll mix in related topics to strengthen discrimination."
5. **Mode selection:** Pick 2-4 modes for this session based on:
   - **Time available:** 15 min = 1 mode (flashcards or quiz). 30 min = 2 modes. 45-60 min = 3-4 modes.
   - **Energy level:** Low energy (1-2) = flashcard review + quiz. Medium (3) = add Socratic or teach-back. High (4-5) = add practice problems, derivation, or diagram work.
   - **Topic type matching:** Use the mode that fits the content:
     - Terminology/definitions -> flashcards (2.2a)
     - Computational/math -> practice problems (2.2b) + derive-it mode (2.2i)
     - Conceptual understanding -> Socratic dialogue (2.2c) + teach-back (2.2d)
     - Visual/spatial concepts -> diagram interaction (2.2h)
     - Pre-exam review -> teach-back (2.2d) + a comprehensive Kiosk review deck
     - New material -> generation effect (2.2e) + Socratic (2.2c)
   - **Interleaving is NOT a mode choice** -- it activates automatically based on whether this topic has been studied before (see 2.2f). If `first_studied` exists in `topics.json`, ALL Kiosk modes in this session load from related topics too.
   - **Weak areas from calibration (2.2g):** Prioritize modes that target concepts where confidence-accuracy gap is large
6. **Execute modes in sequence:** Run each selected mode for its allotted time. After each conversational mode, save state and ask the user to type /compact before the next one. Announce: "Switching to [next mode]..."
7. **End-of-session self-assessment:** "We covered [topics]. What still feels fuzzy? Anything you want to come back to?" The system:
   - Records fuzzy areas in the card/topic metadata for future session prioritization
   - Marks topics you flagged as fuzzy in `topics.json` (`fuzzy_until`: three days out); the Kiosk treats their cards as due until then, so they come back sooner
   - Generates a brief session summary note in `07-Daily/` with: topics covered, modes used, time spent, self-assessment results
   - **Post-session remediation generation:** If the session identified weak areas (brain dump gaps, repeated wrong answers, fuzzy self-assessment topics), the orchestrator spawns a subagent AFTER the session ends to generate 5-10 targeted remediation cards and 2-3 focused practice problems for those specific weaknesses. These are saved to the appropriate per-topic card/quiz JSON files using the Topic Matching Protocol (not dumped into a generic file) and will appear in the next study session automatically. This costs ~3,000-5,000 tokens but runs after you've already left -- you don't wait for it.
   - **Update topic study tracking:** In `topics.json`, set `first_studied` to today if null, increment `times_studied`, update `last_studied` to today. This data drives the interleaving decision (2.2f) for the next session on this topic.

**Time tracking:** Track how long each mode actually takes per session. After a few weeks, the orchestrator uses this data to more accurately plan future sessions. If practice problems consistently take 50% longer than estimated, adjust.

**Token cost estimates (Sonnet session + pre-generated cards + Kiosk):**

| Session Length | Modes Used | Est. Tokens | % of a Pro window (conservative ~44k floor, see specs) |
|---------------|-----------|-------------|-----------------|
| 15 min | Kiosk `/review` only (open it yourself, no Claude) | 0 | 0% |
| 30 min | Brain dump (Sonnet) + Kiosk flashcards + self-assessment + `/study-log` (Haiku) | ~5,000 | ~11% |
| 45 min | Brain dump + Kiosk flashcards + Socratic (Sonnet) + self-assessment | ~20,000 | ~45% |
| 1 hour | Brain dump + Kiosk flashcards + Socratic + Kiosk quiz + self-assessment | ~22,000 | ~50% |
| 2 hours | All modes including conversational teach-back + diagram | ~50,000 | ~115% (needs 2 windows) |
| Post-session remediation (background) | Subagent generates targeted cards | ~3,000-5,000 | Runs after session, doesn't block you |

Each Kiosk mode costs ~150 tokens to launch (write the deck spec, send the link) plus ~300 to read the summary JSON when you come back. Everything you do on the page costs nothing.

Note: these estimates assume cards and quizzes are pre-generated at ingestion time. If the orchestrator needs to generate new material during the session (rare -- only for topics with no existing cards), add ~5,000 tokens.

**Steps:**

- [ ] Write the study skill as a SINGLE .md prompt file with orchestrator at top and all modes as sections
- [ ] Have the skill save state and ask you to type /compact after each conversational mode (it can't run it itself)
- [ ] Write the forked `/study-log` helper (`context: fork`, `model: haiku`, `effort: low`)
- [ ] Define the session state JSON format and implement state saving/loading
- [ ] Implement topic-to-mode mapping table (which modes work best for which content types)
- [ ] Implement the brain dump evaluation (compare dump against note frontmatter summaries for the topic)
- [ ] Implement end-of-session self-assessment and feedback storage
- [ ] Add time tracking: log `{session_date, topic, modes_used, planned_minutes, actual_minutes}` to `Meta/study-sessions.json`
- [ ] Add Socratic depth cap to prompt: "Max 8 exchanges per concept."
- [ ] Test 30-min session: "study circuit analysis for 30 minutes at energy 3" -> verify brain dump -> (you type /compact) -> flashcards -> self-assessment -> /study-log runs on Haiku
- [ ] Test that state survives a /compact mid-session (the next mode picks up from `study-session-state.json`)
- [ ] Test session state save/load: interrupt a session, resume later -> verify continuity
- [ ] Test that fuzzy-area flagging actually affects future session priorities
- [ ] Compare token cost of session with /compact vs. without (run /cost at end) to verify savings

**Iteration:**

- [ ] After 2+ weeks of data: use time-per-mode history to improve session planning accuracy
- [ ] Add "surprise review" mode -- occasionally pull in a card/question from a topic you haven't studied recently to test long-term retention
- [ ] Add session difficulty auto-adjustment -- if you're acing everything in a session, escalate to harder modes. If you're struggling, drop back to reinforcement modes.
- [ ] For standalone flashcard-only sessions: create a separate lightweight invocation path that runs in Haiku (no orchestrator overhead, no brain dump, just card review + state save)

#### 2.2l -- Periodic Study Recommendations (Distributor Integration)

**What it does:** The study skill feeds back into the Distributor to proactively recommend study sessions. This is spaced repetition operating at the COURSE level, not just the card level.

**Triggers for generating study tasks:**

- No review session for a course in 7+ days -> generate "Review [course]" task (medium priority)
- Exam/quiz approaching within 7 days -> generate "Study for [exam]" task (high priority, boosted daily as exam approaches)
- Cards overdue for review in a course -> generate "Review [course] flashcards" task (low-medium priority)
- Calibration tracking shows declining accuracy on a topic -> generate "Reinforce [topic]" task (medium priority)
- New material ingested but not yet studied -> generate "Process new [course] material" task (medium priority)

**Steps:**

- [ ] Add a check to the study skill that runs after each session: scan all courses for overdue reviews, upcoming exams (from calendar), and accuracy trends
- [ ] When a study task is needed, write a JSON event to `Meta/events/distributor/` with the recommended task, priority, and reason
- [ ] Distributor treats these like any other task -- they appear when you ask "what should I do?" and are filtered by time/energy like everything else
- [ ] Test: don't study a course for 8 days -> verify a review task appears in Distributor output

---

### 2.3 -- Lecture Audio Transcription Pipeline

**Type:** Local speech-to-text script (Granite Speech 4.1) + the upstream `/transcribe` skill (Lecture Notes mode). No edits to upstream files.
**Existing resource:** Upstream `/transcribe` already has a Lecture Notes mode: key concepts, a definitions table, points the lecturer stressed ("would be on the exam"), questions asked, and links to prior lectures. It can't turn audio into text itself -- it expects a transcript (it suggests Whisper; we use a newer model, below).
**Model:** Sonnet for structuring the transcript; IBM Granite Speech 4.1 2B (local) for audio-to-text
**Token tip:** Speech-to-text runs locally (free, on the 4070 Ti). Claude only sees the text.

**Why Granite Speech instead of Whisper:** released April 2026 under Apache 2.0, it has a mean English word error rate of 5.33% on the Open ASR Leaderboard, among the best open models, and runs far faster than Whisper large-v3. It also takes a keyword list in its prompt ("Keywords: Thevenin, MOSFET, ..."), so course vocabulary comes out spelled right. That matters in engineering lectures, where the jargon is the content. faster-whisper (`large-v3-turbo`) stays as the fallback: easier to install and more languages.
**Required premade skills:** michalparkola/tapestry-skills "Article Extractor" and "YouTube Transcript" for supplementary content

**Pipeline:**

1. Audio file lands in `drive-inbox/` (or you drop it in directly)
2. The 3 AM batch (or "process my uploads") runs `personal/scripts/transcribe-local.sh`: ffmpeg splits the audio on silences into ~5-minute chunks, Granite Speech transcribes each with the course's keyword list (top terms from that course's `topics.json`), and the chunks are joined into a `.txt` transcript next to the audio (zero tokens)
3. The ingestion agent runs `/transcribe` on the transcript, telling it: mode = Lecture Notes, source = local transcript, course = <from calendar or filename>. The note lands in `{{inbox}}` with `type: lecture-notes`.
4. Same batch, Step 2: the `study_generated` check finds the new lecture note and generates cards, quizzes and formulas (Topic Matching Protocol); the note is also uploaded to NotebookLM
5. Step 3 (`/inbox-triage`) files the note into the course folder

**Steps:**

- [ ] Install in the venv: `~/.venvs/brain/bin/pip install "transformers>=4.52.1" torchaudio` and load `ibm-granite/granite-speech-4.1-2b`. It reaches the 4070 Ti through the Windows NVIDIA driver; confirm GPU use with `nvidia-smi` while it runs.
- [ ] Fallback if Granite gives you install trouble: `pip install faster-whisper` with the `large-v3-turbo` model, passing the keyword list as `initial_prompt`
- [ ] Write `personal/scripts/transcribe-local.sh <audio>` -> writes `<audio>.txt` (add it to the allowlist in 0.12)
- [ ] In the ingestion agent prompt: "For audio files, run transcribe-local.sh, then invoke /transcribe on the transcript in Lecture Notes mode, passing the course and 'local transcript' as the source format so it skips its intake questions."
- [ ] Test with: record a short lecture on phone -> export audio to Drive -> "process my uploads" -> confirm a lecture note appears, then cards appear in the course's topic files

**Iteration:**

- [ ] Add YouTube Transcript skill -- professor posts supplementary videos, extract transcripts automatically (it uses yt-dlp captions first, and only falls back to local speech-to-text when there are none)
- [ ] Add Article Extractor -- pull full text from links in lecture slides/syllabi

---

### 2.4 -- Grade Tracker

**Type:** Custom skill -- fork `skills/<name>/SKILL.md`, registered in the dispatcher block (0.12)
**Existing resource:** None -- custom build
**Model:** Haiku (simple math)
**Token tip:** Store all grade data in a single JSON file per course. Agent reads only the file it needs. Calculations are trivial -- Haiku handles this fine.

**Core behavior:**

- Maintains a JSON file per course with grading breakdown and your scores:

```json
{
  "course": "EE225",
  "grading": {
    "homework": {"weight": 0.20, "scores": [95, 88, 92]},
    "labs": {"weight": 0.25, "scores": [90]},
    "midterm": {"weight": 0.25, "scores": []},
    "final": {"weight": 0.30, "scores": []}
  },
  "current_weighted": 91.2,
  "projections": {
    "A": "Need 87+ on remaining assessments",
    "A-": "Need 80+ on remaining assessments"
  }
}
```

- When you report a grade: updates the file, recalculates projections, alerts Distributor if you're borderline

**Steps:**

- [ ] Write the skill prompt
- [ ] Create grade JSON template per course
- [ ] Manually enter grading weights from each syllabus
- [ ] Test: "I got an 88 on the EE225 homework" -> verify update and projection
- [ ] Connect to Distributor: skill writes a JSON event to `Meta/events/distributor/` when a course is borderline -> Distributor reads this and boosts priority

**Iteration:**

- [ ] Auto-detect grades from Canvas if API/scraper is working
- [ ] Generate study recommendations based on which assessments are upcoming and how much they're worth

---

### 2.5 -- Weekly Synthesis

**Type:** Custom skill `/weekly-synthesis` (fork `skills/weekly-synthesis/SKILL.md`) fired by Friday cron. It may end with `### Suggested next agent: connector` so upstream's Connector adds the wikilinks it found; neither Seeker nor Connector is edited.
**Existing resource:** Upstream Connector (links notes when chained); note summaries in frontmatter
**Model:** Sonnet (needs to synthesize across multiple notes -- reasoning required)
**Token tip:** Don't read all notes from the week. Read only frontmatter summaries. For cross-course connections, grep for shared keywords across courses, then load only matching sections.
**Required premade skills:** None

**Core behavior:**

- Runs Friday at 5 PM (cron, not /loop)
- Reads frontmatter summaries of all notes created this week
- Identifies core concepts covered per course
- Finds cross-course connections ("The Fourier transform in EE225 and the spectral decomposition in linear algebra are the same underlying idea")
- Generates a single "Week N Synthesis" note in `07-Daily/`
- Flags any courses where no notes were taken (missed class? or just didn't capture?)

**Steps:**

- [ ] Write the `/weekly-synthesis` skill (triggers: "weekly synthesis", "what did I learn this week" -- NOT "weekly review", which upstream routes to `/vault-audit`)
- [ ] Set up Friday 5 PM cron trigger
- [ ] Test: after a week of notes, trigger manually -> verify cross-course connections are meaningful
- [ ] Review output for a few weeks and tune -- is it finding useful connections or just noise?

---

### 2.6 -- Research Radar

**Type:** Scheduled skill using Deep Research
**Existing resource:** deep-research@sanjay3290/ai-skills
**Model:** Whatever the Deep Research skill uses (likely Sonnet + web search)
**Token tip:** Run weekly, not daily. Cache results. Store as a running digest file that gets appended to, not regenerated.
**Required premade skills:** deep-research@sanjay3290/ai-skills

**Core behavior:**

- Runs Sunday evening (cron)
- Searches for new papers, preprints, and lab announcements in your areas of interest:
  - Superconducting qubits
  - Quantum error correction hardware
  - Cryo-CMOS
  - Micro/nano fabrication techniques
  - Any specific topics you add
- Appends to a rolling `03-Resources/research-radar/digest.md` file
- Flags papers that are especially relevant to your grad school targets
- Over time builds a curated reading list for grad school prep

**Steps:**

- [ ] Install deep-research skill
- [ ] Define search queries / topic areas in a config file
- [ ] Set up Sunday evening cron trigger
- [ ] Test: trigger manually -> verify results are relevant and not noise
- [ ] Review and tune search queries after a few weeks

**Iteration:**

- [ ] Add target grad programs and professors to the search -- flag when their labs publish something
- [ ] Add auto-summary of papers using the "Learn This" skill from tapestry-skills
- [ ] Connect to a grad school tracking note that maintains your evolving statement of purpose themes

---

### 2.7 -- Exam Countdown Mode

**Type:** Orchestration mode that activates across Distributor, Study Skill, and Morning Briefing
**Existing resource:** None -- custom integration across existing components
**Model:** Haiku for countdown tracking, Sonnet for review plan generation
**Token tip:** The countdown tracking is just a date comparison (trivial). The review plan generation runs once when the countdown activates, not daily.

**What it does:** When an exam is 7 days away (detected via calendar), the system enters a special coordinated mode across multiple components:

**Distributor changes:**
- Heavily prioritizes study tasks for the exam course
- Automatically suggests study sessions when you have free time
- Deprioritizes non-urgent tasks from other courses
- If energy is low, still suggests light review (Kiosk `/review`, 0 tokens) rather than skipping study entirely

**Study Skill changes:**
- Generates a comprehensive 7-day review plan covering all topics for the exam
- Distributes topics across days with spaced review (topics studied on day 1 get reviewed on day 4 and day 7)
- Increases interleaving intensity -- every session interleaves exam topics
- Raises the FSRS target recall for the exam course from 90% to 95% for the countdown (0.13), so the Kiosk schedules those cards more often; it drops back after the exam
- Focuses on weak areas identified by calibration tracking (2.2g) and past session performance
- Day 7 (day before exam): teach-it-back mode for the hardest topics + a timed practice exam in the Kiosk (`/s/{id}/quiz` with `"filter": "all"`, every exam topic, a timer, and no hints)

**Morning Briefing changes:**
- Shows exam countdown: "EE225 Midterm in 3 days"
- Shows today's review plan from the 7-day schedule
- Shows weak areas that still need work

**Dynamic Scheduler changes (when 3.10 is built):**
- Auto-blocks study time for the exam course in the daily schedule
- Increasing study time as the exam approaches (30 min/day at T-7, 2+ hours at T-1)

**Activation:** Automatic when a calendar event matching exam keywords ("exam," "midterm," "final," "quiz," "test") is detected within 7 days. `calendar-sync.sh` flags it (0 tokens) by writing an `exam-detected` event to `Meta/events/scheduler/`, which starts `/exam-mode`. Can also be manually activated: "exam mode for EE225 midterm on April 15."

**Deactivation:** Automatic after the exam date passes. System returns to normal mode.

**Steps:**

- [ ] Add exam detection to `calendar-sync.sh`: any event within 7 days matching exam keywords writes an `exam-detected` event (once per exam; remember the event ID)
- [ ] Write the review plan generator: reads all topics for the course from `topics.json`, prioritizes by weak areas, distributes across 7 days with spaced review
- [ ] Modify Distributor prompt: "When exam countdown is active, boost all tasks for [course] to highest priority"
- [ ] Modify Morning Briefing: add countdown display and today's review plan
- [ ] Store exam countdown state in `Meta/exam-countdown.json`:

```json
{
  "active_countdowns": [
    {
      "course": "EE225",
      "exam_name": "Midterm",
      "exam_date": "2026-04-15",
      "days_remaining": 4,
      "review_plan": {
        "day_1": ["mosfet-operating-regions", "kirchhoffs-laws"],
        "day_2": ["rc-transient-analysis", "thevenin-norton"],
        "day_3": ["review: mosfet", "op-amp-basics"],
        "day_4": ["review: rc-transient", "frequency-response"],
        "day_5": ["interleaved: all topics"],
        "day_6": ["weak-areas-focus", "practice-exam"],
        "day_7": ["teach-back: hardest topics", "light-review"]
      },
      "weak_areas": ["rc-transient-analysis", "frequency-response"],
      "activated": "2026-04-08"
    }
  ]
}
```

- [ ] Test: create a calendar event "EE225 Midterm" 5 days from now -> verify exam mode activates, review plan generates, Distributor prioritizes, morning briefing shows countdown

---

## PHASE 3 -- LIFE & PROJECT FEATURES

Build these once academic features are stable, or as needed.

---

### 3.1 -- Campaign Manager Skill (Multiple Campaigns, GM or Player)

**Type:** Custom skill -- fork `skills/campaign/SKILL.md`, registered in the dispatcher block (0.12)
**Existing resource:** None -- custom build
**Model:** Sonnet for GM modes (narrative reasoning, world simulation), inline on the session's default model. Player bookkeeping (recap filing, sheet edits, the refresher) goes to a forked helper, `/campaign-log` (`context: fork`, `model: haiku`), so it really runs on Haiku (0.12)
**Token tip:** Keep every campaign as small linked notes (one per NPC, faction, plot thread, quest), never one giant bible. The skill's first read is the registry -- every `campaign.json` at once, a few hundred tokens -- and after that it only loads files inside the one campaign it picked. Grep a recap for NPC names before loading their files.

**How it picks the campaign:**

Every campaign has a folder under `01-Projects/campaigns/` with a small `campaign.json`:

```json
{
  "name": "Cyberpunk RED",
  "slug": "cyberpunk-red",
  "role": "gm",
  "system": "Cyberpunk RED",
  "character": null,
  "aliases": ["cyberpunk", "cpr", "night city", "the red game"],
  "status": "active",
  "cadence": "weekly",
  "last_session": 0
}
```

A player campaign sets `"role": "player"` and names your PC in `"character"`. Since you'll usually mention the character rather than the campaign ("level up Orben"), the character name counts as an alias.

1. Read all registries in one call: `jq -c '{slug,name,role,character,aliases,status}' 01-Projects/campaigns/*/campaign.json`
2. Match the message against names, aliases and character names. Exactly one match: use it.
3. No name in the message: if only one campaign is `active`, use it. Otherwise ask one multiple-choice question listing the active campaigns. Never guess, because writing a recap into the wrong campaign is worse than asking.
4. `role` decides which modes exist. GM modes are refused in a player campaign ("that's a GM tool -- you're a player in Aurelion Drift"), and the reverse.

**Folder layouts:**

```
01-Projects/campaigns/
├── cyberpunk-red/                 (role: gm)
│   ├── campaign.json
│   ├── campaign-state.md          (current arc, session count, in-game date)
│   ├── npcs/                      (motivations, status, last seen, relationships)
│   ├── factions/                  (goals, current operations, relationship to PCs)
│   ├── plot-threads/              (status, next beat, NPCs involved)
│   ├── pcs/                       (the players' characters, from your side of the screen)
│   ├── sessions/                  (session-001.md ...)
│   ├── world-state.md             (what's happening independent of PCs)
│   ├── dormant-threads.md         (introduced but not yet active)
│   ├── maps/  inbox/
│
└── aurelion-drift/                (role: player)
    ├── campaign.json
    ├── character.md               (sheet: level, class, stats, features, inventory, resources)
    ├── goals.md                   (character goals, backstory hooks, personal arc)
    ├── party.md                   (other PCs: player, class, how your PC sees them)
    ├── npcs/                      (NPCs met: what you know, attitude to the party, last seen)
    ├── quests.md                  (active / done / rumors and leads)
    ├── level-up-plan.md           (next choices: features, feats, spells, build path)
    ├── lore.md                    (world facts learned -- player knowledge only)
    ├── sessions/                  (recaps from your character's point of view)
    ├── maps/  inbox/
```

**Player-knowledge rule:** a player campaign stores only what your character knows. Guesses about what the GM is planning go under a `theory:` label and never get stated as fact.

**Rules text:** the skill works from what's written in `character.md`. Paste each class feature's mechanics in once (a line or two each). It doesn't recite rulebook text or invent features from memory, which also keeps subclass details like the Swarmkeeper's accurate to your table's version.

**Sub-features (build in order):**

#### 3.1a -- GM: Post-Session Debrief

- You dump what happened (voice or text)
- Skill extracts: NPC interactions, player decisions, new information revealed, plot thread updates
- Updates relevant NPC files, plot thread files, and session log
- Flags continuity issues ("Kozlov was in Night City last session but left for the combat zone in session 4 -- intentional?")
- **Dormant thread detection:** checks all plot threads and NPCs. If anything hasn't been mentioned in 3+ sessions, flags it: "Jacob Cross hasn't appeared since session 5. Is this intentional or did he slip through the cracks?"

**Steps:**

- [ ] Write the skill prompt: campaign resolution (above), then a mode table keyed by `role`
- [ ] Create NPC, faction, plot thread and session templates (shared by all GM campaigns)
- [ ] Populate Cyberpunk RED with your existing data (4 PCs, the netrunner revenge arc, Project CRADLE, all NPCs)
- [ ] Test: write a fake session recap -> verify NPC updates and continuity checking

#### 3.1b -- GM: World Simulation

- You tell it NPC motivations and current actions
- Skill plays out ripple effects: NPC A's reaction -> affects NPC B -> affects faction C
- Concentric circles: immediate reaction -> secondary effects -> outer orbit NPCs
- Writes proposed world state changes to `world-state.md` for your review
- You approve/reject/modify before they become canon

**Steps:**

- [ ] Add world simulation mode to the skill
- [ ] Test: "Kozlov learns the players stole from his warehouse. What does he do, and how does that ripple?" -> verify multi-layer consequences

#### 3.1c -- GM: Session Prep

- Pulls open plot threads, NPC states, pending consequences, dormant threads
- Generates a prep document with:
  - Likely player actions based on last session's cliffhanger
  - NPC reactions prepared for those actions
  - Scenes you could run
  - Loose ends to weave in if there's a lull
  - World events happening independent of PCs

**Steps:**

- [ ] Add session prep mode
- [ ] Test: "prep for next session" -> verify it produces actionable GM notes

#### 3.1d -- Player: Session Recap

- You dump what happened ("Orben session: we got to the drift port, the harbormaster lied about the manifest...")
- Skill writes a recap in `sessions/` from your character's point of view, then updates `quests.md` (new, advanced, done), `npcs/` (new NPCs met, changed attitudes), loot and resources on `character.md`, and progress on `goals.md`
- **Loose-lead check:** flags quest hooks and rumors the party hasn't followed up on in 3+ sessions -- the player version of dormant threads
- Haiku; Sonnet only if the dump runs longer than a page

**Steps:**

- [ ] Add the player recap mode and the player templates (character, goals, party, NPC-met, quests)
- [ ] Test: fake recap -> verify quests move between sections and a new NPC file appears

#### 3.1e -- Player: Character Sheet and Level-Up

- "Update my character" edits `character.md` (HP max, new item, attuned item, resource changes)
- "Level up [character]" reads `level-up-plan.md`, applies the planned choices, updates the sheet, and asks only about choices the plan left open
- Keeps a one-line changelog at the bottom of `character.md`, so you can see when something changed

**Steps:**

- [ ] Add sheet-edit and level-up modes
- [ ] Test: level up with a plan -> sheet updates and the plan moves to the next level

#### 3.1f -- Player: Pre-Session Refresher

- "What do I need to remember for [campaign]?" returns the last recap's key points, active quests, your character's open goals, and the NPCs most likely to show up
- Haiku, ~1,500 tokens -- built for the five minutes before you log on
- The morning briefing (3.2) adds this automatically on days a campaign's session is on your calendar

**Steps:**

- [ ] Add the refresher mode and the morning-briefing hook
- [ ] Test: ask for a refresher -> it fits on one phone screen

#### Setup: register your campaigns

- [ ] Create one folder + `campaign.json` for each campaign. As you do, confirm `role` (GM or player), `system` and the PC name for each:
  - Cyberpunk RED -- GM
  - Aurelion Drift
  - Century of Darkness
  - Orben's campaign
  - Braindance's campaign
  - The swarmkeeper ranger's campaign
  (Some of these may turn out to be the same campaign under two names -- merge them and keep both names as aliases.)
- [ ] Add session days to the calendar (recurring events) so the Scheduler (3.10) and the refresher (3.1f) know when you play
- [ ] Test routing: "session debrief" with two active GM campaigns -> asks which; "level up Orben" -> goes straight to Orben's campaign

---

### 3.2 -- Morning Briefing

**Type:** Custom skill `/morning-briefing` (fork `skills/morning-briefing/SKILL.md`), fired right after the morning schedule is generated (3.10), with a 7 AM cron fallback
**Existing resource:** Kipi System's `/q-morning` pattern (port concept); upstream `/deadline-radar` logic for the deadline section
**Model:** Haiku (aggregation task, not reasoning)
**Token tip:** Read only local, pre-computed files: `today.json`, task frontmatter (status `ready`), `daily-health.json`, `habits.json`, `exam-countdown.json`, and the event folders' file counts. Don't scan the whole vault, and don't call Gmail or Calendar -- the caches already hold what's needed.

**Core behavior:**

- Runs right after schedule generation (wake detection), or 7 AM fallback
- Generates a brief daily note in `{{daily}}/`:
  - Today's schedule (from `today.json`)
  - Top 3 priority tasks
  - Approaching deadlines (next 3 days) -- same grouping as `/deadline-radar`, but read from the calendar cache and task frontmatter instead of querying email
  - Health one-liner, habit streaks, exam countdowns
  - Items waiting in `Meta/events/` and `{{inbox}}`
- The note links to the Kiosk's `/today` view for phone reading

**Steps:**

- [ ] Write the `/morning-briefing` skill
- [ ] Trigger it at the end of the morning pipeline (3.9 wake script), with a 7 AM fallback cron
- [ ] Test: trigger manually -> verify it's concise and actionable (aim for <200 words)

**Iteration:**

- [ ] Add pre-lecture prep for today's classes (merge with 2.1)
- [ ] Add weather if you want (quick web search)
- [ ] Add "energy check-in" prompt -- starts the day by asking your energy level
- [ ] On days with a campaign session on the calendar, add that campaign's 3.1f refresher (player campaigns) or a "prep done?" line (GM campaigns)

---

### 3.3 -- Trello Bidirectional Sync

**Type:** Two zero-token scripts on the Trello REST API, plus Atlassian's official Trello MCP server for one-off requests (optional)
**Existing resource:** Trello REST API (free key + token); official remote Trello MCP at `https://mcp.trello.com/v1` (OAuth, one workspace per connection)
**Model:** Haiku (only when a phone-side change needs a vault note)
**Token tip:** Both directions are curl scripts -- zero Claude tokens. The previous plan used the ComposioHQ Trello skill, which routed every card move through Claude and a third-party service. Moving a card is plumbing, so a script does it, the same way `push-schedule.sh` handles the calendar (3.10).

**Core behavior:**

- **Vault -> Trello (push):** `trello-push.sh` runs with the poller every 5 minutes. It finds task notes whose frontmatter changed since its last run (`find -newer`) and moves, creates or archives their cards. The Distributor and Decomposer don't do anything Trello-specific. Each vault task note stores a `trello_card_id:` in its frontmatter. Each Trello card stores the vault note path in a custom field.
- **Trello -> Vault (pull):** A lightweight bash script polls the Trello API every 5 minutes (zero Claude tokens -- just a curl call). When it detects:
  - Card moved to "Done" list -> writes a JSON event to `Meta/events/distributor/` with the task path and new status
  - New card created in "To Do" list -> writes a JSON event to `Meta/events/ingestion/` with the card title and description to create a new task note in the vault inbox
  - Card moved between lists -> writes appropriate status update message
- **Source of truth:** The vault is authoritative. Trello is a mirror with limited write-back capability. You can't decompose assignments or set effort levels from Trello -- that still happens through Claude Code. But you CAN check off tasks and add quick to-dos from your phone.

**Trello board structure:**

```
Brain Tasks (board)
  Today       -- tasks the Distributor flagged for today
  This Week   -- tasks due this week
  Backlog     -- lower priority / future tasks
  Blocked     -- tasks waiting on dependencies
  Done        -- completed (auto-archived after 3 days)
```

**Trello polling script (zero Claude tokens):**

```bash
#!/bin/bash
# trello-sync.sh -- polls Trello API, writes to message queue
# Runs via cron every 5 minutes. ZERO Claude tokens unless changes detected.

TRELLO_KEY="your-key"
TRELLO_TOKEN="your-token"
BOARD_ID="your-board-id"
DONE_LIST_ID="your-done-list-id"
TODO_LIST_ID="your-todo-list-id"
STATE_FILE="$HOME/brain-vault/Meta/trello-last-sync.json"
MSG_DIR="$HOME/brain-vault/Meta/events"

# Get cards moved to Done since last sync
DONE_CARDS=$(curl -s "https://api.trello.com/1/lists/$DONE_LIST_ID/cards?key=$TRELLO_KEY&token=$TRELLO_TOKEN")

# Compare with last known state, write messages for changes
# (Full implementation would diff against $STATE_FILE and write JSON messages)
# Each detected completion writes to $MSG_DIR/distributor/msg_[timestamp]_trello.json:
# {"from":"trello-sync","to":"distributor","type":"task-completed","task_path":"01-Projects/ee225/lab3-write-methods.md","timestamp":"..."}

# Get new cards in To Do list
NEW_CARDS=$(curl -s "https://api.trello.com/1/lists/$TODO_LIST_ID/cards?key=$TRELLO_KEY&token=$TRELLO_TOKEN")

# New cards without a vault path in their description are user-created from phone
# Write to ingestion inbox for processing:
# {"from":"trello-sync","to":"ingestion","type":"new-task","title":"Buy resistors for lab","description":"...","timestamp":"..."}

# Update state file
echo "$DONE_CARDS" > "$STATE_FILE"
```

**Steps:**

- [ ] Create a Trello board: "Brain Tasks" with lists: Today, This Week, Backlog, Blocked, Done
- [ ] Get Trello API key and token (free at https://trello.com/power-ups/admin)
- [ ] Add `trello_card_id:` field to the task note frontmatter template (in Decomposer and Scribe)
- [ ] Write `personal/scripts/trello-push.sh` (task frontmatter changed since last run -> Trello API: move/create/archive cards) and run it from the same 5-minute cron as the poller
- [ ] Write the Trello polling script (above) and add to cron: `*/5 * * * * /path/to/trello-sync.sh`
- [ ] Add Trello widget to phone home screen
- [ ] Test push: complete a task via Distributor -> verify Trello card moves to Done
- [ ] Test pull: move a card to Done on phone -> verify vault task note updates to `status: done`
- [ ] Test new task: create a card on phone in To Do -> verify a new task note appears in vault inbox
- [ ] Optional: for requests like "move my lab card to Blocked", add the official MCP (`claude mcp add --transport http trello https://mcp.trello.com/v1`) and list it in the dispatcher block (0.12). Skip it if you never ask for that -- every connected MCP server adds tool definitions to sessions.

---

### 3.4 -- Ideation Skill

**Type:** Premade skill (install and customize)
**Existing resource:** create-ideas@NeoLabHQ/context-engineering-kit
**Model:** Whatever the skill specifies
**Token tip:** Use on-demand only, never scheduled

**Steps:**

- [ ] Install the skill
- [ ] Test with a prompt relevant to your work
- [ ] Customize if needed for academic/research ideation vs. general brainstorming

---

### 3.5 -- Video Downloader

**Type:** Script, not a skill
**Existing resource:** `yt-dlp` (installed in the venv, 0.11) -- replaces the ComposioHQ video-downloader skill, which wrapped the same tool behind Claude
**Model:** N/A (utility)
**Token tip:** Zero tokens. The YouTube Transcript skill (4.4) already tries captions first; download only when there are none.

**Steps:**

- [ ] `personal/scripts/get-video.sh <url>`: `yt-dlp -x --audio-format m4a -o "~/brain-vault/drive-inbox/%(title)s.%(ext)s" <url>` -- audio lands in the inbox and flows through speech-to-text (2.3)
- [ ] Test: download a lecture video's audio -> verify it becomes a lecture note in the next batch

---

### 3.6 -- Grad School Tracking

**Type:** Skill or dedicated area in vault (not an agent)
**Existing resource:** None -- custom, but can use Deep Research skill for research
**Model:** Sonnet when actively working on it; otherwise not running
**Token tip:** This is a manually-invoked skill, not scheduled. Zero tokens when you're not using it.

**Maintained documents:**

```
02-Areas/grad-school-prep/
├── target-programs.md        (schools, labs, professors, deadlines)
├── research-interests.md     (evolving statement of your interests)
├── statement-of-purpose-draft.md
├── cv-notes.md               (experiences to highlight)
├── professor-contacts.md     (who you've emailed, responses)
└── timeline.md               (application deadlines, GRE dates, etc.)
```

**Steps:**

- [ ] Create the folder structure and initial documents
- [ ] Populate with your current grad school thinking (quantum hardware focus, target labs)
- [ ] Connect Research Radar (2.6) output to inform `research-interests.md` over time

**Iteration:**

- [ ] Add application deadline tracking -> feeds into Distributor as high-priority tasks when deadlines approach
- [ ] Add "email a professor" template generator based on their recent papers + your interests

---

### 3.7 -- Rest & Health Monitor

**Type:** Enhancement to the Distributor (our agent) -- upstream no longer ships wellness or nutrition agents, so there is nothing to integrate with
**Existing resource:** Energy self-reports (Distributor post-it), health data (3.9)
**Model:** Haiku
**Token tip:** Tracks data passively from your energy check-ins. No extra API calls -- just metadata analysis during Distributor invocations.

**Core behavior:**

- Every time you report energy level to Distributor, it's logged: `{date, time, energy, tasks_completed_today}`
- Patterns detected over time:
  - Declining energy trend over multiple days -> suggest rest day
  - Consistently low energy at certain times -> adjust task scheduling
  - High task completion with low energy reports -> you might be pushing too hard
- Hard rule: if energy <= 1 and nothing is due within 24 hours, Distributor suggests stopping instead of assigning a task

**Steps:**

- [ ] Add energy logging to Distributor agent
- [ ] Create `Meta/energy-log.json` for persistent tracking
- [ ] Add rest-detection logic to Distributor prompt

---

### 3.8 -- Habit Tracker / Creator

**Type:** Skill + Distributor integration + Morning Briefing integration
**Existing resource:** None -- custom build. Inspired by Atomic Habits framework (four laws: make it obvious, attractive, easy, satisfying).
**Model:** Haiku for tracking/reminders. Sonnet for habit creation plans and proactive suggestions.
**Token tip:** Tracking is just JSON updates (trivial). The expensive part -- generating a habit creation plan -- runs once per new habit. Daily tracking costs ~200 tokens per check-in (read habit JSON, update one field).

**Core behavior:**

When you say "I want to start hitting the gym consistently," the system:
1. Creates a habit entry with a science-based onboarding plan
2. Integrates the habit into your daily routines (morning briefing, Distributor, dynamic scheduler)
3. Tracks completion, streaks, and patterns over time
4. Adapts when you're struggling and celebrates when you're consistent

**Habit data -- `Meta/habits.json`:**

```json
{
  "habits": [
    {
      "id": "gym",
      "name": "Go to the gym",
      "target_frequency": "3x/week",
      "target_days": ["monday", "wednesday", "friday"],
      "preferred_time": "morning",
      "duration_min": 60,
      "current_streak": 5,
      "longest_streak": 12,
      "total_completions": 23,
      "total_misses": 8,
      "completion_rate_30d": 0.74,
      "status": "active",
      "created": "2026-04-01",
      "onboarding_plan": {
        "phase": "building",
        "week_1": "Just show up -- even 15 minutes counts",
        "week_2": "30 minute sessions, any exercises",
        "week_3": "45-60 minutes with a basic routine",
        "trigger": "After morning coffee, put on gym clothes",
        "reward": "Protein shake + 10 min guilt-free phone time after",
        "stack_on": "morning-coffee"
      },
      "log": [
        {"date": "2026-04-10", "completed": true, "notes": "45 min, legs day"},
        {"date": "2026-04-09", "completed": false, "reason": "didn't have time"},
        {"date": "2026-04-07", "completed": true, "notes": "30 min, cardio"}
      ],
      "adaptation_history": [
        {"date": "2026-04-08", "change": "Moved from evening to morning -- kept missing evening sessions due to homework"}
      ]
    },
    {
      "id": "reading",
      "name": "Read for 30 minutes",
      "target_frequency": "daily",
      "current_streak": 0,
      "status": "struggling",
      "adaptation_suggestion": "Try 10 minutes instead of 30 -- you've missed 5 of the last 7 days"
    }
  ]
}
```

**Tracking:** When you say "I went to the gym today" or "didn't have time to read today," the system updates the habit log. Can also auto-detect from health data (3.9) -- elevated heart rate at gym location = auto-log gym habit.

**Morning Briefing integration:** Shows today's habits with streaks. "Gym day (streak: 5). Reading: missed 2 days -- try 10 minutes tonight?"

**Distributor integration:** Habit tasks appear alongside academic tasks when you ask "what should I do?" If it's a gym day and you haven't gone yet, the Distributor surfaces it at an appropriate energy level and time slot.

**Dynamic Scheduler integration (3.10):** Habit blocks are scheduled into the day plan. Gym block on M/W/F mornings. Reading block in the evening.

**Adaptation:** If you're consistently missing a habit, the system suggests adjustments:
- Missed 3 of last 5 gym sessions? -> "Try shorter sessions (20 min instead of 60)"
- Always missing evening reading? -> "Try switching to morning or after lunch"
- Streak broken after 10 days? -> "You were doing great. What changed? Let's adjust the trigger."
- The system never shames. Uses ADHD-friendly language: "carried forward" not "missed."

**Proactive suggestions:** The system notices patterns in your behavior and suggests new habits:
- Sleep data (from 3.9) consistently bad? -> "Your sleep has been under 6 hours for a week. Would you like to set a bedtime habit?"
- Energy reports always low on Mondays? -> "You seem to have a rough start to the week. Want to try a Sunday night wind-down routine?"
- Studying only happens in last-minute cramming? -> "You tend to study most the day before deadlines. Want to set a daily 30-min study habit?"
- Proactive suggestions are gentle -- offered once, not nagged. Stored in `Meta/habit-suggestions.json` so the system doesn't re-suggest things you've declined.

**Streaks and visualization:** The Kiosk's `/habits` page (0.13) shows:
- Current streaks per habit with visual streak bars
- 30-day completion calendar (green/red grid per habit)
- Trends over time (are you getting more consistent or less?)
- Comparison of weeks (this week vs last week vs monthly average)
- Bookmark it, or say "show me my habits" and Claude replies with the link (~50 tokens). Viewing it costs nothing, because the page reads `habits.json` directly.
- Iteration: one-tap check-in buttons on the same page append to `Meta/habit-checkins.jsonl`. The habit tracker merges them into `habits.json` on its next run, so `habits.json` has one writer.

**Steps:**

- [ ] Define `Meta/habits.json` format
- [ ] Write habit creation flow in the skill: user states goal -> system generates onboarding plan using Atomic Habits framework (trigger, routine, reward, habit stacking)
- [ ] Add habit tracking to Distributor: "I went to the gym" -> update log
- [ ] Add habit display to Morning Briefing: today's habits + streaks
- [ ] Add adaptation logic: if completion_rate_30d < 0.5 for 2+ weeks, suggest adjustment
- [ ] Add proactive suggestion system: analyze energy logs, sleep data, and study patterns for habit opportunities
- [ ] Build the Kiosk `/habits` page (reads `habits.json`); later add one-tap check-ins (append to `Meta/habit-checkins.jsonl`, merged by the habit tracker)
- [ ] Test: create a gym habit -> track for 5 days -> verify streak updates, morning briefing shows it, Distributor suggests it on target days
- [ ] Test adaptation: miss a habit 4 times in a row -> verify system suggests adjustment, not shame

---

### 3.9 -- Health Data Integration (Samsung Watch + Oura Ring)

**Type:** Data pipeline + integration with Distributor, Habits, Rest Monitor, and Dynamic Scheduler
**Existing resource:** Oura Ring REST API, Samsung Health via Health Connect, both devices owned
**Model:** Haiku for daily data analysis. No Claude tokens for data collection itself.
**Token tip:** Data collection is Python scripts (zero tokens). Daily analysis runs once in the morning briefing (~1,000 tokens to read the health JSON and generate insights). The data informs other components (Distributor, Scheduler) passively by being available in a cached file they already read.

**Data sources and what each provides:**

| Data Point | Samsung Watch | Oura Ring | Strategy |
|-----------|--------------|-----------|----------|
| Heart rate | Yes | Yes | Average both when timestamps overlap |
| Steps | Yes | Yes | Average both |
| Sleep duration | Yes | Yes | Average both |
| Sleep stages (deep/REM/light) | Yes | Yes | Average both |
| HRV | No | **Yes (Oura only)** | Use Oura |
| Sleep score / Readiness | No | **Yes (Oura only)** | Use Oura |
| BMR | **Yes (Samsung only)** | No | Use Samsung |
| Body composition | **Yes (Samsung only)** | No | Use Samsung |
| SpO2 | Yes | Yes | Average both |
| Stress level | **Yes (Samsung only)** | No | Use Samsung |
| Activity/workout detection | Yes | Yes | Use whichever detected the session |
| Skin temperature | No | **Yes (Oura only)** | Use Oura |

**Data collection pipeline:**

```
Two parallel collection paths:

Path A -- Oura Ring (REST API):
1. Python script runs daily via cron at 7 AM
2. Queries Oura API for last 24 hours of data:
   curl -H "Authorization: Bearer $OURA_TOKEN" \
     "https://api.ouraring.com/v2/usercollection/daily_sleep"
   (also: daily_readiness, daily_activity, heartrate, etc.)
3. Parses JSON response, extracts relevant metrics
4. Writes to Meta/health/oura-daily.json

Path B -- Samsung Health (Health Connect):
1. Option A: Claude Android app has Health Connect permission --
   if accessible via Claude Code remote, query directly
2. Option B (more reliable): Android automation (Tasker/MacroDroid)
   exports Health Connect data to JSON daily into a separate Drive
   folder, Brain-Health/ (NOT Brain-Inbox -- that would cost ingestion
   tokens). rclone pulls it before the merge (zero tokens):
     rclone move gdrive:Brain-Health ~/brain-vault/Meta/health/raw
   health-merge.py turns it into Meta/health/samsung-daily.json
3. Option C: Use Samsung Health API (requires Samsung developer account)

Path C -- Merge and analyze:
1. Python script (zero tokens) reads both daily files
2. For overlapping data: averages values at matching timestamps
3. For device-exclusive data: uses the available source
4. Writes merged data to Meta/health/daily-health.json
5. Appends to Meta/health/health-history.json (rolling 90-day log)
```

**Merged daily health file -- `Meta/health/daily-health.json`:**

```json
{
  "date": "2026-04-10",
  "sleep": {
    "duration_hours": 6.8,
    "deep_sleep_hours": 1.2,
    "rem_sleep_hours": 1.5,
    "sleep_score": 72,
    "bedtime": "00:30",
    "wake_time": "07:18",
    "source": "oura+samsung_avg"
  },
  "readiness": {
    "score": 68,
    "source": "oura"
  },
  "hrv": {
    "avg_ms": 42,
    "source": "oura"
  },
  "stress": {
    "avg_level": "medium",
    "high_stress_minutes": 45,
    "source": "samsung"
  },
  "activity": {
    "steps": 8420,
    "active_minutes": 35,
    "workouts": [
      {"type": "gym", "duration_min": 45, "start": "08:15", "source": "samsung"}
    ],
    "source": "oura+samsung_avg"
  },
  "body": {
    "bmr_kcal": 1850,
    "weight_kg": null,
    "body_fat_pct": null,
    "source": "samsung"
  },
  "predicted_energy": 3,
  "notes": "Below-average sleep, moderate stress. Suggest lighter task load."
}
```

**How the system uses health data:**

| Component | How It Uses Health Data |
|-----------|----------------------|
| **Distributor** | Reads `predicted_energy` from health JSON before you self-report. Pre-adjusts task suggestions. If Oura readiness < 60, preemptively suggests lighter tasks. |
| **Morning Briefing** | Shows sleep score, readiness, and a one-line health summary. "Sleep: 6.8h (below target). Readiness: 68. Taking it easy today might help." |
| **Rest Monitor (3.7)** | Uses HRV trend (declining over 3+ days = burnout risk) and stress data to trigger rest suggestions more aggressively. |
| **Habit Tracker (3.8)** | Auto-logs workouts detected by watch. Correlates habit completion with health metrics over time (e.g., "gym days correlate with better sleep scores"). |
| **Dynamic Scheduler (3.10)** | Adjusts day plan intensity based on readiness. Low readiness = more rest blocks, shorter study sessions. |
| **Study Skill** | If readiness is low, study orchestrator defaults to Kiosk-only modes (flashcards, quizzes) rather than demanding conversational modes (Socratic, teach-back). |
| **Auto-wake schedule (3.10)** | When Oura/Samsung detects wake-up, triggers daily schedule generation automatically. |

**Steps:**

- [ ] Get Oura API personal access token from https://cloud.ouraring.com/personal-access-tokens
- [ ] Write Oura data collection Python script (daily cron)
- [ ] Set up Samsung Health -> Health Connect -> export pipeline (Tasker/MacroDroid to the Drive folder `Brain-Health/`, pulled by rclone; or via the Claude Android app if accessible from Claude Code)
- [ ] Write merge script that combines both sources with averaging for overlapping data
- [ ] Create `Meta/health/` directory structure
- [ ] Add `predicted_energy` calculation: simple formula based on sleep score + readiness + stress
- [ ] Add health data reading to Distributor prompt: "Check Meta/health/daily-health.json for predicted energy before assigning tasks"
- [ ] Add health summary to Morning Briefing
- [ ] Connect workout auto-detection to habit tracker (3.8)
- [ ] Test: verify both data sources collect, merge script runs, and Distributor adjusts recommendations based on sleep quality

**Wake Detection Script (triggers morning pipeline):**

A lightweight cron script polls the Oura API every 10 minutes between 5 AM and 5 PM. When it detects you've woken up (Oura's `bedtime_end` timestamp appears), it fires the morning pipeline exactly once. Zero Claude tokens until wake is actually detected.

```bash
#!/bin/bash
# check-wake.sh -- polls Oura for wake detection
# Cron: */10 5-17 * * * /path/to/check-wake.sh
# Runs every 10 min from 5 AM to 5 PM. Zero tokens until wake detected.

OURA_TOKEN="your-token"
WAKE_FILE="$HOME/brain-vault/Meta/health/wake-detected.flag"
TODAY=$(date +%Y-%m-%d)

# Don't re-trigger if already detected today
if [ -f "$WAKE_FILE" ] && grep -q "$TODAY" "$WAKE_FILE"; then
  exit 0
fi

# Check Oura for today's sleep data
SLEEP=$(curl -s -H "Authorization: Bearer $OURA_TOKEN" \
  "https://api.ouraring.com/v2/usercollection/daily_sleep?start_date=$TODAY")

# If bedtime_end exists for today, you woke up
WAKE_TIME=$(echo "$SLEEP" | python3 -c "
import sys, json
data = json.load(sys.stdin)
if data.get('data'):
    print(data['data'][0].get('bedtime_end', ''))
" 2>/dev/null)

if [ -n "$WAKE_TIME" ]; then
  echo "$TODAY $WAKE_TIME" > "$WAKE_FILE"
  # Trigger the morning pipeline:
  # 1. Pull the Samsung export, then merge (0 tokens)
  rclone move gdrive:Brain-Health ~/brain-vault/Meta/health/raw -q
  python3 ~/brain-vault/My-Brain-Is-Full-Crew/personal/scripts/health-merge.py
  # 2. Schedule generation (Claude -- only token cost of the morning).
  #    cd first so the vault's CLAUDE.md and settings.local.json allowlist load.
  cd ~/brain-vault && claude --model haiku --print \
    "/schedule generate today. Write Meta/schedule/today.json."
  # 3. Push to Google Calendar (script, 0 tokens -- Claude never touches the calendar)
  ~/brain-vault/My-Brain-Is-Full-Crew/personal/scripts/push-schedule.sh
  # 4. Morning briefing follows automatically (triggered by schedule file update)
fi
```

The 5 PM cutoff handles edge cases like naps being misdetected as overnight sleep. If Oura doesn't detect wake by 7 AM (ring not worn, data delay), the fallback cron at 7 AM fires the morning pipeline anyway.

**Iteration:**

- [ ] Build the Kiosk `/health` page (reads `Meta/health/health-history.json`): sleep trends, HRV trends, stress patterns, activity levels over 30/90 days
- [ ] Correlate health metrics with academic performance: "you perform better on assignments when you slept 7+ hours"
- [ ] Add weight/body composition tracking if you start using Samsung scale

---

### 3.10 -- Dynamic Scheduling

**Type:** Custom skill `/schedule` (fork `skills/schedule/SKILL.md`) + two zero-token `gws` scripts (calendar cache sync, schedule push) + health data integration
**Existing resource:** `gws` CLI (0.2) for Google Calendar read/write from bash. Upstream `/weekly-agenda` (its calendar + email + vault aggregation is reused as input to the week-ahead plan). Kipi System's friction-ordering patterns.
**Model:** Haiku for daily schedule generation and rescheduling. Sonnet only for initial weekly plan generation.
**Token tip:** Claude never talks to Google Calendar. It only reads and writes local JSON (`Meta/schedule/`). One zero-token script pulls the calendar into a cache every 4 hours; another pushes changed future blocks out after every schedule change. Claude's job shrinks to "edit today.json", which is the single biggest token optimization for this feature.

**Core behavior:**

Every morning (triggered automatically when health devices detect wake-up, or at a preset fallback time), the system generates a time-blocked schedule for the day. Pushes it to Google Calendar. Throughout the day, you report changes and the system adapts in real-time.

**Schedule generation inputs:**

1. **Calendar cache** (`Meta/schedule/calendar-cache.json`): immovable events (classes, appointments, meetings). Updated every 4 hours by a lightweight cron script (zero tokens -- just a calendar API read + file write). You never need to check the actual calendar during rescheduling.
2. **Task list**: task frontmatter (status: ready, effort, time_est, priority, due_date)
3. **Habits due today**: from `Meta/habits.json`
4. **Energy prediction**: from `Meta/health/daily-health.json` (predicted_energy based on sleep/readiness)
5. **Historical energy patterns**: "On Tuesdays you're typically low energy after 3 PM" from `Meta/energy-log.json`
6. **Exam countdowns**: from `Meta/exam-countdown.json`
7. **Morning buffer**: preset time between wake-up and first scheduled item (configured in profile, e.g., 45 minutes)

**Schedule file -- `Meta/schedule/today.json`:**

```json
{
  "date": "2026-04-10",
  "wake_time": "07:18",
  "morning_buffer_min": 45,
  "first_available": "08:03",
  "predicted_energy_curve": {
    "08:00": 3, "10:00": 4, "12:00": 3, "14:00": 3,
    "16:00": 2, "18:00": 2, "20:00": 3, "22:00": 2
  },
  "blocks": [
    {"time": "08:03", "end": "08:45", "type": "habit", "name": "Gym", "status": "scheduled", "movable": true},
    {"time": "09:00", "end": "09:50", "type": "immovable", "name": "EE225 Lecture", "location": "Tech L211", "calendar_id": "abc123"},
    {"time": "10:00", "end": "10:50", "type": "immovable", "name": "COMP_ENG 303 Lecture", "location": "Ford 1.350", "calendar_id": "def456"},
    {"time": "10:50", "end": "11:05", "type": "travel", "name": "Walk to library", "auto_generated": true},
    {"time": "11:05", "end": "12:00", "type": "task", "name": "EE225 Lab Report - Methods Section", "task_path": "01-Projects/ee225/lab3-methods.md", "effort": 3, "status": "scheduled", "movable": true},
    {"time": "12:00", "end": "12:45", "type": "break", "name": "Lunch", "status": "scheduled", "movable": true},
    {"time": "12:45", "end": "13:30", "type": "study", "name": "Study: RC Circuits (flashcards)", "course": "EE225", "status": "scheduled", "movable": true},
    {"time": "14:00", "end": "14:50", "type": "immovable", "name": "PHYSICS 332 Lecture", "calendar_id": "ghi789"},
    {"time": "15:00", "end": "16:00", "type": "task", "name": "COMP_ENG 303 Problem Set Q1-3", "task_path": "01-Projects/ce303/pset4-q1-3.md", "effort": 4, "status": "scheduled", "movable": true},
    {"time": "16:00", "end": "16:30", "type": "habit", "name": "Read 30 minutes", "status": "scheduled", "movable": true},
    {"time": "16:30", "end": "18:00", "type": "free", "name": "Buffer / personal time", "movable": true},
    {"time": "18:00", "end": "19:00", "type": "break", "name": "Dinner", "movable": true},
    {"time": "19:00", "end": "20:30", "type": "task", "name": "EE225 Lab Report - Results Section", "effort": 3, "status": "scheduled", "movable": true},
    {"time": "20:30", "end": "22:00", "type": "free", "name": "Evening free time / D&D prep", "movable": true}
  ],
  "calendar_cache_last_synced": "2026-04-10T06:00:00",
  "version": 3,
  "adaptations": [
    {"time": "13:45", "change": "Moved study session from 13:30 to 15:00 -- user reported going to lunch with friends"},
    {"time": "17:30", "change": "Added dinner plans at 18:00 -- shifted evening tasks"}
  ]
}
```

**Calendar cache strategy (token optimization):**

```
Meta/schedule/calendar-cache.json:
- Contains all Google Calendar events for the next 7 days
- Updated by personal/scripts/calendar-sync.sh every 4 hours (zero tokens):
    gws calendar events list --params '{"calendarId": "primary",
      "timeMin": "<now>", "timeMax": "<now+7d>", "singleEvents": true}'
  (repeat for the Canvas ICS calendar and any shared university calendar)
- The scheduler reads this LOCAL file, never calls the calendar directly
- When YOU add a new event ("I have dinner at 6"), the /schedule skill:
  1. Adds it to the local cache file and to today.json
  2. Reschedules the day from the local cache
  3. Runs personal/scripts/push-schedule.sh (zero tokens), which sends
     the new event plus any moved future blocks to Google Calendar via gws
  - Total Claude work: edit two local files. No calendar read, no API calls.
- When the 4-hour sync runs:
  1. Pulls the next 7 days via gws
  2. Diffs against local cache
  3. If changes found (someone invited you to a meeting): updates the cache
     and writes an event to Meta/events/scheduler/ (0.10), which triggers
     a reschedule
  4. If no changes: does nothing (zero tokens)
```

**Week-ahead view -- `Meta/schedule/week-plan.json`:**

A rolling 7-day lookahead updated every Sunday evening (cron, Sonnet for initial plan generation ~5,000 tokens, then maintained via daily updates).

- Day 0 (today): time-blocked detail (today.json)
- Days 1-6: rough plan (major events, deadlines, planned study sessions, exam countdowns)
- Prevents being blindsided by upcoming deadlines or exams
- Used by the daily scheduler to pre-allocate study time for big assignments due later in the week

**Adaptation examples:**

| You Say | System Does |
|---------|------------|
| "I'm done with the methods section" | Marks task done, removes block, checks if anything should fill the gap or if you get free time |
| "I'm going to dinner at 6" | Adds dinner event at 18:00, shifts or shrinks any blocks that overlap, pushes to Google Calendar |
| "I actually spent 4 hours playing Minecraft" | Marks the lost time, reschedules remaining tasks by priority. Doesn't judge. "Here's your updated plan for the rest of the evening." |
| "I don't feel like studying" | Offers alternatives at current energy level. If nothing is urgent, grants free time. If deadline is tomorrow, gently notes it. |
| "I have plans from 3-5 instead" | Moves whatever was in 3-5 to the next available slot, adjusts downstream blocks |
| "Actually I finished the problem set faster than expected" | Notes the shorter actual time (feeds back to improve future estimates), frees up the remaining time |
| "I want to work out more" | Creates habit (3.8), integrates gym blocks into future daily schedules |

**Travel time estimation:**

- If two consecutive events have different locations: insert travel time block
- Uses a simple location-pair lookup table in `Meta/schedule/travel-times.json`:

```json
{
  "pairs": {
    "Tech L211 -> Ford 1.350": 10,
    "Ford 1.350 -> Mudd Library": 8,
    "home -> campus": 20,
    "campus -> downtown": 25
  },
  "default_same_building": 5,
  "default_different_building": 12
}
```

- Learns over time as you add pairs. If unknown, uses `default_different_building`.
- Back-to-back study sessions at same location: no travel time (assumes same place).

**Auto-wake trigger:**

When health data integration (3.9) detects wake-up (Oura/Samsung):
1. Health data merge script runs (zero tokens)
2. Writes wake_time to `Meta/health/daily-health.json`
3. File watcher detects the update
4. Triggers schedule generation: reads all inputs, generates `today.json`, pushes to Google Calendar
5. By the time you check your phone, today's schedule is already in your calendar

Fallback: if wake detection doesn't fire (devices not worn, data delay), schedule generates at a preset fallback time (e.g., 7 AM cron).

**Google Calendar sync (write-only -- never read during rescheduling):**

- **Who pushes:** `personal/scripts/push-schedule.sh`, never Claude. It compares `today.json` to `Meta/schedule/pushed.json` (what's already in Google Calendar, with event IDs) and calls `gws calendar events insert/patch/delete` only for **future** blocks that changed. Then it updates `pushed.json`.
- **Morning generation:** push all today's blocks to Google Calendar as events on the "Brain Schedule" calendar
- **Rescheduling:** push ONLY changed/new future blocks. Never modify or delete past blocks.
- **Task completion:** Do NOT update Google Calendar when a block is completed. The past event just stays as-is. Nobody looks at the past.
- **Rule: the scheduler only runs in two situations:**
  1. Morning generation (triggered by wake detection or 7 AM fallback)
  2. When you report a change ("I have dinner at 6," "I'm done," "I don't feel like studying")
  - It does NOT run continuously, does NOT poll, does NOT run on a timer during the day.
- Use a dedicated "Brain Schedule" calendar (separate from your main calendar so immovable events stay clean)
- Color-coded by block type: tasks = blue, study = green, habits = orange, breaks = gray, free time = white
- Immovable events stay in your main calendar -- the scheduler reads them from the local cache but never modifies them

**Steps:**

- [ ] Create `Meta/schedule/` directory with `today.json`, `week-plan.json`, `calendar-cache.json`, `travel-times.json`
- [ ] Write `personal/scripts/calendar-sync.sh` (`gws calendar events list` -> `calendar-cache.json`, every 4 hours via cron, zero tokens; writes a `Meta/events/scheduler/` event only when something changed)
- [ ] Write the `/schedule` skill: reads all inputs (cache, tasks, habits, health, energy patterns), generates time-blocked plan, writes to `today.json`, then runs `push-schedule.sh`
- [ ] Create the "Brain Schedule" calendar once by hand in Google Calendar (the `gws` scopes don't include creating calendars) and write `personal/scripts/push-schedule.sh` (diff `today.json` vs `pushed.json`, push future changes with color coding via `gws`)
- [ ] Write rescheduling logic in `/schedule`: when you report a change, update `today.json`, then run `push-schedule.sh`
- [ ] Add schedule display to Morning Briefing: "Today's plan: [summary of blocks]"
- [ ] Connect health data auto-wake trigger: health file update -> file watcher -> schedule generation
- [ ] Add fallback 7 AM cron trigger if wake detection doesn't fire by then
- [ ] Populate `travel-times.json` with your common location pairs (dorm/home to campus buildings)
- [ ] Write weekly plan generation: runs Sunday evening, creates rolling 7-day lookahead. Reuse `/weekly-agenda`'s aggregation (calendar + email deadlines + vault tasks) as the input rather than rebuilding it; `/schedule` adds the time-blocking. "plan my week" routes to `/schedule` (0.12).
- [ ] Test: trigger schedule generation manually -> verify blocks appear in Google Calendar
- [ ] Test adaptation: "I have dinner at 6" -> verify schedule adjusts and Calendar updates
- [ ] Test auto-wake: simulate wake detection -> verify schedule generates automatically

**Token cost per day:**

| Action | Tokens | Frequency |
|--------|--------|-----------|
| Morning schedule generation | ~3,000 | 1x daily |
| Rescheduling on change | ~1,500 | 3-5x daily |
| Calendar cache sync | 0 (bash) | Every 4 hours |
| Week plan generation | ~5,000 (Sonnet) | 1x weekly |
| **Daily total** | **~7,500-10,500** | |

---

### 3.11 -- Explain My Week Summary

**Type:** Scheduled skill (Friday or Sunday)
**Existing resource:** Weekly Synthesis (2.5) covers academic notes. This covers EVERYTHING.
**Model:** Sonnet for synthesis (forked skill, 0.12); Kokoro (local) for the optional audio version
**Token tip:** Reads cached data only (habit JSON, health history, energy log, grade tracker, study session log, task completion log). No vault note scanning needed -- all data is already aggregated in JSON files.
**Audio version:** Kokoro-82M, a small open-weight (Apache 2.0) voice model that runs locally on the 4070 Ti and handles long narration well. It replaces the paid ElevenLabs/Google TTS options: zero cost, and nothing leaves your machine. If you want a more natural voice later, Qwen3-TTS (open-sourced January 2026) is the step up, at the cost of a heavier setup.

**Core behavior:**

Generates a comprehensive weekly review covering all aspects of your life the system tracks. Optionally converts to audio so you can listen while walking or commuting.

**Content:**

1. **Academic:** Tasks completed this week, assignments submitted, study sessions (total hours, topics covered, weak areas). Grade projections per course. Exam countdowns.
2. **Habits:** Completion rates per habit, streak updates, trends. "Gym: 3/3 this week (streak: 12). Reading: 4/7 (down from last week)."
3. **Health:** Average sleep score, HRV trend, stress pattern, activity level. "Sleep averaged 6.5h -- below your 7h target. HRV trending down since Wednesday."
4. **Energy/Productivity:** Average energy self-reports by day, tasks completed vs planned, time estimate accuracy. "You completed 85% of planned tasks. Your time estimates for coding tasks are consistently 30% too low."
5. **Schedule adherence:** How closely your actual day followed the dynamic schedule. "You followed the schedule 70% of the time. Most deviations were afternoon free-time extensions."
6. **Upcoming:** Next week's major events, deadlines in the next 14 days, exams approaching.
7. **Insights/suggestions:** "Your best study days are Tuesday and Thursday. Consider scheduling heavy study sessions then. Your gym habit is strong -- your sleep scores are 15% higher on gym days."

**Output:** A markdown note in `07-Daily/week-summary-[date].md` + optionally an audio file via TTS.

**Steps:**

- [ ] Write the `/explain-my-week` skill (fork `skills/explain-my-week/SKILL.md`) that reads from all system JSON files (habits, health, energy, grades, study sessions, schedule adherence, task completions). Triggers: "explain my week", "how did my week go", "week summary" -- never "weekly review" (upstream routes that to `/vault-audit`).
- [ ] Set up cron trigger: Sunday 7 PM
- [ ] Test: manually trigger after a week of data -> verify comprehensive summary
- [ ] Optional: `~/.venvs/brain/bin/pip install kokoro soundfile` (needs `espeak-ng`, installed in 0.0); `personal/scripts/speak.py` turns the summary note into `week-summary-[date].mp3` in the 3 AM batch after the Sunday run -- zero tokens

---

## PHASE 4 -- PREMADE SKILLS TO INSTALL

Skills that don't need custom development -- just install and configure.

**Two rules for every skill in this phase:**
1. Install into the vault's `.claude/skills/` with the skill's own installer (e.g., `npx skills add <repo> --skill <name> -a claude-code`). Upstream's updater only replaces its own 14 skill folders, so these survive updates.
2. Add the skill's name to the "Extra tools" line of your dispatcher block (0.12). Otherwise the dispatcher treats it as nonexistent and refuses to use it.

---

### 4.1 -- NotebookLM (notebooklm-py, with Auto-Upload Integration)

**Source:** teng-lin/notebooklm-py (MIT) -- a Python library, CLI and Claude Code skill. Replaces the sanjay3290 notebooklm skill.
**Used by:** Study skill (2.2) for conceptual question generation, Ingestion pipeline (1.1) for auto-uploading course materials
**Why the switch:** the old skill drove a real Chrome window with Playwright for every action. notebooklm-py calls NotebookLM's web endpoints directly, so uploads and questions are quick script calls, and it has a "master token" sign-in meant for unattended runs like the 3 AM batch. It's also far more widely used (about 18,500 GitHub stars) and can generate NotebookLM's own quizzes, flashcards and audio overviews. The caveat applies to both: neither is an official Google API, so a change on Google's side can break it until the library catches up.

**Steps:**

- [ ] Install in the venv with its browser extra (Playwright, for the sign-in window): `uv pip install --python ~/.venvs/brain "notebooklm-py[browser]"`, then `notebooklm login`. For cron runs, add a daily `notebooklm auth refresh --quiet`, or switch to the master-token sign-in from the README (`notebooklm login --master-token --account <your Gmail>`), which renews itself without a browser.
- [ ] Install the Claude Code skill: `notebooklm skill install` (or `npx skills add teng-lin/notebooklm-py`), and add it to the dispatcher block's third-party skills line (0.12)
- [ ] Create one notebook per course (`notebooklm create "EE225 - Circuit Analysis"`) and record each ID in `Meta/notebooklm-notebooks.json` (format in 1.1 iteration section)
- [ ] Test standalone: `notebooklm source add <a lecture PDF>` into the EE225 notebook, then `notebooklm ask "What are the key concepts?"` -> verify a source-grounded answer
- [ ] Verify integration with ingestion pipeline (1.1): upload a lecture note -> confirm it gets added to the correct notebook automatically
- [ ] Verify integration with study skill (2.2c): start a Socratic session on a topic -> verify questions are pulled from the correct notebook
- [ ] **Experiment (month 2, optional):** NotebookLM can generate flashcards and quizzes itself (`notebooklm generate flashcards` / `quiz`), on Google's quota instead of Claude's. For one course, for two weeks, import its cards into the Kiosk alongside Sonnet's and compare deletion rates in `card-edits/_stats.json` (0.13). If they hold up, that course's card generation -- the biggest token line in the system -- moves off Claude.

**How the auto-upload pipeline works end-to-end:**

1. You take notes on iPad in lecture
2. Export notes to Google Drive `Brain-Inbox/` folder
3. rclone pulls the file in, the watcher queues it, and the ingestion agent runs (3 AM, or right away if urgent)
4. Ingestion agent classifies file, creates vault note with `course: EE225` frontmatter
5. Ingestion agent reads `Meta/notebooklm-notebooks.json`, finds EE225 notebook ID
6. Ingestion agent runs `notebooklm source add` for that notebook
7. Later, when you study: study skill asks the EE225 notebook for conceptual questions
8. NotebookLM returns source-grounded answers that reference YOUR specific lecture content

**Token tip:** Uploads and notebook management are CLI calls -- zero Claude tokens beyond the one command. Only reading the answer to a question costs tokens.

### 4.2 -- Deep Research Skill

**Source:** deep-research@sanjay3290/ai-skills (still the pick: it hands the research to Gemini's Deep Research agent through the Gemini API, so the heavy reading happens on Google's quota, not your Claude usage; needs a Gemini API key)
**Used by:** Research Radar (2.6), Grad School Tracking (3.6)
**Steps:**
- [ ] Install the skill
- [ ] Test with a quantum computing research query
- [ ] Verify output format works for your digest file

### 4.3 -- Learn This (Tapestry Skills)

**Source:** michalparkola/tapestry-skills "Learn This"
**Used by:** Study skill (2.2), Research Radar (2.6) for paper summaries
**Steps:**
- [ ] Install the skill
- [ ] Test with a concept from one of your courses
- [ ] Integrate with study skill workflow

### 4.4 -- YouTube Transcript (Tapestry Skills)

**Source:** michalparkola/tapestry-skills "YouTube Transcript"
**Used by:** Lecture audio pipeline (2.3) for supplementary videos
**Steps:**
- [ ] Install the skill
- [ ] Test with a lecture video URL
- [ ] Verify transcript feeds into study skill for card generation

### 4.5 -- Article Extractor (Tapestry Skills)

**Source:** michalparkola/tapestry-skills "Article Extractor"
**Used by:** Research Radar (2.6), general resource ingestion
**Steps:**
- [ ] Install the skill
- [ ] Test with an academic article URL

### 4.6 -- Unblock Action (Tapestry Skills)

**Source:** michalparkola/tapestry-skills "Unblock Action"
**Used by:** Distributor -- when you're stuck and no task feels right
**Steps:**
- [ ] Install the skill
- [ ] Test and customize for academic context

### 4.7 -- Video Downloader

Moved to a script: see 3.5 (`yt-dlp`). No skill to install.

### 4.8 -- Trello

Moved to scripts plus the optional official Trello MCP: see 3.3. No skill to install.

### 4.9 -- Ideation (NeoLabHQ)

**Source:** create-ideas@NeoLabHQ/context-engineering-kit
**Steps:**
- [ ] Install
- [ ] Test

### 4.10 -- Other ComposioHQ Automations

Dropped. `gws` covers Gmail and Calendar (0.2), rclone covers Drive (0.3), and scripts cover Trello (3.3), all without routing through a third-party service or spending Claude tokens.

---

## PHASE 5 -- OPTIMIZATION & ITERATION

Ongoing improvements after the system is running.

---

### 5.1 -- Token Usage Audit

**When:** After 2 weeks of use
**Steps:**

- [ ] Check your Claude usage dashboard -- which agents/skills are consuming the most?
- [ ] Identify any agents that run frequently but produce low value
- [ ] Downgrade heavy agents from Sonnet to Haiku where quality is acceptable
- [ ] Review agent prompts again -- after real usage you'll see which instructions are actually needed
- [ ] Check for any /loop tasks that could be converted to event-driven triggers

### 5.2 -- Model Assignment Optimization

**Recommended model assignments (starting point -- tune based on experience):**

In Claude Code (September 2026), `haiku` = Haiku 4.5, `sonnet` = Sonnet 5.5, `opus` = Opus 5.5. The vault defaults to `sonnet` (0.12); "Haiku" below means a forked skill or agent pinned to it. Fable and Opus are never needed here.

| Component | Model | Reasoning |
|-----------|-------|-----------|
| Distributor | Haiku | Filtering/ranking metadata, no deep reasoning |
| Decomposer | Sonnet | Needs to understand assignments and generate good task breakdowns |
| Ingestion classifier | **Local `qwen3.5:9b`**; Haiku only if it says unclassified | Classification moved to 0.11 pre-processing |
| Ingestion OCR/parsing | **Local (`qwen3-vl:8b-instruct` for images and handwritten PDFs, Marker for typed documents)**; Sonnet vision only for flagged pages and diagram figures | 0.11 |
| Study - session orchestrator | Sonnet (session default) + forked Haiku `/study-log` | Brain dump evaluation, mode selection and self-assessment on Sonnet; logging and bookkeeping on Haiku (2.2k). |
| Study - flashcard review | **Kiosk (0 tokens per card)** | `/review` and `/s/{id}/flashcards` (0.13). FSRS-6 runs server-side and writes `review-state/`. ~150 tokens to launch from a session, 0 standalone. Works on your phone over Tailscale. |
| Study - MC quiz / formula practice | **Kiosk (0 tokens per question)** | `/s/{id}/quiz`. Auto-checking and randomized values; formulas go through the safe evaluator. |
| Study - batch question generation | Sonnet (`/study-gen` skill) | Runs at INGESTION TIME, not during study sessions. The batch runs `/study-gen` right after ingestion to generate cards/quizzes/problems for new notes. ~5,000-8,000 tokens per note, once. |
| Study - Socratic dialogue | Sonnet | Conversational reasoning, follow-up questions, hint generation. Needs Claude on every turn, so it can't move to the Kiosk. |
| Study - practice problem gen | Sonnet (`/study-gen`) | Runs at INGESTION TIME. Generates problem templates with variable_ranges and solution_formula. Also extracts formulas for per-topic formula sheets. |
| Study - derive-it / formula review | **Kiosk (0 tokens per problem)** | `/s/{id}/derive`. Loads the per-topic formula sheet + practice problems, randomizes values, auto-checks with the safe evaluator. KaTeX is vendored, so it renders offline. |
| Study - teach-back evaluation | Sonnet | Evaluating free-form explanations for gaps and inaccuracies |
| Study - short-answer evaluation | Sonnet | Evaluating open-ended responses requires reasoning |
| Study - remediation card generation | Sonnet (subagent) | Runs AFTER study session ends if weak areas were identified. Generates 5-10 targeted cards for next session. ~3,000-5,000 tokens, background. |
| Study - image-aware card generation | Sonnet (`/study-gen`) | Runs at INGESTION TIME. Generates identification questions (stripped image) and analysis questions (labeled image) from extracted diagrams. |
| Study - diagram Direction B (identify/analyze) | **Kiosk (0 tokens per question)** | `/s/{id}/diagrams`. Shows stripped/labeled diagram images alongside questions. Identification and analysis modes. |
| Study - diagram Direction A (recall) | Sonnet | Conversational. Vision evaluates user's uploaded drawing against original. |
| Study - diagram Direction C (reproduction) | Kiosk + Sonnet | Kiosk shows the diagram on a timer and takes the photo upload; Sonnet + vision compares your reproduction. |
| Image classification (fallback chain) | Haiku | Steps 1-4 of fallback chain are cheap. Step 5 (ask user) is ~500 tokens. Only escalate to Sonnet for complex PDFs with image extraction. |
| Document image extraction | Marker (local) + Sonnet vision per figure | Marker cuts figures out locally; Sonnet only describes the figures, never whole pages. |
| Stripped image generation | None | `surya_detect` boxes + ImageMagick + a local `qwen3-vl:8b-instruct` check. Zero Claude tokens. |
| Habit Tracker (tracking) | Haiku | JSON updates, streak calculations. Trivial. |
| Habit Tracker (creation/adaptation) | Sonnet | Generating onboarding plans, suggesting adaptations, proactive habit suggestions. Runs rarely. |
| Habit dashboard | **Kiosk (0 tokens)** | `/habits` reads `habits.json` directly. |
| Health dashboard | **Kiosk (0 tokens)** | `/health` reads `health-history.json` directly. |
| Kiosk server | None | FastAPI + static pages. Zero Claude tokens; reads and writes vault files itself. |
| Health Data collection | None | Python scripts + cron. Zero Claude tokens. |
| Health Data analysis | Haiku | Reads merged health JSON, generates predicted_energy and one-line summary. ~1,000 tokens daily. |
| Dynamic Scheduler (generation) | Haiku | Reads cached calendar + tasks + health + habits. Generates time-blocked plan. ~3,000 tokens. |
| Dynamic Scheduler (rescheduling) | Haiku | Reads today.json, applies the change, runs `push-schedule.sh`. ~1,500 tokens per adaptation. |
| Dynamic Scheduler (weekly plan) | Sonnet | Generates 7-day lookahead. Runs once weekly. ~5,000 tokens. |
| Calendar cache sync + push | None | `calendar-sync.sh` and `push-schedule.sh` via gws. Zero Claude tokens. |
| Local pre-processing (reading) | None (local) | `qwen3-vl:8b-instruct` reads images, handwriting and handwritten PDFs; Marker converts typed documents. Zero Claude tokens. |
| Local pre-processing (classification, summaries) | None (local) | `qwen3.5:9b` classifies files, identifies courses, proposes topics and writes summaries. Zero Claude tokens. |
| Topic matching Step 5 | None (local) | `qwen3-embedding:0.6b` similarity. Zero Claude tokens. |
| Lecture speech-to-text | None (local) | Granite Speech 4.1 2B with course keywords (2.3). Zero Claude tokens. |
| Task duration tracking | Haiku (piggybacks on Distributor) | ~200 extra tokens per "done" invocation. Reads/writes task-timing.json. |
| Exam Countdown (activation) | Haiku | Date comparison + review plan generation. Runs once per exam. |
| Exam Countdown (review plan) | Sonnet | Generates 7-day topic-distributed review plan. ~3,000 tokens, once per exam. |
| Explain My Week summary | Sonnet | Weekly synthesis across all system data. ~5,000 tokens. Runs once weekly. |
| Explain My Week audio (optional) | None (local Kokoro) | Zero tokens and no API bill. |
| Seeker | Sonnet | Synthesis across notes requires reasoning |
| Scribe | Haiku | Note capture and formatting is straightforward |
| Sorter | Haiku | Filing decisions are rule-based |
| Connector | Sonnet | Finding non-obvious links requires reasoning |
| Librarian | Opus upstream (`high`) | Upstream ships it on `high`. Run it monthly, or set it to `mid` in your fork (0.12). |
| Architect | Opus upstream (`high`) | Same. Mostly runs at setup and for `/defrag`, `/create-agent`. |
| Postman (email triage) | Haiku | Sender + subject classification is trivial. Only escalates to Sonnet for Tier 1 full-body parsing if needed. |
| Transcriber | Sonnet | Cleanup and structuring of transcripts |
| Campaign Manager (GM: debrief, world sim, prep) | Sonnet | Narrative reasoning, world simulation |
| Campaign Manager (player: sheet, quest log, recap) | Haiku (forked `/campaign-log`) | Updating structured notes |
| Morning Briefing | Haiku | Aggregation, not reasoning |
| Pre-lecture Prep | Haiku | Simple retrieval and summary |
| Grade Tracker | Haiku | Math |
| Research Radar | Sonnet + web search | Research requires reasoning about relevance |
| Weekly Synthesis | Sonnet | Cross-course connection finding |
| Trello Sync (poll + push) | None | Two curl scripts on the Trello API. Zero Claude tokens. |
| Trello Sync (new phone card -> task note) | Haiku | Only when you create a card on your phone. |

### 5.3 -- Vault Health Monitoring

**When:** Monthly
**Existing resource:** Upstream now ships these as skills -- use them, don't build your own: `/vault-audit` ("vault audit" or "weekly review": 7 phases, including duplicates, broken links, frontmatter, MOCs, and a check that every custom agent in the registry has its file), `/deep-clean` (adds stale content and template compliance), `/tag-garden` (unused and near-duplicate tags), `/defrag` (structure, MOC refresh).
**Token tip:** Upstream sets the Librarian and Architect to the `high` (Opus) tier. These are the most expensive calls in the system, so run them monthly, not weekly (see 0.12 on switching them to `mid`).
**Steps:**

- [ ] Say "vault audit" and check its report for:
  - Orphan notes (notes with no links or tags)
  - Duplicate content
  - Stale tasks (marked `ready` but untouched for 2+ weeks -- should they be deprioritized?)
  - Empty folders
- [ ] Every few months: "tag garden" and "defragment the vault"
- [ ] Review energy logs for patterns
- [ ] Review grade projections
- [ ] Review research radar digest -- are the searches finding useful content?

---

## QUICK REFERENCE: BUILD ORDER

### Before class starts (2 days):
1. 0.0 -- Windows host: WSL2 Ubuntu with mirrored networking and systemd, Linux toolchain, Ollama + Tailscale on Windows, no sleep
2. 0.1 -- Fork the repo, create the `jacob` branch, run `launchme.sh`, run `/onboarding` (fills `Meta/user-profile.md`, including your email VIPs)
3. 0.2 -- Set up gws with your own Google Cloud OAuth app (Gmail + Calendar). Test the university account first; if it's blocked, use the forwarding fallback
4. 0.5 -- Set up Canvas iCal feed in Google Calendar
5. 0.6 -- Git backup (cron, takes 5 minutes)
6. 0.9 -- Remote Control in tmux (`remote-control.sh`) + `boot.sh` and the Task Scheduler startup task (0.0); Tailscale on the phone
7. 0.10 -- Create the `Meta/events/` folders (background event inbox)
8. 0.12 -- Add the JACOB block to your fork's `DISPATCHER.md`, write `.claude/settings.local.json`, re-run `updateme.sh` so the vault's CLAUDE.md picks it up
9. 1.3 -- Distributor agent (basic version: energy + time filtering)
10. Manually add syllabi and known assignments to vault

### Week 1:
11. 0.3 -- Google Drive sync pipeline (with 3 AM batch + immediate-exception file watcher)
12. 0.11 -- Local pre-processing pipeline: venv with Marker + Surya, pull `qwen3-vl:8b-instruct`, `qwen3.5:9b`, `qwen3-embedding:0.6b`, set up local-preprocess.py, **run the 10-page handwriting test**
13. 1.1 -- Ingestion pipeline agent (classify + file + smart classification fallback chain + image-categories.json + **reads .meta.json from local pre-processing**) + topic taxonomy + generation subagent with Topic Matching Protocol + Image-Aware Generation
14. 1.2 -- Decomposer agent (break down first real assignments)
15. 0.8 -- Write our agents lean, add `summarize-missing.py` to the 3 AM batch (measure upstream prompts later, trim only what's hot)
16. 4.1 -- Install notebooklm-py (CLI + skill), sign in, create course notebooks
17. 3.3 (push half) -- `trello-push.sh` + Trello board + phone widget (one-way push first)

### Week 2:
18. 1.3 iteration -- Add task duration tracking to Distributor (task-timing.json, ratio-based estimate correction)
19. 0.13 -- Kiosk skeleton + `/review` with delete/edit/flag (FastAPI, FSRS-6 server-side, `review-state/` + `card-edits/`, `tailscale serve`). Build this before the study skill, so cards have somewhere to go
20. 2.2a -- Study skill: flashcard generator + card format + **Kiosk `/s/{id}/flashcards`**
21. 2.2b -- Study skill: quiz/practice problem generator + **Kiosk `/s/{id}/quiz`**
22. 2.2k -- Study skill: session orchestrator (brain dump + mode selection + Kiosk deck specs + self-assessment + forked `/study-log` on Haiku)
23. 2.3 -- Lecture audio transcription pipeline (Granite Speech 4.1 with course keywords)
24. 2.1 -- Pre-lecture prep (cron trigger)
25. 2.4 -- Grade tracker (enter grading weights from syllabi)
26. 1.1 iteration -- Connect ingestion pipeline to NotebookLM auto-upload

### Week 3-4:
27. 0.7 -- Event-driven trigger system (inotifywait on `drive-inbox/` and `Meta/events/*/`; cron from `schedule.conf`)
28. 3.3 -- Trello bidirectional sync (add the polling script for phone -> vault updates)
29. 2.2c -- Study skill: Socratic dialogue mode (with NotebookLM notebook querying)
30. 2.2d -- Study skill: teach-it-back mode
31. 2.2f -- Interleaving strategy: add first_studied tracking to topics.json + have the Kiosk load multi-topic decks when `interleave` is set
32. 2.2l -- Study skill: periodic study recommendations (Distributor integration)
33. 2.5 -- Weekly synthesis (Friday cron)
34. 3.2 -- Morning briefing (7 AM cron) + Kiosk `/today`
35. Install premade skills: 4.2-4.6, 4.9

### Month 2+:
36. 3.1 -- Campaign Manager skill (register every campaign, GM or player)
37. 2.6 -- Research Radar
38. 3.6 -- Grad School Tracking
39. 2.2g -- Study skill: calibration tracking
40. 2.2h -- Study skill: diagram interaction mode (all 3 directions + stripped image generation + Kiosk `/s/{id}/diagrams` for Direction B)
41. 2.2i -- Study skill: derive-it-don't-memorize-it mode (Kiosk `/s/{id}/derive`)
42. 3.7 -- Rest & Health monitor (basic: energy logging + rest detection)
43. 2.2e -- Generation effect prompting
44. 2.7 -- Exam Countdown Mode (Distributor + Study Skill + Morning Briefing coordination)
45. 0.13 iteration -- Kiosk `/upload` (phone photos straight into `drive-inbox/`)

### Month 3+ (Life Systems):
46. 3.9 -- Health Data Integration: Oura API + Samsung Health Connect + merge script + wake detection script + predicted_energy
47. 3.7 iteration -- Upgrade Rest Monitor with HRV trends and stress data from 3.9
48. 3.8 -- Habit Tracker: creation, tracking, streaks, morning briefing integration, Distributor integration
49. 3.8 iteration -- Connect habit auto-detection from health data (gym auto-log from elevated HR)
50. 3.8 iteration -- Proactive habit suggestions based on sleep/energy/study patterns
51. 3.8 iteration -- Kiosk `/habits` page, then one-tap check-ins
52. 3.9 iteration -- Kiosk `/health` page
53. 3.10 -- Dynamic Scheduling: `calendar-sync.sh` cache, `/schedule` daily generation, `push-schedule.sh` to Google Calendar
54. 3.10 iteration -- Auto-wake trigger from health data -> automatic schedule generation
55. 3.10 iteration -- Rescheduling on user reports ("I have dinner at 6")
56. 3.10 iteration -- Week-ahead plan (Sunday evening Sonnet generation)
57. 3.10 iteration -- Travel time estimation between locations
58. 3.10 iteration -- Connect exam countdown to auto-block study time
59. 3.10 iteration -- Connect task duration tracking to scheduler block durations
60. 3.11 -- Explain My Week summary (Sunday cron)
61. 3.11 iteration -- Optional TTS audio version
62. 5.1 -- Token usage audit
63. 5.2 -- Model assignment optimization

---

## GLOBAL TOKEN OPTIMIZATION RULES

Apply these everywhere, to every agent and skill:

1. **Grep before reading.** Never `view` a full file. Always `grep -n "keyword" file.md` first, then `view` only the matching line range.

2. **Frontmatter first.** Every agent that reads notes should check YAML frontmatter `summary:` field before loading content. If the summary answers the question, stop there.

3. **Haiku by default.** Only use Sonnet for tasks requiring genuine reasoning (synthesis, generation, narrative). Use Haiku for everything mechanical (classification, math, status updates, simple retrieval).

4. **Cache aggressively.** If an agent generates a summary, save it to the note. Don't regenerate. Study cards are generated once and stored in JSON, not regenerated per review session.

5. **Event-driven > polling.** Use `inotifywait`/cron for triggers. Reserve `/loop` only for things you're actively interacting with.

6. **Short agent prompts.** Target 500 words per agent prompt. Every word loads on every invocation.

7. **Batch operations.** If multiple notes need processing, have the agent process them in a single invocation rather than one call per note.

8. **Don't load what you won't use.** If Distributor only needs task metadata, it reads frontmatter only. If Seeker only needs to find which notes mention "Fourier," it greps across files, not reads them all.

9. **Structured output > prose.** Agents that communicate with other agents should write JSON/YAML to shared files, not natural language paragraphs. Shorter to write, shorter to parse.

10. **Exit early.** If an agent determines in step 1 that there's nothing to do (no new files, no pending tasks, etc.), it should stop immediately, not continue checking.

11. **Use /compact in long sessions.** Any interactive session exceeding 15 minutes or 15 turns should be compacted. This prevents the quadratic cost problem where each turn re-reads all prior turns. Claude can't run `/compact` itself, so skills save their state and ask you to type it at natural breaks (study mode transitions). One-shot skills avoid the problem entirely by running forked (rule 13).

12. **Separate cheap sessions from expensive sessions.** Standalone flashcard review runs in the Kiosk (`/review`, 0 tokens, no Claude involved). Full study sessions with Socratic/teach-back run in Sonnet conversationally. Don't use Sonnet conversational mode for anything the Kiosk can do.

13. **Pin models where they're reliable: agents and forked skills.** The vault defaults to Sonnet (Claude Code on Pro would otherwise use Opus). Agents take `model:` from their frontmatter. One-shot skills use `context: fork` + `model:` + `effort: low`, which runs them in their own subagent on that model and keeps their working context out of your session. Don't rely on inline `/model` switching inside a conversational skill -- it isn't reliable (0.12).

14. **Prefer the Kiosk over conversational modes for repetitive interactions.** Any mode where the interaction is "show prompt, get response, evaluate, repeat" (flashcards, MC quizzes, formula practice, diagram identification) belongs in the Kiosk, which also saves the results. Reserve conversational mode for interactions that genuinely need Claude's reasoning on each turn (Socratic, teach-back, open-ended evaluation).

15. **Cache external data locally.** Never read Google Calendar, email, or health APIs during a Claude invocation. Use cron scripts (zero tokens) to sync external data to local JSON files on a schedule. Claude reads the local cache. This applies to: calendar events (sync every 4 hours), health data (sync daily at wake), email (`/email-triage` runs 2x/day on schedule). When YOU create a new event, Claude writes the local cache and `today.json`; `push-schedule.sh` pushes it -- never read-then-write, and Claude never calls the calendar itself.

16. **Pre-compute derived data.** Predicted energy levels, habit streak counts, grade projections, exam countdowns -- all of these can be calculated by cheap scripts at sync time and stored in JSON files. Claude reads the pre-computed value instead of re-calculating from raw data each time.

17. **Run local pre-processing before Claude touches any file.** Marker turns documents into Markdown with LaTeX equations and cut-out figures. A local vision model reads images and handwriting, and a local text model classifies files and writes summaries. By the time Claude sees a file, the .meta.json and .extracted.md already hold the text, classification, course guess and topic candidates, and Claude looks at pixels only for diagrams and flagged pages. This alone saves ~25,000-30,000 tokens on a typical day of note ingestion.

18. **Batch file processing at 3 AM.** Queue non-urgent files during the day (zero tokens). Process them all in one Claude invocation at 3 AM (shared context, and it spends a usage window you're asleep for). Only process files immediately if they're time-sensitive (assignments due this week, urgent tags). On-demand processing available via "process my uploads" if you need materials before 3 AM ("triage the inbox" is upstream's `/inbox-triage`, which files notes, not uploads).

19. **Track task durations to improve estimates.** Every completed task logs actual vs estimated time. The ratio feeds back into the Decomposer (better future estimates) and Dynamic Scheduler (more accurate block durations). Costs ~200 tokens per task completion, saves thousands by preventing over/under-scheduled days.

20. **Customize in the fork, register in one block.** Our agents, skills and triggers go in `personal/` and the JACOB block of `DISPATCHER.md` (0.12), never in core agents. Updates overwrite core files; the block and `personal/` survive merges, and nothing in the main session gets refused as "does not exist."

21. **Scripts do the plumbing.** Calendar sync and push, health merges, Drive sync, summaries (Ollama) and the Kiosk are all scripts or local servers. Claude reads their output files and never holds an API connection open.
