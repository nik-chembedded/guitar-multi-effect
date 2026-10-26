"""
test_avmm.py - cocotb tests for ctrl_avmm (v2, HPS control): the Avalon-MM
slave on the HPS lightweight bridge, the register file behind it and the
CODEC register.

AvmmHost plays the Avalon-MM bridge in hps_sys (what Linux reaches at
0xFF200000): byte addresses, register n at 4*n, 32-bit data. The test plays
the I2C master through the i2c_req/i2c_busy/i2c_done/i2c_nak handshake.
"""
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, ReadOnly, RisingEdge

EFFECT_REGS = ["effects_enable", "od_drive", "od_gain", "trem_wave", "trem_depth", "echo_time",
               "echo_repeat", "echo_level", "dist_mix", "dist_type", "chorus_level",
               "chorus_depth", "chorus_rate", "reverb_mix", "reverb_type"]
VERSION = 0x0208
DYN_GR_VALUE = 0x0ABC            # driven on the dyn_gr input (register 0x2C, read-only)
CODEC = 0x15


class AvmmHost:
    """Avalon-MM master: one access at a time, like the bridge (1 pending response)."""

    def __init__(self, dut):
        self.dut = dut
        dut.avs_read.value = 0
        dut.avs_write.value = 0
        dut.avs_address.value = 0
        dut.avs_writedata.value = 0
        dut.avs_byteenable.value = 0xF

    async def write(self, reg, value, byteenable=0xF):
        d = self.dut
        await RisingEdge(d.clk)
        d.avs_address.value = 4 * reg
        d.avs_writedata.value = value & 0xFFFFFFFF
        d.avs_byteenable.value = byteenable
        d.avs_write.value = 1
        await RisingEdge(d.clk)                        # write accepted on this edge
        assert int(d.avs_waitrequest.value) == 0, "waitrequest must stay low"
        d.avs_write.value = 0
        await ReadOnly()                               # registers updated by this edge

    async def write_bytes(self, reg, value, size, rnd):
        """value as byte (size 1) or halfword (size 2) stores, lowest address first,
        like CPython's struct '<I' on /dev/mem. Lanes not enabled carry garbage."""
        mask = (1 << (8 * size)) - 1
        for off in range(0, 4, size):
            lane = ((value >> (8 * off)) & mask) << (8 * off)
            garbage = rnd.getrandbits(32) & ~(mask << (8 * off)) & 0xFFFFFFFF
            await self.write(reg, lane | garbage, byteenable=((1 << size) - 1) << off)

    async def read(self, reg):
        d = self.dut
        await RisingEdge(d.clk)
        d.avs_address.value = 4 * reg
        d.avs_read.value = 1
        await RisingEdge(d.clk)                        # read accepted on this edge
        d.avs_read.value = 0
        for _ in range(4):
            await ReadOnly()                           # outputs after this edge
            if int(d.avs_readdatavalid.value):
                return int(d.avs_readdata.value)
            await RisingEdge(d.clk)
        raise AssertionError("no readdatavalid for register 0x%02X" % reg)


async def setup(dut):
    Clock(dut.clk, 20, unit="ns").start()
    dut.rst.value = 1
    dut.i2c_busy.value = 0
    dut.i2c_done.value = 0
    dut.i2c_nak.value = 0
    dut.status_in.value = 0x0005
    dut.level_in.value = 0x1234
    dut.level_out.value = 0x4321
    dut.dyn_gr.value = DYN_GR_VALUE
    h = AvmmHost(dut)
    await ClockCycles(dut.clk, 5)
    dut.rst.value = 0
    await ClockCycles(dut.clk, 2)
    return h


@cocotb.test()
async def test_version_status(dut):
    """VERSION, STATUS and the level registers read through the Avalon slave."""
    h = await setup(dut)
    for reg, exp in ((0x10, VERSION), (0x11, 0x0005), (0x12, 0x1234), (0x13, 0x4321)):
        v = await h.read(reg)
        assert v == exp, "register 0x%02X = 0x%08X, expected 0x%04X" % (reg, v, exp)
    dut._log.info("VERSION 0x%04X, STATUS / levels OK", VERSION)


