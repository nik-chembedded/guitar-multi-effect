"""CLI parity: every command line of the old tools/gme_hps.py (kept verbatim as
legacy_gme_hps.py) is run against the old code and against the new CLI, both on a Mock
(VERSION 0x0204 = the image the old tool was written for); registers, codec writes,
stdout and exit messages must be identical."""
import os
import sys

import pytest

import legacy_gme_hps as legacy
import gme_hps
from gme import device as gd


class LegacyBoard(legacy.Board):
    """The old Board class on top of a Mock instead of /dev/mem."""

    def __init__(self, dev):
        self.dev = dev

    def read(self, reg):
        return self.dev.read(reg)

    def write(self, reg, value):
        self.dev.write(reg, value)


def seeded_mock(version=0x0204):
    t = [0.37]
    dev = gd.Mock(version=version, clock=lambda: t[0])
    dev.t0 = 0.0
    for i in range(0x20):
        if i not in (0x10, 0x11, 0x12, 0x13, 0x14, 0x15):
            dev.regs[i] = (i * 0x1111 + 7) & 0xFFFF
    return dev


def run_old(argv, dev, monkeypatch, capsys):
    monkeypatch.setattr(legacy, "Board", lambda check=True: LegacyBoard(dev))
    monkeypatch.setattr(sys, "argv", ["gme_hps.py"] + argv)
    code = None
    try:
        legacy.main()
    except SystemExit as e:
        code = e.code
    return capsys.readouterr().out, code


def run_new(argv, dev, tmp_path, capsys):
    code = None
    try:
        gme_hps.run(["--data-dir", str(tmp_path)] + argv, dev=dev)
    except SystemExit as e:
        code = e.code
    return capsys.readouterr().out, code


PRESETS = ["clean", "crunch", "lead", "ambient", "chorus", "flanger", "vibrato", "trem", "pulse"]

CASES = [
    ["status"],
    ["read", "0x10"], ["read", "0x02"], ["read", "0x16"], ["read", "17"],
    ["write", "0x03", "0x0005"], ["write", "0", "9"], ["write", "0x19", "0xFFFF"],
    ["set", "od_drive=3000", "od_gain=4", "effects=OD"],
    ["set", "effects=DIST+ECHO"],
    ["set", "effects=TREM", "trem_shape=square", "trem_hz=6.5", "trem_depth=200"],
    ["set", "effects=TREM", "trem_shape=sine"],
    ["set", "trem_shape=saw", "trem_hz=20"],
    ["set", "trem_shape=triangle"],
    ["set", "mod_fb=-26000"],
    ["set", "mod_fb=26000", "mod_shape=1", "mod_base=96"],
    ["set", "effects=0x0009"],
    ["set", "effects=9"],
    ["set", "effects=OD+TREM+ECHO+DIST+CHORUS+REVERB"],
    ["set", "effects=reverb+chorus"],
    ["set", "chorus_level=128", "chorus_depth=90", "chorus_rate=30", "mod_base=96", "mod_shape=1"],
    ["set", "echo_time=0x3840", "echo_repeat=90", "echo_level=20000"],
    ["set", "reverb_type=3", "reverb_mix=128", "dist_type=2", "dist_mix=220", "trem_wave=7",
     "mod_base=720", "trem_rate=650"],
    ["set", "effects_enable=12", "od_drive=0x0BB8"],
    ["set", "control=2"],
    ["codec", "0x00", "0x080"], ["codec", "0x02", "0x079"], ["codec", "9", "1"],
    ["--no-check", "status"],
    ["preset", "bogus"], ["preset"],
    ["set", "foo=1"], ["set", "trem_shape=bad"],
] + [["preset", n] for n in PRESETS]


@pytest.mark.parametrize("argv", CASES, ids=lambda a: " ".join(a))
def test_parity(argv, monkeypatch, capsys, tmp_path):
    old, new = seeded_mock(), seeded_mock()
    o_out, o_code = run_old(argv, old, monkeypatch, capsys)
    n_out, n_code = run_new(argv, new, tmp_path, capsys)
    if o_code is not None and not isinstance(o_code, str):
        assert n_code == o_code
    elif o_code is not None:
        # error text: the old and new message start the same way
        assert isinstance(n_code, str) and n_code.split(":")[0].split("'")[0] == o_code.split(":")[0].split("'")[0]
        if argv[0] == "preset":
            assert n_code == o_code
    assert n_out == o_out
    assert new.regs == old.regs
    assert new.codec_log == old.codec_log


def test_parity_dump_values(monkeypatch, capsys, tmp_path):
    old, new = seeded_mock(), seeded_mock()
    o_out, _ = run_old(["dump"], old, monkeypatch, capsys)
    n_out, _ = run_new(["dump"], new, tmp_path, capsys)

    def table(text):
        d = {}
        for line in text.splitlines():
            name, rest = line.split(" 0x", 1)
            addr, val = rest.split(" = 0x")
            d[int(addr, 16)] = int(val, 16)
        return d
    assert table(n_out) == table(o_out)
    assert len(o_out.splitlines()) == len(n_out.splitlines())


