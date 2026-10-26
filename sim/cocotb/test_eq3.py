"""
test_eq3.py - eq3 (v2 step D5b, 3-band EQ of three biquads) at GME_DW = 16 or 24.

  test_bitexact   RTL bit-exact to eq3_model.py: power-up (transparent), several coefficient
                  sets (bass / treble / mid / mixed / extreme), random / sine / full-scale
                  input, a half-written coefficient set that must not be used, mid-stream
                  changes, bypass, 16-clock and 1024-clock frames; latency of the result.
  test_response   magnitude response from the impulse response (DFT at 12 frequencies) for
                  four gain settings + flat, against the ideal float response and the response
                  of the quantised coefficients (0.1 dB); one short sine cross-check
  test_flat       all-0 dB sets -> output equals input (+-1 LSB)
  test_lowlevel   -90 dBFS 100 Hz sine through a +12 dB low shelf: no limit cycle / DC drift
                  (24-bit only)
  test_saturation full-scale input with +12 dB gain saturates, never wraps
"""
import math
import os
import random
import sys

import numpy as np

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "tools"))
import eq_coefs as ec                      # noqa: E402
from eq3_model import EQ3                  # noqa: E402

DW = int(os.environ.get("GME_DW", "24"))
MASK = (1 << DW) - 1
FULL = (1 << (DW - 1)) - 1
FS = 48000.0
UNITY15 = [65536 if i % 5 == 0 else 0 for i in range(15)]


def s(v):
    return v - (1 << DW) if v >= 1 << (DW - 1) else v


async def init(dut):
    Clock(dut.clk, 10, unit="ns").start()
    dut.strobe.value = 0
    dut.enable.value = 1
    dut.cw_en.value = 0
    dut.cw_addr.value = 0
    dut.cw_data.value = 0
    dut.apply.value = 0
    dut.data_in.value = 0
    await ClockCycles(dut.clk, 3)


async def frame(dut, x, n=16, rd=12):
    """One sample: strobe, read data_out `rd` clocks after the strobe edge, frame of n clocks."""
    dut.data_in.value = x & MASK
    dut.strobe.value = 1
    await RisingEdge(dut.clk)
    dut.strobe.value = 0
    await ClockCycles(dut.clk, rd)
    v = s(int(dut.data_out.value))
    await ClockCycles(dut.clk, n - 1 - rd)
    return v


async def load(dut, ints, scale=0, apply=True, upto=15, model=None):
    """Write coefficients 0..upto-1 (and the scale register if upto == 15) to the shadow
    registers, then pulse apply. Mirrors the writes into the model."""
    await RisingEdge(dut.clk)
    words = list(enumerate(ints))[:upto] + ([(15, scale)] if upto >= 15 else [])
    for a, v in words:
        dut.cw_en.value = 1
        dut.cw_addr.value = a
        dut.cw_data.value = v & 0x3FFFF
        if model is not None:
            model.write(a, v)
        await RisingEdge(dut.clk)
    dut.cw_en.value = 0
    if apply:
        dut.apply.value = 1
        if model is not None:
            model.apply()
        await RisingEdge(dut.clk)
        dut.apply.value = 0
    await ClockCycles(dut.clk, 2)


def setting(b, m, t):
    ints, shifts, clipped = ec.coefficient_set_full(b, m, t)
    assert not clipped
    return ints, ec.scale_word(shifts)


def stimulus(rnd, n, kind, amp=1.0):
    a = amp * FULL
    out = []
    ph = rnd.random() * 6.28
    f = rnd.choice([60.0, 100.0, 440.0, 1200.0, 3500.0, 9000.0])
    for i in range(n):
        if kind == "rand":
            v = rnd.randint(-FULL - 1, FULL) * amp
        elif kind == "sine":
            v = a * math.sin(ph + 2 * math.pi * f * i / FS)
        else:   # sine + noise
            v = a * 0.7 * math.sin(ph + 2 * math.pi * f * i / FS) + rnd.randint(-FULL, FULL) * amp * 0.3
        out.append(max(-FULL - 1, min(FULL, int(v))))
    return out


