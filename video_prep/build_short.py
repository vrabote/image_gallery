"""Reproducible 24.3-second vertical short. Run: .venv/bin/python video_prep/build_short.py
Original artwork and sticker pixels are preserved; generated photographic intro assets
are composited with a camera pull-back, not generated video. No narration.
"""
from pathlib import Path
import subprocess
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.io import wavfile
from scipy.signal import resample_poly, butter, sosfilt
import imageio_ffmpeg

ROOT = Path(__file__).resolve().parent
W, H, FPS = 1080, 1920, 60
DURATION = 24.3
RETURN_TO_WALL = 15.8
WALL_HOLD = 4.0
IRIS_DURATION = .8
OUTRO_START = RETURN_TO_WALL + WALL_HOLD + IRIS_DURATION
# Bar 7 downbeat: first lead note plus full rhythm. 108 -> 120 BPM
# makes the plan change at 3 s land exactly six beats after the opening.
MUSIC_IN = 6 * 4 * 60 / 108
SECOND_STATEMENT = 13.7
OUT = ROOT / 'short_leave_me_alone.mp4'
WORK = ROOT / 'short_work'
WORK.mkdir(exist_ok=True)
FF = imageio_ffmpeg.get_ffmpeg_exe()
FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
SERIF = '/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf'
LANDINGS = [3.6, 5.6, 7.6, 9.6]
QUESTION_LEAD = .45
CAPTIONS = [
    ('Хрупкая?', 'Да!', 'Fragile?', 'YES!'),
    ('Осторожно?', 'Да!', 'Handle with care?', 'YES!'),
    ('Не бросать?', 'Да!', 'Don’t give up?', 'YES!'),
    ('Не трогать?', 'Именно!', 'Don’t touch?', 'Exactly!'),
]


def read(path):
    return np.array(Image.open(path).convert('RGB'))

def resize(im, size):
    return cv2.resize(im, size, interpolation=cv2.INTER_AREA)

