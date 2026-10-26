"""CLI parity: every command line of the control tool of main (tools/gme_hps.py at e91a733, step D6, kept
verbatim as legacy_gme_hps.py: the oracle) is run against the oracle and against the library CLI
(board/gme_hps.py), both on a Mock with identical seeded registers.  Registers, codec writes, cabinet
memory, EQ memory, stdout and exit messages must be identical, except for the differences that are
intended and listed in test_documented_differences (each one is asserted there, with the reason).

The oracle only differs from main in that its Board is replaced by one on top of the Mock, and that its
EQ coefficient module is loaded from tools/eq_coefs.py of this repository (the library has its own copy,
gme/eq_coefs.py, which another test requires to be identical)."""
import importlib.util
import os
import shlex
import sys

import pytest

import legacy_gme_hps as legacy
import gme_hps
from conftest import REPO
from gme import device as gd
from gme import model as gm

T = gm.load_table()


def _load_tools_eq():
    spec = importlib.util.spec_from_file_location("eq_coefs_tools", os.path.join(REPO, "tools", "eq_coefs.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


EQ_TOOLS = _load_tools_eq()


class LegacyBoard(legacy.Board):
    """The oracle's Board class on top of a Mock instead of /dev/mem (same VERSION check as the original)."""

    def __init__(self, dev, check=True):
        self.dev = dev
        if check:
            v = self.read(legacy.REGS["version"])
            if v & 0xFF00 != 0x0200:
                raise SystemExit("VERSION reads 0x%04X, not 0x02xx: is the multi-effect FPGA image "
                                 "loaded? (--no-check to skip)" % v)

    def read(self, reg):
        return self.dev.read(reg)

    def write(self, reg, value):
        self.dev.write(reg, value)


@pytest.fixture(autouse=True)
def fast(monkeypatch):
    monkeypatch.setattr(legacy, "CAB_SETTLE", 0)
    monkeypatch.setattr(gm, "CAB_SETTLE", 0)
    monkeypatch.setattr(legacy, "load_eq_coefs", lambda: EQ_TOOLS)


READONLY = (0x10, 0x11, 0x12, 0x13, 0x14, 0x15, 0x2C)


def seeded_mock(version=0x0208, **regs):
    t = [0.37]
    dev = gd.Mock(version=version, clock=lambda: t[0])
    dev.t0 = 0.0
    for i in range(0x30):
        if i not in READONLY:
            dev.regs[i] = (i * 0x1111 + 7) & 0xFFFF
    for r, v in regs.items():
        dev.regs[int(r[1:], 16)] = v
    return dev


def run_old(argv, dev, monkeypatch, capsys, cab_dir=None):
    monkeypatch.setattr(legacy, "Board", lambda check=True: LegacyBoard(dev, check))
    full = (["--cab-dir", str(cab_dir)] if cab_dir else []) + list(argv)
    monkeypatch.setattr(sys, "argv", ["gme_hps.py"] + full)
    code = None
    try:
        legacy.main()
    except SystemExit as e:
        code = e.code
    cap = capsys.readouterr()
    return cap.out, code


def run_new(argv, dev, tmp_path, capsys, cab_dir=None):
    code = None
    full = ["--data-dir", str(tmp_path)] + (["--cab-dir", str(cab_dir)] if cab_dir else []) + list(argv)
    try:
        gme_hps.run(full, dev=dev)
    except SystemExit as e:
        code = e.code
    cap = capsys.readouterr()
    return cap.out, code


def reg_exists(reg, version):
    for r in T.registers:
        if r["reg"] == reg:
            return version >= r["min_version"]
    return True                                       # 0x17, 0x2F: unused, read back what was written


def dump_table(text):
    d = {}
    for line in text.splitlines():
        name, rest = line.split(" 0x", 1)
        addr, val = rest.split(" = 0x")
        d[int(addr, 16)] = int(val, 16)
    return d


def same_state(old, new, seeded, version, log=False):
    for i in range(gd.NWORDS):
        if reg_exists(i, version):
            assert new.regs[i] == old.regs[i], "register 0x%02X: library 0x%04X, old tool 0x%04X" % (
                i, new.regs[i], old.regs[i])
        else:                                          # a register the image does not have: the library leaves it alone
            assert new.regs[i] == seeded.regs[i], hex(i)
    assert new.codec_log == old.codec_log
    assert new.cab_mem == old.cab_mem and new.cab_ignored_writes == old.cab_ignored_writes
    assert new.eq_shadow == old.eq_shadow and new.eq_active == old.eq_active and new.eq_applies == old.eq_applies
    if log:
        assert new.log == old.log


def compare(argv, mode, version, tmp_path, monkeypatch, capsys, cabdir):
    """Run one command line on both; returns (old output, new output)."""
    old, new, seeded = seeded_mock(version), seeded_mock(version), seeded_mock(version)
    use_cab = cabdir if argv[0] == "cab" else None
    o_out, o_code = run_old(argv, old, monkeypatch, capsys, use_cab)
    n_out, n_code = run_new(argv, new, tmp_path, capsys, use_cab)
    if mode in ("err", "errp", "erra"):
        assert isinstance(o_code, str) and isinstance(n_code, str), (o_code, n_code)
        if mode == "err":                              # the same message
            assert n_code == o_code
        elif mode == "errp":                           # the same message up to the list of known names
            assert n_code.split(" (known")[0] == o_code.split(" (known")[0]
        assert n_out == o_out
    else:
        assert o_code is None and n_code is None, (o_code, n_code)
        if mode == "status":                           # the library adds one cabinet line (see the differences test)
            lo, ln = o_out.splitlines(), n_out.splitlines()
            assert ln[:len(lo)] == lo and all(x.startswith("cabinet ") for x in ln[len(lo):])
        elif mode == "dump":                           # the library lists the registers of the image only
            to, tn = dump_table(o_out), dump_table(n_out)
            assert tn == dict((a, v) for a, v in to.items() if reg_exists(a, version))
        elif mode != "nostdout":
            assert n_out == o_out
    same_state(old, new, seeded, version, log=(mode == "log"))
    return o_out, n_out


PRESETS = ["clean", "crunch", "lead", "ambient", "chorus", "flanger", "vibrato", "hall", "trem", "pulse"]

# (command line, mode, first FPGA VERSION where the library has the same behaviour)
#   mode: ""         identical stdout
#         err        SystemExit with the identical message;  errp: identical up to "(known ...)";  erra: any message
#         status/dump/nostdout  see compare();  log: also the identical sequence of register writes
V4, V5, V6, V7, V8 = 0x0204, 0x0205, 0x0206, 0x0207, 0x0208
FORMS = [
    # --- the commands of the old tool before step D (unchanged behaviour)
    ("status", "status", V4),
    ("--no-check status", "status", V4),
    ("read 0x10", "", V4), ("read 0x02", "", V4), ("read 0x16", "", V4), ("read 17", "", V4),
    ("read 0x2C", "", V7), ("read 0x2d", "", V8),
    ("write 0x03 0x0005", "", V4), ("write 0 9", "", V4), ("write 0x19 0xFFFF", "", V4),
    ("write 0x2D 0xFC04", "", V8), ("write 0x28 5", "", V7), ("write 0x2B 1", "", V7),
    ("set od_drive=3000 od_gain=4 effects=OD", "", V4),
    ("set effects=DIST+ECHO", "", V4),
    ("set effects=TREM trem_shape=square trem_hz=6.5 trem_depth=200", "", V4),
    ("set effects=TREM trem_shape=sine", "", V4),
    ("set trem_shape=saw trem_hz=20", "", V4),
    ("set trem_shape=triangle", "", V4),
    ("set mod_fb=-26000", "", V4),
    ("set mod_fb=26000 mod_shape=1 mod_base=96", "", V4),
    ("set effects=0x0009", "", V4),
    ("set effects=9", "", V4),
    ("set effects=OD+TREM+ECHO+DIST+CHORUS+REVERB", "", V4),
    ("set effects=reverb+chorus", "", V4),
    ("set chorus_level=128 chorus_depth=90 chorus_rate=30 mod_base=96 mod_shape=1", "", V4),
    ("set echo_time=0x3840 echo_repeat=90 echo_level=20000", "", V4),
    ("set reverb_type=3 reverb_mix=128 dist_type=2 dist_mix=220 trem_wave=7 mod_base=720 trem_rate=650", "", V4),
    ("set effects_enable=12 od_drive=0x0BB8", "", V4),
    ("set control=2", "", V4),
    ("codec 0x00 0x080", "", V4), ("codec 0x02 0x079", "", V4), ("codec 9 1", "", V4),
    ("dump", "dump", V4),
    ("preset bogus", "err", V4), ("preset", "err", V4),
    ("set foo=1", "errp", V4), ("set trem_shape=bad", "err", V4),
] + [("preset " + n, "", V4) for n in PRESETS] + [
    # --- step D: effects word with CAB / DYN / EQ
    ("set effects=CAB", "", V4), ("set effects=DYN", "", V4), ("set effects=EQ+CAB", "", V4),
    ("set effects=dyn+eq+od+trem+echo+dist+chorus+reverb+cab", "", V4), ("set effects=0x1FF", "", V4),
    ("set effects=DYN+EQ", "", V4),
    # --- D3 cabinet (needs 0x0205)
    ("cab list", "nostdout", V5), ("cab 0", "nostdout", V5), ("cab 1", "nostdout", V5),
    ("cab on", "nostdout", V5), ("cab off", "nostdout", V5),
    ("cab 7", "erra", V5),                          # (a bare `cab` differs: see test_documented_differences)
    # --- D4 reverb (0x0206)
    ("set reverb_type=4 reverb_size=60000 reverb_damp=30", "", V6),
    ("set reverb_type=4", "", V6), ("set reverb_size=0xFFFF reverb_damp=255", "", V6),
    ("set reverb_size=0 reverb_damp=0 reverb_type=0", "", V6),
    ("set reverb_size=64225 reverb_damp=128 reverb_mix=110", "", V6),
    # --- D5 dynamics: modes, thresholds in dB, ratio, times, make-up
    ("set effects=DYN dyn=gate+comp gate_db=-45 comp_db=-20 ratio=4 makeup_db=3 attack_ms=2 release_ms=100", "", V7),
    ("set dyn=none", "", V7), ("set dyn=gate", "", V7), ("set dyn=comp", "", V7), ("set dyn=gate+comp", "", V7),
    ("set dyn=bad", "err", V7),
    ("set ratio=1", "", V7), ("set ratio=2", "", V7), ("set ratio=4", "", V7), ("set ratio=8", "", V7),
    ("set ratio=inf", "", V7), ("set ratio=3", "err", V7),
    ("set gate_db=-60", "", V7), ("set gate_db=-90.5", "", V7), ("set gate_db=-0.5", "", V7),
    ("set comp_db=-10.5", "", V7), ("set comp_db=0", "", V7), ("set comp_db=-33.3", "", V7),
    ("set makeup_db=-6", "", V7), ("set makeup_db=0", "", V7), ("set makeup_db=12.5", "", V7),
    ("set attack_ms=0.01", "", V7), ("set attack_ms=0.34", "", V7), ("set attack_ms=1", "", V7),
    ("set attack_ms=5", "", V7), ("set attack_ms=20", "", V7), ("set attack_ms=1000", "", V7),
    ("set release_ms=0.5", "", V7), ("set release_ms=3", "", V7), ("set release_ms=100", "", V7),
    ("set release_ms=250", "", V7), ("set release_ms=700", "", V7),
    ("set gate_thresh=-1913 comp_thresh=-850 comp_ratio=2 comp_attack=6 comp_release=12 comp_makeup=128", "", V7),
    ("set comp_makeup=-128 gate_thresh=0xF889", "", V7),
    ("set comp_ratio=7", "", V7), ("set comp_ratio=0", "", V7), ("set comp_attack=15 comp_release=0", "", V7),
    ("set dyn_ctrl=3", "", V7), ("set dyn_ctrl=2", "", V7),
    # --- D5 EQ (VERSION 0x0207): the full write sequence is compared too
    ("eq 6 -3 2", "log", V7), ("eq 0 0 0", "log", V7), ("eq 12 12 12", "log", V7), ("eq -12 -12 -12", "log", V7),
    ("eq -12 12 -12", "log", V7), ("eq 1.5 -2.5 3.5", "log", V7), ("eq 0 0 12", "log", V7), ("eq -5 0 0", "log", V7),
    ("eq on", "log", V7), ("eq off", "log", V7),
    ("eq 13 0 0", "err", V7), ("eq 0 -12.5 0", "err", V7), ("eq 1 2", "err", V7), ("eq", "err", V7),
    ("eq 6 -3 2 1", "err", V7),
    ("eq on", "err", V4), ("eq 1 2 3", "err", V4),                 # the VERSION guard (run for VERSION < 0x0207 only)
    # --- D6 output levels (0x0208)
    ("set od_db=-3 dist_db=-6", "", V8), ("set od_db=12", "", V8), ("set od_db=-24 dist_db=12", "", V8),
    ("set od_db=0 dist_db=0", "", V8), ("set od_db=-7.3", "", V8),
    ("set od_level=-233 dist_level=512", "", V8), ("set od_level=-1024", "", V8),
    ("set od_level=0xFC04 dist_level=0", "", V8), ("set dist_level=-544", "", V8),
]


def cases_for(version):
    out = []
    for argv, mode, minv in FORMS:
        if argv == "eq" or argv.startswith("eq "):
            if version < V7:                             # the VERSION guard comes first: the same message
                if minv != V4:
                    out.append((argv, "err"))
            elif minv != V4:
                out.append((argv, mode))
        elif version >= minv:
            out.append((argv, mode))
    if version < V5:
        out += [("cab list", "err"), ("cab 0", "err"), ("cab on", "err"), ("cab off", "err")]
    return out


ALL_VERSIONS = [V8, V7, V6, V5, V4]
PARITY = [(v, a, m) for v in ALL_VERSIONS for a, m in cases_for(v)]


@pytest.mark.parametrize("version,argv,mode", PARITY, ids=lambda x: ("%04X" % x) if isinstance(x, int) else str(x))
def test_parity(version, argv, mode, monkeypatch, capsys, tmp_path, cabdir):
    compare(shlex.split(argv), mode, version, tmp_path, monkeypatch, capsys, cabdir)


def test_parity_counts():
    """How many old command forms are checked (printed with -s; asserted to keep the table from shrinking)."""
    full = cases_for(V8)
    assert len(full) >= 125
    assert sum(len(cases_for(v)) for v in ALL_VERSIONS) == len(PARITY)
    print("command forms at 0x0208: %d, all runs including older images: %d" % (len(full), len(PARITY)))


def test_every_group_of_the_old_tool_is_covered():
    cmds = set(a.split()[0] if not a.startswith("--") else a.split()[1] for a, _, _ in FORMS)
    assert {"status", "read", "write", "set", "preset", "codec", "dump", "cab", "eq"} <= cmds
    assert set(gme_hps.COMMANDS) >= {"status", "read", "write", "set", "preset", "codec", "dump", "meter", "selftest",
                                     "cab", "eq"}
    keys = " ".join(a for a, _, _ in FORMS)
    for k in ("dyn=", "gate_db=", "comp_db=", "ratio=", "makeup_db=", "attack_ms=", "release_ms=", "od_db=", "dist_db=",
              "reverb_size=", "reverb_damp=", "reverb_type=4", "od_level=", "dist_level=", "dyn_ctrl=", "comp_ratio="):
        assert k in keys, k
    for n in PRESETS:
        assert "preset " + n in keys


# ---- sequences on one device: the state carries over ---------------------------------------------------------

SEQUENCE = ["preset crunch", "cab 0", "cab on", "set effects=CAB+DYN+EQ+OD", "preset lead", "eq 4 -2 6", "preset hall",
            "cab 1", "set dyn=comp comp_db=-30 ratio=8 effects=DYN+CAB", "preset clean", "eq off", "cab off",
            "preset ambient", "set effects=0x1FF", "preset flanger", "eq on", "set gate_db=-50 attack_ms=3",
            "preset pulse", "preset vibrato"]


def test_parity_sequence(monkeypatch, capsys, tmp_path, cabdir):
    old, new, seeded = seeded_mock(), seeded_mock(), seeded_mock()
    for step in SEQUENCE:
        argv = shlex.split(step)
        use_cab = cabdir if argv[0] == "cab" else None
        o_out, o_code = run_old(argv, old, monkeypatch, capsys, use_cab)
        n_out, n_code = run_new(argv, new, tmp_path, capsys, use_cab)
        assert o_code is None and n_code is None, step
        if argv[0] in ("preset", "eq"):
            assert n_out == o_out, step
        same_state(old, new, seeded, V8)
    # the presets kept the cabinet / dynamics / EQ bits all along: 0x1FF was set, vibrato keeps 0x1C0
    assert new.regs[0] == 0x1C0 | 16


def test_presets_keep_cab_dyn_eq_like_main(monkeypatch, capsys, tmp_path):
    """Main's presets leave the CAB / DYN / EQ bits and the dynamics, cabinet and EQ registers as they are."""
    for name in PRESETS:
        old = seeded_mock(**{"r00": 0x1C5, "r21": 3, "r22": 0xF889, "r1b": 0x33})
        new = seeded_mock(**{"r00": 0x1C5, "r21": 3, "r22": 0xF889, "r1b": 0x33})
        run_old(["preset", name], old, monkeypatch, capsys)
        run_new(["preset", name], new, tmp_path, capsys)
        assert new.regs == old.regs, name
        assert new.regs[0] & 0x1C0 == 0x1C0 and new.regs[0x21] == 3 and new.regs[0x22] == 0xF889 and new.regs[0x1B] == 0x33


def test_old_presets_register_for_register(monkeypatch, capsys, tmp_path):
    """Each factory preset gives exactly the register values main's PRESETS table defines (incl. dist_level, hall)."""
    for name in PRESETS:
        dev = seeded_mock(**{"r00": 0})
        run_new(["preset", name], dev, tmp_path, capsys)
        keys = legacy.EFFECT_REGS + ["trem_rate", "mod_base", "mod_fb", "mod_shape", "reverb_size", "reverb_damp",
                                      "od_level", "dist_level"]
        exp = dict((k, 0) for k in keys)
        exp.update(legacy.PRESETS[name])
        for k, v in exp.items():
            assert dev.regs[legacy.REGS[k]] == v & 0xFFFF, (name, k)
    assert legacy.PRESETS["crunch"]["dist_level"] == -233 and legacy.PRESETS["lead"]["dist_level"] == -544


def test_preset_tables_equal_main():
    """params.json presets == main's PRESETS dict (register values, per preset)."""
    for name, d in legacy.PRESETS.items():
        lib = T.presets[name]
        assert lib["keep"] == ["cab", "dyn", "eq"]
        want = dict((k, v) for k, v in d.items() if k != "effects_enable")
        want = dict(("mod_mix" if k == "chorus_level" else "mod_depth" if k == "chorus_depth" else
                     "mod_rate" if k == "chorus_rate" else k, v) for k, v in want.items())
        assert lib["params"] == want, name
        word = d["effects_enable"]
        assert sum(1 << T.fx_by_id[f]["bit"] for f in lib["fx"]) == word, name
    assert list(legacy.PRESETS) == list(T.presets)


# ---- the oracle itself ---------------------------------------------------------------------------------------------

def test_oracle_selftest_passes(capsys):
    legacy.selftest()
    assert "selftest OK" in capsys.readouterr().out


ORACLE_SHA256 = "20d4f8f4031e7a252e55b18ea3e649003c8fc77a7fd62bc33b112d3cae2c1b55"      # tools/gme_hps.py at e91a733


def test_oracle_is_main_verbatim():
    """legacy_gme_hps.py is main's tools/gme_hps.py at e91a733, unchanged (hash of the file; with git also compared)."""
    import hashlib
    import subprocess
    mine = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "legacy_gme_hps.py"), "rb").read()
    mine = mine.replace(b"\r\n", b"\n")
    assert hashlib.sha256(mine).hexdigest() == ORACLE_SHA256
    try:
        r = subprocess.run(["git", "-C", REPO, "show", "e91a733:tools/gme_hps.py"], capture_output=True)
    except OSError:
        return
    if r.returncode == 0:
        assert mine == r.stdout.replace(b"\r\n", b"\n")


