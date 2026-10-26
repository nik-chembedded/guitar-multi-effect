#!/usr/bin/env python3
"""
level_presets.py - loudness compensation of the overdrive / distortion presets (v2 step D6).

The overdrive and the distortion change the loudness of the guitar (the clipped signal is much
denser than the clean one). OD_LEVEL (0x2D) and DIST_LEVEL (0x2E) are signed output levels in Q8 log2
units (1 unit = 1/256 of a factor 2 = 0.02352 dB, the unit of the dynamics thresholds) applied to the
wet path of the effect (sim/cocotb/golden.py, fpga/rtl/level_gain.vhd). This tool proposes the values
that make every factory preset of tools/gme_hps.py that uses the OD and/or the distortion as loud as
the clean signal.

Method
  * input: sim/audio/the_lick_e_minor.wav (any WAV: --wav), mixed to mono, resampled to 48 kHz (FFT),
    scaled to 24-bit samples (--peak-dbfs sets the peak, default: the recording as it is, which is a
    realistic pickup level; the distortion curves are level dependent, so look at --peak-dbfs too).
  * the preset's OD and distortion run on it with the bit-exact Python models of the RTL (golden.py
    overdrive / distortion at 24 bit; the OD first, then the distortion, as in FX_chain). The other
    effects of a preset (echo, reverb, ...) are not modelled: they are time effects that do not change
    the level of a sustained signal in a way a static compensation could fix.
  * loudness: RMS of the signal in the 100 Hz .. 5 kHz band (ideal band-pass via the FFT of the whole
    clip, Parseval), in dB re full scale. The band removes the DC / rumble and the fizz above 5 kHz that
    a distortion adds and that a guitar speaker does not reproduce, so it is closer to what is heard
    than the plain RMS. Alternative: --weighting a (IEC A-weighting curve instead of the band); both
    numbers are printed in the table whatever is used for the search.
  * search: the OD level first (the output of the OD must be as loud as the input), then the distortion
    level (the output of the distortion must be as loud as the input; the dry part of the mix is not
    scaled by the level, so the gain needed is found by a search over all integer levels, not by a
    formula). Result: the integer level with the smallest |difference|; "ok" when within +-1 dB.

Usage
    python tools/level_presets.py                    # table for the factory presets
    python tools/level_presets.py --peak-dbfs -12    # input peaking at -12 dBFS
    python tools/level_presets.py --weighting a
    python tools/level_presets.py --selftest

Needs numpy. The factory presets and the new levels are in tools/gme_hps.py (PRESETS).
"""
import argparse
import math
import os
import sys
import wave

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "sim", "cocotb"))
sys.path.insert(0, HERE)
import golden                                                   # noqa: E402
import gme_hps                                                  # noqa: E402

FS = 48000
BAND = (100.0, 5000.0)
IP = os.path.join(ROOT, "fpga", "ip")
CURVES = ("soft", "medium", "hard")                              # dist_type 0, 1, 2 (3 = soft)
OD_BIT, DIST_BIT = 1, 8
LEVEL_RANGE = range(golden.LEVEL_MIN, golden.LEVEL_MAX + 1)
Q8_PER_DB = 256 / 6.0206


def load_wav(path, peak_dbfs=None):
    """WAV -> mono, 48 kHz, 24-bit integer samples (int64 array)."""
    with wave.open(path) as w:
        n, ch, width, rate = w.getnframes(), w.getnchannels(), w.getsampwidth(), w.getframerate()
        raw = w.readframes(n)
    if width == 2:
        x = np.frombuffer(raw, dtype="<i2").astype(np.float64) * 256
    elif width == 3:
        b = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3).astype(np.int64)
        x = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
        x = np.where(x >= 1 << 23, x - (1 << 24), x).astype(np.float64)
    else:
        raise SystemExit("only 16 / 24-bit WAV files")
    x = x.reshape(-1, ch).mean(axis=1)
    if rate != FS:                                                # band-limited resampling by FFT
        m = int(round(len(x) * FS / rate))
        x = np.fft.irfft(np.fft.rfft(x), m) * (m / len(x))
    if peak_dbfs is not None:
        x = x * (2 ** 23 * 10 ** (peak_dbfs / 20) / np.abs(x).max())
    return np.clip(np.round(x), -(1 << 23), (1 << 23) - 1).astype(np.int64)


def a_weight(f):
    """IEC 61672 A-weighting, linear magnitude (0 dB at 1 kHz)."""
    f2 = np.asarray(f, dtype=np.float64) ** 2
    ra = (12194.0 ** 2 * f2 ** 2) / ((f2 + 20.6 ** 2) * np.sqrt((f2 + 107.7 ** 2) * (f2 + 737.9 ** 2))
                                      * (f2 + 12194.0 ** 2))
    return ra * 10 ** (2.0 / 20)


