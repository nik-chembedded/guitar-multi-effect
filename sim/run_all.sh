#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# run_all.sh - run the cocotb + GHDL test suites (Linux / WSL2).
#
#   ./run_all.sh               all suites (WAV regression on 0.25 s of audio)
#   ./run_all.sh quick         unit + system tests only
#   ./run_all.sh full          all suites, WAV regression on the whole 3.1 s clip
#   ./run_all.sh -k "test_i2s or test_avmm"     any pytest -k expression
#   ./run_all.sh --waves quick                  also write GTKWave .ghw waveforms
#
# The suites run in parallel (pytest-xdist, one simulation per core), slowest
# first (conftest.py). GME_JOBS=1 runs them one after another.
#
# From Windows:  sim\run_all.cmd [same arguments]
# Environment:   VENV (default ~/venvs/gme), GME_BUILD (default ~/build/gme),
#                GME_JOBS (parallel simulations, default: all cores)
# Log:           sim/out/run_all.log
# -----------------------------------------------------------------------------
set -u
cd "$(dirname "$0")"
SIM_DIR=$(pwd)

VENV=${VENV:-$HOME/venvs/gme}
if [ -f "$VENV/bin/activate" ]; then
  # shellcheck disable=SC1091
  source "$VENV/bin/activate"
fi
command -v ghdl >/dev/null || { echo "ghdl not found (sudo apt install ghdl)"; exit 1; }
python -c "import cocotb" 2>/dev/null || { echo "cocotb not found (pip install 'cocotb~=2.0' numpy pytest pytest-xdist)"; exit 1; }

export GME_BUILD=${GME_BUILD:-$HOME/build/gme}
if [ "${1:-}" = "--waves" ]; then export GME_WAVES=1; shift; fi

SELECT=""
case "${1:-all}" in
  all)   SELECT=""; export GME_WAV_SECONDS=${GME_WAV_SECONDS:-0.25} ;;
  quick) SELECT="test_fx_chain or (test_cabfir and not test_cabfir_full) or test_cab_xfade or test_reverbfv or test_fxlib or test_smooth or test_xfade or test_lfo or test_trem or test_moddelay or test_i2s or test_avmm or test_codec or test_system" ;;
  full)  SELECT=""; export GME_WAV_SECONDS=${GME_WAV_SECONDS:-3.2} ;;
  -k)    SELECT="${2:-}"; export GME_WAV_SECONDS=${GME_WAV_SECONDS:-0.25} ;;
  *)     echo "usage: $0 [--waves] [all|quick|full|-k EXPR]"; exit 2 ;;
esac

JOBS=${GME_JOBS:-auto}
PAR=()
if [ "$JOBS" != "1" ] && python -c "import xdist" 2>/dev/null; then
  PAR=(-n "$JOBS" --dist load)
fi

mkdir -p out
LOG="$SIM_DIR/out/run_all.log"
echo "ghdl: $(ghdl --version | head -1)"
echo "cocotb: $(python -c 'import cocotb; print(cocotb.__version__)'), build dir: $GME_BUILD"
echo "selection: ${SELECT:-all suites}   parallel: ${PAR[*]:-no}   log: $LOG"
start=$(date +%s)

cd "$SIM_DIR/cocotb"
if [ -n "$SELECT" ]; then
  pytest -v -s -rA "${PAR[@]}" -k "$SELECT" > "$LOG" 2>&1
else
  pytest -v -s -rA "${PAR[@]}" > "$LOG" 2>&1
fi
rc=$?

# per-suite cocotb summaries, pytest result per suite, waveform paths
grep -E "TESTS=[0-9]+ PASS|^(PASSED|FAILED) test_runner.py::\S+|waveform:|^ERROR " "$LOG" \
  | sed -E 's/^\s+//; s/\*\*//g'
grep -E "^=+ .*(passed|failed|error).* =+$" "$LOG" | tail -1
echo "time: $(( $(date +%s) - start )) s  (exit $rc)"
exit $rc
