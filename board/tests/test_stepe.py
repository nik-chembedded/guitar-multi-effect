"""Step E (VERSION 0x0209): effect order selectable at run time - Mock routing registers, Model.set_chain /
chain / chain_resync, presets, CLI, API and server start."""
import pytest

import gme_hps
from gme import device as gd
from gme import model as gm
from gme.store import Store
from test_api import start, err, run_main_once

DEFAULT = ["dyn", "od", "dist", "cab", "eq", "mod", "trem", "echo", "reverb"]
ID = {"od": 0, "trem": 1, "echo": 2, "dist": 3, "mod": 4, "reverb": 5, "cab": 6, "dyn": 7, "eq": 8}
REVERSED = DEFAULT[::-1]


def words(order):
    n = [ID[x] for x in order] + [0, 0, 0]
    return [sum(n[4 * w + k] << (4 * k) for k in range(4)) for w in range(3)]


def fresh(version=0x0209, tmp_path=None, **kw):
    dev = gd.Mock(version=version, **kw)
    return dev, gm.Model(dev, store=Store(str(tmp_path)) if tmp_path is not None else None)


# ---- Mock registers ------------------------------------------------------------------------

def test_encoding_of_the_default_order_is_the_reset_value():
    assert words(DEFAULT) == [0x6307, 0x2148, 0x0005]
    d = gd.Mock()
    assert [d.read(r) for r in (0x30, 0x31, 0x32, 0x33)] == [0x6307, 0x2148, 0x0005, 0]
    assert d.chain_active == [ID[x] for x in DEFAULT]


def test_mock_chain_shadow_readback_and_apply():
    d = gd.Mock()
    w = words(REVERSED)
    for i, v in enumerate(w):
        d.write(0x30 + i, v)
    assert [d.read(0x30), d.read(0x31), d.read(0x32)] == w
    assert d.chain_active == [ID[x] for x in DEFAULT]       # not active before the apply
    d.write(0x33, 1)
    assert d.chain_active == [ID[x] for x in REVERSED] and d.chain_applies == 1
    assert d.read(0x33) & 2 == 0
    d.write(0x32, 0xFFF5)                                   # slot 8 is 4 bits wide
    assert d.read(0x32) == 5


def test_mock_chain_reject_keeps_the_order():
    d = gd.Mock()
    d.write(0x30, 0x0000)                                   # not a permutation
    d.write(0x33, 0)
    assert d.read(0x33) & 2 and d.chain_applies == 0
    assert d.chain_active == [ID[x] for x in DEFAULT]
    d.write(0x30, 0x6307)                                   # fixed again: a valid apply clears the bit
    d.write(0x33, 0)
    assert d.read(0x33) & 2 == 0 and d.chain_applies == 1


def test_mock_chain_busy_for_255_frames():
    t = [10.0]
    d = gd.Mock(clock=lambda: t[0])
    assert d.read(0x33) == 0
    d.write(0x33, 1)
    assert d.read(0x33) & 1 == 1
    t[0] += 0.005
    assert d.read(0x33) & 1 == 1
    t[0] += 0.0004                                          # 255 frames = 5.31 ms
    assert d.read(0x33) & 1 == 0
    d.write(0x33, 1)                                        # an apply during the fade is accepted, the newest wins
    t[0] += 0.001
    for i, v in enumerate(words(REVERSED)):
        d.write(0x30 + i, v)
    d.write(0x33, 1)
    assert d.chain_active == [ID[x] for x in REVERSED] and d.read(0x33) & 1 == 1


@pytest.mark.parametrize("version", [0x0207, 0x0208])
def test_mock_routing_registers_ignored_on_older_images(version):
    d = gd.Mock(version=version)
    n = len(d.log)
    for r in (0x30, 0x31, 0x32, 0x33):
        d.write(r, 0x1234)
        assert d.read(r) == 0
    assert len(d.log) == n and d.chain_applies == 0


def test_mock_chain_registers_shared_through_the_state_file(tmp_path):
    f = str(tmp_path / "s.json")
    a, b = gd.Mock(state_file=f), gd.Mock(state_file=f)
    a.write(0x30, 0x1234)
    assert b.read(0x30) == 0x1234


# ---- Model.set_chain / chain -----------------------------------------------------------------

def test_set_chain_register_sequence_and_encoding(tmp_path):
    dev, m = fresh(tmp_path=tmp_path)
    n = len(dev.log)
    r = m.set_chain(REVERSED)
    assert dev.log[n:] == [(0x30, words(REVERSED)[0]), (0x31, words(REVERSED)[1]),
                           (0x32, words(REVERSED)[2]), (0x33, 1)]
    assert dev.chain_active == [ID[x] for x in REVERSED]
    assert r["order"] == REVERSED and r["editable"] is True
    assert m.store.settings()["chain"] == REVERSED


