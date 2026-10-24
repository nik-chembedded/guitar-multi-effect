#!/usr/bin/env python3
"""
gme_ctl.py - host control tool for the guitar multi-effect v2 (UART, 115200 8N1).

    gme_ctl.py -p COM5 ping
    gme_ctl.py -p COM5 status
    gme_ctl.py -p COM5 read  0x02
    gme_ctl.py -p COM5 write 0x00 0x0001          (register, value)
    gme_ctl.py -p COM5 set   od_drive=3000 od_gain=4 effects=OD
    gme_ctl.py -p COM5 preset crunch
    gme_ctl.py -p COM5 codec 0x02 0x079           (codec register, 9-bit value)
    gme_ctl.py -p COM5 dump
    gme_ctl.py selftest                            (no hardware needed)

Protocol (docs/v2_stepB_design.md, fpga/rtl/ctrl_uart.vhd):
    request  A5 cmd addr data_hi data_lo crc8      cmd: 01 write, 02 read, 03 codec, 04 ping
    reply    5A status data_hi data_lo crc8        status: 00 ok, 01 crc, 02 bad cmd/addr,
                                                           03 i2c nak, 04 i2c busy
    CRC-8/SMBUS (poly 0x07, init 0) over the 4 bytes between sync and crc.
Requires pyserial for real ports: pip install pyserial
"""
import argparse
import sys
import time

REGS = {
    "effects_enable": 0x00, "od_drive": 0x01, "od_gain": 0x02, "trem_wave": 0x03,
    "trem_depth": 0x04, "echo_time": 0x05, "echo_repeat": 0x06, "echo_level": 0x07,
    "dist_mix": 0x08, "dist_type": 0x09, "chorus_level": 0x0A, "chorus_depth": 0x0B,
    "chorus_rate": 0x0C, "reverb_mix": 0x0D, "reverb_type": 0x0E,
    "version": 0x10, "status": 0x11, "level_in": 0x12, "level_out": 0x13, "control": 0x14,
}
EFFECT_BITS = {"OD": 1, "TREM": 2, "ECHO": 4, "DIST": 8, "CHORUS": 16, "REVERB": 32}
STATUS_TEXT = {0: "ok", 1: "CRC error", 2: "bad command/address", 3: "codec NAK", 4: "I2C busy"}

PRESETS = {
    "clean":  dict(effects_enable=0),
    "crunch": dict(effects_enable=EFFECT_BITS["DIST"] | EFFECT_BITS["REVERB"], dist_type=1, dist_mix=160,
                   reverb_type=1, reverb_mix=60),
    "lead":   dict(effects_enable=EFFECT_BITS["DIST"] | EFFECT_BITS["ECHO"] | EFFECT_BITS["REVERB"],
                   dist_type=2, dist_mix=220, echo_time=18000, echo_level=20000, echo_repeat=90,
                   reverb_type=2, reverb_mix=80),
    "ambient": dict(effects_enable=EFFECT_BITS["CHORUS"] | EFFECT_BITS["ECHO"] | EFFECT_BITS["REVERB"],
                    chorus_level=30000, chorus_depth=400, chorus_rate=40, echo_time=24000,
                    echo_level=26000, echo_repeat=140, reverb_type=3, reverb_mix=128),
    "trem":   dict(effects_enable=EFFECT_BITS["TREM"], trem_wave=0, trem_depth=200),
}


def crc8(data):
    c = 0
    for b in data:
        c ^= b
        for _ in range(8):
            c = ((c << 1) ^ 0x07) & 0xFF if c & 0x80 else (c << 1) & 0xFF
    return c


def make_frame(cmd, addr, data=0):
    body = [cmd & 0xFF, addr & 0xFF, (data >> 8) & 0xFF, data & 0xFF]
    return bytes([0xA5] + body + [crc8(body)])


def parse_reply(raw):
    if len(raw) != 5 or raw[0] != 0x5A:
        raise IOError("no/invalid reply: %s" % raw.hex(" "))
    if crc8(raw[1:4]) != raw[4]:
        raise IOError("reply CRC error: %s" % raw.hex(" "))
    return raw[1], (raw[2] << 8) | raw[3]


