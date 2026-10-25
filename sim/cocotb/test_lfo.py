"""
test_lfo.py - nco_lfo (v2 step D1): the generated LFO against lfo_model.py.

* every shape at several rates: output bit-exact to the model on every sample,
  with the phase continuing across rate and shape changes (no jumps);
* frequency: rate -> Hz within one phase step (48000 / 2^32 = 11 uHz, from the
  model, which the RTL matches) and the measured period at 20 Hz;
* sine within 1e-4 of sin() over the whole period.
"""
import math

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, ReadOnly, RisingEdge

import lfo_model as m

RATES = [500, 700, 1000, 1200, 1500, 1, 37, 1234, 2000, 65535]


class Lfo:
    def __init__(self, dut):
        self.dut = dut
        self.phase = 0                     # model phase (ticks since start)

    async def set(self, rate, shape):
        await RisingEdge(self.dut.clk)         # (leave the read-only phase of tick())
        self.dut.rate.value = rate
        self.dut.shape.value = shape
        self.rate, self.shape = rate, shape
        await ClockCycles(self.dut.clk, 3)     # inc register follows the rate

    async def tick(self):
        """One sample: returns (rtl, model) LFO output for this sample."""
        d = self.dut
        await RisingEdge(d.clk)
        d.tick.value = 1
        await RisingEdge(d.clk)                # phase += inc on this edge
        d.tick.value = 0
        self.phase = (self.phase + m.inc(self.rate)) & 0xFFFFFFFF
        await RisingEdge(d.clk)                # lfo register follows the phase
        await ReadOnly()
        return int(d.lfo.value), m.wave(self.phase, self.shape)


@cocotb.test()
async def test_lfo(dut):
    Clock(dut.clk, 10, unit="ns").start()
    dut.tick.value = 0
    lfo = Lfo(dut)
    await lfo.set(500, m.SINE)
    n = 0
    for rate in RATES:
        for shape in (m.SINE, m.TRIANGLE, m.SAW, m.SQUARE):
            await lfo.set(rate, shape)
            for _ in range(300):
                got, exp = await lfo.tick()
                assert got == exp, "rate %d shape %d sample %d: rtl %d model %d" % (rate, shape, n, got, exp)
                n += 1
    dut._log.info("%d samples bit-exact (%d rates x 4 shapes, phase continuous)", n, len(RATES))

    # measured period at 20 Hz: 2400 samples between upward mid-level crossings
    await lfo.set(2000, m.SAW)
    prev, wraps = None, []
    for i in range(5000):
        got, _ = await lfo.tick()
        if prev is not None and prev < 32768 <= got:
            wraps.append(i)
        prev = got
    periods = [b - a for a, b in zip(wraps, wraps[1:])]
    assert periods and all(p in (2399, 2400, 2401) for p in periods), "20 Hz periods %s" % periods
    dut._log.info("20 Hz: periods %s samples (2400 expected)", periods)

    step = 48000 / 2 ** 32
    for rate in (1, 100, 500, 700, 1000, 1200, 1500, 2000):
        f = m.frequency(rate)
        assert abs(f - rate / 100) < step, "rate %d -> %.7f Hz" % (rate, f)
    err = max(abs((m.sine16(p) - 32768) / 32767 - math.sin(2 * math.pi * p / 2 ** 32))
              for p in range(0, 2 ** 32, 2 ** 32 // 65536))
    assert err < 1e-4, "sine error %.2e" % err
    dut._log.info("frequency within %.1f uHz of the setting; sine max error %.1e of full scale", step * 1e6, err)
