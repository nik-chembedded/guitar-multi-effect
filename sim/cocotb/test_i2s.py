"""
test_i2s.py - cocotb tests for i2s_core (v2 step B2, FPGA = I2S master).

A Python model of the WM8731 in slave mode (I2S, 24-bit) is attached to the
pins: it drives ADCDAT on BCLK falling edges and samples DACDAT on BCLK rising
edges, with the I2S one-bit delay after each LRCLK edge.
"""
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, RisingEdge

CLK_NS = 20                       # 49.152 MHz in hardware; the period is irrelevant here


def s24(v):
    return v - (1 << 24) if v & (1 << 23) else v


class CodecSlave:
    """WM8731 slave: LRCLK = 0 -> left. Slot 0 after an LRCLK edge is the I2S delay."""

    def __init__(self, dut, adc_words):
        self.dut = dut
        self.adc = list(adc_words)          # [(left, right), ...] sent in order
        self.dac = []                       # captured [(left, right), ...]
        self.frames_sent = 0

    async def run(self):
        d = self.dut
        lr_prev, slot, word_out, cur, dac_l = None, 0, 0, 0, 0
        while True:
            await FallingEdge(d.bclk)
            lr = int(d.lrclk.value)
            if lr != lr_prev:                         # new channel
                slot = 0
                if lr == 0:                           # new frame starts with left
                    pair = self.adc[self.frames_sent] if self.frames_sent < len(self.adc) else (0, 0)
                    self.frames_sent += 1
                    self.pair = pair
                word_out = self.pair[lr]
                lr_prev = lr
            else:
                slot += 1
            d.adcdat.value = (word_out >> (24 - slot)) & 1 if 1 <= slot <= 24 else 0
            await RisingEdge(d.bclk)
            if 1 <= slot <= 24:
                cur = (cur << 1) | int(d.dacdat.value)
                if slot == 24:
                    if lr == 0:
                        dac_l = cur
                    else:
                        self.dac.append((dac_l, cur))
                    cur = 0


async def setup(dut):
    Clock(dut.clk, CLK_NS, unit="ns").start()
    dut.rst.value = 1
    dut.adcdat.value = 0
    dut.tx_left.value = 0
    dut.tx_right.value = 0
    await ClockCycles(dut.clk, 4)
    dut.rst.value = 0


@cocotb.test()
async def test_clocks(dut):
    """BCLK = clk/16 (50 % duty), LRCLK = clk/1024, strobes once per frame, LRCLK edges on BCLK falling."""
    await setup(dut)
    await ClockCycles(dut.clk, 2048)
    hist = {"bclk": [], "lrclk": [], "sample_tick": [], "half_tick": []}
    for i in range(4096):
        await RisingEdge(dut.clk)
        for k in hist:
            hist[k].append(int(getattr(dut, k).value))

    def rises(v):
        return [i for i in range(1, len(v)) if v[i] and not v[i - 1]]

    def falls(v):
        return [i for i in range(1, len(v)) if not v[i] and v[i - 1]]
    b, l = rises(hist["bclk"]), rises(hist["lrclk"])
    assert {b[i + 1] - b[i] for i in range(len(b) - 1)} == {16}, "BCLK period is not 16 clocks"
    assert sum(hist["bclk"][b[0]:b[0] + 16]) == 8, "BCLK duty cycle is not 50 %"
    assert {l[i + 1] - l[i] for i in range(len(l) - 1)} == {1024}, "LRCLK period is not 1024 clocks"
    assert sum(hist["lrclk"][l[0]:l[0] + 1024]) == 512, "LRCLK duty cycle is not 50 %"
    bf = set(falls(hist["bclk"]))
    assert all(e in bf for e in l + falls(hist["lrclk"])), "LRCLK must change with BCLK falling edges"
    st, ht = rises(hist["sample_tick"]), rises(hist["half_tick"])
    assert {st[i + 1] - st[i] for i in range(len(st) - 1)} == {1024}
    assert all(sum(hist["sample_tick"][s:s + 3]) == 1 for s in st), "sample_tick is not 1 clock wide"
    assert all((h - s) % 1024 == 512 for s in st for h in ht), "half_tick is not half a frame after sample_tick"
    dut._log.info("BCLK = clk/16, LRCLK = clk/1024, strobes 512 apart: OK")


@cocotb.test()
async def test_receive(dut):
    """24-bit stereo words sent by the codec arrive bit-exact on rx_left/rx_right."""
    await setup(dut)
    rnd = random.Random(5)
    words = [(rnd.getrandbits(24), rnd.getrandbits(24)) for _ in range(40)]
    words[3] = (0x800000, 0x7FFFFF)                 # full-scale extremes
    words[4] = (0x000001, 0xFFFFFF)
    codec = CodecSlave(dut, words)
    cocotb.start_soon(codec.run())
    got = []
    while len(got) < 36:
        await RisingEdge(dut.sample_tick)
        await RisingEdge(dut.clk)
        got.append((int(dut.rx_left.value), int(dut.rx_right.value)))
    lat = next(k for k in range(4) if got[k + 2] == words[2])
    bad = [n for n in range(2, 34) if got[n + lat] != words[n]]
    assert not bad, "rx mismatch at frame %d: got %s expected %s" % (bad[0], got[bad[0] + lat], words[bad[0]])
    dut._log.info("receive: 32 stereo frames bit-exact, latency %d frame(s)", lat)


@cocotb.test()
async def test_transmit(dut):
    """Words written to tx_left/tx_right appear bit-exact in the I2S stream."""
    await setup(dut)
    rnd = random.Random(6)
    words = [(rnd.getrandbits(24), rnd.getrandbits(24)) for _ in range(40)]
    words[5] = (0x800000, 0x7FFFFF)
    codec = CodecSlave(dut, [])
    cocotb.start_soon(codec.run())
    for n in range(40):                              # new pair each frame, after sample_tick
        await RisingEdge(dut.sample_tick)
        dut.tx_left.value = words[n][0]
        dut.tx_right.value = words[n][1]
    await ClockCycles(dut.clk, 3 * 1024)
    dac = codec.dac
    lat = next(k for k in range(6) if dac[k + 2] == words[2])
    bad = [n for n in range(2, 36) if dac[n + lat] != words[n]]
    assert not bad, "tx mismatch at frame %d: got %s expected %s" % (bad[0], dac[bad[0] + lat], words[bad[0]])
    dut._log.info("transmit: 34 stereo frames bit-exact, latency %d frame(s)", lat)


@cocotb.test()
async def test_loopback(dut):
    """rx -> tx loop through the core: what the codec sends comes back unchanged."""
    await setup(dut)
    rnd = random.Random(7)
    words = [(rnd.getrandbits(24), rnd.getrandbits(24)) for _ in range(30)]
    codec = CodecSlave(dut, words)
    cocotb.start_soon(codec.run())
    for _ in range(30):
        await RisingEdge(dut.sample_tick)
        await RisingEdge(dut.clk)
        dut.tx_left.value = dut.rx_left.value
        dut.tx_right.value = dut.rx_right.value
    await ClockCycles(dut.clk, 3 * 1024)
    dac = codec.dac
    lat = next(k for k in range(8) if dac[k + 2] == words[2])
    assert all(dac[n + lat] == words[n] for n in range(2, 24)), "loopback mismatch"
    dut._log.info("loopback ADC -> DAC bit-exact, latency %d frame(s)", lat)
