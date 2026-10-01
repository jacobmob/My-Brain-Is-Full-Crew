// Fixing bad cards (0.13), shared by /review, /cards and /trash.
// Delete: immediate, 10-second Undo, optional one-tap reason. Edit: live KaTeX preview,
// reset-schedule tick. Flag: optional note. The server records everything in card-edits/.
(() => {
  const $ = (id) => document.getElementById(id);
  const UNDO_MS = 10000;
  const key = (c) => `${c.course}/${c.topic}/${c.id}`;
  const ref = (c) => ({ course: c.course, topic: c.topic, id: c.id });
  let reasons = ["wrong", "vague", "duplicate", "too easy", "not in my course"];

  function math(el) {
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
  }
  const setText = (el, text) => { el.textContent = text || ""; math(el); };

  async function post(path, body) {
    const res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
    const out = await res.json().catch(() => ({}));
    if (!res.ok) {
      const d = out.detail;
      throw new Error(typeof d === "string" ? d : `server said ${res.status}`);
    }
    return out;
  }

  const one = (card, action, body) =>
    post(`/api/card/${[card.course, card.topic, card.id].map(encodeURIComponent).join("/")}/${action}`, body);

  async function bulk(action, cards, extra) {
    const out = await post("/api/cards/bulk", { action, items: cards.map(ref), ...extra });
    if (out.failed.length && !out.cards.length) throw new Error(out.failed[0].error);
    return out;
  }

  // ---------- snackbar ----------
  let snackTimer = null, snackUndo = null;

  function hideSnack() {
    clearTimeout(snackTimer);
    snackUndo = null;
    $("snackbar").hidden = true;
  }

  function snack(msg, { undo = null, reasonFor = null } = {}) {
    clearTimeout(snackTimer);
    $("snack-msg").textContent = msg;
    snackUndo = undo;
    $("snack-undo").hidden = !undo;
    const chips = $("snack-reasons");
    chips.hidden = !reasonFor;
    if (reasonFor) {
      chips.replaceChildren(...reasons.map((r) => {
        const b = document.createElement("button");
        b.type = "button";
        b.textContent = r;
        b.onclick = async () => {
          chips.querySelectorAll("button").forEach((x) => (x.disabled = true));
          try {
            await Promise.all(reasonFor.map((c) => one(c, "reason", { reason: r })));
            b.classList.add("on");
          } catch (e) {
            chips.querySelectorAll("button").forEach((x) => (x.disabled = false));
            $("snack-msg").textContent = `Reason not saved: ${e.message}`;
          }
        };
        return b;
      }));
    }
    $("snackbar").hidden = false;
    snackTimer = setTimeout(hideSnack, undo ? UNDO_MS : 4000);
  }

  $("snack-undo").addEventListener("click", async () => {
    const fn = snackUndo;
    hideSnack();
    if (fn) {
      try { await fn(); } catch (e) { snack(`Undo failed: ${e.message}`); }
    }
  });

  // ---------- actions ----------
  // hooks: onRemoved(cards), onRestored(cards), onEdited(card) -- each gets the server's rows.

  async function restore(cards, hooks) {
    const out = await bulk("restore", cards);
    hooks.onRestored && hooks.onRestored(out.cards);
    return out;
  }

  async function del(cards, hooks = {}) {
    try {
      const out = await bulk("delete", cards);
      hooks.onRemoved && hooks.onRemoved(out.cards);
      const n = out.cards.length;
      const failed = out.failed.length ? ` (${out.failed.length} failed)` : "";
      snack(`Deleted ${n === 1 ? "card" : `${n} cards`}${failed}. Why?`, {
        undo: () => restore(out.cards, hooks),
        reasonFor: out.cards,
      });
    } catch (e) {
      snack(`Not deleted: ${e.message}`);
    }
  }

  function flag(cards, hooks = {}) {
    const dlg = $("fix-flag");
    $("fix-flag-title").textContent = cards.length === 1 ? "Flag for rewrite" : `Flag ${cards.length} cards for rewrite`;
    $("fix-note").value = cards.length === 1 ? cards[0].note || "" : "";
    $("fix-flag-err").hidden = true;
    $("fix-flag-form").onsubmit = async (e) => {
      e.preventDefault();
      const btn = e.submitter;
      if (btn) btn.disabled = true;
      try {
        const out = await bulk("flag", cards, { note: $("fix-note").value });
        dlg.close();
        hooks.onRemoved && hooks.onRemoved(out.cards);
        const n = out.cards.length;
        snack(`Flagged ${n === 1 ? "card" : `${n} cards`} for rewrite.`, { undo: () => restore(out.cards, hooks) });
      } catch (err) {
        $("fix-flag-err").textContent = err.message;
        $("fix-flag-err").hidden = false;
      } finally {
        if (btn) btn.disabled = false;
      }
    };
    dlg.showModal();
    $("fix-note").focus();
  }

  function edit(card, hooks = {}) {
    const dlg = $("fix-edit");
    const q = $("fix-q"), a = $("fix-a");
    q.value = card.question || "";
    a.value = card.answer || "";
    $("fix-reset").checked = false;
    $("fix-edit-err").hidden = true;
    let t = null;
    // Preview only text that has math in it; plain text would just repeat the box above.
    const hasMath = (s) => /\$|\\\(|\\\[/.test(s);
    const preview = () => {
      setText($("fix-q-prev"), hasMath(q.value) ? q.value : "");
      setText($("fix-a-prev"), hasMath(a.value) ? a.value : "");
    };
    q.oninput = a.oninput = () => { clearTimeout(t); t = setTimeout(preview, 120); };
    preview();
    $("fix-edit-form").onsubmit = async (e) => {
      e.preventDefault();
      const btn = e.submitter;
      if (btn) btn.disabled = true;
      try {
        const row = await one(card, "edit", {
          question: q.value, answer: a.value, reset_schedule: $("fix-reset").checked,
        });
        dlg.close();
        hooks.onEdited && hooks.onEdited(row);
        snack(row.status === "edited" ? "Card updated." : "Card back to its original text.");
      } catch (err) {
        $("fix-edit-err").textContent = err.message;
        $("fix-edit-err").hidden = false;
      } finally {
        if (btn) btn.disabled = false;
      }
    };
    dlg.showModal();
  }

  function openMenu(card, hooks = {}) {
    const dlg = $("fix-menu");
    $("fix-menu-title").textContent = card.question || "";
    dlg.querySelector('[data-fix="edit"]').hidden = card.status === "flagged";
    dlg.onclick = (e) => {
      const b = e.target.closest("button[data-fix]");
      if (e.target === dlg) return dlg.close();   // tap on the backdrop
      if (!b) return;
      dlg.close();
      run(b.dataset.fix, card, hooks);
    };
    dlg.showModal();
  }

  function run(action, card, hooks) {
    if (action === "delete") del([card], hooks);
    else if (action === "flag") flag([card], hooks);
    else if (action === "edit" && card.status !== "flagged") edit(card, hooks);
  }

  // Close buttons and backdrop taps on the form dialogs
  document.querySelectorAll("dialog").forEach((dlg) => {
    dlg.addEventListener("click", (e) => {
      if (e.target === dlg || e.target.closest("[data-close]")) dlg.close();
    });
  });

  const dialogOpen = () => !!document.querySelector("dialog[open]");
  const typing = (e) => e.target.closest && e.target.closest("input, textarea, select");

  // D/E/F on whichever card the page says is current (iPad/desktop keyboards).
  function shortcuts(getCard, hooks) {
    document.addEventListener("keydown", (e) => {
      if (e.metaKey || e.ctrlKey || e.altKey || dialogOpen() || typing(e)) return;
      const k = e.key.toLowerCase();
      const action = { d: "delete", e: "edit", f: "flag" }[k];
      const card = action && getCard();
      if (!card) return;
      e.preventDefault();
      run(action, card, hooks);
    });
  }

  window.CardFix = {
    key, math, setText, post, one, bulk, snack, hideSnack, restore,
    del, flag, edit, openMenu, shortcuts, dialogOpen, typing,
    setReasons: (r) => { if (r && r.length) reasons = r; },
  };
})();
