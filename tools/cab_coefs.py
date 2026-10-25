#!/usr/bin/env python3
"""
cab_coefs.py - cabinet IR -> block-floating-point FIR coefficients (v2 step D3).

The IR (after cabir.trim / cabir.normalise) is stored scaled up by 2^shift so
that it uses the 18-bit coefficient range; the FIR block (cab_fir.vhd) takes
`shift` as a parameter and divides it out again:

    shift = largest s in 0..7 with max|h| * 2^s < 1
    coef  = round(h * 2^(17 + shift)), clipped to signed 18 bit
    y[n]  = sat(floor(sum coef[k] * x[n-k] / 2^(17 + shift)))

write_mif() writes an Intel .mif (18-bit words, one per tap, stored as unsigned
two's complement so that every tool reads it the same way).

    source ~/venvs/gme/bin/activate
    python3 tools/cab_coefs.py                # slot 0 -> fpga/ip/cab_default.mif
    python3 tools/cab_coefs.py --slot 3 --out /tmp/cab03.mif
    python3 tools/cab_coefs.py --build        # every manifest slot whose IR file is present
                                              #   -> ir/build/cabNN.coef (for the board, see below)

--build writes, for each cabinet of ir/manifest.json whose IR file exists, the text file
ir/build/cabNN.coef: line 1 the cabinet name, line 2 the shift, then the 2048 signed
coefficients, one per line. Copy them to the board (scp ir/build/*.coef root@<board>:cab/)
and load one with  gme_hps.py cab N  (docs/register_map.md, CAB registers). ir/build/ and
ir/third_party/ are git-ignored: third-party IR files and their coefficients are never committed.
"""
import argparse
import json
import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cabir  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
MANIFEST = os.path.join(ROOT, "ir", "manifest.json")
DEFAULT_MIF = os.path.join(ROOT, "fpga", "ip", "cab_default.mif")
MAX_SHIFT = 7


def to_coefs(h, taps=cabir.TAPS):
    """float IR (|h| < 1, `taps` long) -> (int coefficient array, shift)."""
    h = np.asarray(h, dtype=np.float64)
    peak = float(np.max(np.abs(h)))
    shift = 0
    while shift < MAX_SHIFT and peak * 2.0 ** (shift + 1) < 1.0:
        shift += 1
    full = 1 << (cabir.COEF_BITS - 1)
    c = np.clip(np.round(h * 2.0 ** (17 + shift)), -full, full - 1).astype(np.int64)
    return c, shift


def ir_to_coefs(x, sr, taps=cabir.TAPS):
    """Samples of an IR file -> coefficients (resample, trim, normalise, block-floating-point)."""
    h = cabir.normalise(cabir.trim(cabir.resample(x, sr), taps))
    return to_coefs(h, taps)


def wav_to_coefs(path, taps=cabir.TAPS):
    x, sr = cabir.read_wav(path)
    return ir_to_coefs(x, sr, taps)


def slot_coefs(slot=0, taps=cabir.TAPS):
    """Coefficients of a cabinet of ir/manifest.json -> (coefs, shift)."""
    with open(MANIFEST) as f:
        cabs = json.load(f)["cabinets"]
    c = [c for c in cabs if c["slot"] == slot][0]
    return wav_to_coefs(os.path.join(ROOT, c["file"]), taps)


def write_mif(path, coefs, shift=None, depth=None):
    """Intel .mif, WIDTH 18, DEPTH = depth (default 2 * len(coefs): the RAM holds two banks and
    Quartus wants the .mif depth to equal the RAM depth); bank 0 = coefs, bank 1 = 0.
    Words are unsigned two's complement."""
    n = depth or 2 * len(coefs)
    mask = (1 << cabir.COEF_BITS) - 1
    lines = ["-- cab_coefs.py: cabinet FIR coefficients, signed Q1.17 x 2^shift (block floating point)"]
    if shift is not None:
        lines.append("-- output shift = %d (cab_fir input 'shift')" % shift)
    lines += ["", "WIDTH=%d;" % cabir.COEF_BITS, "DEPTH=%d;" % n, "",
              "ADDRESS_RADIX=UNS;", "DATA_RADIX=UNS;", "", "CONTENT BEGIN"]
    lines += ["\t%d\t:\t%d;" % (i, (int(coefs[i]) & mask) if i < len(coefs) else 0) for i in range(n)]
    lines += ["END;", ""]
    with open(path, "w", newline="\n") as f:
        f.write("\n".join(lines))


BUILD_DIR = os.path.join(ROOT, "ir", "build")


def write_coef(path, name, coefs, shift):
    """cabNN.coef for gme_hps.py: name, shift, then one signed coefficient per line."""
    with open(path, "w", newline="\n") as f:
        f.write("%s\n%d\n" % (name, shift))
        f.write("\n".join(str(int(c)) for c in coefs) + "\n")


def build_all(outdir=BUILD_DIR, taps=cabir.TAPS):
    """cabNN.coef for every manifest slot whose IR file is present; returns the slots written."""
    with open(MANIFEST) as f:
        cabs = json.load(f)["cabinets"]
    os.makedirs(outdir, exist_ok=True)
    done = []
    for c in sorted(cabs, key=lambda c: c["slot"]):
        path = os.path.join(ROOT, c["file"])
        if not os.path.isfile(path):
            print("slot %2d  %-24s missing (%s): skipped" % (c["slot"], c["name"], c["file"]))
            continue
        coefs, shift = wav_to_coefs(path, taps)
        out = os.path.join(outdir, "cab%02d.coef" % c["slot"])
        write_coef(out, c["name"], coefs, shift)
        print("slot %2d  %-24s shift %d, peak %5.1f %% -> %s"
              % (c["slot"], c["name"], shift, 100.0 * np.max(np.abs(coefs)) / (1 << 17), out))
        done.append(c["slot"])
    return done


def read_mif(path):
    """.mif written by write_mif (or any UNS/DEC mif) -> list of signed 18-bit ints."""
    out, data = {}, False
    with open(path) as f:
        lines = f.readlines()
    for line in lines:
        if not data:
            data = "BEGIN" in line
            continue
        m = re.match(r"\s*(\d+)\s*:\s*(-?\d+)\s*;", line)
        if m:
            v = int(m.group(2)) & ((1 << cabir.COEF_BITS) - 1)
            out[int(m.group(1))] = v - (1 << cabir.COEF_BITS) if v >= 1 << (cabir.COEF_BITS - 1) else v
    return [out.get(i, 0) for i in range(max(out) + 1)]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--slot", type=int, default=0, help="cabinet slot of ir/manifest.json (default 0)")
    ap.add_argument("--out", default=DEFAULT_MIF, help="output .mif (default fpga/ip/cab_default.mif)")
    ap.add_argument("--build", action="store_true",
                    help="write ir/build/cabNN.coef for every manifest slot that is present (for gme_hps.py cab)")
    a = ap.parse_args()
    if a.build:
        done = build_all()
        print("%d cabinet file(s) in %s" % (len(done), BUILD_DIR))
        return
    c, shift = slot_coefs(a.slot)
    write_mif(a.out, c, shift)
    print("slot %d -> %s: %d taps, shift %d, peak coefficient %d (%.1f %% of full scale), sum|h| = %.3f"
          % (a.slot, a.out, len(c), shift, np.max(np.abs(c)), 100.0 * np.max(np.abs(c)) / (1 << 17),
             np.sum(np.abs(c)) / 2.0 ** (17 + shift)))


if __name__ == "__main__":
    main()
