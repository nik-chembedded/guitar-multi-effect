# Guitar Multi-Effect: FPGA (VHDL) on the DE1-SoC

A real-time multi-effect processor for electric guitar, implemented in VHDL on an
Intel **Cyclone V** SoC. **v2** (this branch, `main`) processes the audio entirely in
FPGA logic: one 49.152 MHz clock domain, the FPGA as I²S master, the codec configured
over I²C by RTL. **Linux on the on-chip ARM (HPS)** controls the effects through the
lightweight HPS-to-FPGA bridge. There is no soft CPU.

> **Target hardware:** Terasic **DE1-SoC** board (Cyclone V SE **5CSEMA5F31C6**,
> on-board WM8731 audio codec).
> Tool chain: **Quartus Prime Lite 18.1**; simulation with **GHDL + cocotb**
> (WSL2 / GitHub Actions) and ModelSim-Intel Starter 10.5b.

* **v1** (branch `v1`, tag `v1.0`): the original 2021–2022 design (Nios II + C# GUI)
  with its bugs fixed. See [docs/FIXES.md](docs/FIXES.md).
* **v2** (`main`): the plan and progress are in [docs/v2_plan.md](docs/v2_plan.md);
  step B (clocking, I²S, control without the Nios II) is in
  [docs/v2_stepB_design.md](docs/v2_stepB_design.md), the HPS control in
  [docs/v2_hps_control.md](docs/v2_hps_control.md). The UART-controlled version is at the tag `v2-uart`.

## Effects

| Effect     | Implementation                                                          | Parameters |
|------------|-------------------------------------------------------------------------|------------|
| Overdrive  | Hard clipping at a threshold, then gain (saturating)                    | drive, gain |
| Distortion | Waveshaping with ROM transfer curves (soft / medium / heavy)            | type, mix |
| Cabinet    | 2048-tap FIR (42.7 ms) with two coefficient banks: 10 selectable cabinet impulse responses (step D3) | cabinet 0 … 9 |
| Chorus     | Modulated delay line (triangle LFO) with feedback                       | rate, depth, level |
| Tremolo    | Amplitude modulation by a smoothed ROM LFO (sine 5–15 Hz, triangle, saw) | waveform, depth |
| Echo       | Delay line up to ~0.68 s with feedback                                  | time, level, repeat |
| Reverb     | Freeverb: 8 parallel low-pass-feedback comb filters + 4 series all-pass filters (step D4) | type (4 rooms or custom), size, damping, mix |

Signal chain: `ADC → Overdrive → Distortion → Cabinet → Chorus → Tremolo → Echo → Reverb → DAC`.
The cabinet (enable bit 6) is off by default and costs no latency when off; when on it adds one sample.
Cabinets are loaded from Linux with `gme_hps.py cab N` (coefficient files built on the PC by
`tools/cab_coefs.py --build`, third-party IR files are never committed).
The I/O is 48 kHz stereo 24-bit and the effects process **24-bit** samples (v2 step C);
the chain is mono and the processed signal goes to both outputs. Parameter changes
are smoothed (no zipper noise) and switching an effect on or off crossfades over
5 ms (no clicks).

## Architecture (v2)

```
CLOCK_50 ─► PLL ─┬─ sys_clk 49.152 MHz ─► all logic (gme_core) + HPS bridge
                 └─ MCLK 12.288 MHz ────► codec
HPS (ARM, Linux) ── lightweight bridge 0xFF200000 ── hps_sys (Platform Designer) ─┐
gme_core:  i2s_core (FPGA = I2S master, BCLK/LRCLK, sample_tick/half_tick)       │
           FX_chain (effects, advance on the strobes)                            │
           ctrl_avmm (Avalon-MM slave + register file + CODEC register)  ◄───────┘  tools/gme_hps.py
           codec_ctrl (I2C master + codec init ROM)        ──► codec I2C
```

Diagrams of v1 and the planned v2 with the HPS are in [docs/architecture.md](docs/architecture.md).

## Repository layout

```
fpga/                    Quartus project (My_Audio.qpf / .qsf), top level top_v2
  top_v2.sdc             timing constraints (one clock, multicycle effect paths)
  hps_sys.qsys           Platform Designer system: HPS + bridge to our registers
  hps/                   script that builds hps_sys.qsys from Terasic's GHRD
  rtl/                   VHDL: top_v2, gme_core, i2s_core, effects, FX_chain,
                         ctrl_avmm, reg_file, i2c_master, codec_ctrl, fx_pkg;
                         pll_sys.v (altera_pll)
  ip/                    Intel RAM/ROM wrappers + .mif tables
sim/
  cocotb/                Python tests (GHDL): effects, v1 bit-exact reference,
                         I2S, HPS control slave, I2C/codec, full system, WAV audio
  models/                behavioural models of the Intel IP (+ equivalence proof)
  tb/, run_wav.sh        ModelSim frame-level WAV testbench
  audio/                 guitar test recordings (CC BY-SA)
tools/gme_hps.py         control tool, runs on the board's Linux (Python)
docs/                    plan, step-B design, register map/protocol, fixes, diagrams
```

## Board setup (DE1-SoC)

| Signal | Board | Notes |
|--------|-------|-------|
| `CLOCK_50` | PIN_AF14 | |
| `KEY0` | KEY[0] (PIN_AA14) | press = reset |
| Audio | LINE IN (blue) / LINE OUT (green) | codec configured automatically after reset |
| HPS | Ethernet / USB-UART console | Linux from Terasic's SD card (MSEL `01010`), log in as root |
| `LEDR[0..3]` | V16, W16, V17, V18 | PLL locked, codec init done, codec NAK, 1 Hz heartbeat |

## Building

```bash
cd fpga
qsys-generate hps_sys.qsys --synthesis=VERILOG --output-directory=hps_sys --family="Cyclone V" --part=5CSEMA5F31C6
quartus_sh --flow compile My_Audio        # or open My_Audio.qpf in Quartus 18.1
quartus_cpf -c -o bitstream_compression=off output_files/my_audio.sof output_files/soc_system.rbf
```

Program `output_files/my_audio.sof` over JTAG while Linux runs, or put
`soc_system.rbf` on the SD card (details: [docs/v2_hps_control.md](docs/v2_hps_control.md)).
Then, on the board:

```bash
python gme_hps.py status
python gme_hps.py preset crunch
python gme_hps.py set effects=DIST+ECHO dist_type=2 echo_time=14400
python gme_hps.py meter
```

The registers are documented in [docs/register_map.md](docs/register_map.md).

## Simulation

**cocotb + GHDL** (WSL2 Ubuntu or Linux, also run by GitHub Actions on every push).
See [sim/cocotb/README.md](sim/cocotb/README.md):

```bash
sim/run_all.sh          # or from Windows: sim\run_all.cmd   (quick | full | -k EXPR | --waves)
```

The suite includes a **bit-exact comparison against v1** (27 recorded presets),
unit tests of every new block, and an end-to-end system test (codec init over I²C →
settings over the HPS bridge → audio over I²S).

### Example: a test run

```
> sim\run_all.cmd quick
ghdl: GHDL 5.0.1 (Ubuntu 5.0.1+dfsg-1ubuntu1) [Dunoon edition]
cocotb: 2.1.0, build dir: /home/nikita/build/gme
selection: test_fx_chain or test_i2s or test_avmm or test_codec or test_system
 TESTS=7 PASS=7 FAIL=0 SKIP=0     effect chain (bypass, overdrive, distortion, tremolo, chorus, echo, reverb)
 TESTS=4 PASS=4 FAIL=0 SKIP=0     I2S master core
 TESTS=5 PASS=5 FAIL=0 SKIP=0     HPS control slave (Avalon-MM)
 TESTS=4 PASS=4 FAIL=0 SKIP=0     I2C master + codec init sequencer
 TESTS=3 PASS=3 FAIL=0 SKIP=0     gme_core end to end
=========== 5 passed, 2 deselected in 117.72s (0:01:57) ===========
```

(The descriptions after each `TESTS=` line are added here for readability; the
script prints simulated time and speed in their place.)

### Example: what one test does

`test_system.test_overdrive_via_hps` ([sim/cocotb/test_system.py](sim/cocotb/test_system.py))
simulates the whole design (`gme_core`) with Python models of the codec (I²S and I²C)
and of the HPS bridge (an Avalon-MM master):

1. **Power-up:** the RTL configures the codec by itself; the I²C slave model records
   the 15 register writes and ACKs them.
2. **Wait for the codec:** the test reads the STATUS register until bit 0
   (codec init done) is set.
3. **Configure the effect over the bridge:** write `od_drive = 3000`, `od_gain = 4`,
   `effects_enable = OD`, as Linux would at `0xFF200000 + 4·n`.
4. **Stream audio:** the codec model sends 60 frames of random 24-bit stereo samples
   over I²S and records what the FPGA sends back.
5. **Check:** every output frame, left and right, must equal the Python reference
   `golden.overdrive(x, 3000, 4)`, i.e. clip to ±3000, ×4, saturate, **bit for bit**
   (the expected latency is 8 frames). The input/output level registers are read
   back over the bridge as well.

```
cocotb.gme_core   overdrive set over the bridge, output bit-exact, latency 8; levels in 29405 / out 12456
test_system.test_overdrive_via_hps      PASS
```

A step-by-step description of the flow (pytest → GHDL → cocotb → RTL → checks) is in
[sim/cocotb/README.md](sim/cocotb/README.md).

**ModelSim:** real guitar recordings through the effect chain (`sim/run_wav.sh`),
and the equivalence proof of the IP models (`sim/models/run_equiv.sh`).

## Status

* v2 step A (verification) and step B (single clock, I²S master, codec I²C, new top
  level) are done; audio LINE IN → LINE OUT works on the board.
* Control moved from UART to the HPS (Linux): verified in simulation and **on the
  board** (registers, presets, level meters, codec writes from Linux). 4 % of the logic.
* Step C (fixed-point library, 24-bit effects, parameter smoothing, click-free
  on/off) is done: verified in simulation and **on the board**; timing met, 5 % of the logic. See [docs/v2_stepC_design.md](docs/v2_stepC_design.md).
* Step D (better DSP blocks, [docs/v2_stepD_design.md](docs/v2_stepD_design.md)) in progress: D1 generated LFO
  done in simulation (frees 66 M10K); D2 modulated delay done; **D3 cabinet FIR integrated** (`cab_fir`/`cab_stage`
  in the chain, CAB registers 0x1B–0x1E, `gme_hps.py cab`); **D4 Freeverb reverb integrated** (`reverb_fv`
  replaces the Schroeder reverb, REVERB_TYPE 0–3 room presets, 4 = custom, registers 0x1F REVERB_SIZE /
  0x20 REVERB_DAMP, VERSION 0x0206): verified in simulation, timing met in
  Quartus (see [docs/v2_stepD_design.md](docs/v2_stepD_design.md)); next D5–D6. Board test at the end of step D.

## Third-party code

* `fpga/ip/*` wrappers are generated by Intel Quartus MegaWizard / IP Catalog.
* `fpga/hps/ghrd_soc_system.qsys` is Terasic's DE1-SoC Golden Hardware Reference Design
  (DE1-SoC System CD); `hps_sys.qsys` is derived from it.
* `sim/audio/*.wav`: CC BY-SA 4.0 recordings, see [sim/audio/README.md](sim/audio/README.md).
