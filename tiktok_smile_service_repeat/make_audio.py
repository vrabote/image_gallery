"""Синтез космического синти-трека в духе группы SPACE 1980-х годов для BARH (108 BPM, 22.22 с).

Характерные элементы классического Space (Didier Marouani — Magic Fly / Just Blue):
  - пульсирующий 16-дольный аналоговый секвенсор-арпеджиатор с плавным раскрытием фильтра
  - широкие бархатные стерео-струны (Juno/Polymoog chorus pad)
  - поющий аналоговый лид с портаменто и тёплым ленточным эхом
  - мягкий ретро-грув драм-машины 80-х (без агрессии и резких скачков)
"""
import os
import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, lfilter

SR = 48000
BPM = 108.0
BEAT = 60.0 / BPM             # 0.555556 s
BAR = 4 * BEAT                # 2.222222 s
DUR = 10 * BAR                # 22.222222 s
N = int(round(DUR * SR))

rng = np.random.default_rng(1980)


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


def space_arp_note(freq, dur, brightness=1600.0):
    """Классический 80s аналоговый арпеджио-импульс (пила + резонансный спад фильтра)."""
    t = np.arange(int(dur * SR)) / SR
    saw1 = 2.0 * ((t * freq) % 1.0) - 1.0
    saw2 = 2.0 * ((t * freq * 1.003) % 1.0) - 1.0
    raw = (saw1 + saw2) * 0.5
    lo = lp(raw, max(280.0, brightness * 0.32))
    hi = lp(raw, min(6500.0, brightness))
    env_f = np.exp(-t / 0.055)
    sig = lo * (1.0 - env_f) + hi * env_f
    amp = (1.0 - np.exp(-t / 0.004)) * np.exp(-t / max(0.07, dur * 0.65))
    return sig * amp * 0.55


def juno_pad_chord(freqs, dur):
    """Тёплые широкие космические струны 80-х (стерео-хорус)."""
    n_c = int(dur * SR)
    t = np.arange(n_c) / SR
    left = np.zeros(n_c, np.float64)
    right = np.zeros(n_c, np.float64)
    for idx, f in enumerate(freqs):
        lfo = 1.0 + 0.0025 * np.sin(2 * np.pi * (0.45 + 0.08 * idx) * t)
        s_l = 2.0 * ((np.cumsum(f * lfo) / SR) % 1.0) - 1.0
        s_r = 2.0 * ((np.cumsum(f * (2.0 - lfo) * 1.002) / SR) % 1.0) - 1.0
        left += lp(s_l, 1700.0)
        right += lp(s_r, 1700.0)
    env = np.minimum(1.0, t / 0.35) * np.minimum(1.0, (dur - t) / 0.45)
    scale = env / max(1, len(freqs))
    return left * scale * 0.72, right * scale * 0.72


def space_lead_phrase(notes, total_dur):
    """Поющий аналоговый Space-лид с плавным портаменто и лёгким вибрато."""
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
        glide = prev_f + (freq - prev_f) * (1.0 - np.exp(-seg_t / 0.022))
        f_track[i0:i1] = glide
        env = (1.0 - np.exp(-seg_t / 0.018)) * np.minimum(1.0, (n_dur - seg_t) / 0.055)
        amp_track[i0:i1] = np.maximum(amp_track[i0:i1], env)

    vib = 1.0 + 0.0045 * np.sin(2 * np.pi * 5.2 * t)
    ph = 2.0 * np.pi * np.cumsum(f_track * vib) / SR
    saw = 2.0 * ((ph / (2 * np.pi)) % 1.0) - 1.0
    sq = np.tanh(2.2 * np.sin(ph))
    tone = lp(saw * 0.55 + sq * 0.45, 2900.0)
    return tone * amp_track * 0.42


def retro_kick():
    dur = 0.28
    t = np.arange(int(dur * SR)) / SR
    f = 48.0 + 115.0 * np.exp(-t / 0.018)
    ph = 2.0 * np.pi * np.cumsum(f) / SR
    sig = np.sin(ph) * (1.0 - np.exp(-t / 0.003)) * np.exp(-t / 0.11)
    return np.tanh(sig * 1.2) * 0.72


