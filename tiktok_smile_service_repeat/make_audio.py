"""Синтез саундтрека BARH — «SMILE SERVICE REPEAT» (114 BPM, 14.74 с).

0.00 - 2.11 с (Bar 0): Атмосфера полёта + пролёт лайнера -> фирменный самолётный сигнал «DING-DONG» (1.58-2.02 с) -> пауза-вакуум
2.11 - 14.74 с (Bars 1-6): Плотный качающий dark-pop / hip-hop бит в C minor (114 BPM) под смену планов, интерьеров и финальный логотип BARH.
"""
import os
import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, lfilter

SR = 48000
BPM = 114.0
BEAT = 60.0 / BPM             # 0.526316 s
BAR = 4 * BEAT                # 2.105263 s
DUR = 7 * BAR                 # 14.736842 s
N = int(round(DUR * SR))

rng = np.random.default_rng(114)


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


def hp(x, fc):
    b, a = butter(2, max(0.002, fc / (0.5 * SR)), btype='high')
    return lfilter(b, a, x)


def kick_808(dur=0.44, f_end=43.0):
    t = np.arange(int(dur * SR)) / SR
    f = f_end + 112.0 * np.exp(-t / 0.022)
    ph = 2.0 * np.pi * np.cumsum(f) / SR
    body = np.sin(ph) * np.exp(-t / 0.19)
    click = lp(rng.standard_normal(len(t)), 2400) * np.exp(-t / 0.004) * 0.35
    sig = np.tanh((body * 1.45 + click) * 1.25) * np.exp(-t / 0.25)
    return sig * 0.90


def crisp_snare(dur=0.22):
    t = np.arange(int(dur * SR)) / SR
    nz = bp(rng.standard_normal(len(t)), 900, 7600) * np.exp(-t / 0.070)
    tone = np.sin(2 * np.pi * 188 * t * np.exp(-t / 0.07)) * np.exp(-t / 0.032) * 0.50
    return np.tanh((nz * 0.85 + tone) * 1.15) * 0.78


def hihat(closed=True):
    dur = 0.062 if closed else 0.26
    t = np.arange(int(dur * SR)) / SR
    nz = hp(rng.standard_normal(len(t)), 7400)
    tau = 0.015 if closed else 0.090
    return nz * np.exp(-t / tau) * (0.28 if closed else 0.34)


def cabin_chime(freq, dur=0.52):
    """Мягкий двухтоновый колокольчик бортового оповещения (seatbelt chime)."""
    t = np.arange(int(dur * SR)) / SR
    env = (1.0 - np.exp(-t / 0.004)) * np.exp(-t / 0.14)
    sig = (
        0.72 * np.sin(2 * np.pi * freq * t)
        + 0.22 * np.sin(2 * np.pi * freq * 2.0 * t) * np.exp(-t / 0.06)
        + 0.08 * np.sin(2 * np.pi * freq * 3.0 * t) * np.exp(-t / 0.03)
    )
    return sig * env


def dark_bass_note(freq, dur):
    t = np.arange(int(dur * SR)) / SR
    saw = 2.0 * ((t * freq) % 1.0) - 1.0
    sub = np.sin(2 * np.pi * freq * t)
    sig = lp(saw, 280.0) * 0.45 + sub * 0.72
    env = np.minimum(1.0, t / 0.014) * np.minimum(1.0, (dur - t) / 0.025)
    return np.tanh(sig * 1.35) * env * 0.62


def dark_pluck(freq, dur=0.45):
    t = np.arange(int(dur * SR)) / SR
    s1 = np.sin(2 * np.pi * freq * t)
    s2 = np.sin(2 * np.pi * freq * 2.0 * t) * np.exp(-t / 0.08) * 0.35
    s3 = lp(2.0 * ((t * freq * 1.002) % 1.0) - 1.0, 1800) * np.exp(-t / 0.11) * 0.25
    env = (1.0 - np.exp(-t / 0.005)) * np.exp(-t / 0.16)
    return (s1 + s2 + s3) * env * 0.30


