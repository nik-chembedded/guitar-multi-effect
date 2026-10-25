/* Small helpers: DOM builder, API calls, throttled parameter sender, toasts. */
"use strict";
var GME = window.GME = window.GME || {};

/* h("div", {class: "x", onclick: fn}, child, "text", ...) */
GME.h = function (tag, attrs) {
  var el = document.createElement(tag);
  for (var k in (attrs || {})) {
    var v = attrs[k];
    if (v === null || v === undefined || v === false) continue;
    if (k.slice(0, 2) === "on") el.addEventListener(k.slice(2), v);
    else if (k === "class") el.className = v;
    else if (k === "text") el.textContent = v;
    else if (v === true) el.setAttribute(k, "");
    else el.setAttribute(k, v);
  }
  for (var i = 2; i < arguments.length; i++) GME.append(el, arguments[i]);
  return el;
};
GME.append = function (el, c) {
  if (c === null || c === undefined || c === false) return;
  if (Array.isArray(c)) c.forEach(function (x) { GME.append(el, x); });
  else el.appendChild(typeof c === "object" ? c : document.createTextNode(String(c)));
};
GME.clear = function (el) { while (el.firstChild) el.removeChild(el.firstChild); };

GME.toast = function (msg, isError) {
  var box = document.getElementById("toasts");
  var t = GME.h("div", {class: "toast" + (isError ? " err" : "")}, msg);
  box.appendChild(t);
  setTimeout(function () { if (t.parentNode) t.parentNode.removeChild(t); }, isError ? 6000 : 2500);
};

/* JSON API call; rejects with Error(message from {error}) */
GME.api = function (method, path, body) {
  var opt = {method: method, headers: {}};
  if (body !== undefined) {
    opt.body = JSON.stringify(body);
    opt.headers["Content-Type"] = "application/json";
  }
  return fetch(path, opt).then(function (r) {
    return r.text().then(function (t) {
      var j = null;
      try { j = JSON.parse(t); } catch (e) { /* not JSON */ }
      if (!r.ok) throw new Error((j && j.error) || (r.status + " " + r.statusText));
      return j;
    });
  });
};

/* Parameter updates: at most one POST every 50 ms (20/s); the latest value of each
   parameter is always sent (trailing send). */
GME.sender = (function () {
  var INTERVAL = 50;
  var pending = {}, timer = null, last = 0, inflight = 0, listeners = [];
  function flush() {
    timer = null;
    var body = pending; pending = {};
    if (!Object.keys(body).length) return;
    last = Date.now();
    inflight++;
    GME.api("POST", "/api/params", body).then(function (r) {
      listeners.forEach(function (f) { f(r.values, null); });
    }).catch(function (e) {
      GME.toast(e.message, true);
      listeners.forEach(function (f) { f(null, e); });
    }).then(function () { inflight--; });
  }
  return {
    set: function (id, value) {
      pending[id] = value;
      if (timer) return;
      var wait = Math.max(0, INTERVAL - (Date.now() - last));
      timer = setTimeout(flush, wait);
    },
    busy: function () { return inflight > 0 || timer !== null; },
    has: function (id) { return id in pending; },
    onResult: function (f) { listeners.push(f); }
  };
})();
