// /review: every due card across all courses. Confidence (1-5) before the reveal,
// Again/Hard/Good/Easy after it. The server writes review-state after every card.
// A card rated Again comes back a few cards later, until you get it.
(() => {
  const $ = (id) => document.getElementById(id);
  const { key, math, setText } = CardFix;
  const screens = ["loading", "card", "finish", "error"];
  const show = (name) => screens.forEach((s) => ($(s).hidden = s !== name));
  const REQUEUE_GAP = 3;   // other cards shown before a missed one returns

  let deck = [], i = 0, phase = "loading", confidence = null, shownAt = 0, busy = false;
  let started = 0, results = [], removed = new Set(), retry = null;

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
    $("count").textContent = total ? `${total - i} left` : "";
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
    $("where").textContent = "";
    try {
      const res = await fetch("/api/review/due", { cache: "no-store" });
      if (!res.ok) throw new Error(`Server said ${res.status}`);
      deck = (await res.json()).cards;
    } catch (e) {
      return fail(`Couldn't load cards: ${e.message}`, load);
    }
    i = 0; results = []; removed = new Set(); started = Date.now();
    next();
  }

  const next = () => (i < deck.length ? render() : finish());

  function showText(card) {
    setText($("question"), card.question);
    setImage($("q-image"), card, card.image);
    setText($("answer"), card.answer);
    setImage($("a-image"), card, card.image_reveal);
    $("source").textContent = card.source_note ? card.source_note.replace(/\[\[|\]\]/g, "") : "";
  }

  function render() {
    const card = deck[i];
    phase = "confidence"; confidence = null; busy = false;
    const again = results.some((r) => key(r.card) === key(card));
    $("where").textContent = `${card.course} · ${card.topic}${again ? " · again" : card.is_new ? " · new" : ""}`;
    showText(card);
    $("answer-wrap").hidden = true;
    $("confidence").hidden = false;
    $("rating").hidden = true;
    $("toast").hidden = true;
    document.querySelectorAll("#card button").forEach((b) => (b.disabled = false));
    progress();
    show("card");
    window.scrollTo(0, 0);
    shownAt = Date.now();
  }

  function reveal(conf) {
    if (phase !== "confidence") return;
    confidence = conf;
    phase = "rating";
    $("conf-shown").textContent = conf;
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
    if (rating === "again" && !removed.has(key(card))) {
      deck.splice(Math.min(i + 1 + REQUEUE_GAP, deck.length), 0, card);
    }
    i += 1;
    next();
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
    // Per card, not per attempt: a card counts as right if its first rating wasn't Again.
    const first = new Map();
    results.forEach((r) => first.has(key(r.card)) || first.set(key(r.card), r));
    const n = first.size;
    const firstMiss = [...first.values()].filter((r) => r.rating === "again");
    const kept = (r) => !removed.has(key(r.card));     // deleted/flagged cards aren't weak cards
    const missed = firstMiss.filter(kept);
    const over = results.filter((r) => r.rating === "again" && r.confidence >= 4 && kept(r))
      .filter((r, j, a) => a.findIndex((x) => key(x.card) === key(r.card)) === j);
    $("finish-title").textContent = n ? "Session done" : "Nothing due";
    $("s-reviewed").textContent = n;
    $("s-accuracy").textContent = n ? `${Math.round((100 * (n - firstMiss.length)) / n)}%` : "–";
    $("s-minutes").textContent = n ? Math.max(1, Math.round((Date.now() - started) / 60000)) : 0;
    listItems($("weak"), missed);
    listItems($("over"), over);
    $("weak-wrap").hidden = !missed.length;
    $("over-wrap").hidden = !over.length;
    show("finish");
  }

  // ---------- fixing bad cards ----------
  const current = () => (phase === "confidence" || phase === "rating" ? deck[i] : null);

  const hooks = {
    onRemoved(rows) {
      rows.forEach((r) => removed.add(key(r)));
      const gone = new Set(rows.map(key));
      deck = deck.slice(0, i).concat(deck.slice(i).filter((c) => !gone.has(key(c))));
      next();
    },
    onRestored(rows) {
      // Put the card back in front of you, starting over at the confidence step.
      rows.forEach((r) => removed.delete(key(r)));
      deck.splice(i, 0, ...rows.filter((r) => r.status === "active" || r.status === "edited"));
      next();
    },
    onEdited(row) {
      deck.forEach((c) => {
        if (key(c) === key(row)) { c.question = row.question; c.answer = row.answer; c.status = row.status; }
      });
      if (current() && key(current()) === key(row)) showText(current());
    },
  };

  $("card-menu").addEventListener("click", () => current() && CardFix.openMenu(current(), hooks));
  CardFix.shortcuts(current, hooks);

  document.addEventListener("click", (e) => {
    const b = e.target.closest("#app button");
    if (!b || b.disabled) return;
    if (b.dataset.conf) reveal(Number(b.dataset.conf));
    else if (b.dataset.rate) rate(b.dataset.rate);
    else if (b.id === "again-btn") load();
    else if (b.id === "retry-btn" && retry) retry();
  });

  // Keyboard (iPad/desktop): 1-5 confidence, then 1-4 = Again/Hard/Good/Easy.
  document.addEventListener("keydown", (e) => {
    if (e.metaKey || e.ctrlKey || e.altKey || CardFix.dialogOpen() || CardFix.typing(e)) return;
    const n = Number(e.key);
    if (phase === "confidence" && n >= 1 && n <= 5) reveal(n);
    else if (phase === "rating" && n >= 1 && n <= 4) rate(["again", "hard", "good", "easy"][n - 1]);
  });

  load();
})();