def loudness_db(x, weighting="band"):
    """RMS in dB re full scale (2^23) of the 100 Hz .. 5 kHz band, or A-weighted (Parseval on the whole clip)."""
    x = np.asarray(x, dtype=np.float64)
    spec = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1.0 / FS)
    if weighting == "band":
        w = ((f >= BAND[0]) & (f <= BAND[1])).astype(np.float64)
    else:
        w = a_weight(np.maximum(f, 1e-9))
    p = (np.abs(spec) ** 2 * w ** 2)
    p[1:] *= 2                                                    # one-sided spectrum: both halves
    if len(x) % 2 == 0:
        p[-1] /= 2
    rms = math.sqrt(p.sum() / len(x) ** 2)
    return 20 * math.log10(max(rms, 1e-9) / 2 ** 23)


_CURVES = {}


def curve(t):
    name = CURVES[(t & 3) if (t & 3) < 3 else 0]                 # dist_type 3 = soft (distortion.vhd)
    if name not in _CURVES:
        _CURVES[name] = golden.load_mif(os.path.join(IP, "distortion_%s.mif" % name))
    return _CURVES[name]


def np_apply_level(v, level):
    """golden.apply_level on a numpy int64 array (the products stay below 2^63 at 24 bit)."""
    mant, sh = golden.level_gain(level)
    return (v * mant) >> sh


def np_overdrive(x, drive, gain, level):
    """golden.overdrive (dw = 24) vectorised; x: int64 array. Checked against golden.py (selftest, check_models)."""
    t = drive << 8
    out = np_apply_level(np.clip(x, -t, t) * gain, level)
    return np.clip(out, -(1 << 23), (1 << 23) - 1)


def np_distortion(x, tab, mix, level):
    """golden.distortion (dw = 24) vectorised."""
    a = np.minimum(np.abs(x) >> 8, 16383)
    m = np.minimum(np_apply_level(np.asarray(tab, dtype=np.int64)[a] << 8, level), (1 << 23) - 1)
    wet = np.where(x < 0, -m, m)
    return (mix * wet + (255 - mix) * x) >> 8


def run_od(x, p, level):
    if not p.get("effects_enable", 0) & OD_BIT:
        return x
    return np_overdrive(x, p.get("od_drive", 0), p.get("od_gain", 0), level)


def run_dist(x, p, level):
    if not p.get("effects_enable", 0) & DIST_BIT:
        return x
    return np_distortion(x, curve(p.get("dist_type", 0)), p.get("dist_mix", 0) & 0xFF, level)


def check_models(x, n=20000):
    """The vectorised models equal the bit-exact golden.py models (first n samples, a few levels and presets)."""
    xs = [int(v) for v in x[:n]]
    xa = np.asarray(xs, dtype=np.int64)
    for lv in (-1024, -600, -1, 0, 1, 255, 300, 512):
        for drive, gain in ((3000, 4), (65535, 3), (500, 1)):
            assert list(np_overdrive(xa, drive, gain, lv)) == golden.overdrive(xs, drive, gain, dw=24, level=lv)
        for t in range(3):
            for mix in (255, 160, 7):
                assert list(np_distortion(xa, curve(t), mix, lv)) == golden.distortion(xs, curve(t), mix, dw=24, level=lv)


def search(fn, target_db, weighting, coarse=16):
    """Integer level in -1024 .. +512 whose loudness fn(level) is closest to target_db (coarse grid, then refine;
    the loudness is monotonic in the level, saturation only flattens it at the top)."""
    cand = list(LEVEL_RANGE)[::coarse]
    best = min(cand, key=lambda lv: abs(loudness_db(fn(lv), weighting) - target_db))
    lo, hi = max(golden.LEVEL_MIN, best - coarse), min(golden.LEVEL_MAX, best + coarse)
    best = min(range(lo, hi + 1), key=lambda lv: abs(loudness_db(fn(lv), weighting) - target_db))
    return best


def compensate(x, p, weighting="band"):
    """(od_level, dist_level) for preset dict p on input x."""
    target = loudness_db(x, weighting)
    od_lv = dist_lv = 0
    if p.get("effects_enable", 0) & OD_BIT:
        od_lv = search(lambda lv: run_od(x, p, lv), target, weighting)
    y = run_od(x, p, od_lv)
    if p.get("effects_enable", 0) & DIST_BIT:
        dist_lv = search(lambda lv: run_dist(y, p, lv), target, weighting)
    return od_lv, dist_lv


