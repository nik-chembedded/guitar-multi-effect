"""
test_fx_chain.py - cocotb tests for the FX_chain entity (frame level).

Bit-exact against golden.py where the effect has no free-running LFO
(bypass, overdrive, distortion); behavioural checks for the time-varying
effects (tremolo, chorus, echo, reverb). Every test also fails on
wrap-around (full-scale jumps between samples).

Run:  cd sim/cocotb && pytest -v            (see test_runner.py)
"""
import math
import random
from pathlib import Path

import cocotb

import golden
from fxdriver import CHORUS, DIST, ECHO, OD, REVERB, TREM, FxChain, find_latency

N = 2000
IP = Path(__file__).resolve().parents[2] / "fpga" / "ip"


def prbs(n, seed=1, amp=32767):
    rnd = random.Random(seed)
    return [rnd.randint(-amp - 1, amp) for _ in range(n)]


def sine(n, f=440.0, amp=12000.0):
    return [round(amp * math.sin(2 * math.pi * f * i / 48000)) for i in range(n)]


def assert_bit_exact(name, expected, got, lat, start=32):
    bad = [(i, expected[i], got[i + lat]) for i in range(start, len(expected) - lat)
           if got[i + lat] != expected[i]]
    assert not bad, "%s: %d mismatches, first: n=%d expected %d got %s" % (
        name, len(bad), *bad[0])


def assert_no_wrap(name, y, start=32, limit=30000):
    v = [s or 0 for s in y]
    jumps = [i for i in range(start + 1, len(v)) if abs(v[i] - v[i - 1]) > limit]
    assert not jumps, "%s: %d wrap-around glitches, first at frame %d" % (name, len(jumps), jumps[0])


# ---------------------------------------------------------------------------
@cocotb.test()
async def test_bypass(dut):
    """All effects off: output bit-exact to the input (full-scale random)."""
    fx = FxChain(dut)
    await fx.start(effects_enable=0)
    x = prbs(N)
    y = await fx.run(x, tail=16)
    lat = find_latency(x, y)
    dut._log.info("bypass latency %d frames", lat)
    assert_bit_exact("bypass", golden.bypass(x), y, lat)


@cocotb.test()
async def test_overdrive(dut):
    """Overdrive bit-exact against the reference model, incl. saturation."""
    fx = FxChain(dut)
    drive, gain = 3000, 4
    await fx.start(effects_enable=OD, od_drive=drive, od_gain=gain)
    x = prbs(N, seed=2)
    y = await fx.run(x, tail=16)
    exp = golden.overdrive(x, drive, gain)
    lat = find_latency(exp, y)
    dut._log.info("overdrive latency %d frames", lat)
    assert_bit_exact("overdrive", exp, y, lat)
    fx.set(od_drive=20000, od_gain=5)            # must saturate, not wrap
    y2 = await fx.run(x[:500], tail=16)
    assert_bit_exact("overdrive saturation", golden.overdrive(x[:500], 20000, 5), y2, lat)


@cocotb.test()
async def test_distortion(dut):
    """All three curves bit-exact (full-scale input, half and full wet mix)."""
    fx = FxChain(dut)
    await fx.start()
    x = prbs(N, seed=3)
    for dtype, name in ((0, "soft"), (1, "medium"), (2, "hard")):
        curve = golden.load_mif(IP / ("distortion_%s.mif" % name))
        for mix in (255, 128):
            fx.set(effects_enable=DIST, dist_type=dtype, dist_mix=mix)
            y = await fx.run(x, tail=16)
            exp = golden.distortion(x, curve, mix)
            lat = find_latency(exp, y)
            # (bit-exact to a saturating model also rules out wrap-around)
            assert_bit_exact("distortion %s mix %d" % (name, mix), exp, y, lat, start=64)
    dut._log.info("distortion: 3 curves x 2 mixes bit-exact")


