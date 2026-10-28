# cocotb + GHDL tests

Python tests ([cocotb](https://www.cocotb.org/)) for the effect chain, simulated
with the open-source [GHDL](https://github.com/ghdl/ghdl). Intel's `altera_mf`
is replaced by the verified behavioural models in [`../models`](../models).
The same tests run locally (WSL2 Ubuntu) and in GitHub Actions on every push.

| File | Purpose |
|------|---------|
| `fxdriver.py` | frame-level driver for `FX_chain`: clock, `sample_tick`/`half_tick` strobes, register writes from Python |
| `golden.py` | bit-exact Python reference models (overdrive, distortion with the `.mif` curves; since D6 with the output level `level=` = `level_gain.vhd`: Q8 log2 units, 0 = unity) |
| `test_fx_chain.py` | the effect tests (run on the 16-bit and the 24-bit chain), incl. the modulated-delay sweep and the fractional echo; step E: `test_routing` (30 random orders through `chain_order` / `chain_apply`, the wiring checked in every frame, equal latency, invalid lists rejected, click-free order change), `test_route_models` (runner entry `test_routing_models`: dynamics, overdrive, distortion, cabinet, EQ in 3 orders bit-exact to the Python models) and `test_latency` (11 frames with everything off, +1 for OD / DIST / CAB when on) |
| `test_dynamics.py` | noise gate + compressor `dynamics` (step D5a) bit-exact to `dynamics_model.py` plus level accuracy, static curve, attack / release, gate, click checks. The block has no reset: the runner entry `test_dynamics` runs the 7 simulations listed in the module docstring (16/24 bit, 16- and 1024-clock frames) |
| `test_eq3.py` | 3-band EQ `eq3` / `biquad` (step D5b) bit-exact to `eq3_model.py`, magnitude response against `tools/eq_coefs.py`, flat, low-level (no limit cycles), saturation. Runner entry `test_eq3`: every testcase its own simulation, 16 and 24 bit (10 simulations) |
| `test_invariance.py` | the configuration of `test_timing_invariance` (all effects on, 400 frames, then five random effect orders applied one after the other, 300 frames each); the runner entry runs it twice, `GME_HALF = 8` (16-clock frames) and `512` (the board's 1024-clock frames), and requires identical output samples |
| `test_cabfir.py` | cabinet FIR block `cab_fir` (step D3) bit-exact to `cabfir_model.py`: random data, saturation, bank switch, impulse = coefficients, minimum frame length; `test_full` = the real 2048 taps with `cab_default.mif` at 1024 clocks per sample (~7 min). Runner entries `test_cabfir` (16/24 bit, 16/64 taps) and `test_cabfir_full` |
| `test_reverbfv.py` | Freeverb reverb block `reverb_fv` (step D4) bit-exact to `reverbfv_model.py` (size / damp / mix changes, clamp, bypass), decay, size and damping behaviour, overload, level, hardware timing. The block has no reset: the runner entry `test_reverbfv` runs every testcase as its own simulation, at 16 and 24 bit (16 simulations, ~4 min with 4 workers) |
| `test_moddelay.py` | modulated delay (`mod_delay`, step D2) bit-exact to `moddelay_model.py`, 16/24 bit, plus an exact static-delay check |
| `test_lfo.py` | generated LFO `nco_lfo` (step D1): bit-exact to `lfo_model.py`, frequency, sine accuracy |
| `test_lfo_v1.py` | no simulation: the 8 v1 LFO tables against the generated LFO (period, shape within 2 %) |
| `test_trem.py` | tremolo on the generated LFO, bit-exact to the model (16 and 24 bit), phase continuous across changes |
| `test_fxlib.py` | fixed-point library `fx_pkg` (wrapper `hdl/fxlib_wrap.vhd`): every function against Python |
| `test_route.py` | effect-order block `fx_route` (step E1, wrapper `hdl/route_wrap.vhd` with 9 stub effects, combinational and registered): power-up, 200 random orders, 50 invalid lists, atomic apply, exact order fade (gain 128 -> 0 -> 128 in steps of 1/128 per frame), apply during the fade; a Python model is compared with the DUT in every frame. Runner entries `test_route` (16 / 24 bit) and `test_route_invariance` (16 and 1024 clocks per frame identical) |
| `test_smooth.py` | `param_smooth`: bit-exact to a model, exact final value, time constant |
| `test_xfade.py` | click-free effect on/off: steady states exact, no step larger than the signals' own |
| `test_refv2.py` | 24-bit chain bit-exact to the v2 references in `ref_v2/` (36 presets, all re-recorded in step E2 for the new latency; incl. chorus / flanger / vibrato, free-mode tremolo, fractional echo, since D5 `dyn_gate`, `dyn_comp`, `eq_3band`, `combo_d5` with everything on, and since D6 `level_od_dist` with non-zero output levels (recorded with `GME_REF_ONLY=level_od_dist`); `GME_REF_MODE=record` re-records, with `GME_REF_ONLY=a,b,..` only those presets while all others are still checked bit-exact in the same run; the Freeverb presets `reverb_t0..t3`, `combo_all`, `combo_change` were re-recorded in step D4) and overdrive / distortion (also with 8 output levels) bit-exact to `golden.py` with full 24-bit input. Replaced the v1 recordings in step D2 |
| `test_i2s.py` | I²S master core (v2 B2) against a WM8731 slave model |
| `test_avmm.py` | HPS control slave (`ctrl_avmm`): Avalon-MM reads/writes, all registers (incl. CHAIN_0..2 0x30..0x32 with their non-zero reset values and CHAIN_APPLY 0x33, REVERB_SIZE 0x1F / REVERB_DAMP 0x20, the dynamics / EQ registers 0x21..0x2B and the read-only live DYN_GR 0x2C, OD_LEVEL 0x2D / DIST_LEVEL 0x2E), invalid/read-only addresses, CONTROL, CODEC register |
| `test_codec.py` | I²C master + codec init sequencer against an I²C slave model |
| `test_system.py` | `gme_core` end to end: codec init, control over the HPS bridge (Avalon-MM), I²S audio; `test_chain_via_hps`: VERSION 0x0209, reset values of 0x30..0x32, an OD / DIST order swap written over the bridge and applied with 0x33 (busy, bit-exact audio), invalid list rejected; `test_reverb_regs`: room presets 0..3 / custom size and damp mapping and smoothed values at the chain; `test_cabinet`: the 2048-tap default cabinet via enable bit 6 / CAB_CTRL, impulse over I²S = coefficients >> (17+shift), writes to the active bank ignored, bank 1 loaded through CAB_ADDR / CAB_DATA_LO / CAB_DATA_HI and switched; `test_dynamics_eq`: EQ set written through 0x28..0x2B changes an 800 Hz sine by the expected dB, the compressor lowers a loud sine and `DYN_GR` (0x2C) reads the reduction, both over real 1024-clock frames; `test_level_via_hps` (runner entry `test_system_level`, 16-tap cabinet, real 1024-clock frames): OD_LEVEL = 256 / -256 written over the bridge doubles / halves a 1 kHz sine exactly (+-6.02 dB), level 0 is exactly unity from reset on, the change glides (no step larger than the steady states') |
| `test_wav.py` | real guitar audio through 8 presets; writes WAVs, checks dry bit-exact / no X / no wrap / no tremolo clicks |
| `test_runner.py` | pytest entry: builds with GHDL (`--std=08 -frelaxed`) and runs the cocotb modules |

## Tests

| Test | Check |
|------|-------|
| `test_bypass` | all effects off, 2000 full-scale random samples, bit-exact |
| `test_overdrive` | bit-exact to `golden.overdrive`, incl. saturation at high gain |
| `test_level` | D6 output level of the overdrive / distortion: level 0 equals the pre-D6 formulas, every level -1100 … +600 (one per frame, incl. the clamps) bit-exact to `golden.py` for OD and the 3 curves, +6.02 dB = exactly 2x, -24 dB within 0.05 dB, saturation without wrap (16 and 24 bit chain) |
| `test_distortion` | bit-exact to `golden.distortion` for all 3 curves × mix 255/128 |
| `test_tremolo` | 5 Hz sine envelope modulated; sawtooth: largest 1-sample step < 5 % |
| `test_chorus` | delay sweeps > 100 samples; stays ≤ 52 + latency after lowering the depth mid-sweep |
| `test_echo` | echo 1 = 8000, echo 2 = 4000 at the measured delay (1200..1208) |
| `test_reverb` | Freeverb: no wrap-around, decaying tail after a noise burst; room presets 0 … 3 ordered by decay length (late/mid tail energy about 0.36 < 0.47 < 0.59 < 0.71, 24 bit; 16 bit 0.37 .. 0.73) |
| `test_reverb_chain_model` | the chain's reverb output equals `reverbfv_model.py` fed with the chain's reverb input (signal `echo_out`), bit-exact over 7 size / damp / mix / enable settings (incl. clamp, mix 0, bypass) at 16 and 24 bit |
| `test_dynamics_chain`, `test_eq_chain` | dynamics (first stage) and EQ (after the cabinet) in the chain: bit off = exact bypass with the latency of the chain without them (also after use, with the block running), bit on = `dynamics_model` fed with the chain input / `eq3_model` fed with the stage input (signal `cab_out`), bit-exact, one frame later; `DYN_GR` equals the model's meter; EQ coefficient sets through the chain's write port, a half-written set is not used. These two run first in the module (the models start from the power-up state) |
| `test_dyn_eq_fade` | with `XFADE` (runner entry `test_dyn_eq_xfade`, 16 and 24 bit): enabling / disabling either stage mid-signal gives no step above the steady states', exact bypass after the fade-out |
| `test_cab` | cabinet stage with `CAB_TAPS = 16` (`sim/models/cab_test16.mif`, copied by the runner; chain frames are 16 clocks): impulse response = coefficients >> (17+shift) one frame after the bypass latency (independent reference), cab off = bit-exact bypass with the same latency, bank 1 loaded through the write port, bank switch mid-stream (steady states exact; with `XFADE`, run by `test_cab_xfade`, no step above the signal's own), writes to the active bank ignored, idle bank rewritten and switched back |

All tests run in **one simulation** (about 3 min since the Freeverb `test_reverb`, ~2 min of it). Because the delay RAMs keep their contents
between tests, a test that measures a delay flushes the line first (see `test_echo`).

## How a test runs

```
pytest ─► test_runner.py ─► cocotb runner ─► ghdl -a (compile RTL + IP models)
                                              │
                                              ▼
                       ghdl -r <top> --vpi=libcocotbvpi_ghdl.so   ◄── VPI ──►  cocotb (Python)
                       simulates the VHDL cycle by cycle                       test_<suite>.py + models
                                              │
                                              ▼
                       results.xml ─► pytest PASS / FAIL (non-zero exit fails CI)
```

1. **pytest** runs a function in `test_runner.py`, e.g. `test_system()`. That function names the top-level
   entity (`gme_core`), the cocotb module (`test_system`), the VHDL files, and generics for simulation
   (e.g. `INIT_WAIT_CLKS=2000` so the codec power-up pause takes fewer clock cycles; the logic is unchanged).
2. **Build:** the `.mif` ROM tables are copied into the build directory, and GHDL compiles the files
   (`--std=08 -frelaxed`). The Intel RAM/ROM wrappers are replaced by `sim/models/ip/*.vhd`
   (same entities, proven equivalent to `altera_mf`). `top_v2` and the PLL are not simulated:
   the test drives `gme_core`'s clock directly.
3. **Simulate:** GHDL elaborates the design and loads cocotb through VPI. cocotb imports the test
   module and runs every `@cocotb.test()` in order, in one simulation. Python can read and write any
   port and wait for clock cycles or signal edges.
4. **Stimulus and models:** the test starts the clock, releases reset and launches the external
   devices as concurrent coroutines that react to the RTL's pins:
   * `test_i2s.CodecSlave`: drives `adcdat` bit by bit on BCLK falling edges and rebuilds the words
     on `dacdat`;
   * `test_codec.I2cSlave`: resolves the open-drain bus, detects START/STOP, ACKs and records transfers;
   * `test_avmm.AvmmHost`: plays the HPS lightweight bridge (Avalon-MM master: register *n* at byte address 4·*n*).
5. **Checks:** plain `assert`s compare what came out of the RTL with the expectation: the Python
   reference maths in `golden.py` (bit-exact), the recorded v1 outputs in `ref/`, exact I²C byte
   sequences, protocol status codes, measured clock periods. A failing assert marks that cocotb
   test FAIL (message and traceback in the log), and the simulation continues with the next test.
6. **Result:** cocotb writes `results.xml`; the pytest function fails if any cocotb test failed.
   `run_all.sh` summarises one line per suite.

## Setup (WSL2 Ubuntu, once)

```bash
sudo apt update && sudo apt install -y ghdl make g++ git python3-venv python3-pip
python3 -m venv ~/venvs/gme && source ~/venvs/gme/bin/activate
pip install "cocotb~=2.0" numpy pytest
```

## Run

The easy way is `sim/run_all.sh` (Linux/WSL) or `sim\run_all.cmd` (Windows, runs
it through WSL):

```bash
sim/run_all.sh                    # all suites (~10 min)
sim/run_all.sh quick              # unit + system tests (~2 min)
sim/run_all.sh full               # all, WAV regression on the whole clip
sim/run_all.sh -k "test_i2s or test_avmm"
sim/run_all.sh --waves -k test_i2s            # + GTKWave waveform
```

It prints one summary line per suite. The full log goes to `sim/out/run_all.log`.

Directly with pytest:

```bash
source ~/venvs/gme/bin/activate
cd "/mnt/d/Claude Projects/guitar-multi-effect/sim/cocotb"
pytest -v -k test_fx_chain                         # effect tests, ~40 s incl. build
TESTCASE=test_echo pytest -v -k test_fx_chain      # a single cocotb test
GME_WAV_SECONDS=3.2 pytest -v -k test_wav          # full clip, WAVs in sim/out/cocotb_wav/
```

`GME_BUILD=~/build/gme` puts the build directory on the Linux filesystem, which is faster than `/mnt/d`.

### Waveforms

`GME_WAVES=1` (or `run_all.sh --waves`) makes GHDL write `<build>/<toplevel>/<toplevel>.ghw`;
the path is printed after the run. Open it with GTKWave (`sudo apt install gtkwave` in
WSL, or the Windows build of GTKWave). Waveforms of long suites get large (the effect
suites dump every signal), so select a single suite or test.

## Speed

`run_all.sh` runs the suites **in parallel** (pytest-xdist, one GHDL simulation per
core, slowest suites first via `conftest.py`); the WAV regression is split into one
simulation per preset and uses 0.25 s of audio (`full`: the whole 3.1 s clip).
`GME_JOBS=1` runs everything one after another.

Measured (step D1, 8-core WSL2): one after another the full set took ~45 min; the
longest single suites are the reference runs (~6–13 min each); in parallel the whole set takes ~16 min.

Where the time goes: the simulator itself. GHDL's mcode backend runs this design at
roughly 8 500 clocks/s (17 clocks per audio frame). A pure-VHDL streaming
testbench without any per-frame Python (tried, bit-identical results) was only
~5 % faster than the cocotb driver, so Python is not the bottleneck. Further speed
would come from an optimising GHDL build (`ghdl-llvm` / `ghdl-gcc` with `-O2`, needs
`sudo apt install`) and from fewer clocks per frame.

| Bench | ModelSim Starter 10.5b | GHDL 5 + cocotb |
|-------|------------------------|-----------------|
| 7 effect tests | ~45 min (I²S testbench, one sim per test) | **~30 s** |
| 1 s of audio, one preset | ~3–4 min | ~35 s |
