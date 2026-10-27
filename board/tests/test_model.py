"""Cabinet loading, presets, codec, chain, store, Mock behaviour."""
import json
import os

import pytest

from conftest import make_coefs, write_cab
from gme import device as gd
from gme import model as gm
from gme.store import Store, StoreError


# ---- Mock ---------------------------------------------------------------------------------

def test_mock_readonly_registers():
    d = gd.Mock(version=0x0205)
    d.write(0x10, 0x1234)
    d.write(0x11, 7)
    d.write(0x12, 7)
    assert d.read(0x10) == 0x0205 and d.read(0x11) == 0x0005
    assert d.log == []


def test_mock_levels_move_and_mute():
    t = [0.0]
    d = gd.Mock(clock=lambda: t[0])
    seen = set()
    for i in range(10):
        t[0] = i * 0.13
        seen.add(d.read(0x12))
    assert len(seen) > 5
    assert all(0 <= v <= 32767 for v in seen)
    d.write(0x14, 2)
    assert d.read(0x13) == 0


def test_mock_control_and_codec_flags():
    d = gd.Mock()
    d.write(0x14, 3)
    assert d.regs[0x14] == 2                       # bit0 self-clearing
    assert d.read(0x15) & 1                        # re-init makes CODEC busy
    while d.read(0x15) & 1:
        pass
    d.write(0x15, (2 << 9) | 0x79)
    assert d.read(0x15) & 1 and not d.read(0x15) & 1
    assert d.codec_log == [(2, 0x79)]
    d.write(0x15, (3 << 9) | 1)
    d.write(0x15, (4 << 9) | 1)                    # dropped: still busy
    assert d.codec_log == [(2, 0x79), (3, 1)]
    assert d.read(0x15) & 4
    n = gd.Mock(nak=True)
    n.write(0x15, 5)
    assert n.read(0x15) & 2


def test_mock_cab_pointer_and_protection():
    d = gd.Mock(version=0x0205)
    d.write(0x1C, 1 << 11 | 5)                     # bank 1, tap 5 (bank 0 active)
    d.write(0x1D, 0xFFFF)
    d.write(0x1E, 3)                               # -1 as 18 bit
    d.write(0x1D, 0x0002)
    d.write(0x1E, 0)
    assert d.cab_coef(1, 5) == -1 and d.cab_coef(1, 6) == 2
    assert d.cab_ptr == (1 << 11) | 7
    d.write(0x1C, 3)                               # bank 0 = active: ignored
    d.write(0x1D, 9)
    d.write(0x1E, 0)
    assert d.cab_mem[0][3] == 0 and d.cab_ignored_writes == 1
    assert d.cab_ptr == 4
    d.write(0x1B, 1)                               # switch to bank 1: now bank 0 writable
    d.write(0x1C, 3)
    d.write(0x1D, 9)
    d.write(0x1E, 0)
    assert d.cab_mem[0][3] == 9


def test_mock_old_image_has_no_cab_logic():
    d = gd.Mock(version=0x0204)
    d.write(0x1C, 0x123)
    assert d.read(0x1C) == 0x123 and d.cab_ptr == 0


def test_mock_unknown_addresses():
    d = gd.Mock()
    d.write(0x30, 5)
    assert d.read(0x30) == 0
    d.write(0x2F, 5)
    assert d.read(0x2F) == 5
    with pytest.raises(gd.DeviceError):
        d.read(64)


# ---- cabinet ------------------------------------------------------------------------------

