#!/usr/bin/env python3
"""
dist_aliasing.py - aliasing of the distortion and what 2x oversampling would give (v2 step D6, data only).

The distortion is a memoryless waveshaper (sim/cocotb/golden.distortion: |x| >> 8 -> 14-bit table, sign
restored, mix) running at 48 kHz, so every harmonic above 24 kHz folds back into the audio band. This tool
measures it with the bit-exact Python model and simulates 2x oversampling (half-band interpolator, the same
table at 96 kHz, half-band decimator). Nothing here is implemented in the FPGA.

Measurement
  * input: a sine with an exactly coherent frequency (2 s = 96000 samples, so 1 / 1.1 / 2.5 / 5 kHz all fall on
    FFT bins), amplitude -3 dBFS (drives the table end, i.e. the curve is clipped hard) and -12 dBFS;
    mix 255 (wet only), curves soft / medium / hard.
  * spectrum: 4-term Blackman-Harris window, 96000-point FFT.
  * "aliased component" = the strongest spectral line that is NOT a baseband harmonic of the input, level in dB
    re the fundamental. Two ways, both printed:
      - inharmonic: the strongest line at a frequency that is not a multiple of f0 (+-3 bins). At 1 kHz every
        alias lands exactly on a harmonic bin (48 kHz / 1 kHz is an integer), so there is no inharmonic line;
        1.1 kHz shows what 1 kHz hides.
      - error: the strongest line of  y - y_ideal  where y_ideal is the same waveshaper evaluated at 8x the rate
        and band-limited to 24 kHz (brick wall in the FFT domain: exactly the harmonics below 24 kHz). It also
        catches aliases that land on harmonic bins, and (for the 2x variants) the part of the baseband harmonics
        that the decimation filter removes near 24 kHz.
  * 2x: zero-stuff, half-band lowpass (Kaiser window, 23 or 31 taps, gain 2), shaper at 96 kHz (the same
    14-bit table, address |x| >> 8 of the interpolated sample), half-band lowpass, keep every second sample.
    Exact integer arithmetic is not modelled (floating-point filters, output rounded to 24 bit).

Usage:  python tools/dist_aliasing.py
"""
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "sim", "cocotb"))
import golden                                                   # noqa: E402

FS = 48000
N = 96000
CURVES = ("soft", "medium", "hard")
FILTERS = {"23": (23, 7.0), "31": (31, 8.0)}                     # taps, Kaiser beta


def shaper(x, tab, mix=255):
    """golden.distortion (dw = 24) on an int64 array (the sample rate does not matter: memoryless)."""
    a = np.minimum(np.abs(x) >> 8, 16383)
    m = np.asarray(tab, dtype=np.int64)[a] << 8
    wet = np.where(x < 0, -m, m)
    return (mix * wet + (255 - mix) * x) >> 8


