"""Quiz mode (2.2b): multiple choice and practice problems for /s/{id}/quiz.

Quiz files (quizzes/<topic>.json) are read-only here, like card files. Practice problems draw
random values from variable_ranges and are checked against solution_formula with simpleeval --
never eval(): the formulas are generated text. Every answer is recorded in review-state's
quiz_attempts, tagged with the session, and the Finish summary is built from those records.
"""
import ast
import math
import operator
import random
import re
from datetime import datetime

import simpleeval

import sessions
import store

TOLERANCE = 0.01           # answers within 1% of the expected value count as right
KINDS = ("multiple_choice", "practice_problem")
MAX_DRAWS = 25             # redraws before a problem whose formula keeps failing counts as broken
WEAK_RATE = 0.7

# ---------- safe evaluation ----------

FUNCTIONS = {"exp": math.exp, "log": math.log, "ln": math.log, "sqrt": math.sqrt,
             "sin": math.sin, "cos": math.cos, "tan": math.tan, "abs": abs}
CONSTANTS = {"pi": math.pi, "e": math.e}
OPERATORS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
             ast.Div: operator.truediv, ast.Pow: simpleeval.safe_power,
             ast.USub: operator.neg, ast.UAdd: operator.pos}
ASSIGN = re.compile(r"^\s*([A-Za-z_]\w*)\s*=(?!=)\s*(.+)$")


class Broken(Exception):
    """A generated problem that can't be used: bad formula, missing variable, no valid values."""


def _number(x) -> float:
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        raise ValueError("not a number")
    x = float(x)
    if not math.isfinite(x):
        raise ValueError("not finite")
    return x


def evaluate(expr: str, names: dict) -> float:
    """One arithmetic expression: + - * / ^, the FUNCTIONS above, pi and e. ^ means power."""
    ev = simpleeval.SimpleEval(operators=OPERATORS, functions=FUNCTIONS, names={**CONSTANTS, **names})
    return _number(ev.eval(expr.replace("^", "**")))


def steps(formula: str) -> list[tuple[str | None, str]]:
    """solution_formula as [(name or None, expr)]: ';' separates steps, 'x = ...' names one."""
    out = []
    for part in (p.strip() for p in formula.split(";")):
        if part:
            m = ASSIGN.match(part)
            out.append((m.group(1), m.group(2)) if m else (None, part))
    if not out:
        raise Broken("empty formula")
    return out


def solve(formula: str, values: dict) -> float:
    names = dict(values)
    result = None
    for name, expr in steps(formula):
        result = evaluate(expr, names)
        if name:
            names[name] = result
    return result


def parse_answer(text: str) -> float:
    """What you typed: a number, or a small expression like 3/4, 1.2e-3 or 2*pi."""
    text = text.strip().replace("×", "*").replace("−", "-")
    if not text or len(text) > 60:
        raise ValueError("empty or too long")
    try:
        return evaluate(text, {})
    except ValueError:
        raise
    except Exception:                  # simpleeval refusing a name, a function or a huge power
        raise ValueError("not a number")


def close_enough(given: float, expected: float) -> bool:
    if expected == 0:
        return abs(given) < 1e-9
    return abs(given - expected) <= TOLERANCE * abs(expected)


# ---------- drawing values ----------

def fmt(x: float) -> str:
    """Numbers as shown in questions and answers."""
    if float(x).is_integer() and abs(x) < 1e12:
        return str(int(x))
    if x != 0 and (abs(x) >= 1e6 or abs(x) < 1e-3):
        return f"{x:.4g}"
    return f"{x:.6g}"


def _int_range(lo, hi) -> bool:
    return all(isinstance(b, int) and not isinstance(b, bool) for b in (lo, hi))


def _draw(lo, hi, rng: random.Random):
    if _int_range(lo, hi):
        return rng.randint(min(lo, hi), max(lo, hi))
    x = rng.uniform(float(lo), float(hi))
    if x == 0:
        return 0.0
    return round(x, 2 - math.floor(math.log10(abs(x))))       # 3 significant figures


