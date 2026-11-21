import math
import os
import subprocess
import wave
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from scipy.signal import resample_poly
import imageio_ffmpeg

SR = 44100
FPS = 24
W, H = 1280, 720
CROSSFADE = 0.60

SCENES = [
    {
        "img": "kir_bakh/cake_story/01_dropped_cake.png",
        "wav": "kir_bakh/audio/scene_01.wav",
        "pad_pre": 0.45,
        "pad_post": 0.85,
        "cam": ("zoom_in", (0.50, 0.50), (0.50, 0.57), 1.00, 1.13),
        "fx": "drop_cat",
    },
    {
        "img": "kir_bakh/cake_story/02_friend_kitchen_cookbook.png",
        "wav": "kir_bakh/audio/scene_02.wav",
        "pad_pre": 0.40,
        "pad_post": 0.80,
        "cam": ("pan", (0.37, 0.46), (0.57, 0.48), 1.11, 1.08),
        "fx": "cookbook_flour",
    },
    {
        "img": "kir_bakh/cake_story/03_kitchen_disaster.png",
        "wav": "kir_bakh/audio/scene_03.wav",
        "pad_pre": 0.40,
        "pad_post": 0.85,
        "cam": ("shake_zoom", (0.50, 0.48), (0.52, 0.50), 1.03, 1.12),
        "fx": "disaster",
    },
    {
        "img": "kir_bakh/cake_story/04_teamwork_breakthrough.png",
        "wav": "kir_bakh/audio/scene_04.wav",
        "pad_pre": 0.40,
        "pad_post": 0.80,
        "cam": ("zoom_in", (0.48, 0.50), (0.50, 0.52), 1.02, 1.11),
        "fx": "chopping",
    },
    {
        "img": "kir_bakh/cake_story/05_sister_18_waiting.png",
        "wav": "kir_bakh/audio/scene_05.wav",
        "pad_pre": 0.40,
        "pad_post": 0.85,
        "cam": ("pan", (0.60, 0.55), (0.38, 0.43), 1.11, 1.10),
        "fx": "clock",
    },
    {
        "img": "kir_bakh/cake_story/06_happy_finale.png",
        "wav": "kir_bakh/audio/scene_06.wav",
        "pad_pre": 0.40,
        "pad_post": 1.25,
        "cam": ("zoom_out_glow", (0.47, 0.48), (0.52, 0.48), 1.14, 1.02),
        "fx": "finale",
    },
]


