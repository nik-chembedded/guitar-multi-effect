#!/usr/bin/env python
"""
gme_hps.py - control the guitar multi-effect v2 from Linux on the DE1-SoC HPS.

The FPGA registers sit behind the HPS lightweight bridge: register n is the
32-bit word at 0xFF200000 + 4*n (fpga/rtl/ctrl_avmm.vhd). Run as root:

    python gme_hps.py status
    python gme_hps.py read  0x02
    python gme_hps.py write 0x00 0x0001          (register, value)
    python gme_hps.py set   od_drive=3000 od_gain=4 effects=OD
    python gme_hps.py set   effects=TREM trem_shape=square trem_hz=6.5 trem_depth=200
    python gme_hps.py preset flanger             (also: chorus, vibrato, ambient, ...)
    python gme_hps.py set   mod_fb=-26000        (flanger feedback, signed)
    python gme_hps.py preset crunch
    python gme_hps.py codec 0x00 0x080           (codec register, 9-bit value: mute line in)
    python gme_hps.py dump
    python gme_hps.py meter                      (input/output levels, Ctrl+C to stop)
    python gme_hps.py selftest                   (no hardware needed)

By parameter id, in display units (a number with its unit; a bare number is the raw
register value, as in the old command line):

    python gme_hps.py set   echo_time=320ms trem_rate=6.5Hz echo_on=on dist_type=heavy
    python gme_hps.py get   echo_time trem_rate  (no argument: all parameters)
    python gme_hps.py params                     (the parameter table)
    python gme_hps.py cab   list | N | on | off   (cabinet simulator, FPGA VERSION >= 0x0205)
    python gme_hps.py chain                      (effect order)
    python gme_hps.py preset list | save NAME | delete NAME

--mock runs against an in-memory register file (no board needed).
Every command first checks the VERSION register (0x02xx), so nothing is written
when another FPGA image is loaded. Works with Python 2.7 and 3.
"""
from __future__ import print_function, division

import argparse
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from gme import model as gm                                    # noqa: E402
from gme import device as gd                                   # noqa: E402
from gme.store import Store, StoreError                        # noqa: E402

COMMANDS = ["status", "read", "write", "set", "preset", "codec", "dump", "meter", "selftest",
            "get", "params", "cab", "chain"]
# tremolo free mode (step D1): trem_wave = 8 + shape, rate in trem_rate (0.01 Hz)
TREM_SHAPES = {"sine": 0, "triangle": 1, "saw": 2, "square": 3}
PRESET_EXTRA = ("list", "save", "delete")


def num(s):
    return int(s, 0)


def parse_assignments(m, items):
    """['k=v', ...] -> list of ('effects'|'reg'|'param', key, raw value); nothing is written."""
    out = []
    t = m.table
    for it in items:
        if "=" not in it:
            raise SystemExit("expected name=value, got '%s'" % it)
        k, v = it.split("=", 1)
        try:
            if k == "effects":
                out.append(("reg", t.reg_by_name["effects_enable"], m.parse_effects(v)))
            elif k == "trem_shape":
                if v not in TREM_SHAPES:
                    raise SystemExit("trem_shape: %s" % ", ".join(sorted(TREM_SHAPES)))
                out.append(("param", "trem_wave", 8 + TREM_SHAPES[v]))
            elif k == "trem_hz":
                out.append(("param", "trem_rate", int(round(float(v) * 100))))
            elif k in t.by_id:
                p = t.by_id[k]
                out.append(("param", p.id, p.parse(v, legacy_raw=True)))
            elif k in t.reg_by_name:
                out.append(("reg", t.reg_by_name[k], num(v)))
            else:
                known = [p.id for p in t.params] + sorted(t.reg_by_name)
                raise SystemExit("unknown register '%s' (known: %s)" % (k, ", ".join(known)))
        except gm.ParamError as e:
            raise SystemExit(str(e))
    return out


def apply_assignments(m, parsed):
    for kind, key, raw in parsed:
        if kind == "reg":
            m.write(key, raw)
        else:
            m.set_raw({key: raw})


