"""Вертикальный ролик 9:16 для TikTok: BARH — «SMILE SERVICE REPEAT» (Кино-нуар).

Сценарий «После рейса» (86 BPM, 6 тактов = 16.744 с):
  0.000 – 2.791 с  Хук: табличка EXIT ->, свет иллюминатора, звук затихающего салона,
                   одна короткая кино-строка в стиле субтитра.
  2.791 – 8.372 с  Непрерывный спуск камеры сверху вниз (без единой склейки и
                   без лишних титров) до надписи SMILE / SERVICE / REPEAT на тележке.
  8.372 – 11.163 с Полный галерейный показ холста на матовом тёмном фоне (без мыла).
 11.163 – 13.953 с Три быстрых макро-кадра фактуры мазков (живая краска, не цифра).
 13.953 – 16.744 с Финал: крупный фирменный рукописный логотип BARH белым на чёрном.

Темп 86 BPM соответствует треку Steve Lacy — «the feeling» (Nov 2026 TikTok),
поэтому беззвучная версия идеально ложится в бит прямо в TikTok.

Запуск: ../.venv/bin/python build_video.py
"""
import os
import sys
import subprocess
from functools import lru_cache

import cv2
import numpy as np
import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont
from scipy.interpolate import PchipInterpolator

# ------------------------------------------------------------------ КОНСТАНТЫ
W, H = 1080, 1920
FPS = 30
BPM = 86
BEAT = 60.0 / BPM                         # 0.697674 s
BAR = 4 * BEAT                            # 2.790698 s
BARS = 6
DUR = BARS * BAR                          # 16.744186 s

ART = 'artwork.jpg'
LOGO_PATH = 'barh_logo_white.png'
AUDIO = 'audio/BARH_noir_86bpm.wav'
OUT = 'SMILE_SERVICE_REPEAT_BARH.mp4'
OUT_SILENT = 'SMILE_SERVICE_REPEAT_BARH_silent.mp4'

F_SERIF_IT = 'fonts/InstrumentSerif-Italic.ttf'
F_MONO = 'fonts/IBMPlexMono-Regular.ttf'

SRC = cv2.imread(ART)
if SRC is None:
    raise SystemExit(f'нет файла {ART}')
SH, SW = SRC.shape[:2]
ONES = np.full((SH, SW), 255, np.float32)

LOGO = cv2.imread(LOGO_PATH, cv2.IMREAD_UNCHANGED)
if LOGO is None:
    raise SystemExit(f'нет файла {LOGO_PATH}')
LW = 720
LH = int(LOGO.shape[0] * LW / LOGO.shape[1])
LOGO_RS = cv2.resize(LOGO, (LW, LH), interpolation=cv2.INTER_AREA).astype(np.float32)
LOGO_ALPHA = LOGO_RS[..., 3:4] / 255.0

# ------------------------------------------------------------------ ГАЛЕРЕЙНЫЙ ФОН
# Матовый тёмный галерейный фон с мягким верхним софитом и дизерингом против бандинга
gy, gx = np.mgrid[0:H, 0:W].astype(np.float32)
spot_r = ((gx - W / 2) / (W * 0.64)) ** 2 + ((gy - H * 0.38) / (H * 0.58)) ** 2
GALLERY_BG = np.zeros((H, W, 3), np.float32)
spot = np.exp(-spot_r * 1.45)
_dither = np.random.default_rng(77).uniform(-0.75, 0.75, (H, W, 1)).astype(np.float32)
GALLERY_BG[..., 0] = 9 + 17 * spot        # B (холодный графит)
GALLERY_BG[..., 1] = 9 + 15 * spot        # G
GALLERY_BG[..., 2] = 11 + 16 * spot       # R
GALLERY_BG += _dither

# Мягкая кино-виньетка для крупных планов
VIG = 1.0 - 0.30 * (((gx - W / 2) / (W / 2)) ** 2 + ((gy - H / 2) / (H / 2)) ** 2) * 0.55
VIG = VIG[..., None].astype(np.float32)

# Частицы пыли в тёплом луче салона (для первых 3.5 секунд)
_rng_dust = np.random.default_rng(42)
N_DUST = 28
DUST_X0 = _rng_dust.uniform(60, W - 60, N_DUST)
DUST_Y0 = _rng_dust.uniform(180, H - 300, N_DUST)
DUST_VX = _rng_dust.uniform(-16, 12, N_DUST)
DUST_VY = _rng_dust.uniform(-28, -8, N_DUST)
DUST_RAD = _rng_dust.uniform(1.5, 3.6, N_DUST)
DUST_PH = _rng_dust.uniform(0, 2 * np.pi, N_DUST)

