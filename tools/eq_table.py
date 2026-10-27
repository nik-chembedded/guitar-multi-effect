#!/usr/bin/env python3
"""
eq_table.py - precomputed EQ coefficients for the board (board/gme/eq_table.json).

The coefficient search in eq_coefs.py takes ~0.4 s per section on a PC, far too slow for the board's ARM.
This tool runs exactly that search (eq_coefs.coefficient_set_full with one section at a gain, the others at
0 dB) for every gain from -12.0 to +12.0 dB in 0.1 dB steps and writes the results as a compact JSON table:

    {"format": 1, "step": 0.1, "min": -120, "max": 120,
     "sections": {"bass": [[b0, b1, b2, a1, a2, shift], ...], "mid": [...], "treble": [...]}}

entry k of a section is the gain (k - 120) / 10 dB.  The library (gme/model.py) looks gains up here.

    python3 tools/eq_table.py                 # writes board/gme/eq_table.json (about 5 min, uses all cores)
    python3 tools/eq_table.py --check         # recomputes and compares with the file
"""
import argparse
import json
import multiprocessing
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eq_coefs  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
OUT = os.path.join(ROOT, "board", "gme", "eq_table.json")
SECTIONS = ("bass", "mid", "treble")
KMIN, KMAX = -120, 120


def entry(job):
    sec, k = job
    args = [0.0, 0.0, 0.0]
    args[sec] = k / 10.0
    ints, shifts, _clipped = eq_coefs.coefficient_set_full(*args)
    return ints[5 * sec:5 * sec + 5] + [shifts[sec]]


def build(procs=None):
    jobs = [(s, k) for s in range(3) for k in range(KMIN, KMAX + 1)]
    with multiprocessing.Pool(procs) as pool:
        res = pool.map(entry, jobs, chunksize=4)
    n = KMAX - KMIN + 1
    return {"format": 1, "step": 0.1, "min": KMIN, "max": KMAX,
            "sections": dict((SECTIONS[s], res[s * n:(s + 1) * n]) for s in range(3))}


def dumps(table):
    return json.dumps(table, separators=(",", ":")) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="recompute and compare with the file")
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args(argv)
    text = dumps(build())
    if a.check:
        same = open(a.out).read() == text
        print("eq_table.json is %s" % ("up to date" if same else "DIFFERENT from a fresh computation"))
        return 0 if same else 1
    with open(a.out, "w", newline="\n") as f:
        f.write(text)
    print("wrote %s (%d bytes)" % (a.out, len(text)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
