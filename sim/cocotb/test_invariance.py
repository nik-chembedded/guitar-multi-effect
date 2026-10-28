"""
test_invariance.py - one FX_chain configuration with ALL effects on, for the timing-invariance test.

test_runner.test_timing_invariance runs this module twice (GME_HALF = 8 and 512, i.e. 16-clock and
1024-clock frames, in two simulations), each run saving the output to the file named by GME_INV_OUT,
and requires the two outputs to be identical. The chain only advances on its strobes, so a block whose
result changes between the strobes of its consumers differently in the two timings would show up here.

Configuration: dynamics (gate + compressor), overdrive, distortion, cabinet (16-tap test .mif), EQ
(non-flat), modulated delay, tremolo, echo, reverb, XFADE on (the fades run in the middle of the
test); at frame 120 dynamics and EQ are switched off, at frame 250 on again (both are then fading).
D6: overdrive and distortion have non-zero output levels (+3 dB / -4 dB), changed at frame 300.

Step E (effect order): test_orders continues in the same simulation with the same configuration and five random
effect orders, applied one after the other through the chain ports (chain_order / chain_apply, order fade of
about 260 frames each, 300 frames per order); its output goes to <GME_INV_OUT without .npy>_orders.npy and must
also be identical at 16 and 1024 clocks per frame.
"""
import math
import os
import random
import sys
from pathlib import Path

import cocotb
import numpy as np

from fxdriver import (CAB, CHORUS, CLK_PER_HALF, DEFAULT_ORDER, DIST, DYN, ECHO, EQ, OD, REVERB, TREM, FxChain,
                      unpack_order)

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import eq_coefs as ec                                        # noqa: E402

FRAMES = 400
ALL = OD | TREM | ECHO | DIST | CHORUS | REVERB | CAB | DYN | EQ


def q8(db):
    return round(db * 256 / (20 * math.log10(2)))


async def configure(fx):
    """Non-flat EQ and every effect on."""
    ints, sh, _ = ec.coefficient_set_full(7, -5, 9)
    await fx.eq_write(ints, ec.scale_word(sh))
    fx.set(effects_enable=ALL,
           dyn_ctrl=3, gate_thresh=q8(-60), comp_thresh=q8(-18), comp_ratio=2, comp_attack=3,
           comp_release=6, comp_makeup=q8(4),
           od_drive=6000, od_gain=2, dist_type=1, dist_mix=128, od_level=q8(3), dist_level=q8(-4),
           cab_ctrl=(3 << 4) | (2 << 1),
           chorus_level=128, chorus_depth=40, chorus_rate=900, mod_base=100,
           trem_wave=8 + 1, trem_rate=2200, trem_depth=120,
           echo_time=90, echo_level=24000, echo_repeat=100,
           reverb_type=2, reverb_mix=90)


@cocotb.test()
async def test_run(dut):
    fx = FxChain(dut)
    assert fx.dw == 24
    await fx.start()
    dut._log.info("CLK_PER_HALF = %d (%d clocks per frame)", CLK_PER_HALF, 2 * CLK_PER_HALF)
    await configure(fx)
    rnd = random.Random(77)
    x = [round(3_000_000 * math.sin(2 * math.pi * 330 * n / 48000) * (1 if (n // 100) % 2 == 0 else 0.15)
               + rnd.randint(-400_000, 400_000)) for n in range(FRAMES)]

    def on_frame(n):
        if n == 120:
            fx.set(effects_enable=ALL & ~(DYN | EQ))
        elif n == 250:
            fx.set(effects_enable=ALL)
        elif n == 300:
            fx.set(od_level=q8(-6), dist_level=q8(5))

    y = await fx.run(x, on_frame=on_frame, raw=True)
    assert all(v is not None for v in y), "X/U in the output"
    out = np.array(y, dtype=np.int64)
    np.save(os.environ["GME_INV_OUT"], out)
    dut._log.info("saved %d frames to %s (peak %d, checksum %d)", len(out), os.environ["GME_INV_OUT"],
                  int(np.abs(out).max()), int(out.sum() % (1 << 40)))
    assert np.abs(out).max() > 100_000, "output too small to be a useful test"


ORDER_FRAMES = 300
N_ORDERS = 5


@cocotb.test()
async def test_orders(dut):
    """Five random effect orders (all effects on), applied through the chain ports after test_run (same simulation,
    the state continues): each order change fades for about 260 frames, 300 frames are played per order."""
    fx = FxChain(dut)
    assert fx.dw == 24
    await fx.start()                 # (restarts the clock; the chain keeps its state and its active order)
    await configure(fx)
    rnd = random.Random(1234)
    orders = []
    while len(orders) < N_ORDERS:
        o = list(range(9))
        rnd.shuffle(o)
        if o != DEFAULT_ORDER and o not in orders:
            orders.append(o)
    n = 0
    y = []
    for order in orders:
        await fx.apply_order(order)
        x = [round(3_000_000 * math.sin(2 * math.pi * 330 * (n + i) / 48000) * (1 if ((n + i) // 100) % 2 == 0 else 0.15)
                   + rnd.randint(-400_000, 400_000)) for i in range(ORDER_FRAMES)]
        y += await fx.run(x, raw=True)
        n += ORDER_FRAMES
        assert int(dut.chain_busy.value) == 0 and unpack_order(int(dut.chain_active.value)) == order
    assert all(v is not None for v in y), "X/U in the output"
    out = np.array(y, dtype=np.int64)
    path = os.environ["GME_INV_OUT"].replace(".npy", "_orders.npy")
    np.save(path, out)
    dut._log.info("saved %d frames of %d orders to %s (peak %d, checksum %d)", len(out), N_ORDERS, path,
                  int(np.abs(out).max()), int(out.sum() % (1 << 40)))
    assert np.abs(out).max() > 100_000, "output too small to be a useful test"