def test_cab_load_register_sequence(model, mock, cabdir):
    coefs = make_coefs(1)
    r = model.cab_load(0)
    assert r == {"slot": 0, "name": "Default", "shift": 3, "bank": 1}
    log = [e for e in mock.log]
    assert log[0] == (0x1C, 1 << 11)                                  # pointer: inactive bank 1
    data = log[1:1 + 2 * 2048]
    assert [a for a, _ in data] == [0x1D, 0x1E] * 2048
    for i, c in enumerate(coefs):
        v = c & 0x3FFFF
        assert data[2 * i] == (0x1D, v & 0xFFFF)
        assert data[2 * i + 1] == (0x1E, v >> 16)
    assert log[1 + 2 * 2048:] == [(0x1B, 3 << 4), (0x1B, (3 << 4) | 1)]   # shift of bank 1, then switch
    assert mock.cab_ignored_writes == 0
    for i in (0, 1, 2, 500, 2047):
        assert mock.cab_coef(1, i) == coefs[i]
    assert mock.cab_coef(0, 0) == 0
    assert model.get_raw("cab_bank") == 1 and model.get_raw("cab_shift1") == 3
    # second load goes into bank 0 and switches back
    r = model.cab_load(1)
    assert r["bank"] == 0 and r["shift"] == 5
    assert mock.cab_coef(0, 0) == -131072 and mock.cab_coef(0, 1) == 131071
    assert model.get_raw("cab_bank") == 0
    assert model.get_raw("cab_shift0") == 5 and model.get_raw("cab_shift1") == 3
    assert model.cab_slot == 1
    assert model.store.settings()["cab_slot"] == 1


def test_cab_resync_after_new_image(model, mock, cabdir, tmp_path):
    model.cab_load(1)
    # a new FPGA image: registers and coefficient banks back to power-up, settings.json still says slot 1
    fresh = gd.Mock(version=0x0208)
    m2 = gm.Model(fresh, store=Store(str(tmp_path / "data")), cab_dir=str(cabdir))
    assert m2.cab_slot == 1 and fresh.read(0x1B) & 1 == 0 and fresh.cab_coef(1, 0) == 0
    r = m2.cab_resync()
    assert r == {"slot": 1, "name": "Marshall 4x12", "shift": 5, "bank": 1}
    assert [fresh.cab_coef(1, i) for i in range(2048)] == make_coefs(2)
    assert m2.get_raw("cab_bank") == 1 and m2.get_raw("cab_shift1") == 5 and fresh.cab_ignored_writes == 0
    # already playing (server restart, same image): loaded into the other bank, the sound stays the same
    assert m2.cab_resync()["bank"] == 0 and [fresh.cab_coef(0, i) for i in range(2048)] == make_coefs(2)
    # nothing stored, or an image without the cabinet: no writes
    for m in (gm.Model(gd.Mock(version=0x0208), store=Store(str(tmp_path / "other")), cab_dir=str(cabdir)),
              gm.Model(gd.Mock(version=0x0204), store=Store(str(tmp_path / "data")), cab_dir=str(cabdir))):
        assert m.cab_resync() is None and m.dev.log == []
    # the stored slot's file is gone
    os.remove(str(cabdir / "cab01.coef"))
    with pytest.raises(gm.CabinetError):
        m2.cab_resync()


def test_cab_refuses_active_bank(model, mock):
    mock.write(0x1B, 1)                                  # bank 1 active
    n = len(mock.log)
    with pytest.raises(gm.CabinetError):
        model.cab_write_bank(1, [0] * 2048)
    assert len(mock.log) == n and mock.cab_ignored_writes == 0
    model.cab_write_bank(0, [5] * 2048)
    assert mock.cab_mem[0][100] == 5
    with pytest.raises(gm.CabinetError):
        model.cab_write_bank(0, [0] * 10)


def test_cab_list_and_errors(model, cabdir):
    assert [(c["slot"], c["name"], c["shift"]) for c in model.cab_list()] == [(0, "Default", 3), (1, "Marshall 4x12", 5)]
    with pytest.raises(gm.CabinetError):
        model.cab_load(5)
    write_cab(cabdir, 2, "short", 1, [1, 2, 3])
    write_cab(cabdir, 3, "big", 1, [200000] + [0] * 2047)
    write_cab(cabdir, 4, "shift", 9, [0] * 2048)
    for s in (2, 3, 4):
        with pytest.raises(gm.CabinetError):
            model.cab_load(s)
    assert model.cab_slot is None


def test_cab_not_in_old_image(cabdir):
    m = gm.Model(gd.Mock(version=0x0204), cab_dir=str(cabdir))
    assert m.cab_status()["available"] is False
    with pytest.raises(gm.CabinetError):
        m.cab_load(0)
    with pytest.raises(gm.CabinetError):
        m.cab_enable(True)


