"""
test_cabfir.py - cab_fir (v2 step D3), run with GME_DW, GME_TAPS, GME_LANES (and the
matching generics DW, TAPS, LANES). Test cases:

  test_random   (TAPS < 2048) random full-scale input, random coefficients, shifts 0..7,
                saturation, bank 1 written while bank 0 plays, then switched; frames of
                the minimum length TAPS/LANES + 7 clocks; bit-exact to cabfir_model.py
  test_impulse  independent of the model: an impulse reproduces the coefficient sequence
                (A * h[k] >> (17 + shift)) at the right latency, both banks
  test_latency  smallest frame length (clocks between starts) with a correct result
  test_full     (TAPS = 2048) the real default .mif (checked against the IR), impulse over
                all 2048 taps, then 1024-clock frames of random input, a bank switch
                with a few coefficients written to bank 1, all bit-exact to the model
"""
import os
import random
import sys

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge

from cabfir_model import CabFir

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import cab_coefs  # noqa: E402

DW = int(os.environ.get("GME_DW", "24"))
TAPS = int(os.environ.get("GME_TAPS", "64"))
LANES = int(os.environ.get("GME_LANES", "4"))
TPL = TAPS // LANES
MIN_FRAME = TPL + 7                      # clocks between starts (derived, checked by test_latency)
MASK = (1 << DW) - 1
MIF = os.path.join(ROOT, "fpga", "ip", "cab_default.mif")
XMIN, XMAX = -(1 << (DW - 1)), (1 << (DW - 1)) - 1


def sgn(v, w=DW):
    return v - (1 << w) if v >= 1 << (w - 1) else v


class Drv:
    """Drives frames of F clocks and records data_out (= y[n-1] after start n)."""

    def __init__(self, dut, model, F):
        self.dut, self.model, self.F = dut, model, F
        self.outs, self.exp, self.xs = [], [], []

    async def frame(self, x, bank=0, shift=0, writes=None, F=None):
        d, F = self.dut, F or self.F
        writes = writes if writes is not None else []
        d.data_in.value = x & MASK
        d.bank.value = bank
        d.shift.value = shift
        d.start.value = 1
        await RisingEdge(d.clk)                  # start edge E0
        d.start.value = 0
        for _ in range(F - 1):
            if writes:                           # one coefficient per clock
                b, a, v = writes.pop(0)
                d.cw_en.value, d.cw_bank.value, d.cw_addr.value = 1, b, a
                d.cw_data.value = v & 0x3FFFF
                self.model.write(b, a, v)
            else:
                d.cw_en.value = 0
            await RisingEdge(d.clk)
        d.cw_en.value = 0
        self.outs.append(sgn(int(d.data_out.value)))      # y[n-1]
        self.exp.append(self.model.step(x, bank, shift))  # y[n]
        self.xs.append(x)

    async def flush(self, bank=0, shift=0):
        await self.frame(0, bank, shift)

    def mismatches(self, skip_first=1):
        """data_out of frame n+1 must be the model's y[n]."""
        return [n for n in range(len(self.exp) - 1) if self.outs[n + 1] != self.exp[n]]


async def setup(dut):
    Clock(dut.clk, 10, unit="ns").start()
    for s in ("start", "cw_en", "cw_bank", "bank"):
        getattr(dut, s).value = 0
    dut.data_in.value = 0
    dut.shift.value = 0
    dut.cw_addr.value = 0
    dut.cw_data.value = 0
    await RisingEdge(dut.clk)


def mif_model():
    return CabFir(DW, TAPS, cab_coefs.read_mif(MIF))


def coef_writes(bank, coefs):
    return [(bank, a, int(c)) for a, c in enumerate(coefs)]


