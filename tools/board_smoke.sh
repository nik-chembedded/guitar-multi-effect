#!/usr/bin/env bash
# board_smoke.sh - smoke test of the deployed web UI, over ssh.
#
#   tools/board_smoke.sh [HOST] [--port 8080] [--user root] [--remote-dir /home/root/gme] [--dry-run]
#
# On the board (one ssh session): python -V, gme_hps.py status, then gme_smoke.py: GET /api/info,
# /api/state, /api/chain, /api/levels and for every effect set one parameter through the API,
# read it back and restore it.  Then from the PC: curl /api/info (network path PC -> board).
# PASS/FAIL per check; exit status 1 when anything fails.
set -u

HOST=192.168.1.123
USER_=root
PORT=8080
RDIR=/home/root/gme
DRY=0
while [ $# -gt 0 ]; do
    case "$1" in
        --port) PORT=${2:?}; shift 2 ;;
        --user) USER_=${2:?}; shift 2 ;;
        --remote-dir) RDIR=${2:?}; shift 2 ;;
        --dry-run) DRY=1; shift ;;
        -h|--help) sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        -*) echo "unknown option: $1" >&2; exit 2 ;;
        *) HOST=$1; shift ;;
    esac
done
SSH=${GME_SSH:-ssh}

REMOTE="cd '$RDIR' || { echo 'FAIL remote directory $RDIR'; exit 1; }
fail=0
PY=\${GME_PY:-python}; command -v \$PY >/dev/null 2>&1 || PY=python3
if out=\$(\$PY -V 2>&1 </dev/null); then echo \"PASS python: \$out\"; else echo \"FAIL python: \$out\"; fail=1; fi
if out=\$(\$PY gme_hps.py \${GME_HPS_ARGS:-} status 2>&1 </dev/null); then echo \"PASS gme_hps.py status\"; echo \"\$out\" | sed 's/^/     /'; else echo \"FAIL gme_hps.py status: \$out\"; fail=1; fi
\$PY gme_smoke.py --port '$PORT' --wait ${GME_SMOKE_WAIT:-15} </dev/null || fail=1
exit \$fail"

if [ "$DRY" = 1 ]; then
    echo "[dry-run] $SSH -o ConnectTimeout=10 $USER_@$HOST sh -s   (script on stdin):"
    printf '%s\n' "$REMOTE" | sed 's/^/[dry-run]   /'
    echo "[dry-run] curl -fsS http://$HOST:$PORT/api/info"
    exit 0
fi

rc=0
printf '%s\n' "$REMOTE" | $SSH -o ConnectTimeout=10 "$USER_@$HOST" sh -s || rc=1
if command -v curl >/dev/null 2>&1; then
    if curl -fsS -m 10 "http://$HOST:$PORT/api/info" >/dev/null; then
        echo "PASS PC -> board: http://$HOST:$PORT/api/info"
    else
        echo "FAIL PC -> board: http://$HOST:$PORT/api/info (firewall, wrong address, or the server is not running)"
        rc=1
    fi
else
    echo "SKIP PC -> board check: curl not installed"
fi
[ "$rc" = 0 ] && echo "ALL CHECKS PASSED" || echo "SOME CHECKS FAILED"
exit $rc
