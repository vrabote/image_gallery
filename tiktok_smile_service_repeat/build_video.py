"""Вертикальный ролик 9:16 для TikTok: BARH — «SMILE SERVICE REPEAT».

Идея монтажа: холст вытянут сильнее, чем 9:16, поэтому камера «скроллит»
картину сверху вниз — точно так же, как пользователь скроллит ленту.
Три слова из работы становятся тремя экранными командами, а слово REPEAT
одновременно является инструкцией к пересмотру: чёрный кадр в начале
плавно смыкается с чёрным логотипом в конце ( seamless loop ).

Хронометраж = 8 тактов по 88 BPM (такт 2.727 с), все смены картинки лежат
на долях. Каждые 1–3 с — pattern interrupt; весь смысл читается без звука.

Запуск:  .venv/bin/python build_video.py
Выход:   SMILE_SERVICE_REPEAT_BARH.mp4        (готов к публикации, оригинальный звук)
         SMILE_SERVICE_REPEAT_BARH_silent.mp4 (для подстановки трендового звука в TikTok)
         cover.png                            (обложка = кадр хука)
"""
import os
import sys
import subprocess
from functools import lru_cache

import cv2
import numpy as np
import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont

# ------------------------------------------------------------------ КОНСТАНТЫ
W, H = 1080, 1920
FPS = 30
BPM = 88
BEAT = 60 / BPM
BAR = 4 * BEAT
BARS = 8
DUR = BARS * BAR                                  # 21.818 c

ART = 'artwork.jpg'
AUDIO = 'audio/BARH_original_sound.wav'
OUT = 'SMILE_SERVICE_REPEAT_BARH.mp4'
OUT_SILENT = 'SMILE_SERVICE_REPEAT_BARH_silent.mp4'

# --- Всё, что нужно для A/B-теста хука, меняется здесь ----------------------
HOOK = ['УЛЫБКА —', 'ЧАСТЬ ФОРМЫ']
HOOK_SUB = 'НО ПОСЛЕ СМЕНЫ ЕЁ НЕ СНЯТЬ'
WORDS = [('SMILE', 'УЛЫБНИСЬ'), ('SERVICE', 'ОБСЛУЖИ'), ('REPEAT', 'ПОВТОРИ')]
COMMENT_BAIT = 'УЗНАЁШЬ СВОЮ СМЕНУ?'
# -----------------------------------------------------------------------------

F_ANTON = 'fonts/Anton-Regular.ttf'
F_OSWALD = 'fonts/Oswald-Variable.ttf'
F_MONO = 'fonts/IBMPlexMono-Bold.ttf'
WHITE = (255, 255, 255)
RED = (214, 42, 76)                              # цвет шарфа на холсте
DIM = (206, 212, 222)

SRC = cv2.imread(ART)
if SRC is None:
    raise SystemExit(f'нет файла {ART}')
SH, SW = SRC.shape[:2]
ONES = np.full((SH, SW), 255, np.uint8)


