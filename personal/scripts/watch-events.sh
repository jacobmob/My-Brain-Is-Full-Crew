#!/bin/bash
# watch-events.sh -- blueprint 0.10
# Only the scheduler folder triggers immediately; other consumers read their folder on their next run.
export PATH="$HOME/.local/bin:$HOME/.venvs/brain/bin:$PATH"
VAULT="$HOME/brain-vault"
LOG="$VAULT/Meta/logs/watch.log"
mkdir -p "$VAULT"/Meta/events/{distributor,ingestion,scheduler,study-skill,habits,processed} "$(dirname "$LOG")"

inotifywait -m -q -e close_write -e moved_to --format '%w%f' "$VAULT/Meta/events/scheduler/" | while read -r event; do
  sleep 5   # debounce bursts from one sync
  echo "$(date '+%F %T') scheduler event: $event" >> "$LOG"
  (cd "$VAULT" && claude --model haiku --print \
    "Scheduler: apply pending events in Meta/events/scheduler/ to today's plan.") < /dev/null >> "$LOG" 2>&1
done
