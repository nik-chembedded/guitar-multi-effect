# v2 step E - effect order selectable at run time

Status: **approved 2026-10-27, option A** (per-effect output registers + source muxes). Decisions: reorder with the
≈ 5 ms output dip (3.2); off effects keep their place (3.1). Options considered and not taken: A2 (register at the effect
input, order-dependent latency), groups / fixed orders (not "any order"), parallel paths (can extend A later), Avalon-ST
scheduler (option B: 1-frame latency, but every block, the SDC and the regression speed change; revisit for stereo /
oversampling), a soft DSP core. Goal from [v2_plan.md](v2_plan.md): *any effect order selectable by register,
tested*. The web UI and the library already treat the order as data (`/api/chain`, `ROUTING_VERSION` in
`board/gme/model.py`), so step E is mostly RTL + tests, plus a small software step.

## 1. Constraint that drives the design

Today `FX_chain.vhd` is a fixed wire chain. Every stage passes its input straight through to its output, with no
register in between, while it is off or fading (`fx_xfade`, `fx_bypass` in dyn / cab / EQ: `dout = din + (wet - din)·g/256`).
A plain mux crossbar ("input of effect *e* = output of effect *src[e]*") therefore forms **combinational loops** in the
netlist (e.g. A → B → A through two bypassed stages). Even though a valid permutation never closes a loop at run time,
Quartus would still see the loops and could not time them. Every route must start at a register.

## 2. Options

| | A: per-slot registers + mux (recommended) | B: Avalon-ST scheduler |
|---|---|---|
| Idea | every effect gets an output register (`slot_q[e]`, loads at `sample_tick`); the input of effect *e* is a mux over `{chain input, slot_q[0..8]}` | one sequencer walks the order once per frame, hands the sample to effect *k* (valid), waits for its result (valid), passes it on; all effects get a valid/ready ST wrapper |
| Latency | fixed **1–2 frames per effect**, the same for every order (≈ 10–15 frames = 0.2–0.3 ms total; today 4–9 frames depending on what is on) | 1 frame for the whole chain |
| Effect blocks | **unchanged** (strobes, bit-exact block refs stay) | every block's en_rise / en_fall contract re-derived (echo / reverb / chorus RAM timing, cab 519-clock FIR inside a shared 1024-clock budget) |
| SDC | slot registers and muxes fall into the existing multicycle group | `seqblk` / `seqout` / `seqram` exceptions redone for all blocks |
| Risk / size | small: one new file, ~700 ALMs, no DSP, no M10K | large: touches every block, all refs, time budget |

0.3 ms is the sound travelling 10 cm through air, so it is inaudible. Option B is only worth it if we later need a
**1-frame** total latency, or want to time-share the arithmetic for 2× oversampling or stereo; it can still replace A
then, because A's register map and software stay the same. **Recommendation: A.**

## 3. Design (option A)

### 3.1 Datapath (`fx_route.vhd`, new; used by `FX_chain.vhd`)

```
 data_in ─► src mux[e] ─► [effect e: block + its own crossfade/bypass, unchanged] ─► slot_q[e] (reg @ sample_tick)
              ▲                                                                         │
              └──────────── {data_in_reg, slot_q[0..8]} ◄───────────────────────────────┘
 data_out = order fade ( slot_q[last effect of the order] )
```

* Effect ids (also the nibble codes): 0 OD, 1 TREM, 2 ECHO, 3 DIST, 4 MOD, 5 REVERB, 6 CAB, 7 DYN, 8 EQ (= the enable
  bits of register 0, so the software uses one id table).
* `src[e]` = the effect before *e* in the order, or the chain input for slot 0, computed from the slot list when the order
  is applied. The output takes `slot_q` of the effect in the last slot.
* **Off effects keep their place** (they are bypassed by their own crossfade, as today). The latency therefore depends
  neither on the order nor on which effects are on. Turning an effect on or off does not move the signal in time.
* The block strobes stay as they are. Each effect loads its input from a register that changes only at `sample_tick`,
  so every block sees a stable input at its own strobe, in any order. The exact frames per slot (1 for effects on
  `half_tick`, 2 for those on `sample_tick` or with a long sequencer such as the cabinet) are measured in E2 and listed
  in the register map.
* `dyn_gr`, the cabinet / EQ write ports and all parameters are unchanged.

### 3.2 Changing the order without a click

Applying a new order fades the chain output to 0 over 128 samples (2.7 ms), switches `src[]`, and fades back in over
128 samples (the same pattern as the cabinet bank switch). Echo, reverb and modulation tails keep running. Only their
place in the chain changes. Total dip ≈ 5.3 ms.

### 3.3 Registers

