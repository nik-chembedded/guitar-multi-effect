"""
test_dynamics.py - dynamics (noise gate + compressor, v2 step D5a).

The block has no reset, so the physical tests each start from a fresh simulation (the
list of the 7 simulations is at the end of this docstring):

  test_bitexact   RTL bit-exact to dynamics_model.py (GME_DW = 16 / 24, GME_FRAME clocks
                  per sample, GME_QUICK = first 300 samples only): level steps, bursts,
                  silence, noise, full-scale squares, parameter changes mid-stream, all
                  enable combinations, extreme parameter values
  test_bypass     exact pass-through when off
  test_timing     clocks from the strobe to the registered result
  test_accuracy   log2 / exp2 error in dB (pure Python, no simulation)
  test_curve      static compressor curve against the ideal curve (sines, RMS)
  test_attack_release  gain settling time after a level step, against a float prediction
  test_gate       gate attenuation, pass-through above the threshold, hysteresis
  test_click      toggling comp_en / gate_en mid-signal: no output step beyond the signal's own,
                  exact bypass after the glide

The 7 simulations for test_runner (toplevel "dynamics", test module "test_dynamics", sources
fx_pkg.vhd + dynamics.vhd, parameters={"DW": DW}, extra_env GME_DW = DW, GME_FRAME, GME_QUICK):

    DW  frame  QUICK  testcases                              tag
    24    16     0    test_bitexact,test_bypass,test_click   _24
    16    16     0    test_bitexact,test_bypass,test_click   _16
    24  1024     1    test_bitexact                          _1024
    24    16     0    test_timing,test_accuracy              _tim
    24    16     0    test_curve                             _curve
    24    16     0    test_attack_release                    _ar
    24    16     0    test_gate                              _gate

(testcase = comma-separated list: pass testcase="a,b".split(","). test_click runs after
test_bitexact / test_bypass in the same simulation; it settles itself.)
"""
import math
import os
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge

import dynamics_model as dm

DW = int(os.environ.get("GME_DW", "16"))
FRAME = int(os.environ.get("GME_FRAME", "16"))
QUICK = os.environ.get("GME_QUICK", "0") == "1"
MASK = (1 << DW) - 1
FULL = (1 << (DW - 1)) - 1
DB_Q8 = 256 / (20 * math.log10(2))          # Q8 log2 units per dB (= 42.52)


def s(v):
    return v - (1 << DW) if v >= 1 << (DW - 1) else v


def q8(db):
    return round(db * DB_Q8)


def amp(db):
    return FULL * 10 ** (db / 20)


class Bench:
    def __init__(self, dut, frame=FRAME):
        self.dut = dut
        self.frame = frame
        self.p = {}

    async def start(self):
        d = self.dut
        Clock(d.clk, 10, unit="ns").start()
        d.strobe.value = 0
        d.data_in.value = 0
        self.p = {}
        self.set(enable=1, gate_en=0, comp_en=0, gate_thresh=0, comp_thresh=0, comp_ratio=0,
                 comp_makeup=0, comp_attack=0, comp_release=0)
        await ClockCycles(d.clk, 20)

    def set(self, **kw):
        for k, v in kw.items():
            if self.p.get(k) != v:
                self.p[k] = v
                getattr(self.dut, k).value = v & (1 if k in ("enable", "gate_en", "comp_en") else 0xFFFF)

    async def push(self, x):
        """One sample; returns (y, gain_reduction) read at the end of the frame."""
        d = self.dut
        d.data_in.value = x & MASK
        d.strobe.value = 1
        await RisingEdge(d.clk)
        d.strobe.value = 0
        await ClockCycles(d.clk, self.frame - 1)
        return s(int(d.data_out.value)), int(d.gain_reduction.value)

    async def run(self, xs):
        ys, ms = [], []
        for x in xs:
            y, m = await self.push(int(x))
            ys.append(y)
            ms.append(m)
        return ys, ms


def sine(n, db, f=1000.0, n0=0):
    return [round(amp(db) * math.sin(2 * math.pi * f / 48000 * (n0 + i))) for i in range(n)]


def rms(v):
    return math.sqrt(sum(float(a) * a for a in v) / len(v))


def dbr(a, b):
    return 20 * math.log10(a / b)