# Плавный монотонный спуск камеры (Bars 0 -> 2):
# 0.00-1.15s держим EXIT -> и штору, затем плавно переходим на свет и лицо,
# и одним непрерывным движением спускаемся до full-bleed тележки SMILE SERVICE REPEAT.
_KP_T = np.array([0.00, 1.05, 1.95, BAR, 1.5 * BAR, 2.0 * BAR, 2.5 * BAR, 2.86 * BAR, 3.0 * BAR])
_KP_VH = np.array([720, 780, 1080, 1180, 1280, 1340, 1320, 1240, 1190], np.float64)
_KP_CX = np.array([1178, 1152, 760, 700, 675, 795, 935, 1028, 1044], np.float64)
_KP_CY = np.array([130, 185, 520, 620, 1180, 1630, 2220, 2495, 2505], np.float64)
SP_VH = PchipInterpolator(_KP_T, _KP_VH)
SP_CX = PchipInterpolator(_KP_T, _KP_CX)
SP_CY = PchipInterpolator(_KP_T, _KP_CY)


def sm(a, b, t):
    q = np.clip((t - a) / max(b - a, 1e-6), 0.0, 1.0)
    return float(q * q * (3.0 - 2.0 * q))


# ------------------------------------------------------------------ ТИПОГРАФИКА
@lru_cache(maxsize=64)
def render_text_tile(text, font_path, size, tracking, color, shadow=True):
    f = ImageFont.truetype(font_path, size)
    probe = ImageDraw.Draw(Image.new('RGBA', (4, 4)))
    widths = [probe.textlength(ch, font=f) for ch in text]
    asc, desc = f.getmetrics()
    tw = int(sum(widths) + tracking * max(0, len(text) - 1) + 56)
    th = int(asc + desc + 36)
    im = Image.new('RGBA', (tw, th), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if shadow:
        x = 28.0
        for ch, cw in zip(text, widths):
            d.text((x + 2, 16), ch, font=f, fill=(0, 0, 0, 185))
            x += cw + tracking
    x = 28.0
    for ch, cw in zip(text, widths):
        d.text((x, 14), ch, font=f, fill=color + (255,))
        x += cw + tracking
    return np.array(im)


def overlay_tile(frame, tile, cx, cy, alpha):
    if alpha <= 0.002:
        return frame
    h, w = tile.shape[:2]
    x0 = int(cx - w / 2)
    y0 = int(cy - h / 2)
    x1, y1 = max(0, x0), max(0, y0)
    x2, y2 = min(W, x0 + w), min(H, y0 + h)
    if x2 <= x1 or y2 <= y1:
        return frame
    sub = tile[y1 - y0:y2 - y0, x1 - x0:x2 - x0].astype(np.float32)
    a = (sub[..., 3:4] / 255.0) * alpha
    rgb = sub[..., :3][..., ::-1]  # RGBA -> BGR
    frame[y1:y2, x1:x2] = frame[y1:y2, x1:x2] * (1.0 - a) + rgb * a
    return frame


def warp_art(vh, cx, cy, bg):
    s = H / vh
    M = np.array([[s, 0.0, W / 2.0 - s * cx],
                  [0.0, s, H / 2.0 - s * cy]], np.float32)
    sharp = cv2.warpAffine(SRC, M, (W, H), flags=cv2.INTER_CUBIC,
                           borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0)).astype(np.float32)
    mask = cv2.warpAffine(ONES, M, (W, H), flags=cv2.INTER_LINEAR,
                          borderMode=cv2.BORDER_CONSTANT, borderValue=0.0) / 255.0
    a = mask[..., None]
    return bg * (1.0 - a) + sharp * a