def retro_snare():
    """Мягкий gated-reverb снэр 80-х."""
    dur = 0.28
    t = np.arange(int(dur * SR)) / SR
    nz = bp(rng.standard_normal(len(t)), 850, 6200) * np.exp(-t / 0.095)
    body = np.sin(2 * np.pi * 175 * t * np.exp(-t / 0.05)) * np.exp(-t / 0.032) * 0.55
    return lp(nz * 0.75 + body, 6800.0) * 0.52


def retro_hat(open_hat=False):
    dur = 0.18 if open_hat else 0.055
    t = np.arange(int(dur * SR)) / SR
    nz = hp(rng.standard_normal(len(t)), 7200)
    return nz * np.exp(-t / (0.065 if open_hat else 0.014)) * (0.20 if open_hat else 0.16)


def stereo_echo(buf, delay_s, fb=0.38):
    d = int(round(delay_s * SR))
    if d <= 0 or d >= N:
        return buf
    out = buf.copy()
    w0 = lp(buf[:, 0], 2600.0) * fb
    w1 = lp(buf[:, 1], 2400.0) * fb
    out[d:, 0] += w1[:-d] * 0.85
    out[d:, 1] += w0[:-d] * 0.85
    if 2 * d < N:
        out[2 * d:, 0] += w0[:-2 * d] * 0.42
        out[2 * d:, 1] += w1[:-2 * d] * 0.42
    return out


