"""Final cut (1080x1920): intro (voice, enhanced) -> dissolve -> painting + stickers (tape sounds) -> fade -> signature on black. Music underneath.
Prereqs: compressed_IMG_8491.mov, work/stickers_v.mp4 (build_video.py with VW=1080 VH=1346 PADH=1920 FIRST=3 TOTAL=11.5 NOAUDIO=1),
music/space80s.wav (make_music_space80s.py), clean_voice.py, uploads/IMG_8491 (online-video-cutter.com).mp4, sfx_options/*.wav, signature.png.  Output: final_video.mp4"""
import cv2, numpy as np, subprocess, imageio_ffmpeg, sys
from scipy.io import wavfile
FF=imageio_ffmpeg.get_ffmpeg_exe(); SR=48000; FPS=30; W,H=1080,1920
INTRO=32.9; XF1=1.5; STK=11.5; XF2=1.0; OUTRO=6.0
T_STK=INTRO-XF1; T_OUT=T_STK+STK-XF2; TOTAL=T_OUT+OUTRO
import os
REBUILD=os.environ.get('REBUILD')=='1' or not os.path.exists('work/final_silent.mp4')
# ---------- outro: signature written left->right on black ----------
if REBUILD:
    sig=cv2.imread('signature.png',cv2.IMREAD_UNCHANGED); sh=560; sw=int(sig.shape[1]*sh/sig.shape[0])
    sig=cv2.resize(sig,(sw,sh),interpolation=cv2.INTER_AREA).astype(np.float32)
    a=sig[...,3:4]/255; ink=sig[...,:3]
    x0=(W-sw)//2; y0=(H-sh)//2-40
    p=subprocess.Popen([FF,'-y','-loglevel','error','-f','rawvideo','-pix_fmt','bgr24','-s',f'{W}x{H}','-r',str(FPS),'-i','-','-c:v','libx264','-crf','14','-pix_fmt','yuv420p','-an','work/outro.mp4'],stdin=subprocess.PIPE)
    cols=np.arange(sw)[None,:,None]
    for f in range(int(OUTRO*FPS)):
        t=f/FPS; q=np.clip((t-1.0)/2.5,0,1); q=q*q*(3-2*q)                  # write-on progress
        edge=sw*q*1.25-0.25*sw; wipe=np.clip((edge-cols)/(0.25*sw),0,1)
        fade=np.clip((t-0.9)/0.6,0,1)
        fr=np.zeros((H,W,3),np.float32); fr[y0:y0+sh,x0:x0+sw]=ink*a*wipe*fade
        p.stdin.write(np.clip(fr,0,255).astype(np.uint8).tobytes())
    p.stdin.close(); p.wait()
    # ---------- video: intro + stickers + outro with dissolves ----------
    norm=f"fps={FPS},scale={W}:{H},setsar=1,format=yuv420p"
    VF=("hqdn3d=2:2:3:3,colorchannelmixer=rr=1.02:bb=0.97,eq=brightness=0.04:contrast=1.1:saturation=1.12:gamma=1.07,unsharp=5:5:0.35")
    fc=(f"[0:v]{VF},{norm}[a];[1:v]{norm}[b];[2:v]{norm}[c];"
        f"[a][b]xfade=transition=fade:duration={XF1}:offset={INTRO-XF1}[ab];"
        f"[ab][c]xfade=transition=fade:duration={XF2}:offset={INTRO-XF1+STK-XF2}[v]")
    subprocess.run([FF,'-y','-loglevel','error','-i','compressed_IMG_8491.mov','-i','work/stickers_v.mp4','-i','work/outro.mp4','-filter_complex',fc,'-map','[v]','-an',
      '-c:v','libx264','-crf','15','-preset','slow','-pix_fmt','yuv420p','work/final_silent.mp4'],check=True)

# ---------- audio ----------
subprocess.run([sys.executable,'clean_voice.py','../uploads/IMG_8491 (online-video-cutter.com).mp4','work/voice.wav'],check=True)   # clean voice, 0-7.6 s (uncompressed cut)
rd=lambda f:(lambda s,x:(x.astype(np.float32)/32768))(*wavfile.read(f))
N=int(TOTAL*SR); mix=np.zeros((N,2),np.float32)
MUSIC_START=7.7                                                      # music begins right after the spoken words
mus=rd('music/space80s.wav'); m=np.zeros((N,2),np.float32); st=int(MUSIC_START*SR); e=min(N,st+len(mus)); m[st:e]=mus[:e-st]
t=np.arange(N)/SR; m*=np.minimum(1,np.maximum(TOTAL-t,0)/3.0)[:,None]   # fade out at the very end
mix+=m*0.62
def put(sig,t0,g=1.0):
    s=int(t0*SR); sig=sig if sig.ndim==1 else sig.mean(1); e=min(N,s+len(sig)); mix[s:e]+=(sig[:e-s]*g)[:,None]
put(rd('work/voice.wav'),0,1.0)
put(rd('sfx_options/transition_1_long_rip.wav'),INTRO-XF1,0.9)                # press lands as the dissolve ends
A=rd('sfx_options/sticker_A_classic.wav')
for i in range(4): put(A,T_STK+3.0+2.0*i-0.62,0.95 if i%2==0 else 0.85)       # same timing/sound as before
wavfile.write('work/final_audio.wav',SR,(np.clip(mix,-1,1)*32767).astype(np.int16))
subprocess.run([FF,'-y','-loglevel','error','-i','work/final_silent.mp4','-i','work/final_audio.wav','-af','loudnorm=I=-16:TP=-1.5:LRA=11','-c:v','copy','-ar','48000','-c:a','aac','-b:a','192k','-movflags','+faststart','-shortest','final_video.mp4'],check=True)
print('total',TOTAL)
