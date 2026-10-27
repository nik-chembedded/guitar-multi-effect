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
    python gme_hps.py cab list                   (cabinets in the cab directory)
    python gme_hps.py cab 3                      (load cabinet 3 into the idle bank and switch to it)
    python gme_hps.py cab off                    (cabinet effect off / on; also: effects=...+CAB)
    python gme_hps.py set   reverb_type=4 reverb_size=60000 reverb_damp=30   (custom reverb: size Q0.16, damp 0..255)
    python gme_hps.py set   effects=DYN dyn=gate+comp gate_db=-45 comp_db=-20 ratio=4 makeup_db=3 attack_ms=2 release_ms=100
    python gme_hps.py eq 6 -3 2                  (EQ: bass, mid, treble in dB, -12..+12; switches the EQ on)
    python gme_hps.py eq off                     (EQ off / on again with the last setting: eq on)
    python gme_hps.py set   od_db=-3 dist_db=-6  (output level of the overdrive / distortion in dB, -24 .. +12)
    python gme_hps.py selftest                   (no hardware needed)

By parameter id, in display units (a number with its unit; a bare number is the raw
register value, as in the old command line):

    python gme_hps.py set   echo_time=320ms trem_rate=6.5Hz echo_on=on dist_type=heavy
    python gme_hps.py get   echo_time trem_rate  (no argument: all parameters)
    python gme_hps.py params                     (the parameter table)
    python gme_hps.py cab   list | N | on | off | status   (cabinet simulator, FPGA VERSION >= 0x0205)
    python gme_hps.py chain                      (effect order, read from the FPGA)
    python gme_hps.py chain dyn od dist cab eq mod trem echo reverb   (set the order, VERSION >= 0x0209)
    python gme_hps.py chain reset                (factory order)
    python gme_hps.py preset list | save NAME | delete NAME

Dynamics (VERSION >= 0x0207, enable bit DYN): dyn=none|gate|comp|gate+comp, gate_db / comp_db = thresholds
in dBFS, ratio = 1, 2, 4, 8 or inf, attack_ms / release_ms (rounded to the nearest power-of-two number of
samples), makeup_db; the raw registers gate_thresh, comp_thresh, comp_ratio, comp_attack, comp_release,
comp_makeup are accepted as well.  `status` shows the gain reduction (DYN_GR).  EQ (enable bit EQ): `eq B M T`
computes the biquad coefficients (gme/eq_coefs.py), writes them through EQ_ADDR / EQ_DATA_LO / EQ_DATA_HI,
applies them (EQ_APPLY) and switches the EQ on; the gains are kept in settings.json (eq_bass, eq_mid,
eq_treble in dB, 0.1 dB steps, also settable with `set`).  Output level (VERSION >= 0x0208): od_db / dist_db or
the raw od_level / dist_level (signed Q8 log2 units).  Reverb: reverb_type 4 = custom from reverb_size / reverb_damp.

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
            "get", "params", "cab", "chain", "eq"]
# tremolo free mode (step D1): trem_wave = 8 + shape, rate in trem_rate (0.01 Hz)
TREM_SHAPES = {"sine": 0, "triangle": 1, "saw": 2, "square": 3}
PRESET_EXTRA = ("list", "save", "delete")
DYN_MODES = {"none": 0, "gate": 1, "comp": 2, "gate+comp": 3}
COMP_RATIOS = {"1": 0, "2": 1, "4": 2, "8": 3, "inf": 4}
# names of the old command line that are given in display units (dB, ms) instead of raw register values
DISPLAY_KEYS = {"gate_db": "gate_thresh", "comp_db": "comp_thresh", "makeup_db": "comp_makeup",
                "od_db": "od_level", "dist_db": "dist_level", "attack_ms": "comp_attack",
                "release_ms": "comp_release"}