def make_bg(src):
    """Размытое, затемнённое заполнение кадров: видно только на полях при полном холсте."""
    k = max(W / SW, H / SH)
    big = cv2.resize(src, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
    y0 = max(0, (big.shape[0] - H) // 2)
    bg = big[y0:y0 + H, 0:W].astype(np.float32)
    bg = cv2.GaussianBlur(bg, (0, 0), 38)
    return bg * 0.52 + np.array([10, 9, 8], np.float32)


BG = make_bg(SRC)
VIG_Y, VIG_X = np.mgrid[0:H, 0:W].astype(np.float32)
VIG = 1 - 0.40 * (((VIG_X - W / 2) / (W / 2)) ** 2 + ((VIG_Y - H / 2) / (H / 2)) ** 2) * 0.55
VIG = VIG[..., None].astype(np.float32)


# ------------------------------------------------------------------ ТИПОГРАФИКА
@lru_cache(maxsize=512)
def tile(text, path, size, weight, tracking, color):
    """Рендер строки с ручным трекингом в RGBA-плитку (кешируется по параметрам)."""
    f = ImageFont.truetype(path, size)
    if weight:
        f.set_variation_by_axes([weight])
    probe = ImageDraw.Draw(Image.new('RGBA', (4, 4)))
    widths = [probe.textlength(ch, font=f) for ch in text]
    asc, desc = f.getmetrics()
    w = int(sum(widths) + tracking * max(0, len(text) - 1) + 48)
    h = int(asc + desc + 28)
    im = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    x = 24.0
    for ch, cw in zip(text, widths):
        d.text((x, 12), ch, font=f, fill=color + (255,))
        x += cw + tracking
    return np.array(im)


class Canvas:
    """RGBA-слой поверх кадра с корректным alpha-over и обрезкой по краям."""

    def __init__(self):
        self.a = np.zeros((H, W, 4), np.uint8)

    def paste(self, arr, x, y):
        h, w = arr.shape[:2]
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(W, x + w), min(H, y + h)
        if x1 <= x0 or y1 <= y0:
            return
        s = arr[y0 - y:y1 - y, x0 - x:x1 - x].astype(np.float32)
        sa = s[..., 3:4] / 255.0
        d = self.a[y0:y1, x0:x1].astype(np.float32)
        da = d[..., 3:4] / 255.0
        oa = sa + da * (1 - sa)
        rgb = (s[..., :3] * sa + d[..., :3] * da * (1 - sa)) / np.maximum(oa, 1e-6)
        self.a[y0:y1, x0:x1] = np.clip(np.dstack([rgb, oa * 255]), 0, 255).astype(np.uint8)

    def stamp(self, text, center, path, size, weight=0, tracking=0,
              color=WHITE, alpha=1.0, scale=1.0):
        alpha = float(np.clip(alpha, 0, 1))
        if alpha <= 0.001:
            return
        t = tile(text, path, size, weight, tracking, color)
        if scale != 1.0:
            t = cv2.resize(t, (max(1, int(t.shape[1] * scale)), max(1, int(t.shape[0] * scale))),
                           interpolation=cv2.INTER_LINEAR)
        if alpha < 0.999:
            t = t.copy()
            t[..., 3] = (t[..., 3].astype(np.float32) * alpha).astype(np.uint8)
        self.paste(t, int(center[0] - t.shape[1] / 2), int(center[1] - t.shape[0] / 2))

    def rect(self, box, color=WHITE, alpha=1.0):
        x0, y0, x1, y1 = [int(v) for v in box]
        arr = np.zeros((max(1, y1 - y0), max(1, x1 - x0), 4), np.uint8)
        arr[..., :3] = color
        arr[..., 3] = int(255 * np.clip(alpha, 0, 1))
        self.paste(arr, x0, y0)

    def rule(self, cx, y, width, color, thick=3, alpha=1.0):
        self.rect((cx - width / 2, y - thick / 2, cx + width / 2, y + thick / 2), color, alpha)

    def bottom_gradient(self, height=600, strength=210):
        g = np.zeros((height, W, 4), np.uint8)
        ramp = np.linspace(0, 1, height, dtype=np.float32) ** 0.6   # быстро набираем плотность
        g[..., 3] = (ramp[:, None] * strength * np.ones((1, W), np.float32)).astype(np.uint8)
        self.paste(g, 0, H - height)

    def top_gradient(self, height=600, strength=190):
        g = np.zeros((height, W, 4), np.uint8)
        ramp = np.linspace(1, 0, height, dtype=np.float32) ** 0.6
        g[..., 3] = (ramp[:, None] * strength * np.ones((1, W), np.float32)).astype(np.uint8)
        self.paste(g, 0, 0)


def sm(a, b, t):
    q = np.clip((t - a) / max(b - a, 1e-6), 0, 1)
    return q * q * (3 - 2 * q)


def win(t, a, b, fin=0.2, fout=0.2):
    return sm(a, a + fin, t) * (1 - sm(b - fout, b, t))


def punch(t, t0, amp=0.075, tau=0.12):
    return 1 + amp * np.exp(-((t - t0) / tau) ** 2) if t >= t0 else 1.0


# ------------------------------------------------------------------ СЛОВА ПО КАДРАМ
def text_layer(t):
    c = Canvas()
    bait_a = 0.0
    if 5 * BAR + 1.25 <= t < 6 * BAR:
        bait_a = sm(5 * BAR + 1.25, 5 * BAR + 1.55, t)
        c.top_gradient(620, int(200 * bait_a))   # сверху: не перекрываем подпись на холсте

    # Сквозной якорь бренда (визуальная точка опоры между склейками)
    if 0.45 <= t < 6 * BAR + 3 * BEAT:
        c.stamp('BARH · 2026', (168, 92), F_MONO, 27, 0, 4, DIM, 0.40)

    # 0.0–2.727  ХУК. Текст есть уже в самом первом кадре — без «привет» и заставок.
    if t < BAR:
        a = 1 - sm(BAR - 0.22, BAR, t)
        p = punch(t, 0.0, 0.09, 0.13)
        if t < 0.45:
            # чёрная карточка: фразу прочитали ДО того, как увидели лицо
            c.rule(540, 655, 150, RED, 4, a)
            c.stamp(HOOK[0], (540, 770), F_OSWALD, 120, 700, 2, WHITE, a, p)
            c.stamp(HOOK[1], (540, 900), F_OSWALD, 120, 700, 2, WHITE, a * 0.98, p)
            c.stamp(HOOK_SUB, (540, 1030), F_MONO, 30, 0, 5, DIM, a * 0.92)
        else:
            # лицо открыто целиком; текст в нижней безопасной зоне (выше подписи TikTok)
            c.bottom_gradient(900, int(190 * a))
            c.rule(540, 1160, 150, RED, 4, a)
            c.stamp(HOOK[0], (540, 1280), F_OSWALD, 108, 700, 2, WHITE, a, p)
            c.stamp(HOOK[1], (540, 1395), F_OSWALD, 108, 700, 2, WHITE, a, p)
            c.stamp(HOOK_SUB, (540, 1505), F_MONO, 28, 0, 5, DIM, a * 0.92)

    # Три команды «инструкции» — на первом бите каждого такта, со штампом.
    for i, (eng, rus) in enumerate(WORDS):
        t0, t1 = (i + 1) * BAR, (i + 2) * BAR
        if t0 <= t < t1:
            a = 1 - sm(t1 - 0.20, t1, t)
            p = punch(t, t0, 0.075, 0.12)
            c.bottom_gradient(760, int(205 * a))
            c.stamp(f'0{i + 1} / 03', (170, 1230), F_MONO, 30, 0, 6, DIM, a * 0.85)
            c.rule(540, 1490, 210, RED, 4, a)
            c.stamp(eng, (540, 1375), F_ANTON, 140, 0, 8, WHITE, a, p)
            c.stamp(rus, (540, 1550), F_OSWALD, 56, 700, 10, DIM, a)
            if i == 2:
                c.stamp('↻', (890, 1375), F_MONO, 90, 0, 0, WHITE, a * 0.9, p)
                dt = t - t0
                if 0 <= dt < 0.16:                       # глитч-эхо на слове REPEAT
                    c.stamp('REPEAT', (552, 1375), F_ANTON, 140, 0, 8, RED,
                            0.38 * (1 - dt / 0.16), p)

    # Полный холст: титр поверх тёмного градиента, картина остаётся главной.
    if 4 * BAR + 0.90 <= t < 5 * BAR:
        a = sm(4 * BAR + 0.90, 4 * BAR + 1.30, t)
        c.bottom_gradient(800, int(215 * a))
        c.rule(540, 1400, 130, RED, 4, a)
        c.stamp('SMILE  SERVICE  REPEAT', (540, 1480), F_ANTON, 62, 0, 12, WHITE, a)
        c.stamp('BARH · НОВАЯ РАБОТА · 2026', (540, 1560), F_OSWALD, 42, 700, 6, DIM, a)

    # Макро-детали: «Emotional ROI» — доказательство, что это ручная живопись.
    if 5 * BAR <= t < 6 * BAR:
        seg = min(2, int((t - 5 * BAR) / (BAR / 3)))
        labels = ['ФРАГМЕНТ 01 / МАЗОК', 'ФРАГМЕНТ 02 / РУКА', 'ФРАГМЕНТ 03 / ПОДПИСЬ']
        c.stamp(labels[seg], (W - 265, 92), F_MONO, 26, 0, 3, DIM, 0.48)
        if bait_a > 0:
            c.rule(540, 250, 130, RED, 4, bait_a)
            c.stamp(COMMENT_BAIT, (540, 360), F_OSWALD, 80, 700, 1, WHITE, bait_a)
            c.stamp('НАПИШИ В КОММЕНТАРИЯХ', (540, 470), F_MONO, 30, 0, 7, DIM, bait_a)

    # Петля: три слова на чёрном, третье с Circular arrow, затем возврат к хуку.
    if 6 * BAR <= t < 6 * BAR + 3 * BEAT:
        k = min(2, int((t - 6 * BAR) / BEAT))
        t0 = 6 * BAR + k * BEAT
        a = 1 - sm(t0 + 0.42, t0 + 0.62, t)
        p = punch(t, t0, 0.10, 0.13)
        c.stamp(WORDS[k][0], (540, 940), F_ANTON, 200, 0, 14, WHITE, a, p)
        if k == 2:
            c.stamp('↻', (540, 1160), F_MONO, 110, 0, 0, RED, a, p)
        for j in range(3):
            c.rect((515 + j * 35, 1330, 525 + j * 35, 1340), WHITE, 0.22 + 0.65 * (j == k))
    if 6 * BAR + 3 * BEAT <= t < 7 * BAR:
        a = sm(6 * BAR + 3 * BEAT + 0.16, 6 * BAR + 3 * BEAT + 0.40, t)
        c.bottom_gradient(900, int(190 * a))
        c.rule(540, 1160, 150, RED, 4, a)
        c.stamp(HOOK[0], (540, 1280), F_OSWALD, 108, 700, 2, WHITE, a)
        c.stamp(HOOK[1], (540, 1395), F_OSWALD, 108, 700, 2, WHITE, a)
        c.stamp(HOOK_SUB, (540, 1505), F_MONO, 28, 0, 5, DIM, a * 0.9)

    # ФИНАЛ: крупно BARH белым по чёрному. Ничего лишнего в центре кадра.
    if t >= 7 * BAR:
        t0 = 7 * BAR
        a = sm(t0 + 0.08, t0 + 0.26, t)
        p = punch(t, t0 + 0.08, 0.05, 0.16)
        c.stamp('BARH', (540, 880), F_ANTON, 460, 0, 26, WHITE, a, p)
        a2 = sm(t0 + 0.55, t0 + 0.85, t)
        c.rule(540, 1120, 300, WHITE, 2, 0.55 * a2)
        c.stamp('SMILE · SERVICE · REPEAT · 2026', (540, 1210), F_MONO, 30, 0, 10, WHITE, 0.78 * a2)
        c.stamp('ORIGINAL SOUND — BARH', (540, 1760), F_MONO, 24, 0, 8, WHITE, 0.34 * a2)

    return c.a


# ------------------------------------------------------------------ КАМЕРА
def ease(q):
    return q * q * (3 - 2 * q)


def seg(t, a, b, v0, v1):
    return v0 + (v1 - v0) * ease(np.clip((t - a) / (b - a), 0, 1))


def beat_punch(t):
    p = 1.0
    for t0 in (BAR, 2 * BAR, 3 * BAR):
        if t >= t0:
            p += 0.045 * np.exp(-((t - t0) / 0.10) ** 2)
    return p


def camera(t):
    """(видимая высота холста, cx, cy, затемнение, punch, режим)."""
    p = beat_punch(t)
    if t < BAR:                                   # крупно: глаза, губы, воротник
        return seg(t, 0, BAR, 1150, 1000), 690, seg(t, 0, BAR, 690, 720), 0.28, p, 'art'
    if t < 2 * BAR:                               # SMILE — лицо и красный платок
        return seg(t, BAR, 2 * BAR, 1500, 1380), 700, seg(t, BAR, 2 * BAR, 900, 930), 0, p, 'art'
    if t < 3 * BAR:                               # SERVICE — крылышко, рука, тележка
        # Для ещё более «рекламно-безопасного» кадра сдвиньте cx на +150, cy на +250:
        # тогда в кадре останутся только крылышко, рука и тележка.
        return (seg(t, 2 * BAR, 3 * BAR, 1600, 1450),
                seg(t, 2 * BAR, 3 * BAR, 780, 920),
                seg(t, 2 * BAR, 3 * BAR, 1400, 1900), 0, p, 'art')
    if t < 4 * BAR:                               # REPEAT — надпись на тележке
        return (seg(t, 3 * BAR, 4 * BAR, 1250, 1120),
                seg(t, 3 * BAR, 4 * BAR, 980, 1040),
                seg(t, 3 * BAR, 4 * BAR, 2380, 2500), 0, p, 'art')
    if t < 5 * BAR:                               # РЕВИЛ: отъезд на весь холст
        q = 1 - (1 - np.clip((t - 4 * BAR) / 1.30, 0, 1)) ** 3
        return 1120 + (3904 - 1120) * q, 1040 + (692 - 1040) * q, 2500 + (1952 - 2500) * q, 0, 1, 'art'
    if t < 6 * BAR:                               # три макро-детали подряд
        d = t - 5 * BAR
        if d < BAR / 3:
            return seg(t, 5 * BAR, 5 * BAR + BAR / 3, 640, 600), 640, 1330, 0, 1, 'art'
        if d < 2 * BAR / 3:
            return seg(t, 5 * BAR + BAR / 3, 5 * BAR + 2 * BAR / 3, 700, 660), 900, 1830, 0, 1, 'art'
        return seg(t, 5 * BAR + 2 * BAR / 3, 6 * BAR, 520, 480), 130, 3655, 0, 1, 'art'
    if t < 6 * BAR + 3 * BEAT:                    # чёрные штампы слов
        return None, None, None, 1, 1, 'black'
    if t < 7 * BAR:                               # возврат ровно на кадр хука = петля
        a, b = 6 * BAR + 3 * BEAT, 7 * BAR
        return seg(t, a, b, 1150, 1000), 690, 700, 0.28, 1, 'art'
    return None, None, None, 1, 1, 'black'       # логотип


CUTS = [0.45, BAR, 2 * BAR, 3 * BAR, 4 * BAR, 5 * BAR,
        5 * BAR + BAR / 3, 5 * BAR + 2 * BAR / 3,
        6 * BAR, 6 * BAR + 3 * BEAT, 7 * BAR]


def warp(vh, cx, cy, p):
    s = H * p / vh
    M = np.array([[s, 0, W / 2 - s * cx], [0, s, H / 2 - s * cy]], np.float32)
    sharp = cv2.warpAffine(SRC, M, (W, H), flags=cv2.INTER_LINEAR,
                           borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0)).astype(np.float32)
    mask = cv2.warpAffine(ONES, M, (W, H), flags=cv2.INTER_LINEAR,
                          borderMode=cv2.BORDER_CONSTANT, borderValue=0).astype(np.float32) / 255
    a = mask[..., None]
    return BG * (1 - a) + sharp * a


def render_frame(t):
    vh, cx, cy, dark, p, mode = camera(t)
    if mode == 'black' or t < 0.45:
        frame = np.zeros((H, W, 3), np.float32)
    else:
        frame = warp(vh, cx, cy, p)
        if 5 * BAR + 2 * BAR / 3 <= t < 6 * BAR:
            frame = frame * 1.32 + 8               # подпись написана по почти чёрному фону
        frame *= (1 - dark)
        frame[..., 0] *= 1.04                     # чуть холоднее синий мундир
        frame[..., 2] *= 0.985
        frame = (frame - 118) * 1.07 + 118
        frame *= VIG

    # вспышки на склейках (одна белая — на ревиле)
    for cut in CUTS:
        dt = t - cut
        if 0 <= dt < 0.066:
            k = 1 - dt / 0.066
            if abs(cut - 4 * BAR) < 1e-6:
                frame = frame * (1 - 0.30 * k) + 255 * 0.30 * k
            else:
                frame *= 1 - 0.32 * k

    # RGB-сдвиг на слове REPEAT и в петле
    if (3 * BAR + 2.0 <= t < 3 * BAR + 2.09) or (3 * BAR + 2.18 <= t < 3 * BAR + 2.25):
        sh = 9
        frame[:, :, 0] = np.roll(frame[:, :, 0], sh, axis=1)
        frame[:, :, 2] = np.roll(frame[:, :, 2], -sh, axis=1)
        frame[960:964, :] = 255

    # whip-pan: возврат к хуку
    tw = 6 * BAR + 3 * BEAT
    if tw <= t < tw + 0.28:
        k = 1 - (t - tw) / 0.28
        frame = cv2.blur(frame, (1 + int(38 * k), 1))
        frame += 18 * k

    # лёгкое зерно: «плёнка», а не стерильный цифровой зум
    noise = cv2.resize(rng_noise(), (W, H), interpolation=cv2.INTER_LINEAR)
    frame += noise[..., None]

    layer = text_layer(t).astype(np.float32)
    a = layer[..., 3:4] / 255.0
    frame = frame * (1 - a) + layer[..., :3][:, :, ::-1] * a
    return np.clip(frame, 0, 255).astype(np.uint8)


def rng_noise():
    return np.random.default_rng(1 + int(_frame_no[0]) % 7).uniform(-2.2, 2.2, (480, 270)).astype(np.float32)


_frame_no = [0]

# ------------------------------------------------------------------ СБОРКА
def main():
    os.makedirs('work', exist_ok=True)
    if not os.path.exists(AUDIO):
        subprocess.run([sys.executable, 'make_audio.py'], check=True)
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    raw = 'work/video_silent.mp4'
    cmd = [ff, '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'bgr24',
           '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-', '-an', '-c:v', 'libx264',
           '-preset', 'medium', '-crf', '17', '-profile:v', 'high', '-pix_fmt', 'yuv420p',
           '-movflags', '+faststart', raw]
    enc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    n = int(DUR * FPS)
    for i in range(n):
        _frame_no[0] = i
        enc.stdin.write(render_frame(i / FPS).tobytes())
        if i % 150 == 0:
            print(f'  кадр {i}/{n}', flush=True)
    enc.stdin.close()
    if enc.wait() != 0:
        raise SystemExit('ошибка кодирования видео')

    subprocess.run([ff, '-y', '-loglevel', 'error', '-i', raw, '-i', AUDIO,
                    '-map', '0:v', '-map', '1:a', '-af', 'loudnorm=I=-14:TP=-1.0:LRA=11',
                    '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-ar', '48000',
                    '-movflags', '+faststart', '-shortest', OUT], check=True)
    subprocess.run([ff, '-y', '-loglevel', 'error', '-i', OUT, '-c', 'copy', '-an',
                    '-movflags', '+faststart', OUT_SILENT], check=True)
    subprocess.run([ff, '-y', '-loglevel', 'error', '-ss', '1.05', '-i', OUT,
                    '-frames:v', '1', 'cover.png'], check=True)
    os.remove(raw)
    try:
        os.rmdir('work')
    except OSError:
        pass
    print(f'готово: {OUT}  {DUR:.2f}s  {n} кадров  {W}x{H}')
    print(f'       {OUT_SILENT} (без звука — под трендовый аудио)')
    print('       cover.png')


if __name__ == '__main__':
    main()
