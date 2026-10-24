"""
test_codec.py - cocotb tests for codec_ctrl + i2c_master (v2 step B4).

A Python I2C slave resolves the open-drain bus (line = low if anyone pulls it
low), detects START/STOP, collects bytes on SCL rising edges and ACKs on the
9th clock (or NAKs when told to).
"""
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, Edge, First, RisingEdge, Timer
from cocotb.utils import get_sim_time

CLK_NS = 20
I2C_DIV = 123
DEV_W = 0x34                                    # 7-bit 0x1A, write

# expected init sequence: (register, 9-bit data); see codec_ctrl.vhd
INIT = [(15, 0x000), (9, 0x000), (0, 0x01A), (1, 0x01A), (2, 0x07A), (3, 0x07A), (4, 0x010),
        (5, 0x000), (6, 0x000), (7, 0x00A), (8, 0x000), (16, 0x07B), (17, 0x032), (18, 0x000),
        (9, 0x001)]


def to_bytes(reg, data):
    return [DEV_W, ((reg << 1) | (data >> 8)) & 0xFF, data & 0xFF]


class I2cSlave:
    def __init__(self, dut, address=0x1A):
        self.dut = dut
        self.address = address
        self.nak = False                         # NAK the data bytes when True
        self.transfers = []                      # list of byte lists (START..STOP)
        self.scl_rise_times = []
        self.pull = 0

    def lines(self):
        def low(sig):                            # unresolved (t = 0) = released, pulled up
            v = sig.value
            return v.is_resolvable and int(v) == 1
        scl = 0 if low(self.dut.scl_oe) else 1
        sda = 0 if (low(self.dut.sda_oe) or self.pull) else 1
        return scl, sda

    async def run(self):
        d = self.dut
        scl, sda = self.lines()
        d.sda_in.value = sda
        cur, bits, nbits, in_xfer, ack_phase = [], 0, 0, False, False
        while True:
            await First(Edge(d.scl_oe), Edge(d.sda_oe))
            await Timer(1, unit="ns")
            nscl, nsda = self.lines()
            if scl and nscl and sda and not nsda:                     # START
                cur, bits, nbits, in_xfer, ack_phase = [], 0, 0, True, False
                self.scl_rise_times.append(None)                     # period restarts
            elif scl and nscl and not sda and nsda and in_xfer:      # STOP
                self.transfers.append(cur)
                in_xfer = False
            elif not scl and nscl and in_xfer:                       # SCL rising: sample
                self.scl_rise_times.append(get_sim_time("ns"))
                if not ack_phase:
                    bits = (bits << 1) | nsda
                    nbits += 1
            elif scl and not nscl and in_xfer:                       # SCL falling
                if ack_phase:
                    self.pull = 0                                    # end of ACK clock
                    ack_phase = False
                elif nbits == 8:
                    cur.append(bits)
                    first = len(cur) == 1
                    ok = (bits >> 1) == self.address if first else not self.nak
                    self.pull = 1 if ok else 0                       # ACK = pull SDA low
                    ack_phase = True
                    bits, nbits = 0, 0
            scl, nsda2 = self.lines()
            d.sda_in.value = nsda2
            sda = nsda2


async def setup(dut, nak=False):
    Clock(dut.clk, CLK_NS, unit="ns").start()
    dut.rst.value = 1
    dut.init_start.value = 0
    dut.req.value = 0
    dut.req_reg.value = 0
    dut.req_data.value = 0
    dut.sda_in.value = 1
    slave = I2cSlave(dut)
    slave.nak = nak
    cocotb.start_soon(slave.run())
    await ClockCycles(dut.clk, 5)
    dut.rst.value = 0
    return slave


async def wait_init(dut):
    while not int(dut.init_done.value):
        await RisingEdge(dut.clk)


@cocotb.test()
async def test_init_sequence(dut):
    """After reset the exact v2 init sequence is written, every byte ACKed."""
    slave = await setup(dut)
    await wait_init(dut)
    exp = [to_bytes(r, v) for r, v in INIT]
    assert slave.transfers == exp, "init sequence differs:\n got %s\n exp %s" % (slave.transfers, exp)
    assert int(dut.init_nak.value) == 0
    t = slave.scl_rise_times
    p = [b - a for a, b in zip(t, t[1:]) if a is not None and b is not None]   # within transfers
    assert min(p) == max(p) == 4 * I2C_DIV * CLK_NS, "SCL period %s" % sorted(set(p))
    dut._log.info("init: %d writes, R7=0x00A (I2S 24-bit slave), R8=0x000; SCL %.1f kHz",
                  len(exp), 1e6 / (4 * I2C_DIV * 1000 / 49.152) / 1000)


@cocotb.test()
async def test_host_write(dut):
    """A host request after init becomes one I2C write; done without NAK."""
    slave = await setup(dut)
    await wait_init(dut)
    n0 = len(slave.transfers)
    dut.req_reg.value = 4
    dut.req_data.value = 0x112
    dut.req.value = 1
    await RisingEdge(dut.clk)
    dut.req.value = 0
    await RisingEdge(dut.done)
    await RisingEdge(dut.clk)
    assert int(dut.nak.value) == 0
    await ClockCycles(dut.clk, 4 * I2C_DIV)
    assert slave.transfers[n0:] == [to_bytes(4, 0x112)], "host write bytes %s" % slave.transfers[n0:]
    dut._log.info("host write R4 = 0x112 (9-bit) -> bytes %s", [hex(b) for b in slave.transfers[n0]])


@cocotb.test()
async def test_nak(dut):
    """A NAKing codec is reported for the init sequence and for host writes."""
    slave = await setup(dut, nak=True)
    await wait_init(dut)
    assert int(dut.init_nak.value) == 1, "init NAK not reported"
    dut.req_reg.value = 9
    dut.req_data.value = 1
    dut.req.value = 1
    await RisingEdge(dut.clk)
    dut.req.value = 0
    await RisingEdge(dut.done)
    await RisingEdge(dut.clk)
    assert int(dut.nak.value) == 1, "host write NAK not reported"
    dut._log.info("NAK reported for init and host writes")


@cocotb.test()
async def test_reinit(dut):
    """init_start runs the whole sequence again."""
    slave = await setup(dut)
    await wait_init(dut)
    n0 = len(slave.transfers)
    dut.init_start.value = 1
    await RisingEdge(dut.clk)
    dut.init_start.value = 0
    await RisingEdge(dut.clk)
    await wait_init(dut)
    assert slave.transfers[n0:] == [to_bytes(r, v) for r, v in INIT]
    dut._log.info("re-init repeated the %d writes", len(INIT))
