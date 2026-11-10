"""Builds: clean base, sticker layers (RGBA) and a preview video (stickers appear every 2 s).
Needs: pillow numpy opencv-python-headless imageio-ffmpeg. Inputs: original.jpg, work/clean_aligned.png, work/mask_*.png"""
import cv2, numpy as np, glob, os, subprocess, imageio_ffmpeg
os.makedirs('layers',exist_ok=True)
o=cv2.imread('original.jpg'); a=cv2.imread('work/clean_aligned.png'); H,W=o.shape[:2]
names=['1_fragile','2_handle','3_notdrop','4_donottouch']
masks=[cv2.imread(f'work/mask_{n}.png',0).astype(np.float32)/255 for n in names]
union=np.clip(sum(masks),0,1)[...,None]
clean=(o*(1-union)+a*union).astype(np.uint8)
cv2.imwrite('00_clean_base.jpg',clean,[cv2.IMWRITE_JPEG_QUALITY,95])
for n,m in zip(names,masks):
    ys,xs=np.where(m>0.003); y0,y1,x0,x1=ys.min(),ys.max()+1,xs.min(),xs.max()+1
    rgba=np.dstack([o[y0:y1,x0:x1],(m[y0:y1,x0:x1]*255).astype(np.uint8)])
    cv2.imwrite(f'layers/{n}.png',rgba); print(n,'x',x0,'y',y0,'w',x1-x0,'h',y1-y0)
# video
VW,VH=1080,1346; FPS=30; INTERVAL=2.0; FADE=0.5; TOTAL=10.0
rs=lambda im,interp=cv2.INTER_AREA: cv2.resize(im,(VW,VH),interpolation=interp)
base=rs(clean).astype(np.float32); orig=rs(o).astype(np.float32)
ms=[rs(m)[...,None] for m in masks]
ff=subprocess.Popen([imageio_ffmpeg.get_ffmpeg_exe(),'-y','-loglevel','error','-f','rawvideo','-pix_fmt','bgr24','-s',f'{VW}x{VH}','-r',str(FPS),'-i','-',
  '-c:v','libx264','-pix_fmt','yuv420p','-crf','16','-preset','slow','-movflags','+faststart','preview_stickers_every_2s.mp4'],stdin=subprocess.PIPE)
for f in range(int(TOTAL*FPS)):
    t=f/FPS; fr=base
    for i,m in enumerate(ms):
        p=np.clip((t-INTERVAL*(i+1))/FADE,0,1); p=p*p*(3-2*p)
        if p>0: fr=fr*(1-m*p)+orig*(m*p)
    ff.stdin.write(np.clip(fr,0,255).astype(np.uint8).tobytes())
ff.stdin.close(); ff.wait()
