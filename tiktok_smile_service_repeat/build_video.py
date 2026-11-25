"""Сборка финального TikTok-ролика 9:16 для BARH — «SMILE SERVICE REPEAT» (46 × 130 см).

Музыка: космический синти-звук в духе Space 1980-х (108 BPM, 22.22 с).
Структура:
  0.00 – 4.44 с   Ночной пентхаус («01 · TWILIGHT PENTHOUSE») + двуязычный хук:
                  «Stop. Deep breath. Relax and look. / Остановись. Глубокий вдох. Расслабься и посмотри.»
  4.44 – 11.11 с  Кадр между ночью и днём: построчно проявляющийся текст на двух языках (EN + RU)
  11.11 – 15.56 с Дневная современная резиденция («02 · DAYLIGHT RESIDENCE») с живым солнечным лучом
  15.56 – 20.00 с Плавный проезд по всей ширине картины сверху донизу (1384 -> 1080, без рывков и сильного зума)
  20.00 – 22.22 с Финал: крупный фирменный рукописный белый логотип BARH на чистом чёрном фоне
"""
import os
import subprocess
from functools import lru_cache

import cv2
import numpy as np
import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1920
FPS = 30
BPM = 59.5
BEAT = 60.0 / BPM             # 1.008403 s
BAR = 4 * BEAT                # 4.033613 s
DUR = 8.5 * BAR               # 34.285714 s

ART_PATH = 'artwork.jpg'
LOGO_PATH = 'barh_logo_white.png'
PENTHOUSE_PATH = 'work/interior_penthouse.png'
MODERN_GAL_PATH = 'work/interior_modern_gallery.png'
AUDIO_PATH = 'audio/BARH_secret_dreams_60bpm.wav'
OUT_MP4 = 'SMILE_SERVICE_REPEAT_BARH.mp4'
OUT_BOARD = 'storyboard.jpg'
OUT_COVER = 'cover.png'

F_OSWALD = 'fonts/Oswald-Variable.ttf'

SRC = cv2.imread(ART_PATH)
if SRC is None:
    raise SystemExit(f'нет файла {ART_PATH}')
SH, SW = SRC.shape[:2]

LOGO = cv2.imread(LOGO_PATH, cv2.IMREAD_UNCHANGED)
if LOGO is None:
    raise SystemExit(f'нет файла {LOGO_PATH}')
LW = 720
LH = int(LOGO.shape[0] * LW / LOGO.shape[1])
LOGO_RS = cv2.resize(LOGO, (LW, LH), interpolation=cv2.INTER_AREA).astype(np.float32)
LOGO_ALPHA = LOGO_RS[..., 3:4] / 255.0

gy, gx = np.mgrid[0:H, 0:W].astype(np.float32)
VIG = (1.0 - 0.16 * (((gx - W / 2) / (W / 2)) ** 2 + ((gy - H / 2) / (H / 2)) ** 2) * 0.50)[..., None].astype(np.float32)

# Атмосферная приглушённая подложка для текстового кадра (едва уловимый силуэт картины в космическом сумраке)
_bg_crop = cv2.resize(SRC[300:2600, :], (W, H), interpolation=cv2.INTER_AREA).astype(np.float32)
_bg_blur = cv2.GaussianBlur(_bg_crop, (0, 0), 42.0)
TEXT_BG = np.clip(_bg_blur * 0.14 + np.array([12.0, 9.0, 7.0], np.float32), 0, 255) * VIG

_rng = np.random.default_rng(1980)
MOTES = [
    (
        _rng.uniform(260, 820),
        _rng.uniform(380, 1200),
        _rng.uniform(1.0, 2.0),
        _rng.uniform(-7, 7),
        _rng.uniform(-12, -3),
        _rng.uniform(0.08, 0.18),
        _rng.uniform(0, 6.28),
    )
    for _ in range(22)
]


