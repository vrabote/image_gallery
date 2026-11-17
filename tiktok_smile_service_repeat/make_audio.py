"""ОРИГИНАЛЬНЫЙ ЗВУК BARH для ролика «SMILE SERVICE REPEAT».

Почему не модный трек: у бизнес-аккаунтов TikTok большинство популярных песен
недоступны (Commercial Music Library), а окно жизни звука — 7–10 дней.
Свой звук живёт вечно, привязан к ролику и может сам стать трендом.

Стилистика: slowed / moody / bass-heavy, 88 BPM, A minor, 8 тактов = 21.818 с.
Структура повторяет монтаж (см. beat map в конце):
  такт 0  — звонок салона самолёта + гул + пульс (хук)
  такт 1  — DROP: бас, кик, тиканье часов, первое слово SMILE
  такты 2–3 — грув, слова SERVICE / REPEAT, статтер на REPEAT
  такт 4  — БРЕЙК: уходят барабаны, пад разворачивается (полный холст)
  такт 5  — возврат битa, макросъёмка мазков
  такт 6  — три штампа-слова + райзер
  такт 7  — жёсткий срез в тишину: саб-удар и длинный хвост (лого BARH)

Запуск: .venv/bin/python make_audio.py
"""
import os
import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, sosfilt, fftconvolve, resample_poly

SR = 48000
BPM = 88
BEAT = 60 / BPM
BAR = 4 * BEAT
BARS = 8
DUR = BARS * BAR                       # 21.8182 c
rng = np.random.default_rng(2026)
N = int((DUR + 4.0) * SR)


def bus():
    return np.zeros(N), np.zeros(N)


pad, pluck, bass, drum, fx, send = (bus() for _ in range(6))


def lp(x, fc, o=2):
    return sosfilt(butter(o, min(fc, SR / 2 - 100), 'low', fs=SR, output='sos'), x)


def hp(x, fc, o=2):
    return sosfilt(butter(o, fc, 'high', fs=SR, output='sos'), x)


def bp(x, lo, hi, o=3):
    return sosfilt(butter(o, [lo, min(hi, SR / 2 - 100)], 'band', fs=SR, output='sos'), x)


def put(b, x, t0, pan=0.5, g=1.0, snd=0.0):
    s = int(t0 * SR)
    if s < 0 or s >= N:
        return
    e = min(N, s + len(x))
    x = x[:e - s] * g
    c, sn = np.cos(pan * np.pi / 2), np.sin(pan * np.pi / 2)
    b[0][s:e] += x * c
    b[1][s:e] += x * sn
    if snd:
        send[0][s:e] += x * c * snd
        send[1][s:e] += x * sn * snd


def mf(m):
    return 440 * 2 ** ((m - 69) / 12)


def osc(kind, f, n, ph0=0.0, w=0.5, over=2):
    t = np.arange(n * over) / (SR * over)
    ph = (f * t + ph0) % 1
    y = (2 * ph - 1) if kind == 'saw' else np.where(ph < w, 1.0, -1.0)
    if kind == 'tri':
        y = 1 - 4 * np.abs(ph - 0.5)
    if kind == 'sine':
        y = np.sin(2 * np.pi * ph)
    return resample_poly(y, 1, over)


def adsr(n, a, d, s, r):
    t = np.arange(n) / SR
    dur = n / SR
    e = np.minimum(1, t / max(a, 1e-4)) * (s + (1 - s) * np.exp(-np.maximum(t - a, 0) / max(d, 1e-4)))
    return e * np.minimum(1, np.maximum(dur - t, 0) / max(r, 1e-4))


