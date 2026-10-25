"""
cabfir_model.py - bit-exact Python model of cab_fir.vhd (v2 step D3).

    y[n] = sat( floor( sum_k h_bank[k] * x[n-k] / 2^(17+shift) ), DW )

step() takes the sample x[n] (and bank / shift as sampled at the start strobe)
and returns y[n]. The RTL presents y[n] on data_out at the NEXT start strobe
(one sample latency), so data_out right after start n+1 equals step(n).
Coefficients: two banks of `taps` signed 18-bit values; `init` is the content
of the power-up .mif (bank 0 = words 0..taps-1, bank 1 = the following words,
exactly like the RAM: a mif of 2048 words for TAPS = 2048 leaves bank 1 at 0).
"""
import numpy as np

COEF_BITS = 18


def sat(v, w):
    return max(-(1 << (w - 1)), min((1 << (w - 1)) - 1, v))


class CabFir:
    def __init__(self, dw=24, taps=2048, init=None):
        self.dw, self.taps = dw, taps
        init = list(init or [])
        self.bank = [np.zeros(taps, dtype=np.int64), np.zeros(taps, dtype=np.int64)]
        for b in (0, 1):
            w = init[b * taps:(b + 1) * taps]
            self.bank[b][:len(w)] = w
        self.x = np.zeros(taps, dtype=np.int64)          # x[n-k] at index k (newest first)

    def write(self, bank, addr, value):
        assert -(1 << 17) <= value < (1 << 17)
        self.bank[bank][addr] = value

    def step(self, x, bank=0, shift=0):
        self.x = np.roll(self.x, 1)
        self.x[0] = x
        acc = int(np.dot(self.bank[bank], self.x))       # exact: < 2^(dw+17+log2 taps) fits int64
        return sat(acc >> (17 + shift), self.dw)         # >> is floor for negative ints
