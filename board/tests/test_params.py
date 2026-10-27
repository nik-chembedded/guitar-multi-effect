import os
import random
import re

import pytest

from conftest import REPO
from gme import model as gm
from gme import device as gd

T = gm.load_table()


def test_table_basics():
    ids = [p.id for p in T.params]
    assert len(ids) == len(set(ids))
    for p in T.params:
        assert p.type in ("int", "enum", "bool", "signed")
        assert p.min <= p.default <= p.max
        assert p.lsb + p.width <= 16
        assert p.help and p.name and p.group
        assert p.min_version >= 0x0201
        if p.virtual:                                  # kept by the model, no register field
            assert p.reg is None and p.width == 0
            continue
        assert max(abs(p.min), abs(p.max)) <= (1 << p.width) - 1 if p.type != "signed" \
            else max(abs(p.min), abs(p.max)) < (1 << (p.width - 1))
    # bit fields of one register do not overlap
    used = {}
    for p in T.params:
        for b in range(p.lsb, p.lsb + p.width):
            assert (p.reg, b) not in used, (p.id, used[(p.reg, b)])
            used[(p.reg, b)] = p.id
    groups = set(e["id"] for e in T.effects) | {"system"}
    assert set(p.group for p in T.params) <= groups
    for e in T.effects:
        assert T.by_id[e["enable"]].type == "bool"
        assert T.by_id[e["enable"]].reg == 0 and T.by_id[e["enable"]].lsb == e["bit"]


