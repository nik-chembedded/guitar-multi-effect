"""
golden.py - bit-exact Python reference models of the effects (integer maths
exactly as in the RTL). Each function takes a list of input samples and
returns the expected output samples, without the pipeline latency.
"""


def sat16(v):
    return max(-32768, min(32767, v))


def bypass(x):
    return list(x)


def load_mif(path):
    """Intel .mif (lines 'address : value;') -> list of ints."""
    words, data = {}, False
    for line in open(path):
        line = line.strip()
        if "BEGIN" in line:
            data = True
            continue
        if data and ":" in line:
            a, v = line.rstrip(";").split(":")
            words[int(a)] = int(v)
    return [words.get(i, 0) for i in range(max(words) + 1)]


def distortion(x, curve, mix):
    """distortion.vhd: |x| saturated to the 14-bit table, sign restored,
    dry/wet mix (mix*wet + (255-mix)*dry) / 256 (floor, like the bit slice)."""
    out = []
    for s in x:
        a = min(abs(s), 16383)
        wet = -curve[a] if s < 0 else curve[a]
        out.append((mix * wet + (255 - mix) * s) >> 8)
    return out


def overdrive(x, drive, gain):
    """overdrive.vhd: hard clip at +-drive, then * gain, saturated."""
    out = []
    for s in x:
        c = drive if s >= drive else (-drive if s <= -drive else s)
        out.append(sat16(gain * c))
    return out
