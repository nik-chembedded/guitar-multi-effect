# Register Map (v2)

The registers live in `reg_file.vhd`, behind the Avalon-MM slave `ctrl_avmm.vhd`
on the HPS **lightweight HPS-to-FPGA bridge**. Linux on the ARM reaches register *n*
as the 32-bit word at **`0xFF200000 + 4·n`** (tool: [`tools/gme_hps.py`](../tools/gme_hps.py)).
(v1, on the `v1` branch, used a Nios II and the Avalon slave `RegistersControl` at
`0x0800_1000`; the UART protocol of v2 step B is at the tag `v2-uart`.)

| Property      | Value |
|---------------|-------|
| Data width    | 16 bit registers in 32-bit words (bits 31..16 read 0, ignored on write) |
| Byte enables  | honoured: byte / halfword stores change only those bytes, so they give the same result as one 32-bit store |
| Address       | register *n* at byte offset 4·*n* from `0xFF200000` |
| Access        | effect registers R/W, status registers R |
| Reset value   | 0 (all effects off) |

Every register is 16 bits wide. The parameters keep their 16-bit scale with the 24-bit
effects (e.g. Overdrive Drive is still a 16-bit amplitude). Levels, depths, mixes,
repeat and drive are smoothed in the FPGA (time constant 2.7 ms), and enable bits fade
the effect in or out over 5.3 ms. Bits not listed below are reserved: write `0`.
The bit ranges are the bits the RTL actually reads.

Unknown addresses read 0 and ignore writes; writes to the read-only registers are ignored.

