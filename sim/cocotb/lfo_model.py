"""
lfo_model.py - bit-exact Python model of nco_lfo.vhd (v2 step D1) and of the
tremolo built on it (tremolo_v2.vhd).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "tools"))
from gen_lfo_table import SINE_Q  # noqa: E402

K = 916260
SINE, TRIANGLE, SAW, SQUARE = 0, 1, 2, 3
# trem_wave 0..7 (bit 3 = 0): legacy presets -> (shape, rate in 0.01 Hz)
LEGACY = [(SINE, 500), (SINE, 700), (SINE, 1000), (SINE, 1200), (SINE, 1500),
          (TRIANGLE, 500), (TRIANGLE, 1000), (SAW, 1000)]


def inc(rate):
    return ((rate * K) >> 10) & 0xFFFFFFFF


SAW_B, SAW_K1, SAW_K2 = 62259, 68984, 1310620


def saw16(p):
    """rise over 95 % of the period, ramp down over the last 5 % (like the v1 table)"""
    u = p >> 16
    v = (u * SAW_K1) >> 16 if u < SAW_B else ((65535 - u) * SAW_K2) >> 16
    return min(v, 65535)


def sine16(p):
    idx, fr = (p >> 22) & 0xFF, (p >> 14) & 0xFF
    if (p >> 30) & 1 == 0:
        j, f = idx, fr
    else:
        j, f = 255 - idx, 256 - fr
    v = SINE_Q[j] + ((SINE_Q[j + 1] - SINE_Q[j]) * f) // 256
    return 32768 + v if (p >> 31) == 0 else 32768 - v


def wave(p, shape):
    top = (p >> 15) & 0xFFFF
    if shape == SINE:
        return sine16(p)
    if shape == TRIANGLE:
        return top if (p >> 31) == 0 else (~top) & 0xFFFF
    if shape == SAW:
        return saw16(p)
    return 0xFFFF if (p >> 31) == 0 else 0


def decode(trem_wave, trem_rate):
    """tremolo_v2 waveform register -> (shape, rate)."""
    if trem_wave & 8:
        return trem_wave & 3, trem_rate
    return LEGACY[trem_wave & 7]


def frequency(rate):
    """Exact LFO frequency in Hz for a rate setting."""
    return inc(rate) * 48000 / 2 ** 32
