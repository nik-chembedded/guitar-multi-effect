"""
test_route.py - fx_route (v2 step E1): run-time effect order, slot registers, order fade.

Toplevel route_wrap (hdl/route_wrap.vhd): fx_route with 9 stub effects fx_out(e) = (fx_in(e) + (e+1)*1000) * (2e+1)
modulo 2^DW (the odd factor makes the order matter), combinational for most ids and registered on half_tick for
ids 1, 5 and 7, so both kinds are covered. GME_DW selects 16 / 24 bit, GME_HALF (fxdriver) the clocks per frame.

Frame convention (like the chain): the input sample is written right after sample_tick and held for the whole
frame (in the board it is the chain's input register), so combinational and registered effects see the same
value. A sample written in frame n is therefore taken at the tick of frame n+1; every hop costs one frame, the
first one too: output(n) = order composition of input(n - N), latency N = 9 frames, for every order.

A Python model (class Model) of the whole block (slots, src / last, fade, validation) is compared with the DUT
in EVERY frame of every test: chain_out, busy (before and after the tick), rejected, order_active, gain. The
tests add independent checks: the composition of the effects, the latency, the exact gains of the fade.

The tests share one simulation and run in this order (test_powerup first: they continue from the state the
previous one left, with the model in step). GME_ROUTE_OUT=<file.npy>: test_invariance saves its outputs
(test_runner.test_route_invariance compares the runs at 16 and 1024 clocks per frame).
"""
import os
import random

import cocotb
import numpy as np
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge

from fxdriver import CLK_PER_HALF, to_signed

DW = int(os.environ.get("GME_DW", "24"))
N = 9
MASK = (1 << DW) - 1
REG_IDS = (1, 5, 7)                                  # registered stubs (route_wrap.vhd)
DEFAULT = [7, 0, 3, 6, 8, 4, 1, 2, 5]                # DYN OD DIST CAB EQ MOD TREM ECHO REVERB
LAT = N                                              # frames from an input sample to its output


def pack(order):
    return sum(v << (4 * k) for k, v in enumerate(order))


def unpack(word):
    return [(word >> (4 * k)) & 15 for k in range(N)]


def is_perm(order):
    return sorted(order) == list(range(N))


def stub(e, v):
    """Effect e of the stub design, v signed."""
    return to_signed(((v + (e + 1) * 1000) * (2 * e + 1)) & MASK, DW)


def compose(order, v):
    for e in order:
        v = stub(e, v)
    return v


class Model:
    """Bit-exact model of fx_route + the stubs (one call of tick() per sample_tick)."""

    def __init__(self):
        self.slots = [0] * N
        self.set_active(DEFAULT)
        self.pend = list(DEFAULT)
        self.g = 128
        self.dn = False
        self.busy = False
        self.rej = False
        self.ticks = 0

    def set_active(self, order):
        self.active = list(order)
        self.src = [N] * N
        for k in range(1, N):
            self.src[order[k]] = order[k - 1]
        self.last = order[N - 1]

    def apply(self, word):
        order = unpack(word)
        if is_perm(order):
            self.rej, self.pend, self.dn, self.busy = False, order, True, True
        else:
            self.rej = True

    def tick(self, x):
        new = []
        for e in range(N):
            v = stub(e, x if self.src[e] == N else self.slots[self.src[e]])
            if self.ticks == 0 and e in REG_IDS:          # the registered stubs have not seen a half_tick yet
                v = 0
            new.append(v)
        self.slots = new
        self.ticks += 1
        if self.dn:
            if self.g <= 1:
                self.g = 0
                self.set_active(self.pend)
                self.dn = False
            else:
                self.g -= 1
        elif self.g < 128:
            self.g += 1
            if self.g == 128:
                self.busy = False
        return to_signed((self.slots[self.last] * self.g >> 7) & MASK, DW)