# Am – F – C – G, с возвратом в Am на пике и на логотипе
CH = [
    dict(root=45, pad=[57, 60, 64, 69], arp=[69, 72, 76, 72]),  # Am
    dict(root=41, pad=[53, 57, 60, 65], arp=[65, 69, 72, 69]),  # F
    dict(root=48, pad=[55, 60, 64, 67], arp=[67, 72, 76, 72]),  # C
    dict(root=43, pad=[55, 59, 62, 67], arp=[62, 67, 71, 67]),  # G
    dict(root=45, pad=[57, 60, 64, 72], arp=[69, 72, 76, 81]),  # Am (wide)
    dict(root=41, pad=[53, 57, 60, 65], arp=[65, 69, 72, 77]),  # F
    dict(root=45, pad=[57, 60, 64, 69], arp=[69, 72, 76, 72]),  # Am
    dict(root=45, pad=[57, 60, 64, 69], arp=[69, 72, 76, 72]),  # Am (outro)
]


def chorus(x, rate=0.29, depth=0.007):
    t = np.arange(len(x)) / SR
    d = (0.019 + depth * np.sin(2 * np.pi * rate * t)) * SR
    idx = np.arange(len(x)) - d
    return np.interp(np.clip(idx, 0, len(x) - 1), np.arange(len(x)), x)


# ------------------------------------------------------------------ PAD
for b in range(BARS):
    c = CH[b]
    t0 = max(0.0, b * BAR - 0.55)
    dur = BAR + 2.2 + (2.6 if b == BARS - 1 else 0)
    n = int(dur * SR)
    mix = np.zeros(n)
    for m in c['pad']:
        for d in (-0.0042, 0.0042):        # расстройка = «плёночный» slowed-саунд
            mix += osc('saw', mf(m) * (1 + d), n, rng.random(), over=1)
    wobble = 1 + 0.0016 * np.sin(2 * np.pi * 0.7 * np.arange(n) / SR)
    mix = lp(mix, 820 + 340 * np.sin(b * 0.8)) * adsr(n, 1.1, 5, 1, 1.5) * 0.052 * wobble
    put(pad, mix, t0, 0.5, 1.0, snd=0.6)
pad = (0.68 * pad[0] + 0.52 * chorus(pad[0], 0.27),
       0.68 * pad[1] + 0.52 * chorus(pad[1], 0.41, 0.009))

# --------------------------------------------------------------- PLUCK
for b in range(1, 7):
    c = CH[b]
    for i in range(8):
        if b == 4 and i % 2 == 1:          # брейк: оставляем воздух
            continue
        m = c['arp'][[0, 2, 1, 3, 0, 2, 3, 1][i]]
        f = mf(m)
        n = int(0.42 * SR)
        t = np.arange(n) / SR
        x = 0.75 * osc('tri', f, n) + 0.25 * osc('sine', f * 2, n)
        x += 0.05 * bp(rng.standard_normal(n), 1800, 6000) * np.exp(-t / 0.008)
        x = lp(x, 2600) * adsr(n, 0.003, 0.16, 0.12, 0.12) * 0.16
        vel = 0.55 if b == 4 else (1.0 if i % 2 == 0 else 0.72)
        put(pluck, x, b * BAR + i * BEAT / 2, 0.36 + 0.28 * (i % 2), vel, snd=0.55)

# ---------------------------------------------------------------- BASS
for b in range(1, 7):
    c = CH[b]
    r = mf(c['root'])
    for q in range(4):
        if b == 4 and q in (1, 2, 3):      # брейк: только опора на первую долю
            continue
        if b == 3 and q == 3:              # статтер на слове REPEAT
            for k in range(3):
                nn = int(0.09 * SR)
                xx = (0.7 * osc('saw', r * (1 + 0.01 * k), nn) + 0.6 * osc('sine', r, nn))
                xx = lp(xx, 420) * adsr(nn, 0.002, 0.05, 0.3, 0.02) * 0.34
                put(bass, xx, b * BAR + q * BEAT + k * 0.11, 0.5, 0.8)
            continue
        nn = int(BEAT * 0.86 * SR)
        xx = 0.55 * osc('saw', r, nn) + 0.85 * osc('sine', r / 2, nn)
        xx = lp(xx, 360) * adsr(nn, 0.004, 0.22, 0.55, 0.05) * 0.42
        put(bass, xx, b * BAR + q * BEAT, 0.5, 1.0 if q in (0, 2) else 0.62)

