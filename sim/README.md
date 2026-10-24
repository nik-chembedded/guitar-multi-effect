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
| `chorus`     | 440 Hz sine                  | no wrap-around, output differs from input |
| `echo`       | single impulse of 16000      | echo 1 = 8000 at +1200 samples, echo 2 = 4000 at +2400 (level 0.5, repeat 0.5) |
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

To run a single test in the ModelSim GUI with waveforms:

```tcl
cd sim/work
vsim -L altera_mf work.tb_audio_processor -gTEST=echo -gOUT_DIR=../out
add wave -r /tb_audio_processor/dut/FX/*
run -all
```
