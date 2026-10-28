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
| Reset value   | 0 (all effects off); the only exceptions are CHAIN_0 … CHAIN_2 (0x30 … 0x32, the default effect order, step E) |

Every register is 16 bits wide. The parameters keep their 16-bit scale with the 24-bit
effects (e.g. Overdrive Drive is still a 16-bit amplitude). Levels, depths, mixes,
repeat and drive are smoothed in the FPGA (time constant 2.7 ms), and enable bits fade
the effect in or out over 5.3 ms. Bits not listed below are reserved: write `0`.
The bit ranges are the bits the RTL actually reads.

Unknown addresses read 0 and ignore writes; writes to the read-only registers are ignored.

| Reg | Name            | R/W | Bits used | Field                         | Description |
|----:|-----------------|:---:|-----------|-------------------------------|-------------|
| 0   | Effects Enable  | W   | `[8:0]`   | `EQ DYN CAB REVERB CHORUS DIST ECHO TREM OD` | One enable bit per effect, see [(1)](#1-effects-enable). |
| 1   | Overdrive Drive | W   | `[15:0]`  | Drive Value                   | Clipping threshold (unsigned sample amplitude). GUI range 0 … 3500. |
| 2   | Overdrive Gain  | W   | `[15:0]`  | Gain Volume                   | Integer post-clip gain multiplier. GUI range 1 … 5. |
| 3   | Tremolo Wave    | W   | `[3:0]`   | Waveform Selection            | LFO waveform/rate, see [(2)](#2-tremolo-waveform-selection). |
| 4   | Tremolo Depth   | W   | `[7:0]`   | Modulation Depth Value        | 0 = dry … 255 = full modulation. |
| 5   | Echo Time       | W   | `[14:0]`  | Echo Reflection Time Value    | Delay in samples @ 48 kHz (bit 15 must be `0`). 32767 ≈ 0.68 s. Smoothed with a fractional part (step D2): changing it glides like a tape echo. |
| 6   | Echo Repeat     | W   | `[7:0]`   | Repeat Decay Volume           | Feedback amount, 0 … 255 (/256). |
| 7   | Echo Level      | W   | `[15:0]`  | Initial Reflection Volume     | Wet level, unsigned Q0.16 (65535 ≈ 1.0). GUI range 0 … 32000. |
| 8   | Distortion Mix  | W   | `[7:0]`   | Distortion Mixed Signal Value | Dry/wet mix, 0 = dry … 255 = wet. |
| 9   | Distortion Type | W   | `[1:0]`   | Distortion Type Selection     | Clipping curve, see [(3)](#3-distortion-type-selection). |
| 10  | Mod Mix         | W   | `[7:0]`   | Chorus / flanger / vibrato mix | Dry/wet 0 … 255 (step D2; v1: chorus level Q0.16). Smoothed. |
| 11  | Mod Depth       | W   | `[10:0]`  | Modulation depth               | Delay swing ± depth samples around MOD_BASE (step D2). Smoothed. |
| 12  | Mod Rate        | W   | `[15:0]`  | Modulation LFO rate            | 0.01 Hz (step D2; v1: clock divider). Smoothed. |
| 13  | Reverb Mix      | W   | `[7:0]`   | Reverb Mixed Signal Value     | Dry/wet mix, 0 = dry (exactly the input) … 255 = wet. Smoothed. |
| 14  | Reverb Type     | W   | `[3:0]`   | Reverb Type Selection         | Room preset 0 … 3, or 4 = custom size / damp (registers 0x1F / 0x20), see [(4)](#4-reverb-type-selection). Changes glide (size and damp are smoothed). |
| 0x10 | VERSION        | R   | `[15:0]`  | | `0x0209` = step E (the effect order is selectable at run time, registers 0x30 … 0x33); `0x0208` = step D6 (output level of the overdrive / distortion, registers 0x2D / 0x2E); `0x0207` = step D5 (dynamics, EQ: bits 7 / 8, registers 0x21 … 0x2C); `0x0206` = step D4 (Freeverb reverb, REVERB_SIZE / REVERB_DAMP); `0x0205` = step D3 (cabinet FIR, CAB registers); `0x0204` = step D2 (modulated delay, fractional echo); `0x0203` = D1 (generated LFO); `0x0202` = step C (24-bit); `0x0201` = HPS control, 16-bit |
| 0x11 | STATUS         | R   | `[2:0]`   | | bit0 codec init done, bit1 codec NAK (init), bit2 PLL locked |
| 0x12 | LEVEL_IN       | R   | `[15:0]`  | | input peak level (left, 16-bit magnitude, decays ~1/256 per sample) |
| 0x13 | LEVEL_OUT      | R   | `[15:0]`  | | output peak level |
| 0x14 | CONTROL        | R/W | `[1:0]`   | | bit0 = re-run codec init (self-clearing), bit1 = mute |
| 0x15 | CODEC          | R/W | `[15:0]`  | | codec register write over I²C, see [(5)](#5-codec-register) |
| 0x16 | TREM_RATE      | R/W | `[15:0]`  | | tremolo LFO rate in 0.01 Hz for free mode (e.g. 650 = 6.5 Hz; 1 … 2000 = 0.01 … 20 Hz), smoothed |
| 0x18 | MOD_BASE       | R/W | `[10:0]`  | | modulated delay: centre delay in samples (1 … 2046; 48 = 1 ms), smoothed |
| 0x19 | MOD_FB         | R/W | `[15:0]`  | | modulated delay feedback, signed Q15 (−32767 … 32767 = −1 … +1), smoothed |
| 0x1A | MOD_SHAPE      | R/W | `[0]`     | | modulated delay LFO: 0 sine, 1 triangle |
| 0x1B | CAB_CTRL       | R/W | `[6:0]`   | | cabinet: bit0 = active coefficient bank, `[3:1]` = shift of bank 0, `[6:4]` = shift of bank 1, see [(7)](#7-cabinet-fir-step-d3) |
| 0x1C | CAB_ADDR       | R/W | `[11:0]`  | | cabinet coefficient write pointer: bit11 = bank, `[10:0]` = tap; writing sets the pointer (reads back the last value written, not the auto-incremented pointer) |
| 0x1D | CAB_DATA_LO    | R/W | `[15:0]`  | | coefficient bits 15..0 (kept until CAB_DATA_HI is written) |
| 0x1E | CAB_DATA_HI    | R/W | `[1:0]`   | | coefficient bits 17..16; **writing it stores {HI, LO} at the pointer and increments the tap address** |
| 0x1F | REVERB_SIZE    | R/W | `[15:0]`  | | reverb size = feedback of the 8 comb filters, unsigned Q0.16 (65535 ≈ 1.0; limited to 0.98 = 64225 inside), used when REVERB_TYPE = 4; smoothed |
| 0x20 | REVERB_DAMP    | R/W | `[7:0]`   | | reverb damping 0 … 255 (0 = bright tail, higher = darker), used when REVERB_TYPE = 4; smoothed |
| 0x21 | DYN_CTRL       | R/W | `[1:0]`   | | dynamics: bit0 = noise gate on, bit1 = compressor on, see [(8)](#8-dynamics-step-d5) |
| 0x22 | GATE_THRESH    | R/W | `[15:0]`  | | gate threshold, signed, Q8 log2 units re full scale (−45 dBFS = −1913) |
| 0x23 | COMP_THRESH    | R/W | `[15:0]`  | | compressor threshold, signed, Q8 log2 units (−20 dBFS = −850) |
| 0x24 | COMP_RATIO     | R/W | `[2:0]`   | | 0 = 1:1, 1 = 2:1, 2 = 4:1, 3 = 8:1, 4 … 7 = ∞:1 |
| 0x25 | COMP_ATTACK    | R/W | `[3:0]`   | | gain attack, time constant 2^k samples (k = 0 immediate … 15 = 683 ms) |
| 0x26 | COMP_RELEASE   | R/W | `[3:0]`   | | gain release, time constant 2^k samples |
| 0x27 | COMP_MAKEUP    | R/W | `[15:0]`  | | make-up gain, signed, Q8 log2 units (+6 dB = 255) |
| 0x28 | EQ_ADDR        | R/W | `[3:0]`   | | EQ coefficient write pointer 0 … 15 (0 … 14 coefficient, 15 = scale word), see [(9)](#9-eq-step-d5) |
| 0x29 | EQ_DATA_LO     | R/W | `[15:0]`  | | coefficient bits 15..0 (kept until EQ_DATA_HI is written) |
| 0x2A | EQ_DATA_HI     | R/W | `[1:0]`   | | coefficient bits 17..16; **writing it stores {HI, LO} at the pointer and increments the pointer** (15 wraps to 0) |
| 0x2B | EQ_APPLY       | W   | –         | | **any write** applies the written set: all three EQ sections change at the next half-frame strobe (reads back what was written) |
| 0x2C | DYN_GR         | R   | `[15:0]`  | | **read-only** gain-reduction meter of the dynamics stage, unsigned Q8 log2 units (÷ 42.52 = dB); 0 while the stage is off. Writes are ignored |
| 0x2D | OD_LEVEL       | R/W | `[15:0]`  | | overdrive output level, **signed**, Q8 log2 units (1 unit = 0.0235 dB, register = dB × 42.52): −1024 … +512 = −24 … +12 dB, **0 = exactly unity** (reset value; the output is then bit-identical to VERSION ≤ 0x0207); values outside the range are clamped. Smoothed (glides), see [(10)](#10-output-level-of-the-overdrive-and-distortion-step-d6) |
| 0x2E | DIST_LEVEL     | R/W | `[15:0]`  | | distortion output level, same format, applies to the shaped (wet) signal before the dry/wet mix |
| 0x30 | CHAIN_0        | R/W | `[15:0]`  | | **effect order**, slots 0 … 3: one effect id per nibble, slot 0 in bits 3:0. Reset `0x6307`. A shadow register: the order is used only after CHAIN_APPLY, see [(11)](#11-effect-order-step-e) |
| 0x31 | CHAIN_1        | R/W | `[15:0]`  | | effect order, slots 4 … 7 (slot 4 in bits 3:0). Reset `0x2148` |
| 0x32 | CHAIN_2        | R/W | `[3:0]`   | | effect order, slot 8. Reset `0x0005` |
| 0x33 | CHAIN_APPLY    | R/W | `[1:0]`   | | **any write** checks the list in 0x30 … 0x32 and applies it with the ~5 ms output fade (the written value is not stored). Read (live status): bit0 = order change running, bit1 = the last list was rejected (not a permutation of 0 … 8) |
| 0x16 … 0x33 | (extension) | R/W | | | registers of steps D and E; unused ones (0x17, 0x2F) read back what was written |

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
| 6   | Cabinet (FIR, step D3) | Bypass | Enable |
| 7   | Dynamics (gate + compressor, step D5) | Bypass | Enable |
| 8   | EQ (3 bands, step D5) | Bypass | Enable |

Signal chain order (VERSION ≥ 0x0209: selectable, see [(11)](#11-effect-order-step-e); the power-up / reset order is):
`Dynamics → Overdrive → Distortion → Cabinet → EQ → Chorus → Tremolo → Echo → Reverb`

An effect that is off keeps its place in the order (it passes its input on). The chain has a fixed latency per stage that
does not depend on the order; overdrive, distortion and the cabinet add one more frame while they are on, see
[(11)](#11-effect-order-step-e). Enabling / disabling fades over 256 samples like every other effect.

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

Freeverb-style reverb (step D4): 8 parallel low-pass-feedback comb filters + 4 series all-pass filters.
`size` is the comb feedback (Q0.16), `damp` the damping of the low-pass in the feedback loop (0 … 255).
Types 0 … 3 are room presets; the decay time and the brightness of the tail follow from the two values.

| Value | Type              | size (Q0.16)    | damp |
|------:|-------------------|-----------------|-----:|
| 0     | Very light reverb | 0.70 (45875)    | 100  |
| 1     | Light reverb      | 0.80 (52429)    | 80   |
| 2     | Medium reverb     | 0.88 (57672)    | 60   |
| 3     | Heavy reverb      | 0.94 (61604)    | 40   |
| 4 … 15 | Custom           | REVERB_SIZE (0x1F) | REVERB_DAMP (0x20) `[7:0]` |

The mapping is in `gme_core`; `FX_chain` and the reverb block take size and damp. The block limits
the size to 0.98 (stable tail). Switching the type, size or damp glides over about 30 ms
(`param_smooth`), the reverb on / off crossfades like every other effect. Up to VERSION 0x0205 the old
Schroeder reverb used type 0 … 3 and treated other values as 3; since 0x0206 types 5 … 15 act like 4.

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

### (6) Modulated delay (step D2): chorus, flanger, vibrato

One block (effect enable bit 4) with a fractional delay
`MOD_BASE ± MOD_DEPTH · LFO` samples, feedback MOD_FB and mix (register 10):

| Use | MOD_BASE | Depth (11) | Rate (12) | MOD_FB | Mix (10) |
|-----|----------|------------|-----------|--------|----------|
| Chorus | 720 (15 ms) | 144 (3 ms) | 80 (0.8 Hz) | 0 | 128 |
| Flanger | 96 (2 ms) | 90 | 30 (0.3 Hz) | 26000 (+0.8) | 128 |
| Vibrato | 240 (5 ms) | 100 | 600 (6 Hz) | 0 | 255 |

(`gme_hps.py preset chorus | flanger | vibrato`)

### (7) Cabinet FIR (step D3)

A 2048-tap FIR (42.7 ms at 48 kHz, `cab_fir.vhd`), enable bit 6; in the default order between distortion and EQ.
Two coefficient banks of 2048 × 18-bit signed values (Q1.17 scaled up by 2^shift, block floating
point, built by `tools/cab_coefs.py`); output `y = sat(Σ h[k]·x[n−k] >> (17 + shift))`. Bank 0
holds the default cabinet (cabinet 0, shift 3) at power-up, bank 1 is zero. The cabinet adds one
frame (20.8 µs) of latency when it is on (the stage output is its input when it is off), see [(11)](#11-effect-order-step-e).

| Register | Meaning |
|----------|---------|
| CAB_CTRL (0x1B) | bit0 = bank to play; `[3:1]` = shift of bank 0; `[6:4]` = shift of bank 1 (0 … 7) |
| CAB_ADDR (0x1C) | bit11 = bank, `[10:0]` = tap address of the next coefficient write |
| CAB_DATA_LO (0x1D) | coefficient bits 15..0 |
| CAB_DATA_HI (0x1E) | coefficient bits 17..16; the write of `{HI, LO}` happens when this register is written, the tap address then increments (it wraps inside the bank) |

Loading a cabinet (`gme_hps.py cab N` does this): write CAB_ADDR = `bank << 11` for the idle bank, then
for every tap write CAB_DATA_LO and CAB_DATA_HI, then CAB_CTRL with the new bank bit and its shift.

* **Writes to the active bank are ignored** (a playing cabinet is never disturbed). "Active" is the bank
  in use *and* the requested one: while a switch is running (about 5 ms) neither bank accepts writes, so wait
  about 10 ms after a switch before loading the next cabinet. The pointer still increments for ignored writes.
* **Switching** (CAB_CTRL bit0 changes): the cabinet level fades out over 128 samples, the bank (and its
  shift) switches, it fades back in over 128 samples. Enabling / disabling the effect fades over 256 samples
  like every effect. The shift of the playing bank may be changed any time (it steps the gain at the next
  sample); set the idle bank's shift before switching to it.
* The register side effects (pointer, write) happen on a write that contains byte 1 (like CODEC): use
  32-bit or halfword stores, or store byte 0 before byte 1. CAB_DATA_HI only has bits `[1:0]` but must be
  written with a 16-bit or 32-bit store (or byte 0 followed by byte 1) to trigger the write.
* Coefficient files for the board: `python3 tools/cab_coefs.py --build` writes `ir/build/cabNN.coef`
  (git-ignored; third-party IR files are never committed), copy them to the board, then
  `gme_hps.py cab list | cab N | cab on | cab off`.

### (8) Dynamics (step D5)

Noise gate and compressor in one block (`dynamics.vhd`, one level detector, one gain multiplier), the **first** stage of
the default chain order (enable bit 7). `DYN_CTRL` bit 0 switches the gate, bit 1 the compressor; with both off and bit 7 on the stage
is a transparent one-sample delay. Levels are in **Q8 log2 units**: 1 unit = 1/256 of a factor 2 = 0.0235 dB,
register value = dB × 42.52 (signed 16-bit two's complement), e.g. −20 dBFS = −850 (`0xFCAE`), −45 dBFS = −1913,
+6 dB make-up = 255.

* **Detector:** peak follower on |x|, attack 4 samples, release 43 ms; a sine reads about 0.1 dB under its peak.
* **Compressor** (above `COMP_THRESH`): reduction = over − over/ratio (shift-based: 2:1, 4:1, 8:1; ∞:1 = over), limited to 95.9 dB;
  gain = make-up − reduction. The gain is smoothed in the log domain (linear-in-dB glide): attack time constant 2^`COMP_ATTACK`
  samples when the gain falls, 2^`COMP_RELEASE` when it rises. Switching the compressor off glides the reduction and the
  make-up to 0 dB at the release speed, then the stage is an exact pass-through.
* **Gate:** opens at level ≥ `GATE_THRESH`, closes below it − 3 dB (hysteresis, no chatter); closing glides the attenuation
  to −84 dB in 50 ms, opening takes 1 ms. Switching the gate off glides it open in 1 ms.
* **Smoothing:** the gain itself glides (attack / release / gate speeds above), so register changes do not click.
  Thresholds, ratio, make-up and the times are **not** smoothed further: they take effect at the next sample and act through
  the gain glide.
* **DYN_GR (0x2C):** `max(0, −compressor exponent) + gate attenuation`, i.e. the net reduction in Q8 log2 units (make-up counts
  against it), updated every sample, 0 while the stage is off. Read-only.
* Board tool: `gme_hps.py set effects=DYN dyn=gate+comp gate_db=-45 comp_db=-20 ratio=4 makeup_db=3 attack_ms=2 release_ms=100`.

### (9) EQ (step D5)

Three biquad sections in series (`eq3.vhd`): low shelf (100 Hz), peaking mid (800 Hz, Q 0.9), high shelf (3.5 kHz),
−12 … +12 dB each (`tools/eq_coefs.py`, RBJ cookbook), enable bit 8; in the default order between the cabinet and the modulated delay.
The coefficients come from the host (Q2.16, 18 bit): 15 signed coefficients, section × 5 + (b0 b1 b2 a1 a2), then address 15 =
**scale word** (2 bits per section, section 0 in bits 1:0: the section's feed-forward sum is multiplied by 2^n, needed by a
boosting shelf whose b0 exceeds 2). Power-up: transparent.

To load a set: write `EQ_ADDR` = 0; for each of the 16 words write `EQ_DATA_LO` then `EQ_DATA_HI` (the pointer increments); then write
`EQ_APPLY`. The writes go to shadow registers; only `EQ_APPLY` makes the whole set (all three sections and the scale word) active, at
the next half-frame strobe, so a half-written set is never used and the three sections never change at different samples. Like all
registers with side effects, the writes must contain byte 1 (32-bit or halfword stores). The pointer wraps from 15 to 0.
Board tool: `gme_hps.py eq BASS MID TREBLE` (dB), `gme_hps.py eq off`.

### (10) Output level of the overdrive and distortion (step D6)

`OD_LEVEL` (0x2D) and `DIST_LEVEL` (0x2E) set the loudness of the effect's wet path, in the same **Q8 log2 units** as the dynamics
registers: a signed 16-bit value *L* means a gain of 2^(*L*/256) (dB = *L* × 6.0206 / 256; −1020 = −24.0 dB, −256 = −6.02 dB, 0 = 0 dB,
+256 = +6.02 dB, +512 = +12.04 dB; the range −1024 … +512 is enforced by clamping). **0 is exactly unity**: the output is bit-identical
to the one without the stage (all older references stay bit-exact).

* **Where:** overdrive: after the clipping and the `OD_GAIN` multiplication, before the saturation to the sample width
  (`y = sat(floor(clipped × gain × G))`). Distortion: on the magnitude of the shaped value (table output), before the sign is restored
  and before the dry/wet mix, limited to ±(2^(DW−1) − 1) (`golden.py`). With the effect off (or in its fade) nothing changes.
* **Gain:** *G* = mantissa × 2^*n* / 2^16, *n* = *L* ≫ 8, mantissa = round(2^(frac/256) × 65536) from a 256-entry table
  (`level_gain.vhd`, accuracy: the table rounding, < 0.0001 dB; the gain step per register unit is 0.0235 dB). One multiplier per effect.
* **Smoothing:** each level goes through `param_smooth` in offset binary like `MOD_FB` (time constant 128 frames, exact after about
  1600), so a change glides linearly in dB and never clicks. The smoothers start at unity (not at −24 dB) after reset.
* **Presets:** `gme_hps.py` presets carry the levels that make them as loud as the clean signal (`tools/level_presets.py`).
  Board tool: `gme_hps.py set od_db=-3 dist_db=-6` (dB) or `od_level=… dist_level=…` (raw values).

### (11) Effect order (step E)

**Encoding.** Each effect has a fixed id, the number of its enable bit in register 0 (so software uses one id table):

| Id | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|----|---|---|---|---|---|---|---|---|---|
| Effect | Overdrive | Tremolo | Echo | Distortion | Chorus / flanger / vibrato | Reverb | Cabinet | Dynamics | EQ |

The order is a list of the nine ids, **slot 0 (the first effect the signal passes) first**, one id per 4-bit nibble:
`CHAIN_0` = slots 0 … 3 (slot 0 in bits 3:0), `CHAIN_1` = slots 4 … 7, `CHAIN_2` = slot 8 (bits 3:0). The value of the whole
list is Σ id(slot k) · 16^k. The reset (and power-up) order is today's chain, `Dynamics, Overdrive, Distortion, Cabinet, EQ,
Chorus, Tremolo, Echo, Reverb` = ids `7 0 3 6 8 4 1 2 5` = `CHAIN_0 = 0x6307`, `CHAIN_1 = 0x2148`, `CHAIN_2 = 0x0005` (the first
registers that do not reset to 0; a reset of the FPGA restores them). Example, Reverb first and Dynamics last of the
default list: ids `5 0 3 6 8 4 1 2 7` → `CHAIN_0 = 0x6305`, `CHAIN_1 = 0x2148`, `CHAIN_2 = 0x0007`.

**Applying.** The three registers are shadow registers: writing them changes nothing audible. A write to `CHAIN_APPLY` (0x33; any
value; like all registers with side effects the write must contain byte 1, i.e. a 32-bit or halfword store) checks the list and starts
the change:

* **Validation in hardware:** the list must be a permutation of 0 … 8 (every id once, no nibble above 8). Otherwise nothing changes
  (a running order change goes on), the status bit 1 (`rejected`) is set, and no fade starts. A valid apply clears bit 1. A bad write
  can therefore never route nothing to the output or feed an effect twice.
* **Fade:** the chain output fades to 0 over 128 samples (2.7 ms), the new order is switched in at the zero, then the output fades back in over 128
  samples (total dip about 5.3 ms, no click). The effects' own states (echo, reverb and modulation tails, the cabinet history, the
  compressor) keep running; only the place in the chain changes. An apply during the fade replaces the list that is waiting.
* **Status:** reading `CHAIN_APPLY` gives bit 0 = `busy` (from the write of `CHAIN_APPLY`, also for a read right behind it, until the output is back to full level; poll it until it is 0, then read bit 1),
  bit 1 = `rejected`. Writes are not stored. `CHAIN_0 … 2` read back what was written (the list that is *written*, not necessarily
  the one in use).

**Off effects keep their place:** an effect whose enable bit is 0 still sits in its slot and passes its input on (through its own
crossfade), so switching an effect on or off never changes the order or moves the signal in time by more than the effect's own delay.

**Latency.** The chain input is registered once per frame, and every effect has an output register in its slot, so the signal takes a
fixed number of frames per stage, **the same for every order** (measured with an impulse, `test_fx_chain::test_latency`; 1 frame = 20.83 µs):

| Stage (effects off) | frames |
|---------------------|-------:|
| Dynamics, Cabinet, EQ | 1 each |
| Chorus / flanger / vibrato, Tremolo, Echo, Reverb (strobe at half-frame) | 1 each |
| Overdrive, Distortion (strobe at the frame start, one extra register) | 2 each |
| **Total, all effects off** | **11 frames = 229 µs** |

An effect that is **on** adds its own delay: Overdrive, Distortion and the Cabinet one more frame each (Dynamics, EQ, modulation,
tremolo, echo and reverb: none), so at most **14 frames = 292 µs** with everything on (about 10 cm of sound travel; before step E:
4 frames with everything off). The numbers do not depend on the order, because the sum over all nine slots is the same.
Board tool (step E4): `gme_hps.py chain`, `gme_hps.py chain dyn od dist cab eq mod trem echo reverb`, `gme_hps.py chain reset`.