def ranges(problem: dict) -> dict:
    r = problem.get("variable_ranges")
    if not isinstance(r, dict) or not r:
        raise Broken("no variable_ranges")
    for name, b in r.items():
        if not re.fullmatch(r"[A-Za-z_]\w*", name) or not isinstance(b, list) or len(b) != 2:
            raise Broken(f"bad range for {name}")
        try:
            _number(b[0]), _number(b[1])
        except ValueError:
            raise Broken(f"bad range for {name}")
    return r


def draw(problem: dict, rng: random.Random | None = None) -> tuple[dict, float]:
    """Random values (drawn values are what you see, so the answer uses exactly those) and the answer."""
    rng = rng or random.Random()
    r = ranges(problem)
    formula = problem.get("solution_formula") or ""
    for _ in range(MAX_DRAWS):
        values = {k: _draw(lo, hi, rng) for k, (lo, hi) in r.items()}
        try:
            return values, solve(formula, values)
        except (ValueError, ZeroDivisionError, OverflowError, TypeError):
            continue                   # e.g. a division by zero for these values: draw again
        except Exception as e:         # simpleeval: unknown name/function, syntax error
            raise Broken(f"formula: {e}")
    raise Broken("no values gave an answer")


def in_range(problem: dict, values: dict) -> bool:
    r = ranges(problem)
    if set(values) != set(r):
        return False
    try:
        return all(min(lo, hi) - 1e-9 <= _number(values[k]) <= max(lo, hi) + 1e-9
                   for k, (lo, hi) in r.items())
    except ValueError:
        return False


def fill(text: str, values: dict) -> str:
    return re.sub(r"\{([A-Za-z_]\w*)\}", lambda m: fmt(values[m.group(1)]) if m.group(1) in values else m.group(0),
                  text or "")


# ---------- formula -> LaTeX (rendered by the vendored KaTeX) ----------

GREEK = {"alpha", "beta", "gamma", "delta", "epsilon", "theta", "lambda", "mu", "nu", "rho",
         "sigma", "tau", "phi", "omega", "eta", "zeta", "kappa", "psi", "chi", "xi"}
FUNC_TEX = {"sin": r"\sin", "cos": r"\cos", "tan": r"\tan", "log": r"\ln", "ln": r"\ln"}
PREC = {ast.Add: 1, ast.Sub: 1, ast.Mult: 2, ast.Div: 2, ast.USub: 3, ast.UAdd: 3, ast.Pow: 4}


def tex_name(name: str) -> str:
    m = re.fullmatch(r"([A-Za-z]+)_?(\d*)", name)
    base, sub = (m.group(1), m.group(2)) if m else (name, "")
    if base.lower() in GREEK:
        base = "\\" + (base.lower() if base[0].islower() else base.capitalize())
    elif base == "pi":
        base = r"\pi"
    elif len(base) > 1:
        base = rf"\mathrm{{{base}}}"
    return f"{base}_{{{sub}}}" if sub else base


def tex_number(x: float) -> str:
    s = fmt(x)
    if "e" in s:
        mant, exp = s.split("e")
        return rf"{mant}\times 10^{{{int(exp)}}}"
    return s


def _prec(node) -> int:
    if isinstance(node, ast.BinOp):
        return PREC[type(node.op)]
    if isinstance(node, ast.UnaryOp):
        return PREC[type(node.op)]
    if isinstance(node, ast.Constant) and node.value < 0:
        return 3
    return 5