def text(im, words, y, size=42, color=(244, 236, 223), font=FONT):
    d = ImageDraw.Draw(im)
    d.text((W//2, y), words, font=ImageFont.truetype(font, size), fill=color, anchor='mt')

def punch_text(im, lines, age, center_y):
    """First visible on the impact frame; huge type settles in seven frames."""
    if age < -1e-6:
        return im
    layer=Image.new('RGBA',(W,H),(0,0,0,0))
    for words,y,size,color in lines:
        text(layer,words,y,size,color)
    q=float(np.clip(age/.24,0,1))
    scale=1+3.2*(1-q)**3
    mat=cv2.getRotationMatrix2D((W/2,center_y),0,scale)
    pixels=cv2.warpAffine(np.array(layer),mat,(W,H),flags=cv2.INTER_LINEAR)
    return Image.alpha_composite(im.convert('RGBA'),Image.fromarray(pixels)).convert('RGB')


def question_answer(im, caption, age):
    """The question flies in first; the answer is instantly full-size on contact."""
    rq,ra,eq,ea=caption
    for question,answer,y,size,color in [
        (rq,ra,1430,70,(244,236,223)),
        (eq,ea,1545,58,(216,186,146)),
    ]:
        regular=ImageFont.truetype(FONT,size)
        bold=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',size)
        d=ImageDraw.Draw(im)
        qw=d.textlength(question,font=regular)
        aw=d.textlength(answer,font=bold)
        gap=size*.34
        x=(W-qw-gap-aw)/2
        layer=Image.new('RGBA',(W,H),(0,0,0,0))
        ImageDraw.Draw(layer).text((x,y),question,font=regular,fill=color,anchor='lt')
        q=float(np.clip((age+QUESTION_LEAD)/.24,0,1))
        scale=1+3.2*(1-q)**3
        mat=cv2.getRotationMatrix2D((x+qw/2,y+size/2),0,scale)
        pixels=cv2.warpAffine(np.array(layer),mat,(W,H),flags=cv2.INTER_LINEAR)
        im=Image.alpha_composite(im.convert('RGBA'),Image.fromarray(pixels)).convert('RGB')
        if age >= -1e-6:
            # No scale, fade or travel: the complete answer appears on this frame.
            ImageDraw.Draw(im).text((x+qw+gap,y),answer,font=bold,fill=color,anchor='lt')
    return im


def make_heavy_press(sr):
    """Dry close-up tape slap: low palm body, crack and short paper tail."""
    rng=np.random.default_rng(271)
    t=np.arange(round(.34*sr))/sr
    noise=rng.standard_normal(len(t))
    crack=sosfilt(butter(3,[900,8500],btype='bandpass',fs=sr,output='sos'),noise)
    paper=sosfilt(butter(2,[1700,6200],btype='bandpass',fs=sr,output='sos'),rng.standard_normal(len(t)))
    phase=2*np.pi*np.cumsum(66+95*np.exp(-t/.012))/sr
    body=np.sin(phase)*np.exp(-t/.061)
    punch=(body*.95+crack*np.exp(-t/.009)*.85+paper*np.exp(-t/.042)*.3)
    punch*=np.minimum(1,t/.0007)*np.clip((.34-t)/.025,0,1)
    punch=np.tanh(punch*1.45)
    punch*=.92/np.max(np.abs(punch))
    return np.repeat(punch[:,None],2,axis=1).astype(np.float32)


base = read(ROOT / '00_clean_base.jpg')
# Original sticker positions refer to the original 2804 x 3493 extraction canvas.
full = []
for name, (x,y) in zip(['1_fragile', '2_handle', '3_notdrop', '4_donottouch'],
                       [(962,1557), (640,2128), (318,2638), (1604,2715)]):
    layer = np.array(Image.open(ROOT / 'layers' / (name+'.png')).convert('RGBA'))
    canvas = np.zeros((3493,2804,4), np.uint8)
    hh,ww = layer.shape[:2]
    canvas[y:y+hh,x:x+ww] = layer
    full.append(canvas)

# Clean gallery shot. Actual painting is pasted, not reinterpreted by an image model.
room = resize(read(ROOT/'short_assets/interior.jpg'), (W,H))
pw,ph,px,py = 506,630,287,490
shadow = np.zeros((H,W),np.uint8)
shadow[py+12:py+ph+12,px+12:px+pw+12]=75
shadow=cv2.GaussianBlur(shadow,(0,0),15)
room=(room.astype(float)*(1-shadow[...,None]/255)).astype(np.uint8)
room[py-3:py+ph+3,px-3:px+pw+3]=(91,73,52)
room[py:py+ph,px:px+pw]=resize(base,(pw,ph))
# Close-up artwork centered above bilingual subtitles, with no crop.
AW,AH,AX,AY=980,1221,50,108
painting=resize(base,(AW,AH)).astype(np.float32)
layer_data=[]
for layer in full:
    a=resize(layer,(AW,AH)).astype(np.float32)
    mask=a[...,3]/255
    ys,xs=np.where(mask>.5)
    layer_data.append((a[...,:3],mask,(float(xs.mean()),float(ys.mean()))))

def artwork(t):
    p=painting.copy()
    for i,(rgb,a,center) in enumerate(layer_data):
        q=np.clip((t-LANDINGS[i]+.28)/.28,0,1)
        if q<=0: continue
        if q<1:
            e=(1-q)**3
            m=cv2.getRotationMatrix2D(center,(-1)**i*4*e,1+.12*e)
            m[:,2]+=[0,-36*e]
            rgb=cv2.warpAffine(rgb,m,(AW,AH))
            a=cv2.warpAffine(a,m,(AW,AH))*min(1,q*4)
        p=p*(1-a[...,None])+rgb*a[...,None]
    return p.astype(np.uint8)

# Return to the same room with all four original stickers preserved.
room_stickered=room.copy()
room_stickered[py:py+ph,px:px+pw]=resize(artwork(15.8),(pw,ph))

# Signature extracted from the real painting; not replaced by a typeset logo.
sig=base[int(base.shape[0]*.90):,int(base.shape[1]*.025):int(base.shape[1]*.13)]
sig=resize(sig,(420,501)).astype(float)
sig_alpha=np.clip((150-np.min(sig,axis=2))/85,0,1)


# High-resolution, locked wall compositions: artwork and wall always share one camera.
# Float crop boxes with Lanczos avoid warpAffine's quantized subpixel shimmer.
CAMERA_SS=2
room_hi=resize(room,(W*CAMERA_SS,H*CAMERA_SS))
room_stickered_hi=room_hi.copy()
hi_size=(pw*CAMERA_SS,ph*CAMERA_SS)
clean_hi=resize(base,hi_size)
stuck_hi=clean_hi.astype(np.float32)
for layer in full:
    rgba=resize(layer,hi_size).astype(np.float32)
    alpha=rgba[...,3:4]/255
    stuck_hi=stuck_hi*(1-alpha)+rgba[...,:3]*alpha
ys=slice(py*CAMERA_SS,(py+ph)*CAMERA_SS)
xs=slice(px*CAMERA_SS,(px+pw)*CAMERA_SS)
room_hi[ys,xs]=clean_hi
room_stickered_hi[ys,xs]=np.clip(stuck_hi,0,255).astype(np.uint8)


def camera_view(scene,scale):
    # Fixed-kernel continuous affine sampling, then a fixed 2:1 downsample.
    # Unlike resize(box=...), the filter footprint never changes with the zoom.
    # Both wall and canvas are sampled once from the same locked source image.
    cx,cy=px+pw/2,py+ph/2
    inv=1.0/float(scale)
    left=cx*(1-inv)*CAMERA_SS
    top=cy*(1-inv)*CAMERA_SS
    high=Image.fromarray(scene).transform(
        (W*CAMERA_SS,H*CAMERA_SS),Image.Transform.AFFINE,
        (inv,0,left,0,inv,top),resample=Image.Resampling.BICUBIC)
    return np.array(high.resize((W,H),Image.Resampling.LANCZOS))


def sun_glint(t):
    """Soft oval sunlight reflection, not a travelling bright stripe."""
    if not .06 <= t <= .96:
        return room_hi
    q=(t-.06)/.9
    hh,ww=ph*CAMERA_SS,pw*CAMERA_SS
    yy,xx=np.mgrid[:hh,:ww]
    glow=np.exp(-.5*(((xx-ww*.35)/(ww*.36))**2+((yy-hh*.24)/(hh*.29))**2))
    # Smooth single glimmer; no spatial sweep or repeated flashing.
    opacity=.30*glow*np.sin(np.pi*q)**2
    fr=room_hi.copy()
    patch=fr[ys,xs].astype(np.float32)/255
    light=np.array([1.0,.91,.72])[None,None,:]*opacity[...,None]
    fr[ys,xs]=np.clip((1-(1-patch)*(1-light))*255,0,255).astype(np.uint8)
    return fr


def frame(t):
    if t<3:
        # Begin on the actual painting, then pull back to reveal the room.
        q=np.clip(t/3.0,0,1)
        q=q*q*(3-2*q)
        scale=1.65-.65*q
        return camera_view(sun_glint(t),scale)
    if t<RETURN_TO_WALL:
        fr=np.full((H,W,3),(0,0,0),np.uint8)
        fr[AY:AY+AH,AX:AX+AW]=artwork(t)
        im=Image.fromarray(fr)
        if t<LANDINGS[0]-QUESTION_LEAD:
            return fr
        idx=min(3,max(0,sum(t+QUESTION_LEAD+1e-6>=x for x in LANDINGS)-1))
        if t<11.6:
            im=question_answer(im,CAPTIONS[idx],t-LANDINGS[idx])
        else:
            if t<SECOND_STATEMENT:
                ru,en,start='Я не ваша посылка!','I’m not your package!',11.6
            else:
                ru,en,start='Оставьте меня в покое!','Leave me alone!',SECOND_STATEMENT
            im=punch_text(im,[
                (ru,1430,70,(244,236,223)),
                (en,1545,58,(216,186,146)),
            ],t-start,1510)
        return np.array(im)
    if t<OUTRO_START:
        # Four-second push-in, followed by a circular iris closing on the painting.
        q=np.clip((t-RETURN_TO_WALL)/WALL_HOLD,0,1)
        q=q*q*(3-2*q)
        center=(px+pw/2,py+ph/2)
        fr=camera_view(room_stickered_hi,1+.08*q)
        if t>=RETURN_TO_WALL+WALL_HOLD:
            progress=np.clip((t-RETURN_TO_WALL-WALL_HOLD)/(IRIS_DURATION-1/FPS),0,1)
            progress=progress*progress*(3-2*progress)
            yy,xx=np.ogrid[:H,:W]
            dist=np.sqrt((xx-center[0])**2+(yy-center[1])**2)
            radius=np.hypot(max(center[0],W-center[0]),max(center[1],H-center[1]))*(1-progress)
            mask=np.clip((radius-dist)/3,0,1)
            fr=(fr*mask[...,None]).astype(np.uint8)
        return fr
    im=Image.new('RGB',(W,H),(0,0,0))
    text(im,'Картина',430,52,(198,183,162))
    text(im,'“Leave me alone”',550,86,(244,236,223),SERIF)
    text(im,'100×125 см, холст, масло',705,48,(198,183,162))
    fr=np.array(im).astype(float)
    q=np.clip((t-OUTRO_START-.55)/1.0,0,1)
    a=sig_alpha*(np.arange(420)[None,:]<420*q)
    dest=fr[960:1461,330:750]
    fr[960:1461,330:750]=dest*(1-a[...,None])+np.array([244,236,223])*a[...,None]
    return fr.astype(np.uint8)



def render():
    p=subprocess.Popen([FF,'-y','-loglevel','error','-f','rawvideo','-pix_fmt','rgb24',
        '-s',f'{W}x{H}','-r',str(FPS),'-i','-','-an','-c:v','libx264','-crf','18',
        '-preset','fast','-pix_fmt','yuv420p',str(WORK/'silent.mp4')],stdin=subprocess.PIPE)
    try:
        for f in range(round(DURATION*FPS)):
            p.stdin.write(frame(f/FPS).tobytes())
    finally:
        p.stdin.close()
    if p.wait(): raise RuntimeError('Video encoder failed')
    sr=48000
    def audio(path):
        rate,x=wavfile.read(path)
        if rate!=sr: raise ValueError(f'Expected 48kHz: {path}')
        x=x.astype(np.float32)/32768
        if x.ndim==1: x=np.repeat(x[:,None],2,axis=1)
        return x
    n=round(DURATION*sr)
    music=audio(ROOT/'music/space80s.wav')[round(MUSIC_IN*sr):]
    music=resample_poly(music,9,10,axis=0)
    if len(music)<n: raise ValueError('Selected music passage is too short')
    mix=np.zeros((n,2),np.float32)
    mix[:min(n,len(music))]=music[:n]*.52
    tt=np.arange(n)/sr
    mix*=np.minimum(np.clip(tt/.003,0,1),np.clip((DURATION-tt)/1.3,0,1))[:,None]
    # Strong downbeat opens immediately; another bass accent lands on the six-beat cut.
    impact_t=np.arange(round(.65*sr))/sr
    freq=46+55*np.exp(-impact_t/.025)
    phase=2*np.pi*np.cumsum(freq)/sr
    impact=np.sin(phase)*np.exp(-impact_t/.16)*np.minimum(1,impact_t/.002)*.23
    for accent,gain in [(0,.65),(3.0,1.0)]:
        start=round(accent*sr)
        mix[start:start+len(impact)]+=impact[:,None]*gain
    # Leave room around the tape contacts so the music never masks the sync.
    for land in LANDINGS:
        duck=1-.24*np.exp(-((tt-land)/.10)**2)
        mix*=duck[:,None]
    original=audio(ROOT/'sfx_options/sticker_A_classic.wav')
    press=make_heavy_press(sr)
    sfx=np.concatenate([original[:round(.62*sr)]*.75,press],axis=0)
    wavfile.write(WORK/'heavy_tape_press.wav',sr,(press*32767).astype(np.int16))
    for land in LANDINGS:
        start=round((land-.62)*sr); end=min(n,start+len(sfx))
        mix[start:end]+=sfx[:end-start]*.8
    wavfile.write(WORK/'mix.wav',sr,(np.clip(mix,-1,1)*32767).astype(np.int16))
    subprocess.run([FF,'-y','-loglevel','error','-i',str(WORK/'silent.mp4'),'-i',str(WORK/'mix.wav'),
        '-c:v','copy','-af','loudnorm=I=-16:TP=-1.5:LRA=9','-c:a','aac','-b:a','192k',
        '-t',str(DURATION),'-movflags','+faststart',str(OUT)],check=True)
    print(OUT)

if __name__=='__main__':
    render()
