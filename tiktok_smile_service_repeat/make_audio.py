"""Генерация дерзкого вирусного трека BARH (112 BPM, 7 тактов = 15.000 с) + старых спокойных версий.

Главный трек audio/BARH_viral_112bpm.wav:
  0.00 – 1.82 с  «Рекламный джингл авиакомпании»: мажорный весёлый звонок + ксилофон/поп-аккорд
  1.82 – 2.14 с  СКРЕТЧ ВИНИЛА + tape-stop в короткий вакуум перед дропом
  2.14 – 12.86 с ТЯЖЁЛЫЙ КАЧАЮЩИЙ DARK-POP / HIP-HOP БИТ (112 BPM, C minor):
                 упругий 808-бас, жёсткий snare/clap, 16-е хэты, дерзкий синтезаторный плак,
                 открытие широкого пада на 8.57 с (показ 46×130 см в двух интерьерах)
 12.86 – 15.00 с Финальный удар под логотип BARH на чёрном

Запуск: ../.venv/bin/python make_audio.py
"""
import os
import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, sosfilt, fftconvolve

SR = 48000
rng = np.random.default_rng(11200)


def lp(x, fc, order=2):
    return sosfilt(butter(order, min(fc, SR * 0.48), 'low', fs=SR, output='sos'), x)


def hp(x, fc, order=2):
    return sosfilt(butter(order, max(fc, 15.0), 'high', fs=SR, output='sos'), x)


def bp(x, lo, hi, order=2):
    return sosfilt(butter(order, [max(lo, 15.0), min(hi, SR * 0.48)], 'band', fs=SR, output='sos'), x)


def midi_hz(m):
    return 440.0 * (2.0 ** ((m - 69) / 12.0))


def make_reverb(rev_l, rev_r, decay=0.38, cut=3800):
    n = len(rev_l)
    ir_n = int(1.5 * SR)
    t = np.arange(ir_n) / SR
    ir_l = lp(rng.standard_normal(ir_n), cut, 1) * np.exp(-t / decay)
    ir_r = lp(rng.standard_normal(ir_n), cut - 300, 1) * np.exp(-t / (decay + 0.03))
    ir_l[:int(0.015 * SR)] = 0
    ir_r[:int(0.017 * SR)] = 0
    ir_l /= (np.sqrt(np.sum(ir_l ** 2)) + 1e-9)
    ir_r /= (np.sqrt(np.sum(ir_r ** 2)) + 1e-9)
    return fftconvolve(rev_l, ir_l)[:n] * 0.36, fftconvolve(rev_r, ir_r)[:n] * 0.36