class Rig:
    def __init__(self, dut):
        self.dut = dut
        self.m = Model()
        self.rnd = random.Random(2026)
        self.cur_x = 0                                # chain_in as the DUT sees it
        self.xs, self.outs, self.gs, self.busys, self.actives = [], [], [], [], []
        self.have_g = None

    async def start(self):
        d = self.dut
        Clock(d.clk, 10, unit="ns").start()
        if self.xs:                                   # later tests: the state continues
            return
        for name in ("sample_tick", "half_tick", "apply", "order_in", "chain_in"):
            getattr(d, name).value = 0
        await ClockCycles(d.clk, 4)

    def rx(self):
        return self.rnd.randrange(-(1 << (DW - 1)), 1 << (DW - 1))

    def perm(self):
        p = list(range(N))
        self.rnd.shuffle(p)
        return p

    def read_g(self):
        if self.have_g is None:
            try:
                int(self.dut.u_route.g.value)
                self.have_g = True
            except Exception:                         # noqa: BLE001 - internal signal not reachable
                self.have_g = False
        return int(self.dut.u_route.g.value) if self.have_g else None

    async def frame(self, x=None, apply=None, where="pre", set_only=None):
        """One frame. apply = list word to write to order_in and apply (pulse before the tick, or in the same
        clock as the tick: where="tick"); set_only = word written to order_in without apply. x = the sample
        written after the tick (random by default). Compares the DUT with the model; returns the output."""
        d, m = self.dut, self.m
        if x is None:
            x = self.rx()
        if set_only is not None:
            d.order_in.value = set_only
        if apply is not None:
            d.order_in.value = apply
        if apply is not None and where == "pre":
            d.apply.value = 1
            await RisingEdge(d.clk)
            d.apply.value = 0
            m.apply(apply)
        await ClockCycles(d.clk, CLK_PER_HALF)
        busy_pre = int(d.busy.value)
        exp_busy_pre = m.busy
        d.sample_tick.value = 1
        if apply is not None and where == "tick":
            d.apply.value = 1
            m.apply(apply)
        exp = m.tick(self.cur_x)
        await RisingEdge(d.clk)
        d.sample_tick.value = 0
        d.apply.value = 0
        d.chain_in.value = x & MASK
        self.cur_x = x
        await ClockCycles(d.clk, CLK_PER_HALF - 1)
        d.half_tick.value = 1
        await RisingEdge(d.clk)
        d.half_tick.value = 0
        await RisingEdge(d.clk)
        n = len(self.xs)
        assert d.chain_out.value.is_resolvable, "frame %d: chain_out is X" % n
        out = to_signed(int(d.chain_out.value), DW)
        g = self.read_g()
        here = "frame %d" % n
        assert out == exp, "%s: chain_out %d, model %d (g %d)" % (here, out, exp, m.g)
        assert busy_pre == (1 if exp_busy_pre else 0), "%s: busy before the tick %d, model %s" % (here, busy_pre, exp_busy_pre)
        assert int(d.busy.value) == (1 if m.busy else 0), "%s: busy %s, model %s" % (here, d.busy.value, m.busy)
        assert int(d.rejected.value) == (1 if m.rej else 0), "%s: rejected %s, model %s" % (here, d.rejected.value, m.rej)
        assert int(d.order_active.value) == pack(m.active), "%s: order_active %x, model %x" % (
            here, int(d.order_active.value), pack(m.active))
        if g is not None:
            assert g == m.g, "%s: gain %d, model %d" % (here, g, m.g)
        self.xs.append(x)
        self.outs.append(out)
        self.gs.append(m.g)
        self.busys.append(m.busy)
        self.actives.append(list(m.active))
        return out

    async def run(self, frames):
        for _ in range(frames):
            await self.frame()

    async def settle(self, extra=12):
        """Run until the fade is over and the pipeline is flushed (random input)."""
        while self.m.busy:
            await self.frame()
        await self.run(N + extra)

    def check_composition(self, order, count=12):
        """Independent of the model: the last `count` outputs are the composition of `order` applied to the
        input of LAT frames earlier."""
        n = len(self.xs)
        for i in range(n - count, n):
            assert self.outs[i] == compose(order, self.xs[i - LAT]), "frame %d: output %d, composition %d" % (
                i, self.outs[i], compose(order, self.xs[i - LAT]))

    def latency(self, order, count=12):
        """Smallest latency (frames) at which the last `count` outputs equal the composition, or None."""
        n = len(self.xs)
        for lat in range(0, 24):
            if all(self.outs[i] == compose(order, self.xs[i - lat]) for i in range(n - count, n)):
                return lat
        return None


_rig = None


async def rig(dut):
    global _rig
    if _rig is None:
        _rig = Rig(dut)
    await _rig.start()
    return _rig


@cocotb.test()
async def test_powerup(dut):
    """Power-up: default order active, idle, output = the default composition, latency 9 frames."""
    r = await rig(dut)
    assert int(dut.order_active.value) == pack(DEFAULT) and int(dut.busy.value) == 0 and int(dut.rejected.value) == 0
    await r.run(40)
    assert all(not b for b in r.busys) and all(a == DEFAULT for a in r.actives)
    r.check_composition(DEFAULT)
    lat = r.latency(DEFAULT)
    assert lat == LAT, "latency %s frames" % lat
    assert r.read_g() in (None, 128)
    dut._log.info("power-up: default order %x, latency %d frames (%d hops of one frame), g %s",
                  pack(DEFAULT), lat, N, r.read_g())


