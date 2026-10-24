#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# Stream real audio through the effect chain (frame-level testbench tb_fx_wav).
#
#   ./run_wav.sh <sample> [preset ...]      e.g.  ./run_wav.sh the_lick_e_minor echo reverb
#   ./run_wav.sh <sample> all
#
# <sample> is a WAV in sim/audio/ (without .wav). Results: sim/out/wav/<sample>_<preset>.wav
#
# Environment:
#   MODELSIM_BIN  ModelSim bin directory (if vsim/vcom are not on PATH)
#   PYTHON        Python 3 interpreter (default: python3)
#   JOBS          presets simulated in parallel (default 4)
# -----------------------------------------------------------------------------
set -u
cd "$(dirname "$0")"
SIM_DIR=$(pwd)
FPGA_DIR="$SIM_DIR/../fpga"
BIN=${MODELSIM_BIN:+$MODELSIM_BIN/}
PY=${PYTHON:-python3}
JOBS=${JOBS:-4}

# name | generics (effect register values, see docs/register_map.md)
preset() {
  case "$1" in
    dry)          echo "-gEFFECTS=0" ;;
    overdrive)    echo "-gEFFECTS=1 -gOD_DRIVE=4000 -gOD_GAIN=3" ;;
    dist_soft)    echo "-gEFFECTS=8 -gDIST_TYPE=0 -gDIST_MIX=255" ;;
    dist_medium)  echo "-gEFFECTS=8 -gDIST_TYPE=1 -gDIST_MIX=255" ;;
    dist_hard)    echo "-gEFFECTS=8 -gDIST_TYPE=2 -gDIST_MIX=255" ;;
    tremolo)      echo "-gEFFECTS=2 -gTREM_WAVE=0 -gTREM_DEPTH=200" ;;
    tremolo_saw)  echo "-gEFFECTS=2 -gTREM_WAVE=7 -gTREM_DEPTH=200" ;;
    chorus)       echo "-gEFFECTS=16 -gCHORUS_LEVEL=40000 -gCHORUS_DEPTH=400 -gCHORUS_RATE=40" ;;
    echo)         echo "-gEFFECTS=4 -gECHO_TIME=14400 -gECHO_LEVEL=26000 -gECHO_REPEAT=100 -gTAIL_FRAMES=72000" ;;
    reverb)       echo "-gEFFECTS=32 -gREVERB_TYPE=2 -gREVERB_MIX=100 -gTAIL_FRAMES=48000" ;;
    reverb_heavy) echo "-gEFFECTS=32 -gREVERB_TYPE=3 -gREVERB_MIX=128 -gTAIL_FRAMES=72000" ;;
    combo)        echo "-gEFFECTS=44 -gDIST_TYPE=1 -gDIST_MIX=180 -gECHO_TIME=14400 -gECHO_LEVEL=20000 -gECHO_REPEAT=90 -gREVERB_TYPE=1 -gREVERB_MIX=80 -gTAIL_FRAMES=72000" ;;
    *) return 1 ;;
  esac
}
ALL="dry overdrive dist_soft dist_medium dist_hard tremolo tremolo_saw chorus echo reverb reverb_heavy combo"

[ $# -ge 1 ] || { echo "usage: $0 <sample> [preset ...|all]"; exit 1; }
SAMPLE=$1; shift
PRESETS=${*:-dry}
[ "$PRESETS" = "all" ] && PRESETS=$ALL
for p in $PRESETS; do preset "$p" >/dev/null || { echo "unknown preset '$p'"; exit 1; }; done
[ -f "audio/$SAMPLE.wav" ] || { echo "audio/$SAMPLE.wav not found"; exit 1; }

mkdir -p wav out/wav wav_work
"$PY" tools/wavconv.py to-txt "audio/$SAMPLE.wav" "wav/$SAMPLE.txt" || exit 1

# ---- compile once
cd wav_work
cp "$FPGA_DIR"/ip/*.mif .
rm -rf work && "${BIN}vlib" work >/dev/null
compile() { "${BIN}vcom" -quiet -2008 -work work "$@" || exit 1; }
if [ "${IP_MODELS:-0}" = 1 ]; then   # behavioural IP models instead of altera_mf
  compile "$SIM_DIR"/models/sim_rom.vhd "$SIM_DIR"/models/sim_dpram.vhd "$SIM_DIR"/models/sim_dcfifo.vhd "$SIM_DIR"/models/ip/*.vhd
else
  compile "$FPGA_DIR"/ip/*.vhd
fi
compile "$FPGA_DIR"/rtl/fx_pkg.vhd "$FPGA_DIR"/rtl/overdrive.vhd "$FPGA_DIR"/rtl/distortion.vhd \
        "$FPGA_DIR"/rtl/chorus.vhd "$FPGA_DIR"/rtl/tremolo_v2.vhd "$FPGA_DIR"/rtl/echo.vhd \
        "$FPGA_DIR"/rtl/comb_filter.vhd "$FPGA_DIR"/rtl/allpass_filter.vhd "$FPGA_DIR"/rtl/reverbe.vhd \
        "$FPGA_DIR"/rtl/FX_chain.vhd "$SIM_DIR"/tb/tb_fx_wav.vhd
cd ..

# ---- run presets, JOBS at a time (each in its own copy of the library)
run_one() {
  local p=$1 d="wav_work/run_$1"
  rm -rf "$d"; mkdir -p "$d"; cp -r wav_work/work wav_work/*.mif "$d/"
  local t0=$(date +%s)
  ( cd "$d" && "${BIN}vsim" -c -quiet -t ns -L altera_mf work.tb_fx_wav \
        -gIN_FILE="../../wav/$SAMPLE.txt" -gOUT_FILE="out.txt" $(preset "$p") \
        -do ../../run_test.do < /dev/null > sim.log 2>&1 )
  if grep -q "tb_fx_wav: DONE" "$d/sim.log"; then
    "$PY" tools/wavconv.py to-wav "$d/out.txt" "out/wav/${SAMPLE}_$p.wav" > /dev/null
    echo "  $p: OK ($(( $(date +%s) - t0 )) s) -> sim/out/wav/${SAMPLE}_$p.wav"
  else
    echo "  $p: FAILED, see sim/$d/sim.log"
    grep -E "\*\* (Error|Fatal)" "$d/sim.log" | head -3 | sed 's/^/      /'
  fi
}

echo "Simulating '$SAMPLE' with: $PRESETS"
running=0
for p in $PRESETS; do
  run_one "$p" &
  running=$((running + 1))
  if [ $running -ge $JOBS ]; then wait -n; running=$((running - 1)); fi
done
wait
