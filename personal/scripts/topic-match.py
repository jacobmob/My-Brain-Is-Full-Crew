#!/home/jacob/.venvs/brain/bin/python
# topic-match.py -- Topic Matching Protocol, Step 5 (semantic fuzzy match), zero Claude tokens
# Usage: topic-match.py "<candidate>" [more candidates...] --course EE202
# Embeds each candidate with qwen3-embedding:0.6b and compares it against every topic's
# display_name + aliases. Topic embeddings are cached in <course>/topics.embeddings.json
# and refreshed when topics.json changes. Prints JSON: best topic, score and verdict.

import argparse, hashlib, json, math
from pathlib import Path
import ollama

STUDY = Path.home() / "brain-vault/03-Resources/study"
MODEL = "qwen3-embedding:0.6b"
MATCH, CONFIRM = 0.85, 0.75   # >= MATCH: match; CONFIRM-MATCH: read 3 cards to confirm; below: none

def embed(texts):
    return ollama.embed(model=MODEL, input=texts)["embeddings"] if texts else []

def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    return dot / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)) or 1)

def topic_vectors(course_dir):
    """Return {slug: [(text, vector), ...]}, re-embedding only when topics.json changed."""
    raw = (course_dir / "topics.json").read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    cache_path = course_dir / "topics.embeddings.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    if cache.get("topics_sha256") == digest and cache.get("model") == MODEL:
        return {s: list(zip(t["texts"], t["vectors"])) for s, t in cache["topics"].items()}

    topics = (json.loads(raw) or {}).get("topics", {})
    known = {}                                   # reuse vectors for unchanged strings
    for t in cache.get("topics", {}).values() if cache.get("model") == MODEL else []:
        known.update(zip(t["texts"], t["vectors"]))
    texts = {s: list(dict.fromkeys([t.get("display_name") or s, *t.get("aliases", [])]))
             for s, t in topics.items()}
    missing = sorted({x for ts in texts.values() for x in ts} - known.keys())
    known.update(zip(missing, embed(missing)))

    cache = {"model": MODEL, "topics_sha256": digest,
             "topics": {s: {"texts": ts, "vectors": [known[x] for x in ts]} for s, ts in texts.items()}}
    cache_path.write_text(json.dumps(cache))
    return {s: list(zip(t["texts"], t["vectors"])) for s, t in cache["topics"].items()}

def main():
    ap = argparse.ArgumentParser(description="Topic Matching Step 5: semantic fuzzy match")
    ap.add_argument("candidates", nargs="+")
    ap.add_argument("--course", required=True)
    args = ap.parse_args()

    course_dir = STUDY / args.course
    if not (course_dir / "topics.json").exists():
        raise SystemExit(f"No topics.json for course {args.course} in {STUDY}")
    topics = topic_vectors(course_dir)

    best = {"topic": None, "matched_text": None, "candidate": None, "score": 0.0}
    for cand, vec in zip(args.candidates, embed(args.candidates)):
        for slug, pairs in topics.items():
            for text, tvec in pairs:
                score = cosine(vec, tvec)
                if score > best["score"]:
                    best = {"topic": slug, "matched_text": text, "candidate": cand, "score": round(score, 4)}

    s = best["score"]
    best["verdict"] = "match" if s >= MATCH else "confirm" if s >= CONFIRM else "none"
    if best["verdict"] == "none":
        best["topic"] = None
    print(json.dumps(best, indent=2))

if __name__ == "__main__":
    main()
