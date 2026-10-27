/* Guitar multi-effect page.  Everything is built from /api/info (parameter table),
   /api/state and /api/chain: no parameter or effect is named here, except the few
   special cases marked "special" (cabinet slots, dynamics meter, mute button, codec volumes). */
"use strict";
(function () {
  var h = GME.h, api = GME.api, toast = GME.toast;
  var S = {info: null, params: {}, state: null, controls: {}, chainSig: "", chain: null, chainBusy: 0, sel: null,
           editorSel: null, editorIds: [], enableOf: {}, dirty: false, presets: [], cabBusy: false, online: false};

  /* ---------- controls bookkeeping ---------- */
  function onChange(id, value) {
    GME.sender.set(id, value);
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
      if (c && !c.active && !GME.sender.has(id)) c.update(st.values[id], st.raw[id]);
    });
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

  /* ---------- effect chain: strip of pedals + editor of the selected one ---------- */
  var SEL_KEY = "gme.selected";
  function paramsOf(group, skipId) {
    return S.info.params.filter(function (p) { return p.group === group && p.id !== skipId && p.available; });
  }
  function effectOf(id) {
    return S.chain.effects.filter(function (e) { return e.id === id; })[0];
  }
  function shortName(e) {
    var info = S.info.effects.filter(function (x) { return x.id === e.id; })[0];
    return (info && info.short) || e.name;
  }
  function markDirty() { S.dirty = true; showDirty(); }
  function showDirty() {
    var d = document.getElementById("preset-dirty");
    if (d) d.hidden = !S.dirty;
  }

  function renderChain(ch) {
    S.chain = ch;
    var ids = ch.order;
    if (ids.indexOf(S.sel) < 0) {
      var saved = null;
      try { saved = localStorage.getItem(SEL_KEY); } catch (e) { /* storage not available */ }
      S.sel = ids.indexOf(saved) >= 0 ? saved : (ids[0] || null);
    }
    renderStrip();
    renderEditor(false);
  }

  function select(id) {
    S.sel = id;
    try { localStorage.setItem(SEL_KEY, id); } catch (e) { /* storage not available */ }
    renderStrip();
    renderEditor(false);
  }

  /* The strip is rebuilt when the order changes; on/off and selection only patch the tiles
     (keeps the focus where it is). */
  function renderStrip() {
    var ch = S.chain, box = document.getElementById("chain");
    var sig = ch.order.join(",") + "|" + ch.editable;
    if (sig !== S.chainSig) {
      S.chainSig = sig;
      var f = document.activeElement, keep = null;
      if (box.contains(f) && f.getAttribute("data-fx")) keep = {id: f.getAttribute("data-fx"), role: f.getAttribute("data-role")};
      GME.clear(box);
      box.appendChild(h("span", {class: "io", title: "Guitar input"}, "IN"));
      ch.effects.forEach(function (e) {
        box.appendChild(h("span", {class: "conn", "aria-hidden": "true"}));
        box.appendChild(tile(e, ch.editable));
      });
      box.appendChild(h("span", {class: "conn", "aria-hidden": "true"}));
      box.appendChild(h("span", {class: "io", title: "Output"}, "OUT"));
      if (keep) {
        var t = box.querySelector('[data-fx="' + keep.id + '"][data-role="' + keep.role + '"]');
        if (t) t.focus();
      }
    }
    updateTiles();
  }

  function updateTiles() {
    var ch = S.chain, n = ch.order.length;
    ch.effects.forEach(function (e, i) {
      var t = document.querySelector('#chain .tile[data-id="' + e.id + '"]');
      if (!t) return;
      var sel = e.id === S.sel;
      t.classList.toggle("on", !!e.on);
      t.classList.toggle("sel", sel);
      var led = t.querySelector(".led"), btn = t.querySelector(".tile-btn");
      led.setAttribute("aria-checked", e.on ? "true" : "false");
      led.title = "Switch " + e.name + (e.on ? " off" : " on");
      led.setAttribute("aria-label", e.name + " " + (e.on ? "on" : "off"));
      btn.setAttribute("aria-pressed", sel ? "true" : "false");
      btn.setAttribute("aria-label", e.name + ", slot " + (i + 1) + " of " + n + ", " + (e.on ? "on" : "off"));
      t.querySelector(".tslot").textContent = String(i + 1);
    });
    document.getElementById("order-default").disabled = !ch.editable || defaultOrder().join(",") === ch.order.join(",");
    document.getElementById("orderhint").textContent = ch.editable
      ? "Drag a pedal, or Alt+←/→, to move it. Changes apply immediately (short fade)."
      : "Fixed order in this FPGA (VERSION " + S.info.fpga_version_hex + ").";
  }

  function defaultOrder() {                                      /* info.chain_default, only the effects present */
    return S.info.chain_default.filter(function (id) { return S.chain.order.indexOf(id) >= 0; });
  }

  function tile(e, editable) {
    var enable = S.params[e.enable];
    var led = h("button", {type: "button", class: "led", role: "switch", "data-fx": e.id, "data-role": "led",
                           disabled: !(enable && enable.available),
                           onclick: function (ev) { ev.stopPropagation(); setEnable(e.id, !effectOf(e.id).on); }});
    var btn = h("button", {type: "button", class: "tile-btn", "data-fx": e.id, "data-role": "btn",
                           onclick: function () { select(e.id); },
                           onkeydown: function (ev) { tileKey(ev, e.id); }},
      h("span", {class: "tname"}, shortName(e)), h("span", {class: "tslot"}, ""));
    var t = h("div", {class: "tile", "data-id": e.id, draggable: editable ? "true" : null}, led, btn);
    if (editable) enableDrag(t);
    return t;
  }

  /* LED and editor switch both end up in onChange (see enableChanged) */
  function setEnable(id, on) {
    var e = effectOf(id);
    if (e && S.params[e.enable]) {
      var c = S.controls[e.enable];
      if (c) c.update(on, on ? 1 : 0);                           /* the editor switch, when it is shown */
      onChange(e.enable, on);
    }
  }
  function enableChanged(paramId, on) {                          /* optimistic update of the strip */
    S.chain.effects.forEach(function (e) { if (e.enable === paramId) e.on = !!on; });
    updateTiles();
  }

  function tileKey(ev, id) {
    var k = ev.key;
    if (k !== "ArrowLeft" && k !== "ArrowRight") return;
    var order = S.chain.order, i = order.indexOf(id), d = k === "ArrowLeft" ? -1 : 1;
    if (ev.altKey) {
      ev.preventDefault();                                       /* Alt+arrow is "back" in browsers */
      var j = i + d;
      if (!S.chain.editable || j < 0 || j >= order.length) return;
      var next = order.slice();
      next.splice(i, 1);
      next.splice(j, 0, id);
      moveTo(next);
    } else if (!ev.ctrlKey && !ev.metaKey && !ev.shiftKey) {
      ev.preventDefault();
      var to = order[i + d];
      if (!to) return;
      select(to);
      document.querySelector('#chain .tile-btn[data-fx="' + to + '"]').focus();
    }
  }

  /* New order: shown at once, POSTed at once.  On an error the strip snaps back to the real order. */
  function moveTo(order) {
    if (order.join(",") === S.chain.order.join(",")) return;
    var byId = {};
    S.chain.effects.forEach(function (e) { byId[e.id] = e; });
    S.chain.order = order;
    S.chain.effects = order.map(function (id) { return byId[id]; });
    S.chainBusy++;
    renderStrip();
    renderEditor(false);
    api("POST", "/api/chain", {order: order}).then(function (r) {
      markDirty();
      if (--S.chainBusy === 0) renderChain(r);
    }).catch(function (e) {
      S.chainBusy--;
      toast(e.message, true);
      if (!S.chainBusy) refresh(true);
    });
  }

  function enableDrag(t) {
    var id = t.getAttribute("data-id");
    function clear() { t.classList.remove("ins-before", "ins-after"); }
    function after(ev) {                                         /* right half of the tile = insert after it */
      var r = t.getBoundingClientRect();
      return ev.clientX >= r.left + r.width / 2;
    }
    t.addEventListener("dragstart", function (ev) {
      S.dragId = id;
      t.classList.add("drag");
      ev.dataTransfer.setData("text/plain", id);
      ev.dataTransfer.effectAllowed = "move";
    });
    t.addEventListener("dragend", function () {
      S.dragId = null;
      t.classList.remove("drag");
      Array.prototype.forEach.call(document.querySelectorAll("#chain .tile"), function (x) { x.classList.remove("ins-before", "ins-after"); });
    });
    t.addEventListener("dragover", function (ev) {
      if (!S.dragId) return;
      ev.preventDefault();
      ev.dataTransfer.dropEffect = "move";
      var a = after(ev);
      t.classList.toggle("ins-after", a);
      t.classList.toggle("ins-before", !a);
    });
    t.addEventListener("dragleave", clear);
    t.addEventListener("drop", function (ev) {
      ev.preventDefault();
      clear();
      var from = S.dragId;
      S.dragId = null;
      if (!from || from === id) return;
      var order = S.chain.order.filter(function (x) { return x !== from; });
      order.splice(order.indexOf(id) + (after(ev) ? 1 : 0), 0, from);
      moveTo(order);
      var b = document.querySelector('#chain .tile-btn[data-fx="' + from + '"]');
      if (b) b.focus();
    });
  }

  /* The editor is rebuilt only when another effect is selected; the header text is patched. */
  function renderEditor(force) {
    var box = document.getElementById("editor"), e = S.sel && effectOf(S.sel);
    if (!e) { GME.clear(box); S.editorSel = null; return; }
    var slot = "slot " + (S.chain.order.indexOf(e.id) + 1) + " of " + S.chain.order.length;
    if (S.editorSel === S.sel && !force) { S.slotEl.textContent = slot; return; }
    S.editorSel = S.sel;
    GME.clear(box);
    (S.editorIds || []).forEach(function (id) { delete S.controls[id]; });
    S.editorIds = [];
    var enable = S.params[e.enable];
    S.slotEl = h("span", {class: "ed-slot"}, slot);
    var head = h("div", {class: "ed-head"}, h("h2", {class: "ed-name"}, e.name), S.slotEl);
    var body = h("div", {class: "ed-body"});
    if (enable && enable.available) {
      var sw = makeControl(enable);
      sw.el.className = "ctl switch";
      sw.el.title = "Switch " + e.name + " on or off";
      head.appendChild(sw.el);
      S.editorIds.push(enable.id);
    }
    if (e.id === "dyn") {                                        /* special: live gain-reduction meter (DYN_GR) */
      body.appendChild(h("div", {class: "grmeter wide", title: "How much the dynamics stage turns the signal down (compressor and gate)"},
        h("label", {}, "Gain reduction"),
        h("div", {class: "bar"}, h("div", {id: "gr-bar"})),
        h("span", {id: "gr-text"}, "0.0 dB")));
    }
    if (e.id === "cab") {                                        /* special: cabinet slots */
      body.appendChild(h("div", {id: "cabbody", class: "cabbody wide"}));
    } else {
      paramsOf(e.id, e.enable).forEach(function (p) {
        body.appendChild(makeControl(p).el);
        S.editorIds.push(p.id);
      });
    }
    box.appendChild(h("div", {class: "card", "data-id": e.id}, head, body));
    S.editorIds.forEach(function (id) {                          /* the new controls start from the last state */
      if (S.state && id in S.state.values) S.controls[id].update(S.state.values[id], S.state.raw[id]);
    });
    if (S.state) renderCab(S.state.cab);
  }

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