@cocotb.test()
async def test_bitexact(dut):
    await init(dut)
    rnd = random.Random(5)
    model = EQ3(DW)
    got, exp, ins = [], [], []

    async def run(xs, en=1, n=16):
        dut.enable.value = en
        for x in xs:
            ins.append(x)
            got.append(await frame(dut, x, n))
            exp.append(model.step(x, en))

    # power-up: transparent
    await run(stimulus(rnd, 300, "rand"))
    assert got == ins[:300], "power-up coefficients are not transparent"
    dut._log.info("power-up coefficients: transparent, model-exact")

    sets = [
        ("bass+12", (12, 0, 0), "sine"),
        ("treble+12 (scale 2)", (0, 0, 12), "mix"),
        ("mid-12", (0, -12, 0), "rand"),
        ("6/-6/6", (6, -6, 6), "mix"),
        ("-12/12/-12", (-12, 12, -12), "rand"),
        ("all +12", (12, 12, 12), "sine"),
        ("all +12 full scale", (12, 12, 12), "rand"),
        ("bass 2.5 dB", (2.5, 0, -7.5), "mix"),
    ]
    for name, g, kind in sets:
        ints, sc = setting(*g)
        await load(dut, ints, sc, model=model)
        await run(stimulus(rnd, 600, kind, 0.9 if "full" not in name else 1.0))
        await run(stimulus(rnd, 200, "sine", 0.25))
        dut._log.info("set %-22s done" % name)

    # half-written set must not be used (no apply): write 7 coefficients of a new set only
    ints, sc = setting(-9, 5, 9)
    await load(dut, ints, sc, apply=False, upto=7, model=model)
    await run(stimulus(rnd, 100, "mix", 0.5))
    # complete it: remaining coefficients + scale, then apply; used from the next sample
    await RisingEdge(dut.clk)
    for a in range(7, 16):
        dut.cw_en.value = 1
        dut.cw_addr.value = a
        v = ints[a] if a < 15 else sc
        dut.cw_data.value = v & 0x3FFFF
        model.write(a, v)
        await RisingEdge(dut.clk)
    dut.cw_en.value = 0
    dut.apply.value = 1
    model.apply()
    await RisingEdge(dut.clk)
    dut.apply.value = 0
    await run(stimulus(rnd, 400, "mix", 0.8))

    # change a single section's worth mid-stream with the filter running (no gaps)
    for g in ((3, 3, 3), (-3, -3, -3), (12, -12, 12)):
        ints, sc = setting(*g)
        await load(dut, ints, sc, model=model)
        await run(stimulus(rnd, 150, "mix", 0.7))

    # bypass, then back on (filters run through)
    await run(stimulus(rnd, 200, "mix", 0.8), en=0)
    await run(stimulus(rnd, 300, "mix", 0.8), en=1)

    # 1024-clock frames: the same results as in the 16-clock frames (model-exact both ways)
    await run(stimulus(rnd, 60, "mix", 0.8), n=1024)
    await run(stimulus(rnd, 100, "mix", 0.8), n=16)

    # latency: the clock edge (counted after the strobe edge) at which the new result is loaded
    ints, sc = setting(6, -6, 6)
    await load(dut, ints, sc, model=model)
    lat, prev = [], None
    for i in range(40):
        x = (3000 if i % 2 == 0 else -3000) * (1 << (DW - 16))
        dut.data_in.value = x & MASK
        dut.strobe.value = 1
        await RisingEdge(dut.clk)
        dut.strobe.value = 0
        e = model.step(x, 1)
        vals = []
        for k in range(1, 15):                   # vals[k-1] is read right after edge k
            await RisingEdge(dut.clk)
            vals.append(s(int(dut.data_out.value)))
        await ClockCycles(dut.clk, 1)
        got.append(vals[11])                     # as in all other tests: 12 clocks after the strobe
        exp.append(e)
        if prev is not None and prev != e:
            first = [k for k, v in enumerate(vals) if v == e]
            lat.append(first[0] if first else 99)   # loaded at edge `first`: visible when read after edge first+1
        prev = e
    latency = max(lat)
    dut._log.info("data_out register loads at the %dth clock edge after the strobe edge "
                  "(budget 12)", latency)
    assert latency <= 12

    bad = [i for i in range(len(exp)) if got[i] != exp[i]]
    assert not bad, "%d mismatches of %d, first at %d: rtl %d model %d" % (
        len(bad), len(exp), bad[0], got[bad[0]], exp[bad[0]])
    dut._log.info("eq3 (%d-bit): %d samples bit-exact to the model (%d sets, partial write, "
                  "mid-stream changes, bypass, 16- and 1024-clock frames); result %d clocks after the strobe",
                  DW, len(exp), len(sets) + 4, latency)


def float_filter(sections, xs):
    ys = list(xs)
    for b, a in sections:
        x1 = x2 = y1 = y2 = 0.0
        out = []
        for x in ys:
            y = b[0] * x + b[1] * x1 + b[2] * x2 - a[1] * y1 - a[2] * y2
            x2, x1, y2, y1 = x1, x, y1, y
            out.append(y)
        ys = out
    return ys


