"""
cabir.py - shared helpers for the cabinet impulse responses (v2 step D3).

WAV I/O (PCM 16/24/32-bit, float32, WAVE_FORMAT_EXTENSIBLE; stereo is mixed to
mono), resampling to 48 kHz, RBJ biquads, trimming to the FIR length, loudness
normalisation and quantisation to the FPGA coefficient format.
Needs numpy only (runs in the WSL venv: ~/venvs/gme).
"""
import math
import struct

import numpy as np

FS = 48000
TAPS = 2048               # FIR length in the FPGA (42.7 ms at 48 kHz)
COEF_BITS = 18            # signed Q1.17 coefficients (one 18-bit DSP input)
FADE = 128                # fade-out when an IR is longer than TAPS
TARGET_GAIN = 0.5         # loudness after normalisation (-6 dB, headroom for resonances)


# ---------------------------------------------------------------- WAV I/O
def read_wav(path):
    """Return (samples as float64 in -1..1, mono, sample rate)."""
    with open(path, "rb") as f:
        b = f.read()
    if b[:4] != b"RIFF" or b[8:12] != b"WAVE":
        raise ValueError("%s: not a RIFF/WAVE file" % path)
    i, fmt, data = 12, None, None
    while i + 8 <= len(b):
        cid, size = b[i:i + 4], struct.unpack("<I", b[i + 4:i + 8])[0]
        body = b[i + 8:i + 8 + size]
        if cid == b"fmt ":
            tag, ch, sr, _, _, bits = struct.unpack("<HHIIHH", body[:16])
            if tag == 0xFFFE:                                   # extensible: real tag in the GUID
                tag = struct.unpack("<H", body[24:26])[0]
            fmt = (tag, ch, sr, bits)
        elif cid == b"data":
            data = body
        i += 8 + size + (size & 1)
    if fmt is None or data is None:
        raise ValueError("%s: no fmt/data chunk" % path)
    tag, ch, sr, bits = fmt
    if tag == 3 and bits == 32:
        x = np.frombuffer(data, dtype="<f4").astype(np.float64)
    elif tag == 1 and bits == 16:
        x = np.frombuffer(data, dtype="<i2") / 32768.0
    elif tag == 1 and bits == 24:
        u = np.frombuffer(data[:len(data) // 3 * 3], dtype=np.uint8).reshape(-1, 3).astype(np.int32)
        v = u[:, 0] | (u[:, 1] << 8) | (u[:, 2] << 16)
        x = np.where(v >= 1 << 23, v - (1 << 24), v) / float(1 << 23)
    elif tag == 1 and bits == 32:
        x = np.frombuffer(data, dtype="<i4") / float(1 << 31)
    else:
        raise ValueError("%s: unsupported WAV format tag %d, %d bit" % (path, tag, bits))
    x = x[:len(x) // ch * ch].reshape(-1, ch).mean(axis=1)
    return x, sr


def write_wav(path, x, sr=FS, bits=24):
    """Mono float -1..1 -> PCM WAV (16 or 24 bit)."""
    x = np.clip(np.asarray(x, dtype=np.float64), -1.0, 1.0 - 2.0 ** -(bits - 1))
    q = np.round(x * (1 << (bits - 1))).astype(np.int64)
    if bits == 16:
        data = q.astype("<i2").tobytes()
    else:
        u = q & 0xFFFFFF
        data = np.stack([u & 0xFF, (u >> 8) & 0xFF, (u >> 16) & 0xFF], axis=1).astype(np.uint8).tobytes()
    nb = bits // 8
    hdr = b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVE"
    hdr += b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, sr, sr * nb, nb, bits)
    hdr += b"data" + struct.pack("<I", len(data))
    with open(path, "wb") as f:
        f.write(hdr + data)


# ---------------------------------------------------------------- DSP
def resample(x, sr_in, sr_out=FS, half_width=32):
    """Windowed-sinc (Blackman) resampling; band-limited to the lower Nyquist."""
    if sr_in == sr_out:
        return np.asarray(x, dtype=np.float64)
    n_out = int(round(len(x) * sr_out / sr_in))
    cutoff = min(1.0, sr_out / sr_in)
    t = np.arange(n_out) * (sr_in / sr_out)
    k = np.arange(-half_width, half_width + 1)
    y = np.zeros(n_out)
    for i, ti in enumerate(t):
        idx = np.floor(ti).astype(int) + k
        ok = (idx >= 0) & (idx < len(x))
        d = ti - idx[ok]
        w = 0.42 + 0.5 * np.cos(np.pi * d / (half_width + 1)) + 0.08 * np.cos(2 * np.pi * d / (half_width + 1))
        y[i] = np.sum(x[idx[ok]] * cutoff * np.sinc(cutoff * d) * w)
    return y


def biquad(kind, f0, q, gain_db=0.0, fs=FS):
    """RBJ cookbook biquad -> (b, a) normalised to a0 = 1."""
    w = 2 * math.pi * f0 / fs
    alpha = math.sin(w) / (2 * q)
    A = 10 ** (gain_db / 40)
    c = math.cos(w)
    if kind == "lpf":
        b = [(1 - c) / 2, 1 - c, (1 - c) / 2]; a = [1 + alpha, -2 * c, 1 - alpha]
    elif kind == "hpf":
        b = [(1 + c) / 2, -(1 + c), (1 + c) / 2]; a = [1 + alpha, -2 * c, 1 - alpha]
    elif kind == "peak":
        b = [1 + alpha * A, -2 * c, 1 - alpha * A]; a = [1 + alpha / A, -2 * c, 1 - alpha / A]
    else:
        raise ValueError(kind)
    return np.array(b) / a[0], np.array(a) / a[0]


def lfilter(b, a, x):
    y = np.zeros(len(x))
    x1 = x2 = y1 = y2 = 0.0
    for n, xn in enumerate(x):
        yn = b[0] * xn + b[1] * x1 + b[2] * x2 - a[1] * y1 - a[2] * y2
        x2, x1, y2, y1 = x1, xn, y1, yn
        y[n] = yn
    return y


def response_db(h, freqs, fs=FS):
    """Magnitude response of an FIR in dB at the given frequencies."""
    n = np.arange(len(h))
    return np.array([20 * math.log10(max(1e-9, abs(np.sum(h * np.exp(-2j * np.pi * f * n / fs)))))
                     for f in freqs])


def trim(h, taps=TAPS, fade=FADE):
    """Drop leading silence (keep 4 samples before the onset), cut to `taps`
    with a half-cosine fade-out, zero-pad shorter IRs."""
    h = np.asarray(h, dtype=np.float64)
    onset = int(np.argmax(np.abs(h) > 1e-3 * np.max(np.abs(h))))
    h = h[max(0, onset - 4):]
    if len(h) > taps:
        h = h[:taps].copy()
        h[-fade:] *= 0.5 * (1 + np.cos(np.pi * np.arange(1, fade + 1) / fade))
    return np.concatenate([h, np.zeros(taps - len(h))])


def loudness(h, fs=FS):
    """RMS gain for a pink-ish guitar spectrum (1/f weighting, 80 Hz .. 8 kHz)."""
    nfft = 1 << 15
    H = np.abs(np.fft.rfft(h, nfft)) ** 2
    f = np.fft.rfftfreq(nfft, 1.0 / fs)
    w = np.where((f >= 80) & (f <= 8000), 1.0 / np.maximum(f, 1.0), 0.0)
    return math.sqrt(np.sum(H * w) / np.sum(w))


def normalise(h, target=TARGET_GAIN):
    return h * (target / loudness(h))


def quantise(h, bits=COEF_BITS):
    """float -> signed Q1.(bits-1) integers (clipped)."""
    full = 1 << (bits - 1)
    return np.clip(np.round(h * full), -full, full - 1).astype(np.int64)