@cocotb.test()
async def test_write_read_all(dut):
    """All 15 effect registers: write random 32-bit words, read back the low 16 bits."""
    h = await setup(dut)
    rnd = random.Random(1)
    vals = [rnd.getrandbits(32) for _ in EFFECT_REGS]
    for reg, v in enumerate(vals):
        await h.write(reg, v)
    for reg, v in enumerate(vals):
        got = await h.read(reg)
        assert got == v & 0xFFFF, "reg %d read 0x%08X, wrote 0x%08X" % (reg, got, v)
        assert int(getattr(dut, EFFECT_REGS[reg]).value) == v & 0xFFFF, "output %s" % EFFECT_REGS[reg]
    ext = [rnd.getrandbits(32) for _ in range(0x16, 0x30)]     # extension registers (step D)
    for i, v in enumerate(ext):
        await h.write(0x16 + i, v)
    bus = int(dut.ext.value)
    for i, v in enumerate(ext):
        if 0x16 + i == 0x2C:                                   # DYN_GR (D5): read-only meter, see test_dynamics_eq_regs
            assert await h.read(0x2C) == DYN_GR_VALUE and (bus >> (16 * i)) & 0xFFFF == 0
            continue
        assert await h.read(0x16 + i) == v & 0xFFFF, "ext register 0x%02X" % (0x16 + i)
        assert (bus >> (16 * i)) & 0xFFFF == v & 0xFFFF, "ext bus slice 0x%02X" % (0x16 + i)
    dut._log.info("15 effect + 25 extension registers written / read back (bits 31..16 ignored, read 0); "
                  "0x2C is read-only")


@cocotb.test()
async def test_reverb_regs(dut):
    """Reverb registers (D4): 0x0D mix and 0x0E type are effect registers, 0x1F REVERB_SIZE and
    0x20 REVERB_DAMP extension registers; each lands in its own slice of the ext bus."""
    h = await setup(dut)
    for reg, v in ((0x0D, 0x00AB), (0x0E, 4), (0x1F, 0xF5A1), (0x20, 0x003C)):
        await h.write(reg, v)
    assert int(dut.reverb_mix.value) == 0xAB and int(dut.reverb_type.value) == 4
    bus = int(dut.ext.value)
    ext = lambda r: (bus >> (16 * (r - 0x16))) & 0xFFFF
    assert ext(0x1F) == 0xF5A1 and ext(0x20) == 0x003C and ext(0x1E) == 0 and ext(0x21) == 0
    assert [await h.read(r) for r in (0x0D, 0x0E, 0x1F, 0x20)] == [0xAB, 4, 0xF5A1, 0x3C]
    dut._log.info("REVERB_MIX / TYPE / SIZE (0x1F) / DAMP (0x20) written and read back")