def main():
    os.makedirs('audio', exist_ok=True)
    buf = np.zeros((N, 2), np.float64)
    lead_buf = np.zeros((N, 2), np.float64)

    # Классическая космическая гармония в Cm (как у Space 80-х):
    # Cm -> Ab -> Fm -> G -> Cm -> Ab -> Fm -> G -> Cm -> Cm
    bars_spec = [
        (0, [130.81, 196.00, 233.08, 311.13], [130.81, 196.00, 311.13, 196.00]),  # Cm
        (1, [103.83, 155.56, 196.00, 311.13], [103.83, 155.56, 261.63, 155.56]),  # Abmaj7
        (2, [174.61, 207.65, 261.63, 311.13], [87.31,  174.61, 261.63, 174.61]),  # Fm7
        (3, [146.83, 196.00, 246.94, 293.66], [98.00,  146.83, 246.94, 146.83]),  # G
        (4, [130.81, 196.00, 233.08, 311.13], [130.81, 196.00, 311.13, 233.08]),  # Cm7
        (5, [103.83, 155.56, 207.65, 311.13], [103.83, 155.56, 261.63, 207.65]),  # Ab
        (6, [174.61, 207.65, 261.63, 311.13], [87.31,  174.61, 261.63, 207.65]),  # Fm7
        (7, [146.83, 196.00, 246.94, 293.66], [98.00,  196.00, 293.66, 246.94]),  # G
        (8, [130.81, 196.00, 233.08, 311.13], [130.81, 196.00, 311.13, 196.00]),  # Cm
        (9, [130.81, 196.00, 233.08, 311.13], [130.81, 196.00, 311.13, 196.00]),  # Cm (аутро)
    ]

    for b_idx, pad_freqs, arp_freqs in bars_spec:
        bs = b_idx * BAR
        # Juno-струны на каждый такт
        pl, pr = juno_pad_chord(pad_freqs, BAR + 0.25)
        i0 = int(round(bs * SR))
        ln = min(len(pl), N - i0)
        buf[i0:i0 + ln, 0] += pl[:ln]
        buf[i0:i0 + ln, 1] += pr[:ln]

        # Космический 16-дольный арпеджиатор (фирменный почерк Space 80-х)
        if b_idx < 9:
            bright = 1050.0 + 1650.0 * (0.5 - 0.5 * np.cos(np.pi * min(1.0, b_idx / 7.0)))
            g_arp = 0.42 if b_idx >= 2 else 0.28
            for step in range(16):
                af = arp_freqs[step % 4]
                if step % 8 == 7:
                    af *= 2.0  # лёгкий октавный всплеск в духе Magic Fly
                add(buf, bs + step * 0.25 * BEAT,
                    space_arp_note(af, 0.20, brightness=bright),
                    gain=g_arp, pan=-0.16 if step % 2 == 0 else 0.16)

        # Мягкий 80s Space-грув с Bar 2 (когда начинается двуязычный текст) по Bar 8
        if 2 <= b_idx <= 8:
            for beat_i in range(4):
                add(buf, bs + beat_i * BEAT, retro_kick(), gain=0.78)
            for beat_i in (1, 3):
                add(buf, bs + beat_i * BEAT, retro_snare(), gain=0.62)
            for h_i in range(8):
                is_open = (h_i % 4 == 2)
                add(buf, bs + h_i * 0.5 * BEAT, retro_hat(is_open),
                    gain=0.32 if is_open else 0.24, pan=0.22 if h_i % 2 else -0.18)

    # Поющая аналоговая тема в духе Space (Bars 2 - 8)
    mel_notes = [
        # Bar 2-3 (4.44 - 8.89): нежная восходящая космическая фраза
        (2 * BAR + 0.0 * BEAT, 523.25, 1.5 * BEAT),    # C5
        (2 * BAR + 1.5 * BEAT, 622.25, 1.0 * BEAT),    # Eb5
        (2 * BAR + 2.5 * BEAT, 587.33, 1.5 * BEAT),    # D5
        (3 * BAR + 0.0 * BEAT, 493.88, 2.0 * BEAT),    # B4
        (3 * BAR + 2.0 * BEAT, 587.33, 1.5 * BEAT),    # D5
        # Bar 4-5 (8.89 - 13.33): раскрытие на переходе к дневному свету
        (4 * BAR + 0.0 * BEAT, 783.99, 1.5 * BEAT),    # G5
        (4 * BAR + 1.5 * BEAT, 622.25, 1.0 * BEAT),    # Eb5
        (4 * BAR + 2.5 * BEAT, 698.46, 1.5 * BEAT),    # F5
        (5 * BAR + 0.0 * BEAT, 622.25, 2.5 * BEAT),    # Eb5
        (5 * BAR + 2.5 * BEAT, 523.25, 1.5 * BEAT),    # C5
        # Bar 6-8 (13.33 - 20.00): парящий кульминационный мотив над проездом картины
        (6 * BAR + 0.0 * BEAT, 698.46, 1.5 * BEAT),    # F5
        (6 * BAR + 1.5 * BEAT, 783.99, 1.5 * BEAT),    # G5
        (6 * BAR + 3.0 * BEAT, 830.61, 1.0 * BEAT),    # Ab5
        (7 * BAR + 0.0 * BEAT, 783.99, 2.5 * BEAT),    # G5
        (7 * BAR + 2.5 * BEAT, 587.33, 1.5 * BEAT),    # D5
        (8 * BAR + 0.0 * BEAT, 622.25, 2.0 * BEAT),    # Eb5
        (8 * BAR + 2.0 * BEAT, 523.25, 2.5 * BEAT),    # C5
    ]
    lead_sig = space_lead_phrase(mel_notes, DUR)
    lead_buf[:, 0] += lead_sig * 0.90
    lead_buf[:, 1] += lead_sig * 0.90
    buf += stereo_echo(lead_buf, 0.75 * BEAT, fb=0.40)

    # Лёгкая космическая реверберационная дымка + плавный выход за последние 0.80 с
    fade_n = int(0.80 * SR)
    buf[-fade_n:] *= np.linspace(1.0, 0.0, fade_n)[:, None] ** 1.3

    mx = np.max(np.abs(buf))
    if mx > 0.0:
        buf = np.tanh(buf * (0.68 / mx) * 1.10) * 0.72

    pcm = np.clip(buf * 32767.0, -32767, 32767).astype(np.int16)
    out = 'audio/BARH_space80s_108bpm.wav'
    wavfile.write(out, SR, pcm)
    rms = 20 * np.log10(np.sqrt(np.mean(buf ** 2)) + 1e-9)
    print(f'written {out}: {DUR:.3f}s, peak={np.max(np.abs(buf)):.3f}, RMS={rms:.1f} dBFS')


if __name__ == '__main__':
    main()
