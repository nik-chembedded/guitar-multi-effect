"""Register access backends: DevMem (/dev/mem on the board) and Mock (in memory).

Both offer read(reg) / write(reg, value) of 16-bit register values; register n is
the 32-bit word at 0xFF200000 + 4*n.  Python 2.7 and 3 compatible, standard library only.
"""
from __future__ import print_function, division

import json
import math
import os
import threading
import time

LW_BRIDGE = 0xFF200000
SPAN = 0x100
NWORDS = SPAN // 4

REG_VERSION = 0x10
REG_STATUS = 0x11
REG_LEVEL_IN = 0x12
REG_LEVEL_OUT = 0x13
REG_CONTROL = 0x14
REG_CODEC = 0x15
REG_CAB_CTRL = 0x1B
REG_CAB_ADDR = 0x1C
REG_CAB_DATA_LO = 0x1D
REG_CAB_DATA_HI = 0x1E
REG_REVERB_SIZE = 0x1F
REG_REVERB_DAMP = 0x20
REG_DYN_CTRL = 0x21
REG_GATE_THRESH = 0x22
REG_COMP_THRESH = 0x23
REG_COMP_RATIO = 0x24
REG_COMP_MAKEUP = 0x27
REG_EQ_ADDR = 0x28
REG_EQ_DATA_LO = 0x29
REG_EQ_DATA_HI = 0x2A
REG_EQ_APPLY = 0x2B
REG_DYN_GR = 0x2C
REG_OD_LEVEL = 0x2D
REG_DIST_LEVEL = 0x2E

CAB_VERSION = 0x0205
DYN_VERSION = 0x0207            # dynamics, EQ, DYN_GR (step D5)
LEVEL_VERSION = 0x0208          # output level of the overdrive / distortion (step D6)
Q8_PER_DB = 256 / 6.0206        # Q8 log2 units per dB
COMP_RATIOS = (1.0, 2.0, 4.0, 8.0, float("inf"))


class DeviceError(IOError):
    pass


class WrongImage(Exception):
    """VERSION does not read 0x02xx: another FPGA image is loaded."""


class DevMem(object):
    """32-bit register access through /dev/mem.

    Accesses go through a ctypes uint32 array: one 32-bit load/store per
    register. (struct.pack_into('<I', ...) writes byte by byte, i.e. four bus
    writes, which once caused a real bug.)"""

    mock = False

    def __init__(self, base=LW_BRIDGE):
        import ctypes
        import mmap
        import os
        fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
        try:
            self.mem = mmap.mmap(fd, SPAN, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE,
                                 offset=base)
        finally:
            os.close(fd)
        self.words = (ctypes.c_uint32 * NWORDS).from_buffer(self.mem)

    def read(self, reg):
        return self.words[reg] & 0xFFFF

    def write(self, reg, value):
        self.words[reg] = value & 0xFFFF


