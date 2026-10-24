"""
test_ref.py - bit-exact regression against recorded reference outputs.

GME_REF_MODE=record  : run every preset and save the outputs to ref/<preset>.npy
GME_REF_MODE=check   : (default) run the same presets and require identical output

The references in ref/ were recorded from the v1 effect chain (LRCLK-clocked,
commit 8b6995a). v2 step B1 (sys_clk + strobes) must reproduce them exactly.
All presets run in one simulation, in a fixed order, with deterministic
stimuli, so the state carried between presets (delay RAMs, LFO phase) is the
same in both modes.
"""
import math
import os
import random
from pathlib import Path

import cocotb
import numpy as np

from fxdriver import CHORUS, DIST, ECHO, OD, REVERB, TREM, FxChain

REF_DIR = Path(__file__).resolve().parent / "ref"
MODE = os.environ.get("GME_REF_MODE", "check")
NONE = 99999                      # marker for X/U output samples


def stimulus(seed):
    rnd = random.Random(seed)
    x = [rnd.randint(-20000, 20000) for _ in range(1500)]
    x += [round(14000 * math.sin(2 * math.pi * 440 * n / 48000)) for n in range(3000)]
    x += [16000 if n % 300 == 50 else 0 for n in range(1500)]
    return x


ALL = OD | TREM | ECHO | DIST | CHORUS | REVERB
# name -> (registers, registers changed at frame 3000 or None)
PRESETS = {
    "bypass":        (dict(effects_enable=0), None),
    "overdrive":     (dict(effects_enable=OD, od_drive=3000, od_gain=4), dict(od_drive=9000, od_gain=3)),
    **{"dist_%s_%d" % (n, m): (dict(effects_enable=DIST, dist_type=t, dist_mix=m), None)
       for t, n in enumerate(("soft", "medium", "hard")) for m in (255, 128)},
    **{"trem_w%d" % w: (dict(effects_enable=TREM, trem_wave=w, trem_depth=255), None) for w in range(8)},
    "trem_w2_d128":  (dict(effects_enable=TREM, trem_wave=2, trem_depth=128), dict(trem_wave=4)),
    "chorus_a":      (dict(effects_enable=CHORUS, chorus_level=32768, chorus_depth=200, chorus_rate=20), None),
    "chorus_b":      (dict(effects_enable=CHORUS, chorus_level=60000, chorus_depth=600, chorus_rate=3),
                      dict(chorus_depth=100)),
    "echo_a":        (dict(effects_enable=ECHO, echo_time=1200, echo_level=32768, echo_repeat=128), None),
    "echo_b":        (dict(effects_enable=ECHO, echo_time=300, echo_level=50000, echo_repeat=220),
                      dict(echo_time=700)),
    **{"reverb_t%d" % t: (dict(effects_enable=REVERB, reverb_type=t, reverb_mix=128), None) for t in range(4)},
    "combo_all":     (dict(effects_enable=ALL, od_drive=6000, od_gain=2, dist_type=1, dist_mix=128,
                           chorus_level=20000, chorus_depth=300, chorus_rate=10, trem_wave=0,
                           trem_depth=150, echo_time=2000, echo_level=20000, echo_repeat=100,
                           reverb_type=1, reverb_mix=80), None),
    "combo_change":  (dict(effects_enable=DIST | ECHO | REVERB, dist_type=2, dist_mix=200, echo_time=900,
                           echo_level=25000, echo_repeat=90, reverb_type=0, reverb_mix=100),
                      dict(reverb_type=3, effects_enable=DIST | REVERB)),
}
ZERO = {k: 0 for k in ("effects_enable", "od_drive", "od_gain", "trem_depth", "trem_wave", "echo_time",
                       "echo_level", "echo_repeat", "chorus_rate", "chorus_level", "chorus_depth",
                       "dist_mix", "dist_type", "reverb_type", "reverb_mix")}


@cocotb.test()
async def test_reference(dut):
    REF_DIR.mkdir(exist_ok=True)
    fx = FxChain(dut)
    await fx.start()
    failures = []
    for i, (name, (regs, change)) in enumerate(PRESETS.items()):
        fx.set(**{**ZERO, **regs})

        def on_frame(n, change=change):
            if change and n == 3000:
                fx.set(**change)
        y = await fx.run(stimulus(100 + i), on_frame=on_frame)
        y = np.array([NONE if v is None else v for v in y], dtype=np.int32)
        path = REF_DIR / (name + ".npy")
        if MODE == "record":
            np.save(path, y)
            dut._log.info("recorded %-14s %d frames, peak %d", name, len(y), int(np.abs(y[y != NONE]).max()))
        else:
            ref = np.load(path)
            mask = ref != NONE
            bad = np.nonzero((ref != y) & mask)[0]
            if len(bad):
                failures.append("%s: %d mismatches, first at frame %d (ref %d, got %d)"
                                % (name, len(bad), bad[0], ref[bad[0]], y[bad[0]]))
                dut._log.error(failures[-1])
            else:
                dut._log.info("%-14s bit-exact (%d frames)", name, int(mask.sum()))
    assert not failures, "%d presets differ from the reference" % len(failures)
