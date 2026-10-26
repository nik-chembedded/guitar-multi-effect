"""
golden.py - bit-exact Python reference models of the effects (integer maths
exactly as in the RTL). Each function takes a list of input samples and
returns the expected output samples, without the pipeline latency.
dw = sample width (step C: 16 = v1, 24); parameters keep their 16-bit scale.
"""


def sat16(v):
    return max(-32768, min(32767, v))


def sat(v, w):
    return max(-(1 << (w - 1)), min((1 << (w - 1)) - 1, v))


def bypass(x):
    return list(x)


def load_mif(path):
    """Intel .mif (lines 'address : value;') -> list of ints."""
    words, data = {}, False
    with open(path) as f:
        for line in f:
            line = line.strip()
            if "BEGIN" in line:
                data = True
                continue
            if data and ":" in line:
                a, v = line.rstrip(";").split(":")
                words[int(a)] = int(v)
    return [words.get(i, 0) for i in range(max(words) + 1)]


LEVEL_MIN, LEVEL_MAX = -1024, 512          # -24.08 dB .. +12.04 dB (Q8 log2 units)
LEVEL_TAB = [round(2 ** (f / 256) * 65536) for f in range(256)]      # level_gain.vhd, 65536 .. 130718


def level_gain(level):
    """level_gain.vhd: signed Q8 log2 level (clamped to -1024 .. +512) -> (mant, sh) with
    gain = mant / 2^sh = 2^(level/256) (to the table's rounding); 0 -> (65536, 16) = exactly 1."""
    lv = max(LEVEL_MIN, min(LEVEL_MAX, level))
    return LEVEL_TAB[lv & 255], 16 - (lv >> 8)


def apply_level(v, level):
    """floor(v * 2^(level/256)) as the RTL computes it: (v * mant) >> sh, v a (wide) signed integer."""
    mant, sh = level_gain(level)
    return (v * mant) >> sh


def distortion(x, curve, mix, dw=16, level=0):
    """distortion.vhd: |x| / 2^(dw-16) saturated to the 14-bit table, sign
    restored, value * 2^(dw-16), dry/wet mix (mix*wet + (255-mix)*dry) / 256
    (floor, like the bit slice). D6: the magnitude of the shaped value is multiplied by the output
    level (floor) and limited to 2^(dw-1) - 1 before the sign is restored; level 0 = unchanged."""
    sh = dw - 16
    out = []
    for s in x:
        a = min(abs(s) >> sh, 16383)
        m = min(apply_level(curve[a] << sh, level), (1 << (dw - 1)) - 1)
        wet = -m if s < 0 else m
        out.append((mix * wet + (255 - mix) * s) >> 8)
    return out


def overdrive(x, drive, gain, dw=16, level=0):
    """overdrive.vhd: hard clip at +-drive * 2^(dw-16), then * gain, then (D6) * the output level
    (floor), saturated; level 0 = unchanged."""
    t = drive << (dw - 16)
    out = []
    for s in x:
        c = t if s >= t else (-t if s <= -t else s)
        out.append(sat(apply_level(gain * c, level), dw))
    return out
