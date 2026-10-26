"""
eq3_model.py - bit-exact Python model of eq3.vhd / biquad.vhd (v2 step D5b).

Three Direct Form I biquad sections in series, Q2.16 coefficients, error feedback:
    acc = ((b0 x + b1 x1 + b2 x2) << sh) - a1 y1 - a2 y2 + e
    y   = sat(acc >> 16, DW)        (floor)
    e   = acc & 0xFFFF
Use: write() / apply() as the coefficient port, one step() call per sample (strobe).
The new coefficient set is taken over at the next step() after apply(), exactly like the
block copies shadow -> active at the strobe.
"""

NSEC = 3
UNITY = 65536


def sat(v, w):
    return max(-(1 << (w - 1)), min((1 << (w - 1)) - 1, v))


def s18(v):
    v &= 0x3FFFF
    return v - (1 << 18) if v >= 1 << 17 else v


class Section(object):
    def __init__(self, dw):
        self.dw = dw
        self.x1 = self.x2 = self.y1 = self.y2 = 0
        self.e = 0

    def step(self, x, c, sh):
        b0, b1, b2, a1, a2 = c
        acc = ((b0 * x + b1 * self.x1 + b2 * self.x2) << sh) - a1 * self.y1 - a2 * self.y2 + self.e
        y = sat(acc >> 16, self.dw)
        self.e = acc & 0xFFFF
        self.x2, self.x1 = self.x1, x
        self.y2, self.y1 = self.y1, y
        return y


class EQ3(object):
    def __init__(self, dw=24):
        self.dw = dw
        self.sec = [Section(dw) for _ in range(NSEC)]
        self.shadow = [UNITY if i % 5 == 0 else 0 for i in range(15)]
        self.active = list(self.shadow)
        self.sc_shadow = 0
        self.sc_active = 0
        self.pend = False

    def write(self, addr, data):
        """Coefficient port: addr 0..14 (signed 18 bit data, may be given signed or as a word),
        addr 15 = scale register (2 bits per section)."""
        if addr < 15:
            self.shadow[addr] = s18(data)
        else:
            self.sc_shadow = data & 0x3F

    def write_set(self, ints, scale=0):
        for i, v in enumerate(ints):
            self.write(i, v)
        self.write(15, scale)

    def apply(self):
        self.pend = True

    def step(self, x, enable=1):
        """One sample. Returns the value data_out holds after this sample."""
        if self.pend:
            self.active = list(self.shadow)
            self.sc_active = self.sc_shadow
            self.pend = False
        y = x
        for s in range(NSEC):
            y = self.sec[s].step(y, self.active[5 * s:5 * s + 5], (self.sc_active >> (2 * s)) & 3)
        return y if enable else x
