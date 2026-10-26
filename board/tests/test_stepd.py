"""Step D in the library, the Mock, the API and the page: dynamics, EQ, output levels, reverb size / damp,
the new chain order.  (Parity with the old command line is in test_cli_parity.py.)"""
import importlib.util
import json
import os

import pytest

from conftest import REPO, BOARD
from test_api import start, err, api, old_api, read_events      # noqa: F401  (fixtures)
from gme import device as gd
from gme import model as gm
from gme.store import Store

T = gm.load_table()


def tools_eq():
    spec = importlib.util.spec_from_file_location("eq_coefs_tools", os.path.join(REPO, "tools", "eq_coefs.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def m_store(tmp_path):
    dev = gd.Mock(version=0x0208)
    return gm.Model(dev, store=Store(str(tmp_path / "data"))), dev


# ---- Mock: EQ port, DYN_GR, versions ----------------------------------------------------------------------

def test_mock_eq_port_pointer_autoincrement_and_apply():
    d = gd.Mock(version=0x0208)
    d.write(0x28, 14)                                   # pointer at word 14
    for lo, hi in ((0x1234, 1), (0xFFFF, 3), (0x0007, 0)):
        d.write(0x29, lo)
        d.write(0x2A, hi)
    assert d.eq_shadow[14] == (1 << 16) | 0x1234 and d.eq_shadow[15] == 0x3FFFF
    assert d.eq_shadow[0] == 7                          # 15 wraps to 0
    assert d.eq_ptr == 1
    assert d.eq_active == [0] * 16 and d.eq_applies == 0     # nothing is active before EQ_APPLY
    d.write(0x2B, 0)                                    # any write applies
    assert d.eq_active == d.eq_shadow and d.eq_active is not d.eq_shadow and d.eq_applies == 1
    d.write(0x28, 0xFFF5)                               # only 4 bits of the pointer
    assert d.eq_ptr == 5 and d.read(0x28) == 5
    assert d.read(0x2A) == 0                            # HI reads back its 2 bits
    d.write(0x28, 0)
    d.write(0x29, 9)
    d.write(0x2A, 0)
    assert d.eq_active[0] == 7 and d.eq_shadow[0] == 9  # the active set changes only with the next apply


def test_mock_dyn_gr_is_a_read_only_meter():
    t = [0.0]
    d = gd.Mock(version=0x0208, clock=lambda: t[0])
    d.write(0x2C, 1234)
    assert d.read(0x2C) == 0 and d.log == []            # writes ignored
    # comp on, 4:1 above -40 dBFS, no make-up: moves with the input level
    d.write(0, 0x80)
    d.write(0x21, 2)
    d.write(0x23, (-1700) & 0xFFFF)
    d.write(0x24, 2)
    seen = []
    for i in range(12):
        t[0] = i * 0.17
        seen.append(d.read(0x2C))
    assert len(set(seen)) > 6 and max(seen) > 500 and all(0 <= v <= 0xFFFF for v in seen)
    t[0] = 0.37
    gr = d.read(0x2C)
    li = d.read(0x12)
    import math
    over = 20 * math.log10(li / 32768.0) + 1700 * 6.0206 / 256
    assert abs(gr / (256 / 6.0206) - over * 0.75) < 0.1             # reduction = over - over / 4
    d.write(0x27, 128)                                  # +6 dB make-up counts against it
    assert d.read(0x2C) < gr
    d.write(0x24, 4)                                    # infinite ratio: reduction = over
    d.write(0x27, 0)
    assert abs(d.read(0x2C) / (256 / 6.0206) - over) < 0.1
    d.write(0x21, 1)                                    # only the gate: no compressor reduction
    assert d.read(0x2C) == 0
    d.write(0x21, 2)
    d.write(0, 0)                                       # stage off: 0
    assert d.read(0x2C) == 0
    d.write(0, 0x80)
    d.write(0x23, 0)                                    # threshold at 0 dBFS: the signal is below
    assert d.read(0x2C) == 0


def test_mock_old_image_has_no_eq_or_dyn_logic():
    d = gd.Mock(version=0x0206)
    d.write(0x28, 7)
    d.write(0x2A, 3)
    d.write(0x2B, 1)
    d.write(0x2C, 99)
    assert d.eq_applies == 0 and d.read(0x2C) == 99 and d.read(0x28) == 7


def test_mock_default_version_and_cab_pointer_readback():
    d = gd.Mock()
    assert d.read(0x10) == 0x0208
    d.write(0x1C, 5)
    d.write(0x1D, 1)
    d.write(0x1E, 0)
    assert d.cab_ptr == 6 and d.read(0x1C) == 5         # reads back the value written, not the pointer
    d.write(0x2D, 0xFC04)
    d.write(0x2E, 512)
    assert d.read(0x2D) == 0xFC04 and d.read(0x2E) == 512
    d.write(0x1F, 60500)
    d.write(0x20, 30)
    assert (d.read(0x1F), d.read(0x20)) == (60500, 30)


# ---- units of the new parameters ---------------------------------------------------------------------------------

def test_units_of_step_d_parameters():
    p = T.param
    assert p("gate_thresh").parse("-45dB") == -1913 and p("gate_thresh").parse("-45") == -1913
    assert p("comp_thresh").parse("-20 dB") == -850 and p("comp_thresh").format(-850) == "-20 dB"
    assert p("comp_makeup").parse("+3") == 128 and p("comp_makeup").format(255) == "6 dB"
    assert p("od_level").parse("0") == 0 and p("od_level").parse("-24dB") == -1020 and p("od_level").parse("12") == 510
    assert p("od_level").format(512) == "12 dB" and p("dist_level").format(-1024) == "-24.1 dB"
    assert p("od_level").parse("-24.08") == -1024                    # within half a displayed step of the end
    for bad in ("13", "-25"):
        with pytest.raises(gm.ParamError):
            p("od_level").parse(bad)
    assert abs(p("od_level").to_display(-1020) + 23.9883) < 0.001    # dB = v * 6.0206 / 256
    assert p("comp_ratio").parse("4:1") == 2 and p("comp_ratio").parse("infinite") == 4 and p("comp_ratio").parse("8:1") == 3
    assert p("comp_ratio").to_display(6) == "Infinite (alias of 4 b)"
    # attack / release: the register holds k (2^k samples); the display is the effective time in ms
    a = p("comp_attack")
    assert a.to_display(0) == pytest.approx(1 / 48.0, abs=1e-6) and a.to_display(6) == pytest.approx(64 / 48.0, abs=1e-6)
    assert a.to_display(15) == pytest.approx(32768 / 48.0, abs=1e-6)
    assert a.parse("2ms") == 6 and a.parse("2") == 6 and a.parse("1.33") == 6 and a.parse("100ms") == 12
    assert a.parse("0.001") == 0 and a.parse("5000") == 15            # clamped like the old tool
    assert a.format(6) == "1.33 ms" and a.format(15) == "682.67 ms"
    assert a.from_display(a.to_display(9)) == 9
    assert p("comp_release").parse("250") == 13
    assert p("reverb_size").parse("60500", legacy_raw=True) == 60500
    assert p("reverb_size").format(60500) == "92.3 %" and p("reverb_damp").format(255) == "100 %"
    assert p("reverb_type").parse("custom") == 4 and p("reverb_type").format(4) == "Custom"
    # a register dump value of a signed field is read as its two's complement in the old command line
    assert p("od_level").parse("0xFC04", legacy_raw=True) == -1020 and p("comp_makeup").parse("0x0080", legacy_raw=True) == 128
    with pytest.raises(gm.ParamError):
        p("od_level").parse("0xFFFF0", legacy_raw=True)


def test_version_gating_of_step_d():
    cases = {0x0205: [], 0x0206: ["reverb_size", "reverb_damp"],
             0x0207: ["reverb_size", "reverb_damp", "dyn_on", "gate_on", "comp_on", "gate_thresh", "comp_thresh",
                      "comp_ratio", "comp_attack", "comp_release", "comp_makeup", "eq_on", "eq_bass", "eq_mid", "eq_treble"],
             0x0208: ["od_level", "dist_level"]}
    have = set()
    for v, ids in sorted(cases.items()):
        have |= set(ids)
        m = gm.Model(gd.Mock(version=v))
        got = set(p.id for p in m.params()) & set(sum(cases.values(), []))
        assert got == have, (hex(v), got ^ have)
    m = gm.Model(gd.Mock(version=0x0207))
    with pytest.raises(gm.ParamError):
        m.set({"od_level": -3})
    with pytest.raises(gm.ParamError):
        gm.Model(gd.Mock(version=0x0206)).set({"eq_bass": 3})
    with pytest.raises(gm.ParamError):
        gm.Model(gd.Mock(version=0x0205)).set({"reverb_type": "Custom"})
    gm.Model(gd.Mock(version=0x0206)).set({"reverb_type": "Custom"})


def test_dynamics_fields_share_registers_correctly():
    dev = gd.Mock(version=0x0208)
    m = gm.Model(dev)
    m.set({"gate_on": True, "comp_on": True, "dyn_on": True, "comp_ratio": "8:1", "comp_attack": "2ms", "comp_release": "100ms"})
    assert dev.regs[0] == 0x80 and dev.regs[0x21] == 3 and dev.regs[0x24] == 3 and dev.regs[0x25] == 6 and dev.regs[0x26] == 12
    m.set({"gate_on": False})
    assert dev.regs[0x21] == 2
    m.set({"gate_thresh": -45, "comp_thresh": -20, "comp_makeup": 3})
    assert (dev.regs[0x22], dev.regs[0x23], dev.regs[0x27]) == (-1913 & 0xFFFF, -850 & 0xFFFF, 128)
    assert m.get("gate_thresh") == pytest.approx(-44.9899, abs=1e-3) and m.get("comp_ratio") == "8:1"
    assert m.get("comp_attack") == pytest.approx(1.333333, abs=1e-5)
    m.set({"eq_on": True, "dyn_on": False})
    assert dev.regs[0] == 0x100


# ---- EQ in the model ---------------------------------------------------------------------------------------------------

def test_eq_set_writes_the_port_sequence_and_coefficients(m_store):
    m, dev = m_store
    ec = tools_eq()
    m.eq_set(6, -3, 2)
    exp = [ec.word18(v) for v in ec.coefficient_set_full(6, -3, 2)[0]] + [ec.scale_word(ec.coefficient_set_full(6, -3, 2)[1])]
    assert dev.log[0] == (0x28, 0) and len(dev.log) == 1 + 32 + 1
    for i, w in enumerate(exp):
        assert dev.log[1 + 2 * i] == (0x29, w & 0xFFFF) and dev.log[2 + 2 * i] == (0x2A, w >> 16)
    assert dev.log[-1] == (0x2B, 1)
    assert dev.eq_active == exp and dev.eq_applies == 1
    assert m.read(0) == 0                               # the EQ is not switched on by setting its gains
    assert m.eq_gains() == (6.0, -3.0, 2.0)
    assert m.store.settings()["eq"] == {"bass": 6.0, "mid": -3.0, "treble": 2.0}


def test_eq_flat_and_boost_words_and_every_section_on_its_own(m_store):
    m, dev = m_store
    ec = tools_eq()
    m.eq_set(0, 0, 0)
    assert dev.eq_active[0] == 65536 and dev.eq_active[5] == 65536 and dev.eq_active[10] == 65536 and dev.eq_active[15] == 0
    assert sum(dev.eq_active[1:5]) + sum(dev.eq_active[6:10]) + sum(dev.eq_active[11:15]) == 0
    for g in ((12, 12, 12), (-12, 12, -12)):
        full, shifts, _ = ec.coefficient_set_full(*g)
        want = [ec.word18(v) for v in full] + [ec.scale_word(shifts)]
        assert gm.Model.eq_words(*g) == want
    full, shifts, _ = ec.coefficient_set_full(0, 0, 12)
    assert shifts == [0, 0, 2] or shifts[2] > 0                   # the treble shelf needs a scale (b0 ~ 4)
    m.eq_set(treble=12)
    assert dev.eq_active[15] >> 4 == shifts[2]


def test_eq_limits_and_availability(m_store):
    m, dev = m_store
    n = len(dev.log)
    for bad in ((13, 0, 0), (0, -12.01, 0), (0, 0, 99)):
        with pytest.raises(gm.ParamError) as e:
            m.eq_set(*bad)
        assert "-12 .. +12" in str(e.value)
    with pytest.raises(gm.ParamError):
        m.set({"eq_mid": 12.5})
    assert len(dev.log) == n and m.eq_gains() == (0.0, 0.0, 0.0)
    m.eq_set(12, -12, 12)
    old = gm.Model(gd.Mock(version=0x0206))
    with pytest.raises(gm.ParamError) as e:
        old.eq_set(1, 2, 3)
    assert "0x0207" in str(e.value)
    assert old.eq_resync() is False


def test_eq_params_are_model_level_and_stored(m_store, tmp_path):
    m, dev = m_store
    out = m.set({"eq_bass": 6, "eq_treble": "-4.5dB"})
    assert out == {"eq_bass": 6.0, "eq_treble": -4.5}
    assert m.get_raw("eq_bass") == 60 and m.get_raw("eq_treble") == -45 and m.get_raw("eq_mid") == 0
    assert m.get("eq_treble") == -4.5
    assert dev.eq_applies == 1 and dev.regs[0] == 0                # one apply for the pair; the EQ is not switched on
    m.set_raw({"eq_mid": 25})
    assert m.eq_gains() == (6.0, 2.5, -4.5) and dev.eq_applies == 2
    st = m.state()
    assert st["values"]["eq_mid"] == 2.5 and st["raw"]["eq_mid"] == 25 and "eq_bass" in st["values"]
    # another process (the CLI) sees the same stored gains
    m2 = gm.Model(gd.Mock(version=0x0208), store=Store(str(tmp_path / "data")))
    assert m2.eq_gains() == (6.0, 2.5, -4.5) and m2.get_raw("eq_bass") == 60
    # the coefficients cannot be read back: resync after a restart / new image writes them again
    assert m2.eq_resync() is True and m2.dev.eq_active == dev.eq_active
    # without a store the gains live in the model
    m3 = gm.Model(gd.Mock(version=0x0208))
    m3.set({"eq_bass": 3})
    assert m3.eq_gains() == (3.0, 0.0, 0.0)
    assert gm.Model(gd.Mock(version=0x0208)).eq_resync() is False     # flat: nothing to restore


def test_eq_unit_roundtrip_and_rounding():
    p = T.param("eq_bass")
    for raw in (-120, -45, -1, 0, 1, 7, 120):
        assert p.from_display(p.to_display(raw)) == raw and p.parse(p.format(raw)) == raw
    assert p.parse("2.55") == 26 and p.parse("-12dB") == -120 and p.format(25) == "2.5 dB"
    assert p.virtual == "eq" and p.reg is None


# ---- presets: dynamics, EQ, keep -----------------------------------------------------------------------------------------

def test_factory_presets_keep_cab_dyn_eq_and_their_settings(m_store):
    m, dev = m_store
    m.set({"dyn_on": True, "eq_on": True, "cab_on": True, "gate_on": True, "gate_thresh": -50, "comp_ratio": "2:1"})
    m.eq_set(3, 3, 3)
    applies = dev.eq_applies
    regs = dict((r, dev.regs[r]) for r in (0x1B, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27))
    for name in ("clean", "crunch", "lead", "ambient", "hall", "pulse"):
        m.apply_preset(name)
        assert dev.regs[0] & 0x1C0 == 0x1C0, name
        assert dict((r, dev.regs[r]) for r in regs) == regs, name
        assert m.eq_gains() == (3.0, 3.0, 3.0) and dev.eq_applies == applies
    m.apply_preset("hall")
    assert dev.regs[0] == 0x1C0 | 32 and (dev.regs[14], dev.regs[0x1F], dev.regs[0x20], dev.regs[13]) == (4, 60500, 30, 110)
    m.apply_preset("crunch")
    assert dev.regs[0x2E] == (-233) & 0xFFFF and dev.regs[0x2D] == 0 and dev.regs[0x1F] == 0 and dev.regs[0x20] == 0
    m.apply_preset("lead")
    assert dev.regs[0x2E] == (-544) & 0xFFFF


def test_user_preset_saves_and_restores_dynamics_and_eq(m_store):
    m, dev = m_store
    m.set({"dyn_on": True, "comp_on": True, "comp_thresh": -30, "comp_ratio": "4:1", "comp_attack": "5ms", "comp_makeup": 4,
           "od_level": -3, "dist_level": -6, "reverb_size": 70, "reverb_damp": 40})
    m.eq_set(2, -1.5, 4)
    saved = m.save_preset("full")
    assert "dyn" in saved["fx"] and saved["keep"] == [] if "keep" in saved else True
    for k in ("gate_on", "comp_thresh", "comp_ratio", "comp_attack", "comp_makeup", "eq_bass", "eq_mid", "eq_treble",
              "od_level", "dist_level", "reverb_size", "reverb_damp"):
        assert k in saved["params"], k
    assert saved["params"]["eq_mid"] == -15 and saved["params"]["reverb_size"] == 45875
    m.apply_preset("clean")
    m.set({"comp_on": False, "comp_thresh": -10})
    m.eq_set(0, 0, 0)
    want = m.read_all()
    assert m.apply_preset("full") == []
    assert m.read(0x23) == (T.param("comp_thresh").parse("-30") & 0xFFFF) and m.read(0x21) == 2
    assert m.eq_gains() == (2.0, -1.5, 4.0) and dev.eq_active == gm.Model.eq_words(2, -1.5, 4)
    assert m.get_raw("od_level") == -128 and m.get_raw("reverb_damp") == 102 and m.read(0) & 0x80
    assert m.read_all() != want
    # a user preset replaces the on/off state of the dynamics and EQ (no "keep")
    m.save_preset("plain", data={"fx": ["echo"], "params": {"echo_time": 100}, "chain": None, "cab": None})
    m.apply_preset("plain")
    assert m.read(0) == 4
    # old user presets (before step D, without dynamics) still load
    m.set({"gate_thresh": -60})
    m.apply_preset({"fx": ["dist"], "params": {"dist_mix": 100}, "cab": None, "chain": None})
    assert m.get_raw("gate_thresh") == T.param("gate_thresh").parse("-60")


def test_preset_on_image_without_dynamics_warns_not_fails():
    m = gm.Model(gd.Mock(version=0x0205))
    w = m.apply_preset({"fx": ["dyn", "eq", "dist"], "params": {"gate_thresh": -1913, "eq_bass": 30, "dist_mix": 9}, "cab": None, "chain": None})
    assert any("gate_thresh" in x for x in w) and any("eq_bass" in x for x in w) and any("effect dyn" in x for x in w)
    assert m.read(0) == 8 and m.read(8) == 9


def test_gain_reduction_and_levels():
    dev = gd.Mock(version=0x0208, clock=lambda: 0.37)
    dev.t0 = 0.0                                                     # input level -4 dBFS
    m = gm.Model(dev)
    assert m.gain_reduction() == 0.0 and m.levels()["gain_reduction"] == 0.0
    m.set({"dyn_on": True, "comp_on": True, "comp_thresh": -60, "comp_ratio": "Infinite"})
    lv = m.levels()
    assert lv["gain_reduction"] > 20 and m.status()["gain_reduction"] > 0
    old = gm.Model(gd.Mock(version=0x0206))
    assert old.levels()["gain_reduction"] is None and old.status()["gain_reduction"] is None


# ---- API ------------------------------------------------------------------------------------------------------------------------

def test_api_dynamics_and_levels_in_display_units(api):
    s, j = api.post("/api/params", {"dyn_on": True, "gate_on": True, "comp_on": True, "gate_thresh": "-45dB", "comp_thresh": -20,
                                    "comp_ratio": "4:1", "comp_attack": "2ms", "comp_release": 100, "comp_makeup": 3,
                                    "od_level": -3, "dist_level": "-6 dB", "reverb_type": "Custom", "reverb_size": 91.5,
                                    "reverb_damp": 12})
    assert s == 200, j
    d = api.dev
    assert d.regs[0] == 0x80 and d.regs[0x21] == 3 and d.regs[0x22] == (-1913 & 0xFFFF) and d.regs[0x23] == (-850 & 0xFFFF)
    assert d.regs[0x24] == 2 and d.regs[0x25] == 6 and d.regs[0x26] == 12 and d.regs[0x27] == 128
    assert d.regs[0x2D] == (-128 & 0xFFFF) and d.regs[0x2E] == (-255 & 0xFFFF)
    assert d.regs[14] == 4 and d.regs[0x1F] == 59965 and d.regs[0x20] == 31
    assert j["values"]["comp_ratio"] == "4:1" and j["values"]["comp_attack"] == pytest.approx(1.333333, abs=1e-5)
    s, st = api.get("/api/state")
    v = st["values"]
    assert v["gate_on"] is True and v["comp_on"] is True and v["comp_ratio"] == "4:1" and v["reverb_type"] == "Custom"
    assert v["od_level"] == pytest.approx(-3.0, abs=0.03) and st["raw"]["comp_release"] == 12
    assert [e["id"] for e in st["chain"]["effects"]][:2] == ["dyn", "od"] and st["chain"]["effects"][0]["on"] is True
    err(api.post("/api/params", {"comp_ratio": "5:1"}), 400)
    err(api.post("/api/params", {"od_level": 13}), 400)
    err(api.post("/api/params", {"comp_attack": "5Hz"}), 400)


def test_api_eq(api):
    ec = tools_eq()
    s, j = api.post("/api/params", {"eq_bass": 6, "eq_mid": -3, "eq_treble": 2, "eq_on": True})
    assert s == 200 and j["values"] == {"eq_bass": 6.0, "eq_mid": -3.0, "eq_treble": 2.0, "eq_on": True}
    d = api.dev
    full, shifts, _ = ec.coefficient_set_full(6, -3, 2)
    assert d.eq_active == [ec.word18(v) for v in full] + [ec.scale_word(shifts)] and d.eq_applies == 1
    assert d.regs[0] == 0x100
    s, st = api.get("/api/state")
    assert st["values"]["eq_bass"] == 6.0 and st["values"]["eq_mid"] == -3.0 and st["raw"]["eq_treble"] == 20
    assert api.model.store.settings()["eq"] == {"bass": 6.0, "mid": -3.0, "treble": 2.0}
    s, j = api.post("/api/params", {"eq_mid": "1.5dB"})
    assert j["values"] == {"eq_mid": 1.5} and d.eq_applies == 2
    n = len(d.log)
    err(api.post("/api/params", {"eq_bass": 12.5}), 400)
    err(api.post("/api/params", {"eq_bass": "loud"}), 400)
    err(api.post("/api/params", {"eq_bass": 3, "echo_time": "9999ms"}), 400)
    assert len(d.log) == n and api.model.eq_gains() == (6.0, 1.5, 2.0)
    s, info = api.get("/api/info")
    p = [x for x in info["params"] if x["id"] == "eq_bass"][0]
    assert p["virtual"] == "eq" and p["unit"] == "dB" and p["mul"] == 1 and p["div"] == 10 and p["gui_commit"] == "release"


def test_api_eq_not_in_old_image(tmp_path, cabdir):
    srv, dev, model, cl = start(0x0206, tmp_path, cabdir)
    try:
        err(cl.post("/api/params", {"eq_bass": 3}), 400)
        err(cl.post("/api/params", {"gate_on": True}), 400)
        s, j = cl.get("/api/levels")
        assert j["gain_reduction"] is None
        assert cl.get("/api/info")[1]["capabilities"]["eq"] is False
    finally:
        srv.stop()


def test_api_levels_carry_gain_reduction_also_in_the_stream(api):
    s, j = api.get("/api/levels")
    assert s == 200 and j["gain_reduction"] == 0.0
    api.post("/api/params", {"dyn_on": True, "comp_on": True, "comp_thresh": -100, "comp_ratio": "8:1"})
    s, j = api.get("/api/levels")
    assert j["gain_reduction"] > 10
    ev, _ = read_events(api.port, 6)
    assert all("gain_reduction" in e and e["gain_reduction"] >= 0 for e in ev)
    assert len(set(e["gain_reduction"] for e in ev)) > 1          # the meter moves with the input level
    s, st = api.get("/api/state")
    assert st["status"]["gain_reduction"] >= 0


def test_api_presets_keep_dynamics_and_eq(api):
    api.post("/api/params", {"dyn_on": True, "eq_on": True, "eq_bass": 4})
    s, j = api.post("/api/presets/crunch")
    assert s == 200 and api.dev.regs[0] == 0x180 | 8 | 32
    assert j["values"]["eq_bass"] == 4.0 and j["values"]["dyn_on"] is True
    api.post("/api/presets", {"name": "mine"})
    s, p = api.get("/api/presets/mine")
    assert p["params"]["eq_bass"] == 40 and "dyn" in p["fx"] and "eq" in p["fx"]
    api.post("/api/params", {"eq_bass": -2, "dyn_on": False})
    api.post("/api/presets/mine")
    assert api.model.eq_gains()[0] == 4.0 and api.dev.regs[0] & 0x80


def test_api_chain_order_follows_the_hardware(api):
    s, ch = api.get("/api/chain")
    assert ch["order"] == ["dyn", "od", "dist", "cab", "eq", "mod", "trem", "echo", "reverb"]
    assert [e["enable"] for e in ch["effects"]] == ["dyn_on", "od_on", "dist_on", "cab_on", "eq_on", "mod_on", "trem_on",
                                                    "echo_on", "reverb_on"]
    api.post("/api/params", {"dyn_on": True, "eq_on": True})
    assert [e["id"] for e in api.get("/api/chain")[1]["effects"] if e["on"]] == ["dyn", "eq"]
    s, info = api.get("/api/info")
    assert info["chain_default"] == ch["order"]
    bits = dict((e["id"], e["bit"]) for e in info["effects"])
    assert bits["dyn"] == 7 and bits["eq"] == 8 and bits["cab"] == 6
    s, raw = api.get("/api/raw")
    assert {0x1F, 0x20, 0x21, 0x27, 0x28, 0x2B, 0x2C, 0x2D, 0x2E} <= set(r["reg"] for r in raw["registers"])
    assert api.get("/api/raw/dyn_gr")[1]["reg"] == 0x2C and api.post("/api/raw/0x2C", {"value": 5})[1]["value"] != 5
    assert api.post("/api/raw/eq_apply", {"value": 1})[0] == 200


# ---- page ---------------------------------------------------------------------------------------------------------------------------

def test_page_knows_the_new_cards_and_scales():
    js = open(os.path.join(BOARD, "www", "app.js"), encoding="utf-8").read()
    ctl = open(os.path.join(BOARD, "www", "controls.js"), encoding="utf-8").read()
    css = open(os.path.join(BOARD, "www", "app.css"), encoding="utf-8").read()
    assert 'e.id === "dyn"' in js and "gr-bar" in js and "gain_reduction" in js and "GR_FULL_SCALE_DB" in js
    assert "grmeter" in css
    assert 'p.scale === "pow2"' in ctl and "gui_commit" in ctl and "min_version" in ctl
    assert "fpgaVersion" in js
    # the cards themselves come from the table: no parameter of the new effects is named in the page script
    for pid in ("gate_thresh", "comp_ratio", "eq_bass", "eq_mid", "eq_treble", "od_level", "reverb_size"):
        assert pid not in js and pid not in ctl, pid


def test_table_groups_of_the_new_cards():
    groups = {}
    for p in T.params:
        groups.setdefault(p.group, []).append(p.id)
    assert groups["dyn"] == ["dyn_on", "gate_on", "gate_thresh", "comp_on", "comp_thresh", "comp_ratio", "comp_attack",
                             "comp_release", "comp_makeup"]
    assert groups["eq"] == ["eq_on", "eq_bass", "eq_mid", "eq_treble"]
    assert "od_level" in groups["od"] and "dist_level" in groups["dist"]
    assert groups["od"][-1] == "od_level" or groups["od"].index("od_level") > groups["od"].index("od_gain")
    assert [p.group for p in T.params if p.id in ("reverb_size", "reverb_damp")] == ["reverb", "reverb"]
