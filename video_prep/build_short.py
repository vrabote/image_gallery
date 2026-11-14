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
from scipy.signal import resample_poly
import imageio_ffmpeg

ROOT = Path(__file__).resolve().parent
W, H, FPS = 1080, 1920, 30
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
CAPTIONS = [
    ('Хрупкая? Да!', 'Fragile? Yes!'),
    ('Осторожно? Да!', 'Be careful? Yes!'),
    ('Не бросать? Да!', 'Do not drop? Yes!'),
    ('Не трогать? Именно!', 'Don’t touch? Exactly!'),
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


def frame(t):
    if t<3:
        # Begin on the actual painting, then pull back to reveal the room.
        q=np.clip((t-.25)/2.25,0,1)
        q=q*q*(3-2*q)
        scale=1.95-.95*q
        mat=cv2.getRotationMatrix2D((px+pw/2,py+ph/2),0,scale)
        return cv2.warpAffine(room,mat,(W,H),flags=cv2.INTER_CUBIC)
    if t<RETURN_TO_WALL:
        fr=np.full((H,W,3),(0,0,0),np.uint8)
        fr[AY:AY+AH,AX:AX+AW]=artwork(t)
        im=Image.fromarray(fr)
        if t<LANDINGS[0]:
            return fr
        idx=min(3,max(0,sum(t+1e-6>=x for x in LANDINGS)-1))
        if t<11.6:
            ru,en=CAPTIONS[idx]
            im=punch_text(im,[(ru,1430,70,(244,236,223)),
                              (en,1545,58,(216,186,146))],t-LANDINGS[idx],1510)
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
        mat=cv2.getRotationMatrix2D(center,0,1+.12*q)
        fr=cv2.warpAffine(room_stickered,mat,(W,H),flags=cv2.INTER_CUBIC)
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
    for land in LANDINGS+[11.6,SECOND_STATEMENT]:
        duck=1-.24*np.exp(-((tt-land)/.10)**2)
        mix*=duck[:,None]
    sfx=audio(ROOT/'sfx_options/sticker_A_classic.wav')
    for land in LANDINGS:
        start=round((land-.62)*sr); end=min(n,start+len(sfx))
        mix[start:end]+=sfx[:end-start]*.8
    # Final statement gets the same contact sound, without another peel.
    press=sfx[round(.62*sr):]
    for statement in [11.6,SECOND_STATEMENT]:
        start=round(statement*sr); end=min(n,start+len(press))
        mix[start:end]+=press[:end-start]*.8
    wavfile.write(WORK/'mix.wav',sr,(np.clip(mix,-1,1)*32767).astype(np.int16))
    subprocess.run([FF,'-y','-loglevel','error','-i',str(WORK/'silent.mp4'),'-i',str(WORK/'mix.wav'),
        '-c:v','copy','-af','loudnorm=I=-16:TP=-1.5:LRA=9','-c:a','aac','-b:a','192k',
        '-t',str(DURATION),'-movflags','+faststart',str(OUT)],check=True)
    print(OUT)

if __name__=='__main__':
    render()