def load_wav_44k(path: str) -> np.ndarray:
    with wave.open(path, "rb") as w:
        sr = w.getframerate()
        ch = w.getnchannels()
        raw = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        raw = raw.reshape(-1, ch).mean(axis=1)
    if sr != SR:
        # 24000 -> 44100: ratio 147 / 80
        g = math.gcd(SR, sr)
        raw = resample_poly(raw, SR // g, sr // g).astype(np.float32)
    # Trim ultra-quiet tail noise and normalize cleanly
    peak = np.max(np.abs(raw)) + 1e-6
    raw = raw * (0.85 / peak)
    return raw


def smoothstep(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


def make_paper_canvas(w=W, h=H, seed=42) -> Image.Image:
    rng = np.random.default_rng(seed)
    base = np.array([243, 236, 218], dtype=np.float32)
    noise = rng.normal(0, 3.2, (h, w, 1)).astype(np.float32)
    arr = np.clip(base + noise, 0, 255).astype(np.uint8)
    # Subtle warm edge vignette
    yy, xx = np.mgrid[0:h, 0:w]
    nx = (xx - w / 2) / (w / 2)
    ny = (yy - h / 2) / (h / 2)
    r2 = nx * nx + ny * ny
    vig = np.clip(1.0 - 0.11 * np.maximum(0, r2 - 0.45), 0.80, 1.0)[..., None]
    arr = np.clip(arr.astype(np.float32) * vig, 0, 255).astype(np.uint8)
    return Image.fromarray(arr, "RGB")


def make_title_card() -> Image.Image:
    canvas = make_paper_canvas(seed=7)
    # Put cropped/framed duo vignette on the upper-center
    duo = Image.open("kir_bakh/kir_and_petka_duo.png").convert("RGB")
    dw, dh = duo.size
    # Crop central characters
    crop = duo.crop((int(dw * 0.22), int(dh * 0.08), int(dw * 0.80), int(dh * 0.94)))
    crop.thumbnail((640, 390), Image.Resampling.LANCZOS)
    cw, ch = crop.size

    # Soft oval mask so it melts into the paper
    mask = Image.new("L", (cw, ch), 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle((12, 12, cw - 12, ch - 12), radius=36, fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(10))
    px = (W - cw) // 2
    py = 56
    canvas.paste(crop, (px, py), mask)

    # Subtle hand-drawn border frame
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((36, 28, W - 36, H - 28), radius=24, outline="#9C8462", width=3)
    draw.rounded_rectangle((44, 36, W - 44, H - 36), radius=20, outline="#C4B190", width=1)

    font_big = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf", 44)
    font_sub = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 30)

    title = "Приключения Кир Баха и Петьки"
    sub = "Серия 1: Торт на 18-летие"

    tb = draw.textbbox((0, 0), title, font=font_big)
    tw = tb[2] - tb[0]
    draw.text(((W - tw) // 2, py + ch + 26), title, font=font_big, fill="#382B1E")

    sb = draw.textbbox((0, 0), sub, font=font_sub)
    sw = sb[2] - sb[0]
    draw.text(((W - sw) // 2, py + ch + 92), sub, font=font_sub, fill="#735536")
    return canvas


def make_end_card() -> Image.Image:
    canvas = make_paper_canvas(seed=19)
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((36, 28, W - 36, H - 28), radius=24, outline="#9C8462", width=3)
    draw.rounded_rectangle((44, 36, W - 44, H - 36), radius=20, outline="#C4B190", width=1)

    font_big = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf", 52)
    font_sub = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 28)

    t1 = "Вот так и бывает!"
    t2 = "Домашний торт с душой всегда вкуснее магазинного."
    t3 = "Конец"

    for txt, fnt, y, col in [
        (t1, font_big, 215, "#382B1E"),
        (t2, font_sub, 310, "#5C4730"),
        (t3, font_big, 420, "#735536"),
    ]:
        bb = draw.textbbox((0, 0), txt, font=fnt)
        draw.text(((W - (bb[2] - bb[0])) // 2, y), txt, font=fnt, fill=col)
    return canvas


def render_ken_burns(img: Image.Image, p: float, cam_spec, t_sec: float) -> Image.Image:
    mode, c0, c1, z0, z1 = cam_spec
    e = smoothstep(p)
    z = z0 + (z1 - z0) * e
    cx = c0[0] + (c1[0] - c0[0]) * e
    cy = c0[1] + (c1[1] - c0[1]) * e

    iw, ih = img.size
    # Ensure crop fits W/H aspect ratio inside (iw, ih)
    base_aspect = W / H
    if iw / ih >= base_aspect:
        max_ch = ih
        max_cw = ih * base_aspect
    else:
        max_cw = iw
        max_ch = iw / base_aspect

    cw = max_cw / z
    ch = max_ch / z

    ox, oy = 0.0, 0.0
    if mode == "shake_zoom":
        # Playful comic shake in middle portion of scene 3
        shake_env = math.sin(math.pi * max(0.0, min(1.0, (p - 0.15) / 0.70)))
        ox = 7.0 * shake_env * math.sin(2 * math.pi * 5.2 * t_sec)
        oy = 5.0 * shake_env * math.cos(2 * math.pi * 6.7 * t_sec)

    x0 = cx * iw - cw / 2 + ox
    y0 = cy * ih - ch / 2 + oy
    x0 = max(0.0, min(iw - cw, x0))
    y0 = max(0.0, min(ih - ch, y0))

    frame = img.crop((x0, y0, x0 + cw, y0 + ch)).resize((W, H), Image.Resampling.BICUBIC)

    if mode == "zoom_out_glow":
        # Warm soft candle glow pulse in finale
        glow = 0.5 + 0.5 * math.sin(2 * math.pi * 2.1 * t_sec)
        arr = np.asarray(frame, dtype=np.float32)
        yy, xx = np.mgrid[0:H, 0:W]
        gx, gy = int(W * 0.46), int(H * 0.42)
        r2 = ((xx - gx) / (W * 0.18)) ** 2 + ((yy - gy) / (H * 0.18)) ** 2
        boost = (0.04 + 0.03 * glow) * np.exp(-r2)[..., None]
        arr[..., 0] = np.clip(arr[..., 0] + boost[..., 0] * 255 * 1.0, 0, 255)
        arr[..., 1] = np.clip(arr[..., 1] + boost[..., 0] * 255 * 0.85, 0, 255)
        arr[..., 2] = np.clip(arr[..., 2] + boost[..., 0] * 255 * 0.4, 0, 255)
        frame = Image.fromarray(arr.astype(np.uint8), "RGB")

    return frame


def synth_note(freq, dur, kind="flute", vol=0.2):
    n = int(SR * dur)
    t = np.arange(n, dtype=np.float32) / SR
    if kind == "flute":
        # Warm wooden recorder/flute with gentle vibrato + breath
        vib = 1.0 + 0.004 * np.sin(2 * math.pi * 5.2 * t)
        phase = 2 * math.pi * freq * np.cumsum(vib) / SR
        sig = 0.78 * np.sin(phase) + 0.18 * np.sin(2 * phase) + 0.05 * np.sin(3 * phase)
        env = np.minimum(1.0, t / 0.045) * np.exp(-t * 2.2) * np.minimum(1.0, (dur - t) / 0.04)
    elif kind == "pizz":
        sig = 0.8 * np.sin(2 * math.pi * freq * t) + 0.25 * np.sin(4 * math.pi * freq * t)
        env = np.minimum(1.0, t / 0.006) * np.exp(-t * 10.5)
    elif kind == "celesta":
        sig = 0.85 * np.sin(2 * math.pi * freq * t) + 0.15 * np.sin(6 * math.pi * freq * t)
        env = np.minimum(1.0, t / 0.008) * np.exp(-t * 5.2)
    else:
        sig = np.sin(2 * math.pi * freq * t)
        env = np.exp(-t * 5.0)
    return (sig * env * vol).astype(np.float32)


def add_at(buf: np.ndarray, clip: np.ndarray, t_sec: float):
    idx = int(t_sec * SR)
    if idx >= len(buf):
        return
    if idx < 0:
        clip = clip[-idx:]
        idx = 0
    end = min(len(buf), idx + len(clip))
    buf[idx:end] += clip[: end - idx]


def build_music_and_sfx(total_dur: float, segments: list) -> np.ndarray:
    music = np.zeros(int(total_dur * SR) + SR, dtype=np.float32)
    sfx = np.zeros_like(music)

    # Note helper (MIDI -> Hz)
    hz = lambda m: 440.0 * (2.0 ** ((m - 69) / 12.0))

    # Cheerful Soviet-cartoon acoustic score across segments
    # Intro (0 .. seg[0].start): playful flute motif in F major
    intro_notes = [(65, 0.0, 0.35), (69, 0.35, 0.35), (72, 0.70, 0.45), (77, 1.15, 0.65),
                   (76, 1.85, 0.35), (74, 2.20, 0.35), (72, 2.55, 0.70)]
    for m, t0, d in intro_notes:
        add_at(music, synth_note(hz(m), d, "flute", 0.22), t0 + 0.2)
        add_at(music, synth_note(hz(m - 12), d, "celesta", 0.14), t0 + 0.2)

    # Underlying gentle rhythmic pattern per segment
    rng = np.random.default_rng(11)
    for seg in segments:
        kind = seg["kind"]
        t0, t1 = seg["start"], seg["end"]
        if kind == "intro":
            continue
        elif kind == "outro":
            # Warm final birthday flute flourish & resolution
            fin = [(72, 0.1, 0.3), (74, 0.4, 0.3), (77, 0.7, 0.4), (81, 1.1, 0.5), (77, 1.65, 1.2)]
            for m, dt, d in fin:
                add_at(music, synth_note(hz(m), d, "flute", 0.24), t0 + dt)
            for m in [53, 60, 65, 69, 77]:
                add_at(music, synth_note(hz(m), 2.4, "celesta", 0.10), t0 + 0.7)
            continue

        fx = seg["fx"]
        # Choose chord progression and tempo based on scene mood
        if fx in ("drop_cat", "cookbook_flour"):
            step = 0.46
            chords = [[53, 60, 65, 69], [55, 62, 67, 70], [48, 55, 60, 64], [53, 60, 65, 69]]
            mel_pool = [65, 67, 69, 72, 74, 72, 69, 67]
        elif fx == "disaster":
            step = 0.28  # Brisk comical chase rhythm!
            chords = [[50, 57, 62, 65], [52, 59, 64, 67], [49, 55, 61, 64], [50, 57, 62, 65]]
            mel_pool = [74, 75, 74, 72, 70, 69, 72, 74]
        elif fx in ("chopping", "clock"):
            step = 0.52
            chords = [[53, 60, 65, 69], [50, 57, 62, 65], [58, 62, 65, 70], [48, 55, 60, 64]]
            mel_pool = [69, 72, 74, 72, 69, 65, 67, 69]
        else:  # finale
            step = 0.42
            chords = [[53, 60, 65, 69], [58, 65, 70, 74], [48, 55, 60, 64], [53, 60, 65, 69]]
            mel_pool = [72, 74, 77, 81, 79, 77, 74, 77]

        beat = 0
        t = t0
        while t < t1 - 0.25:
            ch = chords[(beat // 4) % len(chords)]
            bass_m = ch[0] - 12
            add_at(music, synth_note(hz(bass_m), step * 0.9, "pizz", 0.22), t)
            if beat % 2 == 1:
                add_at(music, synth_note(hz(ch[1]), step * 0.7, "celesta", 0.11), t)
                add_at(music, synth_note(hz(ch[2]), step * 0.7, "celesta", 0.10), t)
            if beat % 2 == 0:
                m_note = mel_pool[(beat // 2) % len(mel_pool)]
                add_at(music, synth_note(hz(m_note), step * 1.4, "flute", 0.11), t)
            t += step
            beat += 1

        # Scene-specific SFX
        if fx == "drop_cat":
            # Soft thud-splat ~ 10.2s into scene 1 (around "плюхнулся") + gentle cat meow
            splat_t = t0 + 10.0
            nt = int(0.32 * SR)
            tt = np.arange(nt, dtype=np.float32) / SR
            thud = np.sin(2 * math.pi * (140 * np.exp(-tt * 14)) * tt) * np.exp(-tt * 12) * 0.35
            noise = rng.normal(0, 0.12, nt).astype(np.float32) * np.exp(-tt * 16)
            add_at(sfx, thud + noise, splat_t)
            # Cute cat meow chime
            mt = np.arange(int(0.45 * SR), dtype=np.float32) / SR
            mf = 520 + 180 * np.sin(math.pi * mt / 0.45)
            meow = np.sin(2 * math.pi * np.cumsum(mf) / SR) * np.sin(math.pi * mt / 0.45) * 0.12
            add_at(sfx, meow.astype(np.float32), splat_t + 0.65)

        elif fx == "cookbook_flour":
            # Book page rustle + flour poof
            for dt in (4.5, 9.5):
                nt = int(0.28 * SR)
                tt = np.arange(nt, dtype=np.float32) / SR
                poof = rng.normal(0, 0.14, nt).astype(np.float32) * np.sin(math.pi * tt / 0.28)
                add_at(sfx, poof, t0 + dt)

        elif fx == "disaster":
            # Comic bubbles + metallic spoon boings
            for dt in (2.5, 4.2, 6.0, 8.8, 12.2):
                add_at(sfx, synth_note(hz(78), 0.18, "celesta", 0.16), t0 + dt)
                add_at(sfx, synth_note(hz(83), 0.15, "celesta", 0.14), t0 + dt + 0.09)
            # Boing spring
            nt = int(0.45 * SR)
            tt = np.arange(nt, dtype=np.float32) / SR
            bf = 220 + 90 * np.sin(2 * math.pi * 11 * tt)
            boing = np.sin(2 * math.pi * np.cumsum(bf) / SR) * np.exp(-tt * 6.5) * 0.16
            add_at(sfx, boing.astype(np.float32), t0 + 7.2)

        elif fx == "chopping":
            # Gentle wooden chopping taps
            for dt in (5.0, 5.28, 5.56, 5.84, 6.12):
                nt = int(0.06 * SR)
                tt = np.arange(nt, dtype=np.float32) / SR
                tap = np.sin(2 * math.pi * 420 * tt) * np.exp(-tt * 65) * 0.18
                add_at(sfx, tap.astype(np.float32), t0 + dt)

        elif fx == "clock":
            # Delicate antique clock tick-tock every 0.55s
            ct = t0 + 0.5
            k = 0
            while ct < t1 - 0.5:
                f_tick = 1350.0 if k % 2 == 0 else 1050.0
                nt = int(0.045 * SR)
                tt = np.arange(nt, dtype=np.float32) / SR
                tick = np.sin(2 * math.pi * f_tick * tt) * np.exp(-tt * 95) * 0.14
                add_at(sfx, tick.astype(np.float32), ct)
                ct += 0.55
                k += 1

        elif fx == "finale":
            # Happy flute fanfare right around Kir's flute mention!
            fanfare = [(72, 0.0, 0.18), (77, 0.18, 0.18), (81, 0.36, 0.18), (84, 0.55, 0.55)]
            for m, dt, d in fanfare:
                add_at(sfx, synth_note(hz(m), d, "flute", 0.24), t0 + 8.8 + dt)
            add_at(sfx, synth_note(hz(84), 0.7, "celesta", 0.18), t0 + 0.4)

    return music, sfx


def main():
    os.makedirs("kir_bakh/out", exist_ok=True)
    title_img = make_title_card()
    end_img = make_end_card()

    # Build timeline segments
    segments = []
    t_cur = 0.0

    # Intro card
    intro_dur = 3.2
    segments.append({"kind": "intro", "img": title_img, "start": t_cur, "end": t_cur + intro_dur})
    t_cur += intro_dur - CROSSFADE

    voice_tracks = []
    loaded_imgs = []
    for i, sc in enumerate(SCENES):
        v = load_wav_44k(sc["wav"])
        vdur = len(v) / SR
        dur = sc["pad_pre"] + vdur + sc["pad_post"]
        im = Image.open(sc["img"]).convert("RGB")
        loaded_imgs.append(im)
        segments.append({
            "kind": "scene",
            "idx": i,
            "img": im,
            "cam": sc["cam"],
            "fx": sc["fx"],
            "start": t_cur,
            "end": t_cur + dur,
            "voice": v,
            "voice_start": t_cur + sc["pad_pre"],
        })
        t_cur += dur - CROSSFADE

    outro_dur = 3.2
    segments.append({"kind": "outro", "img": end_img, "start": t_cur, "end": t_cur + outro_dur})
    total_dur = t_cur + outro_dur

    total_samples = int(total_dur * SR) + SR
    voice_bus = np.zeros(total_samples, dtype=np.float32)
    for seg in segments:
        if seg["kind"] == "scene":
            add_at(voice_bus, seg["voice"], seg["voice_start"])

    music_bus, sfx_bus = build_music_and_sfx(total_dur, segments)

    # Smooth sidechain ducking envelope from voice_bus
    win = int(0.18 * SR)
    abs_v = np.abs(voice_bus)
    env = np.convolve(abs_v, np.ones(win, dtype=np.float32) / win, mode="same")
    # Also smooth forward/back slightly
    speech_active = np.clip(env * 14.0, 0.0, 1.0)
    duck = 1.0 - 0.65 * speech_active  # drops music to 35% during speech

    mix = voice_bus * 0.95 + music_bus * 0.42 * duck + sfx_bus * 0.55
    # Fade in & fade out audio
    fi = int(0.35 * SR)
    fo = int(1.0 * SR)
    mix[:fi] *= np.linspace(0.0, 1.0, fi, dtype=np.float32)
    end_idx = int(total_dur * SR)
    mix[end_idx - fo : end_idx] *= np.linspace(1.0, 0.0, fo, dtype=np.float32)
    mix = mix[:end_idx]
    mix = np.tanh(mix * 1.05) * 0.92

    audio_path = "kir_bakh/out/soundtrack.wav"
    with wave.open(audio_path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((mix * 32767.0).astype(np.int16).tobytes())

    # Render frames directly into ffmpeg stdin
    out_mp4 = "kir_bakh/priklyucheniya_kir_bakha_tort.mp4"
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [
        ffmpeg_exe, "-y",
        "-f", "rawvideo", "-vcodec", "rawvideo",
        "-s", f"{W}x{H}", "-pix_fmt", "rgb24", "-r", str(FPS),
        "-i", "-",
        "-i", audio_path,
        "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest", "-movflags", "+faststart",
        out_mp4,
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)

    n_frames = int(total_dur * FPS)
    paper_fade_bg = make_paper_canvas(seed=99)

    def render_seg_frame(seg, t):
        p = (t - seg["start"]) / (seg["end"] - seg["start"])
        if seg["kind"] in ("intro", "outro"):
            return seg["img"]
        return render_ken_burns(seg["img"], p, seg["cam"], t - seg["start"])

    for f_idx in range(n_frames):
        t = f_idx / FPS
        active = [s for s in segments if s["start"] <= t <= s["end"]]
        if not active:
            frame = paper_fade_bg
        elif len(active) == 1:
            frame = render_seg_frame(active[0], t)
        else:
            s_prev, s_next = active[0], active[1]
            alpha = smoothstep((t - s_next["start"]) / CROSSFADE)
            f1 = render_seg_frame(s_prev, t)
            f2 = render_seg_frame(s_next, t)
            frame = Image.blend(f1, f2, alpha)

        # Gentle fade in at very start and fade out at very end
        if t < 0.6:
            frame = Image.blend(paper_fade_bg, frame, smoothstep(t / 0.6))
        elif t > total_dur - 0.8:
            frame = Image.blend(frame, paper_fade_bg, smoothstep((t - (total_dur - 0.8)) / 0.8))

        proc.stdin.write(frame.tobytes())

    proc.stdin.close()
    err = proc.stderr.read().decode("utf-8", errors="ignore")
    rc = proc.wait()
    if rc != 0:
        raise RuntimeError(f"ffmpeg failed ({rc}): {err[-1000:]}")
    print(f"Built {out_mp4} ({total_dur:.2f}s, {n_frames} frames)")


if __name__ == "__main__":
    main()