# ---- presets ------------------------------------------------------------------------------

def test_user_preset_roundtrip(model, mock):
    model.set({"echo_time": "250ms", "echo_on": True, "mod_fb": -50, "trem_wave": "Free square"})
    model.cab_load(1)
    saved = model.save_preset("my lead-1")
    assert saved["fx"] == ["echo"] and saved["params"]["echo_time"] == 12000 and saved["cab"] == 1
    assert "mod_fb" in saved["params"] and "mute" not in saved["params"]
    on_disk = json.load(open(os.path.join(model.store.preset_dir, "my lead-1.json")))
    assert on_disk["params"]["trem_wave"] == 11
    model.apply_preset("clean")
    assert mock.regs[0] == 0 and mock.regs[5] == 0
    model.cab_slot = None
    assert model.apply_preset("my lead-1") == []
    assert model.get_raw("echo_time") == 12000 and model.get_raw("echo_on") == 1
    assert model.cab_slot == 1
    names = [(p["name"], p["factory"]) for p in model.preset_list()]
    assert ("clean", True) in names and ("my lead-1", False) in names
    model.delete_preset("my lead-1")
    with pytest.raises(KeyError):
        model.get_preset("my lead-1")


def test_preset_rules(model):
    model.save_preset("a")
    with pytest.raises(gm.PresetExists):
        model.save_preset("a")
    model.save_preset("a", overwrite=True)
    with pytest.raises(gm.FactoryPreset):
        model.save_preset("clean", overwrite=True)
    with pytest.raises(gm.FactoryPreset):
        model.delete_preset("crunch")
    for bad in ("", "../x", "a/b", ".hidden", "x" * 41):
        with pytest.raises((gm.ParamError, StoreError)):
            model.save_preset(bad)
    with pytest.raises(KeyError):
        model.delete_preset("nope")


def test_bad_preset_content(model, mock):
    n = len(mock.log)
    for bad in ({"fx": [], "params": {"zzz": 1}}, {"fx": ["zz"], "params": {}},
                {"fx": [], "params": {"od_drive": 99999999}}, {"fx": [], "params": {"mute": 1}}):
        with pytest.raises(gm.ParamError):
            model.apply_preset(bad)
    assert len(mock.log) == n


def test_preset_on_older_image_skips_new_params():
    m = gm.Model(gd.Mock(version=0x0203))
    w = m.apply_preset("flanger")
    assert any("mod_base" in x for x in w)


def test_preset_keeps_mute_and_cab_bank(model, mock):
    model.cab_load(0)
    model.set({"mute": True})
    model.apply_preset("lead")
    assert model.get_raw("mute") == 1 and model.get_raw("cab_bank") == 1


# ---- codec --------------------------------------------------------------------------------

def test_codec_write(model, mock):
    model.codec_write(2, 0x79)
    model.codec_write(model.codec_reg("left_headphone_out"), 0x7F)
    assert mock.codec_log == [(2, 0x79), (2, 0x7F)]
    assert mock.regs[0x15] == (2 << 9) | 0x7F
    with pytest.raises(gm.ParamError):
        model.codec_write(128, 0)
    with pytest.raises(gm.ParamError):
        model.codec_write(0, 512)
    with pytest.raises(gd.DeviceError):
        gm.Model(gd.Mock(nak=True)).codec_write(0, 1)
    with pytest.raises(gm.ParamError):
        model.codec_reg("nope")


# ---- chain --------------------------------------------------------------------------------

def test_chain_not_editable(model):
    ch = model.chain()
    assert ch["editable"] is False
    assert [e["id"] for e in ch["effects"]] == ch["order"]
    with pytest.raises(gm.NotEditable):
        model.set_chain(ch["order"])


