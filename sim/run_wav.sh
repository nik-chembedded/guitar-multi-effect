#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# Stream real audio through the 24-bit effect chain in ModelSim, on the real
# Intel IP (altera_mf: distortion ROMs, fx_dpram, cab_coef_ram from fpga/).
# Frame-level testbench tb_fx_wav; the GHDL equivalent is cocotb/test_wav.py.
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
#   SECONDS_OF_AUDIO  use only the first N seconds of the sample (default: all; the throttled
#                 Starter Edition needs minutes per second of audio, GHDL does it much faster)
#   COMPARE_DIR   directory with the cocotb outputs (GME_WAV_OUT of test_wav.py, same
#                 SECONDS_OF_AUDIO = GME_WAV_SECONDS): every preset found there is compared
#                 sample by sample (Intel IP vs behavioural models). Not for tremolo*:
#                 test_wav.py runs an extra latency pass before them.
# -----------------------------------------------------------------------------
set -u
cd "$(dirname "$0")"
SIM_DIR=$(pwd)
FPGA_DIR="$SIM_DIR/../fpga"
BIN=${MODELSIM_BIN:+$MODELSIM_BIN/}
PY=${PYTHON:-python3}
JOBS=${JOBS:-4}
SECS=${SECONDS_OF_AUDIO:-0}

# name | generics (effect register values, see docs/register_map.md); the first ten are
# the presets of cocotb/test_wav.py
preset() {
  case "$1" in
    dry)          echo "-gEFFECTS=0" ;;
    overdrive)    echo "-gEFFECTS=1 -gOD_DRIVE=4000 -gOD_GAIN=3" ;;
    dist_medium)  echo "-gEFFECTS=8 -gDIST_TYPE=1 -gDIST_MIX=255" ;;
    tremolo)      echo "-gEFFECTS=2 -gTREM_WAVE=0 -gTREM_DEPTH=200" ;;
    tremolo_saw)  echo "-gEFFECTS=2 -gTREM_WAVE=7 -gTREM_DEPTH=200" ;;
    chorus)       echo "-gEFFECTS=16 -gCHORUS_LEVEL=128 -gCHORUS_DEPTH=144 -gCHORUS_RATE=80 -gMOD_BASE=720" ;;
    flanger)      echo "-gEFFECTS=16 -gCHORUS_LEVEL=128 -gCHORUS_DEPTH=90 -gCHORUS_RATE=30 -gMOD_BASE=96 -gMOD_FB=26000 -gMOD_SHAPE=1" ;;
    vibrato)      echo "-gEFFECTS=16 -gCHORUS_LEVEL=255 -gCHORUS_DEPTH=100 -gCHORUS_RATE=600 -gMOD_BASE=240" ;;
    echo)         echo "-gEFFECTS=4 -gECHO_TIME=14400 -gECHO_LEVEL=26000 -gECHO_REPEAT=100" ;;
    reverb)       echo "-gEFFECTS=32 -gREVERB_SIZE=57672 -gREVERB_DAMP=60 -gREVERB_MIX=100" ;;
    # longer tails (not in the cocotb test)
    dist_soft)    echo "-gEFFECTS=8 -gDIST_TYPE=0 -gDIST_MIX=255" ;;
    dist_hard)    echo "-gEFFECTS=8 -gDIST_TYPE=2 -gDIST_MIX=255" ;;
    reverb_heavy) echo "-gEFFECTS=32 -gREVERB_SIZE=61604 -gREVERB_DAMP=40 -gREVERB_MIX=128 -gTAIL_FRAMES=72000" ;;
    combo)        echo "-gEFFECTS=44 -gDIST_TYPE=1 -gDIST_MIX=180 -gECHO_TIME=14400 -gECHO_LEVEL=20000 -gECHO_REPEAT=90 -gREVERB_SIZE=52429 -gREVERB_DAMP=80 -gREVERB_MIX=80 -gTAIL_FRAMES=72000" ;;
    *) return 1 ;;
  esac
}
ALL="dry overdrive dist_soft dist_medium dist_hard tremolo tremolo_saw chorus flanger vibrato echo reverb reverb_heavy combo"