class Mock(object):
    """In-memory register file emulating the FPGA registers.

    * VERSION, STATUS, LEVEL_IN, LEVEL_OUT are read-only (writes ignored);
      levels move over time (deterministic when a clock function is given).
    * CONTROL: bit0 (codec re-init) is self-clearing and makes CODEC busy.
    * CODEC: a write is logged in codec_log and CODEC reads busy once (bit0);
      a write while busy sets bit2 (dropped) and is not logged; bit1 = NAK
      when nak=True.
    * Cabinet (VERSION >= 0x0205): CAB_ADDR sets the pointer, CAB_DATA_LO is
      latched, a write to CAB_DATA_HI stores {HI,LO} at the pointer and
      increments it; writes to the active bank are ignored (counted in
      cab_ignored_writes), the pointer still increments (CAB_ADDR reads back
      the last value written, not the pointer, like the FPGA).
    * EQ (VERSION >= 0x0207): EQ_ADDR sets the pointer (0..15), EQ_DATA_LO is
      latched, a write to EQ_DATA_HI stores {HI,LO} (18 bit) in the shadow set
      at the pointer and increments it (15 wraps to 0); a write to EQ_APPLY copies
      the shadow set to eq_active (list of 16 words) and counts in eq_applies.
    * DYN_GR (VERSION >= 0x0207) is read-only and moves with the input level: while
      the dynamics stage and the compressor are on, it is the compressor reduction
      (over the threshold, shift ratio, minus make-up) in unsigned Q8 log2 units;
      else 0.  The gate attenuation is not emulated.
    * Other registers up to 0x2F read back what was written; above read 0.
    * max_concurrent records the highest number of overlapping calls, so tests
      can verify that access is serialised; write_delay widens the window.
    """

    mock = True

    def __init__(self, version=0x0208, clock=None, write_delay=0.0, nak=False, status=0x0005,
                 state_file=None):
        self.version = version
        self.clock = clock or time.time
        self.t0 = self.clock()
        self.write_delay = write_delay
        self.nak = nak
        self.status = status
        self.regs = [0] * NWORDS
        self.log = []                       # (reg, value) of every accepted write
        self.codec_log = []                 # (codec register, 9-bit value)
        self.codec_busy_reads = 0
        self.codec_dropped = False
        self.codec_nak = False
        self.cab_mem = [[0] * 2048, [0] * 2048]
        self.cab_ptr = 0
        self.cab_lo = 0
        self.cab_ignored_writes = 0
        self.eq_ptr = 0
        self.eq_lo = 0
        self.eq_shadow = [0] * 16
        self.eq_active = [0] * 16
        self.eq_applies = 0
        self.max_concurrent = 0
        self._active = 0
        self._guard = threading.Lock()
        self.state_file = state_file
        self._sig = None
        self._load_state()

    # -- shared state file (--mock-state): other processes see the same registers ----------
    def _file_sig(self):
        try:
            st = os.stat(self.state_file)
            return (st.st_mtime, st.st_size)
        except OSError:
            return None

    def _load_state(self):
        """Reload the registers when the state file changed (written by another process)."""
        if not self.state_file:
            return
        sig = self._file_sig()
        if sig is None or sig == self._sig:
            return
        try:
            with open(self.state_file) as f:
                regs = json.load(f)["regs"]
        except (IOError, OSError, ValueError, KeyError):
            return
        for i, v in enumerate(regs[:NWORDS]):
            self.regs[i] = int(v) & 0xFFFF
        self._sig = sig

    def _save_state(self):
        if not self.state_file:
            return
        tmp = "%s.%d.tmp" % (self.state_file, os.getpid())
        with open(tmp, "w") as f:
            json.dump({"regs": self.regs}, f)
        rep = getattr(os, "replace", None)
        if rep is not None:
            rep(tmp, self.state_file)
        else:
            try:
                os.rename(tmp, self.state_file)
            except OSError:
                os.remove(self.state_file)
                os.rename(tmp, self.state_file)
        self._sig = self._file_sig()

    # -- helpers --------------------------------------------------------
    def _enter(self):
        with self._guard:
            self._active += 1
            if self._active > self.max_concurrent:
                self.max_concurrent = self._active

    def _leave(self):
        with self._guard:
            self._active -= 1

    def _has_cab(self):
        return self.version >= CAB_VERSION

    def _has_dyn(self):
        return self.version >= DYN_VERSION

    def _dyn_gr(self):
        """Compressor gain reduction (Q8 log2 units) for the current input level."""
        if not self._has_dyn() or not self.regs[0] & 0x80 or not self.regs[REG_DYN_CTRL] & 2:
            return 0
        li = self._levels()[0]
        if li <= 0:
            return 0
        level_db = 20 * math.log10(li / 32768.0)
        thresh = self.regs[REG_COMP_THRESH]
        if thresh & 0x8000:
            thresh -= 0x10000
        over = max(0.0, level_db - thresh / Q8_PER_DB)
        ratio = COMP_RATIOS[min(self.regs[REG_COMP_RATIO] & 7, 4)]
        red = over if ratio == float("inf") else over - over / ratio
        makeup = self.regs[REG_COMP_MAKEUP]
        if makeup & 0x8000:
            makeup -= 0x10000
        red = max(0.0, red - makeup / Q8_PER_DB)
        return min(0xFFFF, int(red * Q8_PER_DB))

    def _levels(self):
        t = self.clock() - self.t0
        li = int(abs(math.sin(t * 2.7)) * 18000 + abs(math.sin(t * 11.3)) * 6000)
        out = li
        if self.regs[REG_CONTROL] & 2:
            out = 0
        elif self.regs[0] & 0x1FF:
            out = min(32767, int(li * 1.3))
        return li, out

    # -- register interface ---------------------------------------------
    def read(self, reg):
        self._enter()
        try:
            if self.write_delay:
                time.sleep(self.write_delay)
            with self._guard:
                self._load_state()
            return self._read(reg)
        finally:
            self._leave()

    def _read(self, reg):
        if reg < 0 or reg >= NWORDS:
            raise DeviceError("register %d outside the mapped span" % reg)
        if reg == REG_VERSION:
            return self.version & 0xFFFF
        if reg == REG_STATUS:
            return self.status & 0xFFFF
        if reg == REG_LEVEL_IN:
            return self._levels()[0]
        if reg == REG_LEVEL_OUT:
            return self._levels()[1]
        if reg == REG_DYN_GR and self._has_dyn():
            return self._dyn_gr()
        if reg == REG_CODEC:
            v = 0
            if self.codec_busy_reads > 0:
                self.codec_busy_reads -= 1
                v |= 1
            if self.codec_nak:
                v |= 2
            if self.codec_dropped:
                v |= 4
            return v
        if reg > 0x2F:
            return 0
        return self.regs[reg]

    def write(self, reg, value):
        self._enter()
        try:
            if self.write_delay:
                time.sleep(self.write_delay)
            with self._guard:
                self._load_state()
                self._write(reg, value & 0xFFFF)
                if reg not in (REG_CAB_ADDR, REG_CAB_DATA_LO, REG_CAB_DATA_HI,
                               REG_EQ_ADDR, REG_EQ_DATA_LO, REG_EQ_DATA_HI):   # bulk coefficient data: not saved per write
                    self._save_state()
        finally:
            self._leave()

    def _write(self, reg, value):
        if reg < 0 or reg >= NWORDS:
            raise DeviceError("register %d outside the mapped span" % reg)
        if reg in (REG_VERSION, REG_STATUS, REG_LEVEL_IN, REG_LEVEL_OUT) or reg > 0x2F:
            return
        if reg == REG_DYN_GR and self._has_dyn():
            return
        self.log.append((reg, value))
        if reg == REG_CONTROL:
            self.regs[reg] = value & 2
            if value & 1:
                self.codec_busy_reads = 3
            return
        if reg == REG_CODEC:
            if self.codec_busy_reads > 0:
                self.codec_dropped = True
                return
            self.codec_dropped = False
            self.codec_nak = bool(self.nak)
            self.codec_log.append(((value >> 9) & 0x7F, value & 0x1FF))
            self.codec_busy_reads = 1
            self.regs[reg] = value
            return
        if self._has_cab():
            if reg == REG_CAB_CTRL:
                self.regs[reg] = value & 0x7F
                return
            if reg == REG_CAB_ADDR:
                self.regs[reg] = value & 0xFFF
                self.cab_ptr = value & 0xFFF
                return
            if reg == REG_CAB_DATA_LO:
                self.regs[reg] = value
                self.cab_lo = value
                return
            if reg == REG_CAB_DATA_HI:
                self.regs[reg] = value & 3
                bank = (self.cab_ptr >> 11) & 1
                tap = self.cab_ptr & 0x7FF
                if bank == (self.regs[REG_CAB_CTRL] & 1):
                    self.cab_ignored_writes += 1
                else:
                    self.cab_mem[bank][tap] = ((value & 3) << 16) | self.cab_lo
                self.cab_ptr = (bank << 11) | ((tap + 1) & 0x7FF)
                return
        if self._has_dyn():
            if reg == REG_EQ_ADDR:
                self.regs[reg] = value & 0xF
                self.eq_ptr = value & 0xF
                return
            if reg == REG_EQ_DATA_LO:
                self.regs[reg] = value
                self.eq_lo = value
                return
            if reg == REG_EQ_DATA_HI:
                self.regs[reg] = value & 3
                self.eq_shadow[self.eq_ptr] = ((value & 3) << 16) | self.eq_lo
                self.eq_ptr = (self.eq_ptr + 1) & 0xF
                return
            if reg == REG_EQ_APPLY:
                self.regs[reg] = value
                self.eq_active = list(self.eq_shadow)
                self.eq_applies += 1
                return
        self.regs[reg] = value

    def cab_coef(self, bank, tap):
        """Stored coefficient as a signed integer (18 bit)."""
        v = self.cab_mem[bank][tap]
        return v - 0x40000 if v & 0x20000 else v
