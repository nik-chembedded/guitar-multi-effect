# Guitar Multi-Effect: FPGA (VHDL) on the DE1-SoC

A real-time multi-effect processor for electric guitar, implemented in VHDL on an
Intel **Cyclone V** FPGA. **v2** (this branch, `main`) runs entirely in FPGA logic:
one 49.152 MHz clock domain, the FPGA as I²S master, the codec configured over I²C
by RTL, and a framed UART protocol for the host. There is no CPU.

> **Target hardware:** Terasic **DE1-SoC** board (Cyclone V SE **5CSEMA5F31C6**,
> on-board WM8731 audio codec).
> Tool chain: **Quartus Prime Lite 18.1**; simulation with **GHDL + cocotb**
> (WSL2 / GitHub Actions) and ModelSim-Intel Starter 10.5b.

* **v1** (branch `v1`, tag `v1.0`): the original 2021–2022 design (Nios II + C# GUI)
  with its bugs fixed. See [docs/FIXES.md](docs/FIXES.md).
* **v2** (`main`): the plan and progress are in [docs/v2_plan.md](docs/v2_plan.md);
  step B (clocking, I²S, control without the Nios II) is in
  [docs/v2_stepB_design.md](docs/v2_stepB_design.md).

## Effects

| Effect     | Implementation                                                          | Parameters |
|------------|-------------------------------------------------------------------------|------------|
| Overdrive  | Hard clipping at a threshold, then gain (saturating)                    | drive, gain |
| Distortion | Waveshaping with ROM transfer curves (soft / medium / heavy)            | type, mix |
| Chorus     | Modulated delay line (triangle LFO) with feedback                       | rate, depth, level |
| Tremolo    | Amplitude modulation by a smoothed ROM LFO (sine 5–15 Hz, triangle, saw) | waveform, depth |
| Echo       | Delay line up to ~0.68 s with feedback                                  | time, level, repeat |
| Reverb     | Schroeder reverb: 4 parallel comb filters + 2 series all-pass filters   | type (4 rooms), mix |

Signal chain: `ADC → Overdrive → Distortion → Chorus → Tremolo → Echo → Reverb → DAC`.
The I/O is 48 kHz stereo 24-bit; the effects are 16-bit mono until v2 step C, and the
processed signal goes to both outputs.

## Architecture (v2)

```
CLOCK_50 ─► PLL ─┬─ sys_clk 49.152 MHz ─► all logic (gme_core)
                 └─ MCLK 12.288 MHz ────► codec
gme_core:  i2s_core (FPGA = I2S master, BCLK/LRCLK, sample_tick/half_tick)
           FX_chain (effects, advance on the strobes)
           ctrl_block (UART frame parser + register file)  ◄── PC: tools/gme_ctl.py
           codec_ctrl (I2C master + codec init ROM)        ──► codec I2C
```

Diagrams of v1 and the planned v2 with the HPS are in [docs/architecture.md](docs/architecture.md).

## Repository layout

```
fpga/                    Quartus project (My_Audio.qpf / .qsf), top level top_v2
  top_v2.sdc             timing constraints (one clock, multicycle effect paths)
  rtl/                   VHDL: top_v2, gme_core, i2s_core, effects, FX_chain,
                         uart_rx/tx, ctrl_uart, reg_file, ctrl_block,
                         i2c_master, codec_ctrl, fx_pkg; pll_sys.v (altera_pll)
  ip/                    Intel RAM/ROM wrappers + .mif tables
sim/
  cocotb/                Python tests (GHDL): effects, v1 bit-exact reference,
                         I2S, UART control, I2C/codec, full system, WAV audio
  models/                behavioural models of the Intel IP (+ equivalence proof)
  tb/, run_wav.sh        ModelSim frame-level WAV testbench
  audio/                 guitar test recordings (CC BY-SA)
tools/gme_ctl.py         host control tool (UART, Python)
docs/                    plan, step-B design, register map/protocol, fixes, diagrams
```

## Board setup (DE1-SoC)

| Signal | Board | Notes |
|--------|-------|-------|
| `CLOCK_50` | PIN_AF14 | |
| `KEY0` | KEY[0] (PIN_AA14) | press = reset |
| Audio | LINE IN (blue) / LINE OUT (green) | codec configured automatically after reset |
| `UART_RX` / `UART_TX` | GPIO_0 D0 (AC18) / D1 (Y17) | external **3.3 V** USB-UART adapter, 115200 8N1 |
| `LEDR[0..3]` | V16, W16, V17, V18 | PLL locked, codec init done, codec NAK, 1 Hz heartbeat |

## Building

```bash
cd fpga
quartus_sh --flow compile My_Audio        # or open My_Audio.qpf in Quartus 18.1
```

There is no Platform Designer system and no software to build. Program
`output_files/My_Audio.sof`, then control the board from the PC:

```bash
pip install pyserial
python tools/gme_ctl.py -p COM5 ping
python tools/gme_ctl.py -p COM5 status
python tools/gme_ctl.py -p COM5 preset crunch
python tools/gme_ctl.py -p COM5 set effects=DIST+ECHO dist_type=2 echo_time=14400
```

The registers and the protocol are documented in [docs/register_map.md](docs/register_map.md).

## Simulation

**cocotb + GHDL** (WSL2 Ubuntu or Linux, also run by GitHub Actions on every push).
See [sim/cocotb/README.md](sim/cocotb/README.md):

```bash
sim/run_all.sh          # or from Windows: sim\run_all.cmd   (quick | full | -k EXPR | --waves)
```

The suite includes a **bit-exact comparison against v1** (27 recorded presets),
unit tests of every new block, and an end-to-end system test (codec init over I²C →
settings over UART → audio over I²S).

### Example: a test run

```
> sim\run_all.cmd quick
ghdl: GHDL 5.0.1 (Ubuntu 5.0.1+dfsg-1ubuntu1) [Dunoon edition]
cocotb: 2.1.0, build dir: /home/nikita/build/gme
selection: test_fx_chain or test_i2s or test_ctrl or test_codec or test_system
 TESTS=7 PASS=7 FAIL=0 SKIP=0     effect chain (bypass, overdrive, distortion, tremolo, chorus, echo, reverb)
 TESTS=4 PASS=4 FAIL=0 SKIP=0     I2S master core
 TESTS=5 PASS=5 FAIL=0 SKIP=0     UART control block (1.536 Mbaud)
 TESTS=1 PASS=1 FAIL=0 SKIP=0     UART control block, ping at 115200 baud
 TESTS=4 PASS=4 FAIL=0 SKIP=0     I2C master + codec init sequencer
 TESTS=3 PASS=3 FAIL=0 SKIP=0     gme_core end to end
=========== 6 passed, 2 deselected in 104.66s (0:01:44) ===========
```

(The descriptions after each `TESTS=` line are added here for readability; the
script prints simulated time and speed in their place.)

### Example: what one test does

`test_system.test_overdrive_via_uart` ([sim/cocotb/test_system.py](sim/cocotb/test_system.py))
simulates the whole design (`gme_core`) with Python models of the codec (I²S and I²C)
and of the PC (UART):

1. **Power-up:** the RTL configures the codec by itself; the I²C slave model records
   the 15 register writes and ACKs them.
2. **Wait for the codec:** the test reads the STATUS register over UART until bit 0
   (codec init done) is set. Every reply is checked for its `0x5A` header and its CRC-8.
3. **Configure the effect over UART:** `WRITE od_drive = 3000`, `od_gain = 4`,
   `effects_enable = OD`. Each request must be acknowledged with status `00`.
4. **Stream audio:** the codec model sends 60 frames of random 24-bit stereo samples
   over I²S and records what the FPGA sends back.
5. **Check:** every output frame, left and right, must equal the Python reference
   `golden.overdrive(x, 3000, 4)`, i.e. clip to ±3000, ×4, saturate, **bit for bit**
   (the expected latency is 8 frames). The input/output level registers are read
   back over UART as well.

```
cocotb.gme_core   overdrive set over UART, output bit-exact, latency 8; levels in 29405 / out 12456
test_system.test_overdrive_via_uart     PASS
```

A step-by-step description of the flow (pytest → GHDL → cocotb → RTL → checks) is in
[sim/cocotb/README.md](sim/cocotb/README.md).

**ModelSim:** real guitar recordings through the effect chain (`sim/run_wav.sh`),
and the equivalence proof of the IP models (`sim/models/run_equiv.sh`).

## Status

* v2 step A (verification) and step B (single clock, I²S master, UART control,
  codec I²C, new top level) are done and verified in simulation. The design meets
  timing in Quartus (4 % of the logic).
* Not yet tested on the board.
* Next: step C (fixed-point library, 24-bit effects), then D (new DSP blocks
  incl. FIR cabinet simulation).

## Third-party code

* `fpga/ip/*` wrappers are generated by Intel Quartus MegaWizard / IP Catalog.
* `sim/audio/*.wav`: CC BY-SA 4.0 recordings, see [sim/audio/README.md](sim/audio/README.md).
