#!/bin/bash
S=~/brain-vault/My-Brain-Is-Full-Crew/personal/scripts
start() { tmux has-session -t "$1" 2>/dev/null || tmux new -d -s "$1" "$2"; }
start brain "$S/remote-control.sh"
# Later: start kiosk "$S/kiosk.sh" and start watchers (blueprint 0.0)
