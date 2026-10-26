"""Parameter table, unit conversion and the high-level operations on the FPGA registers.

Display units <-> register values, presets, cabinets, codec writes, effect chain order.
One Model owns one device and serialises all hardware access with one lock.
Python 2.7 and 3 compatible, standard library only.
"""
from __future__ import print_function, division

import collections
import json
import math
import os
import re
import threading
import time

from . import device
from . import eq_coefs
from .device import (DeviceError, WrongImage, REG_VERSION, REG_STATUS, REG_LEVEL_IN, REG_LEVEL_OUT,
                     REG_CONTROL, REG_CODEC, REG_CAB_CTRL, REG_CAB_ADDR, REG_CAB_DATA_LO,
                     REG_CAB_DATA_HI, REG_EQ_ADDR, REG_EQ_DATA_LO, REG_EQ_DATA_HI, REG_EQ_APPLY,
                     REG_DYN_GR, CAB_VERSION, DYN_VERSION, Q8_PER_DB)

try:
    string_types = (basestring,)        # noqa: F821  (Python 2)
except NameError:
    string_types = (str,)

HERE = os.path.dirname(os.path.abspath(__file__))
TABLE_PATH = os.path.join(HERE, "params.json")

# FPGA VERSION from which the effect chain order can be changed (step E, routing).
# None = no image supports it yet, the order is the fixed hardware order.
ROUTING_VERSION = None

CAB_TAPS = 2048
CAB_COEF_BITS = 18
CAB_SETTLE = 0.02               # s: a bank switch (fade out 128 samples, fade in 128) takes 5.4 ms
EQ_IDS = ("eq_bass", "eq_mid", "eq_treble")
EQ_LIMIT_DB = 12.0
_EQ_CACHE = {}                  # (section, gain dB) -> (5 coefficients, shift): the search in eq_coefs is slow


class ParamError(ValueError):
    """Unknown parameter, value out of range, parameter not in this FPGA image."""


class CabinetError(Exception):
    pass


class FactoryPreset(Exception):
    """Operation not allowed on a factory preset."""


class PresetExists(Exception):
    pass


class NotEditable(Exception):
    """The effect chain order cannot be changed with this FPGA image."""


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def _round_half_up(x):
    return int(math.floor(x + 0.5))


_NUM_RE = re.compile(r"^\s*([+-]?(?:0[xX][0-9a-fA-F]+|\d+\.?\d*(?:[eE][+-]?\d+)?|\.\d+))\s*([A-Za-z%]*)\s*$")


