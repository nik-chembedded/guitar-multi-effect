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
from reverbfv_model import ReverbFV
from fxdriver import CAB, CHORUS, DIST, ECHO, OD, REVERB, TREM, FxChain, find_latency

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
    """Modulated delay (step D2): the delay sweeps base +- depth with the LFO and
    follows a depth change; impulses read with a fractional delay."""
    fx = FxChain(dut)
    # triangle LFO 10 Hz (4800 frames), delay 100 +- 60 samples, 50 % wet
    await fx.start(effects_enable=CHORUS, chorus_level=128, chorus_depth=60, chorus_rate=1000,
                   mod_base=100, mod_shape=1)
    x = [16000 if n % 250 == 30 else 0 for n in range(9600)]
    delays = []

    def on_frame(n):
        if n == 5000:
            fx.set(chorus_depth=10)                  # sweep 90 .. 110 from here
    y = [s or 0 for s in await fx.run(x, on_frame=on_frame)]
    for k in range(len(x) // 250):
        p0 = next((n for n in range(k * 250 + 30, k * 250 + 40) if y[n] > 6000), None)
        if p0 is None or p0 + 240 >= len(y):
            continue
        seg = [abs(v) for v in y[p0 + 20:p0 + 200]]
        pk = max(range(len(seg)), key=seg.__getitem__)
        assert seg[pk] > 1500, "wet copy of impulse %d not found" % k
        delays.append((k * 250 + 30, pk + 20))
    before = [d for f, d in delays if f < 5000]
    after = [d for f, d in delays if f >= 5600]
    dut._log.info("mod delay %d..%d (expected 40..160), after depth 10: %d..%d (90..110)",
                  min(before), max(before), min(after), max(after))
    assert min(before) <= 50 and max(before) >= 150, "delay does not sweep base +- depth"
    assert 38 <= min(before) and max(before) <= 162, "delay outside base +- depth"
    assert 88 <= min(after) and max(after) <= 112, "depth change not followed"
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
async def test_echo_frac(dut):
    """Fractional echo time (step D2): with echo_frac = 0 the echo is the input T
    samples back; with echo_frac = f it is exactly the linear interpolation
    between the samples T and T + 1 back."""
    fx = FxChain(dut)
    await fx.start(effects_enable=ECHO, echo_time=300, echo_level=40000, echo_repeat=0, echo_frac=0)
    rnd = random.Random(9)
    m = 12000 << fx.shift                              # full-width samples (16 or 24 bit)
    x = [rnd.randint(-m, m) for _ in range(1500)]
    y = [s or 0 for s in await fx.run(x, raw=True)]
    # output = dry (chain latency d) + level * echo (d + l): find both
    d, lat = next((d, l) for d in range(0, 8) for l in range(290, 320)
                  if all(y[n] == x[n - d] + ((40000 * x[n - d - l]) >> 16) for n in range(700, 1500)))
    fx.set(echo_frac=128)
    x2 = [rnd.randint(-m, m) for _ in range(1500)]
    y2 = [s or 0 for s in await fx.run(x2, raw=True)]
    for n in range(700, 1500):
        a, b = x2[n - d - lat], x2[n - d - lat - 1]
        assert y2[n] == x2[n - d] + ((40000 * (a + (((b - a) * 128) >> 8))) >> 16), "echo_frac frame %d" % n
    dut._log.info("echo: delay %d frames for echo_time 300 (chain latency %d), half-sample interpolation exact",
                  lat, d)


@cocotb.test()
async def test_reverb_chain_model(dut):
    """(Runs before test_reverb: the model starts with empty lines, so does the chain.)
    FX_chain reverb output equals the block's Python model (reverbfv_model) fed with the reverb
    input of the chain (echo_out) - bit-exact, with room presets and size / damp / mix changes."""
    fx = FxChain(dut)
    await fx.start(effects_enable=REVERB, reverb_mix=200)
    model = ReverbFV(dw=fx.dw)
    fx.probe = []
    rnd = random.Random(5)
    m = 12000 << fx.shift
    n_total = 0
    for size, damp, mix, enable in ((45875, 100, 200, 1), (61604, 40, 128, 1), (50000, 255, 255, 1),
                                    (65535, 0, 90, 1), (52429, 80, 0, 1), (57672, 60, 160, 0),
                                    (57672, 60, 160, 1)):
        fx.set(reverb_size=size, reverb_damp=damp, reverb_mix=mix,
               effects_enable=REVERB if enable else 0)
        x = [rnd.randint(-m, m) if n < 600 else (m if n % 200 == 0 else 0) for n in range(1500)]
        fx.probe.clear()
        y = await fx.run(x, raw=True)
        for n, (xin, out) in enumerate(zip(fx.probe, y)):
            exp = model.step(xin, enable, size, damp, mix)
            assert out == exp, "size %d damp %d mix %d en %d frame %d: chain %s, model %d" % (
                size, damp, mix, enable, n, out, exp)
        n_total += len(y)
    dut._log.info("FX_chain reverb == reverbfv_model for %d frames (7 settings, incl. clamp and bypass)", n_total)


def tone_burst_response(y, burst):
    """Energy (sum |y|) of the reverb tail in three windows after the burst."""
    e = lambda a, b: sum(abs(v) for v in y[burst + a:burst + b])
    return e(100, 700), e(2500, 3500), e(5000, 6000)


@cocotb.test()
async def test_reverb(dut):
    """Freeverb: no wrap-around, a tail that decays after a noise burst, and the room presets
    0 (very light) .. 3 (heavy) ordered by decay length (rate of tail decay, slower = longer)."""
    fx = FxChain(dut)
    await fx.start(effects_enable=REVERB, reverb_mix=128)
    burst = 1000
    x = prbs(burst, seed=3, amp=12000) + [0] * 6000                 # noise burst: no coherent tone interference
    ratios = []
    for t in range(4):
        fx.set(reverb_size=0, reverb_damp=0)                    # flush the lines (no feedback)
        await fx.run([0] * 2400)
        fx.set(reverb_type=t)
        y = [s or 0 for s in await fx.run(x)]
        early, mid, late = tone_burst_response(y, burst)
        dut._log.info("reverb room %d: tail energy early %d, mid %d, late %d (late/mid %.3f)",
                      t, early, mid, late, late / mid)
        assert early > 0, "room %d: no reverb tail" % t
        assert late < mid, "room %d: tail does not decay" % t
        assert_no_wrap("reverb room %d" % t, y)
        ratios.append(late / mid)
    assert ratios == sorted(ratios) and len(set(ratios)) == 4,         "rooms not ordered by decay length: late/mid energy %s" % ratios


# ---------------------------------------------------------------------------
# Cabinet (step D3): CAB_TAPS = 16 here (sim/models/cab_test16.mif, shift 2); the full
# 2048-tap cabinet is tested in test_cabfir and through gme_core in test_system.
def cab_conv(x, h, shift, dw):
    """Independent reference: y[n] = sat(floor(sum_k h[k] x[n-k] / 2^(17+shift)))."""
    lo, hi = -(1 << (dw - 1)), (1 << (dw - 1)) - 1
    return [max(lo, min(hi, sum(h[k] * x[n - k] for k in range(len(h)) if n >= k) >> (17 + shift)))
            for n in range(len(x))]


def max_step(v):
    return max(abs(v[i] - v[i - 1]) for i in range(1, len(v)))


@cocotb.test()
async def test_cab(dut):
    """Cabinet stage: impulse response = coefficients >> (17+shift) one sample after the bypass
    latency; cab off = bit-exact bypass with the same latency; bank switch mid-stream
    (bank 1 loaded through the write port) smooth when the chain fades (XFADE), writes to the
    active bank ignored, writes to the inactive bank take effect."""
    import os
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
    import cab_coefs
    from cocotb.triggers import ClockCycles

    fx = FxChain(dut)
    dw = fx.dw
    xfade = os.environ.get("GME_XFADE", "0") == "1"
    lo, hi = -(1 << (dw - 1)), (1 << (dw - 1)) - 1
    sh0, sh1 = 2, 3
    h0 = cab_coefs.read_mif(str(Path(__file__).resolve().parents[2] / "sim" / "models" / "cab_test16.mif"))[:16]
    rnd = random.Random(31)
    h1 = [rnd.randint(-(1 << 16), (1 << 16) - 1) >> (k // 3) for k in range(16)]
    h2 = [rnd.randint(-(1 << 17), (1 << 17) - 1) >> (k // 2) for k in range(16)]
    ctrl = lambda bank, s0=sh0, s1=sh1: (s1 << 4) | (s0 << 1) | bank           # noqa: E731
    junk = [rnd.randint(-(1 << 17), (1 << 17) - 1) for _ in range(16)]

    # 1. cab off: bypass, and its latency
    await fx.start(effects_enable=0, cab_ctrl=ctrl(0))
    await fx.cab_write(1, h1)                          # bank 1 is free: loaded while the chain runs
    x = [rnd.randint(lo, hi) for _ in range(600)]
    y = await fx.run(x, tail=16, raw=True)
    lat = find_latency(x, y)
    assert_bit_exact("cab off", x, y, lat)
    dut._log.info("cab off: bit-exact bypass, latency %d frames", lat)

    # 2. cab on, impulse
    fx.set(effects_enable=CAB)
    amp = 1 << (dw - 3)
    n0 = 300
    y = await fx.run([0] * n0 + [amp] + [0] * 40, raw=True)
    want = [max(lo, min(hi, (amp * c) >> (17 + sh0))) for c in h0]
    got = y[n0 + lat + 1: n0 + lat + 1 + 16]
    assert got == want, "impulse response %s, expected %s" % (got, want)
    assert all(v == 0 for v in y[lat + 2:n0 + lat + 1]) and all(v == 0 for v in y[n0 + lat + 17:]), \
        "output outside the impulse response must be 0"
    dut._log.info("cab impulse: %d taps equal the coefficients >> %d at latency %d + 1 frames", 16, 17 + sh0, lat)

    # 3. cab off again: identical to the bypass, same latency
    fx.set(effects_enable=0)
    await fx.run([rnd.randint(lo, hi) for _ in range(300)], raw=True)       # fade-out
    x = [rnd.randint(lo, hi) for _ in range(600)]
    y = await fx.run(x, tail=16, raw=True)
    lat2 = find_latency(x, y)
    assert lat2 == lat, "cab off added latency: %d -> %d frames" % (lat, lat2)
    assert_bit_exact("cab off after use", x, y, lat)

    # 4. bank switch 0 -> 1 mid-stream
    fx.set(effects_enable=CAB, cab_ctrl=ctrl(0))
    sig = [round(0.5 * hi * math.sin(2 * math.pi * 1000 * i / 48000)) for i in range(1200)]
    y = await fx.run(sig[:400], raw=True)              # fade-in, cabinet 0 steady
    fx.set(cab_ctrl=ctrl(1))
    y += await fx.run(sig[400:900], raw=True)
    i1 = 900                                           # bank 1 steady from here
    for i in range(0, 16, 4):                          # writes into the active bank 1: ignored
        await fx.cab_write(1, junk[i:i + 4], first=i)
    y += await fx.run(sig[900:1200], raw=True)
    w0, w1 = cab_conv(sig, h0, sh0, dw), cab_conv(sig, h1, sh1, dw)
    for lo_i, hi_i, w, name in ((300, 400 - lat - 2, w0, "bank 0"), (i1, 1200 - lat - 1, w1, "bank 1 (junk writes ignored)")):
        bad = [i for i in range(lo_i, hi_i) if y[i + lat + 1] != w[i]]
        assert not bad, "%s steady state: %d mismatches, first at %d: got %d expected %d" % (
            name, len(bad), bad[0], y[bad[0] + lat + 1], w[bad[0]])
    ms = max_step(y[lat + 1 + 100: lat + 1 + 1200])
    ref = max(max_step(sig), max_step(w0[100:]), max_step(w1[100:]))
    dut._log.info("bank switch: max step %d, signal / steady-state max step %d (ratio %.2f)%s",
                  ms, ref, ms / ref, "" if xfade else " [no fade: XFADE = false]")
    if xfade:
        assert ms <= 1.25 * ref, "step %d at the bank switch exceeds the signal's own (%d)" % (ms, ref)

    # 5. bank 0 is now idle: rewrite it, switch back, the new content plays
    await fx.cab_write(0, h2)
    fx.set(cab_ctrl=ctrl(0, sh0, sh1))
    y = await fx.run(sig[:700], raw=True)
    w2 = cab_conv(sig, h2, sh0, dw)
    bad = [i for i in range(500, 700 - lat - 1) if y[i + lat + 1] != w2[i]]
    assert not bad, "bank 0 rewritten: %d mismatches, first at %d" % (len(bad), bad[0])
    dut._log.info("cab: write to the idle bank + switch back OK")
