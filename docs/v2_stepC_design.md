# v2 step C: fixed-point library, 24-bit effects, parameter smoothing

**Status:** done: verified in simulation, timing met, and **tested on the board** (2026-10-25,
JTAG `.sof`: VERSION 0x0202, presets switch without clicks, level/mix changes glide,
all effects, meter and codec writes OK).

Goal: the whole effect chain processes **24-bit** samples (the codec's full
resolution, was 16), user parameters change **without zipper noise**, and
switching an effect on or off **does not click**. The effect algorithms stay
the same (better DSP blocks are step D).

## Design

### C1: fixed-point library (`fx_pkg.vhd`)

Width-generic helpers on `signed` (VHDL `integer` is 32-bit, too small for
24 × 16-bit products):

| Function | Meaning |
|----------|---------|
| `sat(x, W)` | clamp a signed value of any width to W bits |
| `mul_shr(x, k, s)` | `floor(x · k / 2^s)`, x signed, k unsigned (the v1 `result(31 downto 16)` slices) |
| `smul_shr(x, k, s)` | same with signed k |
| `add_sat(a, b, W)` | saturating add |
| `div_pow2(x, s)` | `x / 2^s` truncated toward zero (v1's integer `/ 64`) |
| `mix8(dry, wet, m, W)` | `floor((m · wet + (255 − m) · dry) / 256)` |

Unit test: a small wrapper entity exposes every function; cocotb drives random
and corner vectors (±full scale, 0, −1) for W = 16 and 24 and compares with
Python.

### C2: width-generic effects (`DW` = 16 or 24)

Every effect gets a generic `DW`. The arithmetic is written so that it does
not depend on the width (shifts relative to the parameter scale, not to the
sample width):

| Effect | 24-bit form (S = DW − 16) |
|--------|---------------------------|
| Overdrive | clip at `drive · 2^S`, × gain, `sat(DW)` |
| Distortion | table address `min(|x| / 2^S, 16383)`, table value × 2^S, `mix8` |
| Chorus / echo / combs / all-pass | delay lines DW wide; `mul_shr(x, level, 16)` etc. unchanged |
| Tremolo | `mul_shr(x, lfo, 16)`, `mix8` |
| Reverb | input / 4, saturating sums, `mix8` |

**With DW = 16 every effect is bit-exact to v1**, so the 27 recorded v1
references keep checking the arithmetic after the rewrite. With DW = 24 the
same formulas carry 8 more bits.

Delay lines: one generic RAM entity `fx_dpram` (altsyncram, simple dual port,
same settings as the proven wrappers, generic width/depth) replaces the four
16-bit RAM wrappers. The echo line becomes 32 k words (the register only reaches
32767 samples; the 64 k line wasted half): 32 k × 24 bit fits in fewer M10K
blocks than 64 k × 16 did, so 24-bit delay lines fit the device.

### C3: parameter smoothing and click-free bypass

* **`param_smooth`** between the register file and the chain, for the
  continuous parameters (drive, depths, levels, mixes, repeat): one-pole
  `y += (target − y) / 2^7` per sample with 8 extra fraction bits and a final
  ±1 step, so it reaches the target exactly. Time constant 128 samples
  (2.7 ms); a full-scale step is exact after about 1700 samples (36 ms).
  Selectors (types, waveforms, enables) and delay times are not
  smoothed (delay-time changes need interpolated delay lines, step D).
* **Bypass crossfade:** when an enable bit changes, the effect's output fades
  between the dry and the processed signal over 256 samples (5.3 ms). The effect
  keeps running until the fade-out is complete. In the steady state the output is
  exactly the effect output (on) or the dry signal (off).
* Both are generics of `FX_chain` / `gme_core` (off for the v1 reference tests).

### I/O

`gme_core`: ADC 24 bits → chain → DAC 24 bits (was `rx(23:8)` and `fx & x"00"`).
Level meters stay 16-bit (top bits). VERSION `0x0202`.

## Verification

| Test | Check |
|------|-------|
| `test_fxlib` (new) | every library function, W = 16 / 24, against Python |
| `test_reference` | DW = 16 chain still bit-exact to the 27 v1 recordings |
| `test_fx_chain` | the 7 effect tests at DW = 16 (unchanged) and at DW = 24 (golden overdrive/distortion generalised to 24 bits) |
| `test_ref24` (new) | DW = 24 vs DW = 16 for the 27 presets, input with 16 significant bits: difference within the 16-bit rounding noise of v1 (error RMS < −80 dBFS, peak bounded) |
| `test_smooth` (new) | smoother reaches every target exactly, monotonic, time constant; crossfade: no step larger than the signal, exact steady state |
| `test_system` | end to end with 24-bit audio (bit-exact for bypass and overdrive) |
| `test_wav` | real guitar through the 24-bit chain: no wrap-around, no clicks |

## Results

**Simulation** (`sim/run_all.sh`, 12 suites, all pass):

| Test | Result |
|------|--------|
| `test_fxlib` | 20 049 vectors × 8 functions bit-exact (corner cases ±full scale, 0, −1) |
| `test_reference` (DW = 16) | all 27 v1 presets **bit-exact**: the width-generic rewrite does not change the v1 arithmetic |
| `test_ref24` | full 24-bit random input bit-exact for bypass, overdrive and 3 distortion curves × 2 mixes; the 27 v1 presets on the 24-bit chain within **14.5 LSB peak / 6.4 LSB rms** (16-bit LSB) of v1: bypass, overdrive 0, distortion ≤ 1, tremolo / chorus ≤ 3, echo ≤ 4.3, reverb ≤ 8.5, all effects 11.6. That is v1's own 16-bit truncation noise, which the 24-bit chain does not have |
| `test_fx_chain` / `_24` | the 7 effect tests pass on both widths |
| `test_smooth` | bit-exact to the Python model, 63 % of a step after 128 samples, every target exact |
| `test_xfade` | on/off: largest step 75 k vs. 2.24 M for a hard switch (24-bit units); dry / wet steady states exact |
| `test_system` | bypass and overdrive bit-exact **at 24 bits** end to end (I²S in → effects → I²S out) |
| `test_wav` | 8 presets of real guitar audio on the 24-bit chain: no X, no wrap-around, dry bit-exact, no tremolo clicks |

IP models: `sim/models/run_equiv.sh` (ModelSim, `altera_mf`): the 11 ROMs and
`fx_dpram` in all 6 configurations used, 20 000 random cycles, 0 mismatches.

**Quartus Prime Lite 18.1:** 0 errors, timing met (sys_clk setup +7.3 ns, hold +0.22 ns;
worst overall +0.077 ns in the HPS DDR3 PHY). 1 649 ALMs (5 %), 305 M10K (was 324),
2.53 Mbit (was 2.65), 25 DSP blocks (was 35).

**Found on the way:**
* `resize` of a `signed` to fewer bits keeps the sign bit: the smoother lost its top
  bit above half scale (caught by `test_smooth`, fixed with a slice).
* The echo line size is visible only with `echo_time = 0` (read and write at the
  same address return the word one ring ago: 0.68 s with 32 k words, 1.36 s in v1).
  The v1 reference test therefore runs with the v1 size (`ECHO_AW = 16`).