def _tex(node, values: dict | None) -> str:
    paren = lambda n, p: rf"\left({_tex(n, values)}\right)" if _prec(n) < p else _tex(n, values)
    if isinstance(node, ast.Constant):
        return tex_number(node.value)
    if isinstance(node, ast.Name):
        if values is not None and node.id in values:
            v = values[node.id]
            return rf"\left({tex_number(v)}\right)" if v < 0 else tex_number(v)
        return tex_name(node.id)
    if isinstance(node, ast.UnaryOp):
        return ("-" if isinstance(node.op, ast.USub) else "+") + paren(node.operand, 3)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        f, args = node.func.id, [_tex(a, values) for a in node.args]
        inner = ", ".join(args)
        if f == "sqrt":
            return rf"\sqrt{{{inner}}}"
        if f == "exp":
            return rf"e^{{{inner}}}"
        if f == "abs":
            return rf"\left|{inner}\right|"
        return rf"{FUNC_TEX.get(f, rf'\operatorname{{{f}}}')}\left({inner}\right)"
    if isinstance(node, ast.BinOp):
        op = type(node.op)
        if op is ast.Div:
            return rf"\frac{{{_tex(node.left, values)}}}{{{_tex(node.right, values)}}}"
        if op is ast.Pow:
            return rf"{{{paren(node.left, 5)}}}^{{{_tex(node.right, values)}}}"
        if op is ast.Mult:
            left, right = paren(node.left, 2), paren(node.right, 2)
            # Implicit product between letters (RC); a dot wherever a number is involved (2·R, 3·4)
            dot = values is not None or re.match(r"[\d.\-]", right) or re.search(r"[\d.]$", left)
            return f"{left} \\cdot {right}" if dot else f"{left} {right}"
        sym = "+" if op is ast.Add else "-"
        return f"{paren(node.left, 1)} {sym} {paren(node.right, 2)}"
    raise ValueError("unsupported")


def to_latex(expr: str, values: dict | None = None) -> str | None:
    """LaTeX for one expression; with values, the numbers substituted in. None if it won't parse."""
    try:
        return _tex(ast.parse(expr.replace("^", "**"), mode="eval").body, values)
    except (SyntaxError, ValueError, KeyError, AttributeError):
        return None


def worked(problem: dict, values: dict) -> list[dict]:
    """The formula step by step: symbolic, with numbers, and the value each step gives."""
    names, out = dict(values), []
    for name, expr in steps(problem.get("solution_formula") or ""):
        result = evaluate(expr, names)
        lhs = tex_name(name) if name else None
        out.append({"lhs": lhs, "symbolic": to_latex(expr), "numeric": to_latex(expr, names),
                    "result": tex_number(result)})
        if name:
            names[name] = result
    return out


# ---------- items, attempts, decks ----------

def quiz_topics(course: str) -> list[str]:
    return sorted(p.stem for p in (store.course_dir(course) / "quizzes").glob("*.json"))


def load_items(course: str, topic: str) -> list[dict]:
    """A topic's quiz items as decks use them: rewrites hide what they replace, and anything
    deleted or flagged in card-edits stays out."""
    if topic not in quiz_topics(course):
        raise KeyError(topic)
    raw = (store.read_json(store.course_dir(course) / "quizzes" / f"{topic}.json") or {}).get("quizzes", [])
    edits = store.load_edits(course, topic)
    replaced = {q["replaces"] for q in raw if isinstance(q, dict) and q.get("replaces")}
    out = []
    for q in raw:
        if not isinstance(q, dict) or not q.get("id") or q.get("type") not in KINDS or q["id"] in replaced:
            continue
        if (edits.get(q["id"]) or {}).get("action") in ("deleted", "flagged"):
            continue
        out.append(dict(q, course=course, topic=topic))
    return out


def find_item(course: str, topic: str, qid: str) -> dict:
    item = next((q for q in load_items(course, topic) if q["id"] == qid), None)
    if item is None:
        raise KeyError(qid)
    return item


def record_attempt(course: str, topic: str, qid: str, record: dict) -> list:
    path = store.review_state_path(course, topic)
    with store.lock_for(path):
        state = store.load_review_state(course, topic)
        state.setdefault("topic", topic)
        state.setdefault("cards", {})
        tries = state.setdefault("quiz_attempts", {}).setdefault(qid, [])
        tries.append(record)
        store.write_json_atomic(path, state)
        return tries


def _mc_valid(q: dict) -> bool:
    opts, ans = q.get("options"), q.get("correct_answer")
    return (isinstance(opts, list) and len(opts) >= 2 and isinstance(ans, int)
            and not isinstance(ans, bool) and 0 <= ans < len(opts))


NO_SHUFFLE = re.compile(r"\b(all|none|both|neither) of (the )?(above|these)\b|^\s*(both|neither)\b|\b[A-D] and [A-D]\b", re.I)


def public_mc(q: dict, rng: random.Random) -> dict:
    """Options in random order (unless one refers to the others); the answer stays on the server."""
    order = list(range(len(q["options"])))
    if not any(NO_SHUFFLE.search(str(o)) for o in q["options"]):
        rng.shuffle(order)
    return {"kind": "multiple_choice", "id": q["id"], "course": q["course"], "topic": q["topic"],
            "question": q.get("question", ""), "options": [{"i": i, "text": str(q["options"][i])} for i in order],
            "source_note": q.get("source_note")}