def main():
    os.makedirs('audio', exist_ok=True)
    buf = np.zeros((N, 2), np.float64)

    # ---------------- BAR 0 (0.00 - 2.11 с): Пролёт самолёта + DING-DONG
    n0 = int(round((BAR - 0.06) * SR))
    t0 = np.arange(n0) / SR
    # Гул турбин + воздушный поток с плавным Доплер-свипом
    raw_jet = rng.standard_normal(n0)
    jet_lo = bp(raw_jet, 85, 460)
    jet_hi = bp(raw_jet, 240, 1300)
    prog = np.clip(t0 / BAR, 0.0, 1.0)
    jet_noise = jet_lo * (1.0 - 0.55 * prog) + jet_hi * (0.20 + 0.80 * prog)
    jet_hum = np.sin(2 * np.pi * (110.0 - 18.0 * (t0 / BAR)) * t0) * 0.18
    fly_env = np.sin(np.pi * np.clip(t0 / (BAR - 0.06), 0, 1)) ** 0.75
    pad = (
        np.sin(2 * np.pi * 130.81 * t0) * 0.15
        + np.sin(2 * np.pi * 196.00 * t0) * 0.12
        + np.sin(2 * np.pi * 293.66 * t0) * 0.08
    ) * np.minimum(1.0, t0 / 0.25) * np.clip(1.0 - (t0 - (BAR - 0.22)) / 0.16, 0, 1)
    sky_sig = (jet_noise * 0.26 + jet_hum) * fly_env + pad
    buf[:n0, 0] += sky_sig * 0.78
    buf[:n0, 1] += sky_sig * 0.78

    # Культовый двойной «DING-DONG» самолёта прямо перед дропом
    add(buf, 1.54, cabin_chime(880.0, 0.36), gain=0.46, pan=-0.10)   # A5
    add(buf, 1.76, cabin_chime(659.25, 0.44), gain=0.52, pan=0.10)   # E5

    # Короткий вакуум (2.04 - 2.11)
    vac0, vac1 = int(round(2.04 * SR)), int(round(BAR * SR))
    buf[vac0:vac1] *= np.linspace(1.0, 0.0, vac1 - vac0)[:, None] * 0.04

    # ---------------- BARS 1 - 6 (2.11 - 14.74 с): ПЛОТНЫЙ DARK-POP БИТ (114 BPM)
    roots = [
        (1, 65.41),   # C2  (Bar 1 - Upper painting drop)
        (2, 51.91),   # G#1 (Bar 2 - Lower painting switch)
        (3, 43.65),   # F1  (Bar 3 - Loft 46x130)
        (4, 49.00),   # G1  (Bar 4 - Loft -> Gallery)
        (5, 65.41),   # C2  (Bar 5 - Gallery 46x130)
        (6, 65.41),   # C2  (Bar 6 - BARH finale)
    ]

    for b_idx, f_root in roots:
        bs = b_idx * BAR
        add(buf, bs, dark_bass_note(f_root, BAR - 0.03), gain=0.86)

        if b_idx < 6:
            # Качающий паттерн кика: 0, 1.5, 2.5, 3.25
            for off, g in [(0.0, 0.96), (1.5 * BEAT, 0.72), (2.5 * BEAT, 0.88), (3.25 * BEAT, 0.62)]:
                add(buf, bs + off, kick_808(0.42), gain=g)
            # Снэр/клэп на 2 и 4
            for off in (1.0 * BEAT, 3.0 * BEAT):
                add(buf, bs + off, crisp_snare(), gain=0.72, pan=-0.04)
                add(buf, bs + off, crisp_snare(), gain=0.35, pan=0.16)
            # Хэты 8-ми и быстрая трещотка перед сменой такта
            for i in range(8):
                is_open = (i == 7 and b_idx in (2, 4))
                add(buf, bs + i * 0.5 * BEAT, hihat(not is_open),
                    gain=0.40 if i % 2 == 0 else 0.25, pan=0.22 if i % 2 else -0.18)
            if b_idx in (1, 3, 5):
                add(buf, bs + 3.75 * BEAT, hihat(True), gain=0.34, pan=0.12)

            # Минорные плаки (C minor: C4, Eb4, G4, Bb4)
            mel = [261.63, 311.13, 392.00, 311.13, 466.16, 392.00, 311.13, 293.66]
            for i, mf in enumerate(mel):
                if i in (0, 2, 3, 5, 6):
                    add(buf, bs + i * 0.5 * BEAT, dark_pluck(mf, 0.42),
                        gain=0.44 if i == 0 else 0.30, pan=-0.20 if i % 2 == 0 else 0.22)
        else:
            # Финальный удар на BARH (12.63 с)
            add(buf, bs, kick_808(0.85, 38.0), gain=1.05)
            add(buf, bs, crisp_snare(0.32), gain=0.50)
            add(buf, bs, dark_pluck(523.25, 0.90), gain=0.45)
            # Затухание за 60 мс до 14.74 с для чистого лупа
            fade_len = int(0.06 * SR)
            buf[-fade_len:] *= np.linspace(1.0, 0.0, fade_len)[:, None]

    # Перебивочный вздох/краш на дропе (2.11), лофте (6.32) и галерее (9.47)
    for t_hit in (BAR, 3 * BAR, 4.5 * BAR, 6 * BAR):
        t_c = np.arange(int(0.65 * SR)) / SR
        cr = hp(rng.standard_normal(len(t_c)), 4800) * np.exp(-t_c / 0.18) * 0.26
        add(buf, t_hit, cr, gain=0.80)

    mx = np.max(np.abs(buf))
    if mx > 0.0:
        buf = np.tanh(buf * (0.68 / mx) * 1.12) * 0.72

    pcm = np.clip(buf * 32767.0, -32767, 32767).astype(np.int16)
    out = 'audio/BARH_sky_114bpm.wav'
    wavfile.write(out, SR, pcm)
    rms = 20 * np.log10(np.sqrt(np.mean((buf) ** 2)) + 1e-9)
    print(f'written {out}: {DUR:.3f}s, peak={np.max(np.abs(buf)):.3f}, RMS={rms:.1f} dBFS')


if __name__ == '__main__':
    main()
