/* Controls generated from one row of the parameter table (/api/info -> params[]).
   Nothing here knows a parameter by name: type, range, unit and labels come from the table. */
"use strict";
(function () {
  var h = GME.h;

  function toDisplay(p, raw) { return p.unit ? raw * p.mul / p.div : raw; }

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

  function label(p, valueEl) {
    return h("div", {class: "ctl-head"},
      h("span", {class: "ctl-name", title: p.help}, p.name),
      h("span", {class: "help", title: p.help}, "?"),
      valueEl || null);
  }

  /* Returns {id, el, update(display, raw)}.  onChange(id, value) gets the display value
     (number in the table's unit, enum label, boolean). */
  GME.makeControl = function (p, onChange) {
    var ctl = {id: p.id, active: false};

    if (p.type === "bool") {
      var cb = h("input", {type: "checkbox", id: "c-" + p.id});
      cb.addEventListener("change", function () { onChange(p.id, cb.checked); });
      ctl.el = h("label", {class: "ctl toggle", title: p.help}, cb, h("span", {class: "ctl-name"}, p.name));
      ctl.update = function (disp) { cb.checked = !!disp; };
      return ctl;
    }

    if (p.type === "enum") {
      var sel = h("select", {id: "c-" + p.id});
      (p.enum || []).forEach(function (e) {
        if (!e.alias) sel.appendChild(h("option", {value: e.label}, e.label));
      });
      sel.addEventListener("change", function () { onChange(p.id, sel.value); });
      sel.addEventListener("focus", function () { ctl.active = true; });
      sel.addEventListener("blur", function () { ctl.active = false; });
      ctl.el = h("div", {class: "ctl"}, label(p), sel);
      ctl.update = function (disp) {
        if (!Array.prototype.some.call(sel.options, function (o) { return o.value === disp; }))
          sel.appendChild(h("option", {value: disp}, String(disp)));
        sel.value = disp;
      };
      return ctl;
    }

    /* int / signed: slider in raw steps, shown in display units */
    var lo = p.gui_min !== undefined ? p.gui_min : p.min;
    var hi = p.gui_max !== undefined ? p.gui_max : p.max;
    var out = h("output", {class: "ctl-val"}, "");
    var rng = h("input", {type: "range", id: "c-" + p.id, min: lo, max: hi, step: 1, value: lo});
    function raw() { return parseInt(rng.value, 10); }
    function show() { out.textContent = GME.format(p, raw()); }
    rng.addEventListener("input", function () {
      show();
      var v = toDisplay(p, raw());
      onChange(p.id, p.unit ? Number(v.toFixed(6)) : v);
    });
    ["pointerdown", "keydown", "focus"].forEach(function (ev) {
      rng.addEventListener(ev, function () { ctl.active = true; });
    });
    ["pointerup", "pointercancel", "blur", "keyup"].forEach(function (ev) {
      rng.addEventListener(ev, function () { setTimeout(function () { ctl.active = false; }, 150); });
    });
    ctl.el = h("div", {class: "ctl"}, label(p, out), rng);
    ctl.update = function (disp, rawValue) {
      if (rawValue < rng.min) rng.min = rawValue;          /* value outside the GUI range */
      if (rawValue > rng.max) rng.max = rawValue;
      rng.value = rawValue;
      show();
    };
    return ctl;
  };
})();