def test_library_eq_coefs_is_the_tools_file():
    a = open(os.path.join(REPO, "tools", "eq_coefs.py"), "rb").read().replace(b"\r\n", b"\n")
    b = open(os.path.join(REPO, "board", "gme", "eq_coefs.py"), "rb").read().replace(b"\r\n", b"\n")
    assert a == b


# ---- number conversions against the oracle -----------------------------------------------------------------------

def test_db_conversion_sweep_matches_oracle():
    gate = T.param("gate_thresh")
    for i in range(-1440, 121):
        x = i / 10.0
        assert gate.parse("%.1f" % x) == legacy.db_to_q8(x), x
    level = T.param("od_level")
    for i in range(-240, 121):
        x = i / 10.0
        assert level.parse("%.1f" % x) == max(-1024, legacy.db_to_q8(x)), x
    mk = T.param("comp_makeup")
    for x in (-24, -12.5, -6, -3.3, 0, 1, 2.2, 3, 6, 9.9, 12, 24):
        assert mk.parse(str(x)) == legacy.db_to_q8(x), x
    assert (legacy.db_to_q8(-20) & 0xFFFF) == 0xFCAE and gate.parse("-20") & 0xFFFF == 0xFCAE


def test_ms_conversion_sweep_matches_oracle():
    for name in ("comp_attack", "comp_release"):
        p = T.param(name)
        x = 0.005
        while x < 3000:
            assert p.parse("%.4f" % x) == legacy.ms_to_shift(float("%.4f" % x)), x
            x *= 1.07
        for k in range(16):                              # the effective time of each setting maps back to it
            assert p.parse(p.format(k)) == k and p.from_display(p.to_display(k)) == k
    p = T.param("comp_attack")
    assert p.format(0) == "0.02 ms" and p.format(6) == "1.33 ms" and p.format(12) == "85.33 ms" and p.format(15) == "682.67 ms"


