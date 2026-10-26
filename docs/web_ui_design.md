# Web UI for the guitar multi-effect (design, for review)

Branch `web-ui` (worktree `../guitar-multi-effect-webui`), merged into `main` after
step D. Status: design approved 2026-10-25 (with the two decisions below); implementation W1–W4.

Decisions: (1) **step E (effect reordering) comes next** – the UI and API treat the
chain order as data from the start; (2) **PC browser only** for now – desktop layout
first, tested in the PC browser; phone layout is a later nice-to-have.

## Goals

* Control everything from a PC browser on the board's network: effects,
  presets, cabinets, EQ, dynamics, codec, levels.
* The Python CLI (`gme_hps.py`) stays and **always has the full capabilities** of the
  current FPGA image: it is the fallback and the test tool.
* Runs on the board's current Linux (Terasic image: kernel 3.18, Python 2.7, no pip,
  maybe no internet) **and** later on a fresh Debian (Python 3): standard library
  only, Python 2.7 and 3 compatible, no build step, no CDN.

## Architecture

```
 browser (phone / PC)
   │  HTTP: static page + JSON API (+ server-sent events for meters)
   ▼
 gme_web.py ──┐                               gme_hps.py (CLI)
              ├── gme/  (one library)  ◄──────┘
              │     params.json   one table: every parameter of the FPGA image
              │     device.py     DevMem (/dev/mem, ctypes 32-bit) | Mock (in memory)
              │     model.py      units <-> register values, presets, cabinets, codec
              │     store.py      user presets / settings as JSON files
              ▼
 /dev/mem 0xFF200000 + 4·n  (lightweight bridge, register map of docs/register_map.md)
```

* **One parameter table (`params.json`)** is the single source of truth. For every
  parameter: id, register, bits, type (int, enum, bool, signed), raw range, display
  unit and conversion (e.g. `echo_time` samples ↔ ms, `trem_rate` 0.01 Hz ↔ Hz,
  feedback Q15 ↔ %), effect group, default, help text, and the VERSION from which it
  exists. The CLI and the web UI are both generated from it, so a new FPGA
  feature added to the table appears in both, and neither can lose a capability.
  A test checks that every register in `docs/register_map.md` is covered.
* The CLI keeps every current command (`status`, `read`, `write`, `set`, `preset`,
  `codec`, `dump`, `meter`, `cab`, `selftest`) and gains `get/set` by parameter id in
  display units (`set echo_time=320ms`), plus raw `read/write` for anything.
* **Device backends:** `DevMem` on the board; `Mock` (a simulated register file with
  VERSION, STATUS, levels) for running the server and the tests on a PC.

## JSON API (all under `/api`)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/info` | version, FPGA VERSION register, parameter table |
| GET | `/api/state` | all parameter values (display units) + status |
| POST | `/api/params` | `{id: value, ...}` set one or more parameters |
| GET | `/api/levels` (SSE: `/api/levels/stream`) | input/output level, gain reduction, ~15 Hz |
| GET / POST / DELETE | `/api/presets[/name]` | factory presets (read-only) + user presets (saved JSON, incl. chain order) |
| GET / POST | `/api/chain` | effect order: `{order: [ids], editable: bool}`; `editable` only when the FPGA VERSION supports routing (step E); until then POST returns 409 |
| POST | `/api/cab` | `{slot: n}` load cabinet n (inactive bank, switch) |
| POST | `/api/codec` | WM8731 register write (volumes, input select) |
| GET / POST | `/api/raw/<reg>` | raw register access (expert, parity with the CLI) |

Errors are JSON `{error: text}` with HTTP 4xx. Writes are serialised by one lock
(the hardware has one register port).

## User interface (PC browser first, one page, vanilla HTML/CSS/JS)

* **Top bar:** connection state, FPGA version, codec / PLL status, input and output
  meters, mute button.
