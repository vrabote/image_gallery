"""Сборка двух неторопливых, кристально резких TikTok-роликов (9:16) для BARH:

1) Сценарий Б — «Контраст: Витрина vs Усталость» (76 BPM, 22.11 с):
   SMILE_SERVICE_REPEAT_BARH_contrast.mp4 (+ _silent.mp4)
   - 0.00–3.16 с  Спокойный портрет + деликатный титр «what passengers never see.»
   - 3.16–6.32 с  Табличка EXIT -> и тёплый свет иллюминатора
   - 6.32–9.47 с  Золотое крылышко, красный платок и рука на ведёрке со льдом
   - 9.47–12.63 с Тележка с надписью SMILE / SERVICE / REPEAT
   - 12.63–18.95 с Полный показ картины 46×130 см в тёмном лофте (без полей!)
   - 18.95–22.11 с Фирменный рукописный логотип BARH белым на чёрном

2) Сценарий В — «Чистый ArtTok / Галерея» (72 BPM, 20.00 с):
   SMILE_SERVICE_REPEAT_BARH_arttok.mp4 (+ _silent.mp4)
   - 0.00–3.33 с  Чистый портрет с первого кадра (ноль слов)
   - 3.33–6.67 с  Тележка SMILE / SERVICE / REPEAT и рука на льду
   - 6.67–10.00 с Два спокойных макро-этюда живых мазков (глаза -> крылышко)
   - 10.00–16.67 с Полный показ картины 46×130 см в светлой галерее (без полей!)
   - 16.67–20.00 с Фирменный рукописный логотип BARH белым на чёрном

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

W, H = 1080, 1920
FPS = 30

ART_PATH = 'artwork.jpg'
LOGO_PATH = 'barh_logo_white.png'
LOFT_PATH = 'work/interior_loft.png'
GALLERY_PATH = 'work/interior_gallery.png'
F_SERIF_IT = 'fonts/InstrumentSerif-Italic.ttf'
F_MONO = 'fonts/IBMPlexMono-Regular.ttf'

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
VIG = (1.0 - 0.24 * (((gx - W / 2) / (W / 2)) ** 2 + ((gy - H / 2) / (H / 2)) ** 2) * 0.55)[..., None].astype(np.float32)


def build_mounted_room(room_path, crop_box, target_h_1080, center_xy_1080,
                       shadow_dx, shadow_dy, light_mode, scale_hi=1.5):
    """Рендерит интерьер в повышенном разрешении с точно масштабированной картиной 46x130 см."""
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
    if light_mode == 'loft':
        spot = 0.89 + 0.13 * np.exp(-((nx - 0.5) * 1.4) ** 2 - ((ny - 0.28) * 1.1) ** 2)
        canvas *= spot[..., None]
        canvas[..., 2] *= 1.02
        canvas[..., 0] *= 0.96
        side_col = np.array([28, 30, 34], np.float32)
    else:
        side = 0.94 + 0.07 * (1.0 - nx) - 0.03 * ny
        canvas *= side[..., None]
        canvas[..., 2] *= 1.02
        canvas[..., 0] *= 0.97
        side_col = np.array([156, 158, 160], np.float32)

    sh_mask = np.zeros((rh, rw), np.float32)
    sh_mask[py:py + ph, px:px + pw] = 1.0
    sdx = int(round(shadow_dx * scale_hi))
    sdy = int(round(shadow_dy * scale_hi))
    contact = cv2.GaussianBlur(np.roll(sh_mask, (int(4 * scale_hi), int(2 * scale_hi)), axis=(0, 1)), (0, 0), 5.0 * scale_hi) * 0.48
    cast = cv2.GaussianBlur(np.roll(sh_mask, (sdy, sdx), axis=(0, 1)), (0, 0), 22.0 * scale_hi) * 0.38
    deep = cv2.GaussianBlur(np.roll(sh_mask, (sdy + int(10 * scale_hi), sdx + int(5 * scale_hi)), axis=(0, 1)), (0, 0), 42.0 * scale_hi) * 0.20
    total_sh = np.clip(contact + cast * 0.72 + deep * 0.5, 0.0, 0.74)[..., None]
    out = rm * (1.0 - total_sh)

    ew = int(round(3 * scale_hi))
    if shadow_dx >= 0:
        out[py + ew:py + ph + ew, px + pw:px + pw + ew] = side_col * 0.84
        out[py + ph:py + ph + ew, px:px + pw + ew] = side_col * 0.68
    else:
        out[py + ew:py + ph + ew, px - ew:px] = side_col * 0.84
        out[py + ph:py + ph + ew, px - ew:px + pw] = side_col * 0.68

    out[py:py + ph, px:px + pw] = canvas
    out[py:py + 2, px:px + pw] = np.clip(out[py:py + 2, px:px + pw] * 1.10, 0, 255)
    return np.clip(out, 0, 255).astype(np.float32)


print('Подготовка интерьеров 46x130 см...')
ROOM_LOFT = build_mounted_room(
    LOFT_PATH,
    crop_box=(48, 120, 720, 1315),
    target_h_1080=720,            # 130 см -> 720 px, 46 см -> 255 px
    center_xy_1080=(540, 815),
    shadow_dx=4,
    shadow_dy=18,
    light_mode='loft',
)
ROOM_GALLERY = build_mounted_room(
    GALLERY_PATH,
    crop_box=(20, 50, 740, 1330),
    target_h_1080=700,            # 130 см -> 700 px, 46 см -> 248 px
    center_xy_1080=(570, 825),
    shadow_dx=15,
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


def crop_art(vh, cx, cy, sharp_boost=0.22):
    """Резкий, не смазанный кадр с холста с деликатной детализацией мазков."""
    s = H / vh
    M = np.array([[s, 0.0, W / 2.0 - s * cx],
                  [0.0, s, H / 2.0 - s * cy]], np.float32)
    fr = cv2.warpAffine(SRC, M, (W, H), flags=cv2.INTER_LANCZOS4,
                        borderMode=cv2.BORDER_REPLICATE).astype(np.float32)
    if sharp_boost > 0:
        blur = cv2.GaussianBlur(fr, (0, 0), 1.4)
        fr = fr + sharp_boost * (fr - blur)
    fr[..., 2] *= 1.015
    fr = (fr - 118.0) * 1.05 + 118.0
    fr *= VIG
    return fr


@lru_cache(maxsize=32)
def text_tile(text, font_path, size, tracking, color, shadow=True):
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
            d.text((x + 2, 16), ch, font=f, fill=(0, 0, 0, 195))
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
    x0, y0 = int(cx - w / 2), int(cy - h / 2)
    x1, y1 = max(0, x0), max(0, y0)
    x2, y2 = min(W, x0 + w), min(H, y0 + h)
    if x2 <= x1 or y2 <= y1:
        return frame
    sub = tile[y1 - y0:y2 - y0, x1 - x0:x2 - x0].astype(np.float32)
    a = (sub[..., 3:4] / 255.0) * alpha
    frame[y1:y2, x1:x2] = frame[y1:y2, x1:x2] * (1.0 - a) + sub[..., :3][..., ::-1] * a
    return frame


def render_barh_outro(dt):
    frame = np.zeros((H, W, 3), np.float32)
    q = np.clip((dt - 0.05) / 0.85, 0.0, 1.0)
    q = q * q * (3.0 - 2.0 * q)
    cols = np.arange(LW, dtype=np.float32)[None, :, None]
    edge = LW * q * 1.18 - 0.18 * LW
    wipe = np.clip((edge - cols) / (0.18 * LW), 0.0, 1.0)
    fade = np.clip(dt / 0.16, 0.0, 1.0)
    x0 = (W - LW) // 2
    y0 = (H - LH) // 2 - 30
    frame[y0:y0 + LH, x0:x0 + LW] = 255.0 * LOGO_ALPHA * wipe * fade
    return frame


def blend_shots(t, shots):
    """Мягкий кросс-диссолв 0.45 с между спокойными планами (без дёрганых склеек)."""
    xf = 0.45
    for idx, (t0, t1, fn) in enumerate(shots):
        if t < t1 or idx == len(shots) - 1:
            fr = fn(t)
            if idx + 1 < len(shots) and t > t1 - xf:
                q = sm(t1 - xf, t1, t)
                fr2 = shots[idx + 1][2](t)
                fr = fr * (1.0 - q) + fr2 * q
            return fr
    return shots[-1][2](t)


# ================================================================== СЦЕНАРИЙ Б: КОНТРАСТ
def make_contrast_renderer():
    BPM = 76
    BAR = 4 * (60.0 / BPM)                # 3.15789 s
    DUR = 7 * BAR                         # 22.10526 s

    def s_face(t):
        p = np.clip(t / BAR, 0.0, 1.0)
        fr = crop_art(1160.0 - 38.0 * p, 695.0, 625.0)
        a_sub = sm(0.20, 0.70, t) * (1.0 - sm(BAR - 0.50, BAR - 0.10, t))
        if a_sub > 0.005:
            g_top = np.clip((430.0 - gy) / 430.0, 0.0, 1.0) ** 1.2 * 0.56 * a_sub
            fr *= (1.0 - g_top[..., None])
            tile = text_tile('what passengers never see.', F_SERIF_IT, 56, 1, (248, 245, 238), shadow=True)
            fr = overlay_tile(fr, tile, W / 2, 230, a_sub * 0.98)
        return fr

    def s_exit(t):
        p = np.clip((t - BAR) / BAR, 0.0, 1.0)
        # Держим cy = vh/2, чтобы красная табличка EXIT -> целиком оставалась в правом верхнем углу
        vh = 940.0 - 30.0 * p
        cx = 1118.0 - 8.0 * p
        cy = vh / 2.0 + 4.0
        return crop_art(vh, cx, cy)

    def s_service(t):
        p = np.clip((t - 2 * BAR) / BAR, 0.0, 1.0)
        return crop_art(1330.0 - 45.0 * p, 795.0 + 18.0 * p, 1560.0 + 35.0 * p)

    def s_trolley(t):
        p = np.clip((t - 3 * BAR) / BAR, 0.0, 1.0)
        return crop_art(1185.0 - 40.0 * p, 1046.0, 2475.0)

    def s_loft(t):
        p = np.clip((t - 4 * BAR) / (2 * BAR), 0.0, 1.0)
        fr = zoom_room(ROOM_LOFT, 1.00 + 0.065 * p, cy_shift=-12.0 * p)
        a_tit = sm(4 * BAR + 0.65, 4 * BAR + 1.25, t) * (1.0 - sm(6 * BAR - 0.55, 6 * BAR - 0.15, t))
        if a_tit > 0.005:
            tile = text_tile('“SMILE SERVICE REPEAT”  ·  46 × 130 cm', F_MONO, 23, 5, (230, 226, 218), shadow=True)
            fr = overlay_tile(fr, tile, W / 2, 1255, a_tit * 0.90)
        return fr

    def s_outro(t):
        return render_barh_outro(max(0.0, t - 6 * BAR))

    shots = [
        (0.0, BAR, s_face),
        (BAR, 2 * BAR, s_exit),
        (2 * BAR, 3 * BAR, s_service),
        (3 * BAR, 4 * BAR, s_trolley),
        (4 * BAR, 6 * BAR, s_loft),
        (6 * BAR, DUR, s_outro),
    ]

    def render(t):
        return np.clip(blend_shots(t, shots), 0, 255).astype(np.uint8)

    return DUR, BAR, render


# ================================================================== СЦЕНАРИЙ В: ЧИСТЫЙ ARTTOK
def make_arttok_renderer():
    BPM = 72
    BAR = 4 * (60.0 / BPM)                # 3.33333 s
    DUR = 6 * BAR                         # 20.0000 s

    def s_face(t):
        p = np.clip(t / BAR, 0.0, 1.0)
        return crop_art(1150.0 - 38.0 * p, 695.0, 625.0)

    def s_trolley(t):
        p = np.clip((t - BAR) / BAR, 0.0, 1.0)
        return crop_art(1200.0 - 42.0 * p, 1044.0, 2445.0 + 30.0 * p)

    def s_macro_eyes(t):
        p = np.clip((t - 2 * BAR) / (0.5 * BAR), 0.0, 1.0)
        return crop_art(570.0 - 25.0 * p, 695.0, 590.0, sharp_boost=0.26)

    def s_macro_wings(t):
        p = np.clip((t - 2.5 * BAR) / (0.5 * BAR), 0.0, 1.0)
        return crop_art(530.0 - 25.0 * p, 845.0 + 12.0 * p, 1455.0, sharp_boost=0.26)

    def s_gallery(t):
        p = np.clip((t - 3 * BAR) / (2 * BAR), 0.0, 1.0)
        fr = zoom_room(ROOM_GALLERY, 1.00 + 0.065 * p, cy_shift=-10.0 * p)
        a_tit = sm(3 * BAR + 0.65, 3 * BAR + 1.25, t) * (1.0 - sm(5 * BAR - 0.55, 5 * BAR - 0.15, t))
        if a_tit > 0.005:
            tile = text_tile('BARH  ·  “SMILE SERVICE REPEAT”  ·  46 × 130 cm', F_MONO, 22, 4, (52, 48, 44), shadow=False)
            fr = overlay_tile(fr, tile, W / 2, 1265, a_tit * 0.88)
        return fr

    def s_outro(t):
        return render_barh_outro(max(0.0, t - 5 * BAR))

    shots = [
        (0.0, BAR, s_face),
        (BAR, 2 * BAR, s_trolley),
        (2 * BAR, 2.5 * BAR, s_macro_eyes),
        (2.5 * BAR, 3 * BAR, s_macro_wings),
        (3 * BAR, 5 * BAR, s_gallery),
        (5 * BAR, DUR, s_outro),
    ]

    def render(t):
        return np.clip(blend_shots(t, shots), 0, 255).astype(np.uint8)

    return DUR, BAR, render


def encode_cut(name, dur, audio_path, out_mp4, out_silent, render_fn, bar, board_name, board_labels):
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    raw = f'work/{name}_raw.mp4'
    cmd = [ff, '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'bgr24',
           '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-', '-an', '-c:v', 'libx264',
           '-preset', 'medium', '-crf', '16', '-profile:v', 'high', '-pix_fmt', 'yuv420p',
           '-movflags', '+faststart', raw]
    enc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    n = int(round(dur * FPS))
    print(f'Рендер {name}: {n} кадров ({dur:.2f} с)...', flush=True)
    for i in range(n):
        enc.stdin.write(render_fn(i / FPS).tobytes())
        if i % 150 == 0:
            print(f'  {name}: {i}/{n}', flush=True)
    enc.stdin.close()
    if enc.wait() != 0:
        raise SystemExit(f'ошибка кодирования {name}')

    subprocess.run([ff, '-y', '-loglevel', 'error', '-i', raw, '-i', audio_path,
                    '-map', '0:v', '-map', '1:a', '-af', 'loudnorm=I=-14:TP=-1.0:LRA=11',
                    '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-ar', '48000',
                    '-movflags', '+faststart', '-shortest', out_mp4], check=True)
    subprocess.run([ff, '-y', '-loglevel', 'error', '-i', out_mp4, '-c', 'copy', '-an',
                    '-movflags', '+faststart', out_silent], check=True)
    os.remove(raw)

    # Контакт-лист сториборда (8 ключевых кадров)
    cap = cv2.VideoCapture(out_mp4)
    tiles = []
    for ts, lbl in board_labels:
        cap.set(cv2.CAP_PROP_POS_FRAMES, min(n - 1, int(round(ts * FPS))))
        ok, fr = cap.read()
        if ok:
            th = cv2.resize(fr, (360, 640), interpolation=cv2.INTER_AREA)
            cv2.rectangle(th, (0, 0), (360, 36), (18, 18, 22), -1)
            cv2.putText(th, lbl, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.56, (235, 235, 235), 2, cv2.LINE_AA)
            tiles.append(th)
    cap.release()
    gap = np.full((640, 12, 3), 28, np.uint8)
    r1 = np.hstack([tiles[0], gap, tiles[1], gap, tiles[2], gap, tiles[3]])
    r2 = np.hstack([tiles[4], gap, tiles[5], gap, tiles[6], gap, tiles[7]])
    vgap = np.full((12, r1.shape[1], 3), 28, np.uint8)
    cv2.imwrite(board_name, np.vstack([r1, vgap, r2]), [cv2.IMWRITE_JPEG_QUALITY, 93])
    print(f'готово: {out_mp4}, {out_silent}, {board_name}', flush=True)


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else 'all'
    os.makedirs('work', exist_ok=True)
    if not (os.path.exists('audio/BARH_contrast_76bpm.wav') and os.path.exists('audio/BARH_arttok_72bpm.wav')):
        subprocess.run([sys.executable, 'make_audio.py'], check=True)

    if only in ('all', 'contrast'):
        dur_b, bar_b, fn_b = make_contrast_renderer()
        encode_cut(
            'contrast', dur_b, 'audio/BARH_contrast_76bpm.wav',
            'SMILE_SERVICE_REPEAT_BARH_contrast.mp4',
            'SMILE_SERVICE_REPEAT_BARH_contrast_silent.mp4',
            fn_b, bar_b, 'storyboard_contrast.jpg',
            [
                (1.2, '01.20 HOOK FACE'),
                (4.5, '04.50 EXIT ->'),
                (7.8, '07.80 WINGS & ICE'),
                (11.0, '11.00 TROLLEY'),
                (14.5, '14.50 LOFT 46x130'),
                (17.5, '17.50 LOFT TITLE'),
                (19.5, '19.50 BARH WRITE'),
                (21.0, '21.00 BARH HOLD'),
            ],
        )

    if only in ('all', 'arttok'):
        dur_c, bar_c, fn_c = make_arttok_renderer()
        encode_cut(
            'arttok', dur_c, 'audio/BARH_arttok_72bpm.wav',
            'SMILE_SERVICE_REPEAT_BARH_arttok.mp4',
            'SMILE_SERVICE_REPEAT_BARH_arttok_silent.mp4',
            fn_c, bar_c, 'storyboard_arttok.jpg',
            [
                (1.2, '01.20 CLEAN FACE'),
                (4.8, '04.80 TROLLEY'),
                (7.4, '07.40 MACRO EYES'),
                (9.1, '09.10 MACRO WINGS'),
                (11.8, '11.80 GALLERY 46x130'),
                (14.8, '14.80 GALLERY TITLE'),
                (17.2, '17.20 BARH WRITE'),
                (18.9, '18.90 BARH HOLD'),
            ],
        )

    ff = imageio_ffmpeg.get_ffmpeg_exe()
    subprocess.run([ff, '-y', '-loglevel', 'error', '-ss', '1.20', '-i',
                    'SMILE_SERVICE_REPEAT_BARH_arttok.mp4', '-frames:v', '1', 'cover.png'], check=True)


if __name__ == '__main__':
    main()