def selftest():
    dev = gd.Mock(version=0x0205)
    m = gm.Model(dev)
    r = parse_assignments(m, ["effects=DIST+ECHO", "od_gain=4", "echo_time=0x3840"])
    assert r == [("reg", 0, 12), ("param", "od_gain", 4), ("param", "echo_time", 14400)], r
    assert m.effects_text(12) == "ECHO+DIST"
    assert ((0x02 & 0x7F) << 9) | 0x079 == 0x0479                 # CODEC word for R2 = 0x079
    r = parse_assignments(m, ["trem_shape=square", "trem_hz=6.5"])
    assert r == [("param", "trem_wave", 11), ("param", "trem_rate", 650)], r
    t = m.table.param("echo_time")
    assert t.parse("320ms") == 15360 and t.format(15360) == "320 ms"
    for name in m.factory_names():
        m.apply_preset(name)
    m.set({"echo_time": "320ms", "trem_rate": 6.5})
    assert dev.read(5) == 15360 and dev.read(0x16) == 650
    print("selftest OK")


def show_params(m):
    print("%-12s %-7s %-6s %-6s %-22s %-6s %s" % ("id", "reg", "bits", "type", "range (display)", "vers", "help"))
    for p in m.table.params:
        lo, hi = p.format(p.min), p.format(p.max)
        if p.type == "enum":
            lo, hi = "%d..%d" % (p.min, p.max), ""
            rng = "0..%d (%s)" % (p.max, "/".join(str(e["label"]) for e in p.enum if not e.get("alias")))
        elif p.type == "bool":
            rng = "on/off"
        else:
            rng = "%s .. %s" % (lo, hi)
        bits = "[%d:%d]" % (p.lsb + p.width - 1, p.lsb) if p.width > 1 else "[%d]" % p.lsb
        print("%-12s 0x%02X    %-6s %-6s %-22s %04X%s %s" % (
            p.id, p.reg, bits, p.type, rng[:22], p.min_version, " " if m.available(p) else "!", p.help))


def cmd_get(m, ids):
    ids = ids or [p.id for p in m.params()]
    for pid in ids:
        p = m.table.param(pid)
        if not m.available(p):
            print("%-12s not in this FPGA image (needs VERSION 0x%04X)" % (p.id, p.min_version))
            continue
        raw = m.get_raw(p.id)
        shown = p.format(raw)
        if p.type in ("int", "signed") and not p.has_unit:
            print("%-12s = %s" % (p.id, shown))
        else:
            print("%-12s = %s (raw %d)" % (p.id, shown, raw))


def cmd_cab(m, args):
    sub = args[0] if args else "status"
    if sub == "list":
        slots = m.cab_list()
        if not slots:
            print("no cabinet files in %s" % m.cab_dir)
        for c in slots:
            print("%2d  %-28s shift %s%s" % (c["slot"], c["name"], c["shift"],
                                             "   <- loaded" if c["slot"] == m.cab_slot else ""))
    elif sub in ("on", "off"):
        m.cab_enable(sub == "on")
        print("cabinet %s" % sub)
    elif sub == "status":
        st = m.cab_status()
        if not st["available"]:
            print("no cabinet simulator in this FPGA image (VERSION 0x%04X)" % m.version)
        else:
            print("cabinet %s, active bank %d, loaded slot %s" % (
                "on" if st["enabled"] else "off", st["active_bank"],
                "?" if st["slot"] is None else st["slot"]))
    else:
        try:
            slot = num(sub)
        except ValueError:
            raise SystemExit("cab list | N | on | off | status")
        r = m.cab_load(slot)
        print("cabinet %d '%s' loaded into bank %d (shift %d)" % (r["slot"], r["name"], r["bank"], r["shift"]))


def cmd_preset(m, args):
    names = [p["name"] for p in m.preset_list()]
    if args and args[0] == "list":
        for p in m.preset_list():
            print("%-14s %s%s" % (p["name"], "factory" if p["factory"] else "user", ("  " + p["description"]) if p["description"] else ""))
        return
    if args and args[0] in ("save", "delete") and len(args) >= 2:
        try:
            if args[0] == "save":
                m.save_preset(args[1], overwrite=(len(args) > 2 and args[2] == "overwrite"))
                print("preset '%s' saved" % args[1])
            else:
                m.delete_preset(args[1])
                print("preset '%s' deleted" % args[1])
        except (gm.FactoryPreset, gm.PresetExists, gm.ParamError, StoreError, KeyError) as e:
            raise SystemExit(str(e).strip("'\"") if not isinstance(e, KeyError) else "no such preset '%s'" % args[1])
        return
    if not args or args[0] not in names:
        raise SystemExit("presets: %s" % ", ".join(names))
    warnings = m.apply_preset(args[0])
    for w in warnings:
        sys.stderr.write("warning: %s\n" % w)
    print("preset '%s' loaded" % args[0])


