"""HD video: stickers get 'stuck' onto the painting one after another (every 2 s) + tape sound.
Run after build.py (needs 00_clean_base.jpg, layers/*.png). Output: sticker_video_hd.mp4"""
import cv2, numpy as np, subprocess, imageio_ffmpeg
from scipy.io import wavfile
from make_sfx import make, SR
VW,VH=1542,1920; FPS=30; TOTAL=10.5
FIRST=2.0; INTERVAL=2.0      # 1st slap at 2 s, then every 2 s
APPROACH=0.45                # how long a sticker "flies in" before it lands
PEEL=0.62                    # length of the peel part of the sound (ends exactly at landing)
names=['1_fragile','2_handle','3_notdrop','4_donottouch']
offs=[(962,1557),(640,2128),(318,2638),(1604,2715)]   # layer position in the 2804x3493 original
r=VW/2804; rs=lambda im:cv2.resize(im,(VW,VH),interpolation=cv2.INTER_AREA)
base=rs(cv2.imread('00_clean_base.jpg')).astype(np.float32)
layers=[]
for n,(x,y) in zip(names,offs):
    L=cv2.imread(f'layers/{n}.png',cv2.IMREAD_UNCHANGED); h,w=L.shape[:2]
    full=np.zeros((3493,2804,4),np.uint8); full[y:y+h,x:x+w]=L
    f=cv2.resize(full,(VW,VH),interpolation=cv2.INTER_AREA).astype(np.float32)
    a=f[...,3:4]/255; ys,xs=np.where(a[...,0]>0.5)
    layers.append((f[...,:3],a,(xs.mean(),ys.mean())))
def over(bg,rgb,a): return bg*(1-a)+rgb*a
stages=[base]                                  # stages[i] = base with first i stickers stuck
for rgb,a,_ in layers: stages.append(over(stages[-1],rgb,a))
rng=np.random.default_rng(3); tilt=[2.5,-2.0,3.0,-2.5]
def frame(t):
    k=sum(t>=FIRST+INTERVAL*i for i in range(4))          # fully landed
    fr=stages[k]
    if k<4:
        land=FIRST+INTERVAL*k; p=(t-(land-APPROACH))/APPROACH
        if p>0:
            p=min(p,1); e=1-(1-p)**3                      # ease-out
            rgb,a,(cx,cy)=layers[k]; q=1-e
            sc=1+0.16*q*q+(0.012*np.sin(np.pi*p) if p<1 else 0)*0  # hover size
            M=cv2.getRotationMatrix2D((cx,cy),tilt[k]*q*q,sc)
            M[:,2]+=[0,-30*q*q]                           # comes from slightly above
            W=lambda im:cv2.warpAffine(im,M,(VW,VH),flags=cv2.INTER_LINEAR,borderValue=0)
            wrgb=W(rgb); wa=W(a)[...,None] if W(a).ndim==2 else W(a)
            al=wa*min(1,p*3)
            # soft shadow that shrinks as the sticker touches down
            sh=cv2.GaussianBlur(wa[...,0] if wa.ndim==3 else wa,(0,0),6+34*q)
            sh=np.roll(sh,(int(6+38*q),int(3+18*q)),(0,1))[...,None]*0.55*min(1,p*3)*(0.25+0.75*q)
            fr=fr*(1-sh*(1-al))
            fr=over(fr,wrgb,al)
    return fr
# ---- audio ----
y=make(PEEL); aud=np.zeros(int(TOTAL*SR)+len(y))
for i in range(4):
    s=int((FIRST+INTERVAL*i-PEEL)*SR); aud[s:s+len(y)]+=y*(0.95 if i%2==0 else 0.85)
aud=aud[:int(TOTAL*SR)]; aud=np.tanh(aud)*0.9
wavfile.write('sfx/soundtrack.wav',SR,(aud*32767).astype(np.int16))
# ---- video ----
ff=subprocess.Popen([imageio_ffmpeg.get_ffmpeg_exe(),'-y','-loglevel','error','-f','rawvideo','-pix_fmt','bgr24','-s',f'{VW}x{VH}','-r',str(FPS),'-i','-',
  '-i','sfx/soundtrack.wav','-c:v','libx264','-profile:v','high','-pix_fmt','yuv420p','-crf','14','-preset','slow','-c:a','aac','-b:a','192k',
  '-movflags','+faststart','-shortest','sticker_video_hd.mp4'],stdin=subprocess.PIPE)
for f in range(int(TOTAL*FPS)):
    ff.stdin.write(np.clip(frame(f/FPS),0,255).astype(np.uint8).tobytes())
ff.stdin.close(); ff.wait()
