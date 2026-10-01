#!/home/jacob/.venvs/brain/bin/python
# summarize-missing.py -- blueprint 0.8, zero Claude tokens
# Finds notes over 200 words with no summary: field and writes a 2-3 sentence
# summary: into their frontmatter using the local text model.

import argparse, json, re
from pathlib import Path
import ollama

MODEL = "qwen3.5:9b"
MIN_WORDS = 200
SKIP_DIRS = {".claude", ".git", ".obsidian", ".trash", "My-Brain-Is-Full-Crew", "drive-inbox", "Meta"}
PROMPT = ("Summarize this note in 2-3 plain sentences (under 60 words) so someone can tell "
          "what it contains without opening it. Reply with the summary only.\n\n"
          "Title: {title}\n\n{text}")
FRONT = re.compile(r"\A---\n(.*?)\n---\n?", re.S)

def skipped(path, vault):
    parts = path.relative_to(vault).parts[:-1]
    if path.name.startswith("CLAUDE"):  # dispatcher and its backups, installed from the fork
        return True
    return any(p in SKIP_DIRS or p.lower().endswith("templates") for p in parts)

def summarize(title, text):
    r = ollama.chat(model=MODEL, think=False, options={"temperature": 0.2, "num_ctx": 8192},
                    messages=[{"role": "user", "content": PROMPT.format(title=title, text=text[:12000])}])
    return " ".join(r["message"]["content"].split())

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", default=str(Path.home() / "brain-vault"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    vault, dry = Path(args.vault), args.dry_run
    done = 0
    for path in sorted(vault.rglob("*.md")):
        if skipped(path, vault):
            continue
        raw = path.read_text(errors="ignore")
        m = FRONT.match(raw)
        front, body = (m.group(1), raw[m.end():]) if m else (None, raw)
        if front is not None and re.search(r"^summary:", front, re.M):
            continue
        if len(body.split()) <= MIN_WORDS:
            continue
        if dry:
            print(f"  would summarize: {path.relative_to(vault)}")
            continue
        try:
            s = summarize(path.stem, body)
        except Exception as e:
            print(f"  failed: {path.relative_to(vault)}: {e}")
            continue
        line = f"summary: {json.dumps(s, ensure_ascii=False)}"
        new = (f"---\n{line}\n{front}\n---\n{body}" if front is not None
               else f"---\n{line}\n---\n\n{body}")
        path.write_text(new)
        done += 1
        print(f"  summarized: {path.relative_to(vault)}")
    print(f"summarize-missing: {done} notes updated")

if __name__ == "__main__":
    main()
