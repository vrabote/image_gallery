"""Генерация двух спокойных кинематографичных саундтреков под оба сценария BARH:
  1) audio/BARH_contrast_76bpm.wav — 76 BPM, 7 тактов = 22.105 с (Сценарий Б: Контраст)
  2) audio/BARH_arttok_72bpm.wav   — 72 BPM, 6 тактов = 20.000 с (Сценарий В: Чистый ArtTok)

Запуск: ../.venv/bin/python make_audio.py
"""
import os
import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, sosfilt, fftconvolve

SR = 48000
rng = np.random.default_rng(46130)


def lp(x, fc, order=2):
    return sosfilt(butter(order, min(fc, SR * 0.48), 'low', fs=SR, output='sos'), x)


def hp(x, fc, order=2):
    return sosfilt(butter(order, max(fc, 15.0), 'high', fs=SR, output='sos'), x)


def bp(x, lo, hi, order=2):
    return sosfilt(butter(order, [max(lo, 15.0), min(hi, SR * 0.48)], 'band', fs=SR, output='sos'), x)


def midi_hz(m):
    return 440.0 * (2.0 ** ((m - 69) / 12.0))


def felt_piano(midi, dur, vel=1.0):
    """Мягкое камерное «felt piano» / тёплое Rhodes — чисто, без резкой синтетики."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = midi_hz(midi)
    body = np.sin(2 * np.pi * f * t) * np.exp(-t / max(1.3, dur * 0.85))
    warm2 = 0.22 * np.sin(2 * np.pi * (f * 2.0) * t) * np.exp(-t / 0.35)
    soft3 = 0.05 * np.sin(2 * np.pi * (f * 3.0) * t) * np.exp(-t / 0.12)
    att = np.minimum(1.0, t / 0.018)
    rel = np.minimum(1.0, np.maximum(dur - t, 0.0) / 0.25)
    return (body + warm2 + soft3) * att * rel * vel


def make_reverb(rev_l, rev_r, decay=0.65, cut=2400):
    n = len(rev_l)
    ir_n = int(2.2 * SR)
    t = np.arange(ir_n) / SR
    ir_l = lp(rng.standard_normal(ir_n), cut, 1) * np.exp(-t / decay)
    ir_r = lp(rng.standard_normal(ir_n), cut - 200, 1) * np.exp(-t / (decay + 0.05))
    ir_l[:int(0.025 * SR)] = 0
    ir_r[:int(0.028 * SR)] = 0
    ir_l /= (np.sqrt(np.sum(ir_l ** 2)) + 1e-9)
    ir_r /= (np.sqrt(np.sum(ir_r ** 2)) + 1e-9)
    return fftconvolve(rev_l, ir_l)[:n] * 0.44, fftconvolve(rev_r, ir_r)[:n] * 0.44


def build_track(path, bpm, bars, chords, bass_seq, with_drums=True, with_chime=True):
    beat = 60.0 / bpm
    bar = 4 * beat
    dur = bars * bar
    n = int((dur + 2.5) * SR)
    L = np.zeros(n, np.float64)
    R = np.zeros(n, np.float64)
    RL = np.zeros(n, np.float64)
    RR = np.zeros(n, np.float64)

    def put(x, t0, pan=0.5, gain=1.0, rev=0.0):
        s = int(t0 * SR)
        if s >= n or s + len(x) <= 0:
            return
        if s < 0:
            x = x[-s:]
            s = 0
        e = min(n, s + len(x))
        seg = x[:e - s] * gain
        gl, gr = np.cos(pan * np.pi / 2), np.sin(pan * np.pi / 2)
        L[s:e] += seg * gl
        R[s:e] += seg * gr
        if rev > 0:
            RL[s:e] += seg * gl * rev
            RR[s:e] += seg * gr * rev

    # Мягкий плёночный воздух
    air = bp(rng.standard_normal(n), 700, 4200, 1)
    air = air / (np.std(air) + 1e-9) * 0.0018
    L += air
    R += np.roll(air, 419)

    if with_chime:
        # Деликатный далёкий звонок салона на первом такте перехода к EXIT-> (t = 1 * bar + 0.18s)
        for dt_c, hz in [(0.0, 783.99), (0.42, 622.25)]:
            cn = int(1.4 * SR)
            ct = np.arange(cn) / SR
            ch = (np.sin(2 * np.pi * hz * ct) * np.exp(-ct / 0.45)
                  + 0.14 * np.sin(2 * np.pi * hz * 2 * ct) * np.exp(-ct / 0.16)) * np.minimum(1.0, ct / 0.006)
            put(ch, 1 * bar + 0.15 + dt_c, pan=0.54, gain=0.10, rev=0.65)

    for b_idx, b_len, notes, g in chords:
        t0 = b_idx * bar
        d_sec = b_len * bar
        for idx, m in enumerate(notes):
            pan = 0.40 + 0.20 * (idx / max(1, len(notes) - 1))
            put(felt_piano(m, d_sec + 0.8, vel=g), t0 + idx * 0.026, pan=pan, gain=1.0, rev=0.45)

    for b_idx, b_len, m, g in bass_seq:
        t0 = b_idx * bar
        d_sec = b_len * bar
        bn = int(d_sec * SR)
        bt = np.arange(bn) / SR
        f = midi_hz(m)
        sub = lp(np.sin(2 * np.pi * f * bt) + 0.22 * np.sin(2 * np.pi * 2 * f * bt), 155, 2)
        env = np.minimum(1.0, bt / 0.035) * np.exp(-bt / max(1.0, d_sec * 0.9)) * np.minimum(1.0, np.maximum(d_sec - bt, 0.0) / 0.12)
        put(sub * env, t0, pan=0.5, gain=g, rev=0.03)

    if with_drums:
        kn = int(0.35 * SR)
        kt = np.arange(kn) / SR
        k_wav = np.sin(2 * np.pi * np.cumsum(44 + 80 * np.exp(-kt / 0.035)) / SR) * np.exp(-kt / 0.12) * np.minimum(1.0, kt / 0.004)
        rn = int(0.14 * SR)
        rt = np.arange(rn) / SR
        r_wav = (np.sin(2 * np.pi * 390 * rt) * np.exp(-rt / 0.015) * 0.4
                 + bp(rng.standard_normal(rn), 950, 2900, 2) * np.exp(-rt / 0.035) * 0.5) * np.minimum(1.0, rt / 0.003)
        for b in range(1, bars - 1):
            # Пауза перед полным показом в интерьере на 3.8..4.0 такте
            for bt in (0.0, 1.5, 2.5):
                if b == 3 and bt > 2.0:
                    continue
                put(k_wav, b * bar + bt * beat, pan=0.5, gain=0.38, rev=0.04)
            for bt in (1.0, 3.0):
                if b == 3 and bt >= 3.0:
                    continue
                put(r_wav, b * bar + bt * beat, pan=0.52, gain=0.14, rev=0.35)

    # Тёплый глубокий удар в начале финального лого BARH
    fn = int(2.2 * SR)
    ft = np.arange(fn) / SR
    boom = np.sin(2 * np.pi * np.cumsum(38 + 38 * np.exp(-ft / 0.08)) / SR) * np.exp(-ft / 0.85)
    put(boom, (bars - 1) * bar, pan=0.5, gain=0.34, rev=0.20)

    wl, wr = make_reverb(RL, RR)
    mix = np.column_stack([L + wl, R + wr])[:int(dur * SR)]
    # Плавный fade-out последних 0.7 с
    fo_n = int(0.70 * SR)
    mix[-fo_n:] *= (np.linspace(1.0, 0.0, fo_n) ** 1.6)[:, None]
    pk = np.max(np.abs(mix)) + 1e-9
    if pk > 0.84:
        mix = np.tanh(mix * (0.84 / pk) * 1.12) * 0.84

    os.makedirs(os.path.dirname(path), exist_ok=True)
    wavfile.write(path, SR, np.clip(mix * 32767, -32767, 32767).astype(np.int16))
    rms = 20 * np.log10(np.sqrt(np.mean(mix ** 2)) + 1e-9)
    print(f'written {path}: {len(mix)/SR:.3f}s, peak={np.abs(mix).max():.3f}, RMS={rms:.1f} dBFS')


# 1) Сценарий Б — Контраст (76 BPM, 7 тактов = 22.105 s, C minor)
build_track(
    'audio/BARH_contrast_76bpm.wav',
    bpm=76,
    bars=7,
    chords=[
        (0.0, 1.0, [48, 55, 62, 63], 0.11),        # Cm(add9)
        (1.0, 1.0, [44, 51, 55, 60], 0.12),        # Abmaj7
        (2.0, 1.0, [41, 48, 55, 56], 0.13),        # Fm9
        (3.0, 0.9, [43, 50, 53, 58], 0.13),        # G7sus4
        (4.0, 1.0, [48, 55, 58, 63, 67], 0.15),    # Cm9 (вход в лофт)
        (5.0, 1.0, [44, 51, 55, 60, 67], 0.14),    # Abmaj7
        (6.0, 0.95, [48, 55, 58, 63], 0.13),       # Cm9 (BARH)
    ],
    bass_seq=[
        (0.0, 1.0, 36, 0.20),
        (1.0, 1.0, 32, 0.24),
        (2.0, 1.0, 29, 0.25),
        (3.0, 0.85, 31, 0.25),
        (4.0, 1.0, 36, 0.28),
        (5.0, 1.0, 32, 0.26),
        (6.0, 0.90, 36, 0.25),
    ],
    with_drums=True,
    with_chime=True,
)

# 2) Сценарий В — Чистый ArtTok / Галерея (72 BPM, 6 тактов = 20.000 s, F minor / Ab major)
build_track(
    'audio/BARH_arttok_72bpm.wav',
    bpm=72,
    bars=6,
    chords=[
        (0.0, 1.0, [53, 60, 63, 67, 68], 0.12),    # Fm9
        (1.0, 1.0, [49, 56, 60, 63, 68], 0.13),    # Dbmaj9
        (2.0, 1.0, [44, 51, 56, 60, 67], 0.13),    # Abmaj7
        (3.0, 1.0, [44, 51, 56, 60, 63, 67], 0.15),# Abmaj9 (вход в светлую галерею)
        (4.0, 1.0, [49, 56, 60, 65, 68], 0.14),    # Dbmaj7
        (5.0, 0.95, [53, 60, 63, 68], 0.13),       # Fm7 (BARH)
    ],
    bass_seq=[
        (0.0, 1.0, 41, 0.20),
        (1.0, 1.0, 37, 0.22),
        (2.0, 1.0, 32, 0.23),
        (3.0, 1.0, 32, 0.27),
        (4.0, 1.0, 37, 0.25),
        (5.0, 0.90, 41, 0.24),
    ],
    with_drums=False,
    with_chime=False,
)
