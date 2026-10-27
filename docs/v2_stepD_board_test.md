# v2 step D - board test package

Everything of step D (D1..D6) plus the web UI, first time on the DE1-SoC. Nothing on the SD card changes:
the FPGA image goes in over JTAG, the software into `/home/root/gme/` (Terasic Linux stays as it is).

## What is in the package

| Item | Where | Notes |
|------|-------|-------|
| FPGA image | `fpga/output_files/my_audio.sof` | VERSION 0x0208, built 2026-10-27 from `main` (Quartus Lite 18.1): 15 % ALMs, 268 M10K, 72/87 DSP, timing met (setup +1.73 ns, hold +0.069 ns) |
| SD-card image (later) | `fpga/output_files/soc_system.rbf` | same build, uncompressed; only for step 2 of `docs/v2_hps_control.md`, not needed now |
| Board software | `board/` | CLI `gme_hps.py`, web server `gme_web.py` (port 8080), copied by `tools/deploy_board.sh` |
| Cabinets | `ir/build/cab00..09.coef` | made on the PC by `python3 tools/cab_coefs.py --build` (third-party IRs stay local) |

The build outputs and `ir/build/` are not in git; they are on this PC.

## Bring-up

1. Boot the board as usual (Terasic rbf), log in as root. PC on "Ethernet 3" (192.168.1.100), board 192.168.1.123.
2. Quartus Programmer: program `fpga/output_files/my_audio.sof` (5CSEMA5, leave SOCVHPS alone). Linux keeps running.
3. From the PC (Git Bash or WSL), in the repository:

   ```
   tools/deploy_board.sh --host 192.168.1.123 --install --cab ir/build
   ```

   It prints the init system it found, restarts the server and runs the smoke test (PASS/FAIL per check).
4. Browser: **http://192.168.1.123:8080**. On the board, `cd /home/root/gme`, the CLI is `python gme_hps.py ...`.

If anything fails, `tools/board_smoke.sh 192.168.1.123` reruns the smoke test; server log `/var/log/gme_web.log`.

## Checklist

Guitar into LINE IN, LINE OUT to the amp / headphones. Write what you hear in the last column (OK / problem).

| # | Area | How | Expected | Result |
|---|------|-----|----------|--------|
| 1 | Image + software | `python gme_hps.py status` | `version 0x0208`, codec init done, PLL locked; deploy smoke test all PASS | |
| 2 | Python 2.7 / init system | the deploy output; then `reboot` and `tail /var/log/gme_web.log` before re-programming | the server started at boot and refused (Terasic image loaded: "VERSION reads ..."); after re-programming the `.sof`, `sh gme_web.init restart` brings it up. Full autostart only with our rbf on the card (later) | |
| 3 | Dry path | all effects off | clean, no hum or clicks, same level as through a cable | |
| 4 | Noise gate | `set effects=DYN dyn=gate gate_db=-45`, stop playing | hiss disappears when the strings are muted, notes not cut off | |
| 5 | Compressor + meter | `dyn=comp comp_db=-20 ratio=4 makeup_db=3`; page GR meter | even sustain, GR meter moves with picking strength | |
| 6 | Overdrive / distortion level | page level knobs, or `set od_db=-3 dist_db=-6` | level changes smoothly, no clicks; 0 dB = old loudness | |
| 7 | Cabinet | `cab list`, `cab 0`, `cab on`, then switch slots 1..9 while playing | cab sound obvious with distortion; switching is click-free | |
| 8 | EQ | `eq 6 -3 2`, then `eq off` / `eq on`; page sliders | clear bass / mid / treble change; on/off click-free | |
| 9 | Chorus / flanger / vibrato | page Modulation card: rate, depth, mix, feedback, shape | smooth sweep, flanger feedback audible, no zipper noise | |
| 10 | Tremolo | 4 shapes (sine, triangle, square, saw), rate knob | rate follows the knob, square/saw without clicks | |
| 11 | Echo | `set echo_time=320ms`, then sweep the time while playing | repeats in time; sweeping glides (fractional delay), no crackle | |
| 12 | Reverb | room types 0..3, then `reverb_type=Custom reverb_size=92% reverb_damp=12%` | 4 distinct rooms, custom size/damping work, tail fades cleanly | |
| 13 | Full chain | dynamics + distortion + cab + EQ + chorus + echo + reverb at once | no overload or distortion that the single effects don't have | |
| 14 | Presets | save a user preset on the page, rerun `tools/deploy_board.sh` (no `--install`) | preset is still there | |
| 15 | Oversampling decision | distortion, high notes on the top strings (12th fret and up) | harsh / metallic "fizz" on high notes = aliasing: then build 2x oversampling (measured in D6, not built) | |

## Known, accepted

* EQ: 0.21 dB off for a 100 Hz shelf at +12 dB.
* Reverb feedback rounds toward zero (the tail ends in true silence).
* Page tested on the PC with `--mock` only; the board runs it for the first time.
