// /s/<id>/quiz (2.2b): multiple choice with the explanation after each answer, and practice
// problems with random values. The server checks every answer (simpleeval for formulas, 1%
// tolerance), records it in review-state's quiz_attempts, and on Finish writes the summary for
// the study skill from those records. A reload carries on: questions already answered in this
// session don't come back.
(() => {
  const $ = (id) => document.getElementById(id);
  const { math, setText, post } = CardFix;
  const screens = ["loading", "item", "finish", "error"];
  const show = (name) => screens.forEach((s) => ($(s).hidden = s !== name));
  const SRC = $("deck").dataset.src;
  const endBtn = $("end-btn");

  let items = [], i = 0, done = 0, deckSize = 0, names = {}, broken = [];
  let phase = "loading", busy = false, shownAt = 0, started = Date.now(), retry = null;
  let log = [];          // this page's answers: {item, correct, first}
  let last = null;       // the server's reply for the current question

  const tex = (src, el, display = true) => {
    if (window.katex) katex.render(src, el, { displayMode: display, throwOnError: false });
    else el.textContent = src;
  };

  function progress() {
    const total = deckSize;
    const at = done + i;
    $("progress-fill").style.width = total ? `${(100 * at) / total}%` : "0";
    $("count").textContent = total ? `${total - at} left` : "";
  }

  function fail(msg, again) {
    $("error-msg").textContent = msg;
    retry = again;
    phase = "error";
    show("error");
  }

  async function load() {
    phase = "loading";
    show("loading");
    try {
      const res = await fetch(SRC, { cache: "no-store" });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `Server said ${res.status}`);
      }
      const data = await res.json();
      items = data.items; names = data.topic_names || {}; broken = data.broken || [];
      done = data.done || 0;
    } catch (e) {
      return fail(`Couldn't load the quiz: ${e.message}`, load);
    }
    i = 0; log = []; deckSize = done + items.length;
    next();
  }

  const next = () => (i < items.length ? render() : finish());

  function render() {
    const q = items[i];
    phase = q.kind === "multiple_choice" ? "choose" : "solve";
    busy = false; last = null;
    $("where").textContent = `${q.course} · ${names[q.topic] || q.topic}`;
    $("kind").textContent = q.kind === "multiple_choice" ? "Multiple choice" : "Practice problem";
    setText($("question"), q.question);
    $("source").textContent = q.source_note ? q.source_note.replace(/\[\[|\]\]/g, "") : "";
    $("result").hidden = true; $("solution").hidden = true; $("after").hidden = true;
    $("toast").hidden = true;
    $("mc").hidden = q.kind !== "multiple_choice";
    $("problem").hidden = q.kind !== "practice_problem";
    if (q.kind === "multiple_choice") {
      $("mc").replaceChildren(...q.options.map((o, n) => {
        const b = document.createElement("button");
        b.type = "button";
        b.className = "option";
        b.dataset.choice = o.i;
        const k = document.createElement("span");
        k.className = "opt-key";
        k.textContent = n + 1;
        const t = document.createElement("span");
        t.className = "opt-text";
        setText(t, o.text);
        b.append(k, t);
        return b;
      }));
    } else {
      $("answer").value = "";
      $("answer").disabled = false;
      $("check-btn").disabled = false;
      $("giveup-btn").disabled = false;
      // Focus only with a hardware keyboard; on a phone it would pop the keyboard over the question.
      if (matchMedia("(hover: hover)").matches) $("answer").focus();
    }
    progress();
    endBtn.hidden = false;
    show("item");
    window.scrollTo(0, 0);
    shownAt = Date.now();
  }

  async function submit(body) {
    if (busy) return null;
    busy = true;
    const q = items[i];
    $("toast").hidden = true;
    try {
      const out = await post(`${SRC}/answer`, {
        course: q.course, topic: q.topic, id: q.id,
        time_sec: Math.round((Date.now() - shownAt) / 1000), ...body,
      });
      log.push({ item: q, correct: out.correct, first: out.first_in_session });
      return out;
    } catch (e) {
      $("toast").textContent = `Not checked: ${e.message}`;
      $("toast").hidden = false;
      return null;
    } finally {
      busy = false;
    }
  }

  async function choose(choice) {
    if (phase !== "choose") return;
    const out = await submit({ choice });
    if (!out) return;
    phase = "answered"; last = out;
    document.querySelectorAll("#mc .option").forEach((b) => {
      const c = Number(b.dataset.choice);
      b.disabled = true;
      if (c === out.correct_answer) b.classList.add("right");
      else if (c === choice) b.classList.add("wrong");
    });
    verdict(out.correct, out.correct ? "Right." : "Not quite.");
    setText($("explanation"), out.explanation);
    afterButtons(false);
  }

  async function solve(gaveUp) {
    if (phase !== "solve") return;
    const text = $("answer").value.trim();
    if (!gaveUp && !text) { $("answer").focus(); return; }
    const out = await submit({ values: items[i].values, answer: gaveUp ? null : text, gave_up: gaveUp });
    if (!out) return;
    phase = "answered"; last = out;
    $("answer").disabled = true; $("check-btn").disabled = true; $("giveup-btn").disabled = true;
    const msg = gaveUp ? `The answer is ${out.expected}.`
      : out.correct ? `Right: ${out.expected}.`
      : `Not quite. You said ${out.given}; the answer is ${out.expected}.`;
    verdict(out.correct, msg);
    $("explanation").replaceChildren();
    fillSolution(out);
    if (gaveUp) $("solution").hidden = false;
    afterButtons(true);
  }

  function verdict(ok, msg) {
    $("verdict").textContent = msg;
    $("verdict").className = `verdict ${ok ? "ok" : "no"}`;
    $("result").hidden = false;
  }

  function fillSolution(out) {
    $("steps").replaceChildren(...out.steps.map((s) => {
      const li = document.createElement("li");
      setText(li, s);
      return li;
    }));
    $("worked").replaceChildren(...out.worked.map((w) => {
      const div = document.createElement("div");
      // One line each, so long formulas fit a phone: symbolic, numbers substituted, value.
      const parts = [w.symbolic, w.numeric, w.result].filter((p, n, a) => p && a.indexOf(p) === n);
      const lhs = w.lhs ? `${w.lhs} ` : "";
      tex(`\\begin{aligned}${parts.map((p, n) => `${n ? "" : lhs}&${n || w.lhs ? "= " : ""}${p}`).join(" \\\\ ")}\\end{aligned}`, div);
      return div;
    }));
  }

  function afterButtons(isProblem) {
    $("steps-btn").hidden = !isProblem || !$("solution").hidden;
    $("another-btn").hidden = !isProblem;
    $("after-row").className = `row ${isProblem ? ($("steps-btn").hidden ? "two" : "three") : ""}`;
    $("after").hidden = false;
    if (matchMedia("(hover: hover)").matches) $("next-btn").focus();
  }

  function showSteps() {
    if (phase !== "answered" || !last || !last.worked) return;
    $("solution").hidden = false;
    afterButtons(true);
  }

  async function another() {
    if (phase !== "answered" || busy || items[i].kind !== "practice_problem") return;
    busy = true;
    const q = items[i];
    try {
      const res = await fetch(`${SRC}/${encodeURIComponent(q.course)}/${encodeURIComponent(q.topic)}/${encodeURIComponent(q.id)}/another`, { cache: "no-store" });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.detail || `Server said ${res.status}`);
      items[i] = body;          // same question, new values; extra practice in the summary
    } catch (e) {
      $("toast").textContent = `Couldn't get new values: ${e.message}`;
      $("toast").hidden = false;
      busy = false;
      return;
    }
    render();
  }

  function advance() {
    if (phase !== "answered") return;
    i += 1;
    next();
  }

  // ---------- finish ----------
  async function saveSummary() {
    ["saved", "save-err", "resave-btn"].forEach((id) => ($(id).hidden = true));
    try {
      await post(`${SRC}/finish`, { minutes: (Date.now() - started) / 60000, deck: deckSize, broken });
      $("saved").hidden = false;
    } catch (e) {
      $("save-err").textContent = `Summary not saved: ${e.message}`;
      $("save-err").hidden = false;
      $("resave-btn").hidden = false;
    }
  }

  function finish() {
    phase = "done";
    endBtn.hidden = true;
    $("progress-fill").style.width = "100%";
    $("count").textContent = ""; $("where").textContent = "";
    // First answer per question decides; the server's summary also counts answers from before a reload.
    const firsts = log.filter((r) => r.first);
    const n = firsts.length, right = firsts.filter((r) => r.correct).length;
    $("finish-title").textContent = n || done ? "Quiz done" : "Nothing to quiz";
    $("s-answered").textContent = n;
    $("s-accuracy").textContent = n ? `${Math.round((100 * right) / n)}%` : "–";
    $("s-minutes").textContent = n ? Math.max(1, Math.round((Date.now() - started) / 60000)) : 0;
    const by = (k) => firsts.filter((r) => r.item.kind === k);
    const mc = by("multiple_choice"), pp = by("practice_problem");
    $("s-types").textContent = [
      mc.length && `Multiple choice ${mc.filter((r) => r.correct).length}/${mc.length}`,
      pp.length && `Problems ${pp.filter((r) => r.correct).length}/${pp.length}`,
      done && `${done} answered before a reload`,
    ].filter(Boolean).join(" · ");
    const missed = firsts.filter((r) => !r.correct);
    $("weak").replaceChildren(...missed.map((r) => {
      const li = document.createElement("li");
      li.textContent = r.item.question;
      const small = document.createElement("small");
      small.textContent = `${r.item.course} · ${names[r.item.topic] || r.item.topic}`;
      li.append(small);
      math(li);
      return li;
    }));
    $("weak-wrap").hidden = !missed.length;
    $("broken-note").textContent = broken.length
      ? `${broken.length} broken question${broken.length > 1 ? "s were" : " was"} left out: ${broken.join(", ")}` : "";
    $("broken-note").hidden = !broken.length;
    show("finish");
    saveSummary();
  }

  // ---------- input ----------
  $("problem").addEventListener("submit", (e) => { e.preventDefault(); solve(false); });
  document.addEventListener("click", (e) => {
    const b = e.target.closest("#app button");
    if (!b || b.disabled) return;
    if (b.dataset.choice !== undefined) choose(Number(b.dataset.choice));
    else if (b.id === "giveup-btn") solve(true);
    else if (b.id === "steps-btn") showSteps();
    else if (b.id === "another-btn") another();
    else if (b.id === "next-btn") advance();
    else if (b.id === "retry-btn" && retry) retry();
    else if (b.id === "resave-btn") saveSummary();
  });
  endBtn.addEventListener("click", () => phase !== "done" && finish());

  // Keyboard (iPad/desktop): 1-9 picks an option; Enter checks or goes on; S solution; A another.
  document.addEventListener("keydown", (e) => {
    if (e.metaKey || e.ctrlKey || e.altKey || CardFix.dialogOpen()) return;
    if (CardFix.typing(e)) return;            // the answer box handles its own Enter
    const k = e.key.toLowerCase();
    const n = Number(e.key);
    if (phase === "choose" && n >= 1) {
      const b = document.querySelectorAll("#mc .option")[n - 1];
      if (b) choose(Number(b.dataset.choice));
    } else if (phase === "solve" && k === "s") { e.preventDefault(); solve(true); }
    else if (phase === "answered" && k === "enter") { e.preventDefault(); advance(); }
    else if (phase === "answered" && k === "s") showSteps();
    else if (phase === "answered" && k === "a") another();
  });

  load();
})();