def build_mounted_room(room_path, crop_box, target_h_1080, center_xy_1080,
                       shadow_dx, shadow_dy, light_mode, scale_hi=1.5):
    rw = int(W * scale_hi)
    rh = int(H * scale_hi)
    rm = cv2.imread(room_path)
    if rm is None:
        raise SystemExit(f'нет файла {room_path}')
    x0, y0, x1, y1 = crop_box
    rm = cv2.resize(rm[y0:y1, x0:x1], (rw, rh), interpolation=cv2.INTER_LANCZOS4).astype(np.float32)

    ph = int(round(target_h_1080 * scale_hi))
    pw = int(round(ph * 46.0 / 130.0))
    px = int(round(center_xy_1080[0] * scale_hi - pw / 2.0))
    py = int(round(center_xy_1080[1] * scale_hi - ph / 2.0))

    canvas = cv2.resize(SRC, (pw, ph), interpolation=cv2.INTER_AREA).astype(np.float32)
    yy, xx = np.mgrid[0:ph, 0:pw].astype(np.float32)
    ny = yy / max(1, ph - 1)
    nx = xx / max(1, pw - 1)

    if light_mode == 'penthouse':
        spot = 0.87 + 0.16 * np.exp(-((nx - 0.50) * 1.35) ** 2 - ((ny - 0.22) * 1.15) ** 2)
        canvas *= spot[..., None]
        canvas[..., 2] *= 1.025
        canvas[..., 0] *= 0.96 + 0.04 * (1.0 - nx)
        side_col = np.array([34, 34, 36], np.float32)
    else:
        sun = 0.92 + 0.11 * nx * np.exp(-((ny - 0.25) * 1.4) ** 2)
        canvas *= sun[..., None]
        canvas[..., 2] *= 1.03
        canvas[..., 0] *= 0.96
        side_col = np.array([154, 152, 148], np.float32)

    sh_mask = np.zeros((rh, rw), np.float32)
    sh_mask[py:py + ph, px:px + pw] = 1.0
    sdx = int(round(shadow_dx * scale_hi))
    sdy = int(round(shadow_dy * scale_hi))
    contact = cv2.GaussianBlur(np.roll(sh_mask, (int(4 * scale_hi), int(2 * scale_hi)), axis=(0, 1)), (0, 0), 5.0 * scale_hi) * 0.48
    cast = cv2.GaussianBlur(np.roll(sh_mask, (sdy, sdx), axis=(0, 1)), (0, 0), 22.0 * scale_hi) * 0.36
    deep = cv2.GaussianBlur(np.roll(sh_mask, (sdy + int(10 * scale_hi), sdx + int(5 * scale_hi)), axis=(0, 1)), (0, 0), 42.0 * scale_hi) * 0.20
    total_sh = np.clip(contact + cast * 0.72 + deep * 0.5, 0.0, 0.72)[..., None]
    out = rm * (1.0 - total_sh)

    ew = int(round(3 * scale_hi))
    if shadow_dx >= 0:
        out[py + ew:py + ph + ew, px + pw:px + pw + ew] = side_col * 0.84
        out[py + ph:py + ph + ew, px:px + pw + ew] = side_col * 0.68
    else:
        out[py + ew:py + ph + ew, px - ew:px] = side_col * 0.84
        out[py + ph:py + ph + ew, px - ew:px + pw] = side_col * 0.68

    out[py:py + ph, px:px + pw] = canvas
    out[py:py + 2, px:px + pw] = np.clip(out[py:py + 2, px:px + pw] * 1.12, 0, 255)
    return np.clip(out, 0, 255).astype(np.float32)


print('Подготовка современных интерьеров 46x130 см...')
ROOM_PENTHOUSE = build_mounted_room(
    PENTHOUSE_PATH,
    crop_box=(36, 48, 740, 1298),
    target_h_1080=620,
    center_xy_1080=(543, 860),
    shadow_dx=5,
    shadow_dy=15,
    light_mode='penthouse',
)
ROOM_MODERN_GAL = build_mounted_room(
    MODERN_GAL_PATH,
    crop_box=(24, 52, 744, 1332),
    target_h_1080=635,
    center_xy_1080=(539, 855),
    shadow_dx=-15,
    shadow_dy=13,
    light_mode='gallery',
)


def sm(a, b, t):
    q = np.clip((t - a) / max(b - a, 1e-6), 0.0, 1.0)
    return float(q * q * (3.0 - 2.0 * q))


