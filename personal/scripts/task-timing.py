#!/home/jacob/.venvs/brain/bin/python
# task-timing.py -- Task Duration Tracking (blueprint 1.3), zero Claude tokens
# Usage:
#   task-timing.py log --path P --type T --course C --est 45 --started 2026-10-01T14:02:00 --energy 3 [--actual 50]
#       Appends a timing_history entry to Meta/task-timing.json and updates the running
#       averages (by type, by course, by type+course). Actual minutes = now - started unless
#       --actual is given. Exit 2 (nothing written) if that is negative or over 480 minutes.
#   task-timing.py factor --type T --course C
#       Prints {"factor": x, "source": ..., "samples": n}: the most specific average with
#       at least MIN_SAMPLES samples (type+course, then type, then course), else 1.0.

import argparse, json, sys
from datetime import datetime
from pathlib import Path

TIMING = Path.home() / "brain-vault/Meta/task-timing.json"
MIN_SAMPLES = 2
MAX_MIN = 480

def load():
    data = json.loads(TIMING.read_text()) if TIMING.exists() else {}
    for key in ("averages_by_type", "averages_by_course", "averages_by_type_course"):
        data.setdefault(key, {})
    data.setdefault("timing_history", [])
    return data

def bump(table, key, ratio):
    """Running mean: new = (avg * n + ratio) / (n + 1)."""
    a = table.get(key, {"avg_ratio": 0.0, "samples": 0})
    n = a["samples"]
    table[key] = {"avg_ratio": round((a["avg_ratio"] * n + ratio) / (n + 1), 2), "samples": n + 1}

def log(args):
    actual = args.actual
    if actual is None:
        started = datetime.fromisoformat(args.started)
        actual = round((datetime.now() - started).total_seconds() / 60)
    if actual <= 0 or actual > MAX_MIN:
        print(json.dumps({"error": f"actual {actual} min is outside 1-{MAX_MIN}; ask for the real duration"}))
        sys.exit(2)
    ratio = round(actual / args.est, 2)
    entry = {"task_path": args.path, "type": args.type, "course": args.course,
             "estimated_min": args.est, "actual_min": actual, "ratio": ratio,
             "energy_at_start": args.energy, "date": datetime.now().strftime("%Y-%m-%d")}
    data = load()
    data["timing_history"].append(entry)
    bump(data["averages_by_type"], args.type, ratio)
    bump(data["averages_by_course"], args.course, ratio)
    bump(data["averages_by_type_course"], f"{args.type}|{args.course}", ratio)
    TIMING.parent.mkdir(parents=True, exist_ok=True)
    TIMING.write_text(json.dumps(data, indent=2) + "\n")
    print(json.dumps(entry))

def factor(args):
    data = load()
    for source, table, key in (("type+course", "averages_by_type_course", f"{args.type}|{args.course}"),
                               ("type", "averages_by_type", args.type),
                               ("course", "averages_by_course", args.course)):
        a = data[table].get(key)
        if a and a["samples"] >= MIN_SAMPLES:
            print(json.dumps({"factor": a["avg_ratio"], "source": source, "samples": a["samples"]}))
            return
    print(json.dumps({"factor": 1.0, "source": "none", "samples": 0}))

p = argparse.ArgumentParser()
sub = p.add_subparsers(dest="cmd", required=True)
l = sub.add_parser("log")
l.add_argument("--path", required=True)
l.add_argument("--type", required=True)
l.add_argument("--course", required=True)
l.add_argument("--est", type=int, required=True)
l.add_argument("--started")
l.add_argument("--energy", type=int)
l.add_argument("--actual", type=int)
f = sub.add_parser("factor")
f.add_argument("--type", required=True)
f.add_argument("--course", required=True)
args = p.parse_args()
if args.cmd == "log" and args.started is None and args.actual is None:
    p.error("log needs --started or --actual")
log(args) if args.cmd == "log" else factor(args)
