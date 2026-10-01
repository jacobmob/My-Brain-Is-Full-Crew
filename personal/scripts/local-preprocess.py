#!/home/jacob/.venvs/brain/bin/python
# local-preprocess.py -- zero Claude tokens
# For each queued file: extract text (Marker for documents, the local vision
# model for images), classify locally, and write <file>.extracted.md + <file>.meta.json

import sys, json, subprocess, shutil, tempfile
from pathlib import Path
import ollama

VAULT = Path.home() / "brain-vault"
VISION, TEXT = "qwen3-vl:8b-instruct", "qwen3.5:9b"  # the thinking qwen3-vl:8b loops on dense handwriting
DOCS = {".pdf", ".pptx", ".docx", ".xlsx", ".html", ".epub"}
IMAGES = {".png", ".jpg", ".jpeg", ".webp"}
# Handwritten PDFs are read page by page by the vision model instead of Marker. Checks, cheapest first:
HANDWRITTEN_PDF_APPS = ("OneNote", "MyScript", "Nebo")  # 1. Creator/Producer is a note-taking app
TEXT_LAYER_HANDWRITTEN = 100    # 2. under this many text-layer chars/page: handwritten (or scanned)
TEXT_LAYER_TYPED = 500          #    at least this many: typed. In between: 3. vision model checks page 1
LOCAL_HANDWRITING = True        # False = all handwriting goes to Claude vision (old behavior)
TRUST_HANDWRITTEN_MATH = False  # flip to True once your own equations transcribe correctly
UNSURE_LIMIT = 0.02             # more than 2% of words marked [?] -> Claude checks the image

READ_PROMPT = ("Transcribe all text in this image exactly, as Markdown. Write math as LaTeX "
               "($...$). Write [?] in place of any word you cannot read confidently.")
# The transcript is asked for as plain Markdown: inside a JSON string (with every LaTeX
# backslash escaped) the vision model falls into repeat loops. Type and diagram are a second call.
TYPE_PROMPT = "Is the text in this image typed, handwritten, mixed, or is there none? Does it contain a diagram, schematic, graph or chart?"
TYPE_SCHEMA = {"type": "object", "required": ["text_type", "has_diagram"],
    "properties": {"text_type": {"enum": ["typed", "handwritten", "mixed", "none"]},
                   "has_diagram": {"type": "boolean"}}}
OPTIONS = {"temperature": 0, "num_ctx": 16384, "num_predict": 4096, "repeat_penalty": 1.05}

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

def ask(model, prompt, schema, image=None, **kw):
    msg = {"role": "user", "content": prompt}
    if image:
        msg["images"] = [image]
    if model == TEXT:
        kw["think"] = False  # qwen3.5 thinks by default and can fill the output budget before answering
    r = ollama.chat(model=model, messages=[msg], format=schema, options=OPTIONS, **kw)
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
    msg = {"role": "user", "content": READ_PROMPT, "images": [str(path)]}
    transcript = ollama.chat(model=VISION, messages=[msg], options=OPTIONS)["message"]["content"]
    r = ask(VISION, TYPE_PROMPT, TYPE_SCHEMA, image=str(path))
    return transcript, {"text_type": r["text_type"], "has_diagram": r["has_diagram"],
                        "extracted_images": []}

def pdf_route(path):
    """Return ("vision" | "marker", reason). Runs before Marker, so check 3 unloads its model."""
    info = subprocess.run(["pdfinfo", str(path)], capture_output=True, text=True).stdout
    made_by = " ".join(l for l in info.splitlines() if l.startswith(("Creator:", "Producer:")))
    app = next((a for a in HANDWRITTEN_PDF_APPS if a.lower() in made_by.lower()), None)
    if app:
        return "vision", f"made by {app}"
    pages = int(next((l.split()[1] for l in info.splitlines() if l.startswith("Pages:")), 1))
    text = subprocess.run(["pdftotext", str(path), "-"], capture_output=True, text=True).stdout
    per_page = len("".join(text.split())) // max(1, pages)
    if per_page < TEXT_LAYER_HANDWRITTEN:
        return "vision", f"text layer {per_page} chars/page"
    if per_page >= TEXT_LAYER_TYPED:
        return "marker", f"text layer {per_page} chars/page"
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["pdftoppm", "-r", "100", "-png", "-f", "1", "-l", "1", "-singlefile",
                        str(path), f"{tmp}/p1"], check=True)
        r = ask(VISION, TYPE_PROMPT, TYPE_SCHEMA, image=f"{tmp}/p1.png", keep_alive=0)
    route = "vision" if r["text_type"] in ("handwritten", "mixed") else "marker"
    return route, f"text layer {per_page} chars/page, page 1 looks {r['text_type']}"

def read_pdf_pages(path):
    """Render each page to <stem>_pages/page-N.png and read it with the vision model.
    The page images stay, so Claude can check [?] words and math against the page."""
    pages = path.parent / f"{path.stem}_pages"
    pages.mkdir(exist_ok=True)
    subprocess.run(["pdftoppm", "-r", "150", "-png", str(path), str(pages / "page")], check=True)
    images = sorted(pages.glob("page-*.png"))
    texts, types, has_diagram = [], set(), False
    for img in images:
        text, info = read_image(img)
        texts.append(f"<!-- {img.name} -->\n{text}")
        types.add(info["text_type"])
        has_diagram |= info["has_diagram"]
    types.discard("none")
    text_type = types.pop() if len(types) == 1 else "mixed" if types else "none"
    return "\n\n".join(texts), {"text_type": text_type, "has_diagram": has_diagram,
                                "extracted_images": [], "page_images": [str(i) for i in images]}

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

def preprocess(path, courses, converted, routes):
    ext = path.suffix.lower()
    if path in converted:
        text, info = converted[path]
    elif ext == ".pdf":
        text, info = read_pdf_pages(path)
    elif ext in IMAGES:
        text, info = read_image(path)
    else:
        text, info = path.read_text(errors="ignore"), {"text_type": "typed", "has_diagram": False,
                                                        "extracted_images": []}
    c = ask(TEXT, CLASSIFY_PROMPT.format(courses=courses, name=path.name, text=text[:4000]),
            CLASSIFY_SCHEMA)
    Path(f"{path}.extracted.md").write_text(text)
    meta = {"original_file": str(path), "extracted_text_path": f"{path}.extracted.md",
            **info, **({"pdf_route": routes[path]} if path in routes else {}), **c, "unsure_words": text.count("[?]"),
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
    # Pass 0: decide which PDFs are handwritten (vision model) and which are typed (Marker)
    routes = {f: " -- ".join(pdf_route(f)) for f in files if f.suffix.lower() == ".pdf"}
    # Pass 1: every typed document through Marker at once (GPU: vLLM server, then released)
    converted = convert_documents([f for f in files if f.suffix.lower() in DOCS
                                   and not routes.get(f, "").startswith("vision")])
    # Pass 2: images, handwritten PDFs and classification through Ollama (GPU: one model at a time)
    for f in files:
        preprocess(f, courses, converted, routes)
        print(f"  pre-processed: {f.name}")

if __name__ == "__main__":
    main()
