#!/usr/bin/env python
"""
eq_coefs.py - coefficient sets for the 3-band EQ block (fpga/rtl/eq3.vhd).

Three biquad sections in series, RBJ cookbook formulas, a0 normalised to 1:
    section 0  low shelf   (default 100 Hz)
    section 1  peaking mid (default 800 Hz, Q 0.9)
    section 2  high shelf  (default 3.5 kHz)
Each section has 5 coefficients in the order  b0 b1 b2 a1 a2  (the block's
coefficient write address is section * 5 + index), signed 18 bit, Q2.16:
    integer = round(coef * 65536), range -131072 .. 131071 (-2.0 .. +1.99998).
Scale register (write address 15, 2 bits per section, section 0 in bits 1:0, see
scale_word()): the block multiplies a section's feed-forward sum by 2^n, so b is stored as
b / 2^n. Needed for a boosting high shelf (b0 ~ 4 at +12 dB); write it with the 15 coefficients.
Difference equation (Direct Form I):  y = b0 x + b1 x1 + b2 x2 - a1 y1 - a2 y2.

Only the standard library (math) is used and the file is Python 2.7 / 3
compatible, so the board tool (gme_hps.py) can import it:

    import eq_coefs
    words = eq_coefs.coefficient_set(bass_db=6, mid_db=-3, treble_db=2)   # 15 ints
    # write words[i] & 0x3FFFF to the coefficient port at address i, scale_word(shifts) to
    #   address 15 (coefficient_set_full returns the shifts), then pulse apply

CLI:  python eq_coefs.py --bass 6 --mid -3 --treble 2 [--fs 48000]
"""
from __future__ import print_function, division

import argparse
import cmath
import math
import sys

FS = 48000.0
FRAC = 16                       # Q2.16
COEF_BITS = 18
CMAX = (1 << (COEF_BITS - 1)) - 1
CMIN = -(1 << (COEF_BITS - 1))
GAIN_LIMIT_DB = 12.0

DEF_BASS_F = 100.0
DEF_MID_F = 800.0
DEF_MID_Q = 0.9
DEF_TREBLE_F = 3500.0
DEF_SLOPE = 1.0                 # RBJ shelf slope S (1 = steepest without overshoot)


def _check_gain(g):
    if abs(g) > GAIN_LIMIT_DB + 1e-9:
        raise ValueError("gain %.2f dB outside +-%g dB" % (g, GAIN_LIMIT_DB))


def low_shelf(gain_db, f0=DEF_BASS_F, slope=DEF_SLOPE, fs=FS):
    """RBJ low shelf -> (b, a), a = [1, a1, a2]."""
    _check_gain(gain_db)
    A = 10 ** (gain_db / 40.0)
    w = 2 * math.pi * f0 / fs
    c, s = math.cos(w), math.sin(w)
    alpha = s / 2.0 * math.sqrt((A + 1 / A) * (1 / slope - 1) + 2)
    r = 2 * math.sqrt(A) * alpha
    b = [A * ((A + 1) - (A - 1) * c + r),
         2 * A * ((A - 1) - (A + 1) * c),
         A * ((A + 1) - (A - 1) * c - r)]
    a = [(A + 1) + (A - 1) * c + r,
         -2 * ((A - 1) + (A + 1) * c),
         (A + 1) + (A - 1) * c - r]
    return [x / a[0] for x in b], [1.0, a[1] / a[0], a[2] / a[0]]


def high_shelf(gain_db, f0=DEF_TREBLE_F, slope=DEF_SLOPE, fs=FS):
    """RBJ high shelf -> (b, a)."""
    _check_gain(gain_db)
    A = 10 ** (gain_db / 40.0)
    w = 2 * math.pi * f0 / fs
    c, s = math.cos(w), math.sin(w)
    alpha = s / 2.0 * math.sqrt((A + 1 / A) * (1 / slope - 1) + 2)
    r = 2 * math.sqrt(A) * alpha
    b = [A * ((A + 1) + (A - 1) * c + r),
         -2 * A * ((A - 1) + (A + 1) * c),
         A * ((A + 1) + (A - 1) * c - r)]
    a = [(A + 1) - (A - 1) * c + r,
         2 * ((A - 1) - (A + 1) * c),
         (A + 1) - (A - 1) * c - r]
    return [x / a[0] for x in b], [1.0, a[1] / a[0], a[2] / a[0]]