def test_set_chain_validation_writes_nothing(tmp_path):
    dev, m = fresh(tmp_path=tmp_path)
    n = len(dev.log)
    for bad in (DEFAULT[:-1], DEFAULT + ["od"], ["od"] * 9, DEFAULT[:-1] + ["nope"], "od", None):
        with pytest.raises(gm.ParamError):
            m.set_chain(bad)
    assert len(dev.log) == n and "chain" not in m.store.settings()


def test_set_chain_raises_when_the_fpga_rejects(tmp_path, monkeypatch):
    dev, m = fresh(tmp_path=tmp_path)
    monkeypatch.setattr(m, "_chain_encode", lambda order: [0, 0, 0])      # a bug on the Python side
    with pytest.raises(gm.ParamError, match="rejected"):
        m.set_chain(REVERSED)
    assert "chain" not in m.store.settings()


def test_set_chain_not_editable_on_0x0208(tmp_path):
    dev, m = fresh(0x0208, tmp_path)
    with pytest.raises(gm.NotEditable):
        m.set_chain(REVERSED)
    assert m.chain()["editable"] is False and m.chain()["order"] == DEFAULT


def test_chain_follows_the_hardware(tmp_path):
    dev, m = fresh(tmp_path=tmp_path)
    assert m.chain()["order"] == DEFAULT and m.chain()["editable"] is True
    m.store.update_settings(chain=REVERSED)                 # settings say reversed, the FPGA says default
    assert m.chain()["order"] == DEFAULT
    for i, v in enumerate(words(REVERSED)):                  # another client wrote the shadow registers
        dev.write(0x30 + i, v)
    assert m.chain()["order"] == REVERSED
    assert [e["id"] for e in m.chain()["effects"]] == REVERSED


def test_chain_falls_back_to_settings_then_default(tmp_path):
    dev, m = fresh(tmp_path=tmp_path)
    dev.write(0x30, 0xFFFF)                                  # no permutation
    assert m.chain()["order"] == DEFAULT
    m.store.update_settings(chain=REVERSED)
    assert m.chain()["order"] == REVERSED
    m.store.update_settings(chain=["od", "od"])              # invalid settings as well
    assert m.chain()["order"] == DEFAULT
    dev.write(0x30, 0x6307)
    dev.regs[0x32] = 0x00F5                                  # slot 8 out of range (not reachable through write)
    assert m.chain()["order"] == DEFAULT
    nostore = gm.Model(gd.Mock())
    nostore.dev.write(0x30, 0)
    assert nostore.chain()["order"] == DEFAULT


# ---- chain_resync ----------------------------------------------------------------------------

def test_chain_resync_on_a_fresh_fpga(tmp_path):
    Store(str(tmp_path)).update_settings(chain=REVERSED)
    dev, m = fresh(tmp_path=tmp_path)                         # freshly programmed: default order
    assert m.chain()["order"] == DEFAULT
    assert m.chain_resync() is True
    assert dev.chain_active == [ID[x] for x in REVERSED] and m.chain()["order"] == REVERSED
    n = len(dev.log)
    assert m.chain_resync() is False and len(dev.log) == n    # already there: no needless fade


def test_chain_resync_nothing_to_do(tmp_path):
    dev, m = fresh(tmp_path=tmp_path)
    assert m.chain_resync() is False and dev.chain_applies == 0           # nothing stored
    old_dev, old = fresh(0x0208, tmp_path)
    old.store.update_settings(chain=REVERSED)
    assert old.chain_resync() is False and old_dev.log == []
    m.store.update_settings(chain=["od"])                      # stale settings (not all effects)
    assert m.chain_resync() is False and dev.chain_applies == 0
    assert gm.Model(gd.Mock()).chain_resync() is False         # no store


# ---- presets ---------------------------------------------------------------------------------

def test_preset_round_trips_the_order_into_the_registers(tmp_path):
    dev, m = fresh(tmp_path=tmp_path)
    m.set_chain(REVERSED)
    saved = m.save_preset("rev")
    assert saved["chain"] == REVERSED
    m.set_chain(DEFAULT)
    assert [dev.read(r) for r in (0x30, 0x31, 0x32)] == words(DEFAULT)
    assert m.apply_preset("rev") == []
    assert [dev.read(r) for r in (0x30, 0x31, 0x32)] == words(REVERSED)
    assert dev.chain_active == [ID[x] for x in REVERSED] and m.chain()["order"] == REVERSED


def test_preset_without_order_keeps_it_and_old_image_ignores_it(tmp_path):
    dev, m = fresh(tmp_path=tmp_path)
    m.set_chain(REVERSED)
    assert m.apply_preset("crunch") == []                      # factory presets carry no order
    assert m.chain()["order"] == REVERSED
    dev8, m8 = fresh(0x0208, tmp_path / "o")
    assert m8.apply_preset({"fx": [], "params": {}, "chain": REVERSED}) == []
    assert dev8.chain_applies == 0


def test_bad_order_in_a_preset_is_a_warning(tmp_path):
    dev, m = fresh(tmp_path=tmp_path)
    w = m.apply_preset({"fx": [], "params": {}, "chain": ["od", "dyn"]})
    assert len(w) == 1 and w[0].startswith("chain:") and m.chain()["order"] == DEFAULT


