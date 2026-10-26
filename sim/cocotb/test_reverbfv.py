"""
test_reverbfv.py - reverb_fv (v2 step D4, Freeverb) at GME_DW = 16 or 24.

Every test needs a fresh block (there is no reset), so run each cocotb test in its
own simulation (test_runner.run(..., testcase=<name>)):

  test_bitexact      bit-exact to reverbfv_model.py: random + square-wave input, size / damp /
                     mix changes mid-stream, size clamp, bypass, mix 0     (8/8-clock strobes)
  test_decay / test_size / test_damp
                     model-independent checks on the RTL output: impulse response energy
                     decays; larger size -> longer decay (RT60 estimate); larger damp -> less
                     high-frequency energy in the tail
  test_overload      full-scale noise / square wave at maximum size -> saturates, no wrap-around
  test_level         wet-only RMS within -6..0 dB of the input RMS (pink noise)
  test_mix0_and_bypass
  test_hw_timing     the same stimulus with 512/512-clock strobes (hardware: 1024 clocks per
                     sample) gives identical outputs to the 8/8 timing (a flush in between
                     returns the block to its all-zero state)

Strobes are driven like the chain: en_fall, <half> clocks, en_rise, <half> clocks, ...
"""
import os
import random

import cocotb
import numpy as np
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge

from reverbfv_model import ReverbFV

DW = int(os.environ.get("GME_DW", "16"))
MASK = (1 << DW) - 1
FULL = (1 << (DW - 1)) - 1
HALF = 8
WIN = 4800                       # 100 ms


def s(v):
    return v - (1 << DW) if v >= 1 << (DW - 1) else v


async def init(dut):
    Clock(dut.clk, 10, unit="ns").start()
    dut.en_rise.value = 0
    dut.en_fall.value = 0
    dut.enable.value = 1
    dut.size.value = 0
    dut.damp.value = 0
    dut.mix.value = 255
    dut.data_in.value = 0
    await ClockCycles(dut.clk, 4)


def setp(dut, enable, size, damp, mix):
    dut.enable.value = enable
    dut.size.value = size
    dut.damp.value = damp
    dut.mix.value = mix


async def frame(dut, x, half=HALF):
    """One sample: en_fall, `half` clocks, en_rise, `half` clocks. Returns data_out."""
    dut.data_in.value = x & MASK
    dut.en_fall.value = 1
    await RisingEdge(dut.clk)
    dut.en_fall.value = 0
    await ClockCycles(dut.clk, half - 1)
    dut.en_rise.value = 1
    await RisingEdge(dut.clk)
    dut.en_rise.value = 0
    await ClockCycles(dut.clk, half - 1)
    return s(int(dut.data_out.value))


async def run_impulse(dut, n, size, damp, mix=255, amp=None):
    setp(dut, 1, size, damp, mix)
    amp = amp if amp is not None else FULL            # full-scale impulse (input gain 1/128)
    out = []
    for i in range(n):
        out.append(await frame(dut, amp if i == 0 else 0))
    return np.array(out, dtype=np.float64)


