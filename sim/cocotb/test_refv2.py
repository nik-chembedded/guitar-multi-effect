"""
test_refv2.py - v2 reference regression of the 24-bit effect chain.

GME_REF_MODE=record : run every preset and save the outputs to ref_v2/<preset>.npy
GME_REF_MODE=check  : (default) run the same presets and require identical output
GME_REF_ONLY=a,b,.. : with GME_REF_MODE=record, write only these presets' files; every other
                      preset is still run and checked bit-exact in the same simulation (so a
                      step that changes some effects on purpose can prove the rest unchanged)

The v2 references replace the v1 recordings (step D2, 2026-10-25): they were
recorded from the chain after every block in it had been verified on its own
(bit-exact to its Python model, and the unchanged v1 effects bit-exact to the v1
recordings). A step that changes an effect on purpose re-records only the
affected presets (GME_REF_ONLY), after that effect is verified, and says so in its commit.
Step D4 (Freeverb) re-recorded reverb_t0..t3, combo_all and combo_change.
Step D5 (dynamics, EQ) added dyn_gate, dyn_comp, eq_3band and combo_d5 at the end of PRESETS and
recorded only them; the 31 earlier presets stayed bit-exact (dynamics and EQ are off in them: zero
latency bypass). A preset key "eq" = (bass, mid, treble) dB writes that EQ set (tools/eq_coefs.py)
through the chain's write port before the run (flat for the other presets).

All presets run in one simulation from power-up, in a fixed order, with
deterministic 24-bit stimuli (the state carried between presets, delay lines and
LFO phases, is therefore the same in both modes). Registers change instantly
(XFADE off); the click-free switching and the smoothing have their own tests.

test_golden24: overdrive and distortion bit-exact to golden.py with full 24-bit
random input.
"""
import math
import os
import random
import sys
from pathlib import Path

import cocotb
import numpy as np

import golden
from fxdriver import CAB, CHORUS, DIST, DYN, ECHO, EQ, OD, REVERB, TREM, FxChain, find_latency

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import eq_coefs as ec                                        # noqa: E402

REF_DIR = Path(__file__).resolve().parent / "ref_v2"
MODE = os.environ.get("GME_REF_MODE", "check")
ONLY = {n for n in os.environ.get("GME_REF_ONLY", "").split(",") if n}
NONE = 1 << 30                    # marker for X/U output samples
IP = Path(__file__).resolve().parents[2] / "fpga" / "ip"


def stimulus(seed):
    """6000 frames of 24-bit audio: noise, a 440 Hz sine, an impulse train."""
    rnd = random.Random(seed)
    x = [rnd.randint(-5_000_000, 5_000_000) for _ in range(1500)]
    x += [round(3_600_000 * math.sin(2 * math.pi * 440 * n / 48000)) + rnd.randint(-128, 127)
          for n in range(3000)]
    x += [4_000_000 if n % 300 == 50 else 0 for n in range(1500)]
    return x


ALL = OD | TREM | ECHO | DIST | CHORUS | REVERB


def q8(db):
    """dB -> Q8 log2 units of the dynamics registers."""
    return round(db * 256 / (20 * math.log10(2)))