def draw_full_canvas(t):
    """Полный показ холста на матовой тёмной галерейной стене с тенью."""
    q_pull = sm(3 * BAR, 3 * BAR + 0.52, t)
    # Плавный отъезд от тележки (cy=2505, vh=1300) к полному холсту
    full_h = 1350.0 + 40.0 * ((t - 3 * BAR) / BAR)      # 1350 -> 1390 px на экране
    full_vh = SH * (H / full_h)
    full_cx = SW / 2.0
    # Центр холста чуть выше геометрического центра (внутри безопасной зоны TikTok)
    target_screen_cy = 845.0
    full_cy = SH / 2.0 + (H / 2.0 - target_screen_cy) * (SH / full_h)

    if q_pull < 0.999:
        ease_out = 1.0 - (1.0 - q_pull) ** 3
        vh = 1190.0 + (full_vh - 1190.0) * ease_out
        cx = 1044.0 + (full_cx - 1044.0) * ease_out
        cy = 2505.0 + (full_cy - 2505.0) * ease_out
    else:
        vh, cx, cy = full_vh, full_cx, full_cy

    s = H / vh
    M = np.array([[s, 0.0, W / 2.0 - s * cx],
                  [0.0, s, H / 2.0 - s * cy]], np.float32)
    sharp = cv2.warpAffine(SRC, M, (W, H), flags=cv2.INTER_AREA,
                           borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0)).astype(np.float32)
    mask = cv2.warpAffine(ONES, M, (W, H), flags=cv2.INTER_LINEAR,
                          borderMode=cv2.BORDER_CONSTANT, borderValue=0.0) / 255.0

    # Мягкая глубокая тень холста на стене
    shadow = np.roll(mask, (24, 14), axis=(0, 1))
    shadow = cv2.GaussianBlur(shadow, (0, 0), 28) * 0.68 * q_pull
    bg = GALLERY_BG * (1.0 - shadow[..., None])
    a = mask[..., None]
    frame = bg * (1.0 - a) + sharp * a
    return frame


def render_frame(t, frame_idx):
    # ------------------------------------------------- BAR 5: ФИНАЛ BARH НА ЧЁРНОМ
    if t >= 5 * BAR:
        frame = np.zeros((H, W, 3), np.float32)
        dt = t - 5 * BAR
        # Быстрая прорисовка фирменной кисти слева направо (0.00 -> 0.78 с), затем чистая выдержка
        q = np.clip((dt - 0.05) / 0.72, 0.0, 1.0)
        q = q * q * (3.0 - 2.0 * q)
        cols = np.arange(LW, dtype=np.float32)[None, :, None]
        edge = LW * q * 1.18 - 0.18 * LW
        wipe = np.clip((edge - cols) / (0.18 * LW), 0.0, 1.0)
        fade = np.clip(dt / 0.14, 0.0, 1.0)
        # Белый логотип на чистом чёрном
        x0 = (W - LW) // 2
        y0 = (H - LH) // 2 - 30
        ink = 255.0 * LOGO_ALPHA * wipe * fade
        frame[y0:y0 + LH, x0:x0 + LW] = ink
        return np.clip(frame, 0, 255).astype(np.uint8)

    # ------------------------------------------------- BAR 3: ПОЛНЫЙ ПОКАЗ ХОЛСТА
    if 3 * BAR <= t < 4 * BAR:
        frame = draw_full_canvas(t)
        # Лёгкая кинематографичная контрастность
        frame = (frame - 118.0) * 1.05 + 118.0
        # Аккуратное название работы прямо под картиной в безопасной зоне (y=1572)
        a_title = sm(3 * BAR + 0.45, 3 * BAR + 0.95, t) * (1.0 - sm(4 * BAR - 0.12, 4 * BAR, t))
        if a_title > 0.005:
            tile = render_text_tile('SMILE  SERVICE  REPEAT', F_MONO, 24, 9, (226, 222, 214), shadow=False)
            frame = overlay_tile(frame, tile, W / 2, 1572, a_title * 0.85)
        return np.clip(frame, 0, 255).astype(np.uint8)

    # ------------------------------------------------- BAR 4: 3 МАКРО-КАДРА ЖИВЫХ МАЗКОВ
    if 4 * BAR <= t < 5 * BAR:
        d = t - 4 * BAR
        step = BAR / 3.0
        if d < step:
            p = d / step
            frame = warp_art(470.0 - 32.0 * p, 695.0, 585.0, GALLERY_BG)
        elif d < 2.0 * step:
            p = (d - step) / step
            frame = warp_art(470.0 - 30.0 * p, 845.0 + 18.0 * p, 1455.0, GALLERY_BG)
        else:
            p = (d - 2.0 * step) / step
            frame = warp_art(590.0 - 36.0 * p, 1135.0, 2515.0, GALLERY_BG)
        frame = (frame - 118.0) * 1.07 + 118.0
        frame *= VIG
        # Мягкая короткая вспышка на резкой склейке между мазками
        for tc in (4 * BAR, 4 * BAR + step, 4 * BAR + 2.0 * step):
            dt = t - tc
            if 0.0 <= dt < 0.07:
                frame *= (1.0 - 0.25 * (1.0 - dt / 0.07))
        return np.clip(frame, 0, 255).astype(np.uint8)

    # ------------------------------------------------- BARS 0–2: ХУК EXIT-> И НЕПРЕРЫВНЫЙ СПУСК
    vh = float(SP_VH(t))
    cx = float(SP_CX(t))
    cy = float(SP_CY(t))
    frame = warp_art(vh, cx, cy, GALLERY_BG)

    # В самом начале (0.0..1.2 с) — тёплая тень потолка салона над краем холста и лёгкая вспышка EXIT
    if t < 1.35:
        ceil_fade = np.clip((gy - 120.0) / 360.0, 0.0, 1.0)
        mix_k = 1.0 - sm(0.65, 1.35, t)
        frame *= (1.0 - mix_k + mix_k * ceil_fade[..., None])

    # Тёплый кино-грейд и лёгкая плёночная контрастность
    frame[..., 2] *= 1.02
    frame[..., 0] *= 0.99
    frame = (frame - 118.0) * 1.06 + 118.0
    frame *= VIG

    # Едва заметные пылинки в солнечном луче салона (0.0 – 3.4 с)
    if t < 3.4:
        dust_fade = (1.0 - sm(2.3, 3.4, t)) * 0.42
        if dust_fade > 0.01:
            layer_d = np.zeros((H, W), np.float32)
            for i in range(N_DUST):
                px = int((DUST_X0[i] + DUST_VX[i] * t) % W)
                py = int((DUST_Y0[i] + DUST_VY[i] * t) % H)
                twinkle = 0.5 + 0.5 * np.sin(2.5 * t + DUST_PH[i])
                cv2.circle(layer_d, (px, py), max(1, int(DUST_RAD[i])), float(twinkle * dust_fade), -1, cv2.LINE_AA)
            layer_d = cv2.GaussianBlur(layer_d, (0, 0), 1.4)
            frame[..., 2] += layer_d * 210
            frame[..., 1] += layer_d * 185
            frame[..., 0] += layer_d * 135

    # Мелкое живое 35mm-зерно
    noise = cv2.resize(
        np.random.default_rng(100 + frame_idx % 9).uniform(-1.9, 1.9, (480, 270)).astype(np.float32),
        (W, H), interpolation=cv2.INTER_LINEAR
    )
    frame += noise[..., None]

    # Единственная кино-строка в начале (0.15 – 2.55 с) — без плашек, как субтитр в фильме
    if t < 2.60:
        a_sub = sm(0.15, 0.55, t) * (1.0 - sm(2.10, 2.55, t))
        if a_sub > 0.005:
            # Деликатное затемнение самой нижней трети только под текстом
            g_bot = np.clip((gy - 1200.0) / 520.0, 0.0, 1.0) ** 1.3 * 0.52 * a_sub
            frame *= (1.0 - g_bot[..., None])
            sub_tile = render_text_tile('when the last passenger finally leaves.',
                                        F_SERIF_IT, 54, 1, (246, 243, 236), shadow=True)
            frame = overlay_tile(frame, sub_tile, W / 2, 1495, a_sub * 0.95)

    return np.clip(frame, 0, 255).astype(np.uint8)