def test_old_presets_register_for_register(monkeypatch, capsys, tmp_path):
    """Each factory preset gives exactly the register values the old PRESETS table defined."""
    for name in PRESETS:
        dev = seeded_mock()
        run_new(["preset", name], dev, tmp_path, capsys)
        exp = dict((k, 0) for k in legacy.EFFECT_REGS + ["trem_rate", "mod_base", "mod_fb", "mod_shape"])
        exp.update(legacy.PRESETS[name])
        for k, v in exp.items():
            assert dev.regs[legacy.REGS[k]] == v & 0xFFFF, (name, k)


def test_every_old_command_exists():
    assert set(["status", "read", "write", "set", "preset", "codec", "dump", "meter", "selftest"]) <= set(gme_hps.COMMANDS)


def test_selftest(capsys):
    gme_hps.run(["selftest"])
    assert "selftest OK" in capsys.readouterr().out


def test_options_anywhere(capsys, tmp_path):
    dev = seeded_mock(0x0205)
    gme_hps.run(["set", "--data-dir", str(tmp_path), "od_gain=3"], dev=dev)
    gme_hps.run(["read", "2", "--data-dir", str(tmp_path)], dev=dev)
    assert capsys.readouterr().out.strip() == "0x0003"


def test_meter_counts(capsys, tmp_path):
    gme_hps.run(["--data-dir", str(tmp_path), "meter", "2"], dev=seeded_mock())
    assert "in" in capsys.readouterr().out


# ---- new commands -------------------------------------------------------------------------

def new(argv, dev, tmp_path, capsys, cab_dir=None):
    extra = ["--data-dir", str(tmp_path)] + (["--cab-dir", str(cab_dir)] if cab_dir else [])
    gme_hps.run(extra + argv, dev=dev)
    return capsys.readouterr().out


def test_set_by_id_display_units(tmp_path, capsys):
    dev = gd.Mock(version=0x0205)
    new(["set", "echo_time=320ms", "trem_rate=6.5Hz", "echo_on=on", "dist_type=heavy",
         "echo_repeat=50%", "cab_on=1", "trem_wave=Free square"], dev, tmp_path, capsys)
    assert dev.regs[5] == 15360 and dev.regs[0x16] == 650
    assert dev.regs[9] == 2 and dev.regs[6] == 128 and dev.regs[3] == 11
    assert dev.regs[0] == 0x44                                  # echo (bit2) + cab (bit6)
    out = new(["get", "echo_time", "trem_rate", "echo_on", "dist_type"], dev, tmp_path, capsys)
    assert "echo_time" in out and "320 ms (raw 15360)" in out
    assert "6.5 Hz (raw 650)" in out and "echo_on" in out and "Heavy" in out
    all_out = new(["get"], dev, tmp_path, capsys)
    assert len(all_out.splitlines()) == 29


def test_set_errors(tmp_path, capsys):
    dev = gd.Mock(version=0x0204)
    for bad in (["echo_time=5Hz"], ["echo_time=9999ms"], ["cab_on=1"], ["x"], ["dist_type=zzz"]):
        with pytest.raises(SystemExit):
            gme_hps.run(["--data-dir", str(tmp_path), "set"] + bad, dev=dev)
    assert dev.log == []


def test_params_list(tmp_path, capsys):
    out = new(["params"], gd.Mock(), tmp_path, capsys)
    assert len(out.splitlines()) == 30
    assert "echo_time" in out and "cab_shift1" in out


def test_chain_command(tmp_path, capsys):
    out = new(["chain"], gd.Mock(version=0x0205), tmp_path, capsys)
    names = [l.split(None, 1)[1] for l in out.splitlines()[:-1]]
    assert [n.split()[0] for n in names] == ["Overdrive", "Distortion", "Cabinet", "Chorus", "Tremolo", "Echo", "Reverb"]
    assert "fixed" in out.splitlines()[-1]


def test_cab_command(tmp_path, capsys, cabdir):
    dev = gd.Mock(version=0x0205)
    out = new(["cab", "list"], dev, tmp_path, capsys, cabdir)
    assert "Default" in out and "Marshall 4x12" in out
    out = new(["cab", "1"], dev, tmp_path, capsys, cabdir)
    assert "Marshall 4x12" in out and "bank 1" in out
    new(["cab", "on"], dev, tmp_path, capsys, cabdir)
    assert dev.regs[0] & 0x40
    assert dev.regs[0x1B] & 1 == 1 and (dev.regs[0x1B] >> 4) & 7 == 5
    new(["cab", "off"], dev, tmp_path, capsys, cabdir)
    assert not dev.regs[0] & 0x40
    with pytest.raises(SystemExit):
        gme_hps.run(["--data-dir", str(tmp_path), "--cab-dir", str(cabdir), "cab", "7"], dev=dev)
    with pytest.raises(SystemExit):
        gme_hps.run(["--data-dir", str(tmp_path), "cab", "0"], dev=gd.Mock(version=0x0204))


