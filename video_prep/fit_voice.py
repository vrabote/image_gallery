"""Fits the separately recorded voice to the lip movements of the intro video.
Each spoken phrase of the clean recording is time-stretched (pitch preserved, ffmpeg atempo) so that it starts/ends where the same phrase
is spoken in the video's own (poor) audio, then placed on the timeline.   Usage: python fit_voice.py voice_full.wav out.wav"""
import sys, subprocess, numpy as np, imageio_ffmpeg
from scipy.io import wavfile
FF=imageio_ffmpeg.get_ffmpeg_exe(); SR=48000
# phrase (start,end) in the new recording  ->  (start,end) in the video timeline (= phrases found in the video's own audio, +0.07 s video offset)
MAP=[((0.32,2.60),(1.45,3.33)),
     ((3.32,4.36),(3.61,4.79)),
     ((5.10,6.92),(5.71,7.53))]
PRE,POST=0.10,0.15                                   # keep a little air around each phrase
sr,x=wavfile.read(sys.argv[1]); x=x.astype(np.float32)/32768; assert sr==SR
out=np.zeros(int(8.6*SR),np.float32)
for i,((s0,e0),(s1,e1)) in enumerate(MAP):
    a,b=max(0,s0-PRE),min(len(x)/SR,e0+POST); seg=x[int(a*SR):int(b*SR)].copy()
    fi=int(0.02*SR); seg[:fi]*=np.linspace(0,1,fi); seg[-fi:]*=np.linspace(1,0,fi)
    tempo=(e0-s0)/(e1-s1); wavfile.write('work/_seg.wav',SR,(seg*32767).astype(np.int16))
    subprocess.run([FF,'-y','-loglevel','error','-i','work/_seg.wav','-af',f'atempo={tempo:.4f}','-ar',str(SR),'work/_seg_t.wav'],check=True)
    sr2,t=wavfile.read('work/_seg_t.wav'); t=t.astype(np.float32)/32768
    start=s1-(s0-a)/tempo; k=int(start*SR); out[k:k+len(t)]+=t
    print(f'phrase {i+1}: {s0}-{e0}s -> {s1}-{e1}s, tempo x{tempo:.2f}')
n=int(7.9*SR); out=out[:n]; out[-int(0.1*SR):]*=np.linspace(1,0,int(0.1*SR))
wavfile.write(sys.argv[2],SR,(np.clip(out,-1,1)*32767).astype(np.int16)); print('voice length',len(out)/SR,'peak',np.abs(out).max().round(2))
