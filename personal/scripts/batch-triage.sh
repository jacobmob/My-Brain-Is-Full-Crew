#!/bin/bash
# batch-triage.sh -- blueprint 0.3: the 3 AM batch. Processes all queued work in as few sessions as possible.
# crontab: 0 3 * * * <path>/batch-triage.sh >> $HOME/brain-vault/Meta/logs/batch.log 2>&1
export PATH="$HOME/.local/bin:$HOME/.venvs/brain/bin:/usr/local/bin:/usr/bin:/bin"
VAULT="$HOME/brain-vault"
SCRIPTS="$VAULT/My-Brain-Is-Full-Crew/personal/scripts"
PY="$HOME/.venvs/brain/bin/python"   # the venv with Marker, Ollama client, fsrs (0.11)
QUEUE="$VAULT/Meta/ingestion-queue.txt"
TODAY=$(date +%F)
cd "$VAULT" || exit 1   # CLAUDE.md (the dispatcher) and .claude/ only load from the vault root
echo "=== batch-triage $(date '+%F %T') ==="

# Step 1: Ingest queued uploads (skipped if queue is empty)
if [ -f "$QUEUE" ] && [ -s "$QUEUE" ]; then
  FILE_COUNT=$(wc -l < "$QUEUE")
  echo "Step 1: processing $FILE_COUNT queued files..."

  # Local GPU work first, one job at a time (zero tokens -- 0.11):
  # speech-to-text for audio (2.3), then Marker + the local models
  grep -iE '\.(m4a|mp3|wav)$' "$QUEUE" | while read -r f; do "$SCRIPTS/transcribe-local.sh" "$f"; done
  "$PY" "$SCRIPTS/local-preprocess.py" --queue "$QUEUE"

  # Single Claude invocation processes all pre-processed files
  claude --model sonnet --permission-mode acceptEdits --print \
    "Today: $TODAY. Use the ingestion agent on every file listed in Meta/ingestion-queue.txt \
     as one batch. For each file, read its .meta.json first (from local \
     pre-processing). Run the full ingestion pipeline including study material \
     generation using the Topic Taxonomy system. Delete the queue file when done."

  # Cleanup
  [ -f "$QUEUE" ] && rm "$QUEUE"
else
  echo "Step 1: queue empty"
fi

# Step 1b: Add summary: frontmatter to long notes that lack one (local Ollama, zero tokens -- 0.8)
echo "Step 1b: summaries"
"$PY" "$SCRIPTS/summarize-missing.py" --vault "$VAULT"

# Step 1c: Break down Canvas assignments waiting for the Decomposer (breakdown: pending, from 0.5 Stage 2b).
# One run per assignment; breakdown: done is set only if new task notes appeared.
PENDING_BREAKDOWN=$(grep -rlE "^breakdown: pending" "$VAULT" --include=*.md \
            --exclude-dir=.claude --exclude-dir=My-Brain-Is-Full-Crew --exclude-dir=Templates 2>/dev/null)
echo "Step 1c: $(echo -n "$PENDING_BREAKDOWN" | grep -c .) assignments pending breakdown"
echo "$PENDING_BREAKDOWN" | while IFS= read -r note; do
  [ -n "$note" ] || continue
  tasks="$(dirname "$note")/tasks"
  before=$(ls "$tasks" 2>/dev/null | wc -l)
  claude --model sonnet --permission-mode acceptEdits --print \
    "Today: $TODAY. Use the decomposer agent to break down this assignment: ${note#$VAULT/}. \
     This is an unattended batch run: nobody can answer questions, so write the distributor event instead." < /dev/null
  after=$(ls "$tasks" 2>/dev/null | wc -l)
  if [ "$after" -gt "$before" ]; then
    sed -i 's/^breakdown: pending$/breakdown: done/' "$note"
    echo "  broke down: ${note#$VAULT/} ($((after - before)) tasks)"
  else
    echo "  no tasks written, left pending: ${note#$VAULT/}"
  fi
done

# Step 2: Generate study materials for academic notes that arrived another way
# (Scribe captures, /transcribe lecture notes). Catches anything with
# type: academic-notes | lecture-notes and no study_generated date.
# Zero-token grep first -- only calls Claude if something is pending.
PENDING=$(grep -rlE "^type: (academic-notes|lecture-notes)" "$VAULT" --include=*.md \
            --exclude-dir=.claude --exclude-dir=My-Brain-Is-Full-Crew --exclude-dir=Templates \
          | xargs -r grep -L "^study_generated:" 2>/dev/null)
if [ -n "$PENDING" ]; then
  echo "Step 2: study-gen for $(echo "$PENDING" | wc -l) notes"
  claude --model sonnet --permission-mode acceptEdits --print \
    "/study-gen -- Topic Matching Protocol -- for these notes, \
     then add study_generated: $TODAY to each note's frontmatter: $PENDING"
else
  echo "Step 2: no notes pending study-gen"
fi

# Step 2b: Rewrite study items you flagged in the Kiosk (skipped if none)
FLAGGED=$(grep -l '"type": *"card-flagged"' "$VAULT"/Meta/events/study-skill/*.json 2>/dev/null)
if [ -n "$FLAGGED" ]; then
  echo "Step 2b: rewriting flagged items"
  claude --model sonnet --permission-mode acceptEdits --print \
    "Rewrite the flagged study items in these events, following each note. Write each \
     rewrite as a new item with replaces: <old id> in the same topic file, then move \
     the events to Meta/events/processed/: $FLAGGED"
else
  echo "Step 2b: nothing flagged"
fi

# Step 3: File whatever is sitting in the vault inbox (replaces the old 5 PM
# evening triage). Uses the upstream /inbox-triage skill.
if [ -n "$(ls -A "$VAULT/00-Inbox" 2>/dev/null)" ]; then
  echo "Step 3: inbox triage"
  claude --model haiku --permission-mode acceptEdits --print "triage the inbox"
else
  echo "Step 3: inbox empty"
fi
echo "=== batch-triage done $(date '+%F %T') ==="