# ---- CLI -------------------------------------------------------------------------------------

def cli(argv, dev, tmp_path, capsys):
    gme_hps.run(["--data-dir", str(tmp_path)] + argv, dev=dev)
    return capsys.readouterr().out


def test_cli_chain_show_set_reset(tmp_path, capsys):
    dev = gd.Mock()
    out = cli(["chain"], dev, tmp_path, capsys)
    assert [l.split()[1] for l in out.splitlines()[:2]] == ["Dynamics", "Overdrive"]
    assert out.splitlines()[-1] == "order editable"
    out = cli(["chain"] + [x.upper() for x in REVERSED], dev, tmp_path, capsys)
    assert dev.chain_active == [ID[x] for x in REVERSED]
    assert out.splitlines()[0].split()[1] == "Reverb"
    out = cli(["chain"], dev, tmp_path, capsys)                # read from the FPGA
    assert out.splitlines()[0].split()[1] == "Reverb"
    out = cli(["chain", "reset"], dev, tmp_path, capsys)
    assert dev.chain_active == [ID[x] for x in DEFAULT] and out.splitlines()[0].split()[1] == "Dynamics"
    cli(["chain", "chorus", "dyn", "od", "dist", "cab", "eq", "trem", "echo", "reverb"], dev, tmp_path, capsys)
    assert dev.chain_active[0] == ID["mod"]


def test_cli_chain_errors(tmp_path, capsys):
    dev = gd.Mock()
    with pytest.raises(SystemExit, match="unknown effect"):
        cli(["chain", "fuzz"] + DEFAULT[1:], dev, tmp_path, capsys)
    with pytest.raises(SystemExit, match="every effect"):
        cli(["chain", "od", "dyn"], dev, tmp_path, capsys)
    assert dev.chain_applies == 0
    old = gd.Mock(version=0x0208)
    with pytest.raises(SystemExit, match="fixed"):
        cli(["chain"] + REVERSED, old, tmp_path, capsys)
    assert "fixed (FPGA VERSION 0208)" in cli(["chain"], old, tmp_path, capsys)
    with pytest.raises(SystemExit, match="fixed"):
        cli(["chain", "reset"], old, tmp_path, capsys)


# ---- API -------------------------------------------------------------------------------------

def test_api_chain_editable_at_0x0209(tmp_path, cabdir):
    srv, dev, model, cl = start(0x0209, tmp_path, cabdir)
    try:
        s, j = cl.get("/api/chain")
        assert s == 200 and j["editable"] is True and j["order"] == DEFAULT
        assert cl.get("/api/info")[1]["capabilities"]["chain_editable"] is True
        s, j = cl.post("/api/chain", {"order": REVERSED})
        assert s == 200 and j["order"] == REVERSED
        assert dev.chain_active == [ID[x] for x in REVERSED]
        assert cl.get("/api/chain")[1]["order"] == REVERSED
        assert cl.get("/api/state")[1]["chain"]["order"] == REVERSED
        err(cl.post("/api/chain", {"order": REVERSED[:-1]}), 400)
        err(cl.post("/api/chain", {"order": ["od"] * 9}), 400)
        err(cl.post("/api/chain", {"order": "od"}), 400)
        assert dev.chain_applies == 1
        s, j = cl.post("/api/chain", {"order": DEFAULT, "members": ["od", "dist"]})
        assert s == 200 and j["order"] == DEFAULT and j["members"] == ["od", "dist"]
    finally:
        srv.stop()


def test_api_chain_409_on_0x0208(tmp_path, cabdir):
    srv, dev, model, cl = start(0x0208, tmp_path, cabdir)
    try:
        assert cl.get("/api/chain")[1]["editable"] is False
        err(cl.post("/api/chain", {"order": REVERSED}), 409)
    finally:
        srv.stop()


# ---- server start ----------------------------------------------------------------------------

def test_server_start_restores_the_stored_order(monkeypatch, capsys, tmp_path):
    data = tmp_path / "data"
    Store(str(data)).update_settings(chain=REVERSED)
    nocab = str(tmp_path / "nocab")
    model = run_main_once(monkeypatch, ["--mock", "--port", "0", "--data-dir", str(data), "--cab-dir", nocab])
    assert "effect order restored from settings.json" in capsys.readouterr().out
    assert model.dev.chain_active == [ID[x] for x in REVERSED] and model.chain()["order"] == REVERSED
    # nothing stored: no message, no apply
    model = run_main_once(monkeypatch, ["--mock", "--port", "0", "--data-dir", str(tmp_path / "d2"), "--cab-dir", nocab])
    assert "effect order" not in capsys.readouterr().out and model.dev.chain_applies == 0
    # an older image: the stored order is left alone
    run_main_once(monkeypatch, ["--mock", "--mock-version", "0x0208", "--port", "0", "--data-dir", str(data),
                                "--cab-dir", nocab])
    assert "effect order" not in capsys.readouterr().out
