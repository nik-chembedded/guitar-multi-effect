# cocotb + GHDL tests

Python tests ([cocotb](https://www.cocotb.org/)) for the effect chain, simulated
with the open-source [GHDL](https://github.com/ghdl/ghdl). Intel's `altera_mf`
is replaced by the verified behavioural models in [`../models`](../models).
The same tests run locally (WSL2 Ubuntu) and in GitHub Actions on every push.

| File | Purpose |
|------|---------|
| `fxdriver.py` | frame-level driver for `FX_chain`: clock, `sample_tick`/`half_tick` strobes, register writes from Python |
| `golden.py` | bit-exact Python reference models (overdrive, distortion with the `.mif` curves) |
| `test_fx_chain.py` | the 7 effect tests |
| `test_ref.py` | bit-exact regression against the recorded v1 outputs in `ref/` (27 presets; `GME_REF_MODE=record` re-records) |
| `test_i2s.py` | I²S master core (v2 B2) against a WM8731 slave model |
| `test_ctrl.py` | UART control block: protocol, registers, errors, resync, codec requests |
| `test_codec.py` | I²C master + codec init sequencer against an I²C slave model |
| `test_system.py` | `gme_core` end to end: codec init, UART control, I²S audio |
| `test_wav.py` | real guitar audio through 8 presets; writes WAVs, checks dry bit-exact / no X / no wrap / no tremolo clicks |
| `test_runner.py` | pytest entry: builds with GHDL (`--std=08 -frelaxed`) and runs the cocotb modules |

## Tests

| Test | Check |
|------|-------|
| `test_bypass` | all effects off, 2000 full-scale random samples, bit-exact |
| `test_overdrive` | bit-exact to `golden.overdrive`, incl. saturation at high gain |
| `test_distortion` | bit-exact to `golden.distortion` for all 3 curves × mix 255/128 |
| `test_tremolo` | 5 Hz sine envelope modulated; sawtooth: largest 1-sample step < 5 % |
| `test_chorus` | delay sweeps > 100 samples; stays ≤ 52 + latency after lowering the depth mid-sweep |
| `test_echo` | echo 1 = 8000, echo 2 = 4000 at the measured delay (1200..1208) |
| `test_reverb` | no wrap-around, decaying tail after a tone burst |

All tests run in **one simulation** (about 30 s). Because the delay RAMs keep their contents
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
   (e.g. `BAUD=1536000` so UART transfers take fewer clock cycles; the logic is unchanged).
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
   * `test_ctrl.Host`: sends request frames on `uart_rx` and decodes replies on `uart_tx`.
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
sim/run_all.sh -k "test_i2s or test_ctrl"
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

| Bench | ModelSim Starter 10.5b | GHDL 5 + cocotb |
|-------|------------------------|-----------------|
| 7 effect tests | ~45 min (I²S testbench, one sim per test) | **~30 s** |
| 1 s of audio, one preset | ~3–4 min | ~35 s |
