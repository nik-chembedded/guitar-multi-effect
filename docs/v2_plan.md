# v2 plan

`main` is v2. The `v1` branch and the tag `v1.0` keep the fixed original design.
v1 is the reference: every v2 change is checked against v1's simulated outputs.
For background, see [architecture.md](architecture.md).

**Target:** Terasic DE1-SoC (Cyclone V 5CSEMA5F31C6), on-board WM8731 codec.
**FPGA toolchain:** Quartus Prime Lite **18.1** (unchanged from v1).
**Simulation:** GHDL + cocotb in WSL2 Ubuntu and GitHub Actions. ModelSim-Intel
Starter 10.5b is kept for the Intel-IP-based checks.
**Long term (phase 3):** the ARM HPS controls the whole system.

## Order of work

| Step | What | Done when |
|------|------|-----------|
| **A** | Verification infrastructure (cocotb + GHDL) | v1 tests pass under cocotb/GHDL locally and in GitHub Actions |
| **B** | Single clock domain + new I²S core + control block (Nios II removed) | Audio pass-through bit-exact in simulation; codec initialised and controlled on the board |
| **B+** | HPS control (brought forward from F): Linux writes the registers over the lightweight bridge; UART removed | Board: registers from Linux, see [v2_hps_control.md](v2_hps_control.md) |
| **C** | Fixed-point library | Unit-tested in cocotb against Python reference functions |
| **D** | Better DSP blocks | Each effect bit-exact to its Python golden model; WAV demos |
| **E** | Streaming chain with runtime routing | Any effect order selectable by register, tested |
| **F** (phase 3) | HPS / Linux control | Web UI and MIDI control the effects through the AXI bridge |

### A: Verification infrastructure  (status: done)

Done: GHDL 5 + cocotb 2.1 in WSL2 and CI, verified IP models (`sim/models`),
7 effect tests + WAV regression in `sim/cocotb` (all pass, about 30 s), GitHub Actions workflow.


* **Toolchain:** GHDL + cocotb in WSL2 Ubuntu (locally) and on GitHub Actions
  (Ubuntu), so both use the same Linux environment.
* **Behavioural models** for the Intel megafunctions (`altsyncram` RAM/ROM with
  `.mif` loading, `dcfifo`), cycle-accurate, proven bit-exact against
  `altera_mf` in ModelSim before they're used. GHDL can't use `altera_mf`.
* **Port the v1 tests to Python:** bypass, overdrive, distortion, tremolo, chorus,
  echo, reverb, plus the WAV regression and the click check.
* **Python golden models** per effect (numpy) for bit-exact comparison.
* **GitHub Actions CI:** run all tests on every push and pull request, and keep the WAV outputs as artefacts.
* ModelSim stays usable as a second simulator for the Intel-IP-based top level.

### B: Clocking, I²S and the UART control block  (status: done in simulation, board test pending)

Done: see [v2_stepB_design.md](v2_stepB_design.md). 49.152 MHz sys_clk with the FPGA
as I²S master, effects on strobes (bit-exact to v1), UART control block, codec
I²C init, `top_v2` without Nios II (timing met, 4 % logic).


* **One system clock** from a PLL (MCLK 18.432 MHz, or 49.152 MHz = 1024 × fs), with
  a one-cycle **sample tick** at 48 kHz. BCLK/LRCLK are sampled as data, so all
  logic is in one clock domain and the SDC becomes trivial.
* **I²S core:** codec master mode, 48 BCLK per channel, **stereo, 24-bit**, with
  explicit frame alignment. The datapath carries 24-bit samples.
* **UART control block (temporary, replaced by the HPS in phase 3).** It replaces Nios II,
  SDRAM, Platform Designer and the C firmware, which frees logic and RAM:
  * `uart_rx` / `uart_tx` at 115200 8N1 (configurable);
  * frame parser with a **sync byte, length and CRC-8**, plus ACK/NAK responses;
  * **register file** behind a simple internal bus (`addr`, `wdata`, `we`, `rdata`)
    with **readback**, a version register and status/level registers. In phase 3 the
    HPS AXI bridge drives this same bus, so the effects don't change;
  * **I²C master** in RTL with a **codec init sequencer**: a ROM of register writes
    run at reset, plus pass-through codec writes from the host;
  * protocol documented in `docs/protocol_v2.md`, with a small Python host tool
    for testing (pyserial) until the new GUI exists.
* Top level without Platform Designer: only a PLL IP and the RTL.

### C: Fixed-point library

* Q1.23 audio samples; multiply with rounding; saturation; dry/wet mix;
  one-pole parameter smoothing (applied to every user parameter, so no zipper
  noise); dB/linear gain tables.

### D: DSP blocks

* **NCO LFO** (phase accumulator plus a small sine table): sine, triangle, saw and square
  with smoothed edges; free rate. It replaces the 8 LFO ROMs (frees about 590 kbit).
* **Interpolated delay lines** for chorus, flanger, vibrato and echo (smooth time changes).
* **Damped reverb** (Freeverb- or Dattorro-style).
* **Distortion / overdrive:** level-compensated curves, optional 2× oversampling.
* **New:** noise gate, compressor, tone stack / EQ (biquads).

### E: Streaming chain

* Every effect is an Avalon-ST sink/source with identical ports and its own
  bypass. A routing switch (register-controlled) sets the order.

### F: Phase 3, HPS control

* Linux on the ARM Cortex-A9: web UI (phone/browser), USB-MIDI, presets, meters.
* The lightweight bridge to the register file is done (step B+,
  [v2_hps_control.md](v2_hps_control.md)). DDR3 is used for a looper and cabinet impulse responses.

## Conventions

* Branches: `main` = v2 development, `v1` = maintenance of the original design.
* Every step lands with its tests, and CI must be green before merging.
* Documentation is updated in the same commit as the change.
