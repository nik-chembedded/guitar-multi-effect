#!/usr/bin/env python3
"""
make_cab_ir.py - generate our own default cabinet impulse response (cabinet 0,
v2 step D3): a generic guitar speaker in a closed cabinet, built from filters,
so it has no licence restrictions and lives in git (ir/cab00_default.wav).

    source ~/venvs/gme/bin/activate && python3 tools/make_cab_ir.py

Shape (minimum phase, as a real speaker):
  * 2nd-order high-pass   75 Hz      (cabinet low end)
  * resonance             +5 dB  110 Hz, Q 1.2
  * low-mid scoop         -4 dB  400 Hz, Q 1.0   (less "boxy")
  * presence              +4 dB  2.5 kHz, Q 1.2
  * 4th-order low-pass    5 kHz  (Butterworth; speaker cone roll-off, removes fizz)
"""
import os

import numpy as np

import cabir

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
OUT = os.path.join(ROOT, "ir", "cab00_default.wav")

STAGES = [("hpf", 75, 0.707, 0.0), ("peak", 110, 1.2, 5.0), ("peak", 400, 1.0, -4.0),
          ("peak", 2500, 1.2, 4.0), ("lpf", 5000, 0.5412, 0.0), ("lpf", 5000, 1.3066, 0.0)]


def make():
    h = np.zeros(cabir.TAPS)
    h[0] = 1.0
    for kind, f0, q, g in STAGES:
        b, a = cabir.biquad(kind, f0, q, g)
        h = cabir.lfilter(b, a, h)
    h[-cabir.FADE:] *= 0.5 * (1 + np.cos(np.pi * np.arange(1, cabir.FADE + 1) / cabir.FADE))
    return h


def main():
    h = make()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    cabir.write_wav(OUT, h / np.max(np.abs(h)) * 0.9)       # stored at -1 dBFS peak; level set when built
    print("wrote %s (%d samples, 48 kHz, 24-bit)" % (os.path.relpath(OUT, ROOT), len(h)))
    for f in (60, 110, 400, 1000, 2500, 5000, 8000):
        print("  %5d Hz %6.1f dB" % (f, cabir.response_db(h, [f])[0] - cabir.response_db(h, [1000])[0]))


if __name__ == "__main__":
    main()
