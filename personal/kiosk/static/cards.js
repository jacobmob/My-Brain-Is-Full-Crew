// /cards: browse and search every card; filter by course/topic/status; sort by most failed;
// fix one card from its row, or select several and delete/flag them together.
(() => {
  const $ = (id) => document.getElementById(id);
  const { key, math, setText } = CardFix;
  let rows = [], courses = {}, selected = new Set(), openKey = null;

  const byKey = () => new Map(rows.map((r) => [key(r), r]));

  async function load() {
    try {
      const res = await fetch("/api/cards", { cache: "no-store" });
      if (!res.ok) throw new Error(`server said ${res.status}`);
      const data = await res.json();
      rows = data.cards;
      courses = data.courses;
      CardFix.setReasons(data.reasons);
    } catch (e) {
      $("shown").textContent = `Couldn't load cards: ${e.message}`;
      return;
    }
    $("course").append(...Object.keys(courses).map((c) => new Option(c, c)));
    fillTopics();
    readHash();
    draw();
  }

  function fillTopics() {
    const c = $("course").value;
    const keep = $("topic").value;
    const list = c ? courses[c].map((t) => [t, t]) : Object.entries(courses).flatMap(([cc, ts]) => ts.map((t) => [`${cc}/${t}`, `${cc} · ${t}`]));
    $("topic").replaceChildren(new Option("All topics", ""), ...list.map(([v, l]) => new Option(l, v)));
    $("topic").value = list.some(([v]) => v === keep) ? keep : "";
  }

  // Filters live in the URL hash so Back and reloads keep them.
  function readHash() {
    const p = new URLSearchParams(location.hash.slice(1));
    for (const id of ["q", "course", "status", "sort"]) if (p.has(id)) $(id).value = p.get(id);
    fillTopics();
    if (p.has("topic")) $("topic").value = p.get("topic");
  }
  function writeHash() {
    const p = new URLSearchParams();
    for (const id of ["q", "course", "topic", "status", "sort"]) if ($(id).value) p.set(id, $(id).value);
    history.replaceState(null, "", `#${p}`);
  }

  function filtered() {
    const q = $("q").value.trim().toLowerCase();
    const course = $("course").value, topic = $("topic").value, status = $("status").value;
    let out = rows.filter((r) => {
      if (r.status === "deleted") return false;
      if (status && r.status !== status) return false;
      if (course && r.course !== course) return false;
      if (topic && (course ? r.topic !== topic : `${r.course}/${r.topic}` !== topic)) return false;
      if (q && !`${r.question}\n${r.answer}\n${r.id}\n${r.topic}`.toLowerCase().includes(q)) return false;
      return true;
    });
    if ($("sort").value === "failed") {
      out = out.slice().sort((a, b) => b.fails - a.fails || b.reviews - a.reviews);
    }
    return out;
  }

  function badge(text, cls) {
    const s = document.createElement("span");
    s.className = `badge ${cls || ""}`;
    s.textContent = text;
    return s;
  }

  function rowEl(r) {
    const li = document.createElement("li");
    li.className = "crow";
    li.dataset.key = key(r);

    const check = document.createElement("label");
    check.className = "check";
    const box = document.createElement("input");
    box.type = "checkbox";
    box.checked = selected.has(key(r));
    box.setAttribute("aria-label", "Select card");
    check.append(box);

    const body = document.createElement("div");
    body.className = "cbody";
    const q = document.createElement("p");
    q.className = "cq";
    setText(q, r.question);
    const meta = document.createElement("p");
    meta.className = "cmeta";
    meta.append(`${r.course} · ${r.topic} · ${r.id}`);
    if (r.reviews) meta.append(` · missed ${r.fails}/${r.reviews}`);
    if (r.status === "edited") meta.append(" ", badge("edited"));
    if (r.status === "flagged") meta.append(" ", badge("flagged", "warn"));
    body.append(q, meta);

    if (openKey === key(r)) {
      const more = document.createElement("div");
      more.className = "cmore";
      const a = document.createElement("p");
      a.className = "ca";
      setText(a, r.answer);
      more.append(a);
      for (const path of [r.image, r.image_reveal]) {
        if (!path) continue;
        const img = document.createElement("img");
        img.alt = "";
        img.loading = "lazy";
        img.src = `/media/${encodeURIComponent(r.course)}/${path.split("/").map(encodeURIComponent).join("/")}`;
        more.append(img);
      }
      if (r.note) {
        const n = document.createElement("p");
        n.className = "muted small";
        n.textContent = `Flag note: ${r.note}`;
        more.append(n);
      }
      const acts = document.createElement("div");
      acts.className = "row three";
      const btn = (label, fix, cls) => {
        const b = document.createElement("button");
        b.type = "button"; b.textContent = label; b.dataset.fix = fix;
        if (cls) b.className = cls;
        return b;
      };
      if (r.status === "flagged") acts.append(btn("Unflag", "restore"), btn("Delete", "delete", "danger"));
      else acts.append(btn("Edit", "edit"), btn("Flag", "flag"), btn("Delete", "delete", "danger"));
      more.append(acts);
      body.append(more);
    }

    li.append(check, body);
    return li;
  }

  function draw() {
    writeHash();
    const list = filtered();
    $("rows").replaceChildren(...list.map(rowEl));
    $("empty").hidden = list.length > 0;
    $("shown").textContent = `${list.length} card${list.length === 1 ? "" : "s"}`;
    const shownKeys = list.map(key);
    $("select-all").checked = shownKeys.length > 0 && shownKeys.every((k) => selected.has(k));
    drawBulk();
  }

  function drawBulk() {
    // Drop selections that are no longer visible-able (deleted elsewhere)
    const m = byKey();
    for (const k of selected) if (!m.has(k) || m.get(k).status === "deleted") selected.delete(k);
    $("bulkbar").hidden = selected.size === 0;
    $("bulk-count").textContent = `${selected.size} selected`;
  }

  function update(changed) {
    const m = new Map(changed.map((r) => [key(r), r]));
    rows = rows.map((r) => m.get(key(r)) || r);
    draw();
  }

  const hooks = {
    onRemoved(changed) { changed.forEach((r) => selected.delete(key(r))); update(changed); },
    onRestored: update,
    onEdited: (r) => update([r]),
  };

  const openCard = () => (openKey ? byKey().get(openKey) : null);

  $("rows").addEventListener("click", (e) => {
    const li = e.target.closest(".crow");
    if (!li) return;
    const k = li.dataset.key;
    if (e.target.closest(".check")) {
      if (e.target.matches("input")) {
        e.target.checked ? selected.add(k) : selected.delete(k);
        draw();
      }
      return;
    }
    const b = e.target.closest("button[data-fix]");
    if (b) {
      const r = byKey().get(k);
      if (b.dataset.fix === "restore") {
        CardFix.restore([r], hooks).then(() => CardFix.snack("Unflagged.")).catch((err) => CardFix.snack(`Not unflagged: ${err.message}`));
      } else if (b.dataset.fix === "delete") CardFix.del([r], hooks);
      else if (b.dataset.fix === "flag") CardFix.flag([r], hooks);
      else if (b.dataset.fix === "edit") CardFix.edit(r, hooks);
      return;
    }
    if (e.target.closest(".cmore")) return;   // let people select answer text
    openKey = openKey === k ? null : k;
    draw();
  });

  $("select-all").addEventListener("change", (e) => {
    filtered().forEach((r) => (e.target.checked ? selected.add(key(r)) : selected.delete(key(r))));
    draw();
  });

  const chosen = () => { const m = byKey(); return [...selected].map((k) => m.get(k)).filter(Boolean); };
  $("bulk-delete").addEventListener("click", () => CardFix.del(chosen(), hooks));
  $("bulk-flag").addEventListener("click", () => CardFix.flag(chosen(), hooks));
  $("bulk-clear").addEventListener("click", () => { selected.clear(); draw(); });

  let t = null;
  $("q").addEventListener("input", () => { clearTimeout(t); t = setTimeout(draw, 150); });
  $("course").addEventListener("change", () => { fillTopics(); draw(); });
  for (const id of ["topic", "status", "sort"]) $(id).addEventListener("change", draw);

  // D/E/F act on the card that's open
  CardFix.shortcuts(openCard, hooks);

  load();
})();