FREQS = [50, 100, 200, 400, 800, 1500, 2500, 3500, 5000, 8000, 12000, 15000]
NIMP = 4096                     # impulse response length: poles at radius 0.994 -> decayed by e^-26


def dft_db(h, f, amp):
    """Gain in dB at f of the impulse response h (direct DFT sum), impulse of height amp."""
    n = np.arange(len(h))
    w = 2 * np.pi * f * n / FS
    return 20 * math.log10(abs(np.sum(h * np.exp(-1j * w))) / amp)


async def sine_gain(dut, f, amp, warm=300, nmeas=480):
    """Gain in dB at f from a sine (whole cycles over nmeas samples: f a multiple of 100 Hz for
    480, of 50 Hz for 960)."""
    sr = si = 0.0
    for i in range(warm + nmeas):
        y = await frame(dut, int(round(amp * math.sin(2 * math.pi * f * i / FS))))
        if i >= warm:
            w = 2 * math.pi * f * (i - warm) / FS
            sr += y * math.cos(w)
            si += y * math.sin(w)
    return 20 * math.log10(2.0 * math.hypot(sr, si) / nmeas / amp)


@cocotb.test()
async def test_response(dut):
    """Magnitude response from the impulse response (one impulse, DFT at 12 frequencies),
    against the ideal float response and the response of the quantised coefficients; one short
    sine measurement cross-checks the method."""
    await init(dut)
    amp = 1 << (DW - 4)         # 2^20 at 24 bit, 2^12 at 16 bit
    for name, g in (("bass+12", (12, 0, 0)), ("mid-12", (0, -12, 0)), ("treble+12", (0, 0, 12)),
                    ("6/-6/6", (6, -6, 6)), ("flat", (0, 0, 0))):
        ints, sc = setting(*g)
        shifts = [(sc >> (2 * k)) & 3 for k in range(3)]
        ideal = ec.section_floats(*g)
        quant = ec.to_float_sections(ints, shifts)
        await load(dut, UNITY15, 0)              # clear the filter state of earlier tests:
        for _ in range(6):                       # unity coefficients + zeros zero all x / y history
            await frame(dut, 0)
        await load(dut, ints, sc)
        h = []
        for i in range(NIMP):
            h.append(await frame(dut, amp if i == 0 else 0))
        h = np.array(h, dtype=float)
        worst_q = worst_i = 0.0
        rows = []
        for f in FREQS:
            m = dft_db(h, f, amp)
            if DW == 16 and name in ("bass+12", "mid-12", "6/-6/6") and f <= 1500:
                # the 16-bit shaped rounding noise (about 0.3 LSB x filter gain) is too large for a
                # 12-bit impulse to resolve this shelf to 0.1 dB: use a sine (averages over 960 samples)
                m = await (sine_gain(dut, f, 0.15 * FULL, warm=1500, nmeas=960) if f <= 400
                           else sine_gain(dut, f, 0.15 * FULL))
            worst_q = max(worst_q, abs(m - ec.cascade_db(quant, f)))
            worst_i = max(worst_i, abs(m - ec.cascade_db(ideal, f)))
            rows.append("%d:%+.2f" % (f, m))
        # 0.25 dB for the +-12 dB 100 Hz low shelf: Q2.16 coefficients cannot place its pole pair
        # near z = 1 better than ~0.22 dB (see tools/eq_coefs.py quantise_section)
        tol_i = 0.25 if name == "bass+12" else 0.1
        dut._log.info("%-9s impulse DFT: max |rtl - quantised coefs| = %.3f dB, max |rtl - ideal float| "
                      "= %.3f dB (limit %.2f)  [%s]", name, worst_q, worst_i, tol_i, " ".join(rows))
        assert worst_q <= 0.1, "%s: %.3f dB from the quantised-coefficient response" % (name, worst_q)
        assert worst_i <= tol_i, "%s: %.3f dB from the ideal response" % (name, worst_i)
        if name == "6/-6/6":
            ms = await sine_gain(dut, 1000, 0.15 * FULL)
            mi = dft_db(h, 1000, amp)
            dut._log.info("1 kHz through 6/-6/6: sine %.4f dB, impulse %.4f dB, ideal %.4f dB",
                          ms, mi, ec.cascade_db(ideal, 1000))
            # 16 bit: the 12-bit impulse is noise-limited (about 0.06 dB); the sine is the reference
            assert abs(ms - mi) <= (0.05 if DW == 24 else 0.1), "sine and impulse disagree: %.3f dB" % abs(ms - mi)
            assert abs(ms - ec.cascade_db(quant, 1000)) <= 0.05


