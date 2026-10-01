#!/home/jacob/.venvs/brain/bin/python
# local-preprocess.py -- zero Claude tokens
# For each queued file: extract text (Marker for documents, the local vision
# model for images), classify locally, and write <file>.extracted.md + <file>.meta.json

import sys, json, subprocess, shutil, tempfile
from pathlib import Path
import ollama

VAULT = Path.home() / "brain-vault"
VISION, TEXT = "qwen3-vl:8b", "qwen3.5:9b"
DOCS = {".pdf", ".pptx", ".docx", ".xlsx", ".html", ".epub"}
IMAGES = {".png", ".jpg", ".jpeg", ".webp"}
LOCAL_HANDWRITING = True        # False = all handwriting goes to Claude vision (old behavior)
TRUST_HANDWRITTEN_MATH = False  # flip to True once your own equations transcribe correctly
UNSURE_LIMIT = 0.02             # more than 2% of words marked [?] -> Claude checks the image

READ_PROMPT = ("Transcribe all text in this image exactly, as Markdown. Write math as LaTeX "
               "($...$). Write [?] in place of any word you cannot read confidently.")
READ_SCHEMA = {"type": "object", "required": ["transcript", "text_type", "has_diagram"],
    "properties": {"transcript": {"type": "string"},
                   "text_type": {"enum": ["typed", "handwritten", "mixed", "none"]},
                   "has_diagram": {"type": "boolean"}}}

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

def ask(model, prompt, schema, image=None):
    msg = {"role": "user", "content": prompt}
    if image:
        msg["images"] = [image]
    r = ollama.chat(model=model, messages=[msg], format=schema, options={"temperature": 0})
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
    r = ask(VISION, READ_PROMPT, READ_SCHEMA, image=str(path))
    return r["transcript"], {"text_type": r["text_type"], "has_diagram": r["has_diagram"],
                             "extracted_images": []}

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

def preprocess(path, courses, converted):
    ext = path.suffix.lower()
    if ext in DOCS:
        text, info = converted[path]
    elif ext in IMAGES:
        text, info = read_image(path)
    else:
        text, info = path.read_text(errors="ignore"), {"text_type": "typed", "has_diagram": False,
                                                        "extracted_images": []}
    c = ask(TEXT, CLASSIFY_PROMPT.format(courses=courses, name=path.name, text=text[:4000]),
            CLASSIFY_SCHEMA)
    Path(f"{path}.extracted.md").write_text(text)
    meta = {"original_file": str(path), "extracted_text_path": f"{path}.extracted.md",
            **info, **c, "unsure_words": text.count("[?]"),
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
    # Pass 1: every document through Marker at once (GPU: vLLM server, then released)
    converted = convert_documents([f for f in files if f.suffix.lower() in DOCS])
    # Pass 2: images and classification through Ollama (GPU: one model at a time)
    for f in files:
        preprocess(f, courses, converted)
        print(f"  pre-processed: {f.name}")

if __name__ == "__main__":
    main()