@cocotb.test()
async def test_dynamics_eq_regs(dut):
    """Dynamics / EQ registers (D5): 0x21 DYN_CTRL .. 0x27 COMP_MAKEUP and 0x28 EQ_ADDR .. 0x2B EQ_APPLY are
    ordinary read/write registers, each in its own slice of the ext bus (neighbours 0x20 and 0x2D untouched);
    0x2C DYN_GR reads the live dyn_gr input and ignores writes (no ext bus change, no side effect); every
    write of 0x21..0x2B gives one write event, the write to 0x2C does give one too (ignored by the core)."""
    h = await setup(dut)
    events = []

    async def monitor():
        while True:
            await RisingEdge(dut.clk)
            await ReadOnly()
            if int(dut.ext_we.value):
                events.append((int(dut.ext_wa.value), int(dut.ext_wd.value)))

    cocotb.start_soon(monitor())
    rnd = random.Random(21)
    vals = {r: rnd.getrandbits(16) for r in range(0x21, 0x2C)}
    for r, v in vals.items():
        await h.write(r, 0xCAFE0000 | v)
    bus = int(dut.ext.value)
    ext = lambda r: (bus >> (16 * (r - 0x16))) & 0xFFFF
    for r, v in vals.items():
        assert await h.read(r) == v, "register 0x%02X read back" % r
        assert ext(r) == v, "ext bus slice 0x%02X" % r
    assert ext(0x20) == 0 and ext(0x2C) == 0 and ext(0x2D) == 0, "neighbour slices must stay 0"
    assert [e[0] for e in events] == list(range(0x21, 0x2C)) and all(e[1] == vals[e[0]] for e in events),         "write events %s" % events
    # DYN_GR: live, read-only
    assert await h.read(0x2C) == DYN_GR_VALUE
    await RisingEdge(dut.clk)                # (leave the ReadOnly phase before driving an input)
    dut.dyn_gr.value = 0xFFFF
    assert await h.read(0x2C) == 0xFFFF, "DYN_GR must follow the input"
    await RisingEdge(dut.clk)
    dut.dyn_gr.value = 0
    assert await h.read(0x2C) == 0
    await RisingEdge(dut.clk)
    dut.dyn_gr.value = 0x1357
    n = len(events)
    await h.write(0x2C, 0xFFFF)
    await h.write(0x2C, 0x0000, byteenable=0x3)
    await ClockCycles(dut.clk, 3)
    assert await h.read(0x2C) == 0x1357, "DYN_GR is read-only"
    assert int(dut.ext.value) == int(bus) and [await h.read(r) for r in vals] == list(vals.values()),         "a write to 0x2C changed another register"
    assert all(e[0] == 0x2C for e in events[n:]), "write events %s" % events[n:]
    assert await h.read(0x10) == VERSION
    dut._log.info("DYN/EQ registers 0x21..0x2B read/write with write events, 0x2C live and read-only, VERSION 0x%04X", VERSION)


@cocotb.test()
async def test_level_regs(dut):
    """Output levels (D6): 0x2D OD_LEVEL and 0x2E DIST_LEVEL are ordinary 16-bit read/write registers (signed
    Q8 log2 units, the sign is kept: -1020 reads back 0xFC04), reset to 0 (unity), each in its own slice of the
    ext bus (neighbours 0x2C DYN_GR and 0x2F untouched), one write event each; VERSION 0x0208."""
    h = await setup(dut)
    events = []

    async def monitor():
        while True:
            await RisingEdge(dut.clk)
            await ReadOnly()
            if int(dut.ext_we.value):
                events.append((int(dut.ext_wa.value), int(dut.ext_wd.value)))

    cocotb.start_soon(monitor())
    assert await h.read(0x2D) == 0 and await h.read(0x2E) == 0, "levels reset to 0 (unity)"
    ext = lambda r: (int(dut.ext.value) >> (16 * (r - 0x16))) & 0xFFFF       # noqa: E731
    for od, di in ((-1020 & 0xFFFF, 512), (256, -256 & 0xFFFF), (0x8000, 0x7FFF)):
        await h.write(0x2D, 0xBEEF0000 | od)
        await h.write(0x2E, 0xBEEF0000 | di)
        assert await h.read(0x2D) == od and await h.read(0x2E) == di
        assert ext(0x2D) == od and ext(0x2E) == di and ext(0x2C) == 0 and ext(0x2F) == 0
    assert await h.read(0x2D) == 0x8000 and await h.read(0x2E) == 0x7FFF
    assert [e[0] for e in events] == [0x2D, 0x2E] * 3 and events[0][1] == (-1020 & 0xFFFF) and events[1][1] == 512, events
    assert await h.read(0x10) == VERSION == 0x0208
    dut._log.info("OD_LEVEL (0x2D) / DIST_LEVEL (0x2E) read/write with write events, reset 0, VERSION 0x%04X", VERSION)


