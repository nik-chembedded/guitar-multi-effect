/* Guitar multi-effect page.  Everything is built from /api/info (parameter table),
   /api/state and /api/chain: no parameter or effect is named here, except the few
   special cases marked "special" (cabinet slots, dynamics meter, mute button, codec volumes). */
"use strict";
(function () {
  var h = GME.h, api = GME.api, toast = GME.toast;
  var S = {info: null, params: {}, state: null, controls: {}, chainSig: "", chain: null,
           presets: [], cabBusy: false, online: false};

  /* ---------- controls bookkeeping ---------- */
  function onChange(id, value) { GME.sender.set(id, value); }
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
    if (!force && (GME.sender.busy() || S.cabBusy)) return Promise.resolve();
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
    renderChain(st.chain);
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

  /* ---------- effect chain ---------- */
  function paramsOf(group, skipId) {
    return S.info.params.filter(function (p) { return p.group === group && p.id !== skipId && p.available; });
  }

  function renderChain(ch) {
    var sig = ch.order.join(",") + "|" + ch.editable;
    S.chain = ch;
    if (sig === S.chainSig) return;
    S.chainSig = sig;
    var box = document.getElementById("chain");
    GME.clear(box);
    (S.chainIds || []).forEach(function (id) { delete S.controls[id]; });
    S.chainIds = [];
    document.getElementById("orderhint").textContent = ch.editable
      ? "Drag the cards by their handle to change the order of the effects."
      : "Fixed order in this FPGA (VERSION " + S.info.fpga_version_hex + "): the effects run left to right, then down.";
    ch.effects.forEach(function (e, i) { box.appendChild(card(e, ch.editable)); });
  }

  function card(e, editable) {
    var enable = S.params[e.enable];
    var head = h("div", {class: "card-head"},
      h("span", {class: "grip", title: editable ? "Drag to reorder" : "Fixed order in this FPGA"}, editable ? "☰" : "•"),
      h("span", {class: "card-name"}, e.name));
    var body = h("div", {class: "card-body"});
    var c = h("div", {class: "card", "data-id": e.id}, head, body);
    if (enable && enable.available) {
      var sw = makeControl(enable);
      sw.el.className = "ctl switch";
      sw.el.title = "Switch " + e.name + " on or off";
      head.appendChild(sw.el);
      S.chainIds.push(enable.id);
    }
    if (e.id === "dyn") {                                        /* special: live gain-reduction meter (DYN_GR) */
      body.appendChild(h("div", {class: "grmeter", title: "How much the dynamics stage turns the signal down (compressor and gate)"},
        h("label", {}, "Gain reduction"),
        h("div", {class: "bar"}, h("div", {id: "gr-bar"})),
        h("span", {id: "gr-text"}, "0.0 dB")));
    }
    if (e.id === "cab") {                                        /* special: cabinet slots */
      body.appendChild(h("div", {id: "cabbody", class: "cabbody"}));
    } else {
      paramsOf(e.id, e.enable).forEach(function (p) {
        body.appendChild(makeControl(p).el);
        S.chainIds.push(p.id);
      });
    }
    if (editable) enableDrag(c);
    return c;
  }

  function enableDrag(cardEl) {
    var grip = cardEl.querySelector(".grip");
    grip.addEventListener("mousedown", function () { cardEl.draggable = true; });
    cardEl.addEventListener("dragend", function () { cardEl.draggable = false; cardEl.classList.remove("drag"); });
    cardEl.addEventListener("dragstart", function (ev) {
      cardEl.classList.add("drag");
      ev.dataTransfer.setData("text/plain", cardEl.getAttribute("data-id"));
      ev.dataTransfer.effectAllowed = "move";
    });
    cardEl.addEventListener("dragover", function (ev) { ev.preventDefault(); cardEl.classList.add("over"); });
    cardEl.addEventListener("dragleave", function () { cardEl.classList.remove("over"); });
    cardEl.addEventListener("drop", function (ev) {
      ev.preventDefault();
      cardEl.classList.remove("over");
      var from = ev.dataTransfer.getData("text/plain"), to = cardEl.getAttribute("data-id");
      if (!from || from === to) return;
      var order = S.chain.order.filter(function (x) { return x !== from; });
      order.splice(order.indexOf(to), 0, from);
      api("POST", "/api/chain", {order: order}).then(function () { refresh(true); })
        .catch(function (e) { toast(e.message, true); refresh(true); });
    });
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
    api("POST", "/api/cab", {slot: slot}).then(function () { toast("Cabinet loaded: " + name); })
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
    var name = h("input", {type: "text", id: "preset-name", placeholder: "preset name", "aria-label": "Preset name", maxlength: 40});
    function cur() { return S.presets.filter(function (p) { return p.name === sel.value; })[0]; }
    sel.addEventListener("change", function () { if (cur() && !cur().factory) name.value = cur().name; });
    function doLoad() {
      api("POST", "/api/presets/" + encodeURIComponent(sel.value)).then(function (r) {
        toast("Preset loaded: " + sel.value);
        (r.warnings || []).forEach(function (w) { toast(w, true); });
        refresh(true);
      }).catch(function (e) { toast(e.message, true); });
    }
    function doSave(n, overwrite) {
      api("POST", "/api/presets", {name: n, overwrite: overwrite}).then(function () {
        toast("Preset saved: " + n);
        return loadPresets(n);
      }).catch(function (e) {
        if (!overwrite && /exists/.test(e.message) && confirm("Overwrite preset '" + n + "'?")) doSave(n, true);
        else toast(e.message, true);
      });
    }
    bar.appendChild(h("label", {"for": "preset-sel"}, "Preset"));
    bar.appendChild(sel);
    bar.appendChild(h("button", {class: "btn", onclick: doLoad}, "Load"));
    bar.appendChild(h("span", {class: "sep"}));
    bar.appendChild(name);
    bar.appendChild(h("button", {class: "btn", onclick: function () {
      if (!name.value.trim()) return toast("Type a name first", true);
      doSave(name.value.trim(), false);
    }}, "Save as"));
    bar.appendChild(h("button", {class: "btn", title: "Overwrite the selected user preset with the current settings", onclick: function () {
      var c = cur();
      if (!c || c.factory) return toast("Select a user preset to overwrite", true);
      if (confirm("Overwrite preset '" + c.name + "' with the current settings?")) doSave(c.name, true);
    }}, "Overwrite"));
    bar.appendChild(h("button", {class: "btn danger", onclick: function () {
      var c = cur();
      if (!c || c.factory) return toast("Factory presets cannot be deleted", true);
      if (!confirm("Delete preset '" + c.name + "'?")) return;
      api("DELETE", "/api/presets/" + encodeURIComponent(c.name)).then(function () {
        toast("Preset deleted"); return loadPresets();
      }).catch(function (e) { toast(e.message, true); });
    }}, "Delete"));
    sel.selectedIndex = Math.max(0, S.presets.map(function (p) { return p.name; }).indexOf(S.selectedPreset));
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
    var grBar = document.getElementById("gr-bar"), grText = document.getElementById("gr-text");   /* only in the dynamics card */
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
      onChange("mute", on);
    });
    api("GET", "/api/info").then(function (info) {
      S.info = info;
      GME.fpgaVersion = info.fpga_version;
      info.params.forEach(function (p) { S.params[p.id] = p; });
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
