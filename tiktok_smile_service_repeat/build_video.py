"""Сборка финального TikTok-ролика 9:16 для BARH — «SMILE SERVICE REPEAT» (46 × 130 см).

Сценарий (114 BPM, 14.74 с, без уродливых сверхкрупных кропов и без пустых полей):
  0.00 – 2.11 с  Пролёт самолёта в закатных облаках («WHAT A 12-HOUR FLIGHT ACTUALLY FEELS LIKE»)
                 + бортовой сигнал «DING-DONG» -> пауза перед дропом
  2.11 – 4.21 с  Дроп! Полная ширина холста (верх): окно самолёта, EXIT->, лицо, шампанское
  4.21 – 6.32 с  Переключение в бит: полная ширина холста (низ): тележка SMILE SERVICE REPEAT, подпись
  6.32 – 9.47 с  Полный показ картины 46×130 см в тёмном лофте под софитом
  9.47 – 12.63 с Полный показ картины 46×130 см в светлой минималистичной галерее
 12.63 – 14.74 с Финал: крупный фирменный рукописный логотип BARH белым на чистом чёрном фоне
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
BPM = 114.0
BEAT = 60.0 / BPM             # 0.526316 s
BAR = 4 * BEAT                # 2.105263 s
DUR = 7 * BAR                 # 14.736842 s

ART_PATH = 'artwork.jpg'
LOGO_PATH = 'barh_logo_white.png'
PLANE_PATH = 'work/flying_plane.png'
LOFT_PATH = 'work/interior_loft.png'
GALLERY_PATH = 'work/interior_gallery.png'
AUDIO_PATH = 'audio/BARH_sky_114bpm.wav'
OUT_MP4 = 'SMILE_SERVICE_REPEAT_BARH.mp4'
OUT_BOARD = 'storyboard.jpg'
OUT_COVER = 'cover.png'

F_OSWALD = 'fonts/Oswald-Variable.ttf'
F_MONO = 'fonts/IBMPlexMono-Bold.ttf'

SRC = cv2.imread(ART_PATH)
if SRC is None:
    raise SystemExit(f'нет файла {ART_PATH}')
SH, SW = SRC.shape[:2]

PLANE = cv2.imread(PLANE_PATH)
if PLANE is None:
    raise SystemExit(f'нет файла {PLANE_PATH}')
PLANE = cv2.resize(PLANE, (W, H), interpolation=cv2.INTER_LANCZOS4).astype(np.float32)

LOGO = cv2.imread(LOGO_PATH, cv2.IMREAD_UNCHANGED)
if LOGO is None:
    raise SystemExit(f'нет файла {LOGO_PATH}')
LW = 720
LH = int(LOGO.shape[0] * LW / LOGO.shape[1])
LOGO_RS = cv2.resize(LOGO, (LW, LH), interpolation=cv2.INTER_AREA).astype(np.float32)
LOGO_ALPHA = LOGO_RS[..., 3:4] / 255.0

gy, gx = np.mgrid[0:H, 0:W].astype(np.float32)
VIG = (1.0 - 0.16 * (((gx - W / 2) / (W / 2)) ** 2 + ((gy - H / 2) / (H / 2)) ** 2) * 0.50)[..., None].astype(np.float32)


def build_mounted_room(room_path, crop_box, target_h_1080, center_xy_1080,
                       shadow_dx, shadow_dy, light_mode, scale_hi=1.5):
    """Рендерит интерьер в 1.5x разрешении с картиной в точных пропорциях 46x130 см."""
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
    target_h_1080=720,
    center_xy_1080=(540, 815),
    shadow_dx=4,
    shadow_dy=18,
    light_mode='loft',
)
ROOM_GALLERY = build_mounted_room(
    GALLERY_PATH,
    crop_box=(20, 50, 740, 1330),
    target_h_1080=700,
    center_xy_1080=(570, 825),
    shadow_dx=15,
    shadow_dy=13,
    light_mode='gallery',
)


def sm(a, b, t):
    q = np.clip((t - a) / max(b - a, 1e-6), 0.0, 1.0)
    return float(q * q * (3.0 - 2.0 * q))


def beat_bounce(dt, amp=0.025, tau=0.12):
    return 1.0 + amp * np.exp(-(dt / tau) ** 2)


def zoom_room(room_hi, zoom, cy_shift=0.0):
    rh, rw = room_hi.shape[:2]
    s = (W / rw) * zoom
    cx = rw / 2.0
    cy = rh / 2.0 + cy_shift * (rh / H)
    M = np.array([[s, 0.0, W / 2.0 - s * cx],
                  [0.0, s, H / 2.0 - s * cy]], np.float32)
    return cv2.warpAffine(room_hi, M, (W, H), flags=cv2.INTER_LANCZOS4,
                          borderMode=cv2.BORDER_REPLICATE)


def full_width_art(cy, zoom=1.0):
    """Широкий благородный кадр на всю ширину холста (1384 -> 1080, без уродливого макро)."""
    s = (W / SW) * zoom
    vh = H / s
    cy_clamped = float(np.clip(cy, vh / 2.0, SH - vh / 2.0))
    M = np.array([[s, 0.0, W / 2.0 - s * (SW / 2.0)],
                  [0.0, s, H / 2.0 - s * cy_clamped]], np.float32)
    fr = cv2.warpAffine(SRC, M, (W, H), flags=cv2.INTER_AREA if s < 1.0 else cv2.INTER_LANCZOS4,
                        borderMode=cv2.BORDER_REPLICATE).astype(np.float32)
    fr[..., 2] *= 1.015
    fr = (fr - 118.0) * 1.04 + 118.0
    fr *= VIG
    return fr


@lru_cache(maxsize=32)
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
            d.text((x + 3, pad_y + 3), ch, font=f, fill=(0, 0, 0, 210))
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


def render_barh_outro(dt):
    frame = np.zeros((H, W, 3), np.float32)
    q = np.clip((dt - 0.03) / 0.40, 0.0, 1.0)
    q = q * q * (3.0 - 2.0 * q)
    cols = np.arange(LW, dtype=np.float32)[None, :, None]
    edge = LW * q * 1.18 - 0.18 * LW
    wipe = np.clip((edge - cols) / (0.18 * LW), 0.0, 1.0)
    fade = np.clip(dt / 0.08, 0.0, 1.0)
    x0 = (W - LW) // 2
    y0 = (H - LH) // 2 - 30
    frame[y0:y0 + LH, x0:x0 + LW] = 255.0 * LOGO_ALPHA * wipe * fade
    return frame


def render_frame(t):
    # ---------------- BAR 0 (0.00 - 2.11 с): ПРОЛЁТ САМОЛЁТА В ЗАКАТНОМ НЕБЕ
    if t < BAR:
        if t >= 2.05:
            return np.zeros((H, W, 3), np.uint8)
        p = t / BAR
        # Лёгкий кинематографический пролёт/трекинг за самолётом
        z = 1.02 + 0.13 * p
        cx = W * (0.48 + 0.04 * p)
        cy = H * (0.52 - 0.04 * p)
        M = np.array([[z, 0.0, W / 2.0 - z * cx],
                      [0.0, z, H / 2.0 - z * cy]], np.float32)
        fr = cv2.warpAffine(PLANE, M, (W, H), flags=cv2.INTER_LANCZOS4,
                            borderMode=cv2.BORDER_REPLICATE)
        # Мягкий всплеск золотого света на моменте сигнала «DING-DONG» (1.54-2.05)
        if t >= 1.54:
            flash = np.exp(-((t - 1.56) / 0.12) ** 2) * 18.0
            fr = np.clip(fr + flash, 0, 255)
        t1 = text_tile('WHAT A 12-HOUR FLIGHT', F_OSWALD, 58, 3, (248, 246, 242), shadow=True, weight=600)
        t2 = text_tile('ACTUALLY FEELS LIKE', F_OSWALD, 58, 3, (248, 246, 242), shadow=True, weight=600)
        a_txt = sm(0.08, 0.30, t) * (1.0 - sm(1.88, 2.04, t))
        fr = overlay_tile(fr, t1, W / 2, 275, a_txt)
        fr = overlay_tile(fr, t2, W / 2, 355, a_txt)
        return np.clip(fr, 0, 255).astype(np.uint8)

    # ---------------- BAR 1 (2.11 - 4.21 с): ДРОП — ПОЛНАЯ ШИРИНА ВЕРХНЕЙ ЧАСТИ КАРТИНЫ
    if t < 2 * BAR:
        dt = t - BAR
        p = dt / BAR
        bounce = beat_bounce(dt, 0.032, 0.13)
        fr = full_width_art(cy=1235.0 + 185.0 * p, zoom=bounce)
        if dt < 0.06:
            k = 1.0 - dt / 0.06
            fr = fr * (1.0 - 0.25 * k) + 255.0 * 0.25 * k
        return np.clip(fr, 0, 255).astype(np.uint8)

    # ---------------- BAR 2 (4.21 - 6.32 с): ПЕРЕКЛЮЧЕНИЕ В БИТ — ПОЛНАЯ ШИРИНА НИЖНЕЙ ЧАСТИ КАРТИНЫ
    if t < 3 * BAR:
        dt = t - 2 * BAR
        p = dt / BAR
        bounce = beat_bounce(dt, 0.028, 0.12)
        fr = full_width_art(cy=2490.0 + 185.0 * p, zoom=bounce)
        if dt < 0.05:
            fr *= (1.0 - 0.15 * (1.0 - dt / 0.05))
        return np.clip(fr, 0, 255).astype(np.uint8)

    # ---------------- BAR 3..4.5 (6.32 - 9.47 с): ПОЛНЫЙ ПОКАЗ 46×130 СМ В ТЁМНОМ ЛОФТЕ
    if t < 4.5 * BAR:
        dt = t - 3 * BAR
        p = dt / (1.5 * BAR)
        bounce = beat_bounce(dt % BEAT, 0.012, 0.10)
        fr = zoom_room(ROOM_LOFT, (1.00 + 0.065 * p) * bounce, cy_shift=-10.0 * p)
        if dt < 0.06:
            fr += 24.0 * (1.0 - dt / 0.06)
        lbl = text_tile('“SMILE SERVICE REPEAT”  ·  46 × 130 CM', F_MONO, 24, 5, (236, 232, 224), shadow=True)
        fr = overlay_tile(fr, lbl, W / 2, 1255, 0.94 * sm(0.15, 0.45, dt))
        return np.clip(fr, 0, 255).astype(np.uint8)

    # ---------------- BAR 4.5..6 (9.47 - 12.63 с): ПОЛНЫЙ ПОКАЗ 46×130 СМ В СВЕТЛОЙ ГАЛЕРЕЕ
    if t < 6 * BAR:
        dt = t - 4.5 * BAR
        p = dt / (1.5 * BAR)
        bounce = beat_bounce(dt % BEAT, 0.012, 0.10)
        fr = zoom_room(ROOM_GALLERY, (1.00 + 0.065 * p) * bounce, cy_shift=-8.0 * p)
        if dt < 0.05:
            fr += 20.0 * (1.0 - dt / 0.05)
        lbl = text_tile('BARH  ·  “SMILE SERVICE REPEAT”  ·  46 × 130 CM', F_MONO, 22, 4, (45, 42, 38), shadow=False)
        fr = overlay_tile(fr, lbl, W / 2, 1265, 0.90 * sm(0.15, 0.45, dt))
        return np.clip(fr, 0, 255).astype(np.uint8)

    # ---------------- BAR 6 (12.63 - 14.74 с): КРУПНЫЙ БЕЛЫЙ ЛОГОТИП BARH НА ЧЁРНОМ
    return np.clip(render_barh_outro(t - 6 * BAR), 0, 255).astype(np.uint8)


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

    # Обложка (вид картины в лофте) + раскадровка для проверки
    cv2.imwrite(OUT_COVER, render_frame(7.50))
    cap = cv2.VideoCapture(OUT_MP4)
    stamps = [
        (0.70, '00.70 FLYING PLANE'),
        (1.65, '01.65 CABIN CHIME'),
        (2.40, '02.40 FULL WIDTH TOP'),
        (3.80, '03.80 UPPER PAINTING'),
        (5.00, '05.00 LOWER PAINTING'),
        (7.50, '07.50 LOFT 46x130'),
        (10.80, '10.80 GALLERY 46x130'),
        (13.90, '13.90 BARH LOGO'),
    ]
    tiles = []
    for ts, lbl in stamps:
        cap.set(cv2.CAP_PROP_POS_FRAMES, min(n - 1, int(round(ts * FPS))))
        ok, fr = cap.read()
        if ok:
            th = cv2.resize(fr, (360, 640), interpolation=cv2.INTER_AREA)
            cv2.rectangle(th, (0, 0), (360, 36), (18, 18, 22), -1)
            cv2.putText(th, lbl, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (235, 235, 235), 2, cv2.LINE_AA)
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
