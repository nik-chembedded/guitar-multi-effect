#!/usr/bin/env python3
"""
wavconv.py - convert audio between WAV files and the sample text files used by
the VHDL testbenches (one signed 16-bit integer per line, 48 kHz, mono).

  wavconv.py to-txt  input.wav  samples.txt [--peak 16000] [--seconds N]
  wavconv.py to-wav  samples.txt output.wav
  wavconv.py info    input.wav
  wavconv.py clicks  input.txt output.txt [--limit 0.05]   (gain discontinuities)
  wavconv.py compare samples.txt other.wav                 (sample-exact comparison, exit 1 if different)

to-txt mixes to mono, resamples to 48 kHz (linear interpolation) and scales the
signal so its peak is --peak (default 16000 = -6 dBFS; 0 keeps the level).
Only the Python standard library is used.
"""
import argparse
import array
import struct
import sys
import wave

FS = 48000


def read_wav(path):
    """Return (mono samples as floats in -1..1, sample rate)."""
    with wave.open(path, "rb") as w:
        nch, width, rate, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        raw = w.readframes(n)
    if width == 1:
        data = [(b - 128) / 128.0 for b in raw]
    elif width == 2:
        a = array.array("h")
        a.frombytes(raw)
        if sys.byteorder == "big":
            a.byteswap()
        data = [s / 32768.0 for s in a]
    elif width == 3:
        data = [int.from_bytes(raw[i:i + 3], "little", signed=True) / 8388608.0
                for i in range(0, len(raw), 3)]
    elif width == 4:
        data = [s / 2147483648.0 for s in struct.unpack("<%di" % (len(raw) // 4), raw)]
    else:
        raise ValueError("unsupported sample width %d" % width)
    mono = [sum(data[i:i + nch]) / nch for i in range(0, len(data), nch)]
    return mono, rate


def resample(x, src, dst):
    if src == dst or not x:
        return list(x)
    n_out = int(len(x) * dst / src)
    step = src / dst
    out = []
    for i in range(n_out):
        p = i * step
        k = int(p)
        f = p - k
        a = x[k]
        b = x[k + 1] if k + 1 < len(x) else a
        out.append(a + (b - a) * f)
    return out


def cmd_to_txt(args):
    x, rate = read_wav(args.input)
    x = resample(x, rate, FS)
    if args.seconds:
        x = x[:int(args.seconds * FS)]
    peak = max((abs(v) for v in x), default=0.0)
    scale = (args.peak / peak) if (args.peak and peak > 0) else 32767.0
    with open(args.output, "w") as f:
        for v in x:
            f.write("%d\n" % max(-32768, min(32767, round(v * scale))))
    print("%s: %d samples (%.2f s @ 48 kHz), input peak %.3f FS, scaled to peak %d"
          % (args.output, len(x), len(x) / FS, peak, round(peak * scale)))


def cmd_to_wav(args):
    s = array.array("h")
    with open(args.input) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                s.append(max(-32768, min(32767, int(line.split()[-1]))))
    if sys.byteorder == "big":
        s.byteswap()
    with wave.open(args.output, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(FS)
        w.writeframes(s.tobytes())
    peak = max((abs(v) for v in s), default=0)
    print("%s: %d samples (%.2f s), peak %d" % (args.output, len(s), len(s) / FS, peak))


def read_txt(path):
    with open(path) as f:
        return [int(l.split()[-1]) for l in f if l.strip() and not l.startswith("#")]


def cmd_clicks(args):
    """Largest sample-to-sample change of the gain out/in (amplitude effects)."""
    x, y = read_txt(args.input), read_txt(args.output)
    lat = min(range(0, 33), key=lambda L: sum(abs(y[i + L] - x[i]) for i in range(1000, 3000)
                                               if i + L < len(y)))
    gain = {i: y[i + lat] / x[i] for i in range(len(x) - lat) if abs(x[i]) > args.min_level}
    steps = sorted(((abs(gain[i] - gain[i - 1]), i) for i in gain if i - 1 in gain), reverse=True)
    worst = steps[0] if steps else (0.0, 0)
    print("latency %d, gain %.2f .. %.2f, largest 1-sample gain step %.3f at %.1f ms"
          % (lat, min(gain.values()), max(gain.values()), worst[0], worst[1] / 48.0))
    if worst[0] > args.limit:
        print("CLICK: gain step above %.3f" % args.limit)
        sys.exit(1)


def cmd_compare(args):
    """Sample-exact comparison of a sample text file with a 16-bit WAV (ModelSim vs GHDL output)."""
    a = read_txt(args.input)
    with wave.open(args.other, "rb") as w:
        raw = w.readframes(w.getnframes())
    b = array.array("h")
    b.frombytes(raw)
    if sys.byteorder == "big":
        b.byteswap()
    n = min(len(a), len(b))
    bad = [i for i in range(n) if a[i] != b[i]]
    print("%d vs %d samples, %d differ%s" % (len(a), len(b), len(bad) + abs(len(a) - len(b)),
                                              (", first at %d (%d vs %d)" % (bad[0], a[bad[0]], b[bad[0]])) if bad else ""))
    if bad or len(a) != len(b):
        sys.exit(1)


def cmd_info(args):
    with wave.open(args.input, "rb") as w:
        print("%s: %d ch, %d bit, %d Hz, %.2f s" % (args.input, w.getnchannels(), w.getsampwidth() * 8,
                                                   w.getframerate(), w.getnframes() / w.getframerate()))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("to-txt")
    t.add_argument("input")
    t.add_argument("output")
    t.add_argument("--peak", type=int, default=16000, help="target peak (0 = keep level)")
    t.add_argument("--seconds", type=float, default=0, help="truncate to N seconds")
    t.set_defaults(func=cmd_to_txt)
    w = sub.add_parser("to-wav")
    w.add_argument("input")
    w.add_argument("output")
    w.set_defaults(func=cmd_to_wav)
    c = sub.add_parser("clicks", help="detect gain discontinuities (tremolo-type effects)")
    c.add_argument("input", help="input sample text file")
    c.add_argument("output", help="output sample text file")
    c.add_argument("--min-level", type=int, default=3000, help="ignore quieter input samples")
    c.add_argument("--limit", type=float, default=0.05, help="max allowed 1-sample gain step")
    c.set_defaults(func=cmd_clicks)
    k = sub.add_parser("compare", help="sample-exact comparison of a sample text file with a WAV")
    k.add_argument("input", help="sample text file")
    k.add_argument("other", help="16-bit WAV")
    k.set_defaults(func=cmd_compare)
    i = sub.add_parser("info")
    i.add_argument("input")
    i.set_defaults(func=cmd_info)
    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
