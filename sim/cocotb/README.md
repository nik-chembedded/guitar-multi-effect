# cocotb + GHDL tests

Python tests ([cocotb](https://www.cocotb.org/)) for the effect chain, simulated
with the open-source [GHDL](https://github.com/ghdl/ghdl). Intel's `altera_mf`
is replaced by the verified behavioural models in [`../models`](../models).
The same tests run locally (WSL2 Ubuntu) and in GitHub Actions on every push.

| File | Purpose |
|------|---------|
| `fxdriver.py` | frame-level driver for `FX_chain`: clocks, LRCLK framing, register writes from Python |
| `golden.py` | bit-exact Python reference models (overdrive, distortion with the `.mif` curves) |
| `test_fx_chain.py` | the 7 effect tests |
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

## Setup (WSL2 Ubuntu, once)

```bash
sudo apt update && sudo apt install -y ghdl make g++ git python3-venv python3-pip
python3 -m venv ~/venvs/gme && source ~/venvs/gme/bin/activate
pip install "cocotb~=2.0" numpy pytest
```

## Run

```bash
source ~/venvs/gme/bin/activate
cd "/mnt/d/Claude Projects/guitar-multi-effect/sim/cocotb"
pytest -v -k test_fx_chain                         # effect tests, ~40 s incl. build
TESTCASE=test_echo pytest -v -k test_fx_chain      # a single cocotb test
GME_WAV_SECONDS=3.2 pytest -v -k test_wav          # full clip, WAVs in sim/out/cocotb_wav/
```

`GME_BUILD=~/build/gme` puts the build directory on the Linux filesystem, which is faster than `/mnt/d`.

## Speed

| Bench | ModelSim Starter 10.5b | GHDL 5 + cocotb |
|-------|------------------------|-----------------|
| 7 effect tests | ~45 min (I²S testbench, one sim per test) | **~30 s** |
| 1 s of audio, one preset | ~3–4 min | ~35 s |