class Board:
    def __init__(self, port, baud=115200, timeout=0.5):
        import serial                                    # pyserial
        self.ser = serial.Serial(port, baud, timeout=timeout)

    def transact(self, cmd, addr, data=0, retries=2):
        for attempt in range(retries + 1):
            self.ser.reset_input_buffer()
            self.ser.write(make_frame(cmd, addr, data))
            try:
                status, value = parse_reply(self.ser.read(5))
            except IOError:
                if attempt == retries:
                    raise
                time.sleep(0.02)                         # > 10 ms: the FPGA drops partial frames
                continue
            if status == 1 and attempt < retries:        # CRC error on the way in: retry
                continue
            if status != 0:
                raise IOError("board replied: %s" % STATUS_TEXT.get(status, hex(status)))
            return value

    def ping(self):
        return self.transact(0x04, 0)

    def read(self, reg):
        return self.transact(0x02, reg)

    def write(self, reg, value):
        self.transact(0x01, reg, value)

    def codec(self, reg, value9):
        self.transact(0x03, reg, value9 & 0x1FF)


def num(s):
    return int(s, 0)


def parse_assignments(items):
    regs = {}
    for it in items:
        k, v = it.split("=", 1)
        if k == "effects":
            regs["effects_enable"] = sum(EFFECT_BITS[e.strip().upper()] for e in v.split("+") if e.strip()) \
                if not v[:1].isdigit() else num(v)
        elif k in REGS:
            regs[k] = num(v)
        else:
            raise SystemExit("unknown register '%s' (known: %s)" % (k, ", ".join(REGS)))
    return regs


def selftest():
    assert crc8(b"123456789") == 0xF4, "CRC-8/SMBUS check value"
    f = make_frame(0x01, 0x02, 0xBEEF)
    assert f[0] == 0xA5 and f[5] == crc8(f[1:5])
    st, v = parse_reply(bytes([0x5A, 0x00, 0x02, 0x00, crc8(b"\x00\x02\x00")]))
    assert (st, v) == (0, 0x0200)
    print("selftest OK: CRC-8/SMBUS check 0xF4, frame %s" % f.hex(" "))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-p", "--port", help="serial port, e.g. COM5 or /dev/ttyUSB0")
    ap.add_argument("-b", "--baud", type=int, default=115200)
    ap.add_argument("cmd", choices=["ping", "status", "read", "write", "set", "preset", "codec", "dump", "selftest"])
    ap.add_argument("args", nargs="*")
    a = ap.parse_args()
    if a.cmd == "selftest":
        return selftest()
    if not a.port:
        ap.error("--port is required")
    b = Board(a.port, a.baud)
    if a.cmd == "ping":
        print("version 0x%04X" % b.ping())
    elif a.cmd == "status":
        s = b.read(REGS["status"])
        print("status 0x%04X: codec init %s, codec NAK %s, PLL locked %s; level in %d, out %d" % (
            s, "done" if s & 1 else "pending", "YES" if s & 2 else "no", "yes" if s & 4 else "NO",
            b.read(REGS["level_in"]), b.read(REGS["level_out"])))
    elif a.cmd == "read":
        print("0x%04X" % b.read(num(a.args[0])))
    elif a.cmd == "write":
        b.write(num(a.args[0]), num(a.args[1]))
    elif a.cmd == "set":
        for k, v in parse_assignments(a.args).items():
            b.write(REGS[k], v)
    elif a.cmd == "preset":
        regs = {k: 0 for k in list(REGS)[:15]}
        regs.update(PRESETS[a.args[0]])
        for k, v in regs.items():
            b.write(REGS[k], v)
        print("preset '%s' loaded" % a.args[0])
    elif a.cmd == "codec":
        b.codec(num(a.args[0]), num(a.args[1]))
    elif a.cmd == "dump":
        for k, r in REGS.items():
            try:
                print("%-15s 0x%02X = 0x%04X" % (k, r, b.read(r)))
            except IOError as e:
                print("%-15s 0x%02X : %s" % (k, r, e))


if __name__ == "__main__":
    sys.exit(main())