class Param(object):
    """One row of params.json."""

    def __init__(self, d):
        self.d = d
        for k, v in d.items():
            setattr(self, k, v)
        self.aliases = d.get("aliases", [])
        self.enum = d.get("enum")
        self.mask = (1 << self.width) - 1
        self.has_unit = bool(self.unit)
        self.scale = d.get("scale")             # "pow2": the register holds k, the value is 2^k * mul / div
        self.virtual = d.get("virtual")         # no register: kept by the model (the EQ gains)

    # -- register field ---------------------------------------------------
    def extract(self, regval):
        raw = (regval >> self.lsb) & self.mask
        if self.type == "signed" and raw & (1 << (self.width - 1)):
            raw -= 1 << self.width
        return raw

    def insert(self, regval, raw):
        return (regval & ~(self.mask << self.lsb) & 0xFFFF) | ((raw & self.mask) << self.lsb)

    # -- checks -------------------------------------------------------------
    def check_raw(self, raw):
        if not isinstance(raw, int) or isinstance(raw, bool):
            if isinstance(raw, bool):
                raw = int(raw)
            else:
                raise ParamError("%s: raw value must be an integer" % self.id)
        if raw < self.min or raw > self.max:
            raise ParamError("%s: raw value %d outside %d..%d" % (self.id, raw, self.min, self.max))
        return raw

    # -- conversion -----------------------------------------------------------
    def to_display(self, raw):
        if self.type == "bool":
            return bool(raw)
        if self.type == "enum":
            for e in self.enum:
                if e["value"] == raw:
                    return e["label"]
            return raw
        if self.has_unit:
            if self.scale == "pow2":
                return round((1 << raw) * self.mul / self.div, 6)
            return round(raw * self.mul / self.div, 6)
        return raw

    def from_display(self, value):
        """Display value (number, label, bool or text with unit) -> raw register value."""
        if isinstance(value, string_types):
            return self.parse(value, legacy_raw=False)
        if self.type == "bool":
            if isinstance(value, bool) or value in (0, 1):
                return self.check_raw(int(bool(value)))
            raise ParamError("%s: expected true/false" % self.id)
        if isinstance(value, bool):
            raise ParamError("%s: expected a number" % self.id)
        if not isinstance(value, (int, float)):
            raise ParamError("%s: expected a number" % self.id)
        if self.type == "enum":
            if value != int(value):
                raise ParamError("%s: expected an index or a label" % self.id)
            return self._enum_raw(int(value))
        return self._display_to_raw(value)

    def _enum_raw(self, v):
        if not any(e["value"] == v for e in self.enum):
            raise ParamError("%s: %d is not one of %s" % (self.id, v, self.choices()))
        return v

    def choices(self):
        return ", ".join("%d=%s" % (e["value"], e["label"]) for e in self.enum)

    def _display_to_raw(self, x):
        """Display number -> raw; a value within half a step beyond the range clamps to the end."""
        r = x * self.div / self.mul if self.has_unit else x
        if self.scale == "pow2":                 # nearest power of two (in units), clamped like the old tool
            k = 0
            r = max(1.0, r)
            while k < self.max and abs((1 << (k + 1)) - r) < abs((1 << k) - r):
                k += 1
            return k
        tol = 0.5                                # raw steps; at least half a displayed (rounded) step
        if self.has_unit and self.scale != "pow2":
            tol = max(tol, 0.5 * 10.0 ** (-self.decimals) * self.div / self.mul)
        if self.max < r <= self.max + tol:
            return self.max
        if self.min > r >= self.min - tol:
            return self.min
        return self._check_display(_round_half_up(r))

    def _check_display(self, raw):
        if raw < self.min or raw > self.max:
            raise ParamError("%s: value outside %s .. %s" % (
                self.id, self.format(self.min), self.format(self.max)))
        return raw

    def parse(self, text, legacy_raw=False):
        """Text -> raw.  A bare number is a display value, or a raw register value with
        legacy_raw (the old command line); a number with the unit is always a display value."""
        t = str(text).strip()
        if self.type == "bool":
            n = _norm(t)
            if n in ("1", "on", "true", "yes", "enable", "enabled"):
                return 1
            if n in ("0", "off", "false", "no", "disable", "disabled"):
                return 0
            raise ParamError("%s: expected on/off" % self.id)
        if self.type == "enum":
            n = _norm(t)
            for e in self.enum:
                if _norm(e["label"]) == n:
                    return e["value"]
            if re.match(r"^[+-]?(0[xX][0-9a-fA-F]+|\d+)$", t):
                return self._enum_raw(int(t, 0))
            raise ParamError("%s: unknown value '%s' (%s)" % (self.id, t, self.choices()))
        m = _NUM_RE.match(t)
        if not m:
            raise ParamError("%s: cannot read '%s'" % (self.id, t))
        numtxt, suffix = m.group(1), m.group(2)
        if suffix:
            if not self.has_unit or suffix.lower() != self.unit.lower():
                raise ParamError("%s: unit '%s' not accepted%s" % (
                    self.id, suffix, (" (use %s)" % self.unit) if self.has_unit else ""))
            x = float(int(numtxt, 0)) if numtxt.lower().startswith(("0x", "+0x", "-0x")) else float(numtxt)
            return self._display_to_raw(x)
        if legacy_raw or not self.has_unit:
            try:
                raw = int(numtxt, 0)
            except ValueError:
                x = float(numtxt)
                if x != int(x):
                    raise ParamError("%s: expected an integer" % self.id)
                raw = int(x)
            if legacy_raw and self.type == "signed" and (1 << (self.width - 1)) <= raw < (1 << self.width):
                raw -= 1 << self.width           # a register dump value such as 0xFC04
            return self.check_raw(raw)
        return self._display_to_raw(float(numtxt))

    def format(self, raw):
        v = self.to_display(raw)
        if self.type == "bool":
            return "on" if v else "off"
        if self.type == "enum" or not self.has_unit:
            return str(v)
        s = ("%%.%df" % self.decimals) % v
        if "." in s:
            s = s.rstrip("0").rstrip(".")
        return "%s %s" % (s, self.unit)

    def public(self):
        return dict(self.d)


