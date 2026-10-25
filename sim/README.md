# Simulation

| Flow | Simulator | What |
|------|-----------|------|
| [`cocotb/`](cocotb/README.md) | GHDL + cocotb (WSL2 / GitHub Actions) | **main test suite**: effects, bit-exact v1 reference, I²S core, HPS control slave, I²C/codec, full system, WAV audio |
| [`models/`](models/README.md) | ModelSim (Intel `altera_mf`) | proof that the behavioural RAM/ROM models equal Intel's |
| `run_wav.sh` + `tb/tb_fx_wav.vhd` | ModelSim | real guitar recordings through the effect chain on Intel's IP |

Run everything with `./run_all.sh` (WSL/Linux) or `run_all.cmd` (Windows); see
[cocotb/README.md](cocotb/README.md#run).

The v1 I²S testbench (`tb_audio_processor`, `run_sim.sh`) is on the `v1` branch.
In v2, its role is covered by `cocotb/test_i2s.py` and `cocotb/test_system.py`.

## Real audio: frame-level testbench

`tb/tb_fx_wav.vhd` streams a recording through `FX_chain` and writes the
result back as audio. It drives `FX_chain` with one `sample_tick`/`half_tick`
pair per frame, 16 clock cycles per frame instead of 1024. In the throttled
Starter Edition that's still about **3–4 minutes of simulation per second of
audio**. `sim/cocotb/test_wav.py` does the same with GHDL, much faster.

```bash
export MODELSIM_BIN=/d/intelFPGA_lite/18.1/modelsim_ase/win32aloem
export PYTHON=~/AppData/Local/Programs/Python/Python38/python.exe   # any Python 3, stdlib only
./run_wav.sh the_lick_e_minor dry echo reverb     # selected presets
./run_wav.sh the_lick_e_minor all                 # every preset (JOBS=4 in parallel by default)
```

* Input: `audio/<name>.wav` (any format; converted to 48 kHz mono, peak −6 dBFS,
  by `tools/wavconv.py`). See [audio/README.md](audio/README.md) for sources and licences.
* Output: `out/wav/<name>_<preset>.wav`
* Presets (register values in `run_wav.sh`): `dry overdrive dist_soft dist_medium
  dist_hard tremolo tremolo_saw chorus echo reverb reverb_heavy combo`

The `dry` preset is a sanity check: the output must equal the input exactly
(latency 4 frames). Verified on `the_lick_e_minor`.
