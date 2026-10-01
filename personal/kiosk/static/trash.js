// /trash: everything you deleted, newest first. Restore with one tap.
(() => {
  const $ = (id) => document.getElementById(id);
  const { key, setText } = CardFix;
  let rows = [];

  const when = (iso) => {
    const d = new Date(iso.length === 10 ? `${iso}T00:00:00` : iso);
    const sameDay = d.toDateString() === new Date().toDateString();
    return sameDay
      ? `today ${d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}`
      : d.toLocaleDateString([], { month: "short", day: "numeric" });
  };

  function draw() {
    $("shown").textContent = rows.length ? `${rows.length} deleted card${rows.length === 1 ? "" : "s"}` : "Trash is empty.";
    $("rows").replaceChildren(...rows.map((r) => {
      const li = document.createElement("li");
      li.className = "crow trash";
      li.dataset.key = key(r);
      const body = document.createElement("div");
      body.className = "cbody";
      const q = document.createElement("p");
      q.className = "cq";
      setText(q, r.question);
      const a = document.createElement("p");
      a.className = "ca muted";
      setText(a, r.answer);
      const meta = document.createElement("p");
      meta.className = "cmeta";
      meta.textContent = `${r.course} · ${r.topic} · ${r.reason || "no reason"} · ${when(r.changed)}`;
      body.append(q, a, meta);
      const b = document.createElement("button");
      b.type = "button";
      b.className = "restore";
      b.textContent = "Restore";
      li.append(body, b);
      return li;
    }));
  }

  $("rows").addEventListener("click", async (e) => {
    const b = e.target.closest("button.restore");
    if (!b) return;
    const k = b.closest(".crow").dataset.key;
    const r = rows.find((x) => key(x) === k);
    b.disabled = true;
    try {
      await CardFix.restore([r], {});
      rows = rows.filter((x) => key(x) !== k);
      draw();
      CardFix.snack("Restored. It's back in your decks.");
    } catch (err) {
      b.disabled = false;
      CardFix.snack(`Not restored: ${err.message}`);
    }
  });

  (async () => {
    try {
      const res = await fetch("/api/trash", { cache: "no-store" });
      if (!res.ok) throw new Error(`server said ${res.status}`);
      rows = (await res.json()).cards;
      draw();
    } catch (e) {
      $("shown").textContent = `Couldn't load the trash: ${e.message}`;
    }
  })();
})();