def analyse(x, name, p, weighting="band"):
    """Table row for one preset: dict with the levels and the loudness in dB before / after."""
    uses = [n for n, b in (("OD", OD_BIT), ("DIST", DIST_BIT)) if p.get("effects_enable", 0) & b]
    clean_b, clean_a = loudness_db(x, "band"), loudness_db(x, "a")
    od_lv, dist_lv = compensate(x, p, weighting)
    y0 = run_dist(run_od(x, p, 0), p, 0)
    y1 = run_dist(run_od(x, p, od_lv), p, dist_lv)
    row = dict(name=name, uses="+".join(uses), od_level=od_lv, dist_level=dist_lv,
               clean_band=clean_b, before_band=loudness_db(y0, "band"), after_band=loudness_db(y1, "band"),
               clean_a=clean_a, before_a=loudness_db(y0, "a"), after_a=loudness_db(y1, "a"),
               peak=20 * math.log10(max(int(np.abs(y1).max()), 1) / 2 ** 23))
    return row


def print_table(rows, weighting):
    print("loudness re full scale (dB): band = RMS 100 Hz .. 5 kHz, A = A-weighted; search on '%s'" % weighting)
    print("%-12s %-8s | %9s %9s %9s | %7s %7s | %7s %8s %7s %7s | %s" % (
        "preset", "uses", "clean", "no level", "levelled", "diff", "diff A", "OD_LVL", "OD dB", "DIST_LVL", "dB", "within 1 dB"))
    for r in rows:
        d, da = r["after_band"] - r["clean_band"], r["after_a"] - r["clean_a"]
        print("%-12s %-8s | %9.2f %9.2f %9.2f | %+7.2f %+7.2f | %7d %+7.2f %8d %+7.2f | %s" % (
            r["name"], r["uses"], r["clean_band"], r["before_band"], r["after_band"], d, da,
            r["od_level"], r["od_level"] / Q8_PER_DB, r["dist_level"], r["dist_level"] / Q8_PER_DB,
            "ok" if abs(d if weighting == "band" else da) <= 1.0 else "NO (range / saturation)"))


def selftest():
    # a 1 kHz sine of known RMS: the band loudness is its RMS
    n = FS
    x = np.array([round(2 ** 20 * math.sin(2 * math.pi * 1000 * i / FS)) for i in range(n)], dtype=np.int64)
    check_models(x)
    assert abs(loudness_db(x) - (20 * math.log10(2 ** 20 / math.sqrt(2) / 2 ** 23))) < 0.01
    assert abs(loudness_db(x, "a") - loudness_db(x)) < 0.05                       # A-weighting is 0 dB at 1 kHz
    # 8 kHz is outside the band
    x8 = np.array([round(2 ** 22 * math.sin(2 * math.pi * 8000 * i / FS)) for i in range(n)], dtype=np.int64)
    assert loudness_db(x8) < -100
    # level search: on a pure OD (no clipping, gain 2) the level is exactly -1 octave = -256
    p = dict(effects_enable=OD_BIT, od_drive=65535, od_gain=2)
    assert compensate(x, p)[0] == -256
    # level 0 is the old behaviour
    assert list(run_od(x[:50], p, 0)) == [2 * int(v) for v in x[:50]]
    print("selftest OK")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--wav", default=os.path.join(ROOT, "sim", "audio", "the_lick_e_minor.wav"))
    ap.add_argument("--peak-dbfs", type=float, default=None, help="scale the input to this peak (default: as recorded)")
    ap.add_argument("--weighting", choices=["band", "a"], default="band")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    x = load_wav(a.wav, a.peak_dbfs)
    print("input %s: %d samples at 48 kHz, peak %.1f dBFS" % (os.path.basename(a.wav), len(x),
                                                              20 * math.log10(np.abs(x).max() / 2 ** 23)))
    check_models(x)
    rows = []
    for name, p in gme_hps.PRESETS.items():
        if p.get("effects_enable", 0) & (OD_BIT | DIST_BIT):
            rows.append(analyse(x, name, p, a.weighting))
    # no factory preset uses the overdrive: a typical setting as a reference row
    rows.append(analyse(x, "(od example)", dict(effects_enable=OD_BIT, od_drive=3000, od_gain=4), a.weighting))
    print_table(rows, a.weighting)
    print("\nPRESETS entries (tools/gme_hps.py) for the factory presets:")
    for r in rows:
        if r["name"] in gme_hps.PRESETS:
            extra = ", ".join("%s=%d" % (k, r[k]) for k in ("od_level", "dist_level") if r[k])
            print("  %-10s %s" % (r["name"], extra))


if __name__ == "__main__":
    sys.exit(main())