def halfband(taps, beta):
    """Kaiser-window half-band lowpass (cut-off fs/4, DC gain 1); every second tap besides the centre is 0."""
    n = np.arange(taps) - (taps - 1) // 2
    h = 0.5 * np.sinc(n / 2.0) * np.kaiser(taps, beta)
    h[np.abs(n) % 2 == 0] = 0.0
    h[(taps - 1) // 2] = 0.5
    return h / h.sum()


def os2(x, tab, taps, beta):
    """2x oversampled distortion of the int array x: interpolate, shape at 96 kHz, decimate."""
    h = halfband(taps, beta)
    up = np.zeros(2 * len(x))
    up[::2] = x
    xi = np.round(np.convolve(up, 2 * h, mode="full")[(taps - 1) // 2:(taps - 1) // 2 + 2 * len(x)]).astype(np.int64)
    xi = np.clip(xi, -(1 << 23), (1 << 23) - 1)
    ys = shaper(xi, tab).astype(np.float64)
    lp = np.convolve(ys, h, mode="full")[(taps - 1) // 2:(taps - 1) // 2 + 2 * len(x)]
    return np.round(lp[::2]).astype(np.int64)


def ideal(f0, amp, tab, n=N):
    """The waveshaper at 8x the rate, band-limited to 24 kHz and decimated by an exact FFT-domain cut."""
    k = 8
    t = np.arange(n * k)
    x8 = np.round(amp * np.sin(2 * np.pi * f0 * t / (FS * k))).astype(np.int64)
    y8 = shaper(x8, tab).astype(np.float64)
    spec = np.fft.rfft(y8)[:n // 2 + 1]
    spec[-1] = 0.0                                               # (exactly 24 kHz: not representable)
    return np.fft.irfft(spec, n) / k


def spectrum_db(y, ref_bin):
    w = np.array([0.35875, 0.48829, 0.14128, 0.01168])
    i = np.arange(len(y))
    win = sum((-1) ** m * w[m] * np.cos(2 * np.pi * m * i / (len(y) - 1)) for m in range(4))
    s = np.abs(np.fft.rfft(y * win))
    return s, s[ref_bin]


def analyse(y, y_ref, f0):
    """(inharmonic dB or None, error dB) of the signal y re its fundamental."""
    b0 = int(round(f0 * N / FS))                                 # fundamental bin
    s, _ = spectrum_db(y - y.mean(), b0)
    fund = s[b0 - 2:b0 + 3].max()
    harm = np.zeros(len(s), dtype=bool)
    for m in range(0, int(24000 // f0) + 1):
        c = m * b0
        harm[max(c - 3, 0):c + 4] = True
    s[harm] = 0
    s[:3] = 0
    integer_ratio = abs(FS / f0 - round(FS / f0)) < 1e-9         # every alias then lands on a harmonic bin
    inh = None if integer_ratio else 20 * np.log10(max(s.max(), 1e-9) / fund)
    e, _ = spectrum_db(y - y_ref, b0)
    e[:3] = 0
    return inh, 20 * np.log10(max(e.max(), 1e-9) / fund)


def main():
    print("aliasing of the distortion at 48 kHz and with 2x oversampling (half-band Kaiser, 23 / 31 taps)")
    print("dB re the fundamental; 'inharm' = strongest line not on a harmonic bin, 'error' = strongest line of y - ideal\n")
    for amp_db in (-3.0, -12.0):
        amp = 2 ** 23 * 10 ** (amp_db / 20)
        print("sine amplitude %.0f dBFS, mix 255" % amp_db)
        print("%-7s %-7s | %-18s | %-18s | %-18s" % ("f0", "curve", "current (48 kHz)", "2x, 23 taps", "2x, 31 taps"))
        print("%-7s %-7s | %8s %9s | %8s %9s | %8s %9s" % ("", "", "inharm", "error", "inharm", "error", "inharm", "error"))
        for f0 in (1000.0, 1100.0, 2500.0, 5000.0):
            n = np.arange(N)
            x = np.round(amp * np.sin(2 * np.pi * f0 * n / FS)).astype(np.int64)
            for c in CURVES:
                tab = golden.load_mif(os.path.join(ROOT, "fpga", "ip", "distortion_%s.mif" % c))
                yref = ideal(f0, amp, tab)
                cols = []
                for name, y in (("cur", shaper(x, tab)), ("23", os2(x, tab, *FILTERS["23"])), ("31", os2(x, tab, *FILTERS["31"]))):
                    inh, err = analyse(y.astype(np.float64), yref, f0)
                    cols.append("%8s %9.1f" % ("n/a" if inh is None else "%.1f" % inh, err))
                print("%-7s %-7s | %s | %s | %s" % ("%g k" % (f0 / 1000), c, *cols))
        print("")
    # filter facts
    for name, (taps, beta) in FILTERS.items():
        h = halfband(taps, beta)
        w = np.linspace(0, np.pi, 4096)
        resp = np.abs(np.exp(-1j * np.outer(w, np.arange(taps))) @ h)
        f = w / np.pi * 48000                                    # (the filter runs at 96 kHz)
        def at(hz):
            return 20 * np.log10(resp[np.argmin(np.abs(f - hz))])
        print("half-band %s taps (beta %.1f): %d non-zero taps, %d distinct multipliers (the centre tap is 1/2); response "
              "%.2f dB @ 20 kHz, %.1f @ 24, %.1f @ 28, %.1f @ 32, %.1f @ 36 kHz, %.1f dB @ >= 40 kHz (worst)" % (
                  name, beta, int(np.count_nonzero(h)), int(np.count_nonzero(h[(taps - 1) // 2 + 1:])),
                  at(20000), at(24000), at(28000), at(32000), at(36000), 20 * np.log10(resp[f >= 40000].max())))


if __name__ == "__main__":
    sys.exit(main())