Q8_PER_DB = gd.Q8_PER_DB


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
            elif k == "dyn":
                if v not in DYN_MODES:
                    raise SystemExit("dyn: %s" % ", ".join(sorted(DYN_MODES)))
                out.append(("reg", t.reg_by_name["dyn_ctrl"], DYN_MODES[v]))
            elif k == "ratio":
                if v not in COMP_RATIOS:
                    raise SystemExit("ratio: 1, 2, 4, 8 or inf")
                out.append(("param", "comp_ratio", COMP_RATIOS[v]))
            elif k in DISPLAY_KEYS:
                p = t.by_id[DISPLAY_KEYS[k]]
                out.append(("param", p.id, p.parse(v)))
            elif k in t.by_id:
                p = t.by_id[k]
                out.append(("param", p.id, p.parse(v, legacy_raw=not p.virtual)))     # eq_*: a bare number is dB
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
    dev = gd.Mock(version=0x0208)
    m = gm.Model(dev)
    r = parse_assignments(m, ["effects=DIST+ECHO", "od_gain=4", "echo_time=0x3840"])
    assert r == [("reg", 0, 12), ("param", "od_gain", 4), ("param", "echo_time", 14400)], r
    assert m.effects_text(12) == "ECHO+DIST"
    assert ((0x02 & 0x7F) << 9) | 0x079 == 0x0479                 # CODEC word for R2 = 0x079
    r = parse_assignments(m, ["trem_shape=square", "trem_hz=6.5"])
    assert r == [("param", "trem_wave", 11), ("param", "trem_rate", 650)], r
    r = parse_assignments(m, ["dyn=gate+comp", "gate_db=-45", "comp_db=-20", "ratio=4", "makeup_db=3",
                              "attack_ms=2", "release_ms=100", "od_db=-3", "dist_db=-6"])
    assert r == [("reg", 0x21, 3), ("param", "gate_thresh", -1913), ("param", "comp_thresh", -850),
                 ("param", "comp_ratio", 2), ("param", "comp_makeup", 128), ("param", "comp_attack", 6),
                 ("param", "comp_release", 12), ("param", "od_level", -128), ("param", "dist_level", -255)], r
    words = gm.Model.eq_words(0, 0, 0)
    assert len(words) == 16 and words[0] == 65536 and words[5] == 65536 and words[10] == 65536 and words[15] == 0
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
        reg = "model" if p.virtual else "0x%02X" % p.reg
        if p.virtual:
            bits = ""
        print("%-12s %-7s %-6s %-6s %-22s %04X%s %s" % (
            p.id, reg, bits, p.type, rng[:22], p.min_version, " " if m.available(p) else "!", p.help))


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
    if sub != "status" and not m.cab_available():
        raise SystemExit("the cabinet needs VERSION 0x0205 or later")
    if sub == "list":
        slots = m.cab_list()
        if not slots:
            print("no cabNN.coef files in %s (build: python3 tools/cab_coefs.py --build, then scp)" % m.cab_dir)
        for c in slots:
            print("%2d  %-28s shift %s%s" % (c["slot"], c["name"], c["shift"],
                                             "   <- loaded" if c["slot"] == m.cab_slot else ""))
        if m.cab_available():
            cs = m.cab_status()
            ctl = m.read(m.table.reg_by_name["cab_ctrl"])
            print("cabinet %s, bank %d active, shifts %d / %d" % ("ON" if cs["enabled"] else "off", ctl & 1,
                                                                  (ctl >> 1) & 7, (ctl >> 4) & 7))
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
        print("cabinet %d '%s' loaded into bank %d (shift %d)%s" % (
            r["slot"], r["name"], r["bank"], r["shift"],
            "" if m.cab_status()["enabled"] else "; the cabinet is off: cab on"))


def cmd_eq(m, args):
    if not m.eq_available():
        raise SystemExit("the EQ needs VERSION 0x0207 or later")
    usage = "eq BASS MID TREBLE (dB, -12..12) | eq on | eq off"
    if len(args) == 1 and args[0] in ("on", "off"):
        m.set({"eq_on": args[0] == "on"})
    elif len(args) == 3:
        try:
            gains = [float(a) for a in args]
        except ValueError:
            raise SystemExit(usage)
        if any(abs(g) > 12.0 for g in gains):
            raise SystemExit("EQ gains are limited to -12 .. +12 dB")
        m.eq_set(*gains)
        m.set({"eq_on": True})
        print("EQ bass %+g dB, mid %+g dB, treble %+g dB" % tuple(gains))
    else:
        raise SystemExit(usage)


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
    ap.add_argument("--mock-version", type=num, default=0x0209, help="VERSION of the mock (default 0x0209)")
    ap.add_argument("--mock-state", default=None, metavar="FILE",
                    help="with --mock: keep the mock registers in this JSON file, shared between calls "
                         "(default ~/.gme_mock_state.json)")
    ap.add_argument("--data-dir", default=None, help="presets/ and settings.json (default: next to this script)")
    ap.add_argument("--cab-dir", default=None, help="cabNN.coef files (default: <data-dir>/cab; with --mock ../ir/build if it has cabinet files)")
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
    m = gm.Model(dev, store=Store(data_dir), cab_dir=a.cab_dir or gm.default_cab_dir(data_dir, a.mock))
    try:
        return dispatch(m, a)
    except (gm.ParamError, gm.CabinetError, gm.NotEditable, gd.DeviceError, StoreError) as e:
        raise SystemExit(str(e))


def cmd_chain(m, args):
    if args:
        if len(args) == 1 and args[0].lower() == "reset":
            order = [i for i in m.table.chain_default if m.version >= m.table.fx_by_id[i]["min_version"]]
        else:
            order = []
            for x in args:
                fid = m.table.legacy_effect_names.get(x.upper(), x.lower())
                if fid not in m.table.fx_by_id:
                    raise SystemExit("unknown effect '%s' (%s)" % (x, ", ".join(e["id"] for e in m.table.effects)))
                order.append(fid)
        m.set_chain(order)
    ch = m.chain()
    for i, e in enumerate(ch["effects"]):
        print("%d. %-28s %s" % (i + 1, e["name"], "on" if e["on"] else "off"))
    print("order %s" % ("editable" if ch["editable"] else "fixed (FPGA VERSION %04X)" % m.version))


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
        if m.version >= gd.DYN_VERSION:
            print("dynamics gain reduction %.1f dB" % (m.read(t.reg_by_name["dyn_gr"]) / Q8_PER_DB))
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
        cmd_chain(m, a.args)
    elif a.cmd == "cab":
        cmd_cab(m, a.args)
    elif a.cmd == "eq":
        cmd_eq(m, a.args)
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