def test_eq_words_match_oracle():
    for g in [(0, 0, 0), (6, -3, 2), (12, 12, 12), (-12, -12, -12), (-12, 12, -12), (12, -12, 12), (1.5, -2.5, 3.5),
              (0, 0, 12), (-5, 0, 0), (0.1, -0.1, 0.3)]:
        assert gm.Model.eq_words(*g) == legacy.eq_words(*g), g


# ---- intended differences ------------------------------------------------------------------------------------------

def test_documented_differences(monkeypatch, capsys, tmp_path, cabdir):
    # 1. `status` has one more line, the cabinet (bank, loaded slot), when the image has a cabinet; the dynamics
    #    gain-reduction line is the same and comes first.  Reason: the web page shows the same facts.
    old, new = seeded_mock(), seeded_mock()
    o, _ = run_old(["status"], old, monkeypatch, capsys)
    n, _ = run_new(["status"], new, tmp_path, capsys)
    assert n.splitlines()[:3] == o.splitlines() and len(n.splitlines()) == 4
    assert n.splitlines()[2].startswith("dynamics gain reduction") and n.splitlines()[3].startswith("cabinet ")
    # 2. cab: the registers are the same (parity above) but the texts differ: `cab list` marks the loaded slot,
    #    `cab N` also names the bank; `cab` alone prints the cabinet status (the old tool printed its usage).
    old, new = seeded_mock(), seeded_mock()
    o, oc = run_old(["cab"], old, monkeypatch, capsys, cabdir)
    n, nc = run_new(["cab"], new, tmp_path, capsys, cabdir)
    assert oc == "cab list | cab N | cab on | cab off" and nc is None and n.startswith("cabinet ")
    n, _ = run_new(["cab", "1"], new, tmp_path, capsys, cabdir)
    assert "loaded into bank" in n and "shift 5" in n
    # 3. values outside the range of the register field are refused (the old tool wrote the low 16 bits)
    for arg, reg in (("reverb_type=7", 14), ("gate_thresh=40000", 0x22), ("od_level=600", 0x2D), ("trem_wave=12", 3),
                     ("comp_attack=16", 0x25)):
        old, new = seeded_mock(), seeded_mock()
        run_old(["set", arg], old, monkeypatch, capsys)
        n, nc = run_new(["set", arg], new, tmp_path, capsys)
        assert isinstance(nc, str) and new.regs[reg] != old.regs[reg] and new.regs[reg] == seeded_mock().regs[reg], arg
    # 4. VERSION guards are per register: the library refuses parameters the image does not have, the old tool
    #    wrote the register anyway (harmless: unknown addresses ignore writes)
    for ver, arg in ((V6, "gate_db=-45"), (V7, "od_db=-3"), (V5, "reverb_size=60000"), (V6, "ratio=4")):
        old, new = seeded_mock(ver), seeded_mock(ver)
        run_old(["set", arg], old, monkeypatch, capsys)
        _, nc = run_new(["set", arg], new, tmp_path, capsys)
        assert "needs FPGA VERSION" in nc and new.log == [] and old.log != [], arg
    # 5. dump lists only the registers of the image (the old tool lists all it knows)
    old, new = seeded_mock(V6), seeded_mock(V6)
    o, _ = run_old(["dump"], old, monkeypatch, capsys)
    n, _ = run_new(["dump"], new, tmp_path, capsys)
    assert max(dump_table(n)) == 0x20 and max(dump_table(o)) == 0x2E
    # 6. the reverb type "Custom" needs VERSION 0x0206 (the old tool wrote 4 on any image, where it acts as 3)
    new = seeded_mock(V5)
    _, nc = run_new(["set", "reverb_type=custom"], new, tmp_path, capsys)
    assert "needs FPGA VERSION 0x0206" in nc
    # 7. presets write only the registers the image has (reverb size / damp from 0x0206, levels from 0x0208) and name
    #    the parameters of the preset that it lacks on stderr
    old, new = seeded_mock(V5), seeded_mock(V5)
    run_old(["preset", "hall"], old, monkeypatch, capsys)
    run_new(["preset", "hall"], new, tmp_path, capsys)
    assert old.regs[0x1F] == 60500 and new.regs[0x1F] == seeded_mock(V5).regs[0x1F]
    gme_hps.run(["--data-dir", str(tmp_path), "preset", "hall"], dev=seeded_mock(V5))
    assert "reverb_size not in this FPGA image" in capsys.readouterr().err
    # 8. the EQ gains set with `set eq_bass=...` (or the page) have 0.1 dB steps; `eq B M T` takes any number like
    #    the old tool (the model keeps the exact value, the parameter shows it rounded)
    new = seeded_mock()
    run_new(["eq", "2.55", "0", "0"], new, tmp_path, capsys)
    n, _ = run_new(["get", "eq_bass"], new, tmp_path, capsys)
    assert "2.6 dB (raw 26)" in n
    assert new.eq_active == legacy.eq_words(2.55, 0, 0)