| Reg | Name            | R/W | Bits used | Field                         | Description |
|----:|-----------------|:---:|-----------|-------------------------------|-------------|
| 0   | Effects Enable  | W   | `[5:0]`   | `REVERB CHORUS DIST ECHO TREM OD` | One enable bit per effect, see [(1)](#1-effects-enable). |
| 1   | Overdrive Drive | W   | `[15:0]`  | Drive Value                   | Clipping threshold (unsigned sample amplitude). GUI range 0 … 3500. |
| 2   | Overdrive Gain  | W   | `[15:0]`  | Gain Volume                   | Integer post-clip gain multiplier. GUI range 1 … 5. |
| 3   | Tremolo Wave    | W   | `[3:0]`   | Waveform Selection            | LFO waveform/rate, see [(2)](#2-tremolo-waveform-selection). |
| 4   | Tremolo Depth   | W   | `[7:0]`   | Modulation Depth Value        | 0 = dry … 255 = full modulation. |
| 5   | Echo Time       | W   | `[14:0]`  | Echo Reflection Time Value    | Delay in samples @ 48 kHz (bit 15 must be `0`). 32767 ≈ 0.68 s. |
| 6   | Echo Repeat     | W   | `[7:0]`   | Repeat Decay Volume           | Feedback amount, 0 … 255 (/256). |
| 7   | Echo Level      | W   | `[15:0]`  | Initial Reflection Volume     | Wet level, unsigned Q0.16 (65535 ≈ 1.0). GUI range 0 … 32000. |
| 8   | Distortion Mix  | W   | `[7:0]`   | Distortion Mixed Signal Value | Dry/wet mix, 0 = dry … 255 = wet. |
| 9   | Distortion Type | W   | `[1:0]`   | Distortion Type Selection     | Clipping curve, see [(3)](#3-distortion-type-selection). |
| 10  | Chorus Level    | W   | `[15:0]`  | Chorus Mixed Signal Value     | Wet level, unsigned Q0.16. |
| 11  | Chorus Depth    | W   | `[9:0]`   | Chorus Delay Depth Value      | LFO sweep depth in samples (sweeps 2 … depth+2). |
| 12  | Chorus Rate     | W   | `[9:0]`   | Chorus Delay Rate Value       | LFO clock divider (higher = slower). |
| 13  | Reverb Mix      | W   | `[7:0]`   | Reverb Mixed Signal Value     | Dry/wet mix, 0 = dry … 255 = wet. |
| 14  | Reverb Type     | W   | `[3:0]`   | Reverb Type Selection         | Room preset, see [(4)](#4-reverb-type-selection). |
| 0x10 | VERSION        | R   | `[15:0]`  | | `0x0203` = v2 step D1 (generated LFO); `0x0202` = step C (24-bit effects); `0x0201` = HPS control, 16-bit |
| 0x11 | STATUS         | R   | `[2:0]`   | | bit0 codec init done, bit1 codec NAK (init), bit2 PLL locked |
| 0x12 | LEVEL_IN       | R   | `[15:0]`  | | input peak level (left, 16-bit magnitude, decays ~1/256 per sample) |
| 0x13 | LEVEL_OUT      | R   | `[15:0]`  | | output peak level |
| 0x14 | CONTROL        | R/W | `[1:0]`   | | bit0 = re-run codec init (self-clearing), bit1 = mute |
| 0x15 | CODEC          | R/W | `[15:0]`  | | codec register write over I²C, see [(5)](#5-codec-register) |
| 0x16 | TREM_RATE      | R/W | `[15:0]`  | | tremolo LFO rate in 0.01 Hz for free mode (e.g. 650 = 6.5 Hz; 1 … 2000 = 0.01 … 20 Hz), smoothed |

## Field encodings

### (1) Effects Enable

| Bit | Effect     | `0`     | `1`    |
|----:|------------|---------|--------|
| 0   | Overdrive  | Bypass  | Enable |
| 1   | Tremolo    | Bypass  | Enable |
| 2   | Echo       | Bypass  | Enable |
| 3   | Distortion | Bypass  | Enable |
| 4   | Chorus     | Bypass  | Enable |
| 5   | Reverb     | Bypass  | Enable |

Signal chain order (fixed in `FX_chain.vhd`):
`Overdrive → Distortion → Chorus → Tremolo → Echo → Reverb`

### (2) Tremolo Waveform Selection

| Value | Waveform | Rate  |
|------:|----------|-------|
| 0     | Sine     | 5 Hz  |
| 1     | Sine     | 7 Hz  |
| 2     | Sine     | 10 Hz |
| 3     | Sine     | 12 Hz |
| 4     | Sine     | 15 Hz |
| 5     | Triangle | 5 Hz  |
| 6     | Triangle | 10 Hz |
| 7     | Sawtooth | 10 Hz |

Since step D1 these come from the generated LFO (16-bit, phase-continuous) instead of
8-bit ROM tables; shapes and rates are unchanged.

**Free mode** (bit 3 = 1): bits `[1:0]` select the shape, the rate comes from TREM_RATE (0x16).

| Value | Shape |
|------:|-------|
| 8     | Sine |
| 9     | Triangle |
| 10    | Sawtooth (rising) |
| 11    | Square (edges rounded by the tremolo's 0.7 ms smoothing) |

### (3) Distortion Type Selection

| Value | Type              |
|------:|-------------------|
| 0     | Soft distortion   |
| 1     | Medium distortion |
| 2     | Heavy distortion  |
| 3     | (= Soft)          |

### (4) Reverb Type Selection

| Value | Type              |
|------:|-------------------|
| 0     | Very light reverb |
| 1     | Light reverb      |
| 2     | Medium reverb     |
| 3     | Heavy reverb      |
| other | (= Heavy)         |

### (5) CODEC register

| Access | Bits | Meaning |
|--------|------|---------|
| write  | `[15:9]` | WM8731 register address (0..127) |
| write  | `[8:0]`  | 9-bit register value |
| read   | bit0 | busy (codec init or a write still running) |
| read   | bit1 | the last host write was not ACKed (NAK) |
| read   | bit2 | a write was dropped because the I²C master was busy |

A write that contains byte 1 (bits 15..8) starts one I²C transfer (about 0.3 ms at 100 kHz),
using byte 0 from the same or an earlier write. Store byte 0 first, or write the whole word. Poll bit0 until it is 0
before the next write; `gme_hps.py codec` does this. An accepted write clears bit2.

The codec is initialised by the FPGA itself after reset (I²S slave, 24-bit,
48 kHz; see `codec_ctrl.vhd`). CODEC writes are only needed to change volumes
or routing.

## Access from Linux

```python
import ctypes, mmap, os
fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
mem = mmap.mmap(fd, 0x100, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=0xFF200000)
regs = (ctypes.c_uint32 * 64).from_buffer(mem)    # one 32-bit access per register
regs[0x10]                                        # VERSION -> 0x0202
regs[0x00] = 0x0008                               # effects_enable = DIST
```

Only access these addresses while the multi-effect FPGA image is loaded: with another
image (or none) the bridge has no slave there and the access can hang or crash Linux.
`gme_hps.py` reads VERSION first and refuses to write when it is not `0x02xx`.
