"""
dynamics_model.py - bit-exact Python model of dynamics.vhd (v2 step D5a:
noise gate + compressor).  One call of step() per sample (the block's strobe).
See the header of fpga/rtl/dynamics.vhd for the number formats.
"""
import math

# detector / gate constants (same as the VHDL constants)
K_ATT = 2                 # envelope attack  : tau 2^2  = 4 samples
K_REL = 11                # envelope release : tau 2^11 = 2048 samples (43 ms)
FS_LOG = 23 * 256         # log2 of full scale (2^23) in Q8
GATE_FLOOR = 3584         # gate closed = -14 log2 units (-84.3 dB), Q8
GA_MAX = GATE_FLOOR * 256
GATE_CLOSE = 384          # Q16 log2 units per sample: 0 -> floor in 2389 samples (49.8 ms)
GATE_OPEN = 19200         # Q16 log2 units per sample: floor -> 0 in 48 samples (1.0 ms)
GATE_HYST = 128           # Q8: 0.5 log2 unit = 3.01 dB
RED_MAX = 4095            # max compressor reduction, Q8 log2 (95.9 dB)
G_MIN = -4096             # total gain exponent limits, Q8 log2
G_MAX = 1024
GAIN_FRAC = 18            # gain format: unsigned Q5.18

LOG_T = [round(math.log2(1 + i / 32) * 4096) for i in range(33)]   # Q12
EXP_T = [round(2 ** (i / 32) * 4096) for i in range(33)]           # Q12


def sat(v, w):
    return max(-(1 << (w - 1)), min((1 << (w - 1)) - 1, v))


def s16(v):
    v &= 0xFFFF
    return v - 65536 if v >= 32768 else v


def log2q8(e):
    """log2 of a 24-bit integer, Q8 (0 for e = 0 and e = 1); floor, piecewise linear."""
    if e == 0:
        p, nm = 0, 0
    else:
        p = e.bit_length() - 1
        nm = (e << (23 - p)) & 0x7FFFFF
    i, r = nm >> 18, (nm >> 11) & 127
    t = LOG_T[i] + (((LOG_T[i + 1] - LOG_T[i]) * r) >> 7)
    return p * 256 + (t >> 4)


def exp2gain(g):
    """2^(g/256) as unsigned Q.18 (g signed Q8, -4096 .. 1024)."""
    n, fr = g >> 8, g & 255
    i, r = fr >> 3, fr & 7
    mant = EXP_T[i] + (((EXP_T[i + 1] - EXP_T[i]) * r) >> 3)      # Q12, 4096 .. 8191
    sh = n + 6
    return mant << sh if sh >= 0 else mant >> -sh


class Dynamics:
    def __init__(self, dw=24):
        self.dw = dw
        self.env = 0          # Q8 fraction, 32 bit
        self.cs = 0           # compressor gain-exponent state (-reduction + makeup), Q16 signed
        self.ga = 0           # gate attenuation state, Q16
        self.gopen = 1
        self.meter = 0        # gain_reduction output
        self.level = 0        # last Lrel (Q8, <= 0), for debugging
        self.gexp = 0         # last total gain exponent

    def step(self, x, enable=1, gate_en=0, comp_en=0, gate_thresh=0, comp_thresh=0,
             comp_ratio=0, comp_makeup=0, comp_attack=0, comp_release=0):
        if not enable:
            return x
        tg, tc, mk = s16(gate_thresh), s16(comp_thresh), s16(comp_makeup)
        code, katt, krel = comp_ratio & 7, comp_attack & 15, comp_release & 15
        # level detector
        a = abs(x) << (24 - self.dw)
        diff = (a << 8) - self.env
        step = diff >> (K_ATT if diff > 0 else K_REL)
        if step == 0 and diff > 0:
            step = 1
        self.env += step
        L = log2q8(self.env >> 8) - FS_LOG
        self.level = L
        # noise gate (log domain, linear-in-dB glide)
        # (gate_en = 0 forces "open": the attenuation glides back to 0 at the opening speed)
        if gate_en:
            if L >= tg:
                self.gopen = 1
            elif L < tg - GATE_HYST:
                self.gopen = 0
        else:
            self.gopen = 1
        if self.gopen:
            self.ga = max(0, self.ga - GATE_OPEN)
        else:
            self.ga = min(GA_MAX, self.ga + GATE_CLOSE)
        # compressor: cs = smoothed gain exponent (-reduction + makeup), Q16 signed;
        # comp_en = 0 makes the target 0 dB, so cs glides to exactly 0 at the release speed
        if comp_en:
            over = L - tc
            if over > 0 and code != 0:
                red = over if code >= 4 else over - (over >> code)
            else:
                red = 0
            red = min(red, RED_MAX)
            tgt = max(G_MIN, min(G_MAX, -red + mk))
        else:
            tgt = 0
        d = (tgt << 8) - self.cs
        st = d >> (katt if d < 0 else krel)       # falling gain = attack, rising = release
        if st == 0 and d > 0:
            st = 1
        self.cs += st
        cd, gd = self.cs >> 8, self.ga >> 8
        self.meter = min(65535, max(0, -cd) + gd)
        g = cd - gd
        g = max(G_MIN, min(G_MAX, g))
        self.gexp = g
        G = exp2gain(g)
        return sat((x * G) >> GAIN_FRAC, self.dw)


if __name__ == "__main__":
    print("LOG_T", LOG_T)
    print("EXP_T", EXP_T)