# ----------------------------------------------------------------------------------------
# bit-exact
# ----------------------------------------------------------------------------------------
def build_stimulus(rnd):
    """List of (x, params) per sample."""
    out = []
    n_glob = [0]

    def block(n, par, kind, db, f=0.0137):
        for i in range(n):
            if kind == "sine":
                x = round(amp(db) * math.sin(2 * math.pi * f * n_glob[0]))
            elif kind == "noise":
                x = round(rnd.uniform(-1, 1) * amp(db))
            elif kind == "burst":
                x = round(rnd.uniform(-1, 1) * amp(db)) if (i // 100) % 2 == 0 else 0
            elif kind == "dc":
                x = round(amp(db))
            elif kind == "square":
                x = (FULL if (i // 10) % 2 == 0 else -FULL - 1)
            else:
                x = 0
            n_glob[0] += 1
            out.append((max(-FULL - 1, min(FULL, x)), par))

    def P(en=1, g=0, c=0, gth=-45, cth=-20, rat=2, mk=0, att=3, rel=5):
        return dict(enable=en, gate_en=g, comp_en=c, gate_thresh=q8(gth) & 0xFFFF,
                    comp_thresh=q8(cth) & 0xFFFF, comp_ratio=rat, comp_makeup=q8(mk) & 0xFFFF,
                    comp_attack=att, comp_release=rel)

    # 0: 300 samples, level steps (quick-run segment)
    for db in (-30, -6, -40, -12, -3, -50):
        block(50, P(1, 1, 1, -45, -20, 2, 3, 3, 5), "sine", db)
    if QUICK:
        return out
    # 1: noise bursts and silence, infinity:1, fast attack
    block(1500, P(1, 1, 1, -40, -25, 4, 0, 1, 6), "burst", -10)
    # 2: 2:1 compressor only, level steps
    for db in (-20, -6, -30, 0, -45, -12):
        block(200, P(1, 0, 1, -40, -30, 1, 0, 4, 8), "sine", db)
    # 3: gate only, noise near the threshold, then silence
    block(500, P(1, 1, 0, -50, -20, 0, 0, 0, 0), "noise", -52)
    block(300, P(1, 1, 0, -50, -20, 0, 0, 0, 0), "noise", -35)
    block(300, P(1, 1, 0, -50, -20, 0, 0, 0, 0), "silence", 0)
    # 4: disabled (state frozen), then re-enabled with the old state
    block(300, P(0, 1, 1), "noise", -10)
    block(300, P(1, 1, 1), "noise", -10)
    # 5: 8:1 with negative makeup, DC steps
    for db in (-60, -10, -30, -3):
        block(150, P(1, 0, 1, -40, -35, 3, -6, 2, 7), "dc", db)
    # 6: extremes: full-scale square, very low threshold, makeup way over the limit
    block(400, P(1, 0, 1, -40, -100, 7, 30, 0, 15), "square", 0)
    block(400, P(1, 1, 1, 0, -100, 5, 30, 15, 0), "noise", -3)
    # 7: 1:1 with big makeup (saturates), then raw extreme register values
    block(400, P(1, 0, 1, -40, -30, 0, 12, 15, 0), "sine", -12)
    ex = P(1, 1, 1)
    ex.update(gate_thresh=0x7FFF, comp_thresh=0x8000, comp_ratio=0xFFFF, comp_makeup=0x7FFF,
              comp_attack=0xFFF3, comp_release=0xAAA5)
    block(300, ex, "noise", -20)
    ex = P(1, 1, 1)
    ex.update(gate_thresh=0x8000, comp_thresh=0x7FFF, comp_makeup=0x8000)
    block(300, ex, "noise", -20)
    # 8: random parameters every 100 samples, every enable combination twice
    for i in range(16):
        c = i % 8
        p = P(en=c & 1, g=(c >> 1) & 1, c=(c >> 2) & 1,
              gth=rnd.uniform(-70, 0), cth=rnd.uniform(-70, 0), rat=rnd.randint(0, 7),
              mk=rnd.uniform(-12, 24), att=rnd.randint(0, 15), rel=rnd.randint(0, 15))
        kind = rnd.choice(["sine", "noise", "burst", "dc", "square"])
        block(100, p, kind, rnd.uniform(-60, 0))
    return out


@cocotb.test()
async def test_bitexact(dut):
    b = Bench(dut)
    await b.start()
    rnd = random.Random(11)
    stim = build_stimulus(rnd)
    model = dm.Dynamics(DW)
    mism = 0
    first = None
    n_changed = n_closed = n_sat = 0
    max_meter = 0
    csum = 0
    for i, (x, par) in enumerate(stim):
        b.set(**par)
        y, m = await b.push(x)
        ey = model.step(x, **par)
        em = model.meter if par["enable"] else None
        if i < 300:
            csum = (csum * 31 + (y & MASK) + 7 * (m & 0xFFFF)) % (1 << 61)
        if y != ey or (em is not None and m != em):
            mism += 1
            if first is None:
                first = (i, x, y, ey, m, em)
        if y != x:
            n_changed += 1
        if not model.gopen and par["gate_en"]:
            n_closed += 1
        if y in (FULL, -FULL - 1) and x not in (FULL, -FULL - 1):
            n_sat += 1
        max_meter = max(max_meter, m)
    n = len(stim)
    assert mism == 0, "%d / %d mismatches, first at %s (i, x, rtl y, model y, rtl meter, model meter)" % (mism, n, first)
    if not QUICK:
        assert n_changed > 3000 and n_closed > 300 and n_sat > 0 and max_meter > 1000, \
            "stimulus too weak: changed %d closed %d sat %d meter %d" % (n_changed, n_closed, n_sat, max_meter)
    # the checksum of the first 300 outputs / meters is identical for every frame length
    exp = 0
    m2 = dm.Dynamics(DW)
    for i, (x, par) in enumerate(stim[:300]):
        ey = m2.step(x, **par)
        exp = (exp * 31 + (ey & MASK) + 7 * (m2.meter & 0xFFFF)) % (1 << 61)
    assert csum == exp
    dut._log.info("RESULT bitexact DW=%d frame=%d clk: %d samples bit-exact (output and gain_reduction); "
                  "changed %d, gate-closed %d, saturated %d, max meter %d; checksum(first 300)=%d",
                  DW, FRAME, n, n_changed, n_closed, n_sat, max_meter, csum)


# ----------------------------------------------------------------------------------------
@cocotb.test()
async def test_bypass(dut):
    b = Bench(dut)
    await b.start()
    rnd = random.Random(5)
    xs = [rnd.randint(-FULL - 1, FULL) for _ in range(1500)] + [FULL, -FULL - 1] * 20
    cases = [
        ("gate_en = comp_en = 0 (wild parameters)", dict(enable=1, gate_en=0, comp_en=0, gate_thresh=0x7FFF,
         comp_thresh=0x8000, comp_ratio=4, comp_makeup=0x7FFF, comp_attack=0, comp_release=0)),
        ("enable = 0", dict(enable=0, gate_en=1, comp_en=1, gate_thresh=0x7FFF, comp_thresh=0x8000,
         comp_ratio=4, comp_makeup=0x7FFF, comp_attack=0, comp_release=0)),
        ("comp only at 1:1, makeup 0", dict(enable=1, gate_en=0, comp_en=1, gate_thresh=0x7FFF,
         comp_thresh=q8(-60) & 0xFFFF, comp_ratio=0, comp_makeup=0, comp_attack=0, comp_release=0)),
        ("gate only, always open", dict(enable=1, gate_en=1, comp_en=0, gate_thresh=0x8000,
         comp_thresh=0, comp_ratio=4, comp_makeup=0x7FFF, comp_attack=0, comp_release=0)),
        ("comp threshold 0 dBFS (never reached), makeup 0", dict(enable=1, gate_en=0, comp_en=1,
         gate_thresh=0, comp_thresh=0, comp_ratio=4, comp_makeup=0, comp_attack=0, comp_release=0)),
    ]
    for name, par in cases:
        b.set(**par)
        ys, _ = await b.run(xs)
        bad = [i for i in range(len(xs)) if ys[i] != xs[i]]
        assert not bad, "bypass '%s': %d samples differ, first %d (x %d y %d)" % (
            name, len(bad), bad[0], xs[bad[0]], ys[bad[0]])
    dut._log.info("RESULT bypass DW=%d: output == input exactly for %d samples in each of %d cases",
                  DW, len(xs), len(cases))


# ----------------------------------------------------------------------------------------
@cocotb.test()
async def test_timing(dut):
    """Clocks from the strobe to the registered result."""
    b = Bench(dut, frame=16)
    await b.start()
    # comp_en with 1:1 and makeup +6 dB (g = +256): y = 2 x regardless of history
    b.set(enable=1, gate_en=0, comp_en=1, comp_ratio=0, comp_makeup=256)
    d = dut
    lats = set()
    prev = 0
    for n in range(60):
        x = 1000 if n % 2 == 0 else 3000
        if n == 40:
            b.set(enable=0)               # pass-through: registered at the strobe edge itself
        d.data_in.value = x
        d.strobe.value = 1
        await RisingEdge(d.clk)
        d.strobe.value = 0
        reads = []
        for k in range(1, 16):
            await RisingEdge(d.clk)
            reads.append(s(int(d.data_out.value)))
        new = x if n >= 40 else 2 * x
        # reads[k-1] is the value read after the k-th edge after the strobe edge, i.e. the
        # state after edge E(k-1); the result is registered at the first edge E(N) after
        # which it holds the new value
        first = next(k for k in range(15) if reads[k] == new)
        assert all(r == new for r in reads[first:]), "output not stable after settling: %s" % reads
        assert all(r == prev for r in reads[:first]), "output changed early: %s" % reads
        lats.add(first)
        prev = new
        # (reads[0] is the state after E0)
    dut._log.info("RESULT timing: result registered at clock edge(s) E%s after the strobe edge E0 "
                  "(pass-through included in the set; DUT with enable = 1 -> E10)", sorted(lats))
    assert max(lats) <= 12
    assert sorted(lats) == [0, 10]


# ----------------------------------------------------------------------------------------
@cocotb.test()
async def test_accuracy(dut):
    # log2: error in dB vs the exact value
    errs = []
    es = list(range(1, 65536)) + [1 << k for k in range(24)] + [(1 << k) - 1 for k in range(2, 25)] + \
         [(1 << k) + 1 for k in range(1, 23)]
    rnd = random.Random(3)
    es += [rnd.randint(1, 1 << 23) for _ in range(200000)]
    es += [int(2 ** rnd.uniform(0, 23)) or 1 for _ in range(100000)]
    for e in es:
        if e > 1 << 23:
            continue
        errs.append((dm.log2q8(e) / 256 - math.log2(e)) * 6.0205999)
    lo, hi = min(errs), max(errs)
    assert lo > -0.03 and hi < 0.005, (lo, hi)
    # exp2: gain error in dB over the whole exponent range, and down to -60 dB
    ee_all, ee_60 = [], []
    for g in range(dm.G_MIN, dm.G_MAX + 1):
        G = dm.exp2gain(g) / 2 ** dm.GAIN_FRAC
        err = 20 * math.log10(G) - g / 256 * 6.0205999
        ee_all.append(err)
        if g >= -2560:
            ee_60.append(err)
    ee_48 = [v for g, v in zip(range(dm.G_MIN, dm.G_MAX + 1), ee_all) if g >= -2048]
    assert max(abs(v) for v in ee_48) < 0.01, max(abs(v) for v in ee_48)
    assert max(abs(v) for v in ee_60) < 0.035, max(abs(v) for v in ee_60)
    # mono check: log2 and exp2 are monotonic
    ls = [dm.log2q8(e) for e in range(1, 1 << 16)]
    assert all(b >= a for a, b in zip(ls, ls[1:]))
    gs = [dm.exp2gain(g) for g in range(dm.G_MIN, dm.G_MAX + 1)]
    assert all(b >= a for a, b in zip(gs, gs[1:]))
    # the tables in the VHDL are the ones of the model
    here = os.path.dirname(os.path.abspath(__file__))
    src = open(os.path.join(here, "..", "..", "fpga", "rtl", "dynamics.vhd")).read()
    import re
    for name, tab in (("LOG_T", dm.LOG_T), ("EXP_T", dm.EXP_T)):
        mt = re.search(r"constant %s : tab_t := \(([^)]*)\)" % name, src)
        vals = [int(v) for v in mt.group(1).replace("\n", " ").split(",")]
        assert vals == tab, name
    dut._log.info("RESULT accuracy: log2 (%d values, 1 .. 2^23): error %.4f .. %+.4f dB; "
                  "exp2 (g -96 .. +24 dB, %d values): max |error| %.4f dB for gain >= -48 dB, %.4f dB for "
                  ">= -60 dB, %.3f dB over the full range (the Q18 gain quantisation dominates at low "
                  "gain); VHDL tables == model",
                  len(errs), lo, hi, len(ee_all), max(abs(v) for v in ee_48), max(abs(v) for v in ee_60),
                  max(abs(v) for v in ee_all))


# ----------------------------------------------------------------------------------------
@cocotb.test()
async def test_curve(dut):
    """Static compressor curve: 1 kHz sines, threshold -30 dBFS, RMS gain after settling."""
    b = Bench(dut)
    await b.start()
    T = -30.0
    levels = list(range(-50, 1, 5))
    n_set, n_meas = 3000, 960
    lines = []
    worst = 0
    for code, name, R in ((1, "2:1", 2.0), (2, "4:1", 4.0), (4, "inf:1", math.inf)):
        b.set(enable=1, gate_en=0, comp_en=1, comp_thresh=q8(T) & 0xFFFF, comp_ratio=code,
              comp_makeup=0, comp_attack=3, comp_release=8)
        row = []
        n0 = 0
        await b.run([0] * 16000)                  # let the detector decay from the previous ratio
        for db in levels:
            xs = sine(n_set, db, 1000.0, n0)
            n0 += n_set
            ys, _ = await b.run(xs)
            g = dbr(rms(ys[-n_meas:]), rms(xs[-n_meas:]))
            ideal = -max(0.0, db - T) * (1 - 1 / R)
            row.append((db, g, ideal))
            worst = max(worst, abs(g - ideal))
            assert abs(g - ideal) <= 0.5, "ratio %s level %d dB: gain %.3f dB, ideal %.3f dB" % (name, db, g, ideal)
        lines.append("%s: " % name + " ".join("%d:%+.2f/%+.2f" % r for r in row))
    dut._log.info("RESULT curve (T=-30 dBFS, measured/ideal gain in dB per input level): %s; "
                  "max |error| = %.3f dB", " | ".join(lines), worst)


# ----------------------------------------------------------------------------------------
def predict_settle(par_att, par_rel, db_from, db_to, T, ratio_inf=True, n=60000):
    """Float (unquantised) model of detector + gain smoothing for a DC step; returns the
    number of samples until the gain is within 1 dB of its final value for good."""
    ka, kr = dm.K_ATT, dm.K_REL
    a0, a1 = 2.0 ** 23 * 10 ** (db_from / 20), 2.0 ** 23 * 10 ** (db_to / 20)
    env = a0
    rs = max(0.0, (math.log2(a0) - 23) * 256 - q8(T)) * 256 if db_from > T else 0.0
    gs = []
    for i in range(n):
        env += (a1 - env) / 2 ** (ka if a1 > env else kr)
        L = (math.log2(env) - 23) * 256
        red = max(0.0, L - q8(T))
        d = red * 256 - rs
        rs += d / 2 ** (par_att if d > 0 else par_rel)
        gs.append(-rs / 256 / DB_Q8)
    final = gs[-1]
    last_bad = max((i for i, v in enumerate(gs) if abs(v - final) > 1.0), default=-1)
    return last_bad + 1, final


@cocotb.test()
async def test_attack_release(dut):
    b = Bench(dut)
    await b.start()
    T = -30.0
    res = []
    # --- attack: DC -50 -> -10 dBFS (infinity:1: final gain = -(-10 - -30) = -20 dB)
    for ka in (5, 7):
        b.set(enable=1, gate_en=0, comp_en=1, comp_thresh=q8(T) & 0xFFFF, comp_ratio=4,
              comp_makeup=0, comp_attack=ka, comp_release=10)
        x_lo, x_hi = round(amp(-50)), round(amp(-10))
        await b.run([x_lo] * 12000)              # settle (envelope, gain = 1)
        n = 1500
        ys, _ = await b.run([x_hi] * n)
        g = [dbr(abs(y), x_hi) for y in ys]
        final = g[-1]
        assert abs(final - (-20.0)) < 0.3, final
        meas = max(i for i, v in enumerate(g) if abs(v - final) > 1.0) + 1
        pred, pfinal = predict_settle(ka, 10, -50, -10, T)
        res.append(("attack k=%d" % ka, meas, pred))
        assert abs(meas - pred) <= max(4, 0.12 * pred), (ka, meas, pred)
        # release for the same pair: back to -50 dBFS
        n = 30000
        ys, _ = await b.run([x_lo] * n)
        g = [dbr(abs(y), x_lo) for y in ys]
        meas_r = max(i for i, v in enumerate(g) if abs(v) > 1.0) + 1
        pred_r, _ = predict_settle(10, 10, -10, -50, T)
        res.append(("release k=10 (after attack k=%d)" % ka, meas_r, pred_r))
        assert abs(meas_r - pred_r) <= max(6, 0.12 * pred_r), (meas_r, pred_r)
    # --- release with a slow gain release: k = 12
    b.set(comp_attack=3, comp_release=12)
    await b.run([x_hi] * 12000)
    ys, _ = await b.run([x_lo] * 40000)
    g = [dbr(abs(y), x_lo) for y in ys]
    meas_r = max(i for i, v in enumerate(g) if abs(v) > 1.0) + 1
    pred_r, _ = predict_settle(3, 12, -10, -50, T)
    res.append(("release k=12", meas_r, pred_r))
    assert abs(meas_r - pred_r) <= max(6, 0.12 * pred_r), (meas_r, pred_r)
    # consistency of the scaling: attack time ~ 4x for k + 2
    ta5 = [m for (nme, m, p) in res if nme == "attack k=5"][0]
    ta7 = [m for (nme, m, p) in res if nme == "attack k=7"][0]
    assert 3.3 < ta7 / ta5 < 4.7, (ta5, ta7)
    dut._log.info("RESULT attack/release (DC step 20 dB over the -30 dBFS threshold, infinity:1, "
                  "time until the gain stays within 1 dB of its final value; measured vs float "
                  "prediction): %s; attack k=7 / k=5 = %.2f (ideal 4)",
                  "; ".join("%s: %d samples = %.1f ms (pred %d = %.1f ms)" % (nme, m, m / 48.0, p, p / 48.0)
                            for nme, m, p in res), ta7 / ta5)


# ----------------------------------------------------------------------------------------
@cocotb.test()
async def test_gate(dut):
    b = Bench(dut)
    await b.start()
    rnd = random.Random(9)
    TG = -40.0
    b.set(enable=1, gate_en=1, comp_en=0, gate_thresh=q8(TG) & 0xFFFF)
    # signal above the threshold: sine -20 dBFS -> unchanged
    xs = sine(6000, -20.0, 1000.0)
    ys, ms = await b.run(xs)
    chg = dbr(rms(ys[-960:]), rms(xs[-960:]))
    assert abs(chg) < 0.2 and max(ms[100:]) == 0     # (the first samples: envelope still rising)
    # noise at -60 dBFS rms (peaks of the detector ~ -50 dB, below threshold - 3 dB = -43 dBFS)
    sigma = amp(-60.0)
    noise = [max(-FULL - 1, min(FULL, round(rnd.gauss(0, sigma)))) for _ in range(14000)]
    ys, ms = await b.run(noise)
    # time until the gate has attenuated by 40 dB (meter in Q8 log2 units; 40 dB = 1701)
    t40 = next(i for i, m in enumerate(ms) if m >= q8(40))
    tfull = next(i for i, m in enumerate(ms) if m >= 3584)
    att = dbr(rms(ys[-4000:]), rms(noise[-4000:]))
    assert att < -40, att
    # sine again: opens within ~1 ms, no change afterwards
    xs = sine(4000, -20.0, 1000.0)
    ys, ms = await b.run(xs)
    t_open = next(i for i, m in enumerate(ms) if m == 0)
    chg2 = dbr(rms(ys[-960:]), rms(xs[-960:]))
    assert abs(chg2) < 0.2
    assert t_open <= 60
    # hysteresis with DC levels (threshold -40 dBFS, closes below -43 dBFS)
    async def dc(db, n):
        ys, ms = await b.run([round(amp(db))] * n)
        return ms
    ms = await dc(-20, 3000)
    assert ms[-1] == 0
    ms = await dc(-41.5, 14000)                     # inside the 3 dB window: stays open
    assert max(ms) == 0, "gate closed inside the hysteresis window"
    ms = await dc(-60, 12000)                       # below: closes
    assert ms[-1] == 3584, ms[-1]
    ms = await dc(-41.5, 4000)                      # inside the window: stays closed
    assert min(ms) == 3584, "gate opened inside the hysteresis window"
    ms = await dc(-36, 400)                         # above the threshold: opens
    assert ms[-1] == 0
    dut._log.info("RESULT gate (threshold -40 dBFS): sine -20 dBFS passes with %+.3f dB change (gate open); "
                  "-60 dBFS rms noise: 40 dB attenuation after %d samples (%.1f ms from the start of the noise), "
                  "fully closed (84.3 dB) after %d samples (%.1f ms), measured attenuation of the noise rms "
                  "%.1f dB; reopen: gate fully open %d samples (%.2f ms) after the signal returns, then %+.3f dB; "
                  "hysteresis: stays open at -41.5 dBFS, closes at -60, stays closed at -41.5, opens at -36",
                  chg, t40, t40 / 48.0, tfull, tfull / 48.0, att, t_open, t_open / 48.0, chg2)


# ----------------------------------------------------------------------------------------
@cocotb.test()
async def test_click(dut):
    """comp_en / gate_en toggled in the middle of a sine: the gain glides (no jump), and after
    the glide the output is bit-exact pass-through again."""
    b = Bench(dut)
    await b.start()
    n_glob = [0]
    cth, gth = q8(-30) & 0xFFFF, q8(-40) & 0xFFFF
    base = dict(enable=1, gate_en=0, comp_en=0, gate_thresh=gth, comp_thresh=cth, comp_ratio=4,
                comp_makeup=0, comp_attack=5, comp_release=7)

    async def play(db, n):
        xs = sine(n, db, 1000.0, n_glob[0])
        n_glob[0] += n
        ys, _ = await b.run(xs)
        return xs, ys

    def mstep(v):
        return max(abs(v[i] - v[i - 1]) for i in range(1, len(v)))

    mk6 = q8(6) & 0xFFFF
    # name, level dBFS, pre-toggle settings, post-toggle settings, allowed factor, bypass at end
    cases = [
        ("comp off (24 dB reduction)", -6, dict(comp_en=1), dict(comp_en=0), 1.05, True),
        ("comp on (from 0 dB, 24 dB reduction)", -6, dict(comp_en=0), dict(comp_en=1), 1.05, False),
        ("comp off (+6 dB makeup glides out)", -40, dict(comp_en=1, comp_makeup=mk6),
         dict(comp_en=0), 1.05, True),
        ("comp on (+6 dB makeup glides in)", -40, dict(comp_en=0), dict(comp_en=1, comp_makeup=mk6),
         1.05, False),
        ("gate off, was open", -20, dict(comp_en=0, gate_en=1, comp_makeup=0), dict(gate_en=0), 1.05, True),
        ("gate off, was closed (84 dB)", -60, dict(gate_en=1), dict(gate_en=0), 1.5, True),
        ("gate on (closes over 50 ms)", -60, dict(gate_en=0), dict(gate_en=1), 1.05, False),
    ]
    rep = []
    for name, db, pre, post, factor, bypass in cases:
        b.set(**{**base, **pre})
        x1, y1 = await play(db, 14000 if ("makeup" in name or "comp on" in name) else 9000)
        b.set(**{**base, **pre, **post})
        x2, y2 = await play(db, 6000)
        # steps of the output across the toggle against the larger steady-state output step
        # (before the toggle, and after it: the input's own when the stage is bypassed)
        own = max(mstep(y1[-960:]), mstep(y2[-960:]), mstep(x2) if bypass else 0)
        got = mstep([y1[-1]] + y2)
        assert got <= own * factor, "%s: output step %d > %.2f x own %d" % (name, got, factor, own)
        if bypass:
            bad = [i for i in range(len(x2) - 1000, len(x2)) if y2[i] != x2[i]]
            assert not bad, "%s: not bit-exact after the glide (%d samples)" % (name, len(bad))
        rep.append("%s: max step %d vs own %d (%.2f)%s" % (name, got, own, got / own,
                                                          ", exact bypass after glide" if bypass else ""))
    dut._log.info("RESULT click DW=%d: %s", DW, "; ".join(rep))
