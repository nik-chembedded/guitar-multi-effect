"""
test_xfade.py - click-free effect on/off (fx_xfade in FX_chain, v2 step C),
24-bit chain with XFADE on. Overdrive with a strong setting on a sine:
switching on and off must glide over 256 samples instead of jumping, and the
steady states must be exact (dry when off, golden overdrive when on).
"""
import math

import cocotb

import golden
from fxdriver import OD, FxChain, find_latency

FADE = 256


def sine24(n, amp=0.45, f=40.0):
    return [round(amp * (1 << 23) * math.sin(2 * math.pi * f * i / 48000)) for i in range(n)]


def max_step(y, a, b):
    return max(abs(y[i] - y[i - 1]) for i in range(a + 1, b))


@cocotb.test()
async def test_xfade(dut):
    fx = FxChain(dut)
    await fx.start(od_drive=1500, od_gain=4)
    x = sine24(1600)
    off1 = await fx.run(x[:400], raw=True)                     # effect off
    fx.set(od_drive=1500, od_gain=4, effects_enable=OD)
    on = await fx.run(x[400:1000], raw=True)                    # switched on at frame 400
    fx.set(od_drive=1500, od_gain=4, effects_enable=0)
    off2 = await fx.run(x[1000:], raw=True)                     # switched off at frame 1000
    y = [v or 0 for v in off1 + on + off2]

    lat_dry = find_latency(x, y, start=50, length=300)
    wet = golden.overdrive(x, 1500, 4, dw=24)
    # steady states: dry before the switch, golden overdrive after the fade-in,
    # dry again after the fade-out
    for n in range(50, 400 - lat_dry):
        assert y[n + lat_dry] == x[n], "dry (before) frame %d" % n
    lat_wet = next(l for l in range(1, 8) if all(y[n + l] == wet[n] for n in range(700, 900)))
    for n in range(400 + FADE + 8, 1000 - lat_wet):
        assert y[n + lat_wet] == wet[n], "wet (on) frame %d" % n
    for n in range(1000 + FADE + 8, 1600 - lat_dry):
        assert y[n + lat_dry] == x[n], "dry (after) frame %d" % n

    # transitions: no step larger than what the steady signals have, plus the
    # fade slope; a hard switch would jump by up to max|wet - dry|
    jump = max(abs(wet[n] - x[n]) for n in range(1600))
    steady = max(max_step(x, 0, 1600), max_step(wet, 0, 1600))     # steepest dry / wet step
    t_on = max_step(y, 395, 400 + FADE + 10)
    t_off = max_step(y, 995, 1000 + FADE + 10)
    limit = steady + jump // FADE + 2
    assert t_on <= limit and t_off <= limit, "fade steps %d / %d > %d" % (t_on, t_off, limit)
    assert jump > 20 * limit, "test signal too weak to show a click"
    dut._log.info("fade on/off: largest step %d / %d (steady signal %d, limit %d); hard switch would "
                  "jump %d. Steady states exact (dry latency %d, wet latency %d)",
                  t_on, t_off, steady, limit, jump, lat_dry, lat_wet)
