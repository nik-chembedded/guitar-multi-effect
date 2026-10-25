"""
test_trem.py - the tremolo on the generated LFO (v2 step D1), bit-exact to a
frame-level Python model, on the 16-bit and the 24-bit chain (GME_DW).

Runs in a fresh simulation: the LFO phase starts at 0, and the model follows it
through every setting change (legacy presets and free mode, rate / shape changes
mid-stream), so it also checks that the phase never jumps.

Model (tremolo_v2.vhd, one tick per frame = half_tick):
  phase_n = phase_(n-1) + inc(rate_n)
  w_n     = wave(phase_(n-1), shape_n)               (LFO register before the tick)
  s_n     = s_(n-1) + trunc((w_n - s_(n-1)) / 32)    (one-pole smoothing)
  y_n     = mix8(x_n, floor(x_n * s_(n-1) / 65536), depth)
"""
import random

import cocotb

import lfo_model as m
from fxdriver import TREM, FxChain


def trunc_div(a, b):
    return -((-a) // b) if a < 0 else a // b


def model(xs, settings):
    """xs: tremolo input per frame; settings: per frame (trem_wave, trem_rate, depth)."""
    phase, s, out = 0, 0, []
    for x, (wave, rate, depth) in zip(xs, settings):
        shape, r = m.decode(wave, rate)
        w = m.wave(phase, shape)
        phase = (phase + m.inc(r)) & 0xFFFFFFFF
        modulated = (x * s) >> 16
        out.append((depth * modulated + (255 - depth) * x) >> 8)
        s = s + trunc_div(w - s, 32)
    return out


@cocotb.test()
async def test_trem(dut):
    fx = FxChain(dut)
    await fx.start()
    full = (1 << (fx.dw - 1)) - 1
    rnd = random.Random(11)
    # segments: (frames, trem_wave, trem_rate, depth)
    segments = [(3000, 0, 0, 255), (1500, 2, 0, 200), (1500, 7, 0, 255), (1500, 5, 0, 128),
                (1500, 8 + 0, 450, 255), (1500, 8 + 1, 1234, 255), (1500, 8 + 2, 333, 180),
                (2000, 8 + 3, 700, 255), (1000, 8 + 3, 2000, 90)]
    xs, settings = [], []
    for frames, wave, rate, depth in segments:
        for _ in range(frames):
            xs.append(rnd.randint(-full - 1, full))
            settings.append((wave, rate, depth))
    ys = []
    for n, (x, (wave, rate, depth)) in enumerate(zip(xs, settings)):
        if n == 0 or settings[n - 1] != settings[n]:
            fx.set(effects_enable=TREM, trem_wave=wave, trem_rate=rate, trem_depth=depth)
        ys.append(await fx.frame(x, raw=True))

    # the input reaches the tremolo after the bypassed stages (latency L), and the
    # model's tick index may be offset by a frame: search both
    best = None
    for lat in range(0, 6):
        for off in range(-2, 3):
            xin = [0] * max(0, off) + xs[:len(xs) - max(0, off)] if off >= 0 else xs[-off:] + [0] * (-off)
            exp = model(xin, settings)
            bad = sum(1 for n in range(100, len(xs) - lat) if ys[n + lat] != exp[n])
            if best is None or bad < best[0]:
                best = (bad, lat, off, exp)
    bad, lat, off, exp = best
    first = next((n for n in range(100, len(xs) - lat) if ys[n + lat] != exp[n]), None)
    assert bad == 0, "%d mismatches (latency %d, offset %d), first at frame %s: rtl %s model %s" % (
        bad, lat, off, first, ys[first + lat] if first is not None else "", exp[first] if first is not None else "")
    dut._log.info("tremolo (%d-bit): %d frames bit-exact to the model over %d settings "
                  "(legacy + free mode, rate/shape changes), latency %d", fx.dw, len(xs) - 100,
                  len(segments), lat)