def run(argv, dev=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-check", action="store_true", help="skip the VERSION check")
    ap.add_argument("--mock", action="store_true", help="use an in-memory register file instead of /dev/mem")
    ap.add_argument("--mock-version", type=num, default=0x0205, help="VERSION of the mock (default 0x0205)")
    ap.add_argument("--mock-state", default=None, metavar="FILE",
                    help="with --mock: keep the mock registers in this JSON file, shared between calls "
                         "(default ~/.gme_mock_state.json)")
    ap.add_argument("--data-dir", default=None, help="presets/ and settings.json (default: next to this script)")
    ap.add_argument("--cab-dir", default=None, help="cabNN.coef files (default: <data-dir>/cab)")
    ap.add_argument("cmd", choices=COMMANDS)
    ap.add_argument("args", nargs="*")
    a, extra = ap.parse_known_args(argv)
    for e in extra:                                   # options after the positionals
        if re.match(r"^--?[A-Za-z]", e):
            ap.error("unrecognized argument: %s" % e)
        a.args.append(e)
    if a.cmd == "selftest":
        return selftest()
    if dev is None:
        try:
            dev = gm.open_device(mock=a.mock, mock_version=a.mock_version, check=not a.no_check,
                                state_file=os.path.expanduser(a.mock_state or "~/.gme_mock_state.json"))
        except gd.WrongImage as e:
            raise SystemExit(str(e))
        except (IOError, OSError) as e:
            raise SystemExit("cannot open /dev/mem (run as root on the board; --mock to test): %s" % e)
    data_dir = a.data_dir or HERE
    m = gm.Model(dev, store=Store(data_dir), cab_dir=a.cab_dir or os.path.join(data_dir, "cab"))
    try:
        return dispatch(m, a)
    except (gm.ParamError, gm.CabinetError, gm.NotEditable, gd.DeviceError, StoreError) as e:
        raise SystemExit(str(e))


def dispatch(m, a):
    t = m.table
    if a.cmd == "status":
        s = m.read(t.reg_by_name["status"])
        print("version 0x%04X, status 0x%04X: codec init %s, codec NAK %s, PLL locked %s" % (
            m.read(t.reg_by_name["version"]), s, "done" if s & 1 else "pending", "YES" if s & 2 else "no",
            "yes" if s & 4 else "NO"))
        print("effects %s, mute %s, level in %d, out %d" % (
            m.effects_text(m.read(0)), "on" if m.read(t.reg_by_name["control"]) & 2 else "off",
            m.read(t.reg_by_name["level_in"]), m.read(t.reg_by_name["level_out"])))
        if m.cab_available():
            cs = m.cab_status()
            print("cabinet %s, active bank %d, loaded slot %s" % (
                "on" if cs["enabled"] else "off", cs["active_bank"], "?" if cs["slot"] is None else cs["slot"]))
    elif a.cmd == "read":
        print("0x%04X" % m.read(t.register(a.args[0])))
    elif a.cmd == "write":
        m.write(t.register(a.args[0]), num(a.args[1]))
    elif a.cmd == "set":
        apply_assignments(m, parse_assignments(m, a.args))
    elif a.cmd == "get":
        cmd_get(m, a.args)
    elif a.cmd == "preset":
        cmd_preset(m, a.args)
    elif a.cmd == "codec":
        m.codec_write(m.codec_reg(a.args[0]), num(a.args[1]))
    elif a.cmd == "dump":
        for r in t.registers:
            if m.version >= r["min_version"]:
                print("%-15s 0x%02X = 0x%04X" % (r["name"], r["reg"], m.read(r["reg"])))
    elif a.cmd == "params":
        show_params(m)
    elif a.cmd == "chain":
        ch = m.chain()
        for i, e in enumerate(ch["effects"]):
            print("%d. %-28s %s" % (i + 1, e["name"], "on" if e["on"] else "off"))
        print("order %s" % ("editable" if ch["editable"] else "fixed (FPGA VERSION %04X)" % m.version))
    elif a.cmd == "cab":
        cmd_cab(m, a.args)
    elif a.cmd == "meter":
        count = num(a.args[0]) if a.args else None
        try:
            while count is None or count > 0:
                li, lo = m.read(t.reg_by_name["level_in"]), m.read(t.reg_by_name["level_out"])
                sys.stdout.write("\rin %5d %-20s out %5d %-20s" % (li, "#" * (li * 20 // 32768),
                                                                    lo, "#" * (lo * 20 // 32768)))
                sys.stdout.flush()
                time.sleep(0.1)
                if count is not None:
                    count -= 1
        except KeyboardInterrupt:
            print("")


def main():
    return run(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
