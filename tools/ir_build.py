#!/usr/bin/env python3
"""
ir_build.py - build the cabinet coefficient sets from ir/manifest.json
(v2 step D3).

For every cabinet: read the WAV (checks its sha256), resample to 48 kHz, trim to
2048 taps with a fade-out, normalise to equal loudness (pink-weighted guitar
band) and quantise to signed 18-bit (Q1.17). Output in ir/build/ (not in git):

  cabNN.bin          2048 x int32 little endian (the 18-bit coefficients), for the FPGA
  cabNN.txt          the same, one decimal per line
  demo_NN_<name>.wav guitar lick through a simple distortion and the cabinet
  demo_dry.wav       the same without a cabinet
  responses.svg      frequency responses of all cabinets
  report.txt         loudness, peak coefficient, worst-case gain per cabinet

    source ~/venvs/gme/bin/activate && python3 tools/ir_build.py
"""
import hashlib
import json
import math
import os
import re
import sys

import numpy as np

import cabir

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
MANIFEST = os.path.join(ROOT, "ir", "manifest.json")
OUT = os.path.join(ROOT, "ir", "build")
DEMO_SRC = os.path.join(ROOT, "sim", "audio", "the_lick_e_minor.wav")
COLORS = ["#222222", "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
          "#8c564b", "#e377c2", "#7f7f7f", "#17becf"]


def slug(s):
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def build_one(c):
    path = os.path.join(ROOT, c["file"])
    if not os.path.exists(path):
        raise SystemExit("cabinet %d: %s missing (source: %s)" % (c["slot"], c["file"], c["source"]))
    digest = hashlib.sha256(open(path, "rb").read()).hexdigest()
    if digest != c["sha256"]:
        raise SystemExit("cabinet %d: %s has a different checksum" % (c["slot"], c["file"]))
    x, sr = cabir.read_wav(path)
    h = cabir.normalise(cabir.trim(cabir.resample(x, sr)))
    q = cabir.quantise(h)
    hq = q / float(1 << (cabir.COEF_BITS - 1))
    return h, q, hq, sr, len(x)


def distort(x):
    x = x / np.max(np.abs(x))
    return np.tanh(6.0 * x) / math.tanh(6.0)


def svg_plot(curves, path):
    """curves: [(label, freqs, dB)] -> simple log-frequency SVG plot."""
    W, H, L, T, R, B = 900, 460, 60, 20, 210, 40
    fmin, fmax, dbmin, dbmax = 20.0, 20000.0, -42.0, 12.0
    X = lambda f: L + (math.log10(f) - math.log10(fmin)) / (math.log10(fmax) - math.log10(fmin)) * (W - L - R)
    Y = lambda d: T + (dbmax - max(dbmin, min(dbmax, d))) / (dbmax - dbmin) * (H - T - B)
    s = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" font-family="sans-serif" font-size="11">' % (W, H),
         '<rect width="100%" height="100%" fill="white"/>']
    for f in (20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000):
        s.append('<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="#ddd"/>' % (X(f), T, X(f), H - B))
        s.append('<text x="%.1f" y="%d" text-anchor="middle">%s</text>' % (X(f), H - B + 15, f if f < 1000 else "%dk" % (f // 1000)))
    for d in range(-42, 13, 6):
        s.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="#ddd"/>' % (L, Y(d), W - R, Y(d)))
        s.append('<text x="%d" y="%.1f" text-anchor="end">%d dB</text>' % (L - 5, Y(d) + 4, d))
    for i, (label, fr, db) in enumerate(curves):
        pts = " ".join("%.1f,%.1f" % (X(f), Y(d)) for f, d in zip(fr, db))
        col = COLORS[i % len(COLORS)]
        s.append('<polyline fill="none" stroke="%s" stroke-width="%s" points="%s"/>' % (col, 2.5 if i == 0 else 1.4, pts))
        s.append('<text x="%d" y="%d" fill="%s">%s</text>' % (W - R + 10, T + 14 + 16 * i, col, label))
    s.append('<text x="%d" y="%d" text-anchor="middle">Cabinet responses after normalisation (dB, 48 kHz)</text>' % ((L + W - R) // 2, 12))
    s.append("</svg>")
    with open(path, "w") as f:
        f.write("\n".join(s))


def main():
    cabs = json.load(open(MANIFEST))["cabinets"]
    os.makedirs(OUT, exist_ok=True)
    lick, sr = cabir.read_wav(DEMO_SRC)
    dry = distort(cabir.resample(lick, sr))
    freqs = np.logspace(math.log10(20), math.log10(20000), 240)
    curves, report, demos = [], [], []
    for c in cabs:
        h, q, hq, sr_in, n_in = build_one(c)
        n = "%02d" % c["slot"]
        q.astype("<i4").tofile(os.path.join(OUT, "cab%s.bin" % n))
        np.savetxt(os.path.join(OUT, "cab%s.txt" % n), q, fmt="%d")
        curves.append(("%d %s" % (c["slot"], c["name"]), freqs, cabir.response_db(hq, freqs)))
        demos.append((c, np.convolve(dry, hq)[:len(dry)]))
        report.append("%d %-22s src %5d smp @ %5d Hz  loudness %.3f  peak coef %6.3f  sum|h| %5.2f  max|H| %+5.1f dB" % (
            c["slot"], c["name"], n_in, sr_in, cabir.loudness(hq), np.max(np.abs(hq)), np.sum(np.abs(hq)),
            np.max(curves[-1][2])))
    peak = max(np.max(np.abs(d)) for _, d in demos)                 # one gain for all demos: loudness comparable
    for c, d in demos:
        cabir.write_wav(os.path.join(OUT, "demo_%02d_%s.wav" % (c["slot"], slug(c["name"]))), d / peak * 0.9, bits=16)
    cabir.write_wav(os.path.join(OUT, "demo_dry.wav"), dry * 0.5, bits=16)
    svg_plot(curves, os.path.join(OUT, "responses.svg"))
    with open(os.path.join(OUT, "report.txt"), "w") as f:
        f.write("\n".join(report) + "\n")
    print("\n".join(report))
    print("-> %s (cabNN.bin/.txt, demo_*.wav, responses.svg)" % os.path.relpath(OUT, ROOT))


if __name__ == "__main__":
    sys.exit(main())