[ $# -ge 1 ] || { echo "usage: $0 <sample> [preset ...|all]"; exit 1; }
SAMPLE=$1; shift
PRESETS=${*:-dry}
[ "$PRESETS" = "all" ] && PRESETS=$ALL
for p in $PRESETS; do preset "$p" >/dev/null || { echo "unknown preset '$p'"; exit 1; }; done
[ -f "audio/$SAMPLE.wav" ] || { echo "audio/$SAMPLE.wav not found"; exit 1; }

mkdir -p wav out/wav wav_work
SECARG=""; [ "$SECS" != "0" ] && SECARG="--seconds $SECS"
"$PY" tools/wavconv.py to-txt "audio/$SAMPLE.wav" "wav/$SAMPLE.txt" $SECARG || exit 1

# ---- compile once (file order of cocotb/test_runner.py: FX_RTL)
cd wav_work
cp "$FPGA_DIR"/ip/*.mif "$SIM_DIR"/models/cab_test16.mif .
rm -rf work && "${BIN}vlib" work >/dev/null
compile() { "${BIN}vcom" -quiet -2008 -work work "$@" || exit 1; }
RTL="$FPGA_DIR/rtl"
if [ "${IP_MODELS:-0}" = 1 ]; then   # behavioural IP models instead of altera_mf
  compile "$SIM_DIR"/models/sim_rom.vhd "$SIM_DIR"/models/sim_dpram.vhd "$SIM_DIR"/models/fx_dpram.vhd \
          "$SIM_DIR"/models/cab_coef_ram.vhd "$SIM_DIR"/models/ip/*.vhd
else                                 # the real thing: altsyncram wrappers and RAMs of the design
  compile "$FPGA_DIR"/ip/*.vhd "$RTL/fx_dpram.vhd" "$RTL/cab_coef_ram.vhd"
fi
for f in fx_pkg fx_xfade lfo_sine_pkg nco_lfo level_gain overdrive distortion mod_delay tremolo_v2 echo \
         fv_comb fv_allpass reverb_fv cab_fir cab_stage dynamics biquad eq3 fx_bypass dyn_stage eq_stage FX_chain; do
  compile "$RTL/$f.vhd"
done
compile "$SIM_DIR"/tb/tb_fx_wav.vhd
cd ..

# ---- run presets, JOBS at a time (each in its own copy of the library)
run_one() {
  local p=$1 d="wav_work/run_$1"
  rm -rf "$d"; mkdir -p "$d"; cp -r wav_work/work wav_work/*.mif "$d/"
  local t0=$(date +%s)
  ( cd "$d" && "${BIN}vsim" -c -quiet -t ns -L altera_mf work.tb_fx_wav \
        -gIN_FILE="../../wav/$SAMPLE.txt" -gOUT_FILE="out.txt" $(preset "$p") \
        -do ../../run_test.do < /dev/null > sim.log 2>&1 )
  if grep -q "tb_fx_wav: DONE" "$d/sim.log" && ! grep -q "\*\* Error" "$d/sim.log"; then
    "$PY" tools/wavconv.py to-wav "$d/out.txt" "out/wav/${SAMPLE}_$p.wav" > /dev/null
    echo "  $p: OK ($(( $(date +%s) - t0 )) s) -> sim/out/wav/${SAMPLE}_$p.wav"
    if [ -n "${COMPARE_DIR:-}" ] && [ -f "$COMPARE_DIR/${SAMPLE}_$p.wav" ]; then
      "$PY" tools/wavconv.py compare "$d/out.txt" "$COMPARE_DIR/${SAMPLE}_$p.wav" | sed "s/^/    $p: /"
    fi
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