CHORUS_REGS = dict(chorus_level=128, chorus_depth=144, chorus_rate=80, mod_base=720)
# name -> (registers, registers changed at frame 3000 or None)
PRESETS = {
    "bypass":        (dict(effects_enable=0), None),
    "overdrive":     (dict(effects_enable=OD, od_drive=3000, od_gain=4), dict(od_drive=9000, od_gain=3)),
    **{"dist_%s_%d" % (n, m): (dict(effects_enable=DIST, dist_type=t, dist_mix=m), None)
       for t, n in enumerate(("soft", "medium", "hard")) for m in (255, 128)},
    **{"trem_w%d" % w: (dict(effects_enable=TREM, trem_wave=w, trem_depth=255), None) for w in range(8)},
    "trem_w2_d128":  (dict(effects_enable=TREM, trem_wave=2, trem_depth=128), dict(trem_wave=4)),
    "trem_free":     (dict(effects_enable=TREM, trem_wave=8 + 3, trem_rate=650, trem_depth=200),
                      dict(trem_wave=8 + 2, trem_rate=300)),
    "chorus":        (dict(effects_enable=CHORUS, **CHORUS_REGS), dict(chorus_depth=40)),
    "flanger":       (dict(effects_enable=CHORUS, chorus_level=128, chorus_depth=90, chorus_rate=30,
                           mod_base=96, mod_fb=26000, mod_shape=1), None),
    "flanger_neg":   (dict(effects_enable=CHORUS, chorus_level=128, chorus_depth=60, chorus_rate=50,
                           mod_base=70, mod_fb=(-30000) & 0xFFFF), None),
    "vibrato":       (dict(effects_enable=CHORUS, chorus_level=255, chorus_depth=100, chorus_rate=600,
                           mod_base=240), None),
    "echo_a":        (dict(effects_enable=ECHO, echo_time=1200, echo_level=32768, echo_repeat=128), None),
    "echo_b":        (dict(effects_enable=ECHO, echo_time=300, echo_level=50000, echo_repeat=220),
                      dict(echo_time=700)),
    "echo_frac":     (dict(effects_enable=ECHO, echo_time=500, echo_frac=77, echo_level=40000,
                           echo_repeat=150), dict(echo_frac=200)),
    **{"reverb_t%d" % t: (dict(effects_enable=REVERB, reverb_type=t, reverb_mix=128), None) for t in range(4)},
    "combo_all":     (dict(effects_enable=ALL, od_drive=6000, od_gain=2, dist_type=1, dist_mix=128,
                           trem_wave=0, trem_depth=150, echo_time=2000, echo_level=20000, echo_repeat=100,
                           reverb_type=1, reverb_mix=80, **CHORUS_REGS), None),
    "combo_change":  (dict(effects_enable=DIST | ECHO | REVERB, dist_type=2, dist_mix=200, echo_time=900,
                           echo_level=25000, echo_repeat=90, reverb_type=0, reverb_mix=100),
                      dict(reverb_type=3, effects_enable=DIST | REVERB)),
    # ---- step D5: recorded with GME_REF_ONLY (the 31 presets above are unchanged) ----
    "dyn_gate":      (dict(effects_enable=DYN, dyn_ctrl=1, gate_thresh=q8(-30)), dict(gate_thresh=q8(-45))),
    "dyn_comp":      (dict(effects_enable=DYN, dyn_ctrl=2, comp_thresh=q8(-20), comp_ratio=2, comp_attack=3,
                           comp_release=8, comp_makeup=q8(3)), dict(comp_ratio=4, comp_thresh=q8(-30))),
    "eq_3band":      (dict(effects_enable=EQ, eq=(6, -4, 9)), dict(eq=(-8, 6, -5))),
    "combo_d5":      (dict(effects_enable=ALL | CAB | DYN | EQ, dyn_ctrl=3, gate_thresh=q8(-40), comp_thresh=q8(-18),
                           comp_ratio=2, comp_attack=3, comp_release=7, comp_makeup=q8(2), eq=(4, -3, 6),
                           cab_ctrl=2 << 1, od_drive=7000, od_gain=2, dist_type=0, dist_mix=100, trem_wave=8 + 1,
                           trem_rate=500, trem_depth=100, echo_time=1500, echo_level=18000, echo_repeat=90,
                           reverb_type=1, reverb_mix=70, **CHORUS_REGS),
                      dict(effects_enable=(ALL | CAB) & ~DIST, eq=(-6, 5, -4), comp_ratio=4)),
}
ZERO = {k: 0 for k in ("effects_enable", "od_drive", "od_gain", "trem_depth", "trem_wave", "trem_rate",
                       "echo_time", "echo_frac", "echo_level", "echo_repeat", "chorus_rate", "chorus_level",
                       "chorus_depth", "mod_base", "mod_fb", "mod_shape", "dist_mix", "dist_type",
                       "reverb_type", "reverb_mix", "dyn_ctrl", "gate_thresh", "comp_thresh", "comp_ratio",
                       "comp_attack", "comp_release", "comp_makeup", "cab_ctrl")}


