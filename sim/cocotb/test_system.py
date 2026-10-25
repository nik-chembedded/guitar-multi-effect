"""
test_system.py - end-to-end test of gme_core: the whole v2 design without
the PLL and the HPS, with all three external parts modelled in Python:

  WM8731 audio (I2S slave)   <- test_i2s.CodecSlave
  WM8731 control (I2C slave) <- test_codec.I2cSlave
  HPS (lightweight bridge)   <- test_avmm.AvmmHost (Avalon-MM master)

Power-up -> codec init over I2C -> effect registers over the bridge -> audio through
I2S and the effect chain.
"""
import os
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge

import golden
from test_codec import INIT, I2cSlave, to_bytes
from test_avmm import VERSION, AvmmHost
from test_i2s import CodecSlave

N_FRAMES = 60


def s24(v):
    return v - (1 << 24) if v & (1 << 23) else v


async def boot(dut, adc_words):
    Clock(dut.clk, 20, unit="ns").start()
    dut.rst.value = 1
    dut.pll_locked.value = 1
    dut.adcdat.value = 0
    dut.sda_in.value = 1
    i2c = I2cSlave(dut)
    cocotb.start_soon(i2c.run())
    codec = CodecSlave(dut, adc_words)
    cocotb.start_soon(codec.run())
    host = AvmmHost(dut)
    await ClockCycles(dut.clk, 5)
    dut.rst.value = 0
    return i2c, codec, host


async def wait_init(dut, host):
    """Poll STATUS until the codec init is done."""
    for _ in range(200):
        status = await host.read(0x11)
        if status & 1:
            return status
        await ClockCycles(dut.clk, 5000)
    raise AssertionError("codec init did not finish")


def audio_words(n, seed):
    rnd = random.Random(seed)
    return [(rnd.randint(-(1 << 23), (1 << 23) - 1) & 0xFFFFFF, rnd.getrandbits(24)) for _ in range(n)]


def expect_mono(dac, words, fn):
    """dac (L, R) must be fn(left input 16-bit) << 8 on both channels, at some latency."""
    x = [s24(l) >> 8 for l, _ in words]                       # 16-bit effect input
    y = fn(x)
    for lat in range(1, 16):
        ok = all(s24(dac[n + lat][0]) == y[n] * 256 and s24(dac[n + lat][1]) == y[n] * 256
                 for n in range(10, len(words) - 10) if n + lat < len(dac))
        if ok:
            return lat
    raise AssertionError("output does not match: first frames %s vs %s" % (dac[10:14], y[10:14]))


@cocotb.test()
async def test_boot_and_bypass(dut):
    """Codec init sequence, STATUS/VERSION over the bridge, then dry audio end to end."""
    words = audio_words(N_FRAMES, 1)
    i2c, codec, host = await boot(dut, words)
    status = await wait_init(dut, host)
    assert status & 0b111 == 0b101, "STATUS 0x%04X (init done, no NAK, PLL locked)" % status
    assert i2c.transfers[:len(INIT)] == [to_bytes(r, v) for r, v in INIT], "init sequence"
    assert await host.read(0x10) == VERSION
    # restart the audio stream now that the codec is configured
    codec.adc, codec.dac, codec.frames_sent = words, [], 0
    await ClockCycles(dut.clk, (N_FRAMES + 4) * 1024)
    lat = expect_mono(codec.dac, words, golden.bypass)
    dut._log.info("boot OK (%d codec writes), bypass end-to-end bit-exact at 16 bits, latency %d frames",
                  len(INIT), lat)


@cocotb.test()
async def test_overdrive_via_hps(dut):
    """Effect registers written over the bridge change the audio exactly like the reference model."""
    words = audio_words(N_FRAMES, 2)
    i2c, codec, host = await boot(dut, words)
    await wait_init(dut, host)
    for addr, val in ((1, 3000), (2, 4), (0, 0x0001)):         # drive, gain, enable OD
        await host.write(addr, val)
    codec.adc, codec.dac, codec.frames_sent = words, [], 0
    await ClockCycles(dut.clk, (N_FRAMES + 4) * 1024)
    lat = expect_mono(codec.dac, words, lambda x: golden.overdrive(x, 3000, 4))
    # peak meters decay slowly (1/256 per sample), so the output meter may still
    # hold part of the earlier dry full-scale peak: check it caught the 12000 peaks
    lvl_out = await host.read(0x13)
    lvl_in = await host.read(0x12)
    assert lvl_out >= 11000, "output level register %d" % lvl_out
    assert lvl_in >= 28000, "input level register %d (input is near full scale)" % lvl_in
    dut._log.info("overdrive set over the bridge, output bit-exact, latency %d; levels in %d / out %d",
                  lat, lvl_in, lvl_out)


@cocotb.test()
async def test_mute_and_codec_write(dut):
    """CONTROL mute silences the output; a host CODEC write reaches the I2C bus."""
    words = audio_words(N_FRAMES, 3)
    i2c, codec, host = await boot(dut, words)
    await wait_init(dut, host)
    await host.write(0x14, 0x0002)                                        # mute
    codec.adc, codec.dac, codec.frames_sent = words, [], 0
    await ClockCycles(dut.clk, 20 * 1024)
    assert all(l == 0 and r == 0 for l, r in codec.dac[3:]), "mute did not silence the output"
    n0 = len(i2c.transfers)
    await host.write(0x15, (0x02 << 9) | 0x079)                           # CODEC: R2 = 0x079
    for _ in range(100):                                                  # one write takes ~0.3 ms at 100 kHz
        await ClockCycles(dut.clk, 500)
        if await host.read(0x15) & 1 == 0:
            break
    assert await host.read(0x15) == 0, "CODEC register: still busy or NAK"
    assert i2c.transfers[n0:] == [to_bytes(2, 0x079)]
    dut._log.info("mute OK, host codec write R2=0x079 on the I2C bus")
