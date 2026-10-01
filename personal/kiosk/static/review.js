// /review: every due card across all courses. Confidence (1-5) before the reveal,
// Again/Hard/Good/Easy after it. The server writes review-state after every card.
(() => {
  const $ = (id) => document.getElementById(id);
  const screens = ["loading", "card", "finish", "error"];
  const show = (name) => screens.forEach((s) => ($(s).hidden = s !== name));

  let deck = [], i = 0, phase = "confidence", confidence = null, shownAt = 0, busy = false;
  let started = 0, results = [];
  let retry = null;

  const math = (el) => {
    if (window.renderMathInElement) {
      renderMathInElement(el, {
        delimiters: [
          { left: "$$", right: "$$", display: true },
          { left: "\\[", right: "\\]", display: true },
          { left: "$", right: "$", display: false },
          { left: "\\(", right: "\\)", display: false },
        ],
        throwOnError: false,
      });
    }
  };

  const setText = (el, text) => { el.textContent = text || ""; math(el); };

  const setImage = (el, card, path) => {
    if (path) {
      el.src = `/media/${encodeURIComponent(card.course)}/${path.split("/").map(encodeURIComponent).join("/")}`;
      el.hidden = false;
    } else {
      el.removeAttribute("src");
      el.hidden = true;
    }
  };

  function progress() {
    const total = deck.length;
    $("progress-fill").style.width = total ? `${(100 * i) / total}%` : "0";
    $("count").textContent = total ? `${Math.min(i + 1, total)} / ${total}` : "";
  }

  function fail(msg, again) {
    $("error-msg").textContent = msg;
    retry = again;
    show("error");
  }

  async function load() {
    show("loading");
    $("where").textContent = "";
    try {
      const res = await fetch("/api/review/due", { cache: "no-store" });
      if (!res.ok) throw new Error(`Server said ${res.status}`);
      deck = (await res.json()).cards;
    } catch (e) {
      return fail(`Couldn't load cards: ${e.message}`, load);
    }
    i = 0; results = []; started = Date.now();
    deck.length ? render() : finish();
  }

  function render() {
    const card = deck[i];
    phase = "confidence"; confidence = null; busy = false;
    $("where").textContent = `${card.course} · ${card.topic}${card.is_new ? " · new" : ""}`;
    setText($("question"), card.question);
    setImage($("q-image"), card, card.image);
    $("answer-wrap").hidden = true;
    $("confidence").hidden = false;
    $("rating").hidden = true;
    $("toast").hidden = true;
    document.querySelectorAll("#app button").forEach((b) => (b.disabled = false));
    progress();
    show("card");
    window.scrollTo(0, 0);
    shownAt = Date.now();
  }

  function reveal(conf) {
    if (phase !== "confidence") return;
    const card = deck[i];
    confidence = conf;
    phase = "rating";
    $("conf-shown").textContent = conf;
    setText($("answer"), card.answer);
    setImage($("a-image"), card, card.image_reveal);
    $("source").textContent = card.source_note ? card.source_note.replace(/\[\[|\]\]/g, "") : "";
    $("answer-wrap").hidden = false;
    $("confidence").hidden = true;
    $("rating").hidden = false;
  }

  async function rate(rating) {
    if (phase !== "rating" || busy) return;
    busy = true;
    const card = deck[i];
    document.querySelectorAll("#rating button").forEach((b) => (b.disabled = true));
    try {
      const res = await fetch("/api/review", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          course: card.course, topic: card.topic, id: card.id,
          rating, confidence, duration_ms: Date.now() - shownAt,
        }),
      });
      if (!res.ok) throw new Error(`Server said ${res.status}`);
      const out = await res.json();
      results.push({ card, rating, applied: out.applied, confidence });
      if (out.applied !== rating) {
        // Right but unsure: the server counted it as Hard. Say so briefly before moving on.
        $("toast").textContent = "Low confidence, so this counts as Hard.";
        $("toast").hidden = false;
        await new Promise((r) => setTimeout(r, 900));
      }
    } catch (e) {
      busy = false;
      document.querySelectorAll("#rating button").forEach((b) => (b.disabled = false));
      $("toast").textContent = `Not saved (${e.message}). Tap a rating to try again.`;
      $("toast").hidden = false;
      return;
    }
    i += 1;
    i < deck.length ? render() : finish();
  }

  function listItems(ul, rows) {
    ul.replaceChildren(...rows.map((r) => {
      const li = document.createElement("li");
      li.textContent = r.card.question;
      const small = document.createElement("small");
      small.textContent = `${r.card.course} · ${r.card.topic} · confidence ${r.confidence}`;
      li.append(small);
      math(li);
      return li;
    }));
  }

  function finish() {
    phase = "done";
    $("progress-fill").style.width = "100%";
    $("count").textContent = "";
    $("where").textContent = "";
    const n = results.length;
    const correct = results.filter((r) => r.rating !== "again").length;
    const missed = results.filter((r) => r.rating === "again");
    const over = missed.filter((r) => r.confidence >= 4);
    $("finish-title").textContent = n ? "Session done" : "Nothing due";
    $("s-reviewed").textContent = n;
    $("s-accuracy").textContent = n ? `${Math.round((100 * correct) / n)}%` : "–";
    $("s-minutes").textContent = n ? Math.max(1, Math.round((Date.now() - started) / 60000)) : 0;
    listItems($("weak"), missed);
    listItems($("over"), over);
    $("weak-wrap").hidden = !missed.length;
    $("over-wrap").hidden = !over.length;
    show("finish");
  }

  document.addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b || b.disabled) return;
    if (b.dataset.conf) reveal(Number(b.dataset.conf));
    else if (b.dataset.rate) rate(b.dataset.rate);
    else if (b.id === "again-btn") load();
    else if (b.id === "retry-btn" && retry) retry();
  });

  // Keyboard (iPad/desktop): 1-5 confidence, then 1-4 = Again/Hard/Good/Easy.
  document.addEventListener("keydown", (e) => {
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    const n = Number(e.key);
    if (phase === "confidence" && n >= 1 && n <= 5) reveal(n);
    else if (phase === "rating" && n >= 1 && n <= 4) rate(["again", "hard", "good", "easy"][n - 1]);
  });

  window.addEventListener("DOMContentLoaded", load);
})();
