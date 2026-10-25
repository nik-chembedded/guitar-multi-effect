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
    python gme_hps.py preset crunch
    python gme_hps.py codec 0x00 0x080           (codec register, 9-bit value: mute line in)
    python gme_hps.py dump
    python gme_hps.py meter                      (input/output levels, Ctrl+C to stop)
    python gme_hps.py selftest                   (no hardware needed)

Every command first checks the VERSION register (0x02xx), so nothing is written
when another FPGA image is loaded. Works with Python 2.7 and 3.
"""
import argparse
import ctypes
import mmap
import os
import sys
import time

LW_BRIDGE = 0xFF200000
SPAN = 0x100

REGS = {
    "effects_enable": 0x00, "od_drive": 0x01, "od_gain": 0x02, "trem_wave": 0x03,
    "trem_depth": 0x04, "echo_time": 0x05, "echo_repeat": 0x06, "echo_level": 0x07,
    "dist_mix": 0x08, "dist_type": 0x09, "chorus_level": 0x0A, "chorus_depth": 0x0B,
    "chorus_rate": 0x0C, "reverb_mix": 0x0D, "reverb_type": 0x0E,
    "version": 0x10, "status": 0x11, "level_in": 0x12, "level_out": 0x13, "control": 0x14,
    "codec": 0x15, "trem_rate": 0x16,
}
EFFECT_REGS = [k for k in sorted(REGS, key=REGS.get) if REGS[k] <= 0x0E]   # Python 2: dicts unordered
EFFECT_BITS = {"OD": 1, "TREM": 2, "ECHO": 4, "DIST": 8, "CHORUS": 16, "REVERB": 32}
# tremolo free mode (step D1): trem_wave = 8 + shape, rate in trem_rate (0.01 Hz)
TREM_SHAPES = {"sine": 0, "triangle": 1, "saw": 2, "square": 3}

PRESETS = {
    "clean":  dict(effects_enable=0),
    "crunch": dict(effects_enable=EFFECT_BITS["DIST"] | EFFECT_BITS["REVERB"], dist_type=1, dist_mix=160,
                   reverb_type=1, reverb_mix=60),
    "lead":   dict(effects_enable=EFFECT_BITS["DIST"] | EFFECT_BITS["ECHO"] | EFFECT_BITS["REVERB"],
                   dist_type=2, dist_mix=220, echo_time=18000, echo_level=20000, echo_repeat=90,
                   reverb_type=2, reverb_mix=80),
    "ambient": dict(effects_enable=EFFECT_BITS["CHORUS"] | EFFECT_BITS["ECHO"] | EFFECT_BITS["REVERB"],
                    chorus_level=30000, chorus_depth=400, chorus_rate=40, echo_time=24000,
                    echo_level=26000, echo_repeat=140, reverb_type=3, reverb_mix=128),
    "trem":   dict(effects_enable=EFFECT_BITS["TREM"], trem_wave=0, trem_depth=200),
    "pulse":  dict(effects_enable=EFFECT_BITS["TREM"], trem_wave=8 + TREM_SHAPES["square"],
                   trem_rate=650, trem_depth=180),
}


class Board(object):
    """32-bit register access through /dev/mem.

    Accesses go through a ctypes uint32 array: one 32-bit load/store per
    register. (struct.pack_into('<I', ...) writes byte by byte, i.e. four bus
    writes; the FPGA handles that too since it honours byte enables.)"""

    def __init__(self, base=LW_BRIDGE, check=True):
        fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
        try:
            self.mem = mmap.mmap(fd, SPAN, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE,
                                 offset=base)
        finally:
            os.close(fd)
        self.words = (ctypes.c_uint32 * (SPAN // 4)).from_buffer(self.mem)
        if check:
            v = self.read(REGS["version"])
            if v & 0xFF00 != 0x0200:
                raise SystemExit("VERSION reads 0x%04X, not 0x02xx: is the multi-effect FPGA image "
                                 "loaded? (--no-check to skip)" % v)

    def read(self, reg):
        return self.words[reg] & 0xFFFF

    def write(self, reg, value):
        self.words[reg] = value & 0xFFFF

    def codec(self, reg, value9, timeout=0.1):
        """One WM8731 register write over the FPGA's I2C master."""
        self.wait_codec(timeout)
        self.write(REGS["codec"], ((reg & 0x7F) << 9) | (value9 & 0x1FF))
        st = self.wait_codec(timeout)
        if st & 2:
            raise IOError("codec did not ACK the write")
        if st & 4:
            raise IOError("write dropped: I2C master was busy")

    def wait_codec(self, timeout):
        t0 = time.time()
        while True:
            st = self.read(REGS["codec"])
            if not st & 1:
                return st
            if time.time() - t0 > timeout:
                raise IOError("I2C master busy for %.0f ms" % (timeout * 1e3))
            time.sleep(0.001)