* **Signal chain** as a row of effect cards in the order reported by `/api/chain`
  (today the fixed hardware order of step D: Dynamics → Overdrive → Distortion → Cabinet → EQ →
  Chorus/Flanger/Vibrato → Tremolo → Echo → Reverb).  The Dynamics card has a live gain-reduction
  meter (DYN_GR); the EQ gains are model-level parameters (the FPGA takes coefficients, see `board/README.md`).
  Each card: on/off switch and its controls (sliders with display units; selects for
  types, waveforms, cabinets). **Step E:** when the chain is editable, cards can be
  dragged to reorder; the order is part of presets. The card layout and the API do not
  assume a fixed order, so step E needs no UI rework.
* **Preset bar:** factory and user presets, save as / overwrite / delete.
* **Cabinet card:** the 10 slots by name, load progress, active bank.
* **Settings:** codec headphone / line volume, input gain; network info.
* **Expert page:** all registers raw (read / write) for debugging.
* Moving a slider sends at most ~20 updates/s (throttled); the FPGA smooths the
  values anyway, so there is no zipper noise.
* Desktop layout (≥ 1280 px wide) first; it must stay usable down to ~1000 px.

## Deployment on the board

* Files: `board/` in the repo → `/home/root/gme/` on the board (`gme/`, `gme_hps.py`,
  `gme_web.py`, `www/`, `cab/` coefficient files from `tools/cab_coefs.py`).
* `tools/deploy_board.sh` (PC, Git Bash or WSL): `scp` the files, restart the server
  over `ssh`, then run the board smoke test. The board address comes from an argument
  (default `192.168.1.123`); the user types the SSH password (or sets up a key once).
* Autostart: an init script installed by `deploy_board.sh --install` (the init system
  of the Terasic image is checked first: sysvinit `/etc/init.d` + `update-rc.d`, or
  `/etc/rc.local`), running `python gme_web.py --port 8080` as root (needed for
  `/dev/mem`). It starts only if VERSION reads `0x02xx`, so a different FPGA image is
  never touched.
* Open `http://192.168.1.123:8080` in the PC browser (PC and board on the direct
  Ethernet link 192.168.1.x).

## Testing

| Level | How |
|-------|-----|
| Library | pytest on the PC with the `Mock` backend: every parameter round-trips (display unit → register → display unit), presets, cabinet loading writes the right register sequence, parameter table covers the register map |
| CLI parity | every parameter in the table can be set and read by the CLI; old command lines keep working |
| API | pytest starting the server on a free port with `Mock`, exercising every endpoint |
| UI | the server with `Mock` on the PC, page checked in the PC browser (desktop layout, controls change the mock registers, meters move, chain order shown, reorder disabled until step E), screenshots for review |
| Python 2.7 | the library and server are run with Python 2.7 on the board (no 2.7 on the PC); the syntax is kept 2.7-compatible and checked by a test that compiles the files with `python2` when available |
| Board | `tools/board_smoke.sh`: over ssh, `gme_hps.py status`, `curl` every read endpoint, set and read back one parameter of each effect, check VERSION |

## Phases

1. **W1:** `gme/` library + `params.json` + CLI rewritten on it (full parity) + tests.
2. **W2:** `gme_web.py` server + JSON API + `Mock` + API tests.
3. **W3:** the page (HTML/CSS/JS) + UI check in the browser with `Mock`.
4. **W4:** `deploy_board.sh`, init script, smoke test; one board test (yours).
5. **Merge into `main`** after step D; the parameters added by D3–D6 go into
   `params.json` as their registers are fixed on `main`.  Done on `web-ui` (main merged at step D6,
   `e91a733`): reverb size / damping, dynamics, EQ, output levels, 0x0208 mock; the CLI is
   tested against `main`'s `tools/gme_hps.py` (`board/tests/legacy_gme_hps.py`).

## Settings

Decided: port 8080, no access key, dark "pedalboard" look, user presets on the SD card
(`/home/root/gme/presets/`).
