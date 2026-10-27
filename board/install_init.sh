#!/bin/sh
# install_init.sh detect|install|uninstall   (run on the board, as root, by tools/deploy_board.sh --install)
#
# Finds the init system, prints what it found and sets up the autostart of gme_web.init:
#   systemd          unit /etc/systemd/system/gme_web.service
#   sysv-update-rc   /etc/init.d/gme_web + update-rc.d gme_web defaults 90 10
#   sysv-links       /etc/init.d/gme_web + S90/K10 links in /etc/rc?.d (no update-rc.d)
#   upstart          /etc/init/gme_web.conf
#   rc.local         a line in /etc/rc.local (fallback)
# Only /etc files named gme_web* (and the one line in rc.local, marked "# gme_web") are touched.
#
# Overrides (tests): GME_ROOT (prefix of /etc, /run), GME_DIR, GME_INIT_SYSTEM, GME_PORT

ROOT=${GME_ROOT:-}
DIR=${GME_DIR:-/home/root/gme}
PORT=${GME_PORT:-8080}
INIT="$DIR/gme_web.init"
MARK="# gme_web"

detect() {
    if [ -n "$GME_INIT_SYSTEM" ]; then echo "$GME_INIT_SYSTEM"; return; fi
    if [ -d "$ROOT/run/systemd/system" ]; then echo systemd
    elif [ -d "$ROOT/etc/init.d" ] && command -v update-rc.d >/dev/null 2>&1; then echo sysv-update-rc
    elif [ -d "$ROOT/etc/init.d" ] && ls -d "$ROOT"/etc/rc[2-5].d >/dev/null 2>&1; then echo sysv-links
    elif [ -d "$ROOT/etc/init" ]; then echo upstart
    else echo rc.local
    fi
}

python_path() {
    for p in python python3 python2; do
        if command -v $p >/dev/null 2>&1; then command -v $p; return 0; fi
    done
    echo python
}

rclocal_remove() {
    f="$ROOT/etc/rc.local"
    [ -f "$f" ] || return 0
    grep -v "$MARK" "$f" > "$f.gme.tmp"
    cat "$f.gme.tmp" > "$f"
    rm -f "$f.gme.tmp"
}

do_install() {
    kind=$(detect)
    echo "init system found: $kind"
    chmod +x "$INIT" 2>/dev/null
    case "$kind" in
        systemd)
            mkdir -p "$ROOT/etc/systemd/system"
            cat > "$ROOT/etc/systemd/system/gme_web.service" <<EOF
[Unit]
Description=guitar multi-effect web UI
After=network.target

[Service]
User=root
WorkingDirectory=$DIR
ExecStart=/bin/sh -c 'exec $(python_path) $DIR/gme_web.py --port $PORT >> /var/log/gme_web.log 2>&1'
Restart=no

[Install]
WantedBy=multi-user.target
EOF
            if [ -z "$ROOT" ]; then systemctl daemon-reload; systemctl enable gme_web.service; fi
            ;;
        sysv-update-rc)
            mkdir -p "$ROOT/etc/init.d"
            ln -sf "$INIT" "$ROOT/etc/init.d/gme_web"
            update-rc.d gme_web defaults 90 10
            ;;
        sysv-links)
            mkdir -p "$ROOT/etc/init.d"
            ln -sf "$INIT" "$ROOT/etc/init.d/gme_web"
            for n in 2 3 4 5; do
                [ -d "$ROOT/etc/rc$n.d" ] && ln -sf ../init.d/gme_web "$ROOT/etc/rc$n.d/S90gme_web"
            done
            for n in 0 1 6; do
                [ -d "$ROOT/etc/rc$n.d" ] && ln -sf ../init.d/gme_web "$ROOT/etc/rc$n.d/K10gme_web"
            done
            ;;
        upstart)
            mkdir -p "$ROOT/etc/init"
            cat > "$ROOT/etc/init/gme_web.conf" <<EOF
description "guitar multi-effect web UI"
start on runlevel [2345]
task
exec /bin/sh $INIT start
EOF
            ;;
        rc.local)
            f="$ROOT/etc/rc.local"
            mkdir -p "$ROOT/etc"
            if [ ! -f "$f" ]; then printf '#!/bin/sh\nexit 0\n' > "$f"; chmod +x "$f"; fi
            rclocal_remove
            # insert before the final "exit 0" (or append)
            if grep -q '^exit 0' "$f"; then
                awk -v line="/bin/sh $INIT start $MARK" '/^exit 0/ && !done { print line; done=1 } { print }' "$f" > "$f.gme.tmp"
                cat "$f.gme.tmp" > "$f"
                rm -f "$f.gme.tmp"
            else
                echo "/bin/sh $INIT start $MARK" >> "$f"
            fi
            ;;
        *) echo "unknown init system '$kind'" >&2; return 1 ;;
    esac
    echo "autostart installed ($kind): gme_web starts at boot, never restarts itself"
}

do_uninstall() {
    kind=$(detect)
    echo "init system found: $kind"
    case "$kind" in
        systemd)
            [ -z "$ROOT" ] && systemctl disable gme_web.service 2>/dev/null
            rm -f "$ROOT/etc/systemd/system/gme_web.service" ;;
        sysv-update-rc)
            update-rc.d -f gme_web remove 2>/dev/null
            rm -f "$ROOT/etc/init.d/gme_web" ;;
        sysv-links)
            rm -f "$ROOT"/etc/rc?.d/S90gme_web "$ROOT"/etc/rc?.d/K10gme_web "$ROOT/etc/init.d/gme_web" ;;
        upstart) rm -f "$ROOT/etc/init/gme_web.conf" ;;
        rc.local) rclocal_remove ;;
    esac
    echo "autostart removed"
}

case "$1" in
    detect) detect ;;
    install) do_install ;;
    uninstall) do_uninstall ;;
    *) echo "usage: $0 detect|install|uninstall" >&2; exit 2 ;;
esac
