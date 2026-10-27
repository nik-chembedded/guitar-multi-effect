"""The library CLI (board/gme_hps.py): commands beyond the old tool, options, mock state, dynamics, EQ, levels.
Parity with the old tool is in test_cli_parity.py."""
import os
import sys

import pytest

import gme_hps
from gme import device as gd
from gme import model as gm


def seeded_mock(version=0x0208):
    t = [0.37]
    dev = gd.Mock(version=version, clock=lambda: t[0])
    dev.t0 = 0.0
    return dev


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
    assert len(out.splitlines()) == 47
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
        assert r.stdout.startswith("version 0x0209, status 0x0005")
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
    assert a.read(0x10) == 0x0209                    # read-only registers are not taken from the file
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
