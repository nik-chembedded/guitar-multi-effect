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
SETTLE = 1800            # frames: parameter smoothing + effect fade-in (step C)


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
    """dac (L, R) must be fn(left input, 24-bit) on both channels, at some latency."""
    x = [s24(l) for l, _ in words]                            # 24-bit effect input (step C)
    y = fn(x)
    for lat in range(1, 16):
        ok = all(s24(dac[n + lat][0]) == y[n] and s24(dac[n + lat][1]) == y[n]
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
    dut._log.info("boot OK (%d codec writes), bypass end-to-end bit-exact at 24 bits, latency %d frames",
                  len(INIT), lat)


@cocotb.test()
async def test_overdrive_via_hps(dut):
    """Effect registers written over the bridge change the audio exactly like the reference model."""
    words = audio_words(N_FRAMES, 2)
    i2c, codec, host = await boot(dut, words)
    await wait_init(dut, host)
    for addr, val in ((1, 3000), (2, 4), (0, 0x0001)):         # drive, gain, enable OD
        await host.write(addr, val)
    # the drive is smoothed (exact after ~1500 samples) and OD fades in over 256
    await ClockCycles(dut.clk, SETTLE * 1024)
    codec.adc, codec.dac, codec.frames_sent = words, [], 0
    await ClockCycles(dut.clk, (N_FRAMES + 4) * 1024)
    lat = expect_mono(codec.dac, words, lambda x: golden.overdrive(x, 3000, 4, dw=24))
    # peak meters decay slowly (1/256 per sample), so the output meter may still
    # hold part of the earlier dry full-scale peak: check it caught the 12000 peaks
    lvl_out = await host.read(0x13)
    lvl_in = await host.read(0x12)
    assert lvl_out >= 11000, "output level register %d" % lvl_out
    assert lvl_in >= 28000, "input level register %d (input is near full scale)" % lvl_in
    dut._log.info("overdrive set over the bridge, output bit-exact (24-bit), latency %d; levels in %d / out %d",
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
    # muted output: the peak meter must decay all the way to 0 (it used to stick at 255)
    await ClockCycles(dut.clk, 2000 * 1024)                   # ~256*(1+1/2+..+1/127) + 255 = 1650 frames
    assert await host.read(0x13) == 0, "output level did not decay to 0"
    n0 = len(i2c.transfers)
    await host.write(0x15, (0x02 << 9) | 0x079)                           # CODEC: R2 = 0x079
    for _ in range(100):                                                  # one write takes ~0.3 ms at 100 kHz
        await ClockCycles(dut.clk, 500)
        if await host.read(0x15) & 1 == 0:
            break
    assert await host.read(0x15) == 0, "CODEC register: still busy or NAK"
    assert i2c.transfers[n0:] == [to_bytes(2, 0x079)]
    dut._log.info("mute OK, meter decays to 0, host codec write R2=0x079 on the I2C bus")


@cocotb.test()
async def test_cabinet(dut):
    """Cabinet (step D3) through the whole design: enable bit 6 + CAB_CTRL over the bridge, the default
    2048-tap cabinet (cab_default.mif, shift from its header) answers an I2S impulse with its
    coefficients >> (17+shift); writes to the active bank are ignored; a few coefficients loaded into bank 1
    through CAB_ADDR / CAB_DATA_LO / CAB_DATA_HI play after the bank switch."""
    import re
    import sys
    root = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
    sys.path.insert(0, os.path.join(root, "tools"))
    import cab_coefs
    mif = os.path.join(root, "fpga", "ip", "cab_default.mif")
    h0 = cab_coefs.read_mif(mif)[:2048]
    sh0 = int(re.search(r"output shift = (\d)", open(mif).read()).group(1))
    sh1 = 4
    amp, n_imp, n_chk = 1 << 20, 5, 400

    def sat24(v):
        return max(-(1 << 23), min((1 << 23) - 1, v))

    words = [(0, 0)] * 24
    i2c, codec, host = await boot(dut, words)
    await wait_init(dut, host)

    async def impulse(nframes):
        stream = [(0, 0)] * nframes
        stream[n_imp] = (amp, 0)
        codec.adc, codec.dac, codec.frames_sent = stream, [], 0
        await ClockCycles(dut.clk, (nframes + 4) * 1024)
        return [s24(l) for l, _ in codec.dac]

    # cabinet 0 on: enable bit 6, shift 0 = sh0, bank 0; the fade-in takes 256 frames
    await host.write(0x1B, (sh1 << 4) | (sh0 << 1) | 0)
    await host.write(0, 0x0040)
    assert await host.read(0x1B) == (sh1 << 4) | (sh0 << 1)
    await ClockCycles(dut.clk, 300 * 1024)
    # writes into the active bank are ignored: CAB_ADDR = bank 0 tap 0, 4 coefficients
    await host.write(0x1C, 0x000)
    for v in (0x1FFFF, 0x20000, 0x00001, 0x3FFFF):
        await host.write(0x1D, v & 0xFFFF)
        await host.write(0x1E, v >> 16)
    y = await impulse(n_chk + 24)
    want = [sat24((amp * c) >> (17 + sh0)) for c in h0[:n_chk]]
    # the response starts (dry latency + 1 cabinet sample) after the impulse: find the offset
    # (checked against the dry latency at the end), then compare all taps
    offs = [o for o in range(1, 16) if y[n_imp + o:n_imp + o + n_chk] == want]
    assert len(offs) == 1, "default cabinet: no exact match of %d taps at any latency; y[%d:] = %s want %s" % (
        n_chk, n_imp, y[n_imp:n_imp + 12], want[:6])
    off = offs[0]
    assert any(want) and max(abs(v) for v in want) > 1000
    dut._log.info("cabinet 0 (default .mif, shift %d): impulse response over %d taps equals the coefficients "
                  ">> %d, starting %d frames after the impulse; writes to the active bank ignored", sh0, n_chk,
                  17 + sh0, off)

    # bank 1: a few coefficients (CAB_ADDR bit 11 = bank), then switch
    taps = {0: [100000, -131072, 77777, 5], 40: [131071], 300: [-90000, 12345]}
    h1 = [0] * 2048
    for a, cs in taps.items():
        await host.write(0x1C, 0x800 | a)
        for k, c in enumerate(cs):                                     # pointer auto-increments
            await host.write(0x1D, c & 0xFFFF)
            await host.write(0x1E, (c >> 16) & 3)
            h1[a + k] = c
    await host.write(0x1B, (sh1 << 4) | (sh0 << 1) | 1)
    await ClockCycles(dut.clk, 300 * 1024)                             # fade out 128, switch, fade in 128
    y = await impulse(n_chk + 24)
    want = [sat24((amp * c) >> (17 + sh1)) for c in h1[:n_chk]]
    got = y[n_imp + off: n_imp + off + n_chk]
    assert got == want, "bank 1: first mismatch at tap %d" % next(i for i in range(n_chk) if got[i] != want[i])
    assert sum(1 for v in want if v) == 7
    dut._log.info("bank 1 loaded over CAB_ADDR/DATA_LO/DATA_HI (7 coefficients, shift %d), switched: "
                  "impulse response exact over %d taps", sh1, n_chk)

    # cabinet off again: the stage is a plain connection, the dry latency is one frame less than 'off'
    await host.write(0, 0x0000)
    await ClockCycles(dut.clk, 300 * 1024)
    y = await impulse(24)
    lat = next(i for i, v in enumerate(y) if v) - n_imp
    assert y[n_imp + lat] == amp and lat + 1 == off, "dry latency %d, cabinet response offset %d" % (lat, off)
    dut._log.info("cabinet off: dry latency %d frames (cabinet adds exactly 1 when on)", lat)


@cocotb.test()
async def test_reverb_regs(dut):
    """Reverb room presets / custom size and damp over the bridge: REVERB_TYPE 0..3 select the
    presets, 4 (and 5..15) the registers 0x1F / 0x20 (damp = low byte); the chain gets the value
    smoothed (param_smooth, time constant 128 frames; its exactness is tested in test_smooth)."""
    # last test of the file: the cabinet FIR history of test_cabinet must not be disturbed
    i2c, codec, host = await boot(dut, audio_words(N_FRAMES, 4))
    await wait_init(dut, host)
    rooms = ((45875, 100), (52429, 80), (57672, 60), (61604, 40))
    await host.write(0x1F, 0xBEEF)
    await host.write(0x20, 0x1234)
    for t, exp in list(enumerate(rooms)) + [(4, (0xBEEF, 0x34)), (7, (0xBEEF, 0x34)), (3, rooms[3])]:
        await host.write(0x0E, t)
        await ClockCycles(dut.clk, 4)
        got = (int(dut.rev_size.value), int(dut.rev_damp.value))
        assert got == exp, "REVERB_TYPE %d: (size, damp) = %s, expected %s" % (t, got, exp)
    s0, d0 = int(dut.u_fx.reverb_size.value), int(dut.u_fx.reverb_damp.value)
    await host.write(0x0E, 4)
    await host.write(0x1F, 50000)
    await host.write(0x20, 77)
    await ClockCycles(dut.clk, 200 * 1024)      # 200 frames: 1 - (127/128)^200 = 79 % of the way
    size, damp = int(dut.u_fx.reverb_size.value), int(dut.u_fx.reverb_damp.value)
    assert abs(50000 - s0) > 5000, "test setup: the smoothed size must start away from 50000"
    assert 0.1 * abs(50000 - s0) < abs(50000 - size) < 0.3 * abs(50000 - s0),         "smoothed size at the chain: %d -> %d (target 50000)" % (s0, size)
    assert abs(77 - damp) <= 0.3 * abs(77 - d0), "smoothed damp at the chain: %d -> %d (target 77)" % (d0, damp)
    dut._log.info("reverb presets 0..3, custom (4, 5..15) OK; smoothed size %d -> %d (target 50000), "
                  "damp %d -> %d (target 77) after 200 frames", s0, size, d0, damp)
