"""Синтез меланхоличного хитового саундтрека для BARH — «SMILE SERVICE REPEAT» (92 BPM, 15.65 с).

Настроение: тёплый альт-R&B / инди-поп (Cm9 -> Abmaj7 -> Fm9 -> G7sus4):
  - бархатные тёплые клавиши (Rhodes / felt pad) с лёгкой плёночной теплотой
  - запоминающийся гитарно-колокольный мотив с мягким стерео-дилеем
  - глубокий тёплый саб-бас и мягкий деликатный грув (без резких скачков и агрессии)
"""
import os
import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, lfilter

SR = 48000
BPM = 92.0
BEAT = 60.0 / BPM             # 0.652174 s
BAR = 4 * BEAT                # 2.608696 s
DUR = 6 * BAR                 # 15.652174 s
N = int(round(DUR * SR))

rng = np.random.default_rng(92)


def add(buf, t0, sig, gain=1.0, pan=0.0):
    i0 = int(round(t0 * SR))
    if i0 >= N or i0 + len(sig) <= 0:
        return
    s0 = max(0, -i0)
    d0 = max(0, i0)
    ln = min(len(sig) - s0, N - d0)
    chunk = sig[s0:s0 + ln] * gain
    lg = np.cos((pan + 1.0) * np.pi / 4.0)
    rg = np.sin((pan + 1.0) * np.pi / 4.0)
    buf[d0:d0 + ln, 0] += chunk * lg
    buf[d0:d0 + ln, 1] += chunk * rg


def lp(x, fc):
    b, a = butter(2, min(0.95, fc / (0.5 * SR)), btype='low')
    return lfilter(b, a, x)


def bp(x, f0, f1):
    b, a = butter(2, [max(0.002, f0 / (0.5 * SR)), min(0.95, f1 / (0.5 * SR))], btype='band')
    return lfilter(b, a, x)


def warm_rhodes(freq, dur):
    """Тёплое электропиано с мягкой атакой и бархатным телом."""
    t = np.arange(int(dur * SR)) / SR
    vib = 1.0 + 0.0014 * np.sin(2 * np.pi * 3.8 * t)
    f = freq * vib
    body = (
        0.72 * np.sin(2 * np.pi * f * t)
        + 0.20 * np.sin(2 * np.pi * f * 2.0 * t) * np.exp(-t / 0.65)
        + 0.08 * np.sin(2 * np.pi * f * 3.0 * t) * np.exp(-t / 0.14)
    )
    tine = np.sin(2 * np.pi * f * 4.0 * t) * np.exp(-t / 0.035) * 0.06
    env = (1.0 - np.exp(-t / 0.022)) * np.exp(-t / max(0.9, dur * 0.85))
    fade_out = np.minimum(1.0, (dur - t) / 0.06)
    return lp((body + tine) * env * fade_out, 2400.0)


def hook_pluck(freq, dur=1.25):
    """Запоминающийся атмосферный инди-мотив (гитара / стеклянный плак)."""
    t = np.arange(int(dur * SR)) / SR
    f = freq * (1.0 + 0.001 * np.sin(2 * np.pi * 4.5 * t))
    sig = (
        0.65 * np.sin(2 * np.pi * f * t)
        + 0.25 * np.sin(2 * np.pi * f * 2.0 * t) * np.exp(-t / 0.35)
        + 0.10 * np.sin(2 * np.pi * f * 3.0 * t) * np.exp(-t / 0.12)
    )
    env = (1.0 - np.exp(-t / 0.008)) * np.exp(-t / 0.42)
    return lp(sig * env, 3200.0) * 0.42


def soft_sub_bass(freq, dur):
    t = np.arange(int(dur * SR)) / SR
    sub = np.sin(2 * np.pi * freq * t) * 0.82 + np.sin(2 * np.pi * freq * 2.0 * t) * 0.18
    env = np.minimum(1.0, t / 0.045) * np.minimum(1.0, (dur - t) / 0.08)
    return np.tanh(sub * 1.15) * env * 0.55


def heartbeat_kick():
    """Мягкий глубокий кик без резкого щелчка."""
    dur = 0.42
    t = np.arange(int(dur * SR)) / SR
    f = 42.0 + 68.0 * np.exp(-t / 0.032)
    ph = 2.0 * np.pi * np.cumsum(f) / SR
    sig = np.sin(ph) * (1.0 - np.exp(-t / 0.006)) * np.exp(-t / 0.18)
    return lp(sig, 180.0) * 0.78


def velvet_rimshot():
    """Тёплый приглушённый римшот/снеп."""
    dur = 0.20
    t = np.arange(int(dur * SR)) / SR
    nz = bp(rng.standard_normal(len(t)), 700, 3600) * np.exp(-t / 0.048) * 0.55
    wood = np.sin(2 * np.pi * 245 * t * np.exp(-t / 0.05)) * np.exp(-t / 0.022) * 0.45
    return lp(nz + wood, 4200.0) * 0.65


def brushed_hat():
    dur = 0.09
    t = np.arange(int(dur * SR)) / SR
    nz = bp(rng.standard_normal(len(t)), 4500, 10500)
    return nz * np.exp(-t / 0.024) * 0.22


