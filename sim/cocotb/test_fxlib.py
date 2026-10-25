"""
test_fxlib.py - the fixed-point library fx_pkg.vhd (v2 step C) against Python:
random and corner values (full scale, 0, -1, +-1 LSB) for 16 and 24 bits.
"""
import random

import cocotb
from cocotb.triggers import Timer


def sat(v, w):
    return max(-(1 << (w - 1)), min((1 << (w - 1)) - 1, v))


def trunc_div(v, s):
    return -((-v) >> s) if v < 0 else v >> s


def expected(a24, b24, a16, b16, k, ks, m):
    return {
        "sat16_o": sat(a24, 16),
        "addsat24_o": sat(a24 + b24, 24),
        "addsat16_o": sat(a16 + b16, 16),
        "mulshr_o": (a24 * k) >> 16,
        "smulshr_o": (a24 * ks) >> 16,
        "div64_o": trunc_div(a24, 6),
        "mix24_o": (m * a24 + (255 - m) * b24) >> 8,     # mix8(dry = b, wet = a)
        "mix16_o": (m * a16 + (255 - m) * b16) >> 8,
    }


def corners(w):
    f = 1 << (w - 1)
    return [-f, -f + 1, -1, 0, 1, f - 2, f - 1]


@cocotb.test()
async def test_fxlib(dut):
    """Every fx_pkg function, corner cases and 20000 random vectors."""
    rnd = random.Random(5)
    vectors = []
    for a in corners(24):
        for b in corners(24):
            vectors.append((a, b, a >> 8, b >> 8, rnd.choice([0, 1, 65535, 32768]),
                            rnd.choice([-65535, 65535, -1, 0]), rnd.choice([0, 1, 128, 254, 255])))
    for _ in range(20000):
        vectors.append((rnd.randint(-(1 << 23), (1 << 23) - 1), rnd.randint(-(1 << 23), (1 << 23) - 1),
                        rnd.randint(-32768, 32767), rnd.randint(-32768, 32767),
                        rnd.getrandbits(16), rnd.randint(-65535, 65535), rnd.getrandbits(8)))
    for v in vectors:
        a24, b24, a16, b16, k, ks, m = v
        dut.a24.value, dut.b24.value, dut.a16.value, dut.b16.value = a24, b24, a16, b16
        dut.k.value, dut.ks.value, dut.m.value = k, ks, m
        await Timer(1, unit="ns")
        for port, exp in expected(*v).items():
            got = getattr(dut, port).value.to_signed()
            assert got == exp, "%s for %s: got %d expected %d" % (port, v, got, exp)
    dut._log.info("fx_pkg: %d vectors x 8 functions bit-exact", len(vectors))
