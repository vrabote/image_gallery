"""Синтез лиричной космической баллады в духе SPACE 1980-х годов (Ballad for Space Lovers / Just Blue).

76 BPM · 7 тактов · 22.11 с · C minor -> Eb major -> Ab major -> G7sus4 -> Cm:
  - широкие бархатные стерео-струны Solina / Juno с медленным космическим хорусом
  - нежные переливы электропиано (8-ми нотами, без диско-спешки)
  - поющий лиричный аналоговый Moog-лид с экспрессивным вибрато и длинным эхом
  - мягкий тёплый бас и деликатная балладная перкуссия 80-х
"""
import os
import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, lfilter

SR = 48000
BPM = 76.0
BEAT = 60.0 / BPM             # 0.789474 s
BAR = 4 * BEAT                # 3.157895 s
DUR = 7 * BAR                 # 22.105263 s
N = int(round(DUR * SR))

rng = np.random.default_rng(1981)


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


def solina_strings(freqs, dur):
    """Классический лиричный ансамбль струн 80-х (Solina / Juno chorus)."""
    n_c = int(dur * SR)
    t = np.arange(n_c) / SR
    left = np.zeros(n_c, np.float64)
    right = np.zeros(n_c, np.float64)
    for idx, f in enumerate(freqs):
        lfo1 = 1.0 + 0.0032 * np.sin(2 * np.pi * (0.38 + 0.07 * idx) * t)
        lfo2 = 1.0 + 0.0030 * np.sin(2 * np.pi * (0.52 + 0.06 * idx) * t + 1.7)
        s_l = 2.0 * ((np.cumsum(f * lfo1) / SR) % 1.0) - 1.0
        s_r = 2.0 * ((np.cumsum(f * lfo2 * 1.0018) / SR) % 1.0) - 1.0
        left += lp(s_l, 1450.0)
        right += lp(s_r, 1450.0)
    env = np.minimum(1.0, t / 0.55) * np.minimum(1.0, (dur - t) / 0.65)
    sc = env / max(1, len(freqs))
    return left * sc * 0.76, right * sc * 0.76


def dreamy_rhodes_note(freq, dur=1.45):
    """Мягкая стеклянная капля электропиано для космического перебора."""
    t = np.arange(int(dur * SR)) / SR
    sig = (
        0.74 * np.sin(2 * np.pi * freq * t)
        + 0.20 * np.sin(2 * np.pi * freq * 2.0 * t) * np.exp(-t / 0.45)
        + 0.06 * np.sin(2 * np.pi * freq * 3.0 * t) * np.exp(-t / 0.12)
    )
    env = (1.0 - np.exp(-t / 0.015)) * np.exp(-t / 0.62)
    return lp(sig * env, 2300.0) * 0.34


def warm_fretless_bass(freq, dur):
    t = np.arange(int(dur * SR)) / SR
    sig = np.sin(2 * np.pi * freq * t) * 0.78 + lp(2.0 * ((t * freq) % 1.0) - 1.0, 220.0) * 0.35
    env = np.minimum(1.0, t / 0.065) * np.minimum(1.0, (dur - t) / 0.12)
    return sig * env * 0.54


def lyrical_space_lead(notes, total_dur):
    """Певучий лиричный аналоговый Moog-лид (Ballad for Space Lovers style)."""
    n_l = int(round(total_dur * SR))
    t = np.arange(n_l) / SR
    f_track = np.full(n_l, notes[0][1], np.float64)
    amp_track = np.zeros(n_l, np.float64)

    for i, (t_start, freq, n_dur) in enumerate(notes):
        i0 = int(round(t_start * SR))
        i1 = min(n_l, int(round((t_start + n_dur) * SR)))
        if i0 >= n_l or i1 <= i0:
            continue
        prev_f = notes[i - 1][1] if i > 0 else freq
        seg_t = np.arange(i1 - i0) / SR
        # Нежное долгое портаменто между нотами
        glide = prev_f + (freq - prev_f) * (1.0 - np.exp(-seg_t / 0.048))
        f_track[i0:i1] = glide
        # Задержка вибрато — появляется на тянущихся нотах
        env = (1.0 - np.exp(-seg_t / 0.045)) * np.minimum(1.0, (n_dur - seg_t) / 0.12)
        amp_track[i0:i1] = np.maximum(amp_track[i0:i1], env)

    vib = 1.0 + 0.0055 * np.sin(2 * np.pi * 4.8 * t)
    ph = 2.0 * np.pi * np.cumsum(f_track * vib) / SR
    # Тёплая аналоговая форма (мягкий квадрат + треугольник/синус)
    sig = 0.55 * np.sin(ph) + 0.30 * np.tanh(1.8 * np.sin(ph)) + 0.15 * np.sin(2 * ph)
    return lp(sig, 2200.0) * amp_track * 0.44