def sample_raws(p):
    rs = random.Random(sum(ord(c) for c in p.id))
    if p.type == "enum":
        return [e["value"] for e in p.enum]
    vals = set([p.min, p.max, p.default, (p.min + p.max) // 2])
    if p.min <= 0 <= p.max:
        vals.add(0)
    vals |= set(rs.randint(p.min, p.max) for _ in range(40))
    return sorted(vals)


@pytest.mark.parametrize("p", T.params, ids=lambda p: p.id)
def test_display_roundtrip(p):
    for raw in sample_raws(p):
        disp = p.to_display(raw)
        assert p.from_display(disp) == raw, (p.id, raw, disp)
        # as text, with the unit
        text = "%r%s" % (disp, p.unit) if p.has_unit else str(disp)
        assert p.parse(text) == raw, (p.id, raw, text)
        if p.has_unit:
            # the formatted text is rounded to `decimals`: within half a displayed step
            back = p.parse(p.format(raw))
            step = p.mul / p.div
            assert abs(back - raw) * step <= 0.5 * 10 ** (-p.decimals) + 1e-9, (p.id, raw, p.format(raw))


@pytest.mark.parametrize("p", T.params, ids=lambda p: p.id)
def test_register_roundtrip(p):
    dev = gd.Mock(version=0x0208)
    m = gm.Model(dev)
    # neighbours in shared registers must survive
    other = [q for q in T.params if q.reg == p.reg and q is not p and not q.virtual]
    for q in other:
        m.set_raw({q.id: q.max if q.type != "signed" else q.min})
    before = dict((q.id, m.get_raw(q.id)) for q in other)
    samples = sample_raws(p)
    if p.virtual:                                      # every change computes EQ coefficients (slow)
        samples = [p.min, p.max, 0, 7, -33]
    for raw in samples:
        m.set_raw({p.id: raw})
        assert m.get_raw(p.id) == raw
        assert m.get(p.id) == p.to_display(raw)
        m.set({p.id: p.to_display(raw)})
        assert m.get_raw(p.id) == raw
        assert dict((q.id, m.get_raw(q.id)) for q in other) == before


def test_units():
    p = T.param
    assert p("echo_time").parse("320ms") == 15360
    assert p("echo_time").to_display(14400) == 300
    assert p("echo_time").from_display(300) == 14400
    assert p("trem_rate").parse("6.5Hz") == 650
    assert p("trem_rate").parse("650", legacy_raw=True) == 650
    assert p("trem_rate").parse("6.5") == 650                    # bare number = display value
    assert p("trem_rate").from_display(6.5) == 650
    assert p("echo_repeat").parse("50%") == 128
    assert p("echo_repeat").parse("90", legacy_raw=True) == 90
    assert abs(p("mod_fb").to_display(-26000) + 79.3) < 0.1
    assert p("mod_fb").parse("-79.3%") == -25984
    assert p("trem_wave").parse("free square") == 11
    assert p("trem_wave").parse("Sine 7 Hz") == 1
    assert p("dist_type").parse("heavy") == 2
    assert p("reverb_type").parse("3") == 3
    assert p("mute").parse("on") == 1 and p("mute").parse("off") == 0
    assert p("echo_time").format(15360) == "320 ms"
    assert p("trem_rate").format(650) == "6.5 Hz"
    assert p("od_drive").parse("0x0BB8", legacy_raw=True) == 3000


def test_range_and_unit_errors():
    p = T.param
    with pytest.raises(gm.ParamError):
        p("echo_time").parse("1000ms")          # > 0.68 s
    with pytest.raises(gm.ParamError):
        p("echo_time").parse("5Hz")
    with pytest.raises(gm.ParamError):
        p("od_gain").parse("70000")
    with pytest.raises(gm.ParamError):
        p("dist_type").parse("nonsense")
    with pytest.raises(gm.ParamError):
        p("dist_type").from_display(7)
    with pytest.raises(gm.ParamError):
        p("mute").from_display("maybe")
    with pytest.raises(gm.ParamError):
        T.param("nope")


def test_version_gating():
    m = gm.Model(gd.Mock(version=0x0204))
    assert "cab_on" not in [p.id for p in m.params()]
    with pytest.raises(gm.ParamError):
        m.set({"cab_on": True})
    m = gm.Model(gd.Mock(version=0x0202))
    with pytest.raises(gm.ParamError):
        m.set({"mod_base": 10})
    assert "trem_rate" not in [p.id for p in m.params()]
    m = gm.Model(gd.Mock(version=0x0208))
    m.set({"cab_on": True})
    assert m.get_raw("cab_on") == 1 and m.read(0) == 0x40


def test_set_is_atomic_on_error():
    dev = gd.Mock(version=0x0208)
    m = gm.Model(dev)
    with pytest.raises(gm.ParamError):
        m.set({"od_drive": 1000, "echo_time": "5Hz"})
    assert dev.read(1) == 0 and dev.log == []


def parse_register_map():
    text = open(os.path.join(REPO, "docs", "register_map.md")).read()
    regs = {}
    for line in text.splitlines():
        m = re.match(r"^\|\s*(0x[0-9A-Fa-f]+|\d+)\s*\|\s*([^|]+?)\s*\|\s*([RW/]+)\s*\|", line)
        if m:
            regs[int(m.group(1), 0)] = (m.group(2), m.group(3))
    return regs


def test_table_covers_register_map():
    doc = parse_register_map()
    assert len(doc) >= 45, doc                      # the parser found the table
    assert {0, 14, 0x10, 0x15, 0x16, 0x18, 0x19, 0x1A, 0x1F, 0x21, 0x27, 0x28, 0x2B, 0x2C, 0x2D, 0x2E} <= set(doc)
    table_regs = dict((r["reg"], r) for r in T.registers)
    missing = sorted(set(doc) - set(table_regs))
    assert not missing, "registers in docs/register_map.md missing from params.json: %s" % missing
    # every writable register of the map is driven by at least one parameter, except the actions: codec
    # (Model.codec_write), the cabinet coefficient port (cab_load), the EQ coefficient port + apply
    # (eq_set); the read-only DYN_GR is the meter (Model.gain_reduction)
    param_regs = set(p.reg for p in T.params if not p.virtual)
    for reg, (name, rw) in doc.items():
        if "W" in rw and "action" not in table_regs[reg]:
            assert reg in param_regs, "register 0x%02X %s has no parameter" % (reg, name)
        assert table_regs[reg]["rw"] == rw, (reg, rw, table_regs[reg]["rw"])
    actions = dict((r["reg"], r["action"]) for r in T.registers if "action" in r)
    assert actions == {0x15: "codec", 0x1C: "cab", 0x1D: "cab", 0x1E: "cab", 0x28: "eq", 0x29: "eq", 0x2A: "eq",
                       0x2B: "eq", 0x2C: "meter",
                       0x30: "chain", 0x31: "chain", 0x32: "chain", 0x33: "chain"}
    assert set(r["min_version"] for r in T.registers if 0x30 <= r["reg"] <= 0x33) == {0x0209}
    # every bit of the effects register is a parameter
    assert set(p.lsb for p in T.params if p.reg == 0) == set(range(9))
    assert [r["min_version"] for r in T.registers if r["reg"] in (0x1F, 0x20)] == [0x0206, 0x0206]
    assert set(r["min_version"] for r in T.registers if 0x21 <= r["reg"] <= 0x2C) == {0x0207}
    assert set(r["min_version"] for r in T.registers if r["reg"] in (0x2D, 0x2E)) == {0x0208}
    assert T.by_id["dyn_on"].lsb == 7 and T.by_id["eq_on"].lsb == 8
    # the upcoming cabinet registers are present and version-gated
    for reg in (0x1B, 0x1C, 0x1D, 0x1E):
        assert table_regs[reg]["min_version"] == 0x0205
    assert T.by_id["cab_on"].reg == 0 and T.by_id["cab_on"].lsb == 6
    assert T.by_id["cab_shift0"].lsb == 1 and T.by_id["cab_shift0"].width == 3
    assert T.by_id["cab_shift1"].lsb == 4 and T.by_id["cab_shift1"].width == 3


def test_enum_labels_match_register_map():
    assert len(T.by_id["trem_wave"].enum) == 12
    assert [e["label"] for e in T.by_id["reverb_type"].enum] == ["Very light", "Light", "Medium", "Heavy", "Custom"]
    assert [e["label"] for e in T.by_id["comp_ratio"].enum if not e.get("alias")] == ["1:1", "2:1", "4:1", "8:1", "Infinite"]
    assert [e["value"] for e in T.by_id["comp_ratio"].enum] == list(range(8))
    assert T.by_id["mod_shape"].enum[1]["label"] == "Triangle"
    assert len(T.by_id["dist_type"].enum) == 4


def test_chain_default_order():
    m = gm.Model(gd.Mock(version=0x0208))
    assert m.chain()["order"] == ["dyn", "od", "dist", "cab", "eq", "mod", "trem", "echo", "reverb"]
    assert m.chain()["editable"] is False
    m = gm.Model(gd.Mock(version=0x0206))
    assert m.chain()["order"] == ["od", "dist", "cab", "mod", "trem", "echo", "reverb"]
    m = gm.Model(gd.Mock(version=0x0204))
    assert m.chain()["order"] == ["od", "dist", "mod", "trem", "echo", "reverb"]