def test_chain_editable_when_routing_exists(model, monkeypatch):
    monkeypatch.setattr(gm, "ROUTING_VERSION", 0x0205)
    assert model.chain()["editable"] is True
    new = ["echo", "dyn", "od", "dist", "cab", "eq", "mod", "trem", "reverb"]
    assert model.set_chain(new)["order"] == new
    assert model.chain()["order"] == new
    assert model.store.settings()["chain"] == new
    for bad in (["od"], new + ["od"], "od", new[:-1] + ["zz"]):
        with pytest.raises(gm.ParamError):
            model.set_chain(bad)
    saved = model.capture_preset()
    assert saved["chain"] == new


def test_chain_members_and_presets(model):
    assert model.chain()["members"] == []                        # nothing saved, nothing on
    model.set({"dist_on": True, "reverb_on": True})
    assert model.chain()["members"] == ["dist", "reverb"]
    model.set_members(["dist", "reverb", "echo"])                # echo in the chain, bypassed
    ch = model.chain()
    assert ch["members"] == ["dist", "echo", "reverb"]                 # in chain order
    assert [e["id"] for e in ch["effects"] if e["member"] and not e["on"]] == ["echo"]
    model.save_preset("Bypassed")
    assert model.store.load_preset("Bypassed")["members"] == ["dist", "echo", "reverb"]
    model.set_members(["dist"])                                  # reverb out: switched off
    assert model.enabled_effects() == ["dist"]
    model.apply_preset(model.get_preset("Bypassed"))
    assert model.chain()["members"] == ["dist", "echo", "reverb"] and model.enabled_effects() == ["dist", "reverb"]
    name = [n for n in model.table.presets][0]                   # a factory preset: the chain = its effects
    model.apply_preset(model.get_preset(name))
    assert model.chain()["members"] == [i for i in model.chain()["order"] if i in model.enabled_effects()]
    for bad in (["zz"], ["od", "od"], "od"):
        with pytest.raises(gm.ParamError):
            model.set_members(bad)


# ---- store --------------------------------------------------------------------------------

def test_store_files(tmp_path):
    s = Store(str(tmp_path / "d"))
    assert s.list_presets() == [] and s.settings() == {}
    s.save_preset("B", {"x": 1})
    s.save_preset("a", {"x": 2})
    assert s.list_presets() == ["a", "B"]
    assert s.load_preset("a") == {"x": 2}
    s.update_settings(k=1)
    s.update_settings(j=2)
    assert s.settings() == {"k": 1, "j": 2}
    s.delete_preset("a")
    assert s.list_presets() == ["B"]
    assert sorted(os.listdir(str(tmp_path / "d" / "presets"))) == ["B.json"]


def test_default_cab_dir(tmp_path):
    board = tmp_path / "board"
    board.mkdir()
    data = str(tmp_path / "data")
    assert gm.default_cab_dir(data, mock=True, board_dir=str(board)) == os.path.join(data, "cab")
    build = tmp_path / "ir" / "build"
    build.mkdir(parents=True)
    (build / "readme.txt").write_text("x")
    assert gm.default_cab_dir(data, mock=True, board_dir=str(board)) == os.path.join(data, "cab")
    (build / "cab00.coef").write_text("n\n0\n")
    assert os.path.normpath(gm.default_cab_dir(data, mock=True, board_dir=str(board))) == str(build)
    assert gm.default_cab_dir(data, mock=False, board_dir=str(board)) == os.path.join(data, "cab")


def test_coef_format_of_cab_coefs_py(tmp_path, mock):
    """Exactly what tools/cab_coefs.py write_coef() writes on main: name, shift, one coefficient per line."""
    coefs = make_coefs(7)
    p = tmp_path / "cab03.coef"
    with open(str(p), "w", newline="\n") as f:
        f.write("%s\n%d\n" % ("Default (generated)", 3))
        f.write("\n".join(str(int(c)) for c in coefs) + "\n")
    name, shift, got = gm.Model.read_coef_file(str(p))
    assert (name, shift, got) == ("Default (generated)", 3, coefs)
    m = gm.Model(mock, cab_dir=str(tmp_path))
    assert m.cab_load(3)["name"] == "Default (generated)"
    # CRLF line endings (file copied through Windows) are fine too
    p.write_bytes(p.read_bytes().replace(b"\n", b"\r\n"))
    assert gm.Model.read_coef_file(str(p))[2] == coefs
