"""
reverbfv_model.py - bit-exact Python model of reverb_fv.vhd (v2 step D4, Freeverb).
One call of step() per sample (the block's en_rise strobe).

Structure (see fpga/rtl/reverb_fv.vhd):
  y   = x (enable = 0, or mix = 0)  |  mix8(x, wet, mix)         (uses the wet value of the
                                                                   PREVIOUS post-step)
  write: comb_i[n]  = sat((x >> IN_SHIFT) + fbv_i);  allp_j[n] = apw_j;  n += 1
  post-step (RTL: clocks 3..8 after the strobe, with this strobe's size / damp):
    out_i   = comb_i[n - L_i]                              (loop delay exactly L_i)
    store_i += ((out_i - store_i) * (256 - d)) >> 8        (floor)
    fbv_i   = trunc_to_zero(store_i * fb / 65536)          fb = min(size, 64225)
    v       = sat(sum out_i)
    allpass j: b = allp_j[n - A_j];  apw_j = sat(v + trunc(b / 2));  v = sat(b - v)
    wet     = v
"""

COMB_LEN = (1215, 1293, 1390, 1476, 1548, 1623, 1695, 1760)
AP_LEN = (605, 480, 371, 245)
NC, NA = 2048, 1024
FB_MAX = 64225          # 0.98 * 65536
IN_SHIFT = 7            # input gain 1/128 (reverb_fv generic IN_SHIFT)
WET_SHIFT = 2           # wet gain 4 (reverb_fv generic WET_SHIFT)


def sat(v, w):
    return max(-(1 << (w - 1)), min((1 << (w - 1)) - 1, v))


def trunc_shr(v, s):
    """v / 2^s truncated toward zero (fx_pkg div_pow2)."""
    return -((-v) >> s) if v < 0 else v >> s


def mix8(dry, wet, m):
    return (m * wet + (255 - m) * dry) >> 8


class ReverbFV:
    def __init__(self, dw=16, wet_shift=WET_SHIFT):
        self.dw = dw
        self.ws = wet_shift
        self.comb = [[0] * NC for _ in COMB_LEN]
        self.ap = [[0] * NA for _ in AP_LEN]
        self.n = 0
        self.store = [0] * 8
        self.fbv = [0] * 8
        self.apw = [0] * 4
        self.wet = 0

    def step(self, x, enable=1, size=0, damp=0, mix=255):
        """x: signed sample. Returns this sample's output."""
        m = mix & 255
        if not enable:
            return x
        y = x if m == 0 else mix8(x, sat(self.wet << self.ws, self.dw), m)
        dw = self.dw
        xg = x >> IN_SHIFT
        for i in range(8):
            self.comb[i][self.n % NC] = sat(xg + self.fbv[i], dw)
        for j in range(4):
            self.ap[j][self.n % NA] = self.apw[j]
        self.n = (self.n + 1) % NC
        # post-step
        fb = min(size & 0xFFFF, FB_MAX)
        d = damp & 255
        outs = [self.comb[i][(self.n - COMB_LEN[i]) % NC] for i in range(8)]
        for i in range(8):
            self.store[i] += ((outs[i] - self.store[i]) * (256 - d)) >> 8
            self.fbv[i] = trunc_shr(self.store[i] * fb, 16)
        v = sat(sum(outs), dw)
        for j in range(4):
            b = self.ap[j][(self.n - AP_LEN[j]) % NA]
            self.apw[j] = sat(v + trunc_shr(b, 1), dw)
            v = sat(b - v, dw)
        self.wet = v
        return y
