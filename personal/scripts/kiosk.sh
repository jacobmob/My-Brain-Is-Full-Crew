#!/bin/bash
# kiosk.sh -- blueprint 0.13. Serves the Kiosk on 127.0.0.1:8484, restarting if it dies.
# Tailscale on Windows publishes it to the tailnet (tailscale serve --bg 8484).
export PATH="$HOME/.local/bin:$HOME/.venvs/brain/bin:$PATH"
VAULT="$HOME/brain-vault"
LOG="$VAULT/Meta/logs/kiosk.log"
mkdir -p "$(dirname "$LOG")"
cd "$VAULT/My-Brain-Is-Full-Crew/personal/kiosk" || exit 1

while true; do
  echo "$(date '+%F %T') kiosk starting" >> "$LOG"
  uvicorn app:app --host 127.0.0.1 --port 8484 --no-access-log >> "$LOG" 2>&1
  echo "$(date '+%F %T') kiosk exited ($?), restarting in 5s" >> "$LOG"
  sleep 5
done
