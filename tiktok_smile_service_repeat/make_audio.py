"""Кинематографичный саунд-дизайн BARH (86 BPM, C minor, 6 тактов = 16.744 с).

Темп 86 BPM и тональность C minor совпадают с главным трендовым ориентиром
недели (Steve Lacy — «the feeling»), поэтому:
  1) основной ролик получает живой атмосферный саунд-дизайн (салон самолёта,
     звонок бортпроводника, защёлка двери, тёплый Rhodes и поздний ночной грув);
  2) беззвучная версия идеально ложится на бит при подстановке трека в TikTok.

Запуск: .venv/bin/python make_audio.py
"""
import os
import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, sosfilt, fftconvolve

SR = 48000
BPM = 86
BEAT = 60.0 / BPM                      # 0.697674 s
BAR = 4 * BEAT                         # 2.790698 s
BARS = 6
DUR = BARS * BAR                       # 16.744186 s
N = int((DUR + 2.5) * SR)
rng = np.random.default_rng(8600)

L = np.zeros(N, dtype=np.float64)
R = np.zeros(N, dtype=np.float64)
REV_L = np.zeros(N, dtype=np.float64)
REV_R = np.zeros(N, dtype=np.float64)


def lp(x, fc, order=2):
    return sosfilt(butter(order, min(fc, SR * 0.48), 'low', fs=SR, output='sos'), x)


def hp(x, fc, order=2):
    return sosfilt(butter(order, max(fc, 15.0), 'high', fs=SR, output='sos'), x)


def bp(x, lo, hi, order=2):
    return sosfilt(butter(order, [max(lo, 15.0), min(hi, SR * 0.48)], 'band', fs=SR, output='sos'), x)


def put(x, t0, pan=0.5, gain=1.0, rev=0.0):
    s = int(t0 * SR)
    if s >= N or s + len(x) <= 0:
        return
    if s < 0:
        x = x[-s:]
        s = 0
    e = min(N, s + len(x))
    seg = x[:e - s] * gain
    gl = np.cos(pan * np.pi / 2.0)
    gr = np.sin(pan * np.pi / 2.0)
    L[s:e] += seg * gl
    R[s:e] += seg * gr
    if rev > 0:
        REV_L[s:e] += seg * gl * rev
        REV_R[s:e] += seg * gr * rev


def midi_hz(m):
    return 440.0 * (2.0 ** ((m - 69) / 12.0))