def zoom_room(room_hi, zoom, cy_shift=0.0):
    rh, rw = room_hi.shape[:2]
    s = (W / rw) * zoom
    cx = rw / 2.0
    cy = rh / 2.0 + cy_shift * (rh / H)
    M = np.array([[s, 0.0, W / 2.0 - s * cx],
                  [0.0, s, H / 2.0 - s * cy]], np.float32)
    return cv2.warpAffine(room_hi, M, (W, H), flags=cv2.INTER_LANCZOS4,
                          borderMode=cv2.BORDER_REPLICATE)


def add_dust_motes(fr, t, warmth=(215, 232, 248)):
    ov = np.zeros((H, W, 3), np.float32)
    for x0, y0, r, vx, vy, a, ph in MOTES:
        x = int(round(x0 + vx * t + 6.0 * np.sin(0.6 * t + ph)))
        y = int(round(y0 + vy * t))
        if 20 < x < W - 20 and 20 < y < H - 20:
            pulse = 0.65 + 0.35 * np.sin(1.2 * t + ph)
            cv2.circle(ov, (x, y), max(1, int(round(r))), (warmth[0] * a * pulse, warmth[1] * a * pulse, warmth[2] * a * pulse), -1, cv2.LINE_AA)
    ov = cv2.GaussianBlur(ov, (0, 0), 1.6)
    return np.clip(fr + ov, 0, 255)


def full_width_art(cy):
    s = W / SW
    vh = H / s
    cy_clamped = float(np.clip(cy, vh / 2.0, SH - vh / 2.0))
    M = np.array([[s, 0.0, 0.0],
                  [0.0, s, H / 2.0 - s * cy_clamped]], np.float32)
    fr = cv2.warpAffine(SRC, M, (W, H), flags=cv2.INTER_AREA,
                        borderMode=cv2.BORDER_REPLICATE).astype(np.float32)
    fr[..., 2] *= 1.012
    fr = (fr - 118.0) * 1.03 + 118.0
    fr *= VIG
    return fr