@cocotb.test()
async def test_invalid_and_readonly(dut):
    """Unknown addresses read 0; writes to them and to read-only registers change nothing."""
    h = await setup(dut)
    await h.write(2, 0x1111)
    for reg in (0x0F, 0x30, 0x3F):
        await h.write(reg, 0xFFFF)
        assert await h.read(reg) == 0, "unknown register 0x%02X must read 0" % reg
    await h.write(0x10, 0xDEAD)
    assert await h.read(0x10) == VERSION, "VERSION is read-only"
    assert [int(getattr(dut, r).value) for r in EFFECT_REGS] == [0, 0, 0x1111] + [0] * 12, \
        "an invalid write changed an effect register"
    dut._log.info("unknown / read-only addresses ignored")


@cocotb.test()
async def test_control(dut):
    """CONTROL: bit1 mute is stored, bit0 gives one codec_init pulse."""
    h = await setup(dut)
    pulses = 0

    async def count():
        nonlocal pulses
        while True:
            await RisingEdge(dut.clk)
            await ReadOnly()
            pulses += int(dut.codec_init.value)

    cocotb.start_soon(count())
    await h.write(0x14, 0x0003)
    await ClockCycles(dut.clk, 5)
    assert pulses == 1, "codec_init pulses: %d" % pulses
    assert int(dut.mute.value) == 1 and await h.read(0x14) == 0x0002
    await h.write(0x14, 0x0000)
    assert int(dut.mute.value) == 0
    dut._log.info("CONTROL mute and codec re-init pulse OK")


@cocotb.test()
async def test_codec_write(dut):
    """CODEC register: I2C request with register/data, busy while it runs, NAK and drop flags."""
    h = await setup(dut)

    async def i2c_master(nak, cycles=300):
        await RisingEdge(dut.i2c_req)
        reg, data = int(dut.i2c_reg.value), int(dut.i2c_data.value)
        await RisingEdge(dut.clk)
        dut.i2c_busy.value = 1
        await ClockCycles(dut.clk, cycles)
        dut.i2c_busy.value = 0
        dut.i2c_nak.value = nak
        dut.i2c_done.value = 1
        await RisingEdge(dut.clk)
        dut.i2c_done.value = 0
        return reg, data

    m = cocotb.start_soon(i2c_master(0))
    await h.write(CODEC, (0x07 << 9) | 0x00A)                 # R7 = 0x00A
    assert await h.read(CODEC) & 1 == 1, "busy bit while the transfer runs"
    assert await m == (0x07, 0x00A), "codec write"
    await ClockCycles(dut.clk, 2)
    assert await h.read(CODEC) == 0, "idle, no NAK"

    m = cocotb.start_soon(i2c_master(1))
    await h.write(CODEC, (0x08 << 9) | 0x100)                 # 9-bit data, NAKed
    await h.write(CODEC, (0x09 << 9) | 0x001)                 # while busy: dropped
    assert await m == (0x08, 0x100)
    await ClockCycles(dut.clk, 2)
    assert await h.read(CODEC) == 0b110, "NAK and dropped flags"

    m = cocotb.start_soon(i2c_master(0, cycles=20))
    await h.write(CODEC, (0x09 << 9) | 0x001)                 # accepted: clears both flags
    assert await m == (0x09, 0x001)
    await ClockCycles(dut.clk, 2)
    assert await h.read(CODEC) == 0
    dut._log.info("codec writes forwarded (incl. 9-bit data); busy, NAK and dropped reported")


