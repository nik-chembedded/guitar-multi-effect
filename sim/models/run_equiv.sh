#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# Prove the behavioural IP models (sim/models) equivalent to the Intel
# altera_mf megafunctions. Needs ModelSim-Intel (it has altera_mf).
#
#   MODELSIM_BIN=/d/intelFPGA_lite/18.1/modelsim_ase/win32aloem ./run_equiv.sh
# -----------------------------------------------------------------------------
set -u
cd "$(dirname "$0")"
HERE=$(pwd)
FPGA="$HERE/../../fpga"
BIN=${MODELSIM_BIN:+$MODELSIM_BIN/}
PY=${PYTHON:-python3}

"$PY" gen_ip_models.py >/dev/null && "$PY" gen_equiv_tb.py >/dev/null || exit 1

rm -rf work_equiv && mkdir -p work_equiv && cd work_equiv
cp "$FPGA"/ip/*.mif "$HERE"/cab_eq_*.mif .
for lib in intel model work; do "${BIN}vlib" $lib >/dev/null; done
"${BIN}vcom" -quiet -2008 -work intel "$FPGA"/ip/*.vhd "$FPGA"/rtl/fx_dpram.vhd "$FPGA"/rtl/cab_coef_ram.vhd || exit 1
"${BIN}vcom" -quiet -2008 -work model "$HERE"/sim_rom.vhd "$HERE"/sim_dpram.vhd "$HERE"/fx_dpram.vhd "$HERE"/cab_coef_ram.vhd "$HERE"/ip/*.vhd || exit 1
"${BIN}vcom" -quiet -2008 -work work "$HERE"/tb_ip_equiv.vhd || exit 1

rc=0
for tb in tb_ip_equiv; do
  "${BIN}vsim" -c -quiet -L altera_mf -L intel -L model work.$tb -do ../../run_test.do < /dev/null > $tb.log 2>&1
  grep -hE "EQUIV:|FIFO:|MISMATCH|RESULT|\*\* (Error|Fatal)" $tb.log | sed 's/^# //'
  grep -q "RESULT: PASS" $tb.log || rc=1
done
exit $rc