@cocotb.test()
async def test_permutations(dut):
    """200 random permutations one after another: bit-exact to the model every frame, composition and latency
    after each change, order_active, rejected = 0."""
    r = await rig(dut)
    for i in range(200):
        order = r.perm()
        await r.frame(apply=pack(order))
        await r.settle()
        assert not r.m.busy and r.actives[-1] == order and not r.m.rej
        assert int(dut.order_active.value) == pack(order) and int(dut.rejected.value) == 0 and int(dut.busy.value) == 0
        r.check_composition(order)
        lat = r.latency(order)
        assert lat == LAT, "order %s: latency %s frames" % (order, lat)
    dut._log.info("200 permutations: composition bit-exact, latency %d frames for every order", LAT)


def bad_list(r, order):
    """A list that is not a permutation: duplicates, ids 9..15, or both."""
    o = list(order)
    kind = r.rnd.randrange(4)
    k = r.rnd.randrange(N)
    if kind == 0:                                         # duplicate
        o[k] = o[(k + 1 + r.rnd.randrange(N - 1)) % N]
    elif kind == 1:                                       # out-of-range id
        o[k] = r.rnd.randrange(N, 16)
    elif kind == 2:                                       # all the same / all zero
        o = [r.rnd.randrange(16)] * N
    else:                                                 # random nibbles
        o = [r.rnd.randrange(16) for _ in range(N)]
    return o if not is_perm(o) else bad_list(r, order)


@cocotb.test()
async def test_invalid(dut):
    """50 invalid lists: rejected = 1, order_active and output unchanged, no fade (busy stays 0)."""
    r = await rig(dut)
    base = list(r.actives[-1])
    for i in range(50):
        await r.frame(apply=pack(bad_list(r, base)))
        assert int(dut.rejected.value) == 1
        for _ in range(6):
            await r.frame()
            assert int(dut.busy.value) == 0 and int(dut.rejected.value) == 1
            assert int(dut.order_active.value) == pack(base)
        assert all(not b for b in r.busys[-7:]) and all(g == 128 for g in r.gs[-7:])
        r.check_composition(base, 6)
        assert r.latency(base, 6) == LAT
    # a valid list clears rejected, an invalid one during the fade does not disturb it
    new = r.perm()
    await r.frame(apply=pack(new))
    assert int(dut.rejected.value) == 0
    await r.run(30)
    await r.frame(apply=pack(bad_list(r, new)))
    assert int(dut.rejected.value) == 1 and int(dut.busy.value) == 1
    await r.settle()
    assert r.actives[-1] == new and int(dut.rejected.value) == 1
    r.check_composition(new)
    dut._log.info("50 invalid lists rejected: order, output and busy unchanged; invalid list during a fade ignored")


@cocotb.test()
async def test_atomic(dut):
    """Writing order_in without apply changes nothing; the list captured at apply is the one used."""
    r = await rig(dut)
    base = list(r.actives[-1])
    for _ in range(5):
        await r.frame(set_only=pack(r.perm()))
        await r.run(60)
    assert all(a == base for a in r.actives[-300:]) and not any(r.busys[-300:])
    assert int(dut.order_active.value) == pack(base)
    r.check_composition(base)
    a, b = r.perm(), r.perm()
    await r.frame(apply=pack(a))
    for k in range(40):                                   # order_in changes (also to a bad list) during the fade
        await r.frame(set_only=pack(b) if k % 2 else pack(bad_list(r, b)))
    await r.settle()
    assert r.actives[-1] == a and r.m.pend == a
    r.check_composition(a)
    dut._log.info("order_in without apply: no effect; the list of the apply is used")