@cocotb.test()
async def test_byte_writes(dut):
    """Byte and halfword stores (garbage on the other lanes) act like one 32-bit store."""
    h = await setup(dut)
    rnd = random.Random(7)
    requests = []

    async def i2c_master():
        while True:
            await RisingEdge(dut.i2c_req)
            requests.append((int(dut.i2c_reg.value), int(dut.i2c_data.value)))
            await RisingEdge(dut.clk)
            dut.i2c_busy.value = 1
            await ClockCycles(dut.clk, 50)
            dut.i2c_busy.value = 0
            dut.i2c_done.value = 1
            await RisingEdge(dut.clk)
            dut.i2c_done.value = 0

    cocotb.start_soon(i2c_master())
    for size in (1, 2):
        for reg, v in ((1, 0x1234 + size), (5, 0xBEEF - size), (0, 0x0021)):
            await h.write_bytes(reg, v, size, rnd)
            assert await h.read(reg) == v, "reg %d after %d-byte stores" % (reg, size)
        await h.write(2, 0xAAAA)
        await h.write(2, 0x55, byteenable=0x1)                # low byte only
        assert await h.read(2) == 0xAA55
        await h.write(2, 0x1100, byteenable=0x2)              # high byte only
        assert await h.read(2) == 0x1155
        await h.write(2, 0xFFFF0000, byteenable=0xC)          # bytes 2..3: ignored
        assert await h.read(2) == 0x1155
        n = len(requests)
        await h.write_bytes(CODEC, (0x02 << 9) | 0x060, size, rnd)
        await ClockCycles(dut.clk, 60)
        assert requests[n:] == [(0x02, 0x060)], "%d-byte stores: I2C requests %s" % (size, requests[n:])
        assert await h.read(CODEC) == 0, "no dropped/NAK flag after %d-byte stores" % size
    dut._log.info("byte / halfword stores: registers merged per byte, one correct codec write each")


@cocotb.test()
async def test_ext_write_event(dut):
    """Cabinet registers 0x1B..0x1E read back (low 16 bits); ext_we gives one event per write of an
    extension register that contains byte 1 (address and merged data), none for byte-0-only
    stores, CODEC, effect registers and invalid addresses."""
    h = await setup(dut)
    events = []

    async def monitor():
        while True:
            await RisingEdge(dut.clk)
            await ReadOnly()
            if int(dut.ext_we.value):
                events.append((int(dut.ext_wa.value), int(dut.ext_wd.value)))

    cocotb.start_soon(monitor())
    rnd = random.Random(11)
    vals = {r: rnd.getrandbits(16) for r in (0x1B, 0x1C, 0x1D, 0x1E)}
    for r, v in vals.items():
        n = len(events)
        await h.write(r, 0xABCD0000 | v)
        await ClockCycles(dut.clk, 3)
        assert await h.read(r) == v, "register 0x%02X read back" % r
        assert events[n:] == [(r, v)], "0x%02X: write events %s" % (r, events[n:])
    # byte stores (lowest byte first): the event comes with the store that contains byte 1
    for size in (1, 2):
        for r in (0x1C, 0x1E):
            n = len(events)
            v = rnd.getrandbits(16)
            await h.write_bytes(r, v, size, rnd)
            await ClockCycles(dut.clk, 3)
            assert await h.read(r) == v
            assert events[n:] == [(r, v)], "%d-byte stores of 0x%02X: events %s" % (size, r, events[n:])
    await h.write(0x1D, 0, byteenable=0x3)
    await ClockCycles(dut.clk, 3)
    n = len(events)
    await h.write(0x1D, 0x1234, byteenable=0x1)                # byte 0 only: stored, no event
    await h.write(0x1D, 0x5500, byteenable=0x4)                # byte 2 only: ignored, no event
    await h.write(0x05, 0x1111)                                # effect register
    await h.write(0x15, 0x0010)                                # CODEC
    await h.write(0x30, 0x1111)                                # invalid
    await h.write(0x14, 0x0002)                                # CONTROL
    await ClockCycles(dut.clk, 5)
    assert events[n:] == [] and await h.read(0x1D) == 0x0034, "unexpected write events %s" % events[n:]
    dut._log.info("CAB registers 0x1B..0x1E read back; ext write events only for byte-1 writes of 0x16..0x2F")
