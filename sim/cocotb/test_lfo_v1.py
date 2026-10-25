"""
test_lfo_v1.py - the generated LFO (v2 step D1) against the 8 v1 LFO tables
(v1_lfo_tables/, the former ROM contents), without simulation.

For every legacy waveform code 0..7: the v1 table holds one period of N samples
(8-bit, 0..254). The new LFO (lfo_model, bit-exact to nco_lfo.vhd) must have
  * the same period: 48000 / f within 1 sample of N,
  * the same shape: after the best circular phase alignment, every sample within
    2 % of full scale of the v1 table (the v1 tables have 8-bit steps of 0.4 %).
Run by pytest (test_runner.test_lfo_vs_v1).
"""
from pathlib import Path

import numpy as np

import golden
import lfo_model as m

MIF = Path(__file__).resolve().parent / "v1_lfo_tables"
TABLES = ["sine_5hz_8bit", "sine_7hz_8bit", "my_sin", "sine_12hz_8bit", "sine_15hz_8bit",
          "triangle_5hz_8bit", "triangle_10hz_8bit", "sawtooth_10hz_8bit"]
DEPTH = {"sine_5hz_8bit": 9600, "sine_7hz_8bit": 6857, "my_sin": 4800, "sine_12hz_8bit": 4000,
         "sine_15hz_8bit": 3200, "triangle_5hz_8bit": 9600, "triangle_10hz_8bit": 4800,
         "sawtooth_10hz_8bit": 4800}           # entries used by the v1 counters
TOL = 0.02


def compare(code):
    name = TABLES[code]
    t = np.array(golden.load_mif(MIF / (name + ".mif"))[:DEPTH[name]], dtype=float) / 254.0
    shape, rate = m.decode(code, 0)
    n = len(t)
    period = 48000 / m.frequency(rate)
    phase = 0
    w = np.empty(n)
    for i in range(n):
        w[i] = m.wave(phase, shape) / 65535.0
        phase = (phase + m.inc(rate)) & 0xFFFFFFFF
    # best circular alignment (FFT cross-correlation), then the max difference there
    xc = np.fft.irfft(np.fft.rfft(t - t.mean()) * np.conj(np.fft.rfft(w - w.mean())), n)
    s = int(np.argmax(xc))
    diff = np.abs(np.roll(w, s) - t)
    return name, n, period, float(diff.max()), float(diff.mean())


def check_all(log=print):
    rows = [compare(c) for c in range(8)]
    for name, n, period, mx, mean in rows:
        log("%-20s v1 period %5d, new %8.2f samples; max diff %.4f, mean %.4f" % (name, n, period, mx, mean))
        assert abs(period - n) <= 1.0, "%s: period %.2f vs %d" % (name, period, n)
        assert mx < TOL, "%s: shape differs by %.4f" % (name, mx)
    return rows


if __name__ == "__main__":
    check_all()