def peaking(gain_db, f0=DEF_MID_F, q=DEF_MID_Q, fs=FS):
    """RBJ peaking EQ -> (b, a)."""
    _check_gain(gain_db)
    A = 10 ** (gain_db / 40.0)
    w = 2 * math.pi * f0 / fs
    c = math.cos(w)
    alpha = math.sin(w) / (2.0 * q)
    b = [1 + alpha * A, -2 * c, 1 - alpha * A]
    a = [1 + alpha / A, -2 * c, 1 - alpha / A]
    return [x / a[0] for x in b], [1.0, a[1] / a[0], a[2] / a[0]]


def section_floats(bass_db=0.0, mid_db=0.0, treble_db=0.0, bass_f=DEF_BASS_F, mid_f=DEF_MID_F,
                   mid_q=DEF_MID_Q, treble_f=DEF_TREBLE_F, slope=DEF_SLOPE, fs=FS):
    """The three ideal (float) sections [(b, a), ...]. A 0 dB section is exactly unity."""
    gains = (bass_db, mid_db, treble_db)
    secs = [low_shelf(bass_db, bass_f, slope, fs),
            peaking(mid_db, mid_f, mid_q, fs),
            high_shelf(treble_db, treble_f, slope, fs)]
    return [([1.0, 0.0, 0.0], [1.0, 0.0, 0.0]) if g == 0 else sc for g, sc in zip(gains, secs)]


def quantise(x):
    """Float -> Q2.16 integer, round to nearest, clamped to the 18-bit range.
    Returns (integer, clipped)."""
    v = int(math.floor(x * (1 << FRAC) + 0.5))
    if v > CMAX:
        return CMAX, True
    if v < CMIN:
        return CMIN, True
    return v, False


def _grid(fs, n=64):
    return [40.0 * (min(20000.0, 0.45 * fs) / 40.0) ** (i / (n - 1.0)) for i in range(n)]


def _mag_db_list(k, shift, zs):
    """|H| in dB for integer coefficients k = [b0 b1 b2 a1 a2] (b scaled by 2^shift)."""
    sc = float(1 << FRAC)
    g = float(1 << shift) / sc
    b0, b1, b2 = k[0] * g, k[1] * g, k[2] * g
    a1, a2 = k[3] / sc, k[4] / sc
    out = []
    for z1 in zs:
        z2 = z1 * z1
        h = (b0 + b1 * z1 + b2 * z2) / (1 + a1 * z1 + a2 * z2)
        out.append(20 * math.log10(max(abs(h), 1e-12)))
    return out


def quantise_section(b, a, fs=FS, radius=2, optimise=True):
    """Quantise one section to Q2.16.

    Returns (ints[5], shift, clipped).  Large feed-forward coefficients (a high shelf
    boosting +12 dB has b0 ~ 4, beyond the +-2 range of Q2.16) are divided by 2^shift
    (shift = 0..3, the smallest that fits) and the block multiplies the feed-forward sum
    by 2^shift again (scale register, write address 15).

    With `optimise`, the integers are searched within +-radius LSB of the rounded values
    for the set whose magnitude response deviates least (max error in dB over 40 Hz ..
    20 kHz) from the ideal float response: a plain rounding of a 100 Hz shelf moves the
    pole pair near z = 1 enough to cost up to 0.6 dB at 50 Hz.
    """
    shift = 0
    while shift < 3 and max(abs(b[0]), abs(b[1]), abs(b[2])) / (1 << shift) > CMAX / 65536.0:
        shift += 1
    fl = [b[0] / (1 << shift), b[1] / (1 << shift), b[2] / (1 << shift), a[1], a[2]]
    base, clipped = [], False
    for x in fl:
        v, c = quantise(x)
        base.append(v)
        clipped = clipped or c
    if not optimise or (b[0] == 1.0 and b[1] == 0.0 and b[2] == 0.0 and a[1] == 0.0 and a[2] == 0.0):
        return base, shift, clipped
    zs = [cmath.exp(-2j * math.pi * f / fs) for f in _grid(fs)]
    ideal = []
    for z1 in zs:
        z2 = z1 * z1
        h = (b[0] + b[1] * z1 + b[2] * z2) / (1 + a[1] * z1 + a[2] * z2)
        ideal.append(20 * math.log10(max(abs(h), 1e-12)))
    best, best_err = base, None
    rng = range(-radius, radius + 1)
    for d0 in rng:
        for d1 in rng:
            for d2 in rng:
                for d3 in rng:
                    for d4 in rng:
                        k = [base[0] + d0, base[1] + d1, base[2] + d2, base[3] + d3, base[4] + d4]
                        if max(k) > CMAX or min(k) < CMIN:
                            continue
                        m = _mag_db_list(k, shift, zs)
                        err = max(abs(u - v) for u, v in zip(m, ideal))
                        if best_err is None or err < best_err:
                            best, best_err = k, err
    return best, shift, clipped