def add_stereo_delay(buf, delay_s, fb=0.32):
    d = int(round(delay_s * SR))
    if d <= 0 or d >= N:
        return buf
    out = buf.copy()
    wet = lp(buf[:, 0], 2600.0) * fb
    wet_r = lp(buf[:, 1], 2200.0) * fb
    out[d:, 0] += wet_r[:-d] * 0.85
    out[d:, 1] += wet[:-d] * 0.85
    if 2 * d < N:
        out[2 * d:, 0] += wet[:-2 * d] * 0.35
        out[2 * d:, 1] += wet_r[:-2 * d] * 0.35
    return out


def main():
    os.makedirs('audio', exist_ok=True)
    buf = np.zeros((N, 2), np.float64)
    mel_buf = np.zeros((N, 2), np.float64)

    # Прогрессия: Cm9 -> Abmaj7 -> Fm9 -> G7sus4 -> Cm9 -> Cm9 (умиротворённо и цепляюще)
    chords = [
        # (bar_idx, root_bass, [chord_freqs])
        (0, 65.41, [130.81, 196.00, 233.08, 293.66, 311.13]),   # Cm9
        (1, 51.91, [103.83, 155.56, 196.00, 246.94, 311.13]),   # Abmaj7
        (2, 43.65, [174.61, 207.65, 261.63, 311.13, 392.00]),   # Fm9
        (3, 49.00, [146.83, 196.00, 261.63, 293.66, 349.23]),   # G7sus4 -> G
        (4, 65.41, [130.81, 196.00, 233.08, 293.66, 311.13]),   # Cm9
        (5, 65.41, [130.81, 196.00, 233.08, 311.13]),           # Cm (финальный вздох)
    ]

    # Запоминающийся 8-нотный инди-поп мотив в C minor (работает как хук!)
    motif = [
        (0.0, 392.00),     # G4
        (0.75, 311.13),    # Eb4
        (1.5, 293.66),     # D4
        (2.0, 261.63),     # C4
        (2.5, 466.16),     # Bb4
        (3.25, 392.00),    # G4
    ]

    for b_idx, f_bass, ch_freqs in chords:
        bs = b_idx * BAR
        # Тёплое перебирание аккорда с мягким страм-смещением
        for j, cf in enumerate(ch_freqs):
            add(buf, bs + j * 0.032, warm_rhodes(cf, BAR + 0.35),
                gain=0.23, pan=-0.28 + 0.14 * j)

        # Саб-бас со 2-го такта (плавный эмоциональный подъём)
        if b_idx >= 1 and b_idx < 5:
            add(buf, bs, soft_sub_bass(f_bass, BAR - 0.04), gain=0.78)
        elif b_idx == 0:
            add(buf, bs + 2.0 * BEAT, soft_sub_bass(f_bass, 2.0 * BEAT), gain=0.45)
        else:
            add(buf, bs, soft_sub_bass(f_bass, BAR - 0.12), gain=0.62)

        # Хук-мотив с 1-го по 5-й такт
        if b_idx < 5:
            for m_beat, mf in motif:
                # На 2-м и 4-м такте чуть меняем верхнюю ноту для развития
                if b_idx in (1, 3) and abs(m_beat - 2.5) < 0.01:
                    mf = 523.25 if b_idx == 1 else 466.16
                add(mel_buf, bs + m_beat * BEAT, hook_pluck(mf, 1.35),
                    gain=0.46 if b_idx >= 1 else 0.36, pan=0.14)

        # Мягкий, качающий сердцебиение-грув со 2-го такта (Bars 1-4)
        if 1 <= b_idx <= 4:
            for off, g in [(0.0, 0.85), (1.75 * BEAT, 0.56), (2.5 * BEAT, 0.72)]:
                add(buf, bs + off, heartbeat_kick(), gain=g)
            for off in (1.0 * BEAT, 3.0 * BEAT):
                add(buf, bs + off, velvet_rimshot(), gain=0.58, pan=-0.08)
            for i in range(8):
                add(buf, bs + i * 0.5 * BEAT, brushed_hat(),
                    gain=0.30 if i % 2 == 0 else 0.17, pan=0.22 if i % 2 else -0.18)

    # Тонкий тёплый виниловый/воздушный слой на весь трек (едва слышимый уют)
    air = bp(rng.standard_normal(N), 240, 2400) * 0.012
    buf[:, 0] += air
    buf[:, 1] += air

    # Стерео-дилей на мелодию (3/8 ноты = 0.75 * BEAT)
    mel_wet = add_stereo_delay(mel_buf, 0.75 * BEAT, fb=0.38)
    buf += mel_wet

    # Финальное мягкое затухание за последние 0.65 с
    fade_n = int(0.65 * SR)
    buf[-fade_n:] *= np.linspace(1.0, 0.0, fade_n)[:, None] ** 1.4

    mx = np.max(np.abs(buf))
    if mx > 0.0:
        buf = np.tanh(buf * (0.68 / mx) * 1.08) * 0.72

    pcm = np.clip(buf * 32767.0, -32767, 32767).astype(np.int16)
    out = 'audio/BARH_melancholic_92bpm.wav'
    wavfile.write(out, SR, pcm)
    rms = 20 * np.log10(np.sqrt(np.mean(buf ** 2)) + 1e-9)
    print(f'written {out}: {DUR:.3f}s, peak={np.max(np.abs(buf)):.3f}, RMS={rms:.1f} dBFS')


if __name__ == '__main__':
    main()