def public_problem(q: dict, rng: random.Random) -> dict:
    values, _ = draw(q, rng)
    return {"kind": "practice_problem", "id": q["id"], "course": q["course"], "topic": q["topic"],
            "question": fill(q.get("question", ""), values), "values": values,
            "source_note": q.get("source_note")}


def public(q: dict, rng: random.Random) -> dict:
    return public_mc(q, rng) if q["type"] == "multiple_choice" else public_problem(q, rng)


def _pool(course, topic, flt, kinds, session_id, rng):
    """One topic's items in study order: missed last time, then never tried, then the rest
    (longest since last tried first). "weak" keeps only items missed last time or under 70%."""
    attempts = store.load_review_state(course, topic).get("quiz_attempts", {})
    missed, new, rest, broken = [], [], [], []
    for q in load_items(course, topic):
        if q["type"] not in kinds:
            continue
        tries = attempts.get(q["id"]) or []
        if any(t.get("session") == session_id for t in tries):
            continue                                       # already done in this session (reload)
        if q["type"] == "multiple_choice" and not _mc_valid(q):
            broken.append(q["id"])
            continue
        if q["type"] == "practice_problem":
            try:
                draw(q, rng)
            except Broken:
                broken.append(q["id"])
                continue
        right = sum(bool(t.get("correct")) for t in tries)
        last_wrong = bool(tries) and not tries[-1].get("correct")
        if flt == "weak":
            if tries and (last_wrong or right / len(tries) < WEAK_RATE):
                missed.append(q)
        elif last_wrong:
            missed.append(q)
        elif not tries:
            new.append(q)
        else:
            rest.append((tries[-1].get("time") or tries[-1].get("date") or "", q))
    rng.shuffle(missed)
    rng.shuffle(new)
    return missed + new + [q for _, q in sorted(rest, key=lambda x: x[0])], broken


def build_deck(spec: dict, session_id: str, rng: random.Random | None = None) -> dict:
    rng = rng or random.Random()
    course = spec["course"]
    flt = "weak" if spec.get("filter") == "weak" else "all"
    kinds = [k for k in (spec.get("kinds") or KINDS) if k in KINDS] or list(KINDS)
    limit = spec.get("limit")
    limit = limit if isinstance(limit, int) and limit > 0 else None
    registry = sessions.topic_registry(course)
    have = set(quiz_topics(course))
    subs = bool(spec.get("include_subtopics"))

    primary = sessions.expand(spec.get("topics"), registry, subs, have)
    related = []
    if spec.get("interleave"):
        named = [t for t in (spec.get("related_topics") or []) if t not in primary][:sessions.MAX_RELATED]
        related = [t for t in sessions.expand(named, registry, subs, have) if t not in primary]

    broken = []
    main = []
    for t in primary:
        items, bad = _pool(course, t, flt, kinds, session_id, rng)
        main += items
        broken += bad
    pools = [main]
    for t in related:
        items, bad = _pool(course, t, flt, kinds, session_id, rng)
        pools.append(items)
        broken += bad
    take = sessions._allocate(pools, limit)
    pools = [p[:n] for p, n in zip(pools, take)]
    items = sessions._mix(pools, rng) if related else pools[0]

    done = attempted_in_session(course, primary + related, session_id)
    names = {t: (registry.get(t) or {}).get("display_name") or t for t in primary + related}
    return {"items": [public(q, rng) for q in items], "course": course, "topics": primary,
            "related_topics": related, "interleave": bool(related), "filter": flt, "kinds": kinds,
            "topic_names": names, "broken": broken, "done": len(done)}


