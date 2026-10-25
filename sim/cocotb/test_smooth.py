"""
test_smooth.py - param_smooth (v2 step C): one-pole parameter smoothing.
Bit-exact against a Python model, reaches every target exactly, monotonic,
time constant 128 samples.
"""
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, ReadOnly, RisingEdge

K, FRAC, W = 7, 8, 16


class Model:
    def __init__(self):
        self.y = 0

    def tick(self, target):
        diff = (target << FRAC) - self.y
        step = diff >> K
        if step == 0 and diff != 0:
            step = 1 if diff > 0 else -1
        self.y += step
        return self.y >> FRAC


async def tick(dut):
    await RisingEdge(dut.clk)
    dut.tick.value = 1
    await RisingEdge(dut.clk)
    dut.tick.value = 0
    await ReadOnly()
    return int(dut.value.value)


@cocotb.test()
async def test_smooth(dut):
    """Steps up / down / small / random: bit-exact to the model, exact final value."""
    Clock(dut.clk, 10, unit="ns").start()
    dut.rst.value = 1
    dut.tick.value = 0
    dut.target.value = 0
    await ClockCycles(dut.clk, 3)
    dut.rst.value = 0
    m = Model()
    rnd = random.Random(3)
    targets = [65535, 1000, 1005, 0, 255, 128] + [rnd.getrandbits(16) for _ in range(6)]
    for t in targets:
        await RisingEdge(dut.clk)
        dut.target.value = t
        start = m.y >> FRAC
        seq = []
        for n in range(1800):
            got = await tick(dut)
            exp = m.tick(t)
            assert got == exp, "target %d, tick %d: got %d model %d" % (t, n, got, exp)
            seq.append(got)
        assert seq[-1] == t, "target %d not reached exactly (%d)" % (t, seq[-1])
        diffs = [b - a for a, b in zip([start] + seq, seq)]
        assert all(d >= 0 for d in diffs) or all(d <= 0 for d in diffs), "not monotonic for %d" % t
        if abs(t - start) > 10000:                           # time constant ~128 samples
            frac = (seq[127] - start) / (t - start)
            assert 0.55 < frac < 0.70, "after 128 samples %.2f of the step (expected ~0.63)" % frac
            settle = next(i for i, v in enumerate(seq) if v == t)
            dut._log.info("step %5d -> %5d: 63%% after 128 samples (%.2f), exact after %d samples",
                          start, t, frac, settle + 1)
    dut._log.info("%d targets bit-exact to the model and reached exactly", len(targets))