@cocotb.test()
async def test_fade(dut):
    """Fade of one order change with a constant input: gain 128 -> 0 -> 128 in steps of 1/128 per frame (exact
    values, floor, also for negative samples), switch frame, busy timing."""
    r = await rig(dut)
    for trial in range(6):
        c = [r.rx(), -(1 << (DW - 1)), (1 << (DW - 1)) - 1, -12345, 777, r.rx()][trial]
        old = list(r.actives[-1])
        new = r.perm()
        if new == old:
            new = new[1:] + new[:1]
        s_old, s_new = compose(old, c), compose(new, c)
        for _ in range(N + 4):                                # flush with the constant
            await r.frame(x=c)
        assert r.outs[-1] == s_old
        a = len(r.xs)
        await r.frame(x=c, apply=pack(new))
        for i in range(1, 256):
            await r.frame(x=c)
        await r.frame(x=c)
        for i in range(256):
            f = a + i
            if i < 128:                                       # g = 127 - i
                g, s, act = 127 - i, s_old, old if i < 127 else new
            else:                                             # g = i - 127
                g, s, act = i - 127, s_new, new
            assert r.gs[f] == g, "frame +%d: gain %d, expected %d" % (i, r.gs[f], g)
            if i < 128 or i - 128 >= N - 1:                   # up-ramp: new slot values arrive after the pipeline
                assert r.outs[f] == (s * g) >> 7, "frame +%d: output %d, expected %d" % (i, r.outs[f], (s * g) >> 7)
            assert r.actives[f] == act, "frame +%d: order_active switches at +127" % i
            assert r.busys[f] == (i < 255), "frame +%d: busy %s" % (i, r.busys[f])
        assert r.outs[a + 255] == s_new and r.outs[a + 256] == s_new
        assert r.gs[a + 255] == 128 and r.gs[a + 127] == 0 and r.outs[a + 127] == 0
        steps = [abs(y - x) for x, y in zip(r.gs[a - 1:a + 256], r.gs[a:a + 256])]
        assert max(steps) == 1 and min(steps) == 1
    dut._log.info("fade: gain 127 .. 0 (switch at frame +127) .. 128 (busy until +255), exact floor, 6 constants")


async def fade_scenario(r, first, extra, tail=True):
    """Apply `first`, then the (offset, list, where) applies of `extra` (offset in frames after the first
    apply). Checks the gain never jumps and the newest valid list ends up active."""
    await r.settle()
    last_valid = list(r.actives[-1])
    start = len(r.xs)
    events = {off: (w, wh) for off, w, wh in extra}
    events[0] = (pack(first), "pre")
    for f in range(max(events) + 1):
        if f in events:
            w, wh = events[f]
            if is_perm(unpack(w)):
                last_valid = unpack(w)
            await r.frame(apply=w, where=wh)
        else:
            await r.frame()
    await r.settle()
    gs = r.gs[start - 1:]
    assert all(abs(b - a) <= 1 for a, b in zip(gs, gs[1:])), "gain jumps"
    assert r.actives[-1] == last_valid and int(r.dut.order_active.value) == pack(last_valid)
    r.check_composition(last_valid)
    return last_valid


@cocotb.test()
async def test_apply_during_fade(dut):
    """Apply during the fade-down, at the switch, during the fade-up (turn-around without a jump), in the last
    frame, in the same clock as the tick; the newest list wins."""
    r = await rig(dut)
    offsets = [1, 20, 126, 127, 128, 129, 140, 200, 253, 254, 255, 256, 257]
    n = 0
    for off in offsets:
        for where in ("pre", "tick"):
            first, second = r.perm(), r.perm()
            await fade_scenario(r, first, [(off, pack(second), where)])
            n += 1
    for _ in range(25):                                   # several applies, valid and invalid, at random offsets
        evs = [(r.rnd.randrange(1, 400), pack(r.perm()) if r.rnd.random() < 0.7 else pack(bad_list(r, DEFAULT)),
                r.rnd.choice(["pre", "tick"])) for _ in range(r.rnd.randrange(2, 5))]
        seen = set()
        evs = [e for e in evs if not (e[0] in seen or seen.add(e[0]))]
        await fade_scenario(r, r.perm(), evs)
        n += 1
    # explicit turn-around: apply 150 frames after the first one (g peaks at 22), no jump
    s = len(r.xs)
    await fade_scenario(r, r.perm(), [(150, pack(r.perm()), "pre")])
    seg = r.gs[s:]
    peak = max(i for i in range(1, len(seg) - 1) if seg[i - 1] < seg[i] > seg[i + 1])
    assert seg[peak] == 149 - 127 and seg[peak - 1] == seg[peak] - 1 and seg[peak + 1] == seg[peak] - 1, seg[peak - 2:peak + 3]
    dut._log.info("apply during the fade: %d scenarios, newest list wins, gain steps of 1", n)


@cocotb.test()
async def test_invariance(dut):
    """A fixed scenario (changes, rejects, apply mid-fade); the outputs go to GME_ROUTE_OUT for the comparison
    between 16-clock and 1024-clock frames (test_runner.test_route_invariance)."""
    r = await rig(dut)
    rnd = random.Random(7)
    r.rnd = rnd
    start = len(r.xs)
    for k in range(3):
        await fade_scenario(r, r.perm(), [(40 + 90 * k, pack(r.perm()), "pre")])
        await r.frame(apply=pack(bad_list(r, DEFAULT)))
        await r.run(20)
    out = np.array(r.outs[start:], dtype=np.int64)
    path = os.environ.get("GME_ROUTE_OUT")
    if path:
        np.save(path, out)
    dut._log.info("invariance scenario: %d frames", len(out))