def coefficient_set_full(bass_db=0.0, mid_db=0.0, treble_db=0.0, optimise=True, **kw):
    """-> (15 integers, shifts[3], clipped). `kw`: bass_f, mid_f, mid_q, treble_f, slope, fs."""
    fs = kw.get("fs", FS)
    ints, shifts, clipped = [], [], False
    for b, a in section_floats(bass_db, mid_db, treble_db, **kw):
        k, sh, c = quantise_section(b, a, fs, optimise=optimise)
        ints += k
        shifts.append(sh)
        clipped = clipped or c
    return ints, shifts, clipped


def coefficient_set(bass_db=0.0, mid_db=0.0, treble_db=0.0, **kw):
    """The 15 signed Q2.16 integers (section * 5 + [b0 b1 b2 a1 a2]).  Use
    coefficient_set_full() to get the scale shifts as well; any section with a feed-forward
    coefficient beyond +-2 (treble boost) needs them (see scale_word)."""
    return coefficient_set_full(bass_db, mid_db, treble_db, **kw)[0]


def scale_word(shifts):
    """Value for write address 15: 2 bits per section, section 0 in bits 1:0."""
    return shifts[0] | (shifts[1] << 2) | (shifts[2] << 4)


def to_float_sections(ints, shifts=(0, 0, 0)):
    """15 Q2.16 integers (+ scale shifts) -> [(b, a), ...] floats (the quantised response)."""
    out = []
    for s in range(3):
        k = [v / float(1 << FRAC) for v in ints[5 * s:5 * s + 5]]
        g = float(1 << shifts[s])
        out.append(([k[0] * g, k[1] * g, k[2] * g], [1.0, k[3], k[4]]))
    return out


def word18(v):
    """Signed coefficient -> 18-bit two's complement word for the write port."""
    return v & ((1 << COEF_BITS) - 1)


def response(b, a, f, fs=FS):
    z1 = cmath.exp(-2j * math.pi * f / fs)
    z2 = z1 * z1
    return (b[0] + b[1] * z1 + b[2] * z2) / (1 + a[1] * z1 + a[2] * z2)


def cascade_db(sections, f, fs=FS):
    """Magnitude of the cascade in dB at f."""
    h = 1.0
    for b, a in sections:
        h *= response(b, a, f, fs)
    return 20 * math.log10(max(abs(h), 1e-12))


def main(argv=None):
    p = argparse.ArgumentParser(description="3-band EQ coefficients (Q2.16, 15 integers)")
    p.add_argument("--bass", type=float, default=0.0, help="low shelf gain, dB (-12..12)")
    p.add_argument("--mid", type=float, default=0.0, help="peaking mid gain, dB (-12..12)")
    p.add_argument("--treble", type=float, default=0.0, help="high shelf gain, dB (-12..12)")
    p.add_argument("--bass-f", type=float, default=DEF_BASS_F)
    p.add_argument("--mid-f", type=float, default=DEF_MID_F)
    p.add_argument("--mid-q", type=float, default=DEF_MID_Q)
    p.add_argument("--treble-f", type=float, default=DEF_TREBLE_F)
    p.add_argument("--slope", type=float, default=DEF_SLOPE, help="shelf slope S")
    p.add_argument("--fs", type=float, default=FS)
    args = p.parse_args(argv)
    ints, shifts, clipped = coefficient_set_full(args.bass, args.mid, args.treble, bass_f=args.bass_f,
                                                 mid_f=args.mid_f, mid_q=args.mid_q,
                                                 treble_f=args.treble_f, slope=args.slope, fs=args.fs)
    names = ["b0", "b1", "b2", "a1", "a2"]
    for s, sec in enumerate(("low shelf", "mid peak", "high shelf")):
        print("section %d (%s)" % (s, sec))
        for i in range(5):
            v = ints[5 * s + i]
            print("  addr %2d  %s = %8d  0x%05X  (%+.6f)" % (5 * s + i, names[i], v, word18(v),
                                                        v / 65536.0))
    print("addr 15  scale = 0x%02X  (section shifts %d %d %d)" % (scale_word(shifts), shifts[0],
                                                              shifts[1], shifts[2]))
    print("ints:", " ".join(str(v) for v in ints), "  scale:", scale_word(shifts))
    if clipped:
        sys.stderr.write("warning: a coefficient was clamped to the Q2.16 range\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