def test_eq_via_set_equals_eq_command(tmp_path, capsys):
    """set eq_bass=.. eq_mid=.. eq_treble=.. (display units) writes the same coefficients as `eq B M T`."""
    a, b = seeded_mock(), seeded_mock()
    run_new(["eq", "6", "-3", "2"], a, tmp_path / "a", capsys)
    run_new(["set", "eq_bass=6", "eq_mid=-3dB", "eq_treble=2"], b, tmp_path / "b", capsys)
    assert a.eq_active == b.eq_active == legacy.eq_words(6, -3, 2)
    assert b.regs[0] & 0x100 == seeded_mock().regs[0] & 0x100          # `set` does not switch the EQ on


def test_status_gain_reduction_line(monkeypatch, capsys, tmp_path):
    """DYN_GR in the status: identical to the old tool with the compressor on (non-zero) and off (0.0)."""
    kw = {"r00": 0x80, "r21": 2, "r23": (-850) & 0xFFFF, "r24": 2, "r27": 0}
    old, new = seeded_mock(**kw), seeded_mock(**kw)
    o, _ = run_old(["status"], old, monkeypatch, capsys)
    n, _ = run_new(["status"], new, tmp_path, capsys)
    line = [l for l in o.splitlines() if l.startswith("dynamics gain reduction")][0]
    assert line in n.splitlines() and float(line.split()[3]) > 1.0, line
    kw = {"r00": 0x00, "r21": 3}
    old, new = seeded_mock(**kw), seeded_mock(**kw)
    o, _ = run_old(["status"], old, monkeypatch, capsys)
    n, _ = run_new(["status"], new, tmp_path, capsys)
    assert "dynamics gain reduction 0.0 dB" in o and "dynamics gain reduction 0.0 dB" in n
    o, _ = run_old(["status"], seeded_mock(V6), monkeypatch, capsys)
    n, _ = run_new(["status"], seeded_mock(V6), tmp_path, capsys)
    assert "gain reduction" not in o and "gain reduction" not in n
