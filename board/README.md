# board/ - control software for the guitar multi-effect (runs on the DE1-SoC's Linux)

| File | Purpose |
|------|---------|
| `gme/` | library: `params.json` (the one parameter table), `device.py` (/dev/mem and Mock), `model.py`, `store.py` |
| `gme_hps.py` | command line tool (all the old commands + `get`, `params`, `cab`, `chain`, `--mock`) |
| `gme_web.py` | web server + JSON API, serves `www/` (port 8080) |
| `www/` | the page (`index.html`, `app.css`, `util.js`, `controls.js`, `app.js`): built from `/api/info` |
| `gme_smoke.py` | smoke test of the running server (used by `tools/board_smoke.sh`) |
| `gme_web.init`, `install_init.sh` | start/stop script and autostart installer |
| `tests/` | pytest on the PC (not copied to the board) |

Python 2.7 (Terasic Linux 3.18 image) and Python 3 (later Debian): standard library only, no pip.
Run as **root** (needs `/dev/mem`). Everything refuses to touch the hardware unless the FPGA
VERSION register reads `0x02xx`.

## First deployment (from the PC, Git Bash or WSL)

Board and PC on the direct Ethernet link (PC `192.168.1.x`, board `192.168.1.123`), FPGA image loaded.

```
tools/deploy_board.sh --host 192.168.1.123 --install --cab ir/build
```

* copies `board/` to `/home/root/gme/` (replaces `gme/` and `www/`; keeps `presets/`, `settings.json`, `cab/`),
  copies the cabinet files `ir/build/cab*.coef` (made by `python3 tools/cab_coefs.py --build` on the PC) to `/home/root/gme/cab/`,
* `--install` sets up the autostart (it prints the init system it found: systemd, sysvinit, upstart or `/etc/rc.local`),
* restarts the server and runs the smoke test (PASS/FAIL per check).

The ssh password is asked once per step. To avoid it: `ssh-copy-id root@192.168.1.123`.
`--dry-run` prints what would happen; `--no-restart` only copies.

Then open **http://192.168.1.123:8080** in the PC browser.

## Updating

Run `tools/deploy_board.sh` again (without `--install`). User presets and the loaded-cabinet memory stay.
Cabinets only: `tools/deploy_board.sh --cab ir/build --no-restart`.

## On the board

```
cd /home/root/gme
python gme_hps.py status                 # same tool as before
python gme_hps.py set echo_time=320ms trem_rate=6.5Hz
python gme_hps.py cab list | cab 3 | cab on
python gme_web.py --port 8080            # by hand (the init script does this at boot)
sh gme_web.init start|stop|restart|status
```

On the PC, without a board: `python3 board/gme_web.py --mock` and `python3 board/gme_hps.py --mock ...`.
`--mock-state FILE` keeps the mock registers in a file, so the CLI and a running mock server see the same
state (the CLI default with `--mock` is `~/.gme_mock_state.json`). With `--mock` the cabinets come from
`../ir/build` when it has `cabNN.coef` files.

## Cabinet files

`cabNN.coef`, text, written by `tools/cab_coefs.py --build`: line 1 the name, line 2 the shift (0..7),
then 2048 signed integers (18-bit coefficients), one per line. The library loads one into the inactive
bank, sets that bank's shift and switches the active bank. Needs FPGA VERSION >= 0x0205.

## Troubleshooting

* **Page does not open:** `sh /home/root/gme/gme_web.init status`; log: `tail /var/log/gme_web.log`.
* **"VERSION reads 0x.... not 0x02xx":** another FPGA image is loaded. The server (and `gme_hps.py`) refuse to
  write. Load the multi-effect image (Quartus programmer) and run `gme_web.init restart`. The autostart does
  not retry in a loop.
* **Port already in use:** `gme_web.init stop`, or start with `--port 8081` (`GME_PORT=8081 sh gme_web.init restart`).
* **`cannot open /dev/mem`:** not root.
* **Some controls missing:** the parameter belongs to a newer FPGA VERSION than the loaded image
  (`python gme_hps.py params` lists the VERSION of each; `!` marks the unavailable ones).
* **Python 2.7:** no f-strings, no `pip`; if `python` is missing, `gme_web.init` falls back to `python3`/`python2`.
  The code is kept 2.7-compatible by `board/tests/test_py27.py` (AST scan on the PC).
* **ssh asks for a password every time / refuses root:** `ssh-copy-id root@192.168.1.123`; the Terasic image allows root login.
