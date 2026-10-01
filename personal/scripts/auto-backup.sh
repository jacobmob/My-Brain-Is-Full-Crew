#!/bin/bash
cd ~/brain-vault
git add -A
git diff --cached --quiet || git commit -q -m "auto-backup $(date +%Y-%m-%d-%H%M)"
git push -q origin main
