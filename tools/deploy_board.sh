#!/usr/bin/env bash
# deploy_board.sh - copy board/ to the DE1-SoC, (re)start the web server, run the smoke test.
# Runs on the PC in Git Bash or WSL (needs bash, tar, ssh).
#
#   tools/deploy_board.sh [--host 192.168.1.123] [--install] [--no-restart] [--no-smoke]
#                         [--cab DIR] [--user root] [--port 8080] [--remote-dir /home/root/gme]
#                         [--dry-run]
#
#   --install     also install the autostart (detects sysvinit / systemd / upstart / rc.local)
#   --no-restart  copy only (implies --no-smoke)
#   --cab DIR     also copy DIR/cab*.coef to <remote-dir>/cab/   (tools/cab_coefs.py --build -> ir/build)
#   --dry-run     print what would be done, change nothing
#
# What it touches on the board: ONLY <remote-dir> (default /home/root/gme): it replaces gme/ and
# www/ and the program files there; presets/, settings.json, cab/ and the log stay.  Nothing outside
# that directory is deleted; the SD card's boot partition is never touched.  With --install it
# also writes the autostart files named gme_web* (see board/install_init.sh).
#
# The files go over ONE ssh connection (tar through ssh), so the password is asked once per step
# (deploy, smoke test).  To avoid typing it, set up a key once:
#   ssh-keygen -t ed25519            (if you have no key yet)
#   ssh-copy-id root@192.168.1.123
set -eu

HOST=192.168.1.123
USER_=root
PORT=8080
RDIR=/home/root/gme
INSTALL=0
RESTART=1
SMOKE=1
CAB=
DRY=0

usage() { sed -n '2,22p' "$0" | sed 's/^# \{0,1\}//'; exit "${1:-0}"; }

while [ $# -gt 0 ]; do
    case "$1" in
        --host) HOST=${2:?--host needs an address}; shift 2 ;;
        --user) USER_=${2:?}; shift 2 ;;
        --port) PORT=${2:?}; shift 2 ;;
        --remote-dir) RDIR=${2:?}; shift 2 ;;
        --cab) CAB=${2:?--cab needs a directory}; shift 2 ;;
        --install) INSTALL=1; shift ;;
        --no-restart) RESTART=0; SMOKE=0; shift ;;
        --no-smoke) SMOKE=0; shift ;;
        --dry-run) DRY=1; shift ;;
        -h|--help) usage 0 ;;
        *) echo "unknown option: $1" >&2; usage 2 ;;
    esac
done

HERE=$(cd "$(dirname "$0")" && pwd)
BOARD=$(cd "$HERE/../board" && pwd)
TARGET="$USER_@$HOST"
SSH=${GME_SSH:-ssh}
SSH_OPTS="-o ConnectTimeout=10"

say() { printf '%s\n' "$*"; }

# ---- what is sent -----------------------------------------------------------------------------
FILES="gme gme_hps.py gme_web.py gme_smoke.py gme_web.init install_init.sh www README.md"
for f in $FILES; do
    [ -e "$BOARD/$f" ] || { echo "missing $BOARD/$f" >&2; exit 1; }
done
if [ -n "$CAB" ]; then
    ls "$CAB"/cab*.coef >/dev/null 2>&1 || { echo "no cab*.coef files in $CAB" >&2; exit 1; }
fi

# ---- the remote script (POSIX sh, busybox ash) -----------------------------------------------------------
REMOTE="set -e
mkdir -p '$RDIR'
cd '$RDIR'
rm -rf gme www
tar xof -
chmod +x gme_hps.py gme_web.py gme_smoke.py gme_web.init install_init.sh
echo \"files in $RDIR:\"; ls"
if [ "$INSTALL" = 1 ]; then
    REMOTE="$REMOTE
GME_DIR='$RDIR' GME_PORT='$PORT' sh '$RDIR/install_init.sh' install"
fi
if [ "$RESTART" = 1 ]; then
    REMOTE="$REMOTE
GME_DIR='$RDIR' GME_PORT='$PORT' sh '$RDIR/gme_web.init' restart"
fi

say "deploy to $TARGET:$RDIR  (install autostart: $INSTALL, restart: $RESTART, smoke test: $SMOKE)"
say "files: $FILES${CAB:+ + cab/*.coef from $CAB}"

if [ "$DRY" = 1 ]; then
    say "[dry-run] stage the files (without tests, __pycache__, presets, settings.json), then:"
    say "[dry-run] tar -cf - -C <stage> . | $SSH $SSH_OPTS $TARGET sh -c '<remote script>'"
    say "[dry-run] remote script:"
    printf '%s\n' "$REMOTE" | sed 's/^/[dry-run]   /'
    if [ "$SMOKE" = 1 ]; then
        say "[dry-run] then: $HERE/board_smoke.sh $HOST --port $PORT --user $USER_ --remote-dir $RDIR"
    fi
    say "[dry-run] nothing was changed"
    exit 0
fi

# ---- stage and send ----------------------------------------------------------------------------------------
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT
for f in $FILES; do cp -R "$BOARD/$f" "$STAGE/"; done
find "$STAGE" \( -name __pycache__ -o -name '*.pyc' \) -prune -exec rm -rf {} + 2>/dev/null || true
if [ -n "$CAB" ]; then
    mkdir -p "$STAGE/cab"
    cp "$CAB"/cab*.coef "$STAGE/cab/"
fi

say "sending (the ssh password is asked once; hint: ssh-copy-id $TARGET sets up a key) ..."
# shellcheck disable=SC2086  # SSH_OPTS is a list of words
if ! tar -cf - -C "$STAGE" . | $SSH $SSH_OPTS "$TARGET" "$REMOTE"; then
    echo "deploy failed. Is the board reachable (ping $HOST) and is root login over ssh enabled?" >&2
    echo "A key avoids the password prompt:  ssh-copy-id $TARGET" >&2
    exit 1
fi

if [ "$SMOKE" = 1 ]; then
    say "smoke test ..."
    "$HERE/board_smoke.sh" "$HOST" --port "$PORT" --user "$USER_" --remote-dir "$RDIR"
fi
say "done: open http://$HOST:$PORT/ in the PC browser"
