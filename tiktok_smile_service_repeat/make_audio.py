"""Синтез камерного ночного космического ноктюрна в духе SPACE — «Secret Dreams» (1978).

Характерный саунд раннего прог-синти Space (1978, Just Blue B-side):
  - медленный ночной темп (~59.5 BPM, half-time от 119 BPM · 22.18 с)
  - тёплые аналоговые струны с мягким стерео-фейзером (Dm9 -> Gm9 -> Cmaj7 -> Fmaj7 -> Bbmaj7 -> A7sus4 -> Dm9)
  - хрустальные ночные капли электропиано
  - тихий, интимный поющий аналоговый синти-лид (флейта/терменвокс-синт 70-х) с нежным эхом
  - мягчайший тёплый бас и невесомый ночной пульс
"""
import os
import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, lfilter

SR = 48000
BPM = 59.5                    # half-time от 119 BPM («Secret Dreams»)
BEAT = 60.0 / BPM             # 1.008403 s
BAR = 4 * BEAT                # 4.033613 s
DUR = 8.5 * BAR               # 34.285714 s
N = int(round(DUR * SR))

rng = np.random.default_rng(1978)


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


def prog_nocturne_pad(freqs, dur):
    """Тёплый аналоговый пад конца 70-х с медленным дыханием фильтра."""
    n_c = int(dur * SR)
    t = np.arange(n_c) / SR
    left = np.zeros(n_c, np.float64)
    right = np.zeros(n_c, np.float64)
    for idx, f in enumerate(freqs):
        lfo1 = 1.0 + 0.0028 * np.sin(2 * np.pi * (0.28 + 0.05 * idx) * t)
        lfo2 = 1.0 + 0.0026 * np.sin(2 * np.pi * (0.41 + 0.05 * idx) * t + 1.4)
        s_l = 2.0 * ((np.cumsum(f * lfo1) / SR) % 1.0) - 1.0
        s_r = 2.0 * ((np.cumsum(f * lfo2 * 1.0016) / SR) % 1.0) - 1.0
        left += lp(s_l, 1280.0)
        right += lp(s_r, 1280.0)
    env = np.minimum(1.0, t / 0.70) * np.minimum(1.0, (dur - t) / 0.85)
    sc = env / max(1, len(freqs))
    return left * sc * 0.76, right * sc * 0.76


def crystal_ep(freq, dur=1.90):
    """Камерные ночные ноты электропиано."""
    t = np.arange(int(dur * SR)) / SR
    sig = (
        0.78 * np.sin(2 * np.pi * freq * t)
        + 0.16 * np.sin(2 * np.pi * freq * 2.0 * t) * np.exp(-t / 0.55)
        + 0.06 * np.sin(2 * np.pi * freq * 3.0 * t) * np.exp(-t / 0.14)
    )
    env = (1.0 - np.exp(-t / 0.018)) * np.exp(-t / 0.78)
    return lp(sig * env, 2100.0) * 0.34


def warm_sub(freq, dur):
    t = np.arange(int(dur * SR)) / SR
    sig = np.sin(2 * np.pi * freq * t) * 0.84 + lp(2.0 * ((t * freq) % 1.0) - 1.0, 190.0) * 0.25
    env = np.minimum(1.0, t / 0.09) * np.minimum(1.0, (dur - t) / 0.18)
    return sig * env * 0.52


def intimate_synth_flute(notes, total_dur):
    """Нежный ночной аналоговый лид (дух 'Secret Dreams' 1978)."""
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
        glide = prev_f + (freq - prev_f) * (1.0 - np.exp(-seg_t / 0.055))
        f_track[i0:i1] = glide
        env = (1.0 - np.exp(-seg_t / 0.060)) * np.minimum(1.0, (n_dur - seg_t) / 0.16)
        amp_track[i0:i1] = np.maximum(amp_track[i0:i1], env)

    vib = 1.0 + 0.0048 * np.sin(2 * np.pi * 4.5 * t)
    ph = 2.0 * np.pi * np.cumsum(f_track * vib) / SR
    sig = 0.65 * np.sin(ph) + 0.24 * np.tanh(1.5 * np.sin(ph)) + 0.11 * np.sin(2 * ph)
    breath = bp(rng.standard_normal(n_l), 900, 2600) * 0.015
    return lp((sig + breath), 1950.0) * amp_track * 0.44