async def set_regs(fx, regs):
    """Registers, plus the EQ set of the key "eq" (flat when absent) through the write port."""
    regs = dict(regs)
    eq = regs.pop("eq", None)
    fx.set(**regs)
    if eq is not None:
        ints, sh, _ = ec.coefficient_set_full(*eq)
        await fx.eq_write(ints, ec.scale_word(sh))


@cocotb.test()
async def test_presets(dut):
    """All presets bit-exact to the v2 references (or record them)."""
    fx = FxChain(dut)
    assert fx.dw == 24
    await fx.start()
    REF_DIR.mkdir(exist_ok=True)
    unknown = ONLY - set(PRESETS)
    assert not unknown, "GME_REF_ONLY names unknown presets: %s" % sorted(unknown)
    assert MODE == "record" or not ONLY, "GME_REF_ONLY needs GME_REF_MODE=record"
    failures = []
    for i, (name, (regs, change)) in enumerate(PRESETS.items()):
        await set_regs(fx, {"eq": (0, 0, 0), **ZERO, **regs})
        x = stimulus(200 + i)
        if change:                                   # the registers change before frame 3000
            y = await fx.run(x[:3000], raw=True)
            await set_regs(fx, change)
            y += await fx.run(x[3000:], raw=True)
        else:
            y = await fx.run(x, raw=True)
        y = np.array([NONE if v is None else v for v in y], dtype=np.int32)
        path = REF_DIR / (name + ".npy")
        if MODE == "record" and (not ONLY or name in ONLY):
            np.save(path, y)
            dut._log.info("recorded %-14s peak %d", name, int(np.abs(y[y != NONE]).max()))
            continue
        ref = np.load(path)
        bad = np.nonzero(ref != y)[0]
        if len(bad):
            failures.append("%s: %d mismatches, first at frame %d (ref %d, got %d)"
                            % (name, len(bad), bad[0], ref[bad[0]], y[bad[0]]))
            dut._log.error(failures[-1])
        else:
            dut._log.info("%-14s bit-exact (%d frames)", name, len(y))
    assert not failures, "%d presets differ from the v2 reference" % len(failures)
    if ONLY:
        dut._log.info("recorded %d presets, the other %d are bit-exact to the existing references",
                      len(ONLY), len(PRESETS) - len(ONLY))


def rand24(n, seed):
    rnd = random.Random(seed)
    return [rnd.randint(-(1 << 23), (1 << 23) - 1) for _ in range(n)]


def check(name, exp, got, start=32):
    lat = find_latency(exp, got)
    bad = [i for i in range(start, len(exp)) if i + lat < len(got) and got[i + lat] != exp[i]]
    assert not bad, "%s: %d mismatches, first at %d: expected %d got %d" % (
        name, len(bad), bad[0], exp[bad[0]], got[bad[0] + lat])


@cocotb.test()
async def test_golden24(dut):
    """Bypass, overdrive and distortion bit-exact with full 24-bit samples."""
    fx = FxChain(dut)
    await fx.start()                     # (each cocotb test needs its own clock)
    x = rand24(1500, 1)
    y = await fx.run(x, tail=4, raw=True)
    check("bypass", x, y)
    fx.set(**{**ZERO, **dict(effects_enable=OD, od_drive=12345, od_gain=3)})
    y = await fx.run(x, tail=4, raw=True)
    check("overdrive", golden.overdrive(x, 12345, 3, dw=24), y)
    for t, name in enumerate(("soft", "medium", "hard")):
        curve = golden.load_mif(IP / ("distortion_%s.mif" % name))
        for mix in (255, 77):
            fx.set(**{**ZERO, **dict(effects_enable=DIST, dist_type=t, dist_mix=mix)})
            y = await fx.run(x, tail=4, raw=True)
            check("distortion %s/%d" % (name, mix), golden.distortion(x, curve, mix, dw=24), y)
    dut._log.info("24-bit bypass / overdrive / 3 distortion curves x 2 mixes bit-exact")