# --------------------------------------------------------------- DRUMS
def kick():
    n = int(0.45 * SR)
    t = np.arange(n) / SR
    f = 46 + 120 * np.exp(-t / 0.028)
    ph = 2 * np.pi * np.cumsum(f) / SR
    return (np.sin(ph) * np.exp(-t / 0.17)
            + 0.22 * bp(rng.standard_normal(n), 1400, 5200) * np.exp(-t / 0.006))


def clap():
    n = int(0.42 * SR)
    x = np.zeros(n)
    t = np.arange(n) / SR
    for o in (0, 0.011, 0.023):
        s = int(o * SR)
        k = int(0.09 * SR)
        x[s:s + k] += bp(rng.standard_normal(k), 900, 5200) * np.exp(-np.arange(k) / SR / 0.018)
    m = int(0.03 * SR)
    x[m:] += bp(rng.standard_normal(n - m), 900, 4200) * np.exp(-t[:n - m] / 0.11) * 0.4
    return x


def hat(op=False):
    n = int((0.24 if op else 0.045) * SR)
    return hp(rng.standard_normal(n), 7200) * np.exp(-np.arange(n) / SR / (0.085 if op else 0.013))


for b in [1, 2, 3, 5, 6]:
    for q in range(4):
        put(drum, kick(), b * BAR + q * BEAT if q in (0, 2) else b * BAR + q * BEAT, 0.5,
            0.8 if q in (0, 2) else 0.0)
        put(drum, hat(), b * BAR + q * BEAT + BEAT / 2, 0.62, 0.16)
        if q in (1, 3) and b >= 2:
            put(drum, clap(), b * BAR + q * BEAT, 0.5, 0.30, snd=0.5)
        if b >= 2:
            # «тики» часов: 16-е, мотив бесконечной смены
            for j in range(4):
                put(drum, hat(), b * BAR + q * BEAT + j * BEAT / 4, 0.42 + 0.16 * j, 0.045)
    put(drum, hat(True), b * BAR + 3.5 * BEAT, 0.58, 0.11)
# мягкая опора в такте брейка
put(drum, kick(), 4 * BAR, 0.5, 0.42, snd=0.5)

# ------------------------------------------------------------------ FX
def chime(t0, f1=1046.5, f2=1318.5, g=0.20):
    n = int(1.5 * SR)
    t = np.arange(n) / SR
    x = (np.sin(2 * np.pi * f1 * t) + 0.75 * np.sin(2 * np.pi * f2 * t)
         + 0.18 * np.sin(2 * np.pi * f1 * 2 * t))
    x *= np.exp(-t / 0.42) * np.minimum(1, t / 0.004)
    put(fx, lp(x, 5200) * g, t0, 0.5, 1.0, snd=0.85)
    put(fx, lp(x, 5200) * g * 0.8, t0 + 0.23, 0.5, 1.0, snd=0.7)


def stamp(t0, g=1.0):
    n = int(0.20 * SR)
    t = np.arange(n) / SR
    x = bp(rng.standard_normal(n), 350, 3800) * np.exp(-t / 0.026)
    thud = np.sin(2 * np.pi * 95 * t) * np.exp(-t / 0.055) * 0.5
    put(fx, (x * 0.55 + thud) * 0.35 * g, t0, 0.5, 1.0, snd=0.5)


def shutter(t0, g=1.0):
    n = int(0.075 * SR)
    t = np.arange(n) / SR
    x = hp(rng.standard_normal(n), 2600) * np.exp(-t / 0.008) * 0.22 * g
    put(fx, x, t0, 0.62, 1.0)


def riser(a, b):
    n = int((b - a) * SR)
    x = np.zeros(n)
    blk = int(0.08 * SR)
    for i in range(0, n - blk, blk):
        q = i / n
        fc = 280 * (30 ** q)
        x[i:i + blk] = bp(rng.standard_normal(blk), fc * 0.7, fc * 1.5, 2) * q ** 2
    put(send, x * 0.55, a, 0.5, 1.0)