def build_viral_track(path='audio/BARH_viral_112bpm.wav'):
    BPM = 112
    BEAT = 60.0 / BPM                     # 0.535714 s
    BAR = 4 * BEAT                        # 2.142857 s
    BARS = 7
    DUR = BARS * BAR                      # 15.000000 s
    N = int((DUR + 1.5) * SR)

    L = np.zeros(N, np.float64)
    R = np.zeros(N, np.float64)
    RL = np.zeros(N, np.float64)
    RR = np.zeros(N, np.float64)

    def put(x, t0, pan=0.5, gain=1.0, rev=0.0):
        s = int(t0 * SR)
        if s >= N or s + len(x) <= 0:
            return
        if s < 0:
            x = x[-s:]
            s = 0
        e = min(N, s + len(x))
        seg = x[:e - s] * gain
        gl, gr = np.cos(pan * np.pi / 2), np.sin(pan * np.pi / 2)
        L[s:e] += seg * gl
        R[s:e] += seg * gr
        if rev > 0:
            RL[s:e] += seg * gl * rev
            RR[s:e] += seg * gr * rev

    # ---------------- 1) 0.00 - 1.82 s: ПРИТОРНО-ВЕСЁЛЫЙ РЕКЛАМНЫЙ ДЖИНГЛ (C major)
    def bell_pop(hz, d=0.42):
        n = int(d * SR)
        t = np.arange(n) / SR
        y = (np.sin(2 * np.pi * hz * t) * np.exp(-t / 0.16)
             + 0.30 * np.sin(2 * np.pi * 2 * hz * t) * np.exp(-t / 0.07)
             + 0.12 * np.sin(2 * np.pi * 3 * hz * t) * np.exp(-t / 0.03))
        return y * np.minimum(1.0, t / 0.003)

    # Весёлый авиа-звонок (C6 -> E6)
    put(bell_pop(1046.5, 0.55), 0.04, pan=0.55, gain=0.22, rev=0.35)
    put(bell_pop(1318.5, 0.65), 0.24, pan=0.45, gain=0.22, rev=0.35)

    # Пружинистый мажорный поп-рифф C-E-G-A-G-E-C
    jingle_notes = [(0.00, 72), (0.27, 76), (0.54, 79), (0.80, 81), (1.07, 79), (1.34, 76), (1.60, 72)]
    for t_j, m_j in jingle_notes:
        put(bell_pop(midi_hz(m_j), 0.32), t_j, pan=0.50, gain=0.24, rev=0.22)
    # Мажорный поп-аккорд (C-E-G) и лёгкий кик-щёлк
    jn = int(1.84 * SR)
    jt = np.arange(jn) / SR
    j_pad = sum(np.sin(2 * np.pi * midi_hz(m) * jt) for m in (60, 64, 67, 72)) * 0.07
    j_pad *= np.minimum(1.0, jt / 0.02) * np.minimum(1.0, np.maximum(1.84 - jt, 0) / 0.05)
    put(j_pad, 0.0, pan=0.5, gain=1.0, rev=0.25)

    # ---------------- 2) 1.82 - 2.14 s: ВИНТАЖНЫЙ СКРЕТЧ ПЛАСТИНКИ + ВАКУУМ ПЕРЕД ДРОПОМ
    sn = int(0.28 * SR)
    st = np.arange(sn) / SR
    # Быстрое движение иглы вперёд-назад по канавке (сверххарактерный scratch!)
    scrub_freq = 420.0 + 380.0 * np.sin(2 * np.pi * 14.5 * st) - 950.0 * (st / 0.28)
    scrub_freq = np.maximum(65.0, scrub_freq)
    scratch = np.tanh(2.4 * np.sin(2 * np.pi * np.cumsum(scrub_freq) / SR))
    scratch = bp(scratch, 220, 4600, 2)
    scratch_env = np.sin(np.pi * st / 0.28) ** 0.7 * (1.0 - 0.55 * (st / 0.28))
    crackle = bp(rng.standard_normal(sn), 1800, 7500, 2) * 0.25 * (1.0 - st / 0.28)
    put((scratch * 0.55 + crackle) * scratch_env, 1.82, pan=0.5, gain=0.95, rev=0.18)

    # ---------------- 3) 2.14 - 15.00 s: КАЧАЮЩИЙ DARK-POP / HIP-HOP БИТ (112 BPM, C minor)
    def punch_kick():
        n = int(0.32 * SR)
        t = np.arange(n) / SR
        f = 44.0 + 135.0 * np.exp(-t / 0.020)
        body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.11)
        click = bp(rng.standard_normal(n), 1500, 4800, 2) * np.exp(-t / 0.005) * 0.25
        return np.tanh((body + click) * 1.45) * 0.85 * np.minimum(1.0, t / 0.0015)

    def hard_clap_snare():
        n = int(0.20 * SR)
        t = np.arange(n) / SR
        tone = np.sin(2 * np.pi * 195 * t) * np.exp(-t / 0.022) * 0.55
        noise = bp(rng.standard_normal(n), 1100, 6200, 2) * np.exp(-t / 0.055) * 0.70
        clap_double = bp(rng.standard_normal(n), 1600, 5200, 2) * np.exp(-np.maximum(t - 0.014, 0) / 0.04) * (t >= 0.014) * 0.35
        return (tone + noise + clap_double) * np.minimum(1.0, t / 0.0015)

    def crisp_hat(dur=0.055, vel=1.0):
        n = int(dur * SR)
        t = np.arange(n) / SR
        return hp(rng.standard_normal(n), 7200, 2) * np.exp(-t / (dur * 0.28)) * vel

    def bass_808(midi, dur, gain=0.55):
        n = int(dur * SR)
        t = np.arange(n) / SR
        f = midi_hz(midi)
        # Небольшая горка на атаке + плотный гармонический саб
        f_env = f * (1.0 + 0.55 * np.exp(-t / 0.014))
        ph = 2 * np.pi * np.cumsum(f_env) / SR
        raw = np.sin(ph) + 0.38 * np.sin(2 * ph) + 0.18 * np.sin(3 * ph)
        sat = lp(np.tanh(raw * 1.65), 240, 2)
        env = np.minimum(1.0, t / 0.008) * np.exp(-t / max(0.32, dur * 0.85)) * np.minimum(1.0, np.maximum(dur - t, 0) / 0.04)
        return sat * env * gain

    def dark_pluck(midi, dur=0.30, gain=0.22):
        n = int(dur * SR)
        t = np.arange(n) / SR
        f = midi_hz(midi)
        ph = (f * t) % 1.0
        saw = (2.0 * ph - 1.0) + 0.5 * (2.0 * ((f * 1.005 * t) % 1.0) - 1.0)
        y = lp(saw, 1800, 2) * np.exp(-t / 0.09)
        return y * np.minimum(1.0, t / 0.003) * gain

    K = punch_kick()
    SN = hard_clap_snare()

    # Ударный грув по тактам 1..5 (2.14 -> 12.86 s)
    kick_beats = [0.0, 0.75, 1.5, 2.5, 3.25]
    bass_prog = [
        (1, [(0.0, 1.4, 36), (1.5, 0.9, 36), (2.5, 0.7, 39), (3.25, 0.7, 34)]),  # Cm -> Eb -> Bb
        (2, [(0.0, 1.4, 36), (1.5, 0.9, 36), (2.5, 0.7, 41), (3.25, 0.7, 39)]),  # Cm -> F -> Eb
        (3, [(0.0, 1.4, 32), (1.5, 0.9, 32), (2.5, 0.7, 34), (3.25, 0.65, 31)]), # Ab -> Bb -> G
        (4, [(0.0, 1.4, 36), (1.5, 0.9, 36), (2.5, 0.7, 39), (3.25, 0.7, 34)]),  # CHORUS LOFT
        (5, [(0.0, 1.4, 32), (1.5, 0.9, 32), (2.5, 0.7, 34), (3.25, 0.7, 31)]),  # GALLERY
    ]
    for b in range(1, 6):
        tb = b * BAR
        for kb in kick_beats:
            put(K, tb + kb * BEAT, pan=0.5, gain=0.72, rev=0.04)
        for sb in (1.0, 3.0):
            put(SN, tb + sb * BEAT, pan=0.51, gain=0.46, rev=0.28)
        for hb in np.arange(0.0, 4.0, 0.5):
            vel = 0.14 if hb % 1.0 == 0 else 0.09
            put(crisp_hat(0.05, vel), tb + hb * BEAT, pan=0.45, gain=1.0, rev=0.14)
        # Триплетная дробь хэтов в конце Bar 3 прямо перед показом 46×130 см
        if b == 3:
            for j in range(4):
                put(crisp_hat(0.04, 0.13 + 0.02 * j), tb + (3.5 + j * 0.125) * BEAT, pan=0.54, gain=1.0, rev=0.12)

    for b, seq in bass_prog:
        tb = b * BAR
        for sb, sdur, smidi in seq:
            put(bass_808(smidi, sdur * BEAT, gain=0.48), tb + sb * BEAT, pan=0.5, gain=1.0, rev=0.02)

    # Дерзкий dark-pop синт-плак поверх грува (Cm: C4, Eb4, G4, Bb4)
    riff = [(0.0, 60), (0.5, 63), (1.0, 67), (1.5, 63), (2.0, 70), (2.5, 67), (3.0, 63), (3.5, 62)]
    for b in range(1, 6):
        tb = b * BAR
        for rb, rm in riff:
            put(dark_pluck(rm, 0.24, 0.14 if b < 4 else 0.17), tb + rb * BEAT, pan=0.44 if rb % 1 == 0 else 0.56, gain=1.0, rev=0.35)

    # Широкий хорусовый пад на показе двух интерьеров (Bars 4–5: 8.57 – 12.86 s)
    for b, notes in [(4, [48, 55, 63, 67]), (5, [44, 51, 60, 67])]:
        pn = int((BAR + 0.2) * SR)
        pt = np.arange(pn) / SR
        pad_w = np.zeros(pn)
        for m in notes:
            f = midi_hz(m)
            pad_w += lp((2 * ((f * pt) % 1) - 1) + (2 * ((f * 1.006 * pt) % 1) - 1), 1600, 2) * 0.032
        pad_w *= np.minimum(1.0, pt / 0.06) * np.minimum(1.0, np.maximum(BAR + 0.2 - pt, 0) / 0.15)
        put(pad_w, b * BAR, pan=0.5, gain=0.95, rev=0.35)

    # Краш-свип при входе в интерьеры (8.57 s)
    cn = int(0.85 * SR)
    ct = np.arange(cn) / SR
    crash = hp(rng.standard_normal(cn), 3400, 2) * np.exp(-ct / 0.26) * 0.11
    put(crash, 4 * BAR, pan=0.5, gain=1.0, rev=0.45)

    # ---------------- 4) 12.86 - 15.00 s (Bar 6): ФИНАЛ BARH — МОЩНЫЙ УДАР + ХВОСТ
    put(K, 6 * BAR, pan=0.5, gain=0.80, rev=0.05)
    put(SN, 6 * BAR, pan=0.5, gain=0.40, rev=0.45)
    put(bass_808(36, 3.6 * BEAT, gain=0.52), 6 * BAR, pan=0.5, gain=1.0, rev=0.08)

    wl, wr = make_reverb(RL, RR)
    mix = np.column_stack([L + wl, R + wr])[:int(DUR * SR)]
    fo_n = int(0.42 * SR)
    mix[-fo_n:] *= (np.linspace(1.0, 0.0, fo_n) ** 1.5)[:, None]
    pk = np.max(np.abs(mix)) + 1e-9
    if pk > 0.88:
        mix = np.tanh(mix * (0.88 / pk) * 1.15) * 0.88

    os.makedirs(os.path.dirname(path), exist_ok=True)
    wavfile.write(path, SR, np.clip(mix * 32767, -32767, 32767).astype(np.int16))
    rms = 20 * np.log10(np.sqrt(np.mean(mix ** 2)) + 1e-9)
    print(f'written {path}: {len(mix)/SR:.3f}s, peak={np.abs(mix).max():.3f}, RMS={rms:.1f} dBFS')


if __name__ == '__main__':
    build_viral_track()