def soft_pulse_kick():
    dur = 0.48
    t = np.arange(int(dur * SR)) / SR
    f = 44.0 + 58.0 * np.exp(-t / 0.038)
    ph = 2.0 * np.pi * np.cumsum(f) / SR
    return lp(np.sin(ph) * (1.0 - np.exp(-t / 0.012)) * np.exp(-t / 0.20), 150.0) * 0.54


def night_brush():
    dur = 0.36
    t = np.arange(int(dur * SR)) / SR
    return bp(rng.standard_normal(len(t)), 550, 3200) * np.exp(-t / 0.13) * 0.20


def cosmic_echo(buf):
    out = buf.copy()
    for d_s, g in [(0.375 * BEAT, 0.38), (0.75 * BEAT, 0.28), (1.25 * BEAT, 0.18)]:
        d = int(round(d_s * SR))
        if d < N:
            w0 = lp(buf[:, 0], 1900.0) * g
            w1 = lp(buf[:, 1], 1750.0) * g
            out[d:, 0] += w1[:-d]
            out[d:, 1] += w0[:-d]
    return out


def main():
    os.makedirs('audio', exist_ok=True)
    buf = np.zeros((N, 2), np.float64)
    lead_buf = np.zeros((N, 2), np.float64)

    # Ночная прог-гармония в D minor (8.5 тактов, 34.29 с — спокойное дыхание на всю сцену)
    chords = [
        (0, 73.42, [146.83, 220.00, 261.63, 329.63, 349.23], [146.83, 220.00, 329.63, 349.23]),  # Dm9 (Stop / Deep breath)
        (1, 49.00, [196.00, 233.08, 293.66, 349.23, 440.00], [196.00, 293.66, 349.23, 440.00]),  # Gm9 (Relax / And look)
        (2, 73.42, [146.83, 220.00, 261.63, 329.63, 349.23], [146.83, 220.00, 329.63, 349.23]),  # Dm9 (Pause on painting)
        (3, 65.41, [130.81, 196.00, 246.94, 329.63, 392.00], [130.81, 246.94, 329.63, 392.00]),  # Cmaj7 (Bilingual questions)
        (4, 58.27, [116.54, 174.61, 220.00, 293.66, 349.23], [116.54, 220.00, 293.66, 349.23]),  # Bbmaj7 (This is my new work)
        (5, 87.31, [174.61, 220.00, 261.63, 329.63, 440.00], [174.61, 261.63, 329.63, 440.00]),  # Fmaj7 (Daylight residence)
        (6, 49.00, [196.00, 233.08, 293.66, 349.23, 440.00], [196.00, 293.66, 349.23, 440.00]),  # Gm9 (Painting glide top)
        (7, 55.00, [110.00, 164.81, 220.00, 293.66, 329.63], [110.00, 220.00, 293.66, 329.63]),  # Asus4->Am (Painting glide low)
    ]

    for b_idx, f_bass, str_freqs, arp_freqs in chords:
        bs = b_idx * BAR
        sl, sr = prog_nocturne_pad(str_freqs, BAR + 0.55)
        i0 = int(round(bs * SR))
        ln = min(len(sl), N - i0)
        buf[i0:i0 + ln, 0] += sl[:ln]
        buf[i0:i0 + ln, 1] += sr[:ln]

        if b_idx == 0:
            add(buf, bs, warm_sub(f_bass, BAR - 0.06), gain=0.62)
            for st, idx_n in enumerate([0, 1, 2, 3]):
                add(lead_buf, bs + st * BEAT,
                    crystal_ep(arp_freqs[idx_n] * 2.0, 2.40),
                    gain=0.22, pan=-0.18 + 0.12 * st)
        else:
            add(buf, bs, warm_sub(f_bass, BAR - 0.06), gain=0.76)
            seq = [0, 1, 2, 3, 2, 1, 2, 3]
            for st, idx_n in enumerate(seq):
                add(lead_buf, bs + st * 0.5 * BEAT,
                    crystal_ep(arp_freqs[idx_n] * 2.0, 1.90),
                    gain=0.26, pan=-0.26 + 0.075 * st)

        # Тихий невесомый ночной пульс с Bar 2 (когда начинается пауза на картине) по Bar 7
        if 2 <= b_idx <= 7:
            for bi in (0.0, 2.0):
                add(buf, bs + bi * BEAT, soft_pulse_kick(), gain=0.66 if b_idx <= 6 else 0.52)
            for bi in (1.0, 3.0):
                add(buf, bs + bi * BEAT, night_brush(), gain=0.52 if b_idx <= 6 else 0.40, pan=-0.08 if bi == 1 else 0.08)

    # Заключительные 0.5 такта (Bar 8: 32.27 - 34.29 с — финальное разрешение на BARH)
    bs8 = 8 * BAR
    sl8, sr8 = prog_nocturne_pad([146.83, 220.00, 261.63, 329.63], 0.5 * BAR + 0.40)
    i8 = int(round(bs8 * SR))
    ln8 = min(len(sl8), N - i8)
    buf[i8:i8 + ln8, 0] += sl8[:ln8]
    buf[i8:i8 + ln8, 1] += sr8[:ln8]
    add(buf, bs8, warm_sub(73.42, 0.5 * BAR - 0.25), gain=0.52)

    # Интимная ночная мелодия (Bar 2 -> Bar 8)
    mel_notes = [
        # Bar 2 (8.07 - 12.10): чистая пауза на картине после "And look."
        (2 * BAR + 0.0 * BEAT, 587.33, 1.5 * BEAT),    # D5
        (2 * BAR + 1.5 * BEAT, 659.25, 0.75 * BEAT),   # E5
        (2 * BAR + 2.25 * BEAT, 698.46, 1.75 * BEAT),  # F5
        # Bar 3 (12.10 - 16.13): двуязычные вопросы
        (3 * BAR + 0.0 * BEAT, 659.25, 1.5 * BEAT),    # E5
        (3 * BAR + 1.5 * BEAT, 523.25, 1.0 * BEAT),    # C5
        (3 * BAR + 2.5 * BEAT, 587.33, 1.5 * BEAT),    # D5
        # Bar 4 (16.13 - 20.17): "This is my new work."
        (4 * BAR + 0.0 * BEAT, 587.33, 1.5 * BEAT),    # D5
        (4 * BAR + 1.5 * BEAT, 698.46, 1.0 * BEAT),    # F5
        (4 * BAR + 2.5 * BEAT, 880.00, 1.5 * BEAT),    # A5
        # Bar 5 (20.17 - 24.20): дневная резиденция
        (5 * BAR + 0.0 * BEAT, 783.99, 1.5 * BEAT),    # G5
        (5 * BAR + 1.5 * BEAT, 698.46, 1.0 * BEAT),    # F5
        (5 * BAR + 2.5 * BEAT, 659.25, 1.5 * BEAT),    # E5
        # Bar 6-7 (24.20 - 32.27): проезд по картине
        (6 * BAR + 0.0 * BEAT, 698.46, 1.5 * BEAT),    # F5
        (6 * BAR + 1.5 * BEAT, 659.25, 1.0 * BEAT),    # E5
        (6 * BAR + 2.5 * BEAT, 587.33, 1.5 * BEAT),    # D5
        (7 * BAR + 0.0 * BEAT, 659.25, 1.75 * BEAT),   # E5
        (7 * BAR + 1.75 * BEAT, 587.33, 2.25 * BEAT),  # D5
        # Bar 8 (32.27 - 34.29): тихий финал BARH
        (8 * BAR + 0.0 * BEAT, 587.33, 1.8 * BEAT),    # D5
    ]
    ls = intimate_synth_flute(mel_notes, DUR)
    lead_buf[:, 0] += ls * 0.90
    lead_buf[:, 1] += ls * 0.90

    buf += cosmic_echo(lead_buf)

    fade_n = int(1.15 * SR)
    buf[-fade_n:] *= np.linspace(1.0, 0.0, fade_n)[:, None] ** 1.4

    mx = np.max(np.abs(buf))
    if mx > 0.0:
        buf = np.tanh(buf * (0.68 / mx) * 1.08) * 0.72

    pcm = np.clip(buf * 32767.0, -32767, 32767).astype(np.int16)
    out = 'audio/BARH_secret_dreams_60bpm.wav'
    wavfile.write(out, SR, pcm)
    rms = 20 * np.log10(np.sqrt(np.mean(buf ** 2)) + 1e-9)
    print(f'written {out}: {DUR:.3f}s, peak={np.max(np.abs(buf)):.3f}, RMS={rms:.1f} dBFS')


if __name__ == '__main__':
    main()
