# Simulation

Self-checking testbench for the complete audio path of the FPGA design.

```
 i2s_codec_model ──I2S──▶ audio_processor ─────────────────────────────────────▶ i2s_codec_model
  (WM8731, master)         ADC_CONTROLLER → my_fifo → FX_chain → DAC_CONTROLLER   (captures DAC words)
```

* `tb/i2s_codec_model.vhd`: behavioural codec model, configured like the
  firmware sets up the real codec. Master mode, I2S, 16 bit, MCLK 18.432 MHz,
  BCLK = MCLK/4, 96 BCLKs per frame → **48 kHz**.
* `tb/tb_audio_processor.vhd`: drives the effect registers directly (no
  Nios II), streams a stimulus in, captures the output and checks it.

## Tests

| Test         | Stimulus                     | Pass criteria |
|--------------|------------------------------|---------------|
| `bypass`     | full-scale random samples    | output bit-exact to input (after the measured latency) |
| `overdrive`  | 440 Hz sine, ±12000          | bit-exact to `clip(x, ±3000) * 4` |
| `distortion` | 440 Hz sine, ±24000          | no wrap-around, symmetric output (no DC offset), negative samples present |
| `tremolo`    | 440 Hz sine, 0.25 s          | envelope varies more than 2× (5 Hz sine LFO, full depth) |
| `chorus`     | impulse every 250 frames, rate 0; depth 200, lowered to 50 at frame 2000 | wet-copy delay sweeps > 100 samples; after the depth change it stays ≤ 52 + latency (no LFO run-away) |
| `echo`       | single impulse of 16000      | echo 1 = 8000 at +1200..1208 samples, echo 2 = 4000 at twice that delay (level 0.5, repeat 0.5) |
| `reverb`     | 50 ms tone burst             | no wrap-around, tail present after the burst and decaying |

All tests also fail on:

* X/U values in the DAC output, which means uninitialised logic. In hardware
  those registers power up as 0, so simulation and hardware disagree.
* Full-scale jumps (> 30000) between consecutive samples, i.e.
  two's-complement overflow instead of saturation.

## Running

Requires ModelSim-Intel FPGA Starter Edition (bundled with Quartus Prime Lite 18.1,
contains the precompiled `altera_mf` library for the FIFO/RAM/ROM megafunctions).

```bash
# from Git Bash / any bash
MODELSIM_BIN=/d/intelFPGA_lite/18.1/modelsim_ase/win32aloem ./run_sim.sh            # all tests
MODELSIM_BIN=/d/intelFPGA_lite/18.1/modelsim_ase/win32aloem ./run_sim.sh echo       # one test
```

Outputs:

* `sim/work/<test>.log`: transcript; look for `RESULT: PASS|FAIL` and the `Note:` lines with the measured values
* `sim/out/<test>.txt`: captured samples, columns `n input output` (48 kHz)

**Run time.** The Starter Edition throttles designs above its size limit. One
4800-frame test (0.1 s of audio) takes about 6 minutes, and `tremolo` (12000
frames) about 15 minutes. Tests are independent, so they can run in parallel
from separate copies of `sim/work`. The testbench prints a progress note every
480 frames (10 ms of audio).

To run a single test in the ModelSim GUI with waveforms:

```tcl
cd sim/work
vsim -L altera_mf work.tb_audio_processor -gTEST=echo -gOUT_DIR=../out
add wave -r /tb_audio_processor/dut/FX/*
run -all
```

## Real audio: frame-level testbench

`tb/tb_fx_wav.vhd` streams a recording through `FX_chain` and writes the
result back as audio. It drives `FX_chain` directly with one sample per LRCLK
period (16 fast clock cycles per frame instead of the full I2S/MCLK timing), so
it runs about 18× faster than `tb_audio_processor`. It's still about **3–4
minutes of simulation per second of audio** in the throttled Starter Edition.

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