class Table(object):
    def __init__(self, path=TABLE_PATH):
        with open(path) as f:
            data = json.load(f, object_pairs_hook=collections.OrderedDict)
        self.data = data
        self.params = [Param(p) for p in data["params"]]
        self.by_id = {}
        for p in self.params:
            self.by_id[p.id] = p
            for a in p.aliases:
                self.by_id[a] = p
        self.effects = data["effects"]
        self.fx_by_id = dict((e["id"], e) for e in self.effects)
        self.registers = data["registers"]
        self.reg_by_name = dict((r["name"], r["reg"]) for r in self.registers)
        self.presets = data["presets"]
        self.chain_default = list(data["chain_default"])
        self.codec_names = dict((r["name"], r["reg"]) for r in data["codec"]["registers"])
        count = collections.Counter(p.reg for p in self.params if not p.virtual)
        self.shared_regs = set(r for r, n in count.items() if n > 1)
        # legacy names of the old command line
        self.legacy_effect_names = {"OD": "od", "TREM": "trem", "ECHO": "echo", "DIST": "dist",
                                    "CHORUS": "mod", "MOD": "mod", "REVERB": "reverb", "CAB": "cab",
                                    "DYN": "dyn", "EQ": "eq"}
        self.effect_text_names = [("OD", "od"), ("TREM", "trem"), ("ECHO", "echo"), ("DIST", "dist"),
                                  ("CHORUS", "mod"), ("REVERB", "reverb"), ("CAB", "cab"), ("DYN", "dyn"),
                                  ("EQ", "eq")]

    def param(self, pid):
        try:
            return self.by_id[pid]
        except KeyError:
            raise ParamError("unknown parameter '%s'" % pid)

    def register(self, ref):
        """Register number from a number, '0x1B', or a register name."""
        if isinstance(ref, int):
            return ref
        s = str(ref).strip()
        if s in self.reg_by_name:
            return self.reg_by_name[s]
        p = self.by_id.get(s)
        if p is not None and not p.virtual and p.reg not in self.shared_regs:
            return p.reg
        try:
            return int(s, 0)
        except ValueError:
            raise ParamError("unknown register '%s'" % ref)


_table = None


def load_table():
    global _table
    if _table is None:
        _table = Table()
    return _table


def open_device(mock=False, mock_version=0x0208, check=True, state_file=None):
    """The DevMem backend on the board, or the Mock; refuses a foreign FPGA image."""
    dev = device.Mock(version=mock_version, state_file=state_file) if mock else device.DevMem()
    if check:
        v = dev.read(REG_VERSION)
        if v & 0xFF00 != 0x0200:
            raise WrongImage("VERSION reads 0x%04X, not 0x02xx: is the multi-effect FPGA image "
                             "loaded? (--no-check to skip)" % v)
    return dev


def default_cab_dir(data_dir, mock=False, board_dir=None):
    """Directory of the cabNN.coef files: <data-dir>/cab on the board; with the mock, the PC's
    ir/build (written by tools/cab_coefs.py --build) when it holds cabinet files."""
    if mock:
        board_dir = board_dir or os.path.dirname(HERE)
        pc = os.path.normpath(os.path.join(board_dir, os.pardir, "ir", "build"))
        if os.path.isdir(pc) and any(re.match(r"^cab\d\d\.coef$", f) for f in os.listdir(pc)):
            return pc
    return os.path.join(data_dir, "cab")


