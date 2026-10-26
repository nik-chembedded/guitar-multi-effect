"""
fxdriver.py - frame-level driver for the FX_chain VHDL entity (cocotb).

v2 (step B1): FX_chain runs on one clock `clk` with two 1-cycle strobes per
audio frame: `sample_tick`, then `half_tick` CLK_PER_HALF cycles later (in
hardware 512 cycles apart at 49.152 MHz; in simulation shorter, which is
equivalent because the datapath only advances on the strobes). This is the
same timing as sim/tb/tb_fx_wav.vhd. The input sample is presented before
sample_tick; the output is read one clock after half_tick.

GME_HALF (environment, default 8) sets CLK_PER_HALF. 512 gives the 1024-clock frames of the
board; test_timing_invariance runs one configuration at 8 and at 512 and requires identical output.

Step C: the chain is DW bits wide (generic DW, 16 or 24; GME_DW tells the
driver). Samples are given and returned in 16-bit scale (shifted by DW-16)
unless raw=True, which passes DW-bit values unchanged.
"""
import os

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge

CLK_PER_HALF = int(os.environ.get("GME_HALF", "8"))

# effects_enable bits (docs/register_map.md)
OD, TREM, ECHO, DIST, CHORUS, REVERB, CAB, DYN, EQ = 1, 2, 4, 8, 16, 32, 64, 128, 256

# D4: room presets of REVERB_TYPE 0..3 as (size Q0.16, damp); the mapping is done by gme_core
# (checked in test_system), FX_chain takes size / damp. set(reverb_type=t) is shorthand for them.
ROOMS = ((45875, 100), (52429, 80), (57672, 60), (61604, 40))

PARAMS = ("effects_enable", "od_drive", "od_gain", "trem_depth", "trem_wave",
          "echo_time", "echo_level", "echo_repeat", "chorus_rate", "chorus_level",
          "chorus_depth", "dist_mix", "dist_type", "reverb_size", "reverb_damp", "reverb_mix", "trem_rate",
          "mod_base", "mod_fb", "mod_shape", "echo_frac", "cab_ctrl",
          "dyn_ctrl", "gate_thresh", "comp_thresh", "comp_ratio", "comp_attack", "comp_release", "comp_makeup")


def to_s16(v):
    return v - 65536 if v >= 32768 else v


def to_signed(v, bits):
    return v - (1 << bits) if v >= 1 << (bits - 1) else v


class FxChain:
    def __init__(self, dut):
        self.dut = dut
        self.frames = 0
        self.dw = int(os.environ.get("GME_DW", "16"))
        self.shift = self.dw - 16
        self.probe = None          # list: frame() appends the signal named probe_sig seen at half_tick
        self.probe_sig = "echo_out"   # the reverb input; "cab_out" = the EQ stage input

    async def start(self, **params):
        d = self.dut
        Clock(d.clk, 10, unit="ns").start()
        for p in PARAMS:
            getattr(d, p).value = 0
        for name in ("od_enable", "tremolo_enable", "echo_enable"):
            getattr(d, name).value = 0
        d.data_in_left.value = 0
        d.data_in_right.value = 0
        for name, v in (("cab_cw_en", 0), ("cab_cw_bank", 0), ("cab_cw_addr", 0), ("cab_cw_data", 0),
                        ("eq_cw_en", 0), ("eq_cw_addr", 0), ("eq_cw_data", 0), ("eq_apply", 0)):
            getattr(d, name).value = v
        d.sample_tick.value = 0
        d.half_tick.value = 0
        self.set(**params)
        await ClockCycles(d.clk, 4)

    def set(self, **params):
        """Write effect registers, e.g. set(effects_enable=OD, od_drive=3000)."""
        for name, value in params.items():
            if name == "reverb_type":
                size, damp = ROOMS[int(value)]
                self.dut.reverb_size.value, self.dut.reverb_damp.value = size, damp
                continue
            if name not in PARAMS:
                raise ValueError("unknown parameter " + name)
            getattr(self.dut, name).value = int(value) & (0xFF if name == "echo_frac" else 0xFFFF)

    async def cab_write(self, bank, coefs, first=0):
        """Write cabinet coefficients (signed 18-bit) through the chain's write port, one per clock."""
        d = self.dut
        for i, c in enumerate(coefs):
            d.cab_cw_en.value, d.cab_cw_bank.value = 1, bank
            d.cab_cw_addr.value, d.cab_cw_data.value = first + i, int(c) & 0x3FFFF
            await RisingEdge(d.clk)
        d.cab_cw_en.value = 0
        await RisingEdge(d.clk)

    async def eq_write(self, coefs, scale=None, apply=True):
        """Write the EQ coefficients (15 signed 18-bit values, addresses 0..14), the scale word (address 15,
        if given) through the chain's write port, one per clock, then pulse apply (taken over at the next
        half_tick). Call between frames."""
        d = self.dut
        words = [(i, int(c) & 0x3FFFF) for i, c in enumerate(coefs)]
        if scale is not None:
            words.append((15, int(scale) & 0x3F))
        for a, w in words:
            d.eq_cw_en.value, d.eq_cw_addr.value, d.eq_cw_data.value = 1, a, w
            await RisingEdge(d.clk)
        d.eq_cw_en.value = 0
        if apply:
            d.eq_apply.value = 1
            await RisingEdge(d.clk)
            d.eq_apply.value = 0
        await RisingEdge(d.clk)

    async def frame(self, sample, raw=False):
        """Process one input sample, return the output sample of this frame."""
        d = self.dut
        v = int(sample) if raw else int(sample) << self.shift
        d.data_in_left.value = v & ((1 << self.dw) - 1)
        await ClockCycles(d.clk, CLK_PER_HALF)
        d.sample_tick.value = 1
        await RisingEdge(d.clk)
        d.sample_tick.value = 0
        await ClockCycles(d.clk, CLK_PER_HALF - 1)
        if self.probe is not None:
            self.probe.append(to_signed(int(getattr(d, self.probe_sig).value), self.dw))
        d.half_tick.value = 1
        await RisingEdge(d.clk)
        d.half_tick.value = 0
        await RisingEdge(d.clk)
        self.frames += 1
        out = d.data_out_left.value
        if not out.is_resolvable:
            return None                      # X/U while the pipeline fills
        y = to_signed(int(out), self.dw)
        return y if raw else y >> self.shift

    async def run(self, samples, tail=0, on_frame=None, raw=False):
        """Stream samples (+ tail zeros) through the chain, return outputs."""
        out = []
        for n, s in enumerate(list(samples) + [0] * tail):
            if on_frame:
                on_frame(n)
            out.append(await self.frame(s, raw))
        return out


def find_latency(x, y, max_lat=16, start=64, length=400):
    """Latency (frames) at which y best matches x."""
    best = None
    for lat in range(max_lat + 1):
        err = sum(abs((y[i + lat] or 0) - x[i]) for i in range(start, start + length))
        if best is None or err < best[0]:
            best = (err, lat)
    return best[1]
