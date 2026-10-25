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


def distortion(x, curve, mix, dw=16):
    """distortion.vhd: |x| / 2^(dw-16) saturated to the 14-bit table, sign
    restored, value * 2^(dw-16), dry/wet mix (mix*wet + (255-mix)*dry) / 256
    (floor, like the bit slice)."""
    sh = dw - 16
    out = []
    for s in x:
        a = min(abs(s) >> sh, 16383)
        wet = (-curve[a] if s < 0 else curve[a]) << sh
        out.append((mix * wet + (255 - mix) * s) >> 8)
    return out


def overdrive(x, drive, gain, dw=16):
    """overdrive.vhd: hard clip at +-drive * 2^(dw-16), then * gain, saturated."""
    t = drive << (dw - 16)
    out = []
    for s in x:
        c = t if s >= t else (-t if s <= -t else s)
        out.append(sat(gain * c, dw))
    return out
