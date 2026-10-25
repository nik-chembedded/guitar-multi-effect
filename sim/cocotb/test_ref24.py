"""
test_ref24.py - the 24-bit effect chain (v2 step C, DW = 24).

1. Bit-exact with full 24-bit input against the 24-bit golden models
   (bypass, overdrive, distortion).
2. The 27 v1 reference presets: the 16-bit stimulus (x * 256) through the
   24-bit chain must match the recorded v1 outputs within the 16-bit rounding
   noise that v1 adds and the 24-bit chain does not. Each preset prints its
   max / RMS difference in 16-bit LSB.
Runs with ECHO_AW = 16 (v1 echo line size), XFADE off (instant registers).
The preset test runs first: like the v1 recording it must start from power-up
(LFO phases and delay-line contents carry over between tests).
"""
import math
import random

import cocotb
import numpy as np

import golden
from fxdriver import DIST, OD, FxChain, find_latency
from test_fx_chain import IP
from test_ref import NONE, PRESETS, REF_DIR, ZERO, stimulus

# tolerances in 16-bit LSB (v1 truncates to 16 bits after every multiply;
# feedback effects accumulate that noise)
MAX_ERR = 32
RMS_ERR = 8.0


def rand24(n, seed, scale=1.0):
    rnd = random.Random(seed)
    m = int((1 << 23) * scale)
    return [rnd.randint(-m, m - 1) for _ in range(n)]


def check(name, exp, got, start=32):
    lat = find_latency(exp, got)
    bad = [i for i in range(start, len(exp)) if i + lat < len(got) and got[i + lat] != exp[i]]
    assert not bad, "%s: %d mismatches, first at %d: expected %d got %d" % (
        name, len(bad), bad[0], exp[bad[0]], got[bad[0] + lat])


@cocotb.test()
async def test_presets_vs_v1(dut):
    """27 v1 presets through the 24-bit chain: equal to v1 within its 16-bit rounding."""
    fx = FxChain(dut)
    await fx.start()
    worst = []
    for i, (name, (regs, change)) in enumerate(PRESETS.items()):
        fx.set(**{**ZERO, **regs})

        def on_frame(n, change=change):
            if change and n == 3000:
                fx.set(**change)
        y = await fx.run([v << 8 for v in stimulus(100 + i)], on_frame=on_frame, raw=True)
        ref = np.load(REF_DIR / (name + ".npy"))
        mask = (ref != NONE) & np.array([v is not None for v in y])
        got = np.array([0 if v is None else v for v in y], dtype=np.float64) / 256.0
        err = (got - ref)[mask]
        mx, rms = float(np.abs(err).max()), float(math.sqrt(np.mean(err ** 2)))
        dut._log.info("%-14s max %6.1f LSB  rms %5.2f LSB", name, mx, rms)
        worst.append((name, mx, rms))
    bad = [w for w in worst if w[1] > MAX_ERR or w[2] > RMS_ERR]
    assert not bad, "outside the 16-bit rounding tolerance: %s" % bad
    dut._log.info("27 presets within %d LSB peak / %.0f LSB rms of v1 (worst peak %.1f, worst rms %.2f)",
                  MAX_ERR, RMS_ERR, max(w[1] for w in worst), max(w[2] for w in worst))


@cocotb.test()
async def test_golden24(dut):
    """Bypass, overdrive and distortion bit-exact with full 24-bit samples."""
    fx = FxChain(dut)
    assert fx.dw == 24
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
