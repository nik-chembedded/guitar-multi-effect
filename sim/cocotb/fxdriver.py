"""
fxdriver.py - frame-level driver for the FX_chain VHDL entity (cocotb).

One audio frame = one LRCLK period of 2 * CLK_PER_HALF cycles of CLK_18MHZ
(the same timing as sim/tb/tb_fx_wav.vhd). Samples are presented on the
falling LRCLK edge, like the FIFO does in hardware, and the output is read
one clock after the next falling edge.
"""
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge

CLK_PER_HALF = 8

# effects_enable bits (docs/register_map.md)
OD, TREM, ECHO, DIST, CHORUS, REVERB = 1, 2, 4, 8, 16, 32

PARAMS = ("effects_enable", "od_drive", "od_gain", "trem_depth", "trem_wave",
          "echo_time", "echo_level", "echo_repeat", "chorus_rate", "chorus_level",
          "chorus_depth", "dist_mix", "dist_type", "reverb_type", "reverb_mix")


def to_s16(v):
    return v - 65536 if v >= 32768 else v


class FxChain:
    def __init__(self, dut):
        self.dut = dut
        self.frames = 0

    async def start(self, **params):
        d = self.dut
        Clock(d.CLK_18MHZ, 10, unit="ns").start()
        for p in PARAMS:
            getattr(d, p).value = 0
        for name in ("od_enable", "tremolo_enable", "echo_enable"):
            getattr(d, name).value = 0
        d.data_in_left.value = 0
        d.data_in_right.value = 0
        d.AUD_DACLRCLK.value = 0
        self.set(**params)
        await ClockCycles(d.CLK_18MHZ, 4)

    def set(self, **params):
        """Write effect registers, e.g. set(effects_enable=OD, od_drive=3000)."""
        for name, value in params.items():
            if name not in PARAMS:
                raise ValueError("unknown parameter " + name)
            getattr(self.dut, name).value = int(value) & 0xFFFF

    async def frame(self, sample):
        """Process one input sample, return the output sample of this frame."""
        d = self.dut
        d.data_in_left.value = int(sample) & 0xFFFF
        await ClockCycles(d.CLK_18MHZ, CLK_PER_HALF)
        d.AUD_DACLRCLK.value = 1
        await ClockCycles(d.CLK_18MHZ, CLK_PER_HALF)
        d.AUD_DACLRCLK.value = 0
        await RisingEdge(d.CLK_18MHZ)
        self.frames += 1
        out = d.data_out_left.value
        if not out.is_resolvable:
            return None                      # X/U while the pipeline fills
        return to_s16(int(out))

    async def run(self, samples, tail=0, on_frame=None):
        """Stream samples (+ tail zeros) through the chain, return outputs."""
        out = []
        for n, s in enumerate(list(samples) + [0] * tail):
            if on_frame:
                on_frame(n)
            out.append(await self.frame(s))
        return out


def find_latency(x, y, max_lat=16, start=64, length=400):
    """Latency (frames) at which y best matches x."""
    best = None
    for lat in range(max_lat + 1):
        err = sum(abs((y[i + lat] or 0) - x[i]) for i in range(start, start + length))
        if best is None or err < best[0]:
            best = (err, lat)
    return best[1]
