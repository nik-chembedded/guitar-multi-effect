# board/ - control software for the guitar multi-effect (runs on the DE1-SoC's Linux)

| File | Purpose |
|------|---------|
| `gme/` | library: `params.json` (the one parameter table), `device.py` (/dev/mem and Mock), `model.py`, `store.py` |
| `gme_hps.py` | command line tool (all the commands of `tools/gme_hps.py` on `main` through step D6 - `cab`, `eq`, dynamics, levels, reverb size - + `get`, `params`, `chain` (show / set the effect order), `--mock`) |
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
python gme_hps.py eq 6 -3 2              # EQ bass / mid / treble in dB (switches the EQ on); eq off | eq on
python gme_hps.py chain                  # effect order, read from the FPGA
python gme_hps.py chain eq dyn od dist cab mod trem echo reverb   # set it (VERSION >= 0x0209); chain reset
python gme_hps.py set effects=DYN dyn=gate+comp gate_db=-45 comp_db=-20 ratio=4 makeup_db=3 attack_ms=2 release_ms=100
python gme_hps.py set od_db=-3 dist_db=-6 reverb_type=Custom reverb_size=92% reverb_damp=12%
python gme_web.py --port 8080            # by hand (the init script does this at boot)
sh gme_web.init start|stop|restart|status
```

On the PC, without a board: `python3 board/gme_web.py --mock` and `python3 board/gme_hps.py --mock ...`.
`--mock-state FILE` keeps the mock registers in a file, so the CLI and a running mock server see the same
state (the CLI default with `--mock` is `~/.gme_mock_state.json`). With `--mock` the cabinets come from
`../ir/build` when it has `cabNN.coef` files.

## Step D (dynamics, EQ, levels, reverb)

The signal chain, as the hardware has it: Dynamics, Overdrive, Distortion, Cabinet, EQ, Chorus/Flanger/Vibrato,
Tremolo, Echo, Reverb (`/api/chain`, the page and `gme_hps.py chain` list it in this order; with VERSION >= 0x0209 this is
only the default, see Step E).

* **Dynamics** (VERSION >= 0x0207): noise gate and compressor; thresholds, make-up and the output levels are in dB
  (stored as Q8 log2 units, 1 unit = 0.0235 dB), attack and release are shown as the effective time in ms (the hardware
  has 2^k samples, so only 16 values exist). `status`, `/api/levels` and the page show the gain reduction (DYN_GR).
* **EQ** (VERSION >= 0x0207): the hardware takes biquad coefficients that cannot be read back. The gains
  (`eq_bass`, `eq_mid`, `eq_treble`, -12 .. +12 dB, 0.1 dB steps on the page) are model-level parameters kept in
  `settings.json` and rounded to 0.1 dB; the library looks the quantised coefficients up in `gme/eq_table.json`
  (27 kB, made on the PC by `python3 tools/eq_table.py` with the search of `tools/eq_coefs.py`, so the ARM never runs
  the ~0.4 s-per-section search; `eq_coefs.py` is only a fallback if the table is missing) and writes them through
  EQ_ADDR / EQ_DATA_LO / EQ_DATA_HI / EQ_APPLY. The server writes the stored gains again at start (a restarted FPGA
  is transparent). The EQ sliders are sent when released.
* **Output level** of the overdrive / distortion (VERSION >= 0x0208) and the **custom reverb** (VERSION >= 0x0206,
  Room = Custom, size and damping) are ordinary parameters.
* Factory presets leave the cabinet, dynamics and EQ on/off state and settings as they are (like `main`); user presets
  saved from the page include them.

## Step E (effect order)

With FPGA VERSION >= 0x0209 the order of the nine effects can be changed at run time (`ROUTING_VERSION` in `gme/device.py`;
older images keep the fixed order, `/api/chain` POST answers 409 and `gme_hps.py chain <ids>` refuses).

* **Registers:** `CHAIN_0` 0x30 (slots 0..3), `CHAIN_1` 0x31 (slots 4..7), `CHAIN_2` 0x32 (slot 8): one effect id per
  nibble, slot 0 in bits 3:0. The id is the enable bit of register 0 (od 0, trem 1, echo 2, dist 3, mod 4, reverb 5, cab 6,
  dyn 7, eq 8). They read back what was written (reset `0x6307 0x2148 0x0005` = dyn od dist cab eq mod trem echo reverb).
  `CHAIN_APPLY` 0x33: any write applies the list; the FPGA rejects what is not a permutation of 0..8 (read: bit1 = rejected,
  nothing changes) and otherwise switches with an output fade of about 5.3 ms (bit0 = busy). A new apply during the fade
  is allowed. The registers are marked `"action": "chain"` in `params.json`, so no parameter or preset path writes them.
* **Library:** `Model.set_chain(order)` writes 0x30..0x32, then 0x33, checks the rejected bit and keeps the order in
  `settings.json`. `Model.chain()` shows the order read from the FPGA shadow registers (the hardware is the truth; if they
  are not a valid permutation: the stored order, then the default). Every effect stays in the chain at its place when it is
  off; the latency does not depend on the order. User presets store the order and write it when loaded.
* **Command line:** `gme_hps.py chain` (show), `chain dyn od dist cab eq mod trem echo reverb` (set, all nine ids exactly
  once; the old names such as CHORUS work), `chain reset` (default order).
* **At start** the server writes the stored order to the FPGA (`Model.chain_resync()`; a freshly programmed FPGA starts
  with the default order) together with the EQ and cabinet restore, and prints `effect order restored from settings.json`.
  Nothing is written when the FPGA already has that order.
* The Mock (`--mock`, default VERSION 0x0209; `--mock-version 0x0208` for the old behaviour) implements the shadow / apply /
  reject / busy logic of the RTL.

## Cabinet files

`cabNN.coef`, text, written by `tools/cab_coefs.py --build`: line 1 the name, line 2 the shift (0..7),
then 2048 signed integers (18-bit coefficients), one per line. The library loads one into the inactive
bank, sets that bank's shift and switches the active bank. Needs FPGA VERSION >= 0x0205.
The loaded slot is kept in `settings.json`; the server loads it again at start (a new FPGA image plays the
built-in default, and the coefficients cannot be read back). After programming the `.sof` by hand:
`gme_web.init restart`, or `gme_hps.py cab <slot>`.

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