# ------------------------------------------------------------------ СБОРКА
def main():
    os.makedirs('work', exist_ok=True)
    if not os.path.exists(AUDIO):
        subprocess.run([sys.executable, 'make_audio.py'], check=True)
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    raw = 'work/video_silent.mp4'
    cmd = [ff, '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'bgr24',
           '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-', '-an', '-c:v', 'libx264',
           '-preset', 'medium', '-crf', '16', '-profile:v', 'high', '-pix_fmt', 'yuv420p',
           '-movflags', '+faststart', raw]
    enc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    n = int(round(DUR * FPS))
    for i in range(n):
        enc.stdin.write(render_frame(i / FPS, i).tobytes())
        if i % 100 == 0:
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
    # Обложка: чистый портретный кадр лица (t=3.00s) без лишних надписей
    subprocess.run([ff, '-y', '-loglevel', 'error', '-ss', '3.00', '-i', OUT,
                    '-frames:v', '1', 'cover.png'], check=True)
    os.remove(raw)
    try:
        os.rmdir('work')
    except OSError:
        pass
    print(f'готово: {OUT}  {DUR:.2f}s  {n} кадров  {W}x{H}')
    print(f'       {OUT_SILENT} (86 BPM, без звука — под «the feeling» и тренды TikTok)')
    print('       cover.png')


if __name__ == '__main__':
    main()