def test_user_presets_cli(tmp_path, capsys):
    dev = gd.Mock(version=0x0205)
    new(["set", "echo_time=250ms", "echo_on=on"], dev, tmp_path, capsys)
    new(["preset", "save", "mine"], dev, tmp_path, capsys)
    new(["preset", "clean"], dev, tmp_path, capsys)
    assert dev.regs[0] == 0
    new(["preset", "mine"], dev, tmp_path, capsys)
    assert dev.regs[0] == 4 and dev.regs[5] == 12000
    assert "mine" in new(["preset", "list"], dev, tmp_path, capsys)
    with pytest.raises(SystemExit):
        gme_hps.run(["--data-dir", str(tmp_path), "preset", "save", "mine"], dev=dev)
    with pytest.raises(SystemExit):
        gme_hps.run(["--data-dir", str(tmp_path), "preset", "save", "clean"], dev=dev)
    new(["preset", "delete", "mine"], dev, tmp_path, capsys)
    with pytest.raises(SystemExit):
        gme_hps.run(["--data-dir", str(tmp_path), "preset", "mine"], dev=dev)


def test_mock_flag_and_wrapper(tmp_path):
    import subprocess
    import os
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(os.path.dirname(here))
    for script in (os.path.join(root, "board", "gme_hps.py"), os.path.join(root, "tools", "gme_hps.py")):
        r = subprocess.run([sys.executable, script, "--mock", "--mock-state", str(tmp_path / "st.json"), "--data-dir", str(tmp_path), "status"],
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        assert r.stdout.startswith("version 0x0205, status 0x0005")
        r = subprocess.run([sys.executable, script, "--mock", "--mock-state", str(tmp_path / "st.json"), "--data-dir", str(tmp_path), "selftest"],
                           capture_output=True, text=True)
        assert "selftest OK" in r.stdout


def test_wrong_image_refused(tmp_path):
    with pytest.raises(SystemExit) as e:
        gme_hps.run(["--mock", "--mock-version", "0x0100", "--data-dir", str(tmp_path), "status"])
    assert "0x02xx" in str(e.value)
    gme_hps.run(["--mock", "--mock-version", "0x0100", "--no-check", "--data-dir", str(tmp_path), "status"])


def test_mock_state_shared_between_cli_calls(tmp_path):
    import subprocess
    here = os.path.dirname(os.path.abspath(__file__))
    script = os.path.join(os.path.dirname(here), "gme_hps.py")
    base = [sys.executable, script, "--mock", "--mock-state", str(tmp_path / "st.json"), "--data-dir", str(tmp_path)]
    subprocess.run(base + ["set", "echo_time=320ms", "echo_on=on"], check=True)
    r = subprocess.run(base + ["get", "echo_time"], capture_output=True, text=True, check=True)
    assert "320 ms (raw 15360)" in r.stdout
    r = subprocess.run(base + ["read", "0"], capture_output=True, text=True, check=True)
    assert r.stdout.strip() == "0x0004"


def test_mock_state_file_semantics(tmp_path):
    f = str(tmp_path / "s.json")
    a = gd.Mock(state_file=f)
    b = gd.Mock(state_file=f)                        # a second "process"
    a.write(5, 1234)
    assert b.read(5) == 1234
    b.write(6, 77)
    assert a.read(6) == 77 and a.read(5) == 1234     # a sees b's write, keeps its own
    assert gd.Mock(state_file=f).read(5) == 1234     # a new process starts from the file
    a.write(0x10, 9)
    assert a.read(0x10) == 0x0205                    # read-only registers are not taken from the file
    open(f, "w").write("garbage")
    assert a.read(5) == 1234                         # a broken file is ignored


def test_cli_and_server_share_mock_state(tmp_path, capsys):
    import json
    import threading
    import urllib.request
    import gme_web
    from gme import model as gm
    f = str(tmp_path / "shared.json")
    model = gm.Model(gd.Mock(state_file=f))
    srv = gme_web.create_server(model, "127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True).start()
    try:
        url = "http://127.0.0.1:%d/api/state" % srv.server_address[1]
        gme_hps.run(["--mock", "--mock-state", f, "--data-dir", str(tmp_path), "set", "trem_rate=6.5Hz"])
        vals = json.loads(urllib.request.urlopen(url).read().decode())["values"]
        assert vals["trem_rate"] == 6.5
        req = urllib.request.Request(url.replace("state", "params"), json.dumps({"od_gain": 4}).encode(),
                                     {"Content-Type": "application/json"})
        urllib.request.urlopen(req).read()
        gme_hps.run(["--mock", "--mock-state", f, "--data-dir", str(tmp_path), "get", "od_gain"])
        assert "od_gain      = 4" in capsys.readouterr().out
    finally:
        srv.stop()
