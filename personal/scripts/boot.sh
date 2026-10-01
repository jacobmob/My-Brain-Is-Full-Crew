#!/bin/bash
S=~/brain-vault/My-Brain-Is-Full-Crew/personal/scripts
start() { tmux has-session -t "$1" 2>/dev/null || tmux new -d -s "$1" "$2"; }
start brain "$S/remote-control.sh"
start watchers "$S/watch-drive-inbox.sh & $S/watch-events.sh; wait"    # 0.3, 0.10
start kiosk "$S/kiosk.sh"                                                # 0.13
