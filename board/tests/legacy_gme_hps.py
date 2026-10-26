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

Dynamics (step D5, enable bit 7 DYN): noise gate and compressor, first stage of the chain. Settings of `set`:
dyn=none|gate|comp|gate+comp (DYN_CTRL bits), gate_db / comp_db = thresholds in dBFS (e.g. -45, -20; stored as
Q8 log2 units, 1 unit = 0.0235 dB, signed), ratio = 1, 2, 4, 8 or inf (COMP_RATIO 0..4), attack_ms / release_ms
(rounded to the nearest power-of-two number of samples, COMP_ATTACK / COMP_RELEASE 0..15; the raw registers
gate_thresh, comp_thresh, comp_ratio, comp_attack, comp_release, comp_makeup are accepted as well), makeup_db
= make-up gain in dB. `status` shows the gain reduction (DYN_GR, 0x2C) in dB.
EQ (step D5, enable bit 8 EQ): `eq B M T` computes the coefficients of three biquads (low shelf 100 Hz, peaking
mid 800 Hz Q 0.9, high shelf 3.5 kHz; tools/eq_coefs.py, must be next to this script or in ../tools), writes
them through EQ_ADDR / EQ_DATA_LO / EQ_DATA_HI (16 words, the last is the scale word), applies them (EQ_APPLY:
all at once at one sample boundary) and switches the EQ on.

Output level (step D6, VERSION 0x0208): od_level / dist_level (registers 0x2D / 0x2E) scale the wet path of the
overdrive / distortion, signed Q8 log2 units like the dynamics thresholds (0 = exactly unity, -1020 = -24 dB, 512 = +12 dB,
clamped to -1024 .. +512); od_db / dist_db = the same in dB. The factory presets carry levels that make them as loud
as the clean signal (tools/level_presets.py computes them).

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
    # step D5: dynamics (signed thresholds / makeup in Q8 log2 units) and EQ coefficient port
    "dyn_ctrl": 0x21, "gate_thresh": 0x22, "comp_thresh": 0x23, "comp_ratio": 0x24, "comp_attack": 0x25,
    "comp_release": 0x26, "comp_makeup": 0x27,
    "eq_addr": 0x28, "eq_data_lo": 0x29, "eq_data_hi": 0x2A, "eq_apply": 0x2B,
    "dyn_gr": 0x2C,                      # read-only gain-reduction meter (Q8 log2 units, positive)
    # step D6: output level of the overdrive / distortion wet path, signed Q8 log2 units (0 = unity,
    # -1024 .. +512 = -24 .. +12 dB), smoothed in the FPGA
    "od_level": 0x2D, "dist_level": 0x2E,
}
REVERB_ROOMS = ((45875, 100), (52429, 80), (57672, 60), (61604, 40))     # reverb_type 0..3
CAB_TAPS = 2048
CAB_BIT = 64
DYN_BIT = 128
EQ_BIT = 256
KEEP_BITS = CAB_BIT | DYN_BIT | EQ_BIT      # presets leave these effects as they are
Q8_PER_DB = 256 / 6.0206                    # Q8 log2 units per dB
CAB_SETTLE = 0.02            # s: a bank switch (fade out 128 samples, fade in 128) takes 5.4 ms
EFFECT_REGS = [k for k in sorted(REGS, key=REGS.get) if REGS[k] <= 0x0E]   # Python 2: dicts unordered
EFFECT_BITS = {"OD": 1, "TREM": 2, "ECHO": 4, "DIST": 8, "CHORUS": 16, "REVERB": 32, "CAB": CAB_BIT,
               "DYN": DYN_BIT, "EQ": EQ_BIT}
DYN_MODES = {"none": 0, "gate": 1, "comp": 2, "gate+comp": 3}
COMP_RATIOS = {"1": 0, "2": 1, "4": 2, "8": 3, "inf": 4}
# tremolo free mode (step D1): trem_wave = 8 + shape, rate in trem_rate (0.01 Hz)
TREM_SHAPES = {"sine": 0, "triangle": 1, "saw": 2, "square": 3}