def soft_ballad_kick():
    dur = 0.45
    t = np.arange(int(dur * SR)) / SR
    f = 44.0 + 70.0 * np.exp(-t / 0.032)
    ph = 2.0 * np.pi * np.cumsum(f) / SR
    return lp(np.sin(ph) * (1.0 - np.exp(-t / 0.008)) * np.exp(-t / 0.18), 165.0) * 0.65


def soft_brush_snare():
    dur = 0.34
    t = np.arange(int(dur * SR)) / SR
    nz = bp(rng.standard_normal(len(t)), 650, 3800) * np.exp(-t / 0.12)
    return nz * 0.28


def add_cosmic_reverb(buf):
    """Протяжное бархатное стерео-эхо (как в космос-синте 80-х)."""
    out = buf.copy()
    for d_s, g in [(0.375 * BEAT, 0.36), (0.75 * BEAT, 0.28), (1.25 * BEAT, 0.18)]:
        d = int(round(d_s * SR))
        if d < N:
            w0 = lp(buf[:, 0], 2200.0) * g
            w1 = lp(buf[:, 1], 2000.0) * g
            out[d:, 0] += w1[:-d]
            out[d:, 1] += w0[:-d]
    return out


def main():
    os.makedirs('audio', exist_ok=True)
    buf = np.zeros((N, 2), np.float64)
    lead_buf = np.zeros((N, 2), np.float64)

    # Лиричная романтично-меланхоличная гармония 80-х:
    # Cm9 -> Fm9 -> Bb13 -> Ebmaj7 -> Abmaj7 -> G7sus4 -> Cm9
    chords = [
        (0, 65.41, [130.81, 196.00, 233.08, 293.66, 311.13], [130.81, 196.00, 293.66, 311.13]),  # Cm9
        (1, 43.65, [174.61, 207.65, 261.63, 311.13, 392.00], [174.61, 261.63, 311.13, 392.00]),  # Fm9
        (2, 58.27, [116.54, 174.61, 233.08, 293.66, 349.23], [116.54, 233.08, 293.66, 349.23]),  # Bb
        (3, 77.78, [155.56, 196.00, 233.08, 293.66, 392.00], [155.56, 233.08, 293.66, 392.00]),  # Ebmaj7
        (4, 51.91, [103.83, 155.56, 207.65, 246.94, 311.13], [103.83, 207.65, 246.94, 311.13]),  # Abmaj7
        (5, 49.00, [146.83, 196.00, 261.63, 293.66, 349.23], [146.83, 196.00, 261.63, 293.66]),  # G7sus4 -> G
        (6, 65.41, [130.81, 196.00, 233.08, 293.66, 311.13], [130.81, 196.00, 293.66, 311.13]),  # Cm9
    ]

    for b_idx, f_bass, str_freqs, arp_freqs in chords:
        bs = b_idx * BAR
        sl, sr = solina_strings(str_freqs, BAR + 0.45)
        i0 = int(round(bs * SR))
        ln = min(len(sl), N - i0)
        buf[i0:i0 + ln, 0] += sl[:ln]
        buf[i0:i0 + ln, 1] += sr[:ln]

        if b_idx < 6:
            add(buf, bs, warm_fretless_bass(f_bass, BAR - 0.05), gain=0.80)
            # Медленный волнообразный 8-дольный перебор электропиано
            seq = [0, 1, 2, 3, 2, 1, 2, 3]
            for st, idx_n in enumerate(seq):
                add(lead_buf, bs + st * 0.5 * BEAT,
                    dreamy_rhodes_note(arp_freqs[idx_n] * 2.0, 1.35),
                    gain=0.28, pan=-0.26 + 0.075 * st)
        else:
            add(buf, bs, warm_fretless_bass(f_bass, BAR - 0.45), gain=0.62)

        # Деликатный балладный пульс с Bar 1 по Bar 5
        if 1 <= b_idx <= 5:
            add(buf, bs + 0.0 * BEAT, soft_ballad_kick(), gain=0.72)
            add(buf, bs + 2.0 * BEAT, soft_ballad_kick(), gain=0.60)
            add(buf, bs + 1.0 * BEAT, soft_brush_snare(), gain=0.55, pan=-0.08)
            add(buf, bs + 3.0 * BEAT, soft_brush_snare(), gain=0.60, pan=0.08)

    # Певучая лиричная тема (Bars 1 - 5: тянущиеся поющие ноты, как Ballad for Space Lovers)
    mel_notes = [
        # Bar 1 (3.16 - 6.32) — нежное вступление мелодии на тексте
        (1 * BAR + 0.0 * BEAT, 523.25, 1.5 * BEAT),    # C5
        (1 * BAR + 1.5 * BEAT, 587.33, 0.75 * BEAT),   # D5
        (1 * BAR + 2.25 * BEAT, 622.25, 1.75 * BEAT),  # Eb5
        # Bar 2 (6.32 - 9.47)
        (2 * BAR + 0.0 * BEAT, 587.33, 1.5 * BEAT),    # D5
        (2 * BAR + 1.5 * BEAT, 466.16, 1.0 * BEAT),    # Bb4
        (2 * BAR + 2.5 * BEAT, 523.25, 1.5 * BEAT),    # C5
        # Bar 3 (9.47 - 12.63) — светлый вздох при переходе в Ebmaj7 и дневной свет
        (3 * BAR + 0.0 * BEAT, 783.99, 2.0 * BEAT),    # G5
        (3 * BAR + 2.0 * BEAT, 698.46, 1.0 * BEAT),    # F5
        (3 * BAR + 3.0 * BEAT, 622.25, 1.0 * BEAT),    # Eb5
        # Bar 4 (12.63 - 15.79)
        (4 * BAR + 0.0 * BEAT, 622.25, 1.5 * BEAT),    # Eb5
        (4 * BAR + 1.5 * BEAT, 587.33, 1.0 * BEAT),    # D5
        (4 * BAR + 2.5 * BEAT, 523.25, 1.5 * BEAT),    # C5
        # Bar 5 (15.79 - 18.95) — кульминационная высокая фраза на проезде по картине
        (5 * BAR + 0.0 * BEAT, 587.33, 1.5 * BEAT),    # D5
        (5 * BAR + 1.5 * BEAT, 622.25, 1.0 * BEAT),    # Eb5
        (5 * BAR + 2.5 * BEAT, 698.46, 1.5 * BEAT),    # F5
        # Bar 6 (18.95 - 22.11) — умиротворённое разрешение в G5 -> C5
        (6 * BAR + 0.0 * BEAT, 783.99, 1.5 * BEAT),    # G5
        (6 * BAR + 1.5 * BEAT, 523.25, 2.0 * BEAT),    # C5
    ]
    ls = lyrical_space_lead(mel_notes, DUR)
    lead_buf[:, 0] += ls * 0.90
    lead_buf[:, 1] += ls * 0.90

    buf += add_cosmic_reverb(lead_buf)

    fade_n = int(1.05 * SR)
    buf[-fade_n:] *= np.linspace(1.0, 0.0, fade_n)[:, None] ** 1.35

    mx = np.max(np.abs(buf))
    if mx > 0.0:
        buf = np.tanh(buf * (0.68 / mx) * 1.08) * 0.72

    pcm = np.clip(buf * 32767.0, -32767, 32767).astype(np.int16)
    out = 'audio/BARH_space_lyrical_76bpm.wav'
    wavfile.write(out, SR, pcm)
    rms = 20 * np.log10(np.sqrt(np.mean(buf ** 2)) + 1e-9)
    print(f'written {out}: {DUR:.3f}s, peak={np.max(np.abs(buf)):.3f}, RMS={rms:.1f} dBFS')


if __name__ == '__main__':
    main()
