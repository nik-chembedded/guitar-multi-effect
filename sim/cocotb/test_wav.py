"""
test_wav.py - real guitar audio through FX_chain, one preset per pass.

Reads sim/audio/<GME_WAV_SAMPLE>.wav (default the_lick_e_minor), processes the
first GME_WAV_SECONDS seconds (default 1.0) with every preset and writes
sim/out/cocotb_wav/<sample>_<preset>.wav. Checks: dry is bit-exact, no output
is X, no wrap-around, and the tremolo presets have no gain clicks.
"""
import os
import sys
from pathlib import Path

import cocotb

from fxdriver import CHORUS, DIST, ECHO, OD, REVERB, TREM, FxChain, find_latency

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "sim" / "tools"))
import wavconv  # noqa: E402  (stdlib-only WAV helpers)

SAMPLE = os.environ.get("GME_WAV_SAMPLE", "the_lick_e_minor")
SECONDS = float(os.environ.get("GME_WAV_SECONDS", "1.0"))
OUT = Path(os.environ.get("GME_WAV_OUT", ROOT / "sim" / "out" / "cocotb_wav"))

# same register values as sim/run_wav.sh
PRESETS = {
    "dry":          dict(effects_enable=0),
    "overdrive":    dict(effects_enable=OD, od_drive=4000, od_gain=3),
    "dist_medium":  dict(effects_enable=DIST, dist_type=1, dist_mix=255),
    "tremolo":      dict(effects_enable=TREM, trem_wave=0, trem_depth=200),
    "tremolo_saw":  dict(effects_enable=TREM, trem_wave=7, trem_depth=200),
    "chorus":       dict(effects_enable=CHORUS, chorus_level=40000, chorus_depth=400, chorus_rate=40),
    "echo":         dict(effects_enable=ECHO, echo_time=14400, echo_level=26000, echo_repeat=100),
    "reverb":       dict(effects_enable=REVERB, reverb_type=2, reverb_mix=100),
}


def load_input():
    x, rate = wavconv.read_wav(str(ROOT / "sim" / "audio" / (SAMPLE + ".wav")))
    x = wavconv.resample(x, rate, 48000)[: int(SECONDS * 48000)]
    peak = max(abs(v) for v in x) or 1.0
    return [round(v * 16000 / peak) for v in x]


def write_wav(path, samples):
    import array
    import wave
    a = array.array("h", [max(-32768, min(32767, s)) for s in samples])
    if sys.byteorder == "big":
        a.byteswap()
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(48000)
        w.writeframes(a.tobytes())


def max_gain_step(x, y, lat, min_level=3000):
    g = {i: y[i + lat] / x[i] for i in range(len(x) - lat) if abs(x[i]) > min_level}
    return max((abs(g[i] - g[i - 1]) for i in g if i - 1 in g), default=0.0)


@cocotb.test()
async def test_wav_presets(dut):
    OUT.mkdir(parents=True, exist_ok=True)
    x = load_input()
    dut._log.info("%s: %d samples (%.2f s)", SAMPLE, len(x), len(x) / 48000)
    fx = FxChain(dut)
    await fx.start()
    lat = None
    for name, regs in PRESETS.items():
        fx.set(**{**{k: 0 for k in PRESETS["chorus"]}, **regs})
        await fx.run([0] * 64)                       # let the previous preset settle
        y = await fx.run(x, tail=4800)
        assert all(v is not None for v in y[16:]), "%s: X/U in the output" % name
        y = [v or 0 for v in y]
        write_wav(OUT / ("%s_%s.wav" % (SAMPLE, name)), y)
        jumps = sum(1 for i in range(1, len(y)) if abs(y[i] - y[i - 1]) > 30000)
        assert jumps == 0, "%s: %d wrap-around glitches" % (name, jumps)
        if name == "dry":
            lat = find_latency(x, y)
            assert y[lat:lat + len(x)] == x, "dry is not bit-exact"
        if name.startswith("tremolo"):
            step = max_gain_step(x, y, lat)
            assert step < 0.05, "%s: gain click, step %.3f" % (name, step)
            dut._log.info("%s: largest 1-sample gain step %.3f", name, step)
        dut._log.info("%-12s peak %5d -> %s", name, max(abs(v) for v in y), OUT / ("%s_%s.wav" % (SAMPLE, name)))
