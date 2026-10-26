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
    python gme_hps.py selftest                   (no hardware needed)

Reverb (step D4, Freeverb): reverb_type 0..3 = rooms very light / light / medium / heavy
(size 0.70 / 0.80 / 0.88 / 0.94, damp 100 / 80 / 60 / 40), 4 = custom from reverb_size
(Q0.16, 65535 = 1.0, limited to 0.98 inside) and reverb_damp (0..255, higher = darker tail).

Cabinet files (step D3): built on the PC with  python3 tools/cab_coefs.py --build  (ir/build/cabNN.coef,
text: name, shift, 2048 signed integers), copied to the board (scp ir/build/*.coef root@board:cab/) and
found in the directory "cab" next to this script (--cab-dir DIR or GME_CAB_DIR to change).

Every command first checks the VERSION register (0x02xx), so nothing is written
when another FPGA image is loaded. Works with Python 2.7 and 3.
"""
import argparse
import ctypes
import glob
import re
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
    # step D2: modulated delay (chorus / flanger / vibrato). chorus_level = mix 0..255,
    # chorus_depth = depth in samples, chorus_rate = LFO rate in 0.01 Hz
    "mod_base": 0x18, "mod_fb": 0x19, "mod_shape": 0x1A,
    # step D3: cabinet. cab_ctrl: bit 0 active bank, 3:1 shift of bank 0, 6:4 shift of bank 1;
    # cab_addr: bit 11 bank, 10:0 tap (write pointer); cab_data_lo/hi: coefficient bits 15:0 / 17:16
    # (writing hi performs the write and increments the pointer)
    "cab_ctrl": 0x1B, "cab_addr": 0x1C, "cab_data_lo": 0x1D, "cab_data_hi": 0x1E,
    # step D4: reverb size (feedback, Q0.16) and damping (0..255), used with reverb_type = 4
    "reverb_size": 0x1F, "reverb_damp": 0x20,
}
REVERB_ROOMS = ((45875, 100), (52429, 80), (57672, 60), (61604, 40))     # reverb_type 0..3
CAB_TAPS = 2048
CAB_BIT = 64
CAB_SETTLE = 0.02            # s: a bank switch (fade out 128 samples, fade in 128) takes 5.4 ms
EFFECT_REGS = [k for k in sorted(REGS, key=REGS.get) if REGS[k] <= 0x0E]   # Python 2: dicts unordered
EFFECT_BITS = {"OD": 1, "TREM": 2, "ECHO": 4, "DIST": 8, "CHORUS": 16, "REVERB": 32, "CAB": CAB_BIT}
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
                    chorus_level=110, chorus_depth=144, chorus_rate=60, mod_base=720,
                    echo_time=24000, echo_level=26000, echo_repeat=140, reverb_type=3, reverb_mix=128),
    "chorus":  dict(effects_enable=EFFECT_BITS["CHORUS"], chorus_level=128, chorus_depth=144,
                    chorus_rate=80, mod_base=720),
    "flanger": dict(effects_enable=EFFECT_BITS["CHORUS"], chorus_level=128, chorus_depth=90,
                    chorus_rate=30, mod_base=96, mod_fb=26000, mod_shape=1),
    "vibrato": dict(effects_enable=EFFECT_BITS["CHORUS"], chorus_level=255, chorus_depth=100,
                    chorus_rate=600, mod_base=240),
    "hall":   dict(effects_enable=EFFECT_BITS["REVERB"], reverb_type=4, reverb_size=60500,
                   reverb_damp=30, reverb_mix=110),
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

    def cab_load(self, coefs, shift):
        """Load 2048 coefficients into the idle cabinet bank, set its shift, switch to it.
        (The FPGA ignores writes to the active bank; the idle bank is the one CAB_CTRL does not select.)"""
        time.sleep(CAB_SETTLE)                                   # a previous switch must be finished
        ctrl = self.read(REGS["cab_ctrl"])
        bank = (ctrl & 1) ^ 1
        self.write(REGS["cab_addr"], bank << 11)
        for c in coefs:                                          # pointer auto-increments on cab_data_hi
            self.write(REGS["cab_data_lo"], c & 0xFFFF)
            self.write(REGS["cab_data_hi"], (c >> 16) & 3)
        self.write(REGS["cab_ctrl"], cab_ctrl_value(ctrl, bank, shift))
        time.sleep(CAB_SETTLE)

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


def parse_coef(text):
    """cabNN.coef (tools/cab_coefs.py --build): name, shift, 2048 signed 18-bit integers -> (name, shift, list)."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if len(lines) != 2 + CAB_TAPS:
        raise ValueError("expected name, shift and %d coefficients, found %d lines" % (CAB_TAPS, len(lines)))
    name, shift = lines[0], int(lines[1])
    coefs = [int(l) for l in lines[2:]]
    if not 0 <= shift <= 7:
        raise ValueError("shift %d not in 0..7" % shift)
    if min(coefs) < -(1 << 17) or max(coefs) >= 1 << 17:
        raise ValueError("coefficient outside the signed 18-bit range")
    return name, shift, coefs


def cab_ctrl_value(old, bank, shift):
    """CAB_CTRL after loading `bank` with `shift` and selecting it (the other bank's shift is kept)."""
    if bank:
        return (old & 0x0E) | ((shift & 7) << 4) | 1
    return (old & 0x70) | ((shift & 7) << 1)


def cab_files(directory):
    """{slot: path} of the cabNN.coef files in `directory`."""
    out = {}
    for path in glob.glob(os.path.join(directory, "cab*.coef")):
        m = re.match(r"cab(\d+)\.coef$", os.path.basename(path))
        if m:
            out[int(m.group(1))] = path
    return out


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


def cab_command(b, args, directory):
    if b.read(REGS["version"]) < 0x0205:
        raise SystemExit("the cabinet needs VERSION 0x0205 or later")
    if not args:
        raise SystemExit("cab list | cab N | cab on | cab off")
    cmd = args[0]
    files = cab_files(directory)
    if cmd == "list":
        if not files:
            print("no cabNN.coef files in %s (build: python3 tools/cab_coefs.py --build, then scp)" % directory)
        for slot in sorted(files):
            with open(files[slot]) as f:
                name, shift = f.readline().strip(), f.readline().strip()
            print("%2d  %-28s shift %s  (%s)" % (slot, name, shift, files[slot]))
        ctrl, en = b.read(REGS["cab_ctrl"]), b.read(REGS["effects_enable"])
        print("cabinet %s, bank %d active, shifts %d / %d" % ("ON" if en & CAB_BIT else "off", ctrl & 1,
                                                          (ctrl >> 1) & 7, (ctrl >> 4) & 7))
    elif cmd in ("on", "off"):
        en = b.read(REGS["effects_enable"]) & ~CAB_BIT
        b.write(REGS["effects_enable"], en | (CAB_BIT if cmd == "on" else 0))
    else:
        slot = num(cmd)
        if slot not in files:
            raise SystemExit("no cab%02d.coef in %s (cab list)" % (slot, directory))
        with open(files[slot]) as f:
            name, shift, coefs = parse_coef(f.read())
        b.cab_load(coefs, shift)
        print("cabinet %d '%s' loaded (shift %d)%s" % (slot, name, shift,
              "" if b.read(REGS["effects_enable"]) & CAB_BIT else "; the cabinet is off: cab on"))


def selftest():
    r = parse_assignments(["effects=DIST+ECHO", "od_gain=4", "echo_time=0x3840"])
    assert r == {"effects_enable": 12, "od_gain": 4, "echo_time": 14400}, r
    assert effects_text(12) == "ECHO+DIST"
    assert parse_assignments(["effects=DIST+CAB"]) == {"effects_enable": 72}
    text = "Test cab\n3\n" + "\n".join(str(((i * 7919) % 262144) - 131072) for i in range(CAB_TAPS)) + "\n"
    name, shift, c = parse_coef(text)
    assert (name, shift, len(c)) == ("Test cab", 3, CAB_TAPS) and c[1] == 7919 - 131072
    for bad in (text.replace("\n3\n", "\n9\n"), text + "1\n", text.replace("-131072", "131072")):
        try:
            parse_coef(bad)
            raise AssertionError("parse_coef accepted a bad file")
        except ValueError:
            pass
    assert cab_ctrl_value(0, 1, 5) == 0x51 and cab_ctrl_value(0x51, 0, 3) == 0x56
    assert cab_ctrl_value(0x46, 1, 7) == 0x77 and cab_ctrl_value(0x77, 0, 0) == 0x70
    assert ((0x02 & 0x7F) << 9) | 0x079 == 0x0479                 # CODEC word for R2 = 0x079
    assert parse_assignments(["trem_shape=square", "trem_hz=6.5"]) == {"trem_wave": 11, "trem_rate": 650}
    for p in PRESETS.values():
        assert set(p) <= set(EFFECT_REGS) | {"trem_rate", "mod_base", "mod_fb", "mod_shape",
                                                  "reverb_size", "reverb_damp"}
    assert PRESETS["hall"]["reverb_type"] == 4 and REVERB_ROOMS[3] == (61604, 40)
    assert parse_assignments(["reverb_type=4", "reverb_size=60000", "reverb_damp=30"]) ==         {"reverb_type": 4, "reverb_size": 60000, "reverb_damp": 30}
    print("selftest OK")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-check", action="store_true", help="skip the VERSION check")
    ap.add_argument("--cab-dir", default=os.environ.get(
        "GME_CAB_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "cab")),
        help="directory with the cabNN.coef files (default: ./cab next to this script)")
    ap.add_argument("cmd", choices=["status", "read", "write", "set", "preset", "codec", "dump",
                                    "meter", "cab", "selftest"])
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
    elif a.cmd == "cab":
        cab_command(b, a.args, a.cab_dir)
    elif a.cmd == "preset":
        if not a.args or a.args[0] not in PRESETS:
            raise SystemExit("presets: %s" % ", ".join(PRESETS))
        keys = EFFECT_REGS + ["trem_rate", "mod_base", "mod_fb", "mod_shape", "reverb_size", "reverb_damp"]
        regs = dict((k, 0) for k in keys)
        regs.update(PRESETS[a.args[0]])
        regs["effects_enable"] |= b.read(REGS["effects_enable"]) & CAB_BIT      # the cabinet stays as it is
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
