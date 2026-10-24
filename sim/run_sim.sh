#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# Run the self-checking audio testbench in ModelSim (Intel FPGA Starter/Lite
# edition, ships with Quartus Prime Lite 18.1 and includes altera_mf).
#
#   ./run_sim.sh                 # run all tests
#   ./run_sim.sh echo reverb     # run selected tests
#
# Set MODELSIM_BIN if vsim/vcom are not on PATH, e.g.
#   MODELSIM_BIN=/d/intelFPGA_lite/18.1/modelsim_ase/win32aloem ./run_sim.sh
# Results: sim/work/<test>.log, captured samples in sim/out/<test>.txt
# -----------------------------------------------------------------------------
set -u
cd "$(dirname "$0")"
SIM_DIR=$(pwd)
FPGA_DIR="$SIM_DIR/../fpga"

BIN=${MODELSIM_BIN:+$MODELSIM_BIN/}
VLIB="${BIN}vlib"; VCOM="${BIN}vcom"; VSIM="${BIN}vsim"

ALL_TESTS="bypass overdrive distortion tremolo chorus echo reverb"
TESTS=${*:-$ALL_TESTS}

mkdir -p work out
cd work
cp "$FPGA_DIR"/ip/*.mif .            # altsyncram loads init files from the cwd

rm -rf work && "$VLIB" work >/dev/null
compile() { "$VCOM" -quiet -2008 -work work "$@" || exit 1; }
compile "$FPGA_DIR"/ip/*.vhd
compile "$FPGA_DIR"/rtl/fx_pkg.vhd
compile "$FPGA_DIR"/rtl/ADC_CONTROLLER.vhd "$FPGA_DIR"/rtl/DAC_CONTROLLER.vhd \
        "$FPGA_DIR"/rtl/overdrive.vhd "$FPGA_DIR"/rtl/distortion.vhd \
        "$FPGA_DIR"/rtl/chorus.vhd "$FPGA_DIR"/rtl/tremolo_v2.vhd \
        "$FPGA_DIR"/rtl/echo.vhd "$FPGA_DIR"/rtl/comb_filter.vhd \
        "$FPGA_DIR"/rtl/allpass_filter.vhd "$FPGA_DIR"/rtl/reverbe.vhd \
        "$FPGA_DIR"/rtl/FX_chain.vhd "$FPGA_DIR"/rtl/audio_processor.vhd
compile "$SIM_DIR"/tb/i2s_codec_model.vhd "$SIM_DIR"/tb/tb_audio_processor.vhd

pass=0; fail=0; summary=""
for t in $TESTS; do
  frames=4800
  [ "$t" = "tremolo" ] && frames=12000   # one full 5 Hz LFO period is 9600 frames
  printf '%-11s ... ' "$t"
  "$VSIM" -c -quiet -t ns -L altera_mf work.tb_audio_processor \
      -gTEST="$t" -gN_FRAMES=$frames -gOUT_DIR=../out \
      -do ../run_test.do < /dev/null > "$t.log" 2>&1
  if grep -q "RESULT: PASS" "$t.log"; then
    echo "PASS"; pass=$((pass+1)); summary="$summary\n  PASS  $t"
  else
    echo "FAIL  (see sim/work/$t.log)"; fail=$((fail+1)); summary="$summary\n  FAIL  $t"
    grep -E "\*\* (Error|Fatal|Failure)" "$t.log" | sed 's/^/        /' | head -8
  fi
done
echo -e "\nSummary: $pass passed, $fail failed$summary"
[ $fail -eq 0 ]