@cocotb.test()
async def test_flat(dut):
    await init(dut)
    rnd = random.Random(9)
    cases = [("unity", UNITY15, 0)]
    ints, sc = setting(0, 0, 0)
    cases.append(("eq_coefs 0/0/0", ints, sc))
    # a flat set built from non-trivial coefficients: poles and zeros cancel (b = a)
    raw = []
    for fn, f0 in ((ec.low_shelf, 100.0), (ec.peaking, 800.0), (ec.high_shelf, 3500.0)):
        b, a = fn(0.0, f0)
        raw += [ec.quantise(v)[0] for v in (b[0], b[1], b[2], a[1], a[2])]
    cases.append(("cancelling 0 dB", raw, 0))
    for name, ints, sc in cases:
        await load(dut, ints, sc)
        xs = stimulus(rnd, 600, "rand") + stimulus(rnd, 600, "sine", 0.9) + stimulus(rnd, 300, "rand", 0.01)
        worst = 0
        for x in xs:
            y = await frame(dut, x)
            worst = max(worst, abs(y - x))
        dut._log.info("flat (%s): max |out - in| = %d LSB over %d samples", name, worst, len(xs))
        assert worst <= 1, "%s: %d LSB" % (name, worst)


@cocotb.test()
async def test_lowlevel(dut):
    if DW != 24:
        dut._log.info("low-level test only at 24 bit")
        return
    await init(dut)
    ints, sc = setting(12, 0, 0)
    await load(dut, ints, sc)
    shifts = [(sc >> (2 * k)) & 3 for k in range(3)]
    ideal = ec.to_float_sections(ints, shifts)  # float filter with the quantised coefficients
    amp = FULL * 10 ** (-90 / 20.0)             # about 265 LSB
    n_sine, n_zero = 2400 + 4800, 4800
    xs = [int(round(amp * math.sin(2 * math.pi * 100 * i / FS))) for i in range(n_sine)]
    xs += [0] * n_zero
    ys = []
    for x in xs:
        ys.append(await frame(dut, x))
    ref = float_filter(ideal, xs)
    seg = range(2400, n_sine)                   # 10 whole periods of 100 Hz
    res = [ys[i] - ref[i] for i in seg]
    mean = sum(res) / len(res)
    rms = math.sqrt(sum(r * r for r in res) / len(res))
    mx = max(abs(r) for r in res)
    out_mean = sum(ys[i] for i in seg) / len(seg)
    tail = ys[-1500:]
    dut._log.info("-90 dBFS 100 Hz (%.0f LSB peak) through +12 dB low shelf: output peak %d, "
                  "residual vs float filter (same coefs): mean %.3f, rms %.3f, max %.3f LSB; output mean %.3f LSB; "
                  "after input stops: last 1500 outputs min %d max %d",
                  amp, max(ys[2400:n_sine]), mean, rms, mx, out_mean, min(tail), max(tail))
    assert abs(mean) < 0.5 and rms < 8 and mx < 32, "residual too large"
    assert abs(out_mean) < 0.5, "DC drift"
    assert all(abs(v) <= 1 for v in tail), "limit cycle / DC after the input stops"


@cocotb.test()
async def test_saturation(dut):
    await init(dut)
    full_p, full_n = FULL, -FULL - 1
    for name, g, f in (("bass+12 @100 Hz", (12, 0, 0), 100.0), ("all+12 @400 Hz", (12, 12, 12), 400.0),
                       ("treble+12 @8 kHz", (0, 0, 12), 8000.0)):
        ints, sc = setting(*g)
        await load(dut, ints, sc)
        ys = []
        for i in range(2400):
            x = int(round(FULL * math.sin(2 * math.pi * f * i / FS)))
            ys.append(await frame(dut, x))
        ys = ys[600:]
        hit_p = ys.count(full_p)
        hit_n = ys.count(full_n)
        step = max(abs(ys[i] - ys[i - 1]) for i in range(1, len(ys)))
        dut._log.info("%s full scale: %d samples at +FS, %d at -FS, max sample step %.3f FS",
                      name, hit_p, hit_n, step / float(FULL))
        assert hit_p > 20 and hit_n > 20, "no saturation seen"
        if f < 1000:
            assert step < 0.35 * FULL, "wrap-around (step %d)" % step
