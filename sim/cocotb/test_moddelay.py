"""
test_moddelay.py - mod_delay (v2 step D2) bit-exact to moddelay_model.py, at
GME_DW = 16 or 24: static fractional delays, chorus / flanger / vibrato
settings with the LFO, feedback up to +-0.99 (saturation), setting changes
mid-stream, enable off/on.
"""
import os
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge

from moddelay_model import ModDelay

DW = int(os.environ.get("GME_DW", "16"))
CLK_PER_SAMPLE = 16


def s(v):
    return v - (1 << DW) if v >= 1 << (DW - 1) else v


@cocotb.test()
async def test_moddelay(dut):
    Clock(dut.clk, 10, unit="ns").start()
    dut.en_rise.value = 0
    rnd = random.Random(4)
    full = (1 << (DW - 1)) - 1
    # (frames, enable, mix, depth, rate, base, fb, shape)
    segments = [
        (600, 1, 255, 0, 0, 1, 0, 0),           # 1-sample delay, 100 % wet
        (600, 1, 255, 0, 0, 37, 0, 0),          # static integer delay
        (900, 1, 128, 300, 80, 720, 0, 0),      # chorus: 15 ms +- 6 ms, 0.8 Hz sine
        (900, 1, 128, 90, 30, 96, 26000, 1),    # flanger: 2 ms, triangle, feedback +0.8
        (900, 1, 128, 90, 30, 96, -32440, 0),   # flanger, feedback -0.99
        (900, 1, 255, 100, 600, 240, 0, 0),     # vibrato: 5 ms +- 2 ms, 6 Hz, wet only
        (300, 0, 128, 90, 30, 96, 0, 0),        # bypassed
        (900, 1, 200, 2046, 1500, 2046, 32767, 0),  # extremes: full depth, fb +1, clamp
    ]
    model = ModDelay(DW)
    exp, got, xs = [], [], []
    for frames, en, mix, depth, rate, base, fb, shape in segments:
        await RisingEdge(dut.clk)
        for name, v in (("enable", en), ("mix", mix), ("depth", depth), ("rate", rate),
                        ("base", base), ("fb", fb & 0xFFFF), ("shape", shape)):
            getattr(dut, name).value = v
        for _ in range(frames):
            x = rnd.randint(-full - 1, full) // (4 if fb else 1)
            dut.data_in.value = x & ((1 << DW) - 1)
            await ClockCycles(dut.clk, CLK_PER_SAMPLE - 1)
            dut.en_rise.value = 1
            await RisingEdge(dut.clk)
            dut.en_rise.value = 0
            await RisingEdge(dut.clk)
            got.append(s(int(dut.data_out.value)))
            xs.append(x)
            exp.append(model.step(x, en, mix, depth, rate, base, fb & 0xFFFF, shape))
    # independent of the model: the static 37-sample delay at mix 255 (255/256 wet,
    # as mix8 everywhere) is exactly the input 37 samples earlier (segment 2)
    for n in range(600 + 64, 1200):
        assert got[n] == (255 * xs[n - 37]) >> 8, "static delay 37: sample %d" % n
    bad = [i for i in range(len(exp)) if got[i] != exp[i]]
    assert not bad, "%d mismatches, first at sample %d: rtl %d model %d" % (len(bad), bad[0], got[bad[0]], exp[bad[0]])
    dut._log.info("mod_delay (%d-bit): %d samples bit-exact to the model over %d settings "
                  "(fractional delay, chorus/flanger/vibrato, feedback +-0.99, bypass, clamping)",
                  DW, len(exp), len(segments))
