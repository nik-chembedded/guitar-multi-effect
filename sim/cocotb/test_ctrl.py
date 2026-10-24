"""
test_ctrl.py - cocotb tests for ctrl_block (v2 step B3): UART framing,
register read/write, error handling, resynchronisation, codec requests.

A Python UART host drives uart_rx and decodes uart_tx. The test plays the I2C
master through the i2c_req/i2c_done/i2c_nak handshake.
"""
import os
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, RisingEdge

CLK_HZ = 49_152_000
BAUD = int(os.environ.get("GME_BAUD", "1536000"))
BIT = CLK_HZ // BAUD                     # clocks per bit (exact for the test baud rates)
TIMEOUT = int(os.environ.get("GME_TIMEOUT", "20000"))

EFFECT_REGS = ["effects_enable", "od_drive", "od_gain", "trem_wave", "trem_depth", "echo_time",
               "echo_repeat", "echo_level", "dist_mix", "dist_type", "chorus_level",
               "chorus_depth", "chorus_rate", "reverb_mix", "reverb_type"]


def crc8(data):
    c = 0
    for b in data:
        c ^= b
        for _ in range(8):
            c = ((c << 1) ^ 0x07) & 0xFF if c & 0x80 else (c << 1) & 0xFF
    return c


def frame(cmd, addr, data=0, bad_crc=False):
    body = [cmd, addr, (data >> 8) & 0xFF, data & 0xFF]
    c = crc8(body) ^ (0x55 if bad_crc else 0)
    return [0xA5] + body + [c]


class Host:
    def __init__(self, dut):
        self.dut = dut
        dut.uart_rx.value = 1

    async def send_byte(self, b):
        d = self.dut
        for bit in [0] + [(b >> i) & 1 for i in range(8)] + [1]:
            d.uart_rx.value = bit
            await ClockCycles(d.clk, BIT)

    async def send(self, data):
        for b in data:
            await self.send_byte(b)

    async def recv_byte(self):
        d = self.dut
        await FallingEdge(d.uart_tx)                     # start bit
        await ClockCycles(d.clk, BIT + BIT // 2)         # middle of bit 0
        v = 0
        for i in range(8):
            v |= int(d.uart_tx.value) << i
            await ClockCycles(d.clk, BIT)
        assert int(d.uart_tx.value) == 1, "stop bit is not 1"
        return v

    async def transact(self, data):
        rx = cocotb.start_soon(self.recv_reply())
        await self.send(data)
        return await rx

    async def recv_reply(self):
        r = [await self.recv_byte() for _ in range(5)]
        assert r[0] == 0x5A, "reply does not start with 5A: %s" % r
        assert r[4] == crc8(r[1:4]), "reply CRC wrong: %s" % r
        return r[1], (r[2] << 8) | r[3]                  # status, data


async def setup(dut):
    Clock(dut.clk, 20, unit="ns").start()
    dut.rst.value = 1
    dut.uart_rx.value = 1
    dut.i2c_busy.value = 0
    dut.i2c_done.value = 0
    dut.i2c_nak.value = 0
    dut.status_in.value = 0x0005
    dut.level_in.value = 0x1234
    dut.level_out.value = 0x4321
    await ClockCycles(dut.clk, 5)
    dut.rst.value = 0
    await ClockCycles(dut.clk, 5)
    return Host(dut)


@cocotb.test()
async def test_ping(dut):
    """PING returns the version; the reply is framed and CRC-protected."""
    h = await setup(dut)
    st, data = await h.transact(frame(0x04, 0))
    assert (st, data) == (0, 0x0200), "ping reply %s" % ((st, data),)
    dut._log.info("PING -> version 0x%04X at %d baud", data, BAUD)


@cocotb.test()
async def test_write_read_all(dut):
    """All 15 effect registers: write random values, read back, check the outputs."""
    h = await setup(dut)
    rnd = random.Random(1)
    vals = [rnd.getrandbits(16) for _ in EFFECT_REGS]
    for a, v in enumerate(vals):
        st, _ = await h.transact(frame(0x01, a, v))
        assert st == 0, "write reg %d status %d" % (a, st)
    for a, v in enumerate(vals):
        st, data = await h.transact(frame(0x02, a))
        assert (st, data) == (0, v), "read reg %d: %s expected %04X" % (a, (st, data), v)
        assert int(getattr(dut, EFFECT_REGS[a]).value) == v, "output %s" % EFFECT_REGS[a]
    for a, exp in ((0x10, 0x0200), (0x11, 0x0005), (0x12, 0x1234), (0x13, 0x4321)):
        st, data = await h.transact(frame(0x02, a))
        assert (st, data) == (0, exp), "status reg 0x%02X: %s" % (a, (st, data))
    dut._log.info("15 effect registers written/read back, status registers OK")


@cocotb.test()
async def test_errors(dut):
    """Bad CRC, bad address, bad command and writes to read-only registers are rejected."""
    h = await setup(dut)
    await h.transact(frame(0x01, 2, 0x1111))
    st, _ = await h.transact(frame(0x01, 2, 0x2222, bad_crc=True))
    assert st == 1, "bad CRC must give status 1, got %d" % st
    assert int(dut.od_gain.value) == 0x1111, "register changed despite bad CRC"
    assert (await h.transact(frame(0x01, 0x30, 1)))[0] == 2, "bad write address"
    assert (await h.transact(frame(0x02, 0x7F)))[0] == 2, "bad read address"
    assert (await h.transact(frame(0x09, 0)))[0] == 2, "unknown command"
    dut._log.info("CRC / address / command errors rejected")


@cocotb.test()
async def test_resync(dut):
    """Garbage and a truncated frame do not desynchronise the parser."""
    h = await setup(dut)
    await h.send([0x00, 0xFF, 0x13, 0x37])               # noise without A5
    await h.send([0xA5, 0x01, 0x02])                     # truncated frame (lost bytes)
    await ClockCycles(dut.clk, TIMEOUT + 10 * BIT)       # parser times out
    st, _ = await h.transact(frame(0x01, 2, 0xBEEF))
    assert st == 0 and int(dut.od_gain.value) == 0xBEEF, "frame after a truncated one failed"
    dut._log.info("recovered after noise + truncated frame")


@cocotb.test()
async def test_codec_write(dut):
    """CODEC command: I2C request with register/data, reply after done; NAK reported."""
    h = await setup(dut)

    async def i2c_master(nak):
        await RisingEdge(dut.i2c_req)
        reg, data = int(dut.i2c_reg.value), int(dut.i2c_data.value)
        await ClockCycles(dut.clk, 500)                  # transfer time
        dut.i2c_nak.value = nak
        dut.i2c_done.value = 1
        await RisingEdge(dut.clk)
        dut.i2c_done.value = 0
        return reg, data

    m = cocotb.start_soon(i2c_master(0))
    st, _ = await h.transact(frame(0x03, 0x07, 0x00A))   # R7 = 0x0A
    assert st == 0 and await m == (0x07, 0x00A), "codec write"
    m = cocotb.start_soon(i2c_master(1))
    st, _ = await h.transact(frame(0x03, 0x08, 0x100))   # 9-bit data, NAKed
    assert st == 3 and await m == (0x08, 0x100), "codec NAK must give status 3"
    dut.i2c_busy.value = 1
    st, _ = await h.transact(frame(0x03, 0x09, 0x001))
    assert st == 4, "busy I2C must give status 4"
    dut._log.info("codec writes forwarded (incl. 9-bit data), NAK and busy reported")