def check(item: dict, session_id: str, body: dict) -> dict:
    """Check one answer, record it, and return what the page shows next."""
    now = datetime.now()
    record = {"date": now.date().isoformat(), "time": now.isoformat(timespec="seconds"),
              "correct": False, "time_sec": body.get("time_sec"), "session": session_id}
    if item["type"] == "multiple_choice":
        if not _mc_valid(item):
            raise Broken("bad options")
        choice = body.get("choice")
        if not isinstance(choice, int) or not 0 <= choice < len(item["options"]):
            raise ValueError("choice out of range")
        record.update(correct=choice == item["correct_answer"], choice=choice)
        out = {"correct": record["correct"], "correct_answer": item["correct_answer"],
               "explanation": item.get("explanation") or ""}
    else:
        values = body.get("values") or {}
        if not in_range(item, values):
            raise ValueError("values don't match this problem")
        values = {k: _number(v) for k, v in values.items()}
        values = {k: int(v) if _int_range(*item["variable_ranges"][k]) and v.is_integer() else v
                  for k, v in values.items()}
        try:
            expected = solve(item["solution_formula"], values)
        except Exception as e:
            raise Broken(f"formula: {e}")
        gave_up = bool(body.get("gave_up"))
        given = None
        if not gave_up:
            given = parse_answer(str(body.get("answer") or ""))
        record.update(correct=(not gave_up) and close_enough(given, expected),
                      values=values, answer=given, gave_up=gave_up or None)
        out = {"correct": record["correct"], "expected": fmt(expected), "expected_tex": tex_number(expected),
               "given": None if given is None else fmt(given),
               "steps": [str(s) for s in (item.get("solution_steps") or [])],
               "worked": worked(item, values)}
    record = {k: v for k, v in record.items() if v is not None}
    tries = record_attempt(item["course"], item["topic"], item["id"], record)
    out["first_in_session"] = sum(t.get("session") == session_id for t in tries) == 1
    return out


def attempted_in_session(course: str, topics: list[str], session_id: str) -> dict:
    """{(topic, id): [attempts in this session, in order]}."""
    out = {}
    for t in topics:
        for qid, tries in store.load_review_state(course, t).get("quiz_attempts", {}).items():
            mine = [a for a in tries if a.get("session") == session_id]
            if mine:
                out[(t, qid)] = mine
    return out


def summarize(session_id: str, spec: dict, minutes: float, deck_size: int, broken: list[str]) -> dict:
    """The compact summary Claude reads, from what was recorded on the server. An item's first
    attempt in the session decides whether it was right; "Another one like this" is extra practice."""
    course = spec["course"]
    registry = sessions.topic_registry(course)
    have = set(quiz_topics(course))
    subs = bool(spec.get("include_subtopics"))
    topics = sessions.expand(spec.get("topics"), registry, subs, have)
    topics += [t for t in sessions.expand(spec.get("related_topics") or [], registry, subs, have)
               if t not in topics]
    done = attempted_in_session(course, topics, session_id)
    kind_of = {}
    for t in topics:
        for q in load_items(course, t):
            kind_of[(t, q["id"])] = q["type"]

    by_topic, by_type, weak, gave_up = {}, {}, [], []
    extra = 0
    for (t, qid), tries in done.items():
        first = tries[0]
        ok = bool(first.get("correct"))
        n, r = by_topic.get(t, (0, 0))
        by_topic[t] = [n + 1, r + ok]
        k = kind_of.get((t, qid), "practice_problem" if "values" in first else "multiple_choice")
        n, r = by_type.get(k, (0, 0))
        by_type[k] = [n + 1, r + ok]
        if not ok:
            weak.append(qid)
        if first.get("gave_up"):
            gave_up.append(qid)
        extra += len(tries) - 1
    answered = len(done)
    correct = sum(r for _, r in by_topic.values())
    label = {"multiple_choice": "MC", "practice_problem": "problems"}
    parts = ", ".join(f"{label[k]} {r}/{n}" for k, (n, r) in sorted(by_type.items()))
    return {
        "from": "kiosk", "to": "study-skill", "type": "session-summary",
        "session_id": session_id, "mode": "quiz",
        "summary": f"quiz: {correct}/{answered} right first time" + (f" ({parts})" if parts else ""),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "deck": deck_size, "answered": answered, "correct": correct,
        "by_type": by_type, "weak_items": weak, "gave_up": gave_up, "extra_practice": extra,
        "broken": sorted(set(broken)),
        "minutes": max(1, round(minutes)) if answered else round(minutes),
        "by_topic": by_topic,
    }