def stimulus(rnd, count, kind, amp):
    if kind == "noise":
        return [rnd.randint(-amp - 1, amp) for _ in range(count)]
    if kind == "square":
        return [amp if (i // 37) % 2 == 0 else -amp - 1 for i in range(count)]
    if kind == "silence":
        return [0] * count
    raise ValueError(kind)


# (frames, enable, size, damp, mix, kind, amplitude)
SEGMENTS = [
    (1500, 1, 40000, 40, 128, "noise", FULL),
    (1500, 1, 60000, 128, 200, "noise", FULL // 2),
    (1000, 1, 65535, 0, 255, "noise", FULL),             # size above the clamp
    (1200, 1, 65535, 20, 255, "square", FULL),           # saturating the combs
    (500, 0, 50000, 50, 128, "noise", FULL),             # bypass
    (1200, 1, 52000, 255, 100, "noise", FULL // 8),      # maximum damping
    (600, 1, 10000, 200, 0, "noise", FULL),              # mix 0
    (1500, 1, 52000, 90, 77, "silence", 0),              # tail only
]


async def run_segments(dut, model, segs, rnd, half, collect=None):
    mism = []
    n = 0
    for frames, en, size, damp, mix, kind, amp in segs:
        await RisingEdge(dut.clk)
        setp(dut, en, size, damp, mix)
        for x in stimulus(rnd, frames, kind, amp):
            got = await frame(dut, x, half)
            exp = model.step(x, en, size, damp, mix)
            if collect is not None:
                collect.append(got)
            if got != exp:
                mism.append((n, got, exp))
            n += 1
    return n, mism


@cocotb.test()
async def test_bitexact(dut):
    await init(dut)
    model = ReverbFV(DW)
    rnd = random.Random(11)
    n, mism = await run_segments(dut, model, SEGMENTS, rnd, HALF)
    assert not mism, "%d mismatches of %d, first at sample %d: rtl %d model %d" % (
        len(mism), n, mism[0][0], mism[0][1], mism[0][2])
    dut._log.info("reverb_fv (%d-bit): %d samples bit-exact to the model (%d segments, 8/8 strobes)",
                  DW, n, len(SEGMENTS))


@cocotb.test()
async def test_mix0_and_bypass(dut):
    await init(dut)
    rnd = random.Random(5)
    xs = stimulus(rnd, 700, "noise", FULL)
    setp(dut, 1, 50000, 50, 0)                           # mix 0: exact dry
    for x in xs:
        assert await frame(dut, x) == x
    setp(dut, 0, 50000, 50, 255)                         # enable 0: exact dry
    for x in xs:
        assert await frame(dut, x) == x
    setp(dut, 1, 50000, 50, 1)                           # mix 1: not dry any more
    diff = 0
    for x in xs:
        if await frame(dut, x) != x:
            diff += 1
    assert diff > 600
    dut._log.info("mix 0 and enable 0: output == input exactly; mix 1 differs on %d of 700 samples", diff)


@cocotb.test()
async def test_decay(dut):
    """Impulse response energy in successive 100 ms windows decreases (after the first 100 ms)."""
    await init(dut)
    y = await run_impulse(dut, WIN * 9, int(0.85 * 65536), 40)
    en = [float(np.sum(y[k * WIN:(k + 1) * WIN] ** 2)) for k in range(9)]
    dut._log.info("window energies (k=0..8, 100 ms each): " + " ".join("%.3g" % e for e in en))
    assert en[0] > 0
    live = 0
    for k in range(1, 8):
        if en[k] == 0:                                   # 16 bit: the tail has reached exactly 0
            break
        live += 1
        assert en[k + 1] < en[k], "energy not decreasing: window %d (%g) -> %d (%g)" % (k, en[k], k + 1, en[k + 1])
    assert live >= (7 if DW > 16 else 3), "tail too short: %d decreasing steps" % live


@cocotb.test()
async def test_size(dut):
    """Larger size -> longer decay: RT60 from the drop between 100-200 ms and 300-400 ms."""
    await init(dut)
    rt = []
    for i, size_f in enumerate((0.6, 0.8, 0.9, 0.95)):
        if i:
            await flush(dut)
        y = await run_impulse(dut, 4 * WIN, int(size_f * 65536), 40)
        ea = np.sum(y[WIN:2 * WIN] ** 2)
        eb = np.sum(y[3 * WIN:4 * WIN] ** 2)
        db = 10 * np.log10(ea / max(eb, 1.0))        # (16 bit: tail may reach 0)
        rt.append(60.0 * 0.2 / db)
        dut._log.info("size %.2f: window 100-200 ms vs 300-400 ms: %.1f dB drop -> RT60 ~ %.2f s",
                      size_f, db, rt[-1])
    assert all(rt[i] < rt[i + 1] for i in range(3)), "RT60 not increasing with size: %s" % rt


@cocotb.test()
async def test_damp(dut):
    """Larger damp -> less high-frequency energy in the tail (100-200 ms)."""
    await init(dut)
    hf = []
    for i, damp in enumerate((0, 60, 120)):   # (higher damp at 16 bit: tail ~ LSBs, quantisation-noise limited)
        if i:
            await flush(dut)
        y = await run_impulse(dut, 2 * WIN, int(0.9 * 65536), damp)
        t = y[WIN:2 * WIN]
        hf.append(float(np.sum(np.diff(t) ** 2) / np.sum(t ** 2)))
        dut._log.info("damp %3d: tail first-difference energy / energy = %.4f", damp, hf[-1])
    assert hf[0] > hf[1] > hf[2], "HF energy not decreasing with damp: %s" % hf


async def flush(dut):
    """Silence with size 0 / damp 0 until all lines are zero again (5/5-clock frames: the
    block needs 8 clocks per sample)."""
    setp(dut, 1, 0, 0, 255)
    for _ in range(2048 + 605 * 25):
        await frame(dut, 0, 5)


@cocotb.test()
async def test_overload(dut):
    await init(dut)
    rnd = random.Random(7)
    setp(dut, 1, 65535, 0, 255)
    for name, xs in (("noise", stimulus(rnd, 12000, "noise", FULL)),
                     ("square", stimulus(rnd, 6000, "square", FULL))):
        ys = np.array([await frame(dut, x) for x in xs])
        d = np.abs(np.diff(ys))
        jump = int(np.max(d))
        flips = int(np.sum(d > 1.5 * FULL))                # full-swing +rail <-> -rail changes
        nsat = int(np.sum(np.abs(ys) >= 0.985 * FULL))     # wet saturated (mix 255 = 255/256 wet)
        dut._log.info("%s, size max: peak %d (full scale %d), max sample-to-sample jump %d, "
                      "%d full-swing flips (> 1.5 x full scale) in %d samples, %d samples at the rails",
                      name, int(np.max(np.abs(ys))), FULL, jump, flips, len(ys), nsat)
        # With the wet level restored (WET_SHIFT 2) full-scale wide-band stimulus drives the
        # output into saturation and a saturated wide-band signal legitimately swings rail to
        # rail; wrap-around and saturation can no longer be told apart by one jump. The
        # arithmetic (sat everywhere) is checked bit-exactly by test_bitexact; here: the
        # output does saturate, and such swings stay rare.
        assert np.max(np.abs(ys)) > 0.1 * FULL, "%s: no signal" % name
        assert nsat > 0, "%s: the output never saturated (stress too weak)" % name
        assert flips <= 0.10 * len(ys), "%s: %d full-swing flips: wrap-around?" % (name, flips)


def pink_noise(n, rms_dbfs, seed=1):
    """Pink-ish noise: sum of six one-pole low-passes of white noise, scaled to rms_dbfs."""
    rng = np.random.default_rng(seed)
    w = rng.standard_normal(n + 2000)
    p = np.zeros_like(w)
    for a in (0.5, 0.8, 0.9, 0.95, 0.98, 0.99):
        y = np.zeros_like(w)
        st = 0.0
        for i in range(len(w)):
            st = a * st + (1 - a) * w[i]
            y[i] = st
        p += y / np.std(y)
    p = p[2000:]
    p = p / np.sqrt(np.mean(p ** 2)) * 10 ** (rms_dbfs / 20) * FULL
    return [int(v) for v in p]


@cocotb.test()
async def test_level(dut):
    """Wet-only (mix 255) RMS vs input RMS, 1 s pink noise at -12 dBFS RMS, size 0.84, damp 60:
    within -6 .. 0 dB (default WET_SHIFT = 2)."""
    await init(dut)
    xs = pink_noise(48000, -12)
    setp(dut, 1, int(0.84 * 65536), 60, 255)
    ys = np.array([await frame(dut, x) for x in xs], dtype=np.float64)
    r = 20 * np.log10(np.sqrt(np.mean(ys ** 2)) / np.sqrt(np.mean(np.array(xs, dtype=np.float64) ** 2)))
    dut._log.info("wet/input RMS = %.1f dB (pink noise -12 dBFS, size 0.84, damp 60, mix 255)", r)
    assert -6.0 <= r <= 0.0, "wet level %.1f dB outside -6 .. 0 dB" % r


@cocotb.test()
async def test_hw_timing(dut):
    await init(dut)
    segs = [(150, 1, 52000, 60, 160, "noise", FULL), (150, 1, 62000, 10, 255, "square", FULL),
            (100, 0, 0, 0, 0, "noise", FULL // 2), (100, 1, 40000, 200, 90, "silence", 0)]
    out_fast, out_hw = [], []
    m1 = ReverbFV(DW)
    n, mism = await run_segments(dut, m1, segs, random.Random(21), HALF, out_fast)
    assert not mism, "8/8: %d mismatches" % len(mism)
    await flush(dut)
    m2 = ReverbFV(DW)
    n2, mism = await run_segments(dut, m2, segs, random.Random(21), 512, out_hw)
    assert not mism, "512/512: %d mismatches vs model, first %s" % (len(mism), mism[0])
    assert out_fast == out_hw
    dut._log.info("reverb_fv (%d-bit): %d samples with 512/512-clock strobes identical to the 8/8 run "
                  "and to the model", DW, n2)
