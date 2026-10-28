# v2 step E - board test package

Step E (effect order selectable at run time) on the DE1-SoC. This image contains all of step D too, so the
step D checklist ([v2_stepD_board_test.md](v2_stepD_board_test.md)) can run on it in the same session; only
its row 1 changes (`version 0x0209`). Nothing on the SD card changes: the FPGA image goes in over JTAG, the
software into `/home/root/gme/`.

## What is in the package

| Item | Where | Notes |
|------|-------|-------|
| FPGA image | `fpga/output_files/my_audio.sof` | VERSION 0x0209, built 2026-10-28 from `main` (E2, Quartus Lite 18.1, fitter seed 2): 18 % ALMs, 268 M10K, 73/87 DSP, timing met (setup +2.119 ns, hold +0.088 ns), no combinational loops |
| SD-card image (later) | `fpga/output_files/soc_system.rbf` | same build, uncompressed; not needed now |
| Board software | `board/` | effect order: page drag-to-reorder, CLI `gme_hps.py chain`, `/api/chain` |
| Cabinets | `ir/build/cab00..09.coef` | as in step D |

The build outputs and `ir/build/` are not in git; they are on this PC.

## Bring-up

Same as step D: program the `.sof` (5CSEMA5, leave SOCVHPS alone), then from the PC

```
tools/deploy_board.sh --host 192.168.1.123 --install --cab ir/build
```

The smoke test now also changes the order once and restores it. Browser: **http://192.168.1.123:8080**.

## What changed in the sound path (know before listening)

* Every effect now has a register at its output, so the chain is **11 frames (229 µs) late with every effect off**
  (before: 4 frames), at most 14 frames (292 µs) with all on. That is about 10 cm of air: you should not hear it.
* Changing the order fades the output down and up again: a **≈ 5 ms dip**, no click. Effect tails (echo, reverb)
  keep running.
* An effect that is off keeps its place in the order, so the order of off effects makes no difference.

## Checklist

Guitar into LINE IN, LINE OUT to the amp / headphones. On the board: `cd /home/root/gme`.

| # | Area | How | Expected | Result |
|---|------|-----|----------|--------|
| E1 | Image + order read-back | `python gme_hps.py status`; `python gme_hps.py chain` | `version 0x0209`; order `dyn od dist cab eq mod trem echo reverb` (the reset order) | |
| E2 | Dry path / latency | all effects off, play along with an unprocessed signal if you have a split | clean, same as step D; no audible delay or comb-filter colour | |
| E3 | Distortion vs reverb order | distortion + reverb on; `chain dyn od dist cab eq mod trem echo reverb`, then `chain dyn od reverb dist cab eq mod trem echo` | first: clean reverb tail on a distorted note; second: the reverb tail itself is distorted (washy, compressed "wall") | |
| E4 | Echo before / after distortion | distortion + echo on; echo after dist (default), then `chain dyn od echo dist cab eq mod trem reverb` | after: clear distinct repeats; before: repeats are distorted and merge with the note | |
| E5 | Modulation before distortion | chorus (or flanger) + distortion; `chain dyn od mod dist cab eq trem echo reverb` vs default | the sweep sounds different (more aggressive / "into the drive") than after the distortion | |
| E6 | Reorder while playing | hold a chord and change the order (CLI or page) several times | short dip only, no click or pop; echo / reverb tails continue across the change | |
| E7 | Page drag | drag a pedal in the chain row to another place | the order changes on release, `python gme_hps.py chain` shows the same order; "Default order" restores the reset order | |
| E8 | Bad order | `python gme_hps.py chain dyn od dist` (incomplete) | refused with a message; order and sound unchanged | |
| E9 | Order after re-programming | set a non-default order, re-program the `.sof`, `sh gme_web.init restart`, `python gme_hps.py chain` | the stored order is back (the server writes it at start); the CLI shows it | |
| E10 | Off effects keep their place | turn an effect off, reorder only off effects | no change in sound (only the 5 ms dip) | |

## Known, accepted

* Fitter seed 2: the default seed missed hold by 0.071 ns on the reverb comb DSP inputs (not the order logic).
* `sim/run_wav.sh` (ModelSim) has `fx_route` added but was not run.
* Python 2.7 on the board: only a syntax scan ran on the PC.
