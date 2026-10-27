/* Guitar multi-effect page.  Everything is built from /api/info (parameter table),
   /api/state and /api/chain: no parameter or effect is named here, except the few
   special cases marked "special" (cabinet slots, dynamics meter, mute button, codec volumes). */
"use strict";
(function () {
  var h = GME.h, api = GME.api, toast = GME.toast;
  var S = {info: null, params: {}, state: null, controls: {}, chainSig: "", chain: null, chainBusy: 0, sel: null,
           editorSel: null, editorIds: [], sections: [], vals: {}, enableOf: {}, dirty: false, presets: [], cabBusy: false, online: false};

  /* ---------- controls bookkeeping ---------- */
  function onChange(id, value) {
    GME.sender.set(id, value);
    S.vals[id] = value;
    applyWhen();
    var p = S.params[id];
    if (p && p.group !== "system") markDirty();                  /* the loaded preset no longer matches */
    if (S.enableOf[id]) enableChanged(id, value);
  }
  function makeControl(p) {
    var c = GME.makeControl(p, onChange);
    S.controls[p.id] = c;
    return c;
  }
  GME.sender.onResult(function (values, err) {
    if (err) refresh(true);                    /* put the controls back to the real values */
  });

  /* ---------- state ---------- */
  function setOnline(ok, text) {
    S.online = ok;
    var c = document.getElementById("conn");
    c.className = "chip " + (ok ? "ok" : "bad");
    c.lastChild.textContent = text || (ok ? "connected" : "offline");
  }

  function refresh(force) {
    if (!force && (GME.sender.busy() || S.cabBusy || S.chainBusy)) return Promise.resolve();
    return api("GET", "/api/state").then(function (st) {
      setOnline(true);
      applyState(st);
    }).catch(function (e) { setOnline(false, "offline"); });
  }

  function applyState(st) {
    S.state = st;
    var s = st.status;
    document.getElementById("fpga").textContent = "FPGA " + hex4(s.version);
    chip("codec", s.codec_nak ? "codec NAK" : (s.codec_init_done ? "codec ok" : "codec init..."), s.codec_init_done && !s.codec_nak);
    chip("pll", s.pll_locked ? "PLL locked" : "PLL not locked", s.pll_locked);
    if (!S.chainBusy) renderChain(st.chain);                     /* not while a new order is on its way */
    Object.keys(st.values).forEach(function (id) {
      var c = S.controls[id];
      if (GME.sender.has(id) || (c && c.active)) return;
      S.vals[id] = st.values[id];
      if (c) c.update(st.values[id], st.raw[id]);
    });
    applyWhen();
    var mute = st.values.mute;                                   /* special: mute button */
    document.getElementById("mute").classList.toggle("on", !!mute);
    renderCab(st.cab);
  }
  function hex4(v) { return "0x" + ("0000" + v.toString(16).toUpperCase()).slice(-4); }
  function chip(id, text, ok) {
    var el = document.getElementById(id);
    el.textContent = text;
    el.className = "chip " + (ok ? "ok" : "bad");
  }

  /* ---------- effect chain: list of the unused effects, the chain of the used ones, editor ----------
     The FPGA always runs every effect, in the order of /api/chain; an effect that is off is bypassed in its
     place.  The page shows the chain "members" (/api/chain members: the effects the user put in, on or
     bypassed) in their order, and the others in the list beside it.  Putting an effect into the chain switches
     it on at that spot; its LED bypasses it there; taking it out switches it off (its place in the full order
     then does not matter and is left alone, so that costs no fade).  An effect that is on is always a member. */
  var SEL_KEY = "gme.selected";
  function paramsOf(group, skipId) {
    return S.info.params.filter(function (p) { return p.group === group && p.id !== skipId && p.available; });
  }
  function effectOf(id) {
    return S.chain.effects.filter(function (e) { return e.id === id; })[0];
  }
  function fxInfo(id) {
    return S.info.effects.filter(function (x) { return x.id === id; })[0] || {};
  }
  function shortName(e) { return fxInfo(e.id).short || e.name; }
  function icon(e) { return GME.icon(fxInfo(e.id).icon); }
  function kind(e) { return fxInfo(e.id).kind ? " k-" + fxInfo(e.id).kind : ""; }
  function active() {                                            /* the chain: ids of the members, in order */
    return S.chain.effects.filter(function (e) { return e.member; }).map(function (e) { return e.id; });
  }
  function markDirty() { S.dirty = true; showDirty(); }
  function showDirty() {
    var d = document.getElementById("preset-dirty");
    if (d) d.hidden = !S.dirty;
  }

  function renderChain(ch) {
    S.chain = ch;
    if (ch.order.indexOf(S.sel) < 0) {
      var saved = null;
      try { saved = localStorage.getItem(SEL_KEY); } catch (e) { /* storage not available */ }
      S.sel = ch.order.indexOf(saved) >= 0 ? saved : (active()[0] || ch.order[0] || null);
    }
    renderBoard();
    renderEditor(false);
  }

  function select(id) {
    S.sel = id;
    try { localStorage.setItem(SEL_KEY, id); } catch (e) { /* storage not available */ }
    renderBoard();
    renderEditor(false);
  }

  /* Chain and list are rebuilt when the order or the members change; on / off and the selection only patch
     them (keeps the focus where it is). */
  function renderBoard() {
    var ch = S.chain, act = active();
    var sig = ch.order.join(",") + "|" + act.join(",") + "|" + ch.editable;
    if (sig !== S.chainSig) {
      S.chainSig = sig;
      var f = document.activeElement, keep = f && f.getAttribute ? f.getAttribute("data-fx") : null;
      renderStrip(act);
      renderLib(act);
      if (keep) {
        var t = document.querySelector('[data-fx="' + keep + '"]');
        if (t) t.focus();
      }
    }
    Array.prototype.forEach.call(document.querySelectorAll("#tab-board [data-id]"), function (el) {
      var id = el.getAttribute("data-id"), sel = id === S.sel, e = effectOf(id);
      el.classList.toggle("sel", sel);
      var b = el.querySelector("[data-fx]");
      if (b) b.setAttribute("aria-pressed", sel ? "true" : "false");
      var led = el.querySelector(".led");
      if (led && e) {
        el.classList.toggle("on", !!e.on);
        led.setAttribute("aria-checked", e.on ? "true" : "false");
        led.title = (e.on ? "Bypass " : "Switch on ") + e.name;
      }
    });
    var def = defaultOrder().filter(function (id) { return act.indexOf(id) >= 0; });
    document.getElementById("order-default").disabled = !ch.editable || def.join(",") === act.join(",");
    document.getElementById("orderhint").textContent = (ch.editable
      ? "Drag an effect from the list into the chain, or back out to remove it. In the chain: the LED switches it on / off, drag or Alt+←/→ moves it, Delete takes it out. Changes apply at once (short fade)."
      : "Fixed order in this FPGA (VERSION " + S.info.fpga_version_hex + "): an effect you add goes to its fixed place. The LED switches an effect on / off.");
  }

  function renderStrip(act) {
    var box = document.getElementById("chain");
    GME.clear(box);
    box.appendChild(h("span", {class: "io", title: "Guitar input"}, "IN"));
    act.forEach(function (id, i) {                               /* first and last cable stretch: the pedals sit in the middle */
      box.appendChild(h("span", {class: i ? "conn" : "conn first", "aria-hidden": "true"}));
      box.appendChild(tile(effectOf(id), i, act.length));
    });
    if (!act.length) {
      box.appendChild(h("span", {class: "conn first", "aria-hidden": "true"}));
      box.appendChild(h("div", {class: "strip-empty"}, "The chain is empty: drag effects here from the list"));
    }
    box.appendChild(h("span", {class: "conn last", "aria-hidden": "true"}));
    box.appendChild(h("span", {class: "io", title: "Output"}, "OUT"));
  }

  function tile(e, i, n) {
    var btn = h("button", {type: "button", class: "tile-btn", "data-fx": e.id, title: e.name,
                           "aria-label": e.name + ", slot " + (i + 1) + " of " + n,
                           onclick: function () { select(e.id); },
                           onkeydown: function (ev) { tileKey(ev, e.id); }},
      icon(e), h("span", {class: "tname"}, shortName(e)), h("span", {class: "tslot"}, String(i + 1)));
    var led = h("button", {type: "button", class: "led", role: "switch", "aria-label": e.name + " on",
                           onclick: function (ev) { ev.stopPropagation(); setEnable(e.id, !effectOf(e.id).on); }});
    var rm = h("button", {type: "button", class: "tile-rm", title: "Take " + e.name + " out of the chain",
                          "aria-label": "Take " + e.name + " out", onclick: function (ev) { ev.stopPropagation(); removeFromChain(e.id); }}, "×");
    var t = h("div", {class: "tile" + kind(e), "data-id": e.id, draggable: "true"}, btn, led, rm);
    dragSource(t, e.id, "chain");
    dropOnTile(t, e.id);
    return t;
  }

  function renderLib(act) {
    var box = document.getElementById("fxlist");
    GME.clear(box);
    var present = S.chain.order;
    var rest = defaultOrder().concat(present.filter(function (id) { return S.info.chain_default.indexOf(id) < 0; }))
      .filter(function (id) { return act.indexOf(id) < 0; });
    rest.forEach(function (id) {
      var e = effectOf(id);
      var row = h("div", {class: "lib-row" + kind(e), "data-id": id, draggable: "true"},
        h("button", {type: "button", class: "lib-btn", "data-fx": id, title: "Show the settings of " + e.name,
                     onclick: function () { select(id); }}, icon(e), h("span", {class: "lib-name"}, e.name)),
        h("button", {type: "button", class: "lib-add", title: "Put " + e.name + " at the end of the chain",
                     "aria-label": "Add " + e.name, onclick: function () { addAt(id, active().length, true); }}, "+"));
      dragSource(row, id, "lib");
      box.appendChild(row);
    });
    if (!rest.length) box.appendChild(h("p", {class: "note"}, "Every effect is in the chain."));
  }

  function defaultOrder() {                                      /* info.chain_default, only the effects present */
    return S.info.chain_default.filter(function (id) { return S.chain.order.indexOf(id) >= 0; });
  }

  /* on / off (bypass) of one effect, optimistic; switching on an effect outside the chain puts it in */
  function setEnable(id, on) {
    var e = effectOf(id), p = e && S.params[e.enable];
    if (!(p && p.available)) return;
    if (S.controls[e.enable]) S.controls[e.enable].update(on, on ? 1 : 0);   /* the editor switch, when shown */
    onChange(e.enable, on);
  }
  function enableChanged(paramId, on) {
    var joined = false;
    S.chain.effects.forEach(function (e) {
      if (e.enable !== paramId) return;
      e.on = !!on;
      if (on && !e.member) { e.member = true; joined = true; }
    });
    if (joined) postChain(null, active());                       /* stays in the chain when it is bypassed later */
    renderBoard();
    renderEditor(false);
  }
  function removeFromChain(id) {                                 /* out of the chain = off (the server switches it off) */
    var e = effectOf(id);
    e.member = false;
    e.on = false;
    postChain(null, active());
  }

  /* Put effect id at position k of the chain (a member from then on); on = switch it on too (from the list).
     The full order only changes if it has to: the effect goes just before the effect that will follow it in
     the chain (or after the one before it). */
  function addAt(id, k, on) {
    var act = active().filter(function (x) { return x !== id; }), order = S.chain.order;
    if (S.chain.editable && act.length) {
      order = order.filter(function (x) { return x !== id; });
      order.splice(k < act.length ? order.indexOf(act[k]) : order.indexOf(act[act.length - 1]) + 1, 0, id);
    }
    var joins = !effectOf(id).member;
    function switchOn() { if (on && !effectOf(id).on) setEnable(id, true); }
    S.sel = id;
    var newOrder = order.join(",") !== S.chain.order.join(",") ? order : null;
    if (!newOrder && !joins) return switchOn();
    effectOf(id).member = true;
    postChain(newOrder, joins ? active() : null).then(function (ok) { if (ok) switchOn(); });
  }

  function tileKey(ev, id) {
    var k = ev.key, act = active(), i = act.indexOf(id);
    if (k === "Delete" || k === "Backspace") {
      ev.preventDefault();
      var next = act[i + 1] || act[i - 1];
      removeFromChain(id);
      if (next) document.querySelector('#chain [data-fx="' + next + '"]').focus();
      return;
    }
    if (k !== "ArrowLeft" && k !== "ArrowRight") return;
    var d = k === "ArrowLeft" ? -1 : 1;
    if (ev.altKey) {
      ev.preventDefault();                                       /* Alt+arrow is "back" in browsers */
      if (S.chain.editable && i + d >= 0 && i + d < act.length) addAt(id, i + d, false);
    } else if (!ev.ctrlKey && !ev.metaKey && !ev.shiftKey) {
      ev.preventDefault();
      var to = act[i + d];
      if (!to) return;
      select(to);
      document.querySelector('#chain [data-fx="' + to + '"]').focus();
    }
  }

  /* New full order and / or members (null = unchanged): shown at once, POSTed at once; resolves true when
     the board took it.  On an error the chain snaps back to the real state. */
  function postChain(order, members) {
    var body = {};
    if (order) {
      var byId = {};
      S.chain.effects.forEach(function (e) { byId[e.id] = e; });
      S.chain.order = order;
      S.chain.effects = order.map(function (id) { return byId[id]; });
      body.order = order;
    }
    if (members) body.members = members;
    if (!order && !members) return Promise.resolve(true);
    S.chainBusy++;
    renderBoard();
    renderEditor(false);
    return api("POST", "/api/chain", body).then(function (r) {
      markDirty();
      if (--S.chainBusy === 0) renderChain(r);
      return true;
    }).catch(function (e) {
      S.chainBusy--;
      toast(e.message, true);
      if (!S.chainBusy) refresh(true);
      return false;
    });
  }
  function moveTo(order) { return postChain(order.join(",") === S.chain.order.join(",") ? null : order, null); }

  /* ---------- drag and drop: list -> chain (switch on there), chain -> chain (move), chain -> list (off) ---------- */
  function dragSource(el, id, from) {
    el.addEventListener("dragstart", function (ev) {
      S.drag = {id: id, from: from};
      el.classList.add("drag");
      document.body.classList.add("dragging");
      ev.dataTransfer.setData("text/plain", id);
      ev.dataTransfer.effectAllowed = "move";
    });
    el.addEventListener("dragend", function () { el.classList.remove("drag"); endDrag(); });
  }
  function endDrag() {                                           /* also after a drop: the source may be gone by then */
    S.drag = null;
    document.body.classList.remove("dragging");
    Array.prototype.forEach.call(document.querySelectorAll(".ins-before, .ins-after, .drop-ok"), function (x) {
      x.classList.remove("ins-before", "ins-after", "drop-ok");
    });
  }
  function canDropInChain() { return S.drag && (S.drag.from === "lib" || S.chain.editable); }
  function dropOnTile(t, id) {
    function after(ev) {                                         /* right half of the tile = insert after it */
      var r = t.getBoundingClientRect();
      return ev.clientX >= r.left + r.width / 2;
    }
    t.addEventListener("dragover", function (ev) {
      if (!canDropInChain() || S.drag.id === id) return;
      ev.preventDefault();
      ev.stopPropagation();
      ev.dataTransfer.dropEffect = "move";
      var a = after(ev);
      t.classList.toggle("ins-after", a);
      t.classList.toggle("ins-before", !a);
    });
    t.addEventListener("dragleave", function () { t.classList.remove("ins-before", "ins-after"); });
    t.addEventListener("drop", function (ev) {
      var d = S.drag;
      ev.preventDefault();
      ev.stopPropagation();
      endDrag();
      if (!d || d.id === id) return;
      var act = active().filter(function (x) { return x !== d.id; });
      addAt(d.id, act.indexOf(id) + (after(ev) ? 1 : 0), d.from === "lib");
    });
  }
  function initDropZones() {
    var strip = document.getElementById("chain"), lib = document.getElementById("fxlib");
    strip.addEventListener("dragover", function (ev) {           /* on the strip, not on a tile: end of the chain */
      if (!canDropInChain()) return;
      ev.preventDefault();
      strip.classList.add("drop-ok");
    });
    strip.addEventListener("dragleave", function (ev) { if (!strip.contains(ev.relatedTarget)) strip.classList.remove("drop-ok"); });
    strip.addEventListener("drop", function (ev) {
      var d = S.drag;
      ev.preventDefault();
      endDrag();
      if (d) addAt(d.id, active().filter(function (x) { return x !== d.id; }).length, d.from === "lib");
    });
    lib.addEventListener("dragover", function (ev) {
      if (!S.drag || S.drag.from !== "chain") return;
      ev.preventDefault();
      lib.classList.add("drop-ok");
    });
    lib.addEventListener("dragleave", function (ev) { if (!lib.contains(ev.relatedTarget)) lib.classList.remove("drop-ok"); });
    lib.addEventListener("drop", function (ev) {
      var d = S.drag;
      ev.preventDefault();
      endDrag();
      if (d && d.from === "chain") removeFromChain(d.id);
    });
  }

  /* The editor is rebuilt only when another effect is selected; the header is patched. */
  function renderEditor(force) {
    var box = document.getElementById("editor"), e = S.sel && effectOf(S.sel);
    if (!e) { GME.clear(box); S.editorSel = null; return; }
    var act = active(), pos = act.indexOf(e.id);
    var where = pos < 0 ? "not in the chain (off)" : "slot " + (pos + 1) + " of " + act.length + (e.on ? "" : " · bypassed");
    var inout = e.member ? "Take out of the chain" : "Add to the chain";
    if (S.editorSel === S.sel && !force) {
      S.slotEl.textContent = where;
      S.inoutEl.textContent = inout;
      return;
    }
    S.editorSel = S.sel;
    GME.clear(box);
    (S.editorIds || []).forEach(function (id) { delete S.controls[id]; });
    S.editorIds = [];
    var enable = S.params[e.enable];
    S.slotEl = h("span", {class: "ed-slot"}, where);
    S.inoutEl = h("button", {class: "btn", disabled: !(enable && enable.available), onclick: function () {
      var x = effectOf(S.sel);
      if (x.member) removeFromChain(x.id); else addAt(x.id, active().length, true);
    }}, inout);
    var head = h("div", {class: "ed-head"}, icon(e), h("h2", {class: "ed-name"}, e.name), S.slotEl);
    if (enable && enable.available) {                            /* on / bypass, the same as the LED of the pedal */
      var sw = makeControl(enable);
      sw.el.className = "ctl switch";
      sw.el.title = "Switch " + e.name + " on or off (bypass)";
      head.appendChild(sw.el);
      S.editorIds.push(enable.id);
    }
    head.appendChild(S.inoutEl);
    var body = h("div", {class: "ed-body"});
    if (e.id === "dyn") {                                        /* special: live gain-reduction meter (DYN_GR) */
      body.appendChild(h("div", {class: "grmeter wide", title: "How much the dynamics stage turns the signal down (compressor and gate)"},
        h("label", {}, "Gain reduction"),
        h("div", {class: "bar"}, h("div", {id: "gr-bar"})),
        h("span", {id: "gr-text"}, "0.0 dB")));
    }
    if (e.id === "cab") {                                        /* special: cabinet slots */
      body.appendChild(h("div", {id: "cabbody", class: "cabbody wide"}));
    } else {
      layoutControls(body, paramsOf(e.id, e.enable));
    }
    box.appendChild(h("div", {class: "card" + kind(e), "data-ed": e.id}, head, body));
    S.editorIds.forEach(function (id) {                          /* the new controls start from the last state */
      if (S.state && id in S.state.values) S.controls[id].update(S.state.values[id], S.state.raw[id]);
    });
    applyWhen();
    if (S.state) renderCab(S.state.cab);
  }

  /* Controls without "section" first, then one framed section per "section" name (in table order).  A
     "section_switch" bool goes into the section title and dims the section while it is off. */
  function layoutControls(body, params) {
    var secs = {};
    S.sections = [];
    params.forEach(function (p) {
      var c = makeControl(p);
      S.editorIds.push(p.id);
      if (!p.section) return body.appendChild(c.el);
      var s = secs[p.section];
      if (!s) {
        s = secs[p.section] = {head: h("div", {class: "sec-head"}, h("span", {class: "sec-title"}, p.section)),
                               body: h("div", {class: "sec-body"}), sw: null};
        s.el = h("div", {class: "sec"}, s.head, s.body);
        body.appendChild(s.el);
        S.sections.push(s);
      }
      if (p.section_switch && p.type === "bool") {
        c.el.className = "ctl switch";
        c.el.title = "Switch " + p.section.toLowerCase() + " on or off";
        s.head.insertBefore(c.el, s.head.firstChild);
        s.sw = p.id;
      } else {
        s.body.appendChild(c.el);
      }
    });
  }

  /* dims a section whose switch is off and a control whose "gui_when" does not hold (it stays usable) */
  function applyWhen() {
    (S.sections || []).forEach(function (s) { if (s.sw) s.el.classList.toggle("off", !S.vals[s.sw]); });
    S.editorIds.forEach(function (id) {
      var p = S.params[id], w = p.gui_when, c = S.controls[id];
      if (!w || !c) return;
      var ok = w["in"].indexOf(S.vals[w.param]) >= 0;
      c.el.classList.toggle("inactive", !ok);
      c.el.setAttribute("data-when", ok ? "" : "used only when " + title(S.params[w.param]) + " is " + w["in"].join(" / "));
    });
  }
  function title(p) { return p ? (p.gui_label || p.name) : "?"; }

  /* ---------- cabinet (special) ---------- */
  function renderCab(cab) {
    var box = document.getElementById("cabbody");
    if (!box) return;
    GME.clear(box);
    if (!cab.available) {
      box.appendChild(h("p", {class: "note"}, "No cabinet simulator in this FPGA image."));
      return;
    }
    box.appendChild(h("p", {class: "note"}, "Active bank " + cab.active_bank + " · loaded slot " +
      (cab.slot === null ? "unknown" : cab.slot) + (S.cabBusy ? " · loading..." : "")));
    if (!cab.slots.length) box.appendChild(h("p", {class: "note"}, "No cabNN.coef files found on the board."));
    cab.slots.forEach(function (s) {
      var b = h("button", {class: "btn slot" + (s.slot === cab.slot ? " current" : ""), disabled: S.cabBusy || !!s.error,
                           title: s.error || ("shift " + s.shift),
                           onclick: function () { loadCab(s.slot, s.name); }},
        h("b", {}, String(s.slot)), " ", s.name);
      box.appendChild(b);
    });
  }
  function loadCab(slot, name) {
    S.cabBusy = true;
    renderCab(S.state.cab);
    api("POST", "/api/cab", {slot: slot}).then(function () { markDirty(); toast("Cabinet loaded: " + name); })
      .catch(function (e) { toast(e.message, true); })
      .then(function () { S.cabBusy = false; return refresh(true); });
  }

  /* ---------- presets ---------- */
  function renderPresetBar() {
    var bar = document.getElementById("presetbar");
    GME.clear(bar);
    var sel = h("select", {id: "preset-sel", "aria-label": "Preset"});
    [[true, "Factory"], [false, "User"]].forEach(function (g) {
      var items = S.presets.filter(function (p) { return p.factory === g[0]; });
      if (!items.length) return;
      var og = h("optgroup", {label: g[1]});
      items.forEach(function (p) { og.appendChild(h("option", {value: p.name, title: p.description || ""}, p.name)); });
      sel.appendChild(og);
    });
    function cur() { return S.presets.filter(function (p) { return p.name === sel.value; })[0]; }
    /* selecting a preset loads it */
    sel.addEventListener("change", function () {
      var n = sel.value;
      api("POST", "/api/presets/" + encodeURIComponent(n)).then(function (r) {
        S.selectedPreset = n;
        S.dirty = false; showDirty();
        toast("Preset loaded: " + n);
        (r.warnings || []).forEach(function (w) { toast(w, true); });
        refresh(true);
      }).catch(function (e) {
        toast(e.message, true);
        sel.value = S.selectedPreset;
      });
    });
    function doSave(n, overwrite) {
      api("POST", "/api/presets", {name: n, overwrite: overwrite}).then(function () {
        toast("Preset saved: " + n);
        S.dirty = false; showDirty();
        return loadPresets(n);
      }).catch(function (e) {
        if (!overwrite && /exists/.test(e.message) && confirm("Overwrite preset '" + n + "'?")) doSave(n, true);
        else toast(e.message, true);
      });
    }
    function saveAs() {
      var c = cur();
      var n = prompt("Name of the new preset", c && !c.factory ? c.name : "");
      if (n === null || !n.trim()) return;
      doSave(n.trim(), false);
    }
    bar.appendChild(h("label", {"for": "preset-sel"}, "Preset"));
    bar.appendChild(sel);
    bar.appendChild(h("span", {id: "preset-dirty", class: "dirty", hidden: true, title: "changed since the preset was loaded or saved"}, "*"));
    bar.appendChild(h("button", {class: "btn", title: "Overwrite the selected user preset with the current settings (a factory preset: same as Save as)", onclick: function () {
      var c = cur();
      if (!c || c.factory) return saveAs();
      if (confirm("Overwrite preset '" + c.name + "' with the current settings?")) doSave(c.name, true);
    }}, "Save"));
    bar.appendChild(h("button", {class: "btn", title: "Save the current settings under a new name", onclick: saveAs}, "Save as"));
    bar.appendChild(h("button", {class: "btn danger", title: "Delete the selected user preset", onclick: function () {
      var c = cur();
      if (!c || c.factory) return toast("Factory presets cannot be deleted", true);
      if (!confirm("Delete preset '" + c.name + "'?")) return;
      api("DELETE", "/api/presets/" + encodeURIComponent(c.name)).then(function () {
        toast("Preset deleted"); return loadPresets();
      }).catch(function (e) { toast(e.message, true); });
    }}, "Delete"));
    sel.selectedIndex = Math.max(0, S.presets.map(function (p) { return p.name; }).indexOf(S.selectedPreset));
    showDirty();
  }
  function loadPresets(select, onlyIfChanged) {
    if (select) S.selectedPreset = select;
    return api("GET", "/api/presets").then(function (r) {
      var sig = JSON.stringify(r.presets);
      if (onlyIfChanged && sig === S.presetSig) return;
      var keep = document.getElementById("preset-sel") ? document.getElementById("preset-sel").value : null;
      S.presetSig = sig; S.presets = r.presets;
      if (keep && !select) S.selectedPreset = keep;
      renderPresetBar();
    })
      .catch(function (e) { toast(e.message, true); });
  }

  /* ---------- settings tab ---------- */
  function throttled(fn) {                                       /* <= 20 calls/s, last value kept */
    var last = 0, timer = null, arg;
    return function (v) {
      arg = v;
      if (timer) return;
      timer = setTimeout(function () { timer = null; last = Date.now(); fn(arg); }, Math.max(0, 50 - (Date.now() - last)));
    };
  }
  function codecSlider(name, help, reg, lo, hi, def, build, show) {   /* special: WM8731 volumes */
    var cid = "codec-" + reg;
    var out = h("output", {class: "ctl-val", "for": cid}, show(def));
    var send = throttled(function (v) {
      api("POST", "/api/codec", {reg: reg, value: build(v)}).catch(function (e) { toast(e.message, true); });
    });
    var rng = h("input", {type: "range", id: cid, "aria-label": name, title: help, min: lo, max: hi, step: 1, value: def, oninput: function () {
      var v = parseInt(rng.value, 10);
      out.textContent = show(v);
      rng.setAttribute("aria-valuetext", out.textContent);
      send(v);
    }});
    return h("div", {class: "ctl"}, h("div", {class: "ctl-head"}, h("label", {class: "ctl-name", "for": cid, title: help}, name),
      h("span", {class: "help", title: help, "aria-hidden": "true"}, "?"), out), rng);
  }
  function renderSettings() {
    var box = document.getElementById("tab-settings");
    GME.clear(box);
    var info = S.info;
    box.appendChild(h("div", {class: "panel"}, h("h2", {}, "Codec volumes"),
      h("p", {class: "note"}, "The WM8731 cannot be read back: the sliders start at the codec defaults and only send changes."),
      codecSlider("Headphone / line out volume", "WM8731 register 2 (both channels), 48 = mute, 121 = 0 dB", 2, 48, 127, 121,
        function (v) { return 0x100 | v; }, function (v) { return v === 48 ? "mute" : (v - 121) + " dB"; }),
      codecSlider("Line in volume", "WM8731 register 0 (both channels), 23 = 0 dB, 1.5 dB steps", 0, 0, 31, 23,
        function (v) { return 0x100 | v; }, function (v) { return ((v - 23) * 1.5).toFixed(1) + " dB"; })));
    var other = info.params.filter(function (p) { return p.group === "system" && p.id !== "mute" && p.available; });
    if (other.length) {
      var pn = h("div", {class: "panel"}, h("h2", {}, "System"));
      other.forEach(function (p) { pn.appendChild(makeControl(p).el); });
      box.appendChild(pn);
    }
    box.appendChild(h("div", {class: "panel"}, h("h2", {}, "Network and versions"),
      h("table", {class: "kv"},
        row("This page served from", location.host),
        row("Board address", location.hostname),
        row("Web UI software", info.software_version),
        row("FPGA VERSION", info.fpga_version_hex),
        row("Backend", info.mock ? "MOCK (no hardware)" : "/dev/mem"),
        row("Parameters", String(info.params.filter(function (p) { return p.available; }).length) + " of " + info.params.length + " available"))));
  }
  function row(k, v) { return h("tr", {}, h("th", {}, k), h("td", {}, v)); }

  /* ---------- expert tab ---------- */
  function renderExpert() {
    var box = document.getElementById("tab-expert");
    GME.clear(box);
    var reg = h("input", {type: "text", id: "raw-reg", placeholder: "register (0x1B or name)", "aria-label": "Register", size: 18});
    var val = h("input", {type: "text", id: "raw-val", placeholder: "value (0x0000)", "aria-label": "Value", size: 12});
    var res = h("span", {class: "note"}, "");
    function num(t) { return /^\s*(0x[0-9a-f]+|\d+)\s*$/i.test(t) ? parseInt(t, 0) : null; }
    function show(r) { res.textContent = "reg 0x" + r.reg.toString(16).toUpperCase() + " = " + r.hex; }
    box.appendChild(h("div", {class: "panel"}, h("h2", {}, "Raw register access"),
      h("div", {class: "bar-row"}, reg, val,
        h("button", {class: "btn", onclick: function () {
          api("GET", "/api/raw/" + encodeURIComponent(reg.value.trim())).then(function (r) { show(r); val.value = r.hex; renderRegs(); })
            .catch(function (e) { toast(e.message, true); });
        }}, "Read"),
        h("button", {class: "btn", onclick: function () {
          var v = num(val.value);
          if (v === null) return toast("value: a number such as 0x0004 or 4", true);
          api("POST", "/api/raw/" + encodeURIComponent(reg.value.trim()), {value: v}).then(function (r) { show(r); refresh(true); renderRegs(); })
            .catch(function (e) { toast(e.message, true); });
        }}, "Write"), res),
      h("p", {class: "note"}, "Writes go straight to the register; the FPGA ignores read-only registers.")));
    var tbl = h("table", {class: "regs"});
    box.appendChild(h("div", {class: "panel"}, h("h2", {}, "All registers"),
      h("button", {class: "btn", onclick: renderRegs}, "Refresh"), tbl));
    function renderRegs() {
      api("GET", "/api/raw").then(function (r) {
        GME.clear(tbl);
        tbl.appendChild(h("tr", {}, h("th", {}, "reg"), h("th", {}, "name"), h("th", {}, "R/W"), h("th", {}, "value"), h("th", {}, "")));
        r.registers.forEach(function (x) {
          tbl.appendChild(h("tr", {class: "clickable", onclick: function () {
            reg.value = "0x" + x.reg.toString(16).toUpperCase(); val.value = hex4(x.value);
          }}, h("td", {}, "0x" + ("0" + x.reg.toString(16).toUpperCase()).slice(-2)), h("td", {}, x.name), h("td", {}, x.rw),
            h("td", {class: "mono"}, hex4(x.value)),
            h("td", {class: "mono"}, String(x.value))));
        });
      }).catch(function (e) { toast(e.message, true); });
    }
    renderRegs();
  }

  /* ---------- levels ---------- */
  var GR_FULL_SCALE_DB = 24;
  function showLevels(e) {
    [["in", e.in, e.in_db], ["out", e.out, e.out_db]].forEach(function (x) {
      var db = x[2] === null ? -60 : Math.max(-60, x[2]);
      document.getElementById("m-" + x[0]).style.width = ((db + 60) / 60 * 100).toFixed(1) + "%";
      document.getElementById("t-" + x[0]).textContent = x[2] === null ? "-inf" : x[2].toFixed(0) + " dB";
    });
    var grBar = document.getElementById("gr-bar"), grText = document.getElementById("gr-text");   /* only while the dynamics effect is selected */
    if (grBar && grText) {
      var gr = typeof e.gain_reduction === "number" ? e.gain_reduction : 0;
      grBar.style.width = (Math.min(gr, GR_FULL_SCALE_DB) / GR_FULL_SCALE_DB * 100).toFixed(1) + "%";
      grText.textContent = gr.toFixed(1) + " dB";
    }
  }
  function startLevels() {
    var poll = null;
    function polling() {
      if (poll) return;
      (function tick() {                       /* 10 Hz; every 3 s while the board does not answer */
        api("GET", "/api/levels").then(function (e) { showLevels(e); poll = setTimeout(tick, 100); })
          .catch(function () { setOnline(false, "offline"); poll = setTimeout(tick, 3000); });
      })();
    }
    if (!window.EventSource) return polling();
    var es = new EventSource("/api/levels/stream");
    es.onmessage = function (ev) { try { showLevels(JSON.parse(ev.data)); } catch (e) { /* ignore */ } };
    es.onerror = function () {
      /* the browser retries by itself; if the stream is dead, poll instead */
      if (es.readyState === 2) polling();
      else setTimeout(function () { if (es.readyState !== 1) { es.close(); polling(); } }, 3000);
    };
  }

  /* ---------- tabs, mute, start ---------- */
  function initTabs() {
    var btns = document.querySelectorAll("#tabs button");
    Array.prototype.forEach.call(btns, function (b) {
      b.addEventListener("click", function () {
        Array.prototype.forEach.call(btns, function (x) { x.classList.toggle("active", x === b); });
        ["board", "settings", "expert"].forEach(function (t) {
          document.getElementById("tab-" + t).hidden = (t !== b.getAttribute("data-tab"));
        });
        if (b.getAttribute("data-tab") === "expert") renderExpert();
      });
    });
  }

  function start() {
    initTabs();
    document.getElementById("mute").addEventListener("click", function () {
      var on = !document.getElementById("mute").classList.contains("on");
      document.getElementById("mute").classList.toggle("on", on);
      GME.sender.set("mute", on);
    });
    api("GET", "/api/info").then(function (info) {
      S.info = info;
      GME.fpgaVersion = info.fpga_version;
      info.params.forEach(function (p) { S.params[p.id] = p; });
      info.effects.forEach(function (e) { S.enableOf[e.enable] = e.id; });
      document.getElementById("order-default").addEventListener("click", function () { moveTo(defaultOrder()); });
      initDropZones();
      if (!S.params.mute || !S.params.mute.available) document.getElementById("mute").hidden = true;
      renderSettings();
      return Promise.all([loadPresets(), refresh(true)]);
    }).then(function () {
      startLevels();
      setInterval(function () { refresh(false); loadPresets(null, true); }, 3000);
      document.addEventListener("visibilitychange", function () { if (!document.hidden) refresh(true); });
    }).catch(function (e) { setOnline(false, "offline"); toast(e.message, true); });
  }
  start();
})();
