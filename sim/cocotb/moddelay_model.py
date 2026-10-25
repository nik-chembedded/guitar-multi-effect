"""
moddelay_model.py - bit-exact Python model of mod_delay.vhd (v2 step D2).
One call of step() per sample (the block's strobe).
"""
import lfo_model as m

AW = 11
N = 1 << AW
DMAX = N - 2


def sat(v, w):
    return max(-(1 << (w - 1)), min((1 << (w - 1)) - 1, v))


def delay_q8(base, depth, lfo):
    b, dp = min(base, DMAX), min(depth, DMAX)
    d = b * 256 + ((dp * (lfo - 32768)) >> 7)
    return max(256, min(DMAX * 256, d))


class ModDelay:
    def __init__(self, dw=16):
        self.dw = dw
        self.line = [0] * N
        self.wp = 0
        self.wet = 0
        self.phase = 0

    def step(self, x, enable=1, mix=128, depth=0, rate=0, base=1, fb=0, shape=0):
        """Returns this sample's output (before the output register)."""
        fb = fb - 65536 if fb >= 32768 else fb
        if enable:
            y = (mix * self.wet + (255 - mix) * x) >> 8
        else:
            y = x
        lfo = m.wave(self.phase, shape & 1)
        self.phase = (self.phase + m.inc(rate)) & 0xFFFFFFFF
        wp_s = self.wp
        if enable:
            self.line[wp_s] = sat(x + ((self.wet * fb) >> 15), self.dw)
            self.wp = (self.wp + 1) % N
        d = delay_q8(base, depth, lfo)
        di, fr = d >> 8, d & 0xFF
        a = self.line[(wp_s - di + 1) % N]
        b = self.line[(wp_s - di) % N]
        self.wet = a + (((b - a) * fr) >> 8)
        return y
