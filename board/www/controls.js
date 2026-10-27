/* Controls generated from one row of the parameter table (/api/info -> params[]).
   Nothing here knows a parameter by name: type, range, unit and labels come from the table.
   int / signed -> knob, enum with up to SEG_MAX choices -> button row, longer enum -> select, bool -> switch. */
"use strict";
(function () {
  var h = GME.h, SEG_MAX = 5;

  /* "pow2" scale (compressor attack / release): the register holds k, the value is 2^k samples in ms */
  function toDisplay(p, raw) {
    if (!p.unit) return raw;
    return (p.scale === "pow2" ? Math.pow(2, raw) : raw) * p.mul / p.div;
  }
  function toRaw(p, disp) {
    if (!p.unit) return Math.round(disp);
    var r = disp * p.div / p.mul;
    return Math.round(p.scale === "pow2" ? Math.log(Math.max(r, 1e-9)) / Math.LN2 : r);
  }

  /* "320 ms", "6.5 Hz", "62.7 %", "Heavy", "on" */
  GME.format = function (p, raw) {
    if (p.type === "bool") return raw ? "on" : "off";
    if (p.type === "enum") {
      var e = (p.enum || []).filter(function (x) { return x.value === raw; })[0];
      return e ? e.label : String(raw);
    }
    if (!p.unit) return String(raw);
    var s = toDisplay(p, raw).toFixed(p.decimals);
    if (s.indexOf(".") >= 0) s = s.replace(/0+$/, "").replace(/\.$/, "");
    return s + " " + p.unit;
  };

  function title(p) { return p.gui_label || p.name; }          /* inside a section the short label is enough */

  function label(p, valueEl) {
    return h("div", {class: "ctl-head"},
      h("label", {class: "ctl-name", "for": "c-" + p.id, title: p.help}, title(p)),
      h("span", {class: "help", title: p.help, "aria-hidden": "true"}, "?"),
      valueEl || null);
  }

  function choices(p) {
    return (p.enum || []).filter(function (e) {
      return !e.alias && !(e.min_version && GME.fpgaVersion && e.min_version > GME.fpgaVersion);   /* not in this FPGA image */
    });
  }

  /* Returns {id, el, update(display, raw), active}.  onChange(id, value) gets the display value
     (number in the table's unit, enum label, boolean). */
  GME.makeControl = function (p, onChange) {
    if (p.type === "bool") return toggle(p, onChange);
    if (p.type === "enum") return choices(p).length <= SEG_MAX ? segments(p, onChange) : select(p, onChange);
    return knob(p, onChange);
  };

  function toggle(p, onChange) {
    var ctl = {id: p.id, active: false};
    var cb = h("input", {type: "checkbox", id: "c-" + p.id, "aria-label": p.name, title: p.help});
    cb.addEventListener("change", function () { onChange(p.id, cb.checked); });
    ctl.el = h("label", {class: "ctl toggle", title: p.help}, cb, h("span", {class: "ctl-name"}, title(p)));
    ctl.update = function (disp) { cb.checked = !!disp; };
    return ctl;
  }

  function select(p, onChange) {
    var ctl = {id: p.id, active: false};
    var sel = h("select", {id: "c-" + p.id, "aria-label": p.name, title: p.help});
    choices(p).forEach(function (e) { sel.appendChild(h("option", {value: e.label}, e.label)); });
    sel.addEventListener("change", function () { onChange(p.id, sel.value); });
    sel.addEventListener("focus", function () { ctl.active = true; });
    sel.addEventListener("blur", function () { ctl.active = false; });
    ctl.el = h("div", {class: "ctl ctl-select"}, label(p), sel);
    ctl.update = function (disp) {
      sel.setAttribute("aria-valuetext", String(disp));
      if (!Array.prototype.some.call(sel.options, function (o) { return o.value === disp; }))
        sel.appendChild(h("option", {value: disp}, String(disp)));
      sel.value = disp;
    };
    return ctl;
  }

  /* a row of buttons, one per choice (radio group) */
  function segments(p, onChange) {
    var ctl = {id: p.id, active: false}, cur = null;
    var row = h("div", {class: "seg", role: "radiogroup", id: "c-" + p.id, "aria-label": p.name, title: p.help});
    function button(lbl) {
      return h("button", {type: "button", role: "radio", "aria-checked": "false", "data-v": lbl, onclick: function () {
        if (lbl === cur) return;
        ctl.update(lbl);
        onChange(p.id, lbl);
      }, onkeydown: function (ev) {                               /* arrows move along the row, as in a radio group */
        var d = ev.key === "ArrowRight" || ev.key === "ArrowDown" ? 1 : ev.key === "ArrowLeft" || ev.key === "ArrowUp" ? -1 : 0;
        if (!d) return;
        ev.preventDefault();
        var bs = row.querySelectorAll("button"), i = Array.prototype.indexOf.call(bs, ev.target) + d;
        if (i >= 0 && i < bs.length) { bs[i].focus(); bs[i].click(); }
      }}, lbl);
    }
    choices(p).forEach(function (e) { row.appendChild(button(e.label)); });
    ctl.el = h("div", {class: "ctl ctl-seg"}, label(p), row);
    ctl.update = function (disp) {
      cur = disp;
      var known = Array.prototype.some.call(row.querySelectorAll("button"), function (b) { return b.getAttribute("data-v") === disp; });
      if (!known) row.appendChild(button(String(disp)));        /* a value without a button (alias, newer image) */
      Array.prototype.forEach.call(row.querySelectorAll("button"), function (b) {
        var on = b.getAttribute("data-v") === disp;
        b.classList.toggle("on", on);
        b.setAttribute("aria-checked", on ? "true" : "false");
        b.tabIndex = on ? 0 : -1;
      });
    };
    return ctl;
  }

  /* Knob over the raw range (gui_min..gui_max).  Turned with the mouse (Shift = fine), wheel, arrow keys,
     Page Up / Down, Home / End; double-click = default; click the value to type one.  "gui_taper": "log"
     spreads the low end (rates).  A range across 0 draws its arc from the centre. */
  var KS = 60, KR = 24, KC = 30, SWEEP = 135;
  function arcPath(a0, a1) {
    function pt(a) { a = (a - 90) * Math.PI / 180; return (KC + KR * Math.cos(a)).toFixed(1) + " " + (KC + KR * Math.sin(a)).toFixed(1); }
    return "M" + pt(a0) + "A" + KR + " " + KR + " 0 " + (a1 - a0 > 180 ? 1 : 0) + " 1 " + pt(a1);
  }
  function svg(tag, attrs) {
    var el = document.createElementNS("http:\/\/www.w3.org\/2000\/svg", tag);   /* the SVG namespace name, not a resource */
    for (var k in attrs) el.setAttribute(k, attrs[k]);
    return el;
  }

  function knob(p, onChange) {
    var ctl = {id: p.id, active: false};
    var lo = p.gui_min !== undefined ? p.gui_min : p.min;
    var hi = p.gui_max !== undefined ? p.gui_max : p.max;
    var raw = lo, log = p.gui_taper === "log" && lo >= 0;
    var bipolar = lo < 0 && hi > 0;
    function pos(r) {                                            /* raw -> 0..1 along the knob */
      if (hi === lo) return 0;
      if (log) return Math.log(r - lo + 1) / Math.log(hi - lo + 1);
      return (r - lo) / (hi - lo);
    }
    function fromPos(x) {
      x = Math.max(0, Math.min(1, x));
      return Math.round(log ? lo + Math.exp(x * Math.log(hi - lo + 1)) - 1 : lo + x * (hi - lo));
    }
    function angle(r) { return -SWEEP + 2 * SWEEP * Math.max(0, Math.min(1, pos(r))); }

    var face = svg("svg", {width: KS, height: KS - 4, viewBox: "0 0 " + KS + " " + (KS - 4), "aria-hidden": "true"});
    face.appendChild(svg("path", {d: arcPath(-SWEEP, SWEEP), class: "kn-track"}));
    var val = svg("path", {d: "", class: "kn-arc"});
    face.appendChild(val);
    face.appendChild(svg("circle", {cx: KC, cy: KC, r: 16, class: "kn-cap"}));
    var ptr = svg("line", {x1: KC, y1: KC, x2: KC, y2: KC - 13, class: "kn-ptr"});
    face.appendChild(ptr);

    var dial = h("div", {class: "kn-dial", id: "c-" + p.id, role: "slider", tabindex: "0", "aria-label": p.name,
                         "aria-valuemin": lo, "aria-valuemax": hi,
                         title: p.help + "\nTurn it with the mouse (Shift = fine), wheel or arrow keys; double-click = default"}, face);
    var out = h("button", {type: "button", class: "kn-val", title: "Type a value"}, "");
    ctl.el = h("div", {class: "ctl knob"},
      h("label", {class: "ctl-name", "for": "c-" + p.id, title: p.help}, title(p)), dial, out);

    function draw() {
      var a = angle(raw), from = bipolar ? angle(0) : -SWEEP;
      val.setAttribute("d", Math.abs(a - from) < 0.5 ? "" : arcPath(Math.min(a, from), Math.max(a, from)));
      var r = a * Math.PI / 180;
      ptr.setAttribute("x2", (KC + 13 * Math.sin(r)).toFixed(1));
      ptr.setAttribute("y2", (KC - 13 * Math.cos(r)).toFixed(1));
      out.textContent = GME.format(p, raw);
      dial.setAttribute("aria-valuenow", raw);
      dial.setAttribute("aria-valuetext", out.textContent);
    }
    /* gui_commit "release": the value is sent when the knob is let go (the EQ coefficients take a while to compute) */
    var moved = false;                                           /* changed since the last "final" (let go) */
    function send() { var v = toDisplay(p, raw); onChange(p.id, p.unit ? Number(v.toFixed(6)) : v); }
    function set(r, final) {
      r = Math.max(lo, Math.min(hi, r));
      if (r !== raw) {
        raw = r;
        draw();
        moved = true;
        if (p.gui_commit !== "release") send();
      }
      if (final && moved) {
        moved = false;
        if (p.gui_commit === "release") send();
      }
    }
    function step(fine) { return Math.max(1, Math.round((hi - lo) / (fine ? 500 : 100))); }
    function nudge(n) {                                          /* n steps, along the taper for log knobs */
      if (log) {
        var r = fromPos(pos(raw) + n / 100);
        return r === raw ? raw + (n > 0 ? 1 : -1) : r;
      }
      return raw + n * step(false);
    }

    /* turned like a real knob: grab it anywhere, the angle of the pointer around the centre turns it
       (from where it is, no jump); Shift = a quarter of the turn, for fine steps */
    var drag = null;
    function pointerAngle(ev) {                                  /* degrees, 0 = up, clockwise */
      var r = face.getBoundingClientRect();
      var dx = ev.clientX - (r.left + r.width * KC / KS), dy = ev.clientY - (r.top + r.height * KC / (KS - 4));
      return Math.sqrt(dx * dx + dy * dy) < 4 ? null : Math.atan2(dx, -dy) * 180 / Math.PI;   /* too near the centre: unstable */
    }
    dial.addEventListener("pointerdown", function (ev) {
      if (ev.button !== 0) return;
      ctl.active = true;
      drag = {last: pointerAngle(ev), a: angle(raw)};
      dial.setPointerCapture(ev.pointerId);
      dial.focus();
      ev.preventDefault();
    });
    dial.addEventListener("pointermove", function (ev) {
      if (!drag) return;
      var cur = pointerAngle(ev);
      if (cur === null) return;
      if (drag.last !== null) {
        var d = cur - drag.last;
        if (d > 180) d -= 360;                                   /* crossing the bottom of the knob */
        if (d < -180) d += 360;
        drag.a = Math.max(-SWEEP, Math.min(SWEEP, drag.a + d * (ev.shiftKey ? 0.25 : 1)));
        set(fromPos((drag.a + SWEEP) / (2 * SWEEP)));
      }
      drag.last = cur;
    });
    function release() {
      if (!drag) return;
      drag = null;
      set(raw, true);
      setTimeout(function () { ctl.active = false; }, 150);
    }
    dial.addEventListener("pointerup", release);
    dial.addEventListener("pointercancel", release);
    dial.addEventListener("dblclick", function () {
      set(Math.max(lo, Math.min(hi, p.default)), true);
    });
    var wheelTimer = null;
    dial.addEventListener("wheel", function (ev) {
      ev.preventDefault();
      ctl.active = true;
      var n = ev.deltaY < 0 ? 1 : -1;
      set(ev.shiftKey ? raw + n * step(true) : nudge(n));
      clearTimeout(wheelTimer);
      wheelTimer = setTimeout(function () { set(raw, true); ctl.active = false; }, 300);
    });
    dial.addEventListener("keydown", function (ev) {
      var k = ev.key, r = null;
      if (k === "ArrowUp" || k === "ArrowRight") r = ev.shiftKey ? raw + step(true) : nudge(1);
      else if (k === "ArrowDown" || k === "ArrowLeft") r = ev.shiftKey ? raw - step(true) : nudge(-1);
      else if (k === "PageUp") r = nudge(10);
      else if (k === "PageDown") r = nudge(-10);
      else if (k === "Home") r = lo;
      else if (k === "End") r = hi;
      if (r === null) return;
      ev.preventDefault();
      ctl.active = true;
      set(r);
    });
    dial.addEventListener("keyup", function () { set(raw, true); setTimeout(function () { ctl.active = false; }, 150); });
    dial.addEventListener("blur", function () { if (!drag) ctl.active = false; });

    /* typed value, in the unit shown */
    out.addEventListener("click", function () {
      ctl.active = true;
      var inp = h("input", {type: "text", class: "kn-input", value: p.unit ? String(Number(toDisplay(p, raw).toFixed(p.decimals))) : String(raw),
                            "aria-label": p.name + (p.unit ? " in " + p.unit : "")});
      var done = false;
      function finish(ok) {
        if (done) return;
        done = true;
        var v = parseFloat(inp.value.replace(",", "."));
        if (inp.parentNode) inp.parentNode.replaceChild(out, inp);
        ctl.active = false;
        if (ok && !isNaN(v)) set(toRaw(p, v), true);
        dial.focus();
      }
      inp.addEventListener("keydown", function (ev) {
        if (ev.key === "Enter") finish(true);
        else if (ev.key === "Escape") finish(false);
      });
      inp.addEventListener("blur", function () { finish(true); });
      out.parentNode.replaceChild(inp, out);
      inp.focus();
      inp.select();
    });

    ctl.update = function (disp, rawValue) {
      if (rawValue < lo) lo = rawValue;                          /* value outside the GUI range */
      if (rawValue > hi) hi = rawValue;
      raw = rawValue;
      draw();
    };
    draw();
    return ctl;
  };
})();