| Reg | Name | R/W | Bits | Meaning |
|----:|------|:---:|------|---------|
| 0x30 | CHAIN_0 | R/W | `[15:0]` | slots 0..3: one effect id per nibble, slot 0 in bits 3:0 |
| 0x31 | CHAIN_1 | R/W | `[15:0]` | slots 4..7 |
| 0x32 | CHAIN_2 | R/W | `[3:0]`  | slot 8 |
| 0x33 | CHAIN_APPLY | W / R | – / `[1:0]` | **any write** checks the written list and applies it with the fade. Read: bit0 = fade running, bit1 = last list rejected |

* Reset value = today's order `DYN OD DIST CAB | EQ MOD TREM ECHO | REVERB`: CHAIN_0 = `0x6307`, CHAIN_1 = `0x2148`,
  CHAIN_2 = `0x0005` (the first registers that do not reset to 0). Existing software and presets therefore behave as
  with VERSION 0x0208, apart from the latency.
* The shadow registers (0x30..0x32) only become active through CHAIN_APPLY. A half-written order is never used, as with
  EQ_APPLY.
* **Validation in hardware:** if the 9 nibbles are not a permutation of 0..8, nothing changes and bit1 is set. A bad write
  can therefore never route nothing to the output or feed one effect twice. A valid apply clears bit1.
* Writes with side effects must contain byte 1 (same rule as CODEC / CAB / EQ).
* **VERSION 0x0209**. `ROUTING_VERSION = 0x0209` in `board/gme/model.py`.

### 3.4 Software (E4)

* `board/gme`: `set_chain(order)` writes 0x30..0x32 + 0x33, waits for bit0 = 0, checks bit1. Wherever the order is
  shown, read-back comes from the shadow registers. Presets already store `chain`.
* CLI: `gme_hps.py chain` (show), `gme_hps.py chain dyn od dist cab eq mod trem echo reverb` (set), `chain reset`.
* Web: `editable` becomes true at VERSION ≥ 0x0209, which enables the drag-to-reorder that is already built. Tests with
  the `Mock` device (Mock implements the shadow / apply / reject logic).

## 4. Verification

| Test | What |
|------|------|
| `test_route` (unit, `fx_route` alone, stub effects = "add id·k + delay") | 200 random permutations: output equals the composition in order. Apply is atomic: a half-written list is not used. 50 invalid lists are rejected, the order is kept and bit1 is set. The fade has no step larger than 1/128 of full scale |
| `test_fx_chain::test_routing` (16 / 24 bit) | structural check over 30 random orders, all effects on: in every frame the input of effect `order[k]` equals `slot_q[order[k-1]]` (hierarchical signal access). End to end: DYN→DIST→CAB→EQ against the existing Python block models in two orders, bit-exact. Latency is identical for all 30 orders |
| `test_timing_invariance` | extended: 5 random orders, identical at 16 and 1024 clocks per frame |
| `test_refv2` | default order re-recorded once (the latency changes), via `GME_REF_ONLY`. Before that, the new outputs are checked to equal the old ones shifted by the measured latency on the refs without enable/parameter changes |
| `test_system::test_chain_via_hps` | order written over the bridge, VERSION 0x0209, reject bit, read-back |
| board/tests (pytest, Mock) | `set_chain` register sequence, API POST `/api/chain` 200 at 0x0209 and 409 below, presets restore the order |
| Quartus | timing met, resource delta reported (expected ≈ +700 ALMs, 0 DSP, 0 M10K) |
| Board (checklist added to the step D test doc pattern) | DIST→REVERB vs REVERB→DIST, ECHO before/after DIST, MOD before DIST; drag in the page; reorder while playing: short dip only, no click |

## 5. Phases (each: full regression + Quartus + commit, Sonnet agents implement, I review)

* **E1** `fx_route.vhd` standalone (order shadow / apply / validation, slot registers, source muxes, order fade) +
  `test_route` with stub effects. Not wired in yet, so the regression stays green.
* **E2** integration: `FX_chain` uses `fx_route`, reg_file / gme_core 0x30..0x33, VERSION 0x0209; chain tests, timing
  invariance with random orders, refv2 re-record (shift check first), test_system, register_map.md (latencies measured).
* **E3** Quartus + SDC check (expected: no new exceptions; the slot registers are plain `fx`).
* **E4** board library / CLI / web (`ROUTING_VERSION`), Mock, tests.
* **E5** board test package (`docs/v2_stepE_board_test.md`), `.sof` build.

## 6. Questions for you

1. Option A (fixed ≈ 0.3 ms latency, small change) instead of the full Avalon-ST scheduler?
2. Order change with a ≈ 5 ms output dip, or switch instantly (may click)?
3. Off effects keep their place in the order (latency constant), OK?
