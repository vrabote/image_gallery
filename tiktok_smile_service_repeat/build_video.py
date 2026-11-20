"""Сборка финального TikTok-ролика 9:16 для BARH — «SMILE SERVICE REPEAT» (46 × 130 см).

Меланхоличный, ультрасовременный и эстетически выверенный монтаж (92 BPM, 15.65 с):
  - Старт сразу с картины 46×130 см в современном тёмном пентхаусе с панорамой мегаполиса («01 · TWILIGHT PENTHOUSE»)
  - Деликатный текстовый хук «the quiet after 10,000 smiles.» над полотном + живые пылинки в луче света
  - Единый плавный проезд по всей ширине картины сверху донизу (1384 -> 1080, без рывков и тесных кропов)
  - Показ в ультрасовременной светлой резиденции («02 · DAYLIGHT RESIDENCE») с живым движением солнечного луча
  - Финал: крупный фирменный рукописный белый логотип BARH на чистом чёрном фоне
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
BPM = 92.0
BEAT = 60.0 / BPM             # 0.652174 s
BAR = 4 * BEAT                # 2.608696 s
DUR = 6 * BAR                 # 15.652174 s

ART_PATH = 'artwork.jpg'
LOGO_PATH = 'barh_logo_white.png'
PENTHOUSE_PATH = 'work/interior_penthouse.png'
MODERN_GAL_PATH = 'work/interior_modern_gallery.png'
AUDIO_PATH = 'audio/BARH_melancholic_92bpm.wav'
OUT_MP4 = 'SMILE_SERVICE_REPEAT_BARH.mp4'
OUT_BOARD = 'storyboard.jpg'
OUT_COVER = 'cover.png'

F_SERIF_IT = 'fonts/InstrumentSerif-Italic.ttf'
F_MONO = 'fonts/IBMPlexMono-Bold.ttf'

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

# Детерминированные тончайшие пылинки света для глубины кинокамеры
_rng = np.random.default_rng(2026)
MOTES = [
    (
        _rng.uniform(260, 820),   # x0
        _rng.uniform(380, 1200),  # y0
        _rng.uniform(1.0, 2.0),   # radius (тончайшие)
        _rng.uniform(-7, 7),      # vx
        _rng.uniform(-12, -3),    # vy
        _rng.uniform(0.08, 0.18), # alpha (едва заметные)
        _rng.uniform(0, 6.28),    # phase
    )
    for _ in range(22)
]


def build_mounted_room(room_path, crop_box, target_h_1080, center_xy_1080,
                       shadow_dx, shadow_dy, light_mode, scale_hi=1.5):
    """Рендерит ультрасовременный интерьер в 1.5x с картиной в точных пропорциях 46x130 см."""
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
        # Тёплый верхний cove-свет + деликатный холодный рефлекс от панорамного окна слева
        spot = 0.87 + 0.16 * np.exp(-((nx - 0.50) * 1.35) ** 2 - ((ny - 0.22) * 1.15) ** 2)
        canvas *= spot[..., None]
        canvas[..., 2] *= 1.025
        canvas[..., 0] *= 0.96 + 0.04 * (1.0 - nx)
        side_col = np.array([34, 34, 36], np.float32)
    else:
        # Золотой дневной свет из окна справа и диагональный солнечный блик сверху
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
    target_h_1080=740,
    center_xy_1080=(543, 855),
    shadow_dx=5,
    shadow_dy=16,
    light_mode='penthouse',
)
ROOM_MODERN_GAL = build_mounted_room(
    MODERN_GAL_PATH,
    crop_box=(24, 52, 744, 1332),
    target_h_1080=736,
    center_xy_1080=(539, 825),
    shadow_dx=-16,
    shadow_dy=14,
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
    """Тончайшие плавающие пылинки в свете софита/окна (добавляет глубину кинокамеры)."""
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
    """Спокойный кадр на всю ширину холста (1384 -> 1080) без рывков и тесных кропов."""
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


@lru_cache(maxsize=32)
def text_tile(text, font_path, size, tracking, color, shadow=True):
    f = ImageFont.truetype(font_path, size)
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
            d.text((x + 2, pad_y + 2), ch, font=f, fill=(0, 0, 0, 195))
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


T_LOFT_END = 4.25
T_PAN_END = 10.45
T_GAL_END = 13.45


def scene_penthouse(t):
    p = np.clip(t / (T_LOFT_END + 0.5), 0.0, 1.0)
    fr = zoom_room(ROOM_PENTHOUSE, 1.00 + 0.070 * p, cy_shift=-10.0 * p)
    fr = add_dust_motes(fr, t, warmth=(200, 224, 248))

    # Мягкое появление из темноты в первые 0.28 с для бесшовного цикла TikTok
    if t < 0.28:
        fr *= sm(0.0, 0.28, t)

    # Верхний эмоциональный хук на ровной тёмной стене ниже яркой LED-подсветки
    a_hook = sm(0.18, 0.72, t) * (1.0 - sm(T_LOFT_END - 0.85, T_LOFT_END - 0.15, t))
    if a_hook > 0.005:
        eyebrow = text_tile('BARH  ·  “SMILE SERVICE REPEAT”  ·  46 × 130 CM', F_MONO, 19, 4, (208, 204, 196), shadow=True)
        hook = text_tile('the quiet after 10,000 smiles.', F_SERIF_IT, 54, 1, (246, 243, 236), shadow=True)
        fr = overlay_tile(fr, eyebrow, W / 2, 350, a_hook * 0.88)
        fr = overlay_tile(fr, hook, W / 2, 408, a_hook * 0.96)

    # Стильная подпись пространства 01 (для вовлечения и дебатов 01 vs 02 в комментариях)
    a_tag = sm(0.45, 1.05, t) * (1.0 - sm(T_LOFT_END - 0.85, T_LOFT_END - 0.15, t))
    if a_tag > 0.005:
        tag1 = text_tile('01  ·  TWILIGHT PENTHOUSE', F_MONO, 22, 5, (232, 228, 220), shadow=True)
        fr = overlay_tile(fr, tag1, W / 2, 1290, a_tag * 0.90)
    return fr


def scene_pan(t):
    p = np.clip((t - (T_LOFT_END - 0.70)) / ((T_PAN_END + 0.50) - (T_LOFT_END - 0.70)), 0.0, 1.0)
    q = 0.5 - 0.5 * np.cos(np.pi * p)
    vh = H * (SW / W)
    cy0 = vh / 2.0
    cy1 = SH - vh / 2.0
    return full_width_art(cy0 + (cy1 - cy0) * q)


def scene_modern_gallery(t):
    p = np.clip((t - (T_PAN_END - 0.60)) / (T_GAL_END - (T_PAN_END - 0.60)), 0.0, 1.0)
    fr = zoom_room(ROOM_MODERN_GAL, 1.00 + 0.055 * p, cy_shift=-8.0 * p)

    # Живой золотой солнечный луч, медленно скользящий по стене и картине
    beam_center = 0.34 + 0.14 * p
    diag = (gy / H) * 0.85 + (1.0 - gx / W) * 0.55
    beam = np.exp(-((diag - beam_center) / 0.16) ** 2) * (0.55 + 0.45 * np.sin(np.pi * p))
    beam_mask = np.clip((beam - 0.15) * 1.15, 0.0, 1.0)[..., None]
    fr = np.clip(fr + beam_mask * np.array([10.0, 16.0, 22.0], np.float32), 0, 255)
    fr = add_dust_motes(fr, t - T_PAN_END + 2.0, warmth=(200, 230, 255))

    a_tag = sm(T_PAN_END + 0.25, T_PAN_END + 0.80, t) * (1.0 - sm(T_GAL_END - 0.75, T_GAL_END - 0.15, t))
    if a_tag > 0.005:
        tag2 = text_tile('02  ·  DAYLIGHT RESIDENCE', F_MONO, 22, 5, (48, 45, 40), shadow=False)
        sub2 = text_tile('46 × 130 CM', F_MONO, 19, 4, (86, 80, 72), shadow=False)
        fr = overlay_tile(fr, tag2, W / 2, 1255, a_tag * 0.92)
        fr = overlay_tile(fr, sub2, W / 2, 1296, a_tag * 0.82)
    return fr


def scene_barh(t):
    dt = max(0.0, t - T_GAL_END)
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
    xf = 0.85
    if t < T_LOFT_END:
        fr = scene_penthouse(t)
        if t > T_LOFT_END - xf:
            q = sm(T_LOFT_END - xf, T_LOFT_END, t)
            fr = fr * (1.0 - q) + scene_pan(t) * q
    elif t < T_PAN_END:
        fr = scene_pan(t)
        if t > T_PAN_END - xf:
            q = sm(T_PAN_END - xf, T_PAN_END, t)
            fr = fr * (1.0 - q) + scene_modern_gallery(t) * q
    elif t < T_GAL_END:
        fr = scene_modern_gallery(t)
        if t > T_GAL_END - 0.55:
            q = sm(T_GAL_END - 0.55, T_GAL_END, t)
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

    cv2.imwrite(OUT_COVER, render_frame(1.80))
    cap = cv2.VideoCapture(OUT_MP4)
    stamps = [
        (1.20, '01.20 PENTHOUSE 01'),
        (3.10, '03.10 PENTHOUSE HOOK'),
        (5.00, '05.00 PAINTING TOP'),
        (6.60, '06.60 PAINTING MID'),
        (8.10, '08.10 SMILE SERVICE'),
        (9.50, '09.50 PAINTING LOWER'),
        (11.60, '11.60 RESIDENCE 02'),
        (14.80, '14.80 BARH LOGO'),
    ]
    tiles = []
    for ts, lbl in stamps:
        cap.set(cv2.CAP_PROP_POS_FRAMES, min(n - 1, int(round(ts * FPS))))
        ok, fr = cap.read()
        if ok:
            th = cv2.resize(fr, (360, 640), interpolation=cv2.INTER_AREA)
            cv2.rectangle(th, (0, 0), (360, 36), (18, 18, 22), -1)
            cv2.putText(th, lbl, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.50, (235, 235, 235), 2, cv2.LINE_AA)
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
