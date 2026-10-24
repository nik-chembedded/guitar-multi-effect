# Bug fixes: review of the original 2022 code

This document lists the defects found in the original code (commit `4f5529b`,
*Initial import*) and what was changed. Each RTL fix is covered by a test in
`sim/` (see [sim/README.md](../sim/README.md)).

## Summary

| #  | Area      | File(s)                        | Severity | Problem | Fix |
|----|-----------|--------------------------------|----------|---------|-----|
| 1  | RTL       | `distortion.vhd`               | Critical | Output rectified: the ROM address is \|x\| but the sign was never restored, so the negative half-wave came out positive (octave-up, DC offset). | Register the sign with the address and negate the ROM output for negative input. |
| 2  | RTL       | `distortion.vhd`               | Critical | \|x\| ≥ 16384 wrapped around the 14-bit ROM address: loud input gave *low* output. | Saturate the address at 16383 (the curves are flat there). |
| 3  | RTL       | `distortion.vhd`               | Minor    | Dry and wet samples were one sample apart in the mix. | Dry sample is registered alongside the ROM address. |
| 4  | RTL       | `reverbe.vhd`, `comb_filter.vhd`, `allpass_filter.vhd` | Critical | Four combs (feedback up to 0.83, ~6× gain each) summed with no scaling, and every adder wrapped on overflow, which gave loud crackle. | Comb input attenuated ÷4 (12 dB headroom). All adders saturate. |
| 5  | RTL       | `tremolo_v2.vhd`               | Critical | `counter_5hz` declared `0 to 6857` but wraps at 9599 (ranges of the 5 and 7 Hz counters swapped). The 13-bit counter rolled over at 8191, so the 5 Hz LFO was wrong and clicked. In simulation: fatal range error. | Ranges match the table sizes. |
| 6  | RTL       | `tremolo_v2.vhd`               | Major    | 10 Hz counter wrapped at 4599, but the 10 Hz sine/triangle/saw tables hold 4800 samples: a jump every cycle (a click, and 10.4 Hz instead of 10 Hz). | Wrap at 4799. |
| 7  | RTL       | `overdrive.vhd`, `echo.vhd`, `chorus.vhd` | Major | Gain and feedback sums wrapped around (two's complement) instead of clipping. | Saturating arithmetic (`fx_pkg.sat16`). |
| 8  | RTL       | `overdrive.vhd`                | Minor    | Combinational multiply written as a process sensitive only to the clock, so simulation ≠ hardware. | Concurrent assignment. |
| 9  | RTL       | `echo.vhd`                     | Major    | Output was `dry + level·d + repeat·level·d` (feedback counted twice), and the repeat decay was multiplied by the level. | Standard feedback delay: `out = dry + level·d`, `delay_in = dry + repeat·d`. Echo *n* = level·repeat^(n-1)·x. |
| 10 | RTL       | `chorus.vhd`                   | Major    | LFO ran on a ripple clock (`clk_375`) made from a flip-flop, with `chorus_enable` (Nios clock domain) as an **asynchronous reset**. Turn-around used `=`, so lowering the depth while sweeping up let the delay run to 1023 and wrap to 0. | One synchronous process in the sample clock domain (same LFO rate), synchronous enable, `>=` / `<=` turn-around, depth clamped to the RAM size. |
| 11 | RTL       | `distortion`, `echo`, `chorus`, `comb`, `allpass`, `overdrive` | Major | Delay-line write pointers and registered integers had no initial value. The hardware powers up at 0, but simulation produced X/U (or aborted at t=0: `distortion` converted −2³¹ to an address), so **the original design could not be simulated**. | Initial values on all state registers (Quartus uses them as power-up values). |
| 12 | Timing    | `My_Audio.sdc` (new)           | Critical | No SDC file. TimeQuest only knew the JTAG clock, so the 50 MHz/Nios/SDRAM clocks and the audio clocks were never timing-checked. | Clocks, PLL clocks, codec I/O delays, asynchronous clock groups and false paths for slow I/O. |
| 13 | Platform  | `my_audio.qsys`                | Critical | Nios II/**f** is not licensed in Quartus Lite, so the design builds in *IP evaluation mode*: the `.sof` only runs while the JTAG cable is connected, and the CPU is held in reset after the evaluation time-out. | Nios II/**e** (free). Enough for UART parsing and I²C bit-banging. |
| 14 | Firmware  | `main.c`                       | Critical | `buffer_flag` / `b_index` were shared between ISR and `main()` but not `volatile`, so at `-O1`+ the main loop could miss frames. `main()` also reset `b_index` while the ISR could be mid-frame. | `volatile` state. The ISR owns the frame index and hands complete frames to `main()`, which copies them with interrupts disabled. |
| 15 | Firmware  | `main.c`                       | Critical | No framing recovery: one lost byte misaligned every following frame until reboot. | Partial frame dropped after 50 ms of silence; invalid command bytes are skipped at frame start; frames with UART framing/parity/overrun errors are dropped. |
| 16 | Firmware  | `main.c`                       | Minor    | `InitUart1(BaudRate)` ignored its argument and used the CPU clock instead of the UART clock. | Divisor from `UART_FREQ` and the argument, rounded. |
| 17 | Firmware  | `main.c`                       | Minor    | Codec init duplicated in `main()` with different volumes than the `0xEC` preset. Several effect registers (echo repeat, distortion, chorus, reverb) never initialised. | One `init_codec()` (uses the values `main()` used: line-in 0x1A, headphone 0x7A) and `init_effects()` for all 15 registers. |

| 18 | RTL       | `distortion.vhd`               | Minor (sim only) | The curve-select mux was a process sensitive only to `temp_type`, not to the three ROM outputs. Synthesis builds a correct multiplexer, but in simulation the wet signal stayed frozen at the ROM's time-0 value (0). Found by the `distortion` test. | Complete sensitivity list. |

| 19 | RTL / table | `tremolo_v2.vhd`, `ip/sawtooth_10hz_8bit.mif` | Major (audible) | Found by listening to the real-audio simulation: the sawtooth LFO table resets from 254 to 0 in one sample, so the gain dropped from 0.99 to 0.21 instantly, 10 times a second. That's an audible click, which sounds like clipping (measured 1-sample gain step 0.775; no sample was actually clipped). | Saw table regenerated with a 5 ms ramp-down instead of the instant reset (largest table step 254 → 2). The LFO also goes through a one-pole smoothing filter (time constant 32 samples ≈ 0.7 ms, 8 fractional bits kept in the multiply), which removes hard edges and 8-bit zipper steps for every waveform. Check: `sim/tools/wavconv.py clicks`. |

The GUI (`gui/`) was not changed. It will be replaced.

## Known limitations (not fixed here)

These are architectural and will be addressed in the planned redesign:

* The effect datapath is clocked directly by the codec's `AUD_DACLRCLK` pin
  (and its inversion) instead of a system clock with a sample-enable strobe.
* Effect parameters cross from the Nios clock domain to the audio domain
  without synchronisers. They are quasi-static, so the risk is a single
  glitched sample on a parameter change. The SDC declares the domains
  asynchronous.
* The ADC deserializer only works because the FIFO write happens at bit 17. Its
  bit counter wraps at 31 while the codec sends 48 BCLKs per channel.
* Mono only (right FIFO removed). The left result is sent to both DAC channels.
* LFOs are stored as eight separate ROM tables (≈ 590 kbit of block RAM).
  Block RAM utilisation is ~95 %.
* No SDRAM I/O timing constraints (I/O paths of the SDRAM controller are
  unconstrained, as in the original project).
* The chorus delay is not interpolated, so moving the delay causes zipper
  noise. The reverb combs have no damping, so it sounds metallic.
* The *soft* distortion curve has a gain below 1 (input 15000 → output ≈ 6700),
  so switching it on drops the level by about 7 dB. Found in the real-audio
  simulation; the curves need level compensation.
* The real echo delay is `echo_time + 2` samples: the dual-port RAM has a
  registered read address and a registered output (measured in the `echo` test).

## Verification

### Simulation (`sim/run_sim.sh`, ModelSim-Intel Starter 10.5b)

| Test         | Original code (`4f5529b`)                         | After fixes |
|--------------|---------------------------------------------------|-------------|
| `bypass`     | **aborts at t = 0**: `vsim-86 Argument value -2147483648 is not in bounds of subtype NATURAL` in `dist_left` (bug 11) | **PASS**: 4800 full-scale random samples bit-exact, latency 9 frames |
| `overdrive`  | not reached: same abort (distortion is always instantiated) | **PASS**: bit-exact to `clip(x, ±3000)·4`, latency 10 frames |
| `distortion` | not reached: same abort                    | **PASS**: peak 20632, DC offset −1 (symmetric), no wrap-around (input ±24000 > table range) |
| `tremolo`    | not reached: same abort                    | **PASS**: envelope 63 … 15813 over one 5 Hz LFO period (12000 frames) |
| `chorus`     | not reached: same abort                    | **PASS**: wet-copy delay sweeps 6 … 203 samples (depth 200); after lowering the depth to 50 mid-sweep the delay stays ≤ 53 (no run-away), wet = 8125 = 0.5·16000 + feedback |
| `echo`       | not reached: same abort                    | **PASS**: echo 1 = 8000, echo 2 = 4000 (exact), 1202 frames per repeat |
| `reverb`     | not reached: same abort                    | **PASS**: no wrap-around, tail decays (energy 90805 → 79972) |

The test suite itself caught two more problems on the way. The distortion
test found bug 18 (output frozen at 0 in simulation). The first echo test had
a wrong expectation: it assumed exactly 1200 frames per repeat and missed the
2-frame RAM latency, which accumulates per repeat.

### Quartus Prime Lite 18.1, full compile (after fixes)

| | Original | After fixes |
|---|---|---|
| Compile | successful | successful, 0 errors |
| Clocks analysed by TimeQuest | JTAG only | CLOCK_50/SDRAM PLL, audio PLL (MCLK), AUD_BCLK, AUD_LRCLK, JTAG |
| Worst setup slack | n/a | +10.47 ns (SDRAM/Nios PLL clock) |
| Worst hold slack | n/a | +0.108 ns (JTAG), all audio clocks > +0.2 ns |
| Nios II core | /f, **IP evaluation mode** (time-limited `.sof`) | /e, no evaluation mode (`my_audio.sof`) |
| Logic (ALMs) | 3,575 (11 %) | 1,861 (6 %) |
| Block RAM | 378 / 397 blocks (95 %) | 331 / 397 blocks (83 %) |
| DSP blocks | 38 | 35 |

The resource drop comes from the smaller CPU and from removing the SignalTap
instance in the initial import.

### Firmware

`main.c`, `I2C.c` and `debug.c` compile without warnings at `-O0` and `-O2`
(`nios2-elf-gcc` from Nios II EDS 18.1, `-Wall -Wextra`) and link against the
HAL. **Not yet tested on the board**: the BSP has to be regenerated for the
Nios II/e (`create-this-app`).