def rhodes_note(midi, dur, vel=1.0):
    """Тёплое электропиано: чистый фундаментал + мягкий колокольчиковый призвук."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = midi_hz(midi)
    body = np.sin(2 * np.pi * f * t) * np.exp(-t / max(1.1, dur * 0.75))
    tine = 0.24 * np.sin(2 * np.pi * (f * 2.0) * t) * np.exp(-t / 0.14)
    bell = 0.08 * np.sin(2 * np.pi * (f * 7.0) * t) * np.exp(-t / 0.035)
    att = np.minimum(1.0, t / 0.008)
    rel = np.minimum(1.0, np.maximum(dur - t, 0.0) / 0.18)
    trem = 1.0 + 0.06 * np.sin(2 * np.pi * 3.8 * t)
    return (body + tine + bell) * att * rel * trem * vel


# 1. САЛОН САМОЛЁТА (0.00 – 2.85 s): низкий гул + звонок + щелчок двери + мягкий винил
cabin_n = int(3.2 * SR)
cabin_t = np.arange(cabin_n) / SR
brown = bp(np.cumsum(rng.standard_normal(cabin_n)), 48, 220, 4)
brown = brown / (np.std(brown) + 1e-9)
air = bp(rng.standard_normal(cabin_n), 320, 1100, 2)
air = air / (np.std(air) + 1e-9)
cabin_hum = brown * 0.055 + air * 0.012
cabin_fade = np.minimum(1.0, cabin_t / 0.15) * (1.0 - np.clip((cabin_t - 1.35) / 1.45, 0.0, 1.0)) ** 1.4
put(cabin_hum * cabin_fade, 0.0, pan=0.5, gain=1.0, rev=0.12)

# Двухтоновый звонок бортпроводника (G5 -> Eb5, как в C minor)
def chime_tone(hz, dur=1.25):
    n = int(dur * SR)
    t = np.arange(n) / SR
    y = (np.sin(2 * np.pi * hz * t) * np.exp(-t / 0.42)
         + 0.18 * np.sin(2 * np.pi * hz * 2.0 * t) * np.exp(-t / 0.16)
         + 0.06 * np.sin(2 * np.pi * hz * 3.0 * t) * np.exp(-t / 0.07))
    return y * np.minimum(1.0, t / 0.004)


put(chime_tone(783.99, 1.1), 0.24, pan=0.56, gain=0.16, rev=0.55)
put(chime_tone(622.25, 1.5), 0.62, pan=0.44, gain=0.17, rev=0.60)

# Тихий механический щелчок двери/защёлки в пустом салоне (1.45 s)
ln = int(0.28 * SR)
lt = np.arange(ln) / SR
latch = (np.sin(2 * np.pi * 88 * lt) * np.exp(-lt / 0.028) * 0.45
         + bp(rng.standard_normal(ln), 900, 3200, 2) * np.exp(-lt / 0.012) * 0.28)
put(latch, 1.45, pan=0.52, gain=0.42, rev=0.25)

# Виниловая пыль по всей длине (едва слышная, тёплая плёнка)
vin = bp(rng.standard_normal(N), 900, 5200, 1) * 0.0022
L += vin
R += np.roll(vin, 317)

# 2. ГАРМОНИЯ RHODES (C minor: Cm9 -> Abmaj7 -> Fm9 -> G7sus4 -> Cm9 -> Cm9)
chords = [
    (1 * BAR, 2 * BEAT, [48, 55, 58, 63, 62]),        # Cm9 (2.79 s)
    (1 * BAR + 2 * BEAT, 2 * BEAT, [44, 51, 55, 60]), # Abmaj7
    (2 * BAR, 2 * BEAT, [41, 48, 51, 56, 60]),        # Fm9
    (2 * BAR + 2 * BEAT, 1.65 * BEAT, [43, 50, 53, 58]), # G7sus4 (пауза перед ревилом)
    (3 * BAR, 4 * BEAT, [48, 55, 58, 63, 67, 74]),    # Cm9 wide reveal (8.37 s)
    (5 * BAR, 3.8 * BEAT, [48, 55, 58, 63, 67]),      # Cm9 finale (13.95 s)
]
for t0, dur, notes in chords:
    for idx, m in enumerate(notes):
        strum = idx * 0.018
        pan = 0.42 + 0.16 * (idx / max(1, len(notes) - 1))
        put(rhodes_note(m, dur + 0.6, vel=0.14), t0 + strum, pan=pan, gain=1.0, rev=0.42)

# Предвестник входа (мягкий вдох/обратный шлейф перед 2.79 s и перед 8.37 s)
for t_hit, dur_sw, g_sw in [(1 * BAR, 0.9, 0.10), (3 * BAR, 0.72, 0.13)]:
    sn = int(dur_sw * SR)
    st = np.arange(sn) / SR
    sw = lp(rng.standard_normal(sn), 900, 2) * (st / dur_sw) ** 2.6 * np.exp(-(dur_sw - st) * 0.5)
    put(sw, t_hit - dur_sw, pan=0.5, gain=g_sw, rev=0.5)

# 3. ГЛУБОКИЙ САБ-БАС (C2=36, Ab1=32, F1=29, G1=31)
bass_notes = [
    (1 * BAR, 2 * BEAT, 36),
    (1 * BAR + 2 * BEAT, 2 * BEAT, 32),
    (2 * BAR, 2 * BEAT, 29),
    (2 * BAR + 2 * BEAT, 1.55 * BEAT, 31),
    (3 * BAR, 3.8 * BEAT, 36),
    (4 * BAR, 1.2 * BEAT, 36),
    (4 * BAR + 1.333 * BEAT, 1.2 * BEAT, 34),
    (4 * BAR + 2.667 * BEAT, 1.15 * BEAT, 31),
    (5 * BAR, 3.6 * BEAT, 36),
]
for t0, dur, m in bass_notes:
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = midi_hz(m)
    sub = (np.sin(2 * np.pi * f * t) + 0.25 * np.sin(2 * np.pi * f * 2 * t))
    sub = lp(sub, 165, 2)
    env = np.minimum(1.0, t / 0.025) * np.exp(-t / max(0.8, dur * 0.85)) * np.minimum(1.0, np.maximum(dur - t, 0.0) / 0.08)
    put(sub * env, t0, pan=0.5, gain=0.28, rev=0.02)

# 4. МЯГКИЙ R&B / НУАР БИТ (Bars 1-3)
def kick():
    n = int(0.32 * SR)
    t = np.arange(n) / SR
    ph = 2 * np.pi * np.cumsum(46 + 95 * np.exp(-t / 0.032)) / SR
    return np.sin(ph) * np.exp(-t / 0.11) * np.minimum(1.0, t / 0.003)


def rim():
    n = int(0.14 * SR)
    t = np.arange(n) / SR
    tone = np.sin(2 * np.pi * 410 * t) * np.exp(-t / 0.015)
    snap = bp(rng.standard_normal(n), 1100, 3400, 2) * np.exp(-t / 0.035)
    return (tone * 0.45 + snap * 0.55) * np.minimum(1.0, t / 0.002)


def hat(vel=1.0):
    n = int(0.06 * SR)
    t = np.arange(n) / SR
    return hp(rng.standard_normal(n), 6800, 2) * np.exp(-t / 0.015) * vel


K = kick()
RM = rim()
for b in (1, 2, 3):
    t_bar = b * BAR
    # Без лишнего шума на последнем полутакте перед ревилом (пауза 7.65..8.37)
    for bt in (0.0, 1.5, 2.5):
        if b == 2 and bt > 2.0:
            continue
        put(K, t_bar + bt * BEAT, pan=0.5, gain=0.46, rev=0.04)
    for bt in (1.0, 3.0):
        if b == 2 and bt >= 3.0:
            continue
        put(RM, t_bar + bt * BEAT, pan=0.52, gain=0.20, rev=0.35)
    for sub_b in np.arange(0, 4, 0.5):
        if b == 2 and sub_b >= 2.7:
            continue
        put(hat(0.045 if sub_b % 1 == 0 else 0.025), t_bar + sub_b * BEAT, pan=0.46, gain=1.0, rev=0.18)

# 5. ТРИ МАКРО-КАДРА МАЗКОВ (Bar 4: 11.16, 12.09, 13.02): мягкий кистевой/затворный акцент
for k_idx, t_cut in enumerate([4 * BAR, 4 * BAR + 4 / 3 * BEAT, 4 * BAR + 8 / 3 * BEAT]):
    put(K, t_cut, pan=0.5, gain=0.36, rev=0.06)
    bn = int(0.16 * SR)
    bt = np.arange(bn) / SR
    brush = bp(rng.standard_normal(bn), 1400, 4800, 2) * np.exp(-bt / 0.035) * np.minimum(1.0, bt / 0.005)
    put(brush, t_cut, pan=0.44 + 0.06 * k_idx, gain=0.09, rev=0.25)

# 6. ФИНАЛ BARH (13.95 s): глубокий кино-удар и тихое затухание
fn = int(2.2 * SR)
ft = np.arange(fn) / SR
boom = np.sin(2 * np.pi * np.cumsum(38 + 42 * np.exp(-ft / 0.07)) / SR) * np.exp(-ft / 0.72)
put(boom, 5 * BAR, pan=0.5, gain=0.38, rev=0.18)

# 7. РЕВЕРБЕРАЦИЯ И МАСТЕРИНГ
ir_n = int(1.9 * SR)
ir_t = np.arange(ir_n) / SR
ir_l = lp(rng.standard_normal(ir_n), 2800, 1) * np.exp(-ir_t / 0.48)
ir_r = lp(rng.standard_normal(ir_n), 2600, 1) * np.exp(-ir_t / 0.52)
ir_l[:int(0.022 * SR)] = 0
ir_r[:int(0.024 * SR)] = 0
ir_l /= (np.sqrt(np.sum(ir_l ** 2)) + 1e-9)
ir_r /= (np.sqrt(np.sum(ir_r ** 2)) + 1e-9)

wet_l = fftconvolve(REV_L, ir_l)[:N] * 0.42
wet_r = fftconvolve(REV_R, ir_r)[:N] * 0.42

mix_l = L + wet_l
mix_r = R + wet_r

# Плавный fade-out к самому концу 16.744 s
fade_out = np.ones(N)
s_fo = int((DUR - 0.55) * SR)
e_fo = int(DUR * SR)
fade_out[s_fo:e_fo] = np.linspace(1.0, 0.0, e_fo - s_fo) ** 1.6
fade_out[e_fo:] = 0.0

st = np.column_stack([mix_l, mix_r])[:int(DUR * SR)] * fade_out[:int(DUR * SR), None]
pk = np.max(np.abs(st)) + 1e-9
if pk > 0.85:
    st = np.tanh(st * (0.85 / pk) * 1.15) * 0.85

os.makedirs('audio', exist_ok=True)
out_wav = 'audio/BARH_noir_86bpm.wav'
wavfile.write(out_wav, SR, np.clip(st * 32767, -32767, 32767).astype(np.int16))
rms = 20 * np.log10(np.sqrt(np.mean(st ** 2)) + 1e-9)
print(f'written {out_wav}: {len(st)/SR:.3f}s, peak={np.abs(st).max():.3f}, RMS={rms:.1f} dBFS')
print(f'Beat map (86 BPM, BAR={BAR:.3f}s):')
print(f'  0.000s  HOOK: EXIT-> & empty cabin')
print(f'  {1*BAR:.3f}s  DESCENT: face -> scarf -> wings -> champagne -> SMILE SERVICE REPEAT')
print(f'  {3*BAR:.3f}s  REVEAL: full canvas on dark museum wall')
print(f'  {4*BAR:.3f}s  MACROS: 3 brushstroke close-ups')
print(f'  {5*BAR:.3f}s  FINALE: BARH logo white on black')