PRESETS = {
    "clean":  dict(effects_enable=0),
    "crunch": dict(effects_enable=EFFECT_BITS["DIST"] | EFFECT_BITS["REVERB"], dist_type=1, dist_mix=160, dist_level=-233,
                   reverb_type=1, reverb_mix=60),
    "lead":   dict(effects_enable=EFFECT_BITS["DIST"] | EFFECT_BITS["ECHO"] | EFFECT_BITS["REVERB"],
                   dist_type=2, dist_mix=220, dist_level=-544, echo_time=18000, echo_level=20000, echo_repeat=90,
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


def db_to_q8(db):
    """dB -> signed Q8 log2 units (rounded), as used by the threshold and makeup registers."""
    return int(round(float(db) * Q8_PER_DB))


def ms_to_shift(ms):
    """Attack / release time in ms -> k (time constant 2^k samples at 48 kHz), 0..15."""
    samples = max(1.0, float(ms) * 48.0)
    k = 0
    while k < 15 and abs((1 << (k + 1)) - samples) < abs((1 << k) - samples):
        k += 1
    return k


def parse_assignments(items):
    regs = {}
    for it in items:
        k, v = it.split("=", 1)
        if k == "dyn":
            if v not in DYN_MODES:
                raise SystemExit("dyn: %s" % ", ".join(sorted(DYN_MODES)))
            regs["dyn_ctrl"] = DYN_MODES[v]
        elif k == "gate_db":
            regs["gate_thresh"] = db_to_q8(v)
        elif k == "comp_db":
            regs["comp_thresh"] = db_to_q8(v)
        elif k == "makeup_db":
            regs["comp_makeup"] = db_to_q8(v)
        elif k == "od_db":
            regs["od_level"] = db_to_q8(v)
        elif k == "dist_db":
            regs["dist_level"] = db_to_q8(v)
        elif k == "ratio":
            if v not in COMP_RATIOS:
                raise SystemExit("ratio: 1, 2, 4, 8 or inf")
            regs["comp_ratio"] = COMP_RATIOS[v]
        elif k == "attack_ms":
            regs["comp_attack"] = ms_to_shift(v)
        elif k == "release_ms":
            regs["comp_release"] = ms_to_shift(v)
        elif k == "effects":
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


def load_eq_coefs():
    """tools/eq_coefs.py (pure math, Python 2.7 / 3) from this script's directory or ../tools."""
    here = os.path.dirname(os.path.abspath(__file__))
    for d in (here, os.path.join(here, "..", "tools")):
        if os.path.exists(os.path.join(d, "eq_coefs.py")):
            if d not in sys.path:
                sys.path.insert(0, d)
            import eq_coefs
            return eq_coefs
    raise SystemExit("eq_coefs.py not found next to gme_hps.py (copy tools/eq_coefs.py to the board)")


def eq_words(bass, mid, treble):
    """The 16 words for the EQ write port: 15 signed coefficients (18-bit two's complement) and the scale word."""
    ec = load_eq_coefs()
    try:
        ints, shifts, clipped = ec.coefficient_set_full(bass, mid, treble)
    except ValueError as e:
        raise SystemExit(str(e))
    return [ec.word18(v) for v in ints] + [ec.scale_word(shifts)]


def eq_load(b, words):
    """Write the 16 words through EQ_ADDR / DATA_LO / DATA_HI (the pointer auto-increments), then EQ_APPLY."""
    b.write(REGS["eq_addr"], 0)
    for w in words:
        b.write(REGS["eq_data_lo"], w & 0xFFFF)
        b.write(REGS["eq_data_hi"], (w >> 16) & 3)
    b.write(REGS["eq_apply"], 1)


def eq_command(b, args):
    if b.read(REGS["version"]) < 0x0207:
        raise SystemExit("the EQ needs VERSION 0x0207 or later")
    en = b.read(REGS["effects_enable"])
    if len(args) == 1 and args[0] in ("on", "off"):
        b.write(REGS["effects_enable"], (en & ~EQ_BIT) | (EQ_BIT if args[0] == "on" else 0))
    elif len(args) == 3:
        gains = [float(a) for a in args]
        if any(abs(g) > 12.0 for g in gains):
            raise SystemExit("EQ gains are limited to -12 .. +12 dB")
        eq_load(b, eq_words(*gains))
        b.write(REGS["effects_enable"], en | EQ_BIT)
        print("EQ bass %+g dB, mid %+g dB, treble %+g dB" % tuple(gains))
    else:
        raise SystemExit("eq BASS MID TREBLE (dB, -12..12) | eq on | eq off")


class FakeBoard(object):
    """Records register writes (selftest)."""

    def __init__(self, regs=None):
        self.regs = dict(regs or {})
        self.log = []

    def read(self, reg):
        return self.regs.get(reg, 0)

    def write(self, reg, value):
        self.log.append((reg, value & 0xFFFF))
        self.regs[reg] = value & 0xFFFF


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
                                                  "reverb_size", "reverb_damp", "od_level", "dist_level"}
    # D6 output levels: dB -> Q8 units, signed register values, presets carry compensation levels
    assert parse_assignments(["od_db=-3", "dist_db=-6"]) == {"od_level": -128, "dist_level": -255}
    assert (db_to_q8(-24) & 0xFFFF) == 0xFC04 and db_to_q8(12) == 510 and REGS["od_level"] == 0x2D and REGS["dist_level"] == 0x2E
    for n in ("crunch", "lead"):
        assert -1024 <= PRESETS[n]["dist_level"] <= 512
    assert PRESETS["hall"]["reverb_type"] == 4 and REVERB_ROOMS[3] == (61604, 40)
    assert parse_assignments(["reverb_type=4", "reverb_size=60000", "reverb_damp=30"]) ==         {"reverb_type": 4, "reverb_size": 60000, "reverb_damp": 30}
    # dynamics settings
    r = parse_assignments(["dyn=gate+comp", "gate_db=-45", "comp_db=-20", "ratio=4", "makeup_db=3",
                           "attack_ms=2", "release_ms=100"])
    assert r == {"dyn_ctrl": 3, "gate_thresh": -1913, "comp_thresh": -850, "comp_ratio": 2, "comp_makeup": 128,
                 "comp_attack": 6, "comp_release": 12}, r
    assert parse_assignments(["ratio=inf", "effects=DYN+EQ"]) == {"comp_ratio": 4, "effects_enable": 384}
    assert ms_to_shift(0.01) == 0 and ms_to_shift(1000) == 15 and ms_to_shift(0.34) == 4
    assert (db_to_q8(-20) & 0xFFFF) == 0xFCAE and REGS["dyn_gr"] == 0x2C
    # EQ: flat set = unity coefficients; 16 words through the write port, apply, enable
    w = eq_words(0, 0, 0)
    assert len(w) == 16 and w[0] == 65536 and w[5] == 65536 and w[10] == 65536 and w[15] == 0 and sum(w[1:5]) == 0
    fb = FakeBoard({REGS["version"]: 0x0207, REGS["effects_enable"]: 0x0008})
    eq_command(fb, ["6", "-3", "2"])
    exp = eq_words(6, -3, 2)
    assert fb.log[0] == (REGS["eq_addr"], 0) and len(fb.log) == 1 + 32 + 1 + 1
    for i, wd in enumerate(exp):
        assert fb.log[1 + 2 * i] == (REGS["eq_data_lo"], wd & 0xFFFF) and fb.log[2 + 2 * i] == (REGS["eq_data_hi"], wd >> 16)
    assert fb.log[33] == (REGS["eq_apply"], 1) and fb.log[34] == (REGS["effects_enable"], 0x0108)
    eq_command(fb, ["off"])
    assert fb.regs[REGS["effects_enable"]] == 0x0008
    try:
        eq_command(fb, ["13", "0", "0"])
        raise AssertionError("eq accepted 13 dB")
    except SystemExit:
        pass
    print("selftest OK")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-check", action="store_true", help="skip the VERSION check")
    ap.add_argument("--cab-dir", default=os.environ.get(
        "GME_CAB_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "cab")),
        help="directory with the cabNN.coef files (default: ./cab next to this script)")
    ap.add_argument("cmd", choices=["status", "read", "write", "set", "preset", "codec", "dump",
                                    "meter", "cab", "eq", "selftest"])
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
        if b.read(REGS["version"]) >= 0x0207:
            print("dynamics gain reduction %.1f dB" % (b.read(REGS["dyn_gr"]) / Q8_PER_DB))
    elif a.cmd == "read":
        print("0x%04X" % b.read(num(a.args[0])))
    elif a.cmd == "write":
        b.write(num(a.args[0]), num(a.args[1]))
    elif a.cmd == "set":
        for k, v in parse_assignments(a.args).items():
            b.write(REGS[k], v)
    elif a.cmd == "cab":
        cab_command(b, a.args, a.cab_dir)
    elif a.cmd == "eq":
        eq_command(b, a.args)
    elif a.cmd == "preset":
        if not a.args or a.args[0] not in PRESETS:
            raise SystemExit("presets: %s" % ", ".join(PRESETS))
        keys = EFFECT_REGS + ["trem_rate", "mod_base", "mod_fb", "mod_shape", "reverb_size", "reverb_damp"]
        if b.read(REGS["version"]) >= 0x0208:
            keys = keys + ["od_level", "dist_level"]
        regs = dict((k, 0) for k in keys)
        regs.update(dict((k, v) for k, v in PRESETS[a.args[0]].items() if k in regs))
        regs["effects_enable"] |= b.read(REGS["effects_enable"]) & KEEP_BITS    # cabinet, dynamics, EQ stay as they are
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