@cocotb.test(skip=TAPS >= 2048)
async def test_random(dut):
    await setup(dut)
    rnd = random.Random(1234 + DW)
    model = mif_model()                            # as the RAM: mif words beyond bank 0 land in bank 1
    drv = Drv(dut, model, MIN_FRAME)
    nsat = [0, 0]                                  # saturated / not saturated outputs

    def rx():
        return rnd.randint(XMIN, XMAX)

    # bank 0: moderate coefficients written through the port (overwrites the mif content)
    w = coef_writes(0, [rnd.randint(-(1 << 14), (1 << 14) - 1) for _ in range(TAPS)])
    # one idle frame per write batch: writes need the bank not to be in use, so do them
    # before the first sample (bank 1 content from the mif is overwritten later)
    for i in range(0, len(w), 1):
        dut.cw_en.value, dut.cw_bank.value, dut.cw_addr.value = 1, w[i][0], w[i][1]
        dut.cw_data.value = w[i][2] & 0x3FFFF
        model.write(*w[i])
        await RisingEdge(dut.clk)
    dut.cw_en.value = 0
    for n in range(160):                           # bank 0, shifts 0..7
        await drv.frame(rx(), 0, (n // 8) % 8)
    # write bank 1 (full-range coefficients: saturates) while bank 0 plays, then switch
    wr = coef_writes(1, [rnd.randint(-(1 << 17), (1 << 17) - 1) for _ in range(TAPS)])
    for n in range(40):
        await drv.frame(rx(), 0, rnd.randint(0, 7), writes=wr)
    assert not wr, "bank 1 not fully written during the frames"
    for n in range(160):                           # bank 1 active
        await drv.frame(rx(), 1, rnd.randint(0, 7))
    # now rewrite bank 0 while bank 1 plays, switch back
    wr = coef_writes(0, [rnd.randint(-(1 << 16), (1 << 16) - 1) for _ in range(TAPS)])
    for n in range(40):
        await drv.frame(rx(), 1, rnd.randint(0, 7), writes=wr)
    for n in range(120):
        await drv.frame(rx(), 0, rnd.randint(0, 7))
    # extremes: all coefficients -2^17 and input -2^(dw-1) / +max: positive then negative saturation
    wr = coef_writes(1, [-(1 << 17)] * TAPS)
    for n in range(40):
        await drv.frame(XMIN, 0, 0, writes=wr)
    for n in range(TAPS + 8):
        await drv.frame(XMIN, 1, 0)
    for n in range(TAPS + 8):
        await drv.frame(XMAX, 1, 0)
    for n in range(TAPS + 8):
        await drv.frame(XMAX if n & 1 else XMIN, 1, 7)
    await drv.flush()
    bad = drv.mismatches()
    for e in drv.exp:
        nsat[0 if e in (XMIN, XMAX) else 1] += 1
    assert not bad, "%d mismatches, first at sample %d: rtl %d model %d" % (
        len(bad), bad[0], drv.outs[bad[0] + 1], drv.exp[bad[0]])
    assert nsat[0] > 20 and nsat[1] > 100, "stimulus must cover saturated and unsaturated outputs"
    dut._log.info("cab_fir DW=%d TAPS=%d LANES=%d: %d samples bit-exact to the model "
                  "(%d saturated, %d not), frame = %d clocks, bank switches 0>1>0>1",
                  DW, TAPS, LANES, len(drv.exp) - 1, nsat[0], nsat[1], MIN_FRAME)


@cocotb.test()
async def test_impulse(dut):
    """Independent of the model: y[k] = sat(A * h[k] >> (17 + shift)) for an impulse A."""
    if TAPS >= 2048:
        return                                     # done at full size in test_full
    await setup(dut)
    rnd = random.Random(99 + DW)
    model = mif_model()
    drv = Drv(dut, model, MIN_FRAME + 3)
    for bank, shift, a_amp in ((0, 0, (1 << (DW - 2)) + 12345 % (1 << (DW - 2))),
                               (1, 5, -(1 << (DW - 2)) - 321),
                               (0, 2, XMAX)):
        h = [rnd.randint(-(1 << 17), (1 << 17) - 1) for _ in range(TAPS)]
        # load while the other bank is the active one (nothing is running)
        for a, c in enumerate(h):
            dut.cw_en.value, dut.cw_bank.value, dut.cw_addr.value = 1, bank, a
            dut.cw_data.value = c & 0x3FFFF
            await RisingEdge(dut.clk)
        dut.cw_en.value = 0
        base = len(drv.outs)
        nz = TAPS + 2                              # flush the history left by the previous test / round
        for _ in range(nz):
            await drv.frame(0, bank, shift)        # the model is not used for the check below
        await drv.frame(a_amp, bank, shift)        # impulse at frame base+nz = n0
        for k in range(TAPS + 6):
            await drv.frame(0, bank, shift)
        n0 = base + nz
        # data_out in frame n holds y[n-1]; y[n0 + k] sits in frame n0 + k + 1
        for k in range(TAPS):
            want = max(XMIN, min(XMAX, (a_amp * h[k]) >> (17 + shift)))
            got = drv.outs[n0 + k + 1]
            assert got == want, "impulse (bank %d shift %d): y[n0+%d] = %d, expected %d" % (bank, shift, k, got, want)
        for k in range(TAPS, TAPS + 5):
            assert drv.outs[n0 + k + 1] == 0, "impulse response must end after TAPS samples"
        assert drv.outs[n0] == 0, "no output before the impulse"
        # keep the model in sync for the next round (it only tracks writes via drv): rebuild
        model.bank[bank][:] = h
    dut._log.info("cab_fir DW=%d TAPS=%d: impulse response = coefficients (>> 17+shift) for 3 impulses / "
                  "banks / shifts, exact", DW, TAPS)


@cocotb.test()
async def test_latency(dut):
    """Smallest frame length (clocks from start to the next start) that gives correct results."""
    await setup(dut)
    rnd = random.Random(7)
    model = mif_model() if TAPS >= 2048 else CabFir(DW, TAPS)
    if TAPS < 2048:
        for a in range(TAPS):
            c = rnd.randint(-(1 << 15), (1 << 15) - 1)
            dut.cw_en.value, dut.cw_bank.value, dut.cw_addr.value = 1, 0, a
            dut.cw_data.value = c & 0x3FFFF
            model.write(0, a, c)
            await RisingEdge(dut.clk)
        dut.cw_en.value = 0
    ok = {}
    for F in range(TPL + 2, TPL + 12):
        drv = Drv(dut, model, F)
        await drv.frame(rnd.randint(XMIN, XMAX), 0, 1)            # (its y[n-1] belongs to the previous F)
        for _ in range(24):
            await drv.frame(rnd.randint(XMIN, XMAX), 0, rnd.randint(0, 3))
        # frame m's data_out is y[m-1]; frames 2.. were computed entirely with frame length F
        ok[F] = all(drv.outs[m + 1] == drv.exp[m] for m in range(1, 24))
    good = [F for F in sorted(ok) if ok[F]]
    first = good[0]
    dut._log.info("cab_fir TAPS=%d LANES=%d: correct from a frame length of %d clocks (TAPS/LANES + %d); "
                  "result register loaded %d clocks after the start edge. ok per F: %s",
                  TAPS, LANES, first, first - TPL, first - 1, ok)
    assert first == TPL + 7 and all(F >= first for F in good) and len(good) == len(ok) - (first - (TPL + 2)), ok
    assert first <= 14 or TAPS != 16, "TAPS=16 must fit the 16-clock frames of the chain tests"


@cocotb.test(skip=TAPS < 2048)
async def test_full(dut):
    await setup(dut)
    coefs, shift = cab_coefs.slot_coefs(0)
    mif = cab_coefs.read_mif(MIF)
    assert len(mif) == 2 * TAPS and not any(mif[TAPS:]), "mif: bank 0 words, then bank 1 zeros"
    mif = mif[:TAPS]
    assert list(coefs) == mif, "fpga/ip/cab_default.mif is not the current build of cabinet 0 (run tools/cab_coefs.py)"
    assert len(mif) == TAPS
    model = mif_model()
    rnd = random.Random(2048)

    # 1. impulse over all taps (frames of 528 clocks): output = default coefficients >> (17 + shift)
    drv = Drv(dut, model, TPL + 16)
    amp = 1 << (DW - 3)
    await drv.frame(amp, 0, shift)
    for _ in range(TAPS + 3):
        await drv.frame(0, 0, shift)
    for k in range(TAPS):
        want = max(XMIN, min(XMAX, (amp * mif[k]) >> (17 + shift)))
        assert drv.outs[k + 1] == want, "impulse: y[%d] = %d, expected %d" % (k, drv.outs[k + 1], want)
    assert all(v == 0 for v in drv.outs[TAPS + 1:]), "impulse response must end after 2048 taps"
    assert not drv.mismatches()
    dut._log.info("cab_fir full: impulse response over all %d taps equals the default .mif (shift %d), exact",
                  TAPS, shift)

    # 2. real timing: 1024 clocks per sample, random full-scale input, then a bank switch
    drv = Drv(dut, model, 1024)
    for n in range(160):
        await drv.frame(rnd.randint(XMIN, XMAX), 0, shift)
    for n in range(40):                                              # silence: the tail rings out
        await drv.frame(0, 0, shift)
    for n in range(20):                                              # other shifts (saturation)
        await drv.frame(rnd.randint(XMIN, XMAX), 0, rnd.randint(0, 7))
    wr = [(1, a, rnd.randint(-(1 << 17), (1 << 17) - 1)) for a in (0, 1, 2, 3, 5, 512, 513, 1000, 1023, 1024, 2047)]
    for n in range(20):
        await drv.frame(rnd.randint(XMIN, XMAX), 0, shift, writes=wr)
    assert not wr
    for n in range(60):                                              # bank 1 (few non-zero taps)
        await drv.frame(rnd.randint(XMIN, XMAX), 1, rnd.randint(0, 4))
    for n in range(40):                                              # and back to bank 0
        await drv.frame(rnd.randint(XMIN, XMAX), 0, shift)
    await drv.flush()
    bad = drv.mismatches()
    nsat = sum(1 for e in drv.exp if e in (XMIN, XMAX))
    assert not bad, "%d mismatches, first at sample %d: rtl %d model %d" % (
        len(bad), bad[0], drv.outs[bad[0] + 1], drv.exp[bad[0]])
    dut._log.info("cab_fir DW=%d TAPS=%d LANES=%d: %d samples at 1024 clocks bit-exact to the model "
                  "(%d saturated), default .mif, bank switch", DW, TAPS, LANES, len(drv.exp) - 1, nsat)