@cocotb.test()
async def test_tremolo(dut):
    """5 Hz sine LFO at full depth: envelope modulated, no clicks (saw too)."""
    fx = FxChain(dut)
    await fx.start(effects_enable=TREM, trem_wave=0, trem_depth=255)
    x = sine(12000, amp=16000)                   # one 5 Hz period = 9600 frames
    y = [s or 0 for s in await fx.run(x)]
    env = [max(abs(v) for v in y[b:b + 240]) for b in range(480, len(y) - 240, 240)]
    dut._log.info("tremolo envelope %d .. %d", min(env), max(env))
    assert max(env) > 2 * min(env) + 1, "no amplitude modulation"
    assert_no_wrap("tremolo", y)
    # sawtooth: the gain must not jump (the v1 click), checked on a constant input
    fx.set(trem_wave=7, trem_depth=200)
    dc = [16000] * 6000
    y = [s or 0 for s in await fx.run(dc)]
    steps = max(abs(y[i] - y[i - 1]) for i in range(200, len(y)))
    dut._log.info("tremolo saw: largest 1-sample step %d (of 16000)", steps)
    assert steps < 0.05 * 16000, "sawtooth tremolo click: step %d" % steps


@cocotb.test()
async def test_chorus(dut):
    """Delay sweeps 2..depth+2; lowering the depth mid-sweep is safe."""
    fx = FxChain(dut)
    await fx.start(effects_enable=CHORUS, chorus_level=32768, chorus_depth=200, chorus_rate=0)
    x = [16000 if n % 250 == 100 else 0 for n in range(4800)]
    delays = []

    def on_frame(n):
        if n == 2000:
            fx.set(chorus_depth=50)
    y = [s or 0 for s in await fx.run(x, on_frame=on_frame)]
    for k in range(len(x) // 250):
        p0 = next((n for n in range(k * 250 + 100, k * 250 + 140) if y[n] > 8000), None)
        if p0 is None or p0 + 240 >= len(y):
            continue
        pk = next((n for n in range(p0 + 1, p0 + 240) if abs(y[n]) > 3000), None)
        assert pk is not None, "wet copy of impulse %d not found" % k
        delays.append((k * 250 + 100, pk - p0))
    before = [d for f, d in delays if f < 2000]
    after = [d for f, d in delays if f >= 2800]
    dut._log.info("chorus delay %d..%d, after depth change max %d", min(before), max(before), max(after))
    assert max(before) - min(before) > 100, "delay does not sweep"
    assert max(after) <= 52 + 6, "delay not limited after lowering the depth"
    assert_no_wrap("chorus", y)


@cocotb.test()
async def test_echo(dut):
    """Impulse: echo 1 = level*x, echo 2 = level*repeat*x at the measured delay."""
    fx = FxChain(dut)
    # The tests share one simulation and the echo RAM is written even while the
    # echo is off: flush the part of the delay line in use (no feedback) first.
    await fx.start(effects_enable=ECHO, echo_time=1200, echo_level=32768, echo_repeat=0)
    await fx.run([0] * 1500)
    fx.set(echo_repeat=128)
    x = [16000 if n == 100 else 0 for n in range(4000)]
    y = [s or 0 for s in await fx.run(x)]
    p0 = next(n for n in range(len(y)) if y[n] > 8000)
    p1 = next(n for n in range(p0 + 1100, len(y)) if abs(y[n]) > 2000)
    delay = p1 - p0
    dut._log.info("echo: delay %d frames, echoes %d, %d", delay, y[p1], y[p0 + 2 * delay])
    assert 1200 <= delay <= 1208, "echo delay %d" % delay
    assert abs(y[p1] - 8000) <= 400, "echo 1 = %d" % y[p1]
    assert abs(y[p0 + 2 * delay] - 4000) <= 400, "echo 2 = %d" % y[p0 + 2 * delay]


@cocotb.test()
async def test_reverb(dut):
    """Heavy reverb: no wrap-around, tail after a tone burst that decays."""
    fx = FxChain(dut)
    await fx.start(effects_enable=REVERB, reverb_type=3, reverb_mix=128)
    x = sine(2400, amp=12000) + [0] * 2400
    y = [s or 0 for s in await fx.run(x)]
    early = sum(abs(v) for v in y[2600:3300])
    late = sum(abs(v) for v in y[4000:4700])
    dut._log.info("reverb tail energy early %d, late %d", early, late)
    assert early > 0, "no reverb tail"
    assert late < early, "tail does not decay"
    assert_no_wrap("reverb", y)