def boom(t0):
    n = int(2.1 * SR)
    t = np.arange(n) / SR
    f = 58 * np.exp(-t / 0.6) + 32
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.85) * 0.7
    x += bp(rng.standard_normal(n), 60, 700) * np.exp(-t / 0.18) * 0.12
    put(fx, x, t0, 0.5, 1.0, snd=1.0)


chime(0.02)                                            # звонок «пристегните ремни»
# гул салона
n = int(4 * BAR * SR)
rumble = lp(np.cumsum(rng.standard_normal(n)), 160)
rumble /= np.sqrt((rumble ** 2).mean()) + 1e-9       # нормируем: броуновский шум легко уходит в клиппинг
rumble *= 0.030
rumble *= np.minimum(1, np.arange(n) / SR / 0.6) * np.minimum(1, (4 * BAR - np.arange(n) / SR) / 1.2)
put(fx, rumble, 0.0, 0.5, 1.0)
for k, t0 in enumerate([BAR, 2 * BAR, 3 * BAR]):
    stamp(t0, 1.0 if k == 0 else 0.82)                # слова SMILE / SERVICE / REPEAT
shutter(4 * BAR, 0.5)                                 # белая вспышка на ревиле
for k in range(3):
    stamp(6 * BAR + k * BEAT, 0.42)                   # три штампа в лупе
    shutter(6 * BAR + k * BEAT, 0.35)
shutter(5 * BAR, 0.6)
riser(6 * BAR + 2 * BEAT, 7 * BAR)
boom(7 * BAR)

# ------------------------------------------------------------- DELAY / REVERB
def delay(x, time, fb, n=4, tone=3200):
    y = np.zeros(len(x))
    cur = lp(x, tone)
    for k in range(1, n + 1):
        s = int(k * time * SR)
        cur = lp(cur, tone) * fb
        y[s:] += cur[:len(x) - s]
    return y


pluck_e = (pluck[0] + 0.45 * delay(pluck[1], 0.75 * BEAT, 0.42),
           pluck[1] + 0.45 * delay(pluck[0], 0.75 * BEAT, 0.42))


def ir(sec=2.8):
    n = int(sec * SR)
    t = np.arange(n) / SR
    x = rng.standard_normal(n) * np.exp(-t / 0.75)
    x = lp(x, 5800)
    x[:int(0.012 * SR)] *= np.linspace(0, 1, int(0.012 * SR))
    return x / np.sqrt((x ** 2).sum())


wet = (fftconvolve(send[0], ir())[:N], fftconvolve(send[1], ir())[:N])
M = int(DUR * SR)
L = pad[0] + pluck_e[0] + bass[0] + drum[0] + fx[0] + 1.7 * wet[0]
R = pad[1] + pluck_e[1] + bass[1] + drum[1] + fx[1] + 1.7 * wet[1]
y = np.stack([L[:M], R[:M]], 1)
t = np.arange(M) / SR
y *= np.minimum(1, t / 0.06)[:, None]                       # без «вздоха» на старте
y *= np.minimum(1, np.maximum(DUR - t, 0) / 1.15)[:, None]  # хвост уходит в чёрный кадр
y = hp(y.T, 32).T
y = np.tanh(y * 1.5) * 0.72
y *= 0.16 / np.sqrt((y ** 2).mean())
y = np.clip(y / max(1.0, np.abs(y).max() / 0.96), -1, 1)

os.makedirs('audio', exist_ok=True)
wavfile.write('audio/BARH_original_sound.wav', SR, (y * 32767).astype(np.int16))
print(f'audio/BARH_original_sound.wav  {DUR:.3f}s  peak={np.abs(y).max():.3f}  '
      f'rms={20*np.log10(np.sqrt((y**2).mean())):.1f} dBFS')
print('beat map (BPM 88, bar = %.3fs):' % BAR)
for name, k in [('HOOK', 0), ('DROP / SMILE', 1), ('SERVICE', 2), ('REPEAT', 3),
                ('REVEAL / BREAK', 4), ('DETAILS', 5), ('LOOP', 6), ('LOGO BARH', 7)]:
    print(f'  {name:<18} {k*BAR:6.3f}s')
