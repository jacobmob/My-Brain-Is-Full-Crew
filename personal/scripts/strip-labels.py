#!/home/jacob/.venvs/brain/bin/python
# strip-labels.py -- Stripped Image Generation (1.1), zero Claude tokens
# Usage: strip-labels.py <diagram.png> [<out-stripped.png>]
# 1. surya_detect finds every text line (pixel-exact boxes)
# 2. ImageMagick paints background-colored rectangles over the padded boxes
# 3. qwen3-vl:8b checks: no text readable, diagram structure intact
# 4. On failure the stripped file is removed (caller uses the original only)
# Prints JSON: {"stripped": path | null, "boxes": n, "reason": ...}

import sys, json, subprocess, tempfile
from pathlib import Path
import ollama

VISION = "qwen3-vl:8b"
PAD = 4  # pixels around each detected text line

CHECK_PROMPT = ("This is a diagram with its text labels painted over. Is any text (letters, "
                "numbers, component values, node or signal names) still readable, even partially? "
                "Is the circuit/diagram structure (lines, components, shapes) still intact?")
CHECK_SCHEMA = {"type": "object", "required": ["text_readable", "structure_intact"],
    "properties": {"text_readable": {"type": "boolean"}, "structure_intact": {"type": "boolean"}}}

def detect_boxes(image):
    with tempfile.TemporaryDirectory() as out:
        subprocess.run(["surya_detect", str(image), "--output_dir", out],
                       check=True, capture_output=True)
        results = json.loads(next(Path(out).rglob("results.json")).read_text())
    pages = next(iter(results.values()))
    return [b["bbox"] for page in pages for b in page["bboxes"]]

def magick(*args):
    return subprocess.run(["convert", *map(str, args)], check=True,
                          capture_output=True, text=True).stdout.strip()

def main():
    if len(sys.argv) < 2:
        raise SystemExit("Usage: strip-labels.py <diagram.png> [<out-stripped.png>]")
    src = Path(sys.argv[1])
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else src.with_name(f"{src.stem}-stripped.png")
    result = {"stripped": None, "boxes": 0, "reason": None}

    boxes = detect_boxes(src)
    result["boxes"] = len(boxes)
    if not boxes:
        result["reason"] = "no labels detected"
        return print(json.dumps(result, indent=2))

    w, h = map(int, magick(src, "-format", "%w %h", "info:").split())
    background = magick(src, "-format", "%[pixel:p{0,0}]", "info:")  # corner pixel = background
    draws = []
    for x1, y1, x2, y2 in boxes:
        x1, y1 = max(0, int(x1) - PAD), max(0, int(y1) - PAD)
        x2, y2 = min(w - 1, int(x2) + PAD), min(h - 1, int(y2) + PAD)
        draws += ["-draw", f"rectangle {x1},{y1} {x2},{y2}"]
    magick(src, "-fill", background, *draws, dst)

    r = ollama.chat(model=VISION, format=CHECK_SCHEMA, options={"temperature": 0},
                    messages=[{"role": "user", "content": CHECK_PROMPT, "images": [str(dst)]}])
    check = json.loads(r["message"]["content"])
    if check["text_readable"] or not check["structure_intact"]:
        dst.unlink(missing_ok=True)
        result["reason"] = ("text still readable" if check["text_readable"] else "structure damaged")
    else:
        result["stripped"] = str(dst)
        result["reason"] = "verified"
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