class Model(object):
    def __init__(self, dev, store=None, cab_dir=None, table=None):
        self.dev = dev
        self.store = store
        self.cab_dir = cab_dir
        self.table = table or load_table()
        self.lock = threading.RLock()
        self.version = dev.read(REG_VERSION)
        self._cab_slot = None
        self._eq = None                  # EQ gains when there is no store

    @property
    def cab_slot(self):
        """Loaded cabinet slot: kept in settings.json, so the CLI and the server agree."""
        if self.store is not None:
            return self.store.settings().get("cab_slot")
        return self._cab_slot

    @cab_slot.setter
    def cab_slot(self, v):
        self._cab_slot = v
        if self.store is not None:
            self.store.update_settings(cab_slot=v)

    # ------------------------------------------------------------ raw access
    def read(self, reg):
        with self.lock:
            return self.dev.read(reg)

    def write(self, reg, value):
        with self.lock:
            self.dev.write(reg, value)

    def available(self, p):
        return self.version >= p.min_version

    def params(self):
        return [p for p in self.table.params if self.available(p)]

    def _param(self, pid, need_available=True):
        p = self.table.param(pid)
        if need_available and not self.available(p):
            raise ParamError("%s needs FPGA VERSION 0x%04X (this image: 0x%04X)" % (
                p.id, p.min_version, self.version))
        return p

    # ------------------------------------------------------------ parameters
    def get_raw(self, pid):
        p = self._param(pid)
        if p.virtual:
            return self._virtual_raw(p)
        return p.extract(self.read(p.reg))

    def get(self, pid):
        p = self._param(pid)
        return p.to_display(self.get_raw(p.id))

    def read_all(self):
        """{id: raw} of all parameters available in this image, one read per register."""
        with self.lock:
            cache = {}
            out = collections.OrderedDict()
            for p in self.params():
                if p.virtual:
                    out[p.id] = self._virtual_raw(p)
                    continue
                if p.reg not in cache:
                    cache[p.reg] = self.dev.read(p.reg)
                out[p.id] = p.extract(cache[p.reg])
            return out

    def set_raw(self, values):
        """{id: raw} -> registers (validated first, one write per register, bit fields merged)."""
        items = []
        for pid, raw in values.items():
            p = self._param(pid)
            items.append((p, p.check_raw(raw)))
        return self._commit(items)

    def set(self, values):
        """{id: display value, label, bool or text with unit} -> registers.
        Returns {id: display value after}."""
        items = []
        for pid, v in values.items():
            p = self._param(pid)
            items.append((p, p.from_display(v)))
        self._commit(items)
        return dict((p.id, p.to_display(raw)) for p, raw in items)

    def _commit(self, items):
        """Write validated (param, raw) items: one write per register (bit fields merged), then the
        EQ coefficients when an EQ gain changed.  The EQ coefficients are computed before the lock is
        taken (slow), nothing is written when anything is invalid."""
        for p, raw in items:
            self._check_enum_version(p, raw)
        virt = [(p, raw) for p, raw in items if p.virtual]
        eq_new = eq_words = None
        if virt:
            gains = list(self.eq_gains())
            for p, raw in virt:
                gains[EQ_IDS.index(p.id)] = raw / 10.0
            eq_new = tuple(gains)
            eq_words = self._eq_compute(eq_new)
        with self.lock:
            regs = collections.OrderedDict()
            for p, raw in items:
                if p.virtual:
                    continue
                if p.reg not in regs:
                    regs[p.reg] = self.dev.read(p.reg) if p.reg in self.table.shared_regs else 0
                regs[p.reg] = p.insert(regs[p.reg], raw)
            for reg, val in regs.items():
                self.dev.write(reg, val)
            if virt:
                self._eq_write(eq_words)
                self._eq_store(eq_new)
        return dict((p.id, raw) for p, raw in items)

    def _check_enum_version(self, p, raw):
        if p.type == "enum":
            for e in p.enum:
                if e["value"] == raw and e.get("min_version", 0) > self.version:
                    raise ParamError("%s: '%s' needs FPGA VERSION 0x%04X (this image: 0x%04X)" % (
                        p.id, e["label"], e["min_version"], self.version))

    # --------------------------------------------------------------- effects
    def effects_value(self):
        return self.read(0)

    def effects_text(self, v=None):
        if v is None:
            v = self.effects_value()
        names = [n for n, fid in self.table.effect_text_names if v & (1 << self.table.fx_by_id[fid]["bit"])]
        return "+".join(names) or "none"

    def parse_effects(self, text):
        """'OD+ECHO', 'none' or a number -> effects register word (old command line syntax)."""
        t = text.strip()
        if t[:1].isdigit():
            return int(t, 0)
        v = 0
        for e in t.split("+"):
            e = e.strip()
            if not e or e.lower() == "none":
                continue
            fid = self.table.legacy_effect_names.get(e.upper()) or (e.lower() if e.lower() in self.table.fx_by_id else None)
            if fid is None:
                raise ParamError("unknown effect '%s' (%s)" % (e, ", ".join(sorted(self.table.legacy_effect_names))))
            v |= 1 << self.table.fx_by_id[fid]["bit"]
        return v

    def enabled_effects(self, word=None):
        if word is None:
            word = self.effects_value()
        return [e["id"] for e in self.table.effects if word & (1 << e["bit"]) and self.version >= e["min_version"]]

    # ---------------------------------------------------------------- status
    def status(self):
        with self.lock:
            st = self.dev.read(REG_STATUS)
            ctl = self.dev.read(REG_CONTROL)
            word = self.dev.read(0)
            li, lo = self.dev.read(REG_LEVEL_IN), self.dev.read(REG_LEVEL_OUT)
        return collections.OrderedDict([
            ("version", self.version), ("status", st),
            ("codec_init_done", bool(st & 1)), ("codec_nak", bool(st & 2)), ("pll_locked", bool(st & 4)),
            ("mute", bool(ctl & 2)), ("effects", self.effects_text(word)),
            ("effects_word", word), ("level_in", li), ("level_out", lo),
            ("gain_reduction", self.gain_reduction())])

    def gain_reduction(self):
        """Gain reduction of the dynamics stage in dB (DYN_GR), None when the image has no dynamics."""
        if self.version < DYN_VERSION:
            return None
        with self.lock:
            v = self.dev.read(REG_DYN_GR)
        return round(v / Q8_PER_DB, 1)

    def levels(self):
        with self.lock:
            li, lo = self.dev.read(REG_LEVEL_IN), self.dev.read(REG_LEVEL_OUT)
            gr = self.dev.read(REG_DYN_GR) if self.version >= DYN_VERSION else None

        def db(x):
            return round(20 * math.log10(x / 32768.0), 1) if x > 0 else None
        return {"in": li, "out": lo, "in_db": db(li), "out_db": db(lo),
                "gain_reduction": None if gr is None else round(gr / Q8_PER_DB, 1)}

    def state(self):
        with self.lock:
            raw = self.read_all()
            values = collections.OrderedDict((pid, self.table.by_id[pid].to_display(r)) for pid, r in raw.items())
            return collections.OrderedDict([
                ("values", values), ("raw", raw), ("status", self.status()),
                ("chain", self.chain()), ("cab", self.cab_status())])

    # ----------------------------------------------------------------- codec
    def wait_codec(self, timeout=0.1):
        t0 = time.time()
        while True:
            st = self.dev.read(REG_CODEC)
            if not st & 1:
                return st
            if time.time() - t0 > timeout:
                raise DeviceError("I2C master busy for %.0f ms" % (timeout * 1e3))
            time.sleep(0.001)

    def codec_write(self, reg, value9, timeout=0.1):
        """One WM8731 register write over the FPGA's I2C master."""
        with self.lock:
            if not 0 <= reg <= 0x7F or not 0 <= value9 <= 0x1FF:
                raise ParamError("codec register 0..127, value 0..511")
            self.wait_codec(timeout)
            self.dev.write(REG_CODEC, ((reg & 0x7F) << 9) | (value9 & 0x1FF))
            st = self.wait_codec(timeout)
            if st & 2:
                raise DeviceError("codec did not ACK the write")
            if st & 4:
                raise DeviceError("write dropped: I2C master was busy")

    def codec_reg(self, ref):
        if isinstance(ref, int):
            return ref
        s = str(ref).strip()
        if s in self.table.codec_names:
            return self.table.codec_names[s]
        try:
            return int(s, 0)
        except ValueError:
            raise ParamError("unknown codec register '%s'" % ref)

    # --------------------------------------------------------------- presets
    def _preset_scope(self):
        return [p for p in self.params() if p.in_preset]

    def factory_names(self):
        return list(self.table.presets.keys())

    def preset_list(self):
        out = [{"name": n, "factory": True, "description": v.get("description", "")}
               for n, v in self.table.presets.items()]
        if self.store is not None:
            for n in self.store.list_presets():
                if n not in self.table.presets:
                    out.append({"name": n, "factory": False, "description": ""})
        return out

    def get_preset(self, name):
        if name in self.table.presets:
            d = self.table.presets[name]
            return {"name": name, "factory": True, "description": d.get("description", ""),
                    "fx": list(d["fx"]), "params": dict(d["params"]), "chain": None, "cab": None,
                    "keep": list(d.get("keep", []))}
        if self.store is not None and self.store.valid_name(name) and self.store.exists(name):
            d = self.store.load_preset(name)
            d = dict(d)
            d.update({"name": name, "factory": False})
            d.setdefault("fx", [])
            d.setdefault("params", {})
            d.setdefault("chain", None)
            d.setdefault("cab", None)
            d.setdefault("keep", [])
            return d
        raise KeyError(name)

    def apply_preset(self, preset):
        """Apply a preset (name or dict).  Every parameter with in_preset true is rewritten: those the
        preset does not list become 0, like the old tool.  Parameters with in_preset "user" (dynamics,
        EQ: saved by user presets) are only written when the preset lists them.  The effects in the
        preset's "keep" list (factory presets: cabinet, dynamics, EQ) keep their current on/off state.
        Returns a list of warnings."""
        if isinstance(preset, string_types):
            preset = self.get_preset(preset)
        warnings = []
        eq_new = eq_words = None
        eq_in = dict((pid, raw) for pid, raw in preset["params"].items() if pid in EQ_IDS)
        if eq_in and self.eq_available():
            gains = list(self.eq_gains())
            for pid, raw in eq_in.items():
                self.table.param(pid).check_raw(raw)
                gains[EQ_IDS.index(pid)] = raw / 10.0
            eq_new = tuple(gains)
            eq_words = self._eq_compute(eq_new)
        with self.lock:
            for pid, raw in preset["params"].items():
                p = self.table.by_id.get(pid)
                if p is None:
                    raise ParamError("preset: unknown parameter '%s'" % pid)
                if not p.in_preset:
                    raise ParamError("preset: '%s' is not a preset parameter" % pid)
                p.check_raw(raw)
                if not self.available(p):
                    warnings.append("%s not in this FPGA image" % pid)
            word = 0
            for fid in preset["fx"]:
                e = self.table.fx_by_id.get(fid)
                if e is None:
                    raise ParamError("preset: unknown effect '%s'" % fid)
                if self.version >= e["min_version"]:
                    word |= 1 << e["bit"]
                else:
                    warnings.append("effect %s not in this FPGA image" % fid)
            for fid in preset.get("keep") or []:
                e = self.table.fx_by_id.get(fid)
                if e is not None and self.version >= e["min_version"]:
                    word |= self.dev.read(0) & (1 << e["bit"])
            regs = {0: word}
            for p in self._preset_scope():
                if p.virtual or (p.in_preset == "user" and p.id not in preset["params"]):
                    continue
                base = regs.get(p.reg)
                if base is None:
                    base = self.dev.read(p.reg) if p.in_preset == "user" else 0
                regs[p.reg] = p.insert(base, preset["params"].get(p.id, 0))
            for reg in sorted(regs):             # effects word first, then ascending
                self.dev.write(reg, regs[reg])
            if eq_words is not None:
                self._eq_write(eq_words)
                self._eq_store(eq_new)
            slot = preset.get("cab")
            if slot is not None and self.version >= CAB_VERSION and self.cab_dir and slot != self.cab_slot:
                try:
                    self.cab_load(slot)
                except (CabinetError, IOError, OSError) as e:
                    warnings.append("cabinet %s: %s" % (slot, e))
            order = preset.get("chain")
            if order and self.chain_editable():
                try:
                    self.set_chain(order)
                except (NotEditable, ParamError) as e:
                    warnings.append("chain: %s" % e)
        return warnings

    def capture_preset(self):
        with self.lock:
            raw = self.read_all()
            return {"fx": self.enabled_effects(),
                    "params": collections.OrderedDict((p.id, raw[p.id]) for p in self._preset_scope()),
                    "chain": self.chain()["order"], "cab": self.cab_slot}

    def save_preset(self, name, overwrite=False, data=None):
        if self.store is None:
            raise ParamError("no preset store")
        if name in self.table.presets:
            raise FactoryPreset("'%s' is a factory preset (read-only)" % name)
        if not self.store.valid_name(name):
            raise ParamError("invalid preset name (letters, digits, space, _ . -; max 40 characters)")
        if self.store.exists(name) and not overwrite:
            raise PresetExists("preset '%s' exists (overwrite=true to replace)" % name)
        preset = data if data is not None else self.capture_preset()
        self.store.save_preset(name, preset)
        return preset

    def delete_preset(self, name):
        if name in self.table.presets:
            raise FactoryPreset("'%s' is a factory preset (read-only)" % name)
        if self.store is None:
            raise KeyError(name)
        self.store.delete_preset(name)

    # ----------------------------------------------------------------- chain
    def chain_editable(self):
        return ROUTING_VERSION is not None and self.version >= ROUTING_VERSION

    def chain(self):
        with self.lock:
            word = self.dev.read(0)
            avail = [e["id"] for e in self.table.effects if self.version >= e["min_version"]]
            order = None
            if self.chain_editable() and self.store is not None:
                saved = self.store.settings().get("chain")
                if saved and sorted(saved) == sorted(avail):
                    order = list(saved)
            if order is None:
                order = [i for i in self.table.chain_default if i in avail]
            effects = []
            for fid in order:
                e = self.table.fx_by_id[fid]
                effects.append({"id": fid, "name": e["name"], "enable": e["enable"],
                                "on": bool(word & (1 << e["bit"]))})
            return {"order": order, "editable": self.chain_editable(), "effects": effects}

    def set_chain(self, order):
        with self.lock:
            if not self.chain_editable():
                raise NotEditable("the effect order is fixed in this FPGA image (VERSION 0x%04X)" % self.version)
            avail = [e["id"] for e in self.table.effects if self.version >= e["min_version"]]
            if not isinstance(order, list) or sorted(order) != sorted(avail):
                raise ParamError("order must list every effect exactly once: %s" % ", ".join(avail))
            if self.store is not None:
                self.store.update_settings(chain=list(order))
            # the routing registers of step E are written here once they exist
            return self.chain()

    # -------------------------------------------------------------- cabinets
    def cab_available(self):
        return self.version >= CAB_VERSION

    def _cab_path(self, slot):
        if not self.cab_dir:
            raise CabinetError("no cabinet directory configured")
        return os.path.join(self.cab_dir, "cab%02d.coef" % slot)

    @staticmethod
    def read_coef_file(path, full=True):
        with open(path) as f:
            lines = f.read().splitlines()
        if len(lines) < 2:
            raise CabinetError("%s: too short" % os.path.basename(path))
        name = lines[0].strip()
        try:
            shift = int(lines[1].strip(), 0)
        except ValueError:
            raise CabinetError("%s: line 2 must be the shift (0..7)" % os.path.basename(path))
        if not 0 <= shift <= 7:
            raise CabinetError("%s: shift %d outside 0..7" % (os.path.basename(path), shift))
        coefs = None
        if full:
            try:
                coefs = [int(t, 0) for t in " ".join(lines[2:]).split()]
            except ValueError:
                raise CabinetError("%s: coefficients must be integers" % os.path.basename(path))
            if len(coefs) != CAB_TAPS:
                raise CabinetError("%s: %d coefficients, expected %d" % (os.path.basename(path), len(coefs), CAB_TAPS))
            lim = 1 << (CAB_COEF_BITS - 1)
            if min(coefs) < -lim or max(coefs) > lim - 1:
                raise CabinetError("%s: coefficient outside the signed %d bit range" % (os.path.basename(path), CAB_COEF_BITS))
        return name, shift, coefs

    def cab_list(self):
        out = []
        if not self.cab_dir or not os.path.isdir(self.cab_dir):
            return out
        for fn in sorted(os.listdir(self.cab_dir)):
            m = re.match(r"^cab(\d\d)\.coef$", fn)
            if not m:
                continue
            slot = int(m.group(1))
            try:
                name, shift, _ = self.read_coef_file(os.path.join(self.cab_dir, fn), full=False)
                out.append({"slot": slot, "name": name, "shift": shift, "file": fn})
            except (CabinetError, IOError, OSError) as e:
                out.append({"slot": slot, "name": fn, "shift": None, "file": fn, "error": str(e)})
        return out

    def cab_status(self):
        st = {"available": self.cab_available(), "slot": self.cab_slot, "slots": self.cab_list()}
        if self.cab_available():
            with self.lock:
                ctl = self.dev.read(REG_CAB_CTRL)
                st["active_bank"] = ctl & 1
                st["enabled"] = bool(self.dev.read(0) & (1 << self.table.fx_by_id["cab"]["bit"]))
        else:
            st["active_bank"] = None
            st["enabled"] = False
        return st

    def cab_write_bank(self, bank, coefs):
        """Write 2048 signed coefficients into the inactive bank (pointer, then LO/HI pairs)."""
        with self.lock:
            if not self.cab_available():
                raise CabinetError("this FPGA image (VERSION 0x%04X) has no cabinet simulator" % self.version)
            if bank not in (0, 1):
                raise CabinetError("bank must be 0 or 1")
            if len(coefs) != CAB_TAPS:
                raise CabinetError("%d coefficients, expected %d" % (len(coefs), CAB_TAPS))
            if bank == self.dev.read(REG_CAB_CTRL) & 1:
                raise CabinetError("bank %d is the active bank: the hardware ignores writes to it" % bank)
            self.dev.write(REG_CAB_ADDR, bank << 11)
            for c in coefs:
                v = c & 0x3FFFF
                self.dev.write(REG_CAB_DATA_LO, v & 0xFFFF)
                self.dev.write(REG_CAB_DATA_HI, v >> 16)

    def cab_load(self, slot):
        """Load cabinet file slot into the inactive bank, set its shift, switch the active bank."""
        with self.lock:
            if not self.cab_available():
                raise CabinetError("this FPGA image (VERSION 0x%04X) has no cabinet simulator" % self.version)
            path = self._cab_path(slot)
            if not os.path.isfile(path):
                raise CabinetError("cabinet slot %d: %s not found" % (slot, os.path.basename(path)))
            name, shift, coefs = self.read_coef_file(path)
            time.sleep(CAB_SETTLE)                                   # a previous switch must be finished
            ctl = self.dev.read(REG_CAB_CTRL) & 0x7F
            target = 1 - (ctl & 1)
            self.cab_write_bank(target, coefs)
            sp = self.table.param("cab_shift%d" % target)
            ctl = sp.insert(ctl, shift)
            self.dev.write(REG_CAB_CTRL, ctl)                        # shift of the new bank
            self.dev.write(REG_CAB_CTRL, (ctl & ~1 & 0xFFFF) | target)   # switch
            time.sleep(CAB_SETTLE)
            self.cab_slot = slot
            if self.store is not None:
                self.store.update_settings(cab_slot=slot)
            return {"slot": slot, "name": name, "shift": shift, "bank": target}

    def cab_enable(self, on):
        if not self.cab_available():
            raise CabinetError("this FPGA image (VERSION 0x%04X) has no cabinet simulator" % self.version)
        return self.set({"cab_on": bool(on)})


    # ------------------------------------------------------------------- EQ
    # The FPGA takes biquad coefficients (EQ_ADDR / EQ_DATA_LO / EQ_DATA_HI / EQ_APPLY) that cannot be
    # read back, so the gains in dB are kept here (settings.json) and the coefficients are computed
    # with eq_coefs (the same code as tools/eq_coefs.py) whenever a gain changes.
    def eq_available(self):
        return self.version >= DYN_VERSION

    def eq_gains(self):
        """(bass, mid, treble) in dB as last set."""
        if self.store is not None:
            e = self.store.settings().get("eq")
        else:
            e = self._eq
        e = e or {}
        return tuple(float(e.get(k, 0.0)) for k in ("bass", "mid", "treble"))

    def _virtual_raw(self, p):
        return _round_half_up(self.eq_gains()[EQ_IDS.index(p.id)] * 10)

    def _eq_store(self, gains):
        e = {"bass": gains[0], "mid": gains[1], "treble": gains[2]}
        self._eq = e
        if self.store is not None:
            self.store.update_settings(eq=e)

    @staticmethod
    def eq_words(bass, mid, treble):
        """The 16 words for the EQ write port: 15 signed coefficients (18-bit two's complement) and the
        scale word.  Same result as tools/eq_coefs.py coefficient_set_full for all three gains; each
        section is computed on its own (they are independent) and cached, so moving one slider only
        redoes one section."""
        ints, shifts = [], []
        for i, g in enumerate((bass, mid, treble)):
            key = (i, float(g))
            hit = _EQ_CACHE.get(key)
            if hit is None:
                args = [0.0, 0.0, 0.0]
                args[i] = float(g)
                full, sh, _clipped = eq_coefs.coefficient_set_full(*args)
                hit = (full[5 * i:5 * i + 5], sh[i])
                if len(_EQ_CACHE) > 400:
                    _EQ_CACHE.clear()
                _EQ_CACHE[key] = hit
            ints.extend(hit[0])
            shifts.append(hit[1])
        return [eq_coefs.word18(v) for v in ints] + [eq_coefs.scale_word(shifts)]

    def _eq_compute(self, gains):
        if not self.eq_available():
            raise ParamError("the EQ needs VERSION 0x%04X or later" % DYN_VERSION)
        if any(abs(g) > EQ_LIMIT_DB + 1e-9 for g in gains):
            raise ParamError("EQ gains are limited to -12 .. +12 dB")
        return self.eq_words(*gains)

    def _eq_write(self, words):
        """16 words through EQ_ADDR / DATA_LO / DATA_HI (the pointer auto-increments), then EQ_APPLY."""
        self.dev.write(REG_EQ_ADDR, 0)
        for w in words:
            self.dev.write(REG_EQ_DATA_LO, w & 0xFFFF)
            self.dev.write(REG_EQ_DATA_HI, (w >> 16) & 3)
        self.dev.write(REG_EQ_APPLY, 1)

    def eq_set(self, bass=None, mid=None, treble=None):
        """Set EQ gains in dB (None = keep), compute and apply the coefficients.  Does not switch the EQ on."""
        cur = self.eq_gains()
        new = tuple(c if g is None else float(g) for c, g in zip(cur, (bass, mid, treble)))
        words = self._eq_compute(new)
        with self.lock:
            self._eq_write(words)
            self._eq_store(new)
        return new

    def eq_resync(self):
        """Write the stored gains to the FPGA (after a restart of the server or a new FPGA image the
        coefficients are back to transparent).  True when something was written."""
        if not self.eq_available():
            return False
        gains = self.eq_gains()
        if not any(gains):
            return False
        words = self._eq_compute(gains)
        with self.lock:
            self._eq_write(words)
        return True