@lru_cache(maxsize=64)
def text_tile(text, font_path, size, tracking, color, shadow=True, weight=0):
    f = ImageFont.truetype(font_path, size)
    if weight:
        f.set_variation_by_axes([weight])
    probe = ImageDraw.Draw(Image.new('RGBA', (4, 4)))
    widths = [probe.textlength(ch, font=f) for ch in text]
    asc, desc = f.getmetrics()
    pad_x, pad_y = 28, 16
    tw = int(sum(widths) + tracking * max(0, len(text) - 1) + 2 * pad_x)
    th = int(asc + desc + 2 * pad_y)
    im = Image.new('RGBA', (tw, th), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if shadow:
        x = float(pad_x)
        for ch, cw in zip(text, widths):
            d.text((x + 2, pad_y + 2), ch, font=f, fill=(0, 0, 0, 200))
            x += cw + tracking
    x = float(pad_x)
    for ch, cw in zip(text, widths):
        d.text((x, pad_y), ch, font=f, fill=color + (255,))
        x += cw + tracking
    return np.array(im)


def overlay_tile(frame, tile, cx, cy, alpha=1.0):
    if alpha <= 0.002:
        return frame
    h, w = tile.shape[:2]
    x0, y0 = int(cx - w / 2), int(cy - h / 2)
    x1, y1 = max(0, x0), max(0, y0)
    x2, y2 = min(W, x0 + w), min(H, y0 + h)
    if x2 <= x1 or y2 <= y1:
        return frame
    sub = tile[y1 - y0:y2 - y0, x1 - x0:x2 - x0].astype(np.float32)
    a = (sub[..., 3:4] / 255.0) * alpha
    frame[y1:y2, x1:x2] = frame[y1:y2, x1:x2] * (1.0 - a) + sub[..., :3][..., ::-1] * a
    return frame


# Таймлайн (59.5 BPM «Secret Dreams», 34.29 с — спокойное дыхание на старте и чёткое выделение финального блока текста)
T_NIGHT_END = 12.10      # 0.10–8.55 с (по ~2.1 с на фразу под дыхание) -> 8.55–12.10 с чистая пауза на картине
T_TEXT_END = 20.60       # Двуязычный кадр между ночью и днём (8.50 с, спокойный шаг 1.2 с)
T_DAY_END = 25.60        # Дневная резиденция с живым солнечным лучом (5.00 с)
T_PAN_END = 31.80        # Плавный проезд по всей ширине картины (6.20 с)
                         # 31.80 – 34.29 с — Белый логотип BARH на #000000

OPEN_STEPS = [
    (0.10, 2.15, 'Stop.', 'Остановись.', 136, 78),
    (2.20, 4.35, 'Deep breath.', 'Глубокий вдох.', 120, 74),
    (4.40, 6.45, 'Relax.', 'Расслабься.', 136, 78),
    (6.50, 8.55, 'And look.', 'И посмотри.', 126, 78),
]

STANZAS = [
    (T_NIGHT_END + 0.15, 250, 312, 'Smile? Always.', 'Улыбаться? Всегда.'),
    (T_NIGHT_END + 1.35, 435, 497, 'Service? Of course.', 'Обслуживание? Конечно.'),
    (T_NIGHT_END + 2.55, 620, 682, 'Repeat? Until we land.', 'Повторять? Пока не приземлимся.'),
    (T_NIGHT_END + 3.75, 805, 867, 'Tired? Not in the job description.', 'Устал? Этого нет в инструкции.'),
    (T_NIGHT_END + 5.20, 1235, 1300, 'This is my new work.', 'Это моя новая работа.'),
    (T_NIGHT_END + 6.20, 1465, 1528, '“Smile Service Repeat” 46×130 cm, oil on canvas', '«Улыбнись. Помоги. Повтори.», 46×130 см, холст, масло.'),
]


@lru_cache(maxsize=2)
def plaque_overlay():
    """Тонкая музейная плашка с тёплой золотистой рамкой для выделения блока 'This is my new work.'."""
    im = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((36, 1140, W - 36, 1625), radius=28,
                        fill=(16, 15, 13, 172), outline=(244, 212, 148, 135), width=2)
    return np.array(im)


def scene_night(t):
    p = np.clip(t / (T_NIGHT_END + 0.5), 0.0, 1.0)
    fr = zoom_room(ROOM_PENTHOUSE, 1.00 + 0.075 * p, cy_shift=-10.0 * p)
    fr = add_dust_motes(fr, t, warmth=(200, 224, 248))
    if t < 0.35:
        fr *= sm(0.0, 0.35, t)

    # Медленные синхронные вдоху крупные слова поперёк экрана (~2.1 с каждое)
    for t0, t1, txt_en, txt_ru, sz_en, sz_ru in OPEN_STEPS:
        if t < t0 or t > t1:
            continue
        a = sm(t0, t0 + 0.48, t) * (1.0 - sm(t1 - 0.50, t1, t))
        if a > 0.004:
            band = np.exp(-((gy - 880.0) / 195.0) ** 2) * 0.44 * a
            fr *= (1.0 - band[..., None])
            en_t = text_tile(txt_en, F_OSWALD, sz_en, 2, (252, 250, 244), shadow=True, weight=500)
            ru_t = text_tile(txt_ru, F_OSWALD, sz_ru, 2, (232, 228, 220), shadow=True, weight=350)
            fr = overlay_tile(fr, en_t, W / 2, 825, a * 0.99)
            fr = overlay_tile(fr, ru_t, W / 2, 955, a * 0.96)
    return fr


def scene_bilingual_text(t):
    # Показываем саму картину за текстом (бархатная тёмная вуаль + плавное движение вниз)
    p = np.clip((t - (T_NIGHT_END - 0.65)) / (T_TEXT_END - (T_NIGHT_END - 0.65)), 0.0, 1.0)
    q = 0.5 - 0.5 * np.cos(np.pi * p)
    vh = H * (SW / W)
    art_bg = full_width_art(vh / 2.0 + 240.0 + 400.0 * q)
    # Лёгкая кинематографичная мягкость фона + затемнение под текст для безупречной читаемости
    art_soft = cv2.GaussianBlur(art_bg, (0, 0), 3.0)
    vig = np.clip(0.32 + 0.24 * (1.0 - np.abs(gy - H * 0.45) / (H * 0.65)), 0.22, 0.52)[..., None]
    fr = art_soft * vig + TEXT_BG * 0.22
    fr = add_dust_motes(fr, t * 0.65, warmth=(210, 225, 245))
    a_all = 1.0 - sm(T_TEXT_END - 0.65, T_TEXT_END, t)

    # Мягкое появление выделенной нижней плашки «This is my new work.» (опущена ниже с большой паузой воздуха)
    a_plaque = sm(T_NIGHT_END + 4.95, T_NIGHT_END + 5.65, t) * a_all
    if a_plaque > 0.004:
        pl = plaque_overlay().astype(np.float32)
        pa = (pl[..., 3:4] / 255.0) * a_plaque
        fr = fr * (1.0 - pa) + pl[..., :3][..., ::-1] * pa

    for idx, (t_on, y_en, y_ru, txt_en, txt_ru) in enumerate(STANZAS):
        a = sm(t_on, t_on + 0.60, t) * a_all
        if a <= 0.004:
            continue
        if idx == 4:          # Выделенный акцент: «This is my new work. / Это моя новая работа.»
            sz_en, sz_ru = 64, 42
            col_en, col_ru = (250, 224, 168), (240, 216, 172)
            wt_en, wt_ru = 600, 400
        elif idx == 5:        # Название и размеры картины
            sz_en, sz_ru = 42, 33
            col_en, col_ru = (255, 252, 246), (226, 222, 214)
            wt_en, wt_ru = 500, 350
        else:                 # Верхние 4 вопроса поверх картины
            sz_en = 56 if idx == 3 else 60
            sz_ru = 38 if idx in (2, 3) else 40
            col_en, col_ru = (250, 248, 242), (212, 208, 200)
            wt_en, wt_ru = 500, 350

        t_e = text_tile(txt_en, F_OSWALD, sz_en, 2, col_en, shadow=True, weight=wt_en)
        t_r = text_tile(txt_ru, F_OSWALD, sz_ru, 2, col_ru, shadow=True, weight=wt_ru)
        dy = (1.0 - sm(t_on, t_on + 0.60, t)) * 10.0
        fr = overlay_tile(fr, t_e, W / 2, y_en + dy, a * 0.99)
        fr = overlay_tile(fr, t_r, W / 2, y_ru + dy, a * 0.96)
    return fr


def scene_day(t):
    p = np.clip((t - (T_TEXT_END - 0.60)) / (T_DAY_END - (T_TEXT_END - 0.60)), 0.0, 1.0)
    fr = zoom_room(ROOM_MODERN_GAL, 1.00 + 0.060 * p, cy_shift=-8.0 * p)

    beam_center = 0.34 + 0.14 * p
    diag = (gy / H) * 0.85 + (1.0 - gx / W) * 0.55
    beam = np.exp(-((diag - beam_center) / 0.16) ** 2) * (0.55 + 0.45 * np.sin(np.pi * p))
    beam_mask = np.clip((beam - 0.15) * 1.15, 0.0, 1.0)[..., None]
    fr = np.clip(fr + beam_mask * np.array([10.0, 16.0, 22.0], np.float32), 0, 255)
    fr = add_dust_motes(fr, t - T_TEXT_END + 2.0, warmth=(200, 230, 255))
    return fr


def scene_pan(t):
    p = np.clip((t - (T_DAY_END - 0.70)) / ((T_PAN_END + 0.40) - (T_DAY_END - 0.70)), 0.0, 1.0)
    q = 0.5 - 0.5 * np.cos(np.pi * p)
    vh = H * (SW / W)
    cy0 = vh / 2.0
    cy1 = SH - vh / 2.0
    return full_width_art(cy0 + (cy1 - cy0) * q)


def scene_barh(t):
    dt = max(0.0, t - T_PAN_END)
    frame = np.zeros((H, W, 3), np.float32)
    q = np.clip((dt - 0.05) / 0.85, 0.0, 1.0)
    q = q * q * (3.0 - 2.0 * q)
    cols = np.arange(LW, dtype=np.float32)[None, :, None]
    edge = LW * q * 1.18 - 0.18 * LW
    wipe = np.clip((edge - cols) / (0.18 * LW), 0.0, 1.0)
    fade = np.clip(dt / 0.25, 0.0, 1.0)
    x0 = (W - LW) // 2
    y0 = (H - LH) // 2 - 30
    frame[y0:y0 + LH, x0:x0 + LW] = 255.0 * LOGO_ALPHA * wipe * fade
    return frame


def render_frame(t):
    xf = 0.75
    if t < T_NIGHT_END:
        fr = scene_night(t)
        if t > T_NIGHT_END - xf:
            q = sm(T_NIGHT_END - xf, T_NIGHT_END, t)
            fr = fr * (1.0 - q) + scene_bilingual_text(t) * q
    elif t < T_TEXT_END:
        fr = scene_bilingual_text(t)
        if t > T_TEXT_END - xf:
            q = sm(T_TEXT_END - xf, T_TEXT_END, t)
            fr = fr * (1.0 - q) + scene_day(t) * q
    elif t < T_DAY_END:
        fr = scene_day(t)
        if t > T_DAY_END - xf:
            q = sm(T_DAY_END - xf, T_DAY_END, t)
            fr = fr * (1.0 - q) + scene_pan(t) * q
    elif t < T_PAN_END:
        fr = scene_pan(t)
        if t > T_PAN_END - 0.55:
            q = sm(T_PAN_END - 0.55, T_PAN_END, t)
            fr = fr * (1.0 - q) + scene_barh(t) * q
    else:
        fr = scene_barh(t)
    return np.clip(fr, 0, 255).astype(np.uint8)


def main():
    os.makedirs('work', exist_ok=True)
    if not os.path.exists(AUDIO_PATH):
        raise SystemExit(f'нет файла {AUDIO_PATH}')

    ff = imageio_ffmpeg.get_ffmpeg_exe()
    raw = 'work/final_raw.mp4'
    cmd = [ff, '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'bgr24',
           '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-', '-an', '-c:v', 'libx264',
           '-preset', 'medium', '-crf', '16', '-profile:v', 'high', '-pix_fmt', 'yuv420p',
           '-movflags', '+faststart', raw]
    enc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    n = int(round(DUR * FPS))
    print(f'Рендер {OUT_MP4}: {n} кадров ({DUR:.2f} с)...', flush=True)
    for i in range(n):
        enc.stdin.write(render_frame(i / FPS).tobytes())
        if i % 150 == 0:
            print(f'  {i}/{n}', flush=True)
    enc.stdin.close()
    if enc.wait() != 0:
        raise SystemExit('ошибка кодирования')

    subprocess.run([ff, '-y', '-loglevel', 'error', '-i', raw, '-i', AUDIO_PATH,
                    '-map', '0:v', '-map', '1:a', '-af', 'loudnorm=I=-14:TP=-1.0:LRA=11',
                    '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-ar', '48000',
                    '-movflags', '+faststart', '-shortest', OUT_MP4], check=True)
    os.remove(raw)

    cv2.imwrite(OUT_COVER, render_frame(10.20))
    cap = cv2.VideoCapture(OUT_MP4)
    stamps = [
        (1.10, '01.10 STOP / OSTANOVIS'),
        (3.25, '03.25 DEEP BREATH'),
        (7.50, '07.50 AND LOOK'),
        (10.30, '10.30 PAUSE ON PAINTING'),
        (19.60, '19.60 BILINGUAL CARD'),
        (23.10, '23.10 DAY RESIDENCE'),
        (28.80, '28.80 PAINTING GLIDE'),
        (33.20, '33.20 BARH LOGO'),
    ]
    tiles = []
    for ts, lbl in stamps:
        cap.set(cv2.CAP_PROP_POS_FRAMES, min(n - 1, int(round(ts * FPS))))
        ok, fr = cap.read()
        if ok:
            th = cv2.resize(fr, (360, 640), interpolation=cv2.INTER_AREA)
            cv2.rectangle(th, (0, 0), (360, 36), (18, 18, 22), -1)
            cv2.putText(th, lbl, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (235, 235, 235), 2, cv2.LINE_AA)
            tiles.append(th)
    cap.release()
    gap = np.full((640, 12, 3), 28, np.uint8)
    r1 = np.hstack([tiles[0], gap, tiles[1], gap, tiles[2], gap, tiles[3]])
    r2 = np.hstack([tiles[4], gap, tiles[5], gap, tiles[6], gap, tiles[7]])
    vgap = np.full((12, r1.shape[1], 3), 28, np.uint8)
    cv2.imwrite(OUT_BOARD, np.vstack([r1, vgap, r2]), [cv2.IMWRITE_JPEG_QUALITY, 93])
    print(f'готово: {OUT_MP4}, {OUT_BOARD}, {OUT_COVER}', flush=True)


if __name__ == '__main__':
    main()
