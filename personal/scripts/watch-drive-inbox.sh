#!/bin/bash
# watch-drive-inbox.sh -- blueprint 0.3 / 0.7
# QUEUE by default, IMMEDIATE only for time-sensitive files.
# Zero tokens until either an urgent file arrives or the 3 AM batch fires.
export PATH="$HOME/.local/bin:$HOME/.venvs/brain/bin:$PATH"
VAULT="$HOME/brain-vault"
WATCH_DIR="$VAULT/drive-inbox"
QUEUE="$VAULT/Meta/ingestion-queue.txt"
SCRIPTS="$VAULT/My-Brain-Is-Full-Crew/personal/scripts"
PY="$HOME/.venvs/brain/bin/python"
LOG="$VAULT/Meta/logs/watch.log"
mkdir -p "$WATCH_DIR" "$(dirname "$LOG")"

inotifywait -m -q -e close_write -e moved_to --format '%w%f' "$WATCH_DIR" | while read -r event; do
  FILENAME=$(basename "$event")
  [ -d "$event" ] && continue   # <stem>_marker/ and <stem>_pages/ from local pre-processing
  case "$FILENAME" in *.partial|.*|*.extracted.md|*.meta.json) continue ;; esac

  if echo "$FILENAME" | grep -qiE "assignment|urgent|due|exam|quiz"; then
    # Urgent: pre-process just this file locally, then ingest it now.
    # Unattended runs can't answer permission prompts: Bash follows the allowlist in
    # .claude/settings.local.json (0.12); acceptEdits lets it write notes.
    echo "$(date '+%F %T') urgent: $event" >> "$LOG"
    ONE=$(mktemp)
    echo "$event" > "$ONE"
    "$PY" "$SCRIPTS/local-preprocess.py" --queue "$ONE" < /dev/null >> "$LOG" 2>&1
    rm -f "$ONE"
    (cd "$VAULT" && claude --model haiku --permission-mode acceptEdits --print \
      "Today: $(date +%F). Process urgent file: $event using the ingestion agent. Read its .meta.json first (from local pre-processing).") < /dev/null >> "$LOG" 2>&1
    echo "$(date '+%F %T') urgent done: $FILENAME" >> "$LOG"
  else
    echo "$event" >> "$QUEUE"
    echo "$(date '+%F %T') queued: $event" >> "$LOG"
  fi
done
