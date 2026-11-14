"""Reproducible 19.5-second vertical short. Run: .venv/bin/python video_prep/build_short.py
Original artwork and sticker pixels are preserved; generated photographic intro assets
are chroma-keyed/composited, not generated video. No narration.
"""
from pathlib import Path
import subprocess
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.io import wavfile
import imageio_ffmpeg

ROOT = Path(__file__).resolve().parent
W, H, FPS = 1080, 1920, 30
DURATION = 19.5
OUT = ROOT / 'short_leave_me_alone.mp4'
WORK = ROOT / 'short_work'
WORK.mkdir(exist_ok=True)
FF = imageio_ffmpeg.get_ffmpeg_exe()
FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
SERIF = '/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf'
LANDINGS = [3.6, 5.6, 7.6, 9.6]
CAPTIONS = [
    ('Хрупкая? Да.', 'Fragile? Yes.'),
    ('Осторожно? Да.', 'Be careful? Yes.'),
    ('Не бросать? Да.', 'Do not drop? Yes.'),
    ('Не трогать? Именно.', 'Don’t touch? Exactly.'),
]

def read(path):
    return np.array(Image.open(path).convert('RGB'))

def resize(im, size):
    return cv2.resize(im, size, interpolation=cv2.INTER_AREA)

def text(im, words, y, size=42, color=(244, 236, 223), font=FONT):
    d = ImageDraw.Draw(im)
    d.text((W//2, y), words, font=ImageFont.truetype(font, size), fill=color, anchor='mt')

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
pw,ph,px,py = 506,630,287,597
shadow = np.zeros((H,W),np.uint8)
shadow[py+12:py+ph+12,px+12:px+pw+12]=75
shadow=cv2.GaussianBlur(shadow,(0,0),15)
room=(room.astype(float)*(1-shadow[...,None]/255)).astype(np.uint8)
room[py-3:py+ph+3,px-3:px+pw+3]=(91,73,52)
room[py:py+ph,px:px+pw]=resize(base,(pw,ph))
hand=resize(read(ROOT/'short_assets/hands.jpg'),(W,H)).astype(np.float32)
# Soft chroma key with green spill suppression. RGB channels.
r,g,b=cv2.split(hand)
alpha=np.clip((np.maximum(r,b)-g+65)/65,0,1)
hand[...,1]=np.minimum(g,np.maximum(r,b)+8)
# Separate the opposing hands along the empty opening diagonal.
yy,xx=np.mgrid[:H,:W]
left=(yy > 0.73*xx+440).astype(np.float32)
hand_parts=[alpha*left,alpha*(1-left)]

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

# Signature extracted from the real painting; not replaced by a typeset logo.
sig=base[int(base.shape[0]*.90):,int(base.shape[1]*.025):int(base.shape[1]*.13)]
sig=resize(sig,(176,210)).astype(float)
sig_alpha=np.clip((150-np.min(sig,axis=2))/85,0,1)


def frame(t):
    if t<3:
        fr=room.astype(np.float32).copy()
        q=np.clip((t-.65)/1.05,0,1)
        q=q*q*(3-2*q)
        for mask,dx,dy in [(hand_parts[0],-W*q,H*.45*q),(hand_parts[1],W*q,-H*.45*q)]:
            mat=np.float32([[1,0,dx],[0,1,dy]])
            a=cv2.warpAffine(mask,mat,(W,H))
            rgb=cv2.warpAffine(hand,mat,(W,H))
            fr=fr*(1-a[...,None])+rgb*a[...,None]
        return np.clip(fr,0,255).astype(np.uint8)
    if t<15.8:
        fr=np.full((H,W,3),(24,25,25),np.uint8)
        fr[AY:AY+AH,AX:AX+AW]=artwork(t)
        im=Image.fromarray(fr)
        if t<3.32:
            return fr
        idx=min(3,max(0,sum(t>=x for x in LANDINGS)-1))
        if t<11.6:
            ru,en=CAPTIONS[idx]
            text(im,ru,1430,48)
            text(im,en,1510,39,(198,183,162))
        else:
            text(im,'Я не ваша посылка.',1410,45)
            text(im,'Оставьте меня в покое.',1476,45)
            text(im,'I’m not your package.',1576,37,(198,183,162))
            text(im,'Leave me alone.',1635,37,(198,183,162))
        return np.array(im)
    im=Image.new('RGB',(W,H),(239,230,212))
    text(im,'Картина',550,37,(99,86,69))
    text(im,'“Leave me alone”',655,65,(39,37,33),SERIF)
    text(im,'100×125 см, холст, масло',770,34,(99,86,69))
    fr=np.array(im).astype(float)
    q=np.clip((t-16.8)/1.0,0,1)
    a=sig_alpha*(np.arange(176)[None,:]<176*q)
    dest=fr[1000:1210,452:628]
    fr[1000:1210,452:628]=dest*(1-a[...,None])+np.array([101,64,46])*a[...,None]
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
    music=audio(ROOT/'music/space80s.wav')
    mix=np.zeros((n,2),np.float32)
    mix[:min(n,len(music))]=music[:n]*.52
    tt=np.arange(n)/sr
    mix*=np.minimum(np.clip(tt/.25,0,1),np.clip((DURATION-tt)/1.3,0,1))[:,None]
    sfx=audio(ROOT/'sfx_options/sticker_A_classic.wav')
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
