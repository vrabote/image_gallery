"""Spectral-subtraction (Wiener-style) denoise of the voice from the intro, using the noise-only part of the same recording as noise profile.
Usage: python clean_voice.py in.mov out.wav"""
import sys, subprocess, numpy as np, imageio_ffmpeg
from scipy.io import wavfile
from scipy.signal import stft, istft, butter, sosfilt
from scipy.ndimage import uniform_filter
FF=imageio_ffmpeg.get_ffmpeg_exe(); SR=48000
subprocess.run([FF,'-y','-loglevel','error','-i',sys.argv[1],'-vn','-ac','1','-ar',str(SR),'work/_raw_mono.wav'],check=True)
sr,x=wavfile.read('work/_raw_mono.wav'); x=x.astype(np.float64)/32768
x=x[:int(8*SR)]                                     # speech is only in the first seconds
nper=2048; hop=512
f,t,X=stft(x,SR,nperseg=nper,noverlap=nper-hop)
P=np.abs(X)**2
noise_frames=(t>5.0)&(t<7.8)                         # tail with no speech = noise profile
Nn=np.percentile(P[:,noise_frames],75,axis=1)[:,None]
# decision-directed-ish Wiener gain with smoothing
snr_post=P/(Nn+1e-20)
prio=np.maximum(snr_post/3.0-1,0)          # over-subtract (x3)
prio=uniform_filter(prio,size=(3,5))
G=prio/(prio+1.0)
G=np.maximum(G,10**(-30/20))
G=uniform_filter(G,size=(3,3))
Y=X*G
_,y=istft(Y,SR,nperseg=nper,noverlap=nper-hop); y=y[:len(x)]
wavfile.write('work/_denoised_raw.wav',SR,(np.clip(y*8,-1,1)*32767).astype(np.int16))   # temp
# report
seg=lambda a,b:y[int(a*SR):int(b*SR)]
db=lambda s:20*np.log10(np.sqrt((s**2).mean())+1e-12)
print('speech rms before/after dB:',round(db(x[int(1*SR):int(3.9*SR)]),1),round(db(seg(1,3.9)),1))
print('noise  rms before/after dB:',round(db(x[int(6*SR):int(7.5*SR)]),1),round(db(seg(6,7.5)),1))
# voice polish: gain, EQ, compression, fade out. Keep until 4.25s.
af=("highpass=f=75,volume=44dB,agate=threshold=0.03:ratio=4:attack=3:release=120:range=0.05,equalizer=f=220:t=q:w=1:g=-2.5,equalizer=f=3200:t=q:w=1:g=2.5,"
    "equalizer=f=7500:t=q:w=1:g=-2,acompressor=threshold=-24dB:ratio=3:attack=10:release=150:makeup=2,"
    "alimiter=limit=0.89,afade=t=in:st=0.8:d=0.1,afade=t=out:st=3.95:d=0.3")
wavfile.write('work/_den_unity.wav',SR,(np.clip(y,-1,1)*32767).astype(np.int16))
subprocess.run([FF,'-y','-loglevel','error','-i','work/_den_unity.wav','-t','4.3','-af',af,'-ar',str(SR),sys.argv[2]],check=True)
