#!/usr/bin/env python
"""
gme_smoke.py - smoke test of a running gme_web.py (run on the board by tools/board_smoke.sh).

    python gme_smoke.py [--port 8080] [--host 127.0.0.1]

Checks, one PASS/FAIL line each: /api/info, /api/state, /api/chain, /api/levels, and for every
effect: set one parameter (and the enable switch) through the API, read it back, restore the
old value.  Exit status 1 when any check fails.  Python 2.7 and 3, standard library only.
"""
from __future__ import print_function, division

import argparse
import json
import sys
import time

try:
    from urllib2 import urlopen, Request, HTTPError
except ImportError:
    from urllib.request import urlopen, Request
    from urllib.error import HTTPError

RESULTS = []


def call(base, method, path, body=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = Request(base + path, data, {"Content-Type": "application/json"})
    req.get_method = lambda: method
    try:
        return json.loads(urlopen(req, timeout=10).read().decode("utf-8"))
    except HTTPError as e:
        try:
            msg = json.loads(e.read().decode("utf-8")).get("error")
        except ValueError:
            msg = None
        raise RuntimeError("HTTP %d %s" % (e.code, msg or ""))


def check(name, fn):
    try:
        detail = fn()
        RESULTS.append(True)
        print("PASS %s%s" % (name, (": %s" % detail) if detail else ""))
    except Exception as e:                                   # a failed check must not stop the run
        RESULTS.append(False)
        print("FAIL %s: %s" % (name, e))


def need(cond, text):
    if not cond:
        raise AssertionError(text)


def display_of(p, raw):
    if not p["unit"]:
        return raw
    return (2 ** raw if p.get("scale") == "pow2" else raw) * p["mul"] / p["div"]


def other_value(p, raw):
    """(a different valid raw value, the value to send for it in display units)."""
    if p["type"] == "enum":
        for e in p["enum"]:
            if e["value"] != raw and not e.get("alias"):
                return e["value"], e["label"]
        raise AssertionError("enum with a single value")
    lo, hi = p.get("gui_min", p["min"]), p.get("gui_max", p["max"])
    new = (lo + hi) // 2
    if new == raw:
        new = raw + 1 if raw < hi else raw - 1
    v = display_of(p, new)
    return new, (round(v, 6) if p["unit"] else v)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--wait", type=float, default=15.0, help="seconds to wait for the server")
    a = ap.parse_args(argv)
    base = "http://%s:%d" % (a.host, a.port)
    box = {}

    def info():
        t0 = time.time()
        while True:
            try:
                box["info"] = call(base, "GET", "/api/info")
                break
            except Exception as e:
                if time.time() - t0 > a.wait:
                    raise RuntimeError("no answer from %s: %s" % (base, e))
                time.sleep(0.5)
        i = box["info"]
        need(i["fpga_version"] & 0xFF00 == 0x0200, "FPGA VERSION %s is not 0x02xx" % i["fpga_version_hex"])
        need(len(i["params"]) > 10, "parameter table too short")
        return "FPGA %s, %d parameters%s" % (i["fpga_version_hex"], len(i["params"]), ", MOCK" if i["mock"] else "")
    check("GET /api/info", info)
    if "info" not in box:
        print("%d of %d checks passed" % (sum(RESULTS), len(RESULTS)))
        return 1
    params = dict((p["id"], p) for p in box["info"]["params"] if p["available"])

    def state():
        st = call(base, "GET", "/api/state")
        need(set(st["values"]) == set(params), "state does not list the available parameters")
        box["state"] = st
        s = st["status"]
        return "PLL %s, codec init %s" % ("locked" if s["pll_locked"] else "NOT LOCKED",
                                          "done" if s["codec_init_done"] else "PENDING")
    check("GET /api/state", state)

    def chain():
        ch = call(base, "GET", "/api/chain")
        need(ch["order"] and [e["id"] for e in ch["effects"]] == ch["order"], "bad chain")
        box["chain"] = ch
        return " > ".join(ch["order"]) + (" (editable)" if ch["editable"] else "")
    check("GET /api/chain", chain)

    def reorder():                                  # step E: a reversed order through the API, read back, restored
        ch = box["chain"]
        if not ch["editable"]:
            return "skipped (order is fixed in this image)"
        old = list(ch["order"])
        try:
            call(base, "POST", "/api/chain", {"order": old[::-1]})
            now = call(base, "GET", "/api/chain")["order"]
            need(now == old[::-1], "wrote %s, read back %s" % (",".join(old[::-1]), ",".join(now)))
        finally:
            call(base, "POST", "/api/chain", {"order": old})
        back = call(base, "GET", "/api/chain")["order"]
        need(back == old, "order not restored (%s)" % ",".join(back))
        return "reversed, read back, restored"
    check("POST /api/chain (reverse and restore)", reorder)

    def levels():
        lv = call(base, "GET", "/api/levels")
        need(0 <= lv["in"] <= 65535 and 0 <= lv["out"] <= 65535, "level out of range")
        return "in %d out %d" % (lv["in"], lv["out"])
    check("GET /api/levels", levels)

    def roundtrip(eff):
        en = params.get(eff["enable"])
        raw0 = box["state"]["raw"]
        todo = {}
        if en:
            todo[en["id"]] = (1 - raw0[en["id"]], bool(1 - raw0[en["id"]]))
        cands = [p for p in params.values() if p["group"] == eff["id"] and p["id"] != eff["enable"]
                 and p["type"] != "bool" and eff["id"] != "cab"]
        if cands:
            p = cands[0]
            raw, val = other_value(p, raw0[p["id"]])
            todo[p["id"]] = (raw, val)
        need(todo, "nothing to test")
        old = dict((k, box["state"]["values"][k]) for k in todo)
        try:
            call(base, "POST", "/api/params", dict((k, v[1]) for k, v in todo.items()))
            now = call(base, "GET", "/api/state")["raw"]
            for k, (raw, _) in todo.items():
                need(now[k] == raw, "%s: wrote raw %s, read back %s" % (k, raw, now[k]))
        finally:
            call(base, "POST", "/api/params", old)
        back = call(base, "GET", "/api/state")["raw"]
        for k in todo:
            need(back[k] == raw0[k], "%s not restored (%s, was %s)" % (k, back[k], raw0[k]))
        return ", ".join(sorted(todo))

    for eff in box.get("chain", {}).get("effects", []):
        check("set/read back/restore %s" % eff["id"], lambda eff=eff: roundtrip(eff))
    ok = sum(RESULTS)
    print("%d of %d checks passed" % (ok, len(RESULTS)))
    return 0 if ok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