def num(s):
    return int(s, 0)


def parse_assignments(items):
    regs = {}
    for it in items:
        k, v = it.split("=", 1)
        if k == "effects":
            if v[:1].isdigit():
                regs["effects_enable"] = num(v)
            else:
                regs["effects_enable"] = sum(EFFECT_BITS[e.strip().upper()] for e in v.split("+") if e.strip())
        elif k == "trem_shape":
            if v not in TREM_SHAPES:
                raise SystemExit("trem_shape: %s" % ", ".join(sorted(TREM_SHAPES)))
            regs["trem_wave"] = 8 + TREM_SHAPES[v]
        elif k == "trem_hz":
            regs["trem_rate"] = int(round(float(v) * 100))
        elif k in REGS:
            regs[k] = num(v)
        else:
            raise SystemExit("unknown register '%s' (known: %s)" % (k, ", ".join(REGS)))
    return regs


def effects_text(v):
    return "+".join(n for n, b in sorted(EFFECT_BITS.items(), key=lambda x: x[1]) if v & b) or "none"


def selftest():
    r = parse_assignments(["effects=DIST+ECHO", "od_gain=4", "echo_time=0x3840"])
    assert r == {"effects_enable": 12, "od_gain": 4, "echo_time": 14400}, r
    assert effects_text(12) == "ECHO+DIST"
    assert ((0x02 & 0x7F) << 9) | 0x079 == 0x0479                 # CODEC word for R2 = 0x079
    assert parse_assignments(["trem_shape=square", "trem_hz=6.5"]) == {"trem_wave": 11, "trem_rate": 650}
    for p in PRESETS.values():
        assert set(p) <= set(EFFECT_REGS) | {"trem_rate"}
    print("selftest OK")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-check", action="store_true", help="skip the VERSION check")
    ap.add_argument("cmd", choices=["status", "read", "write", "set", "preset", "codec", "dump",
                                    "meter", "selftest"])
    ap.add_argument("args", nargs="*")
    a = ap.parse_args()
    if a.cmd == "selftest":
        return selftest()
    b = Board(check=not a.no_check)
    if a.cmd == "status":
        s = b.read(REGS["status"])
        print("version 0x%04X, status 0x%04X: codec init %s, codec NAK %s, PLL locked %s" % (
            b.read(REGS["version"]), s, "done" if s & 1 else "pending", "YES" if s & 2 else "no",
            "yes" if s & 4 else "NO"))
        print("effects %s, mute %s, level in %d, out %d" % (
            effects_text(b.read(REGS["effects_enable"])), "on" if b.read(REGS["control"]) & 2 else "off",
            b.read(REGS["level_in"]), b.read(REGS["level_out"])))
    elif a.cmd == "read":
        print("0x%04X" % b.read(num(a.args[0])))
    elif a.cmd == "write":
        b.write(num(a.args[0]), num(a.args[1]))
    elif a.cmd == "set":
        for k, v in parse_assignments(a.args).items():
            b.write(REGS[k], v)
    elif a.cmd == "preset":
        if not a.args or a.args[0] not in PRESETS:
            raise SystemExit("presets: %s" % ", ".join(PRESETS))
        keys = EFFECT_REGS + ["trem_rate"]
        regs = dict((k, 0) for k in keys)
        regs.update(PRESETS[a.args[0]])
        for k in keys:
            b.write(REGS[k], regs[k])
        print("preset '%s' loaded" % a.args[0])
    elif a.cmd == "codec":
        b.codec(num(a.args[0]), num(a.args[1]))
    elif a.cmd == "dump":
        for k in sorted(REGS, key=REGS.get):
            print("%-15s 0x%02X = 0x%04X" % (k, REGS[k], b.read(REGS[k])))
    elif a.cmd == "meter":
        try:
            while True:
                li, lo = b.read(REGS["level_in"]), b.read(REGS["level_out"])
                sys.stdout.write("\rin %5d %-20s out %5d %-20s" % (li, "#" * (li * 20 // 32768),
                                                                    lo, "#" * (lo * 20 // 32768)))
                sys.stdout.flush()
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("")


if __name__ == "__main__":
    sys.exit(main())
