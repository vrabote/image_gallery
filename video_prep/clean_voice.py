"""Denoise the voice (Wiener-style spectral subtraction; noise profile = quietest frames of the same recording).
Usage: python clean_voice.py input.(mp4|mov|wav) out.wav [max_seconds]"""
import sys, subprocess, numpy as np, imageio_ffmpeg
from scipy.io import wavfile
from scipy.signal import stft, istft, butter, sosfilt
from scipy.ndimage import uniform_filter
FF=imageio_ffmpeg.get_ffmpeg_exe(); SR=48000
src,dst=sys.argv[1],sys.argv[2]; maxs=float(sys.argv[3]) if len(sys.argv)>3 else 60
subprocess.run([FF,'-y','-loglevel','error','-i',src,'-t',str(maxs),'-vn','-ac','1','-ar',str(SR),'work/_raw_mono.wav'],check=True)
sr,x=wavfile.read('work/_raw_mono.wav'); x=x.astype(np.float64)/32768
nper,hop=2048,512
f,t,X=stft(x,SR,nperseg=nper,noverlap=nper-hop); P=np.abs(X)**2
band=(f>100)&(f<6000); fe=P[band].sum(0)
quiet=fe<=np.percentile(fe,25)                          # noise-only frames
Nn=np.percentile(P[:,quiet],75,axis=1)[:,None]
prio=uniform_filter(np.maximum(P/(Nn+1e-20)/2.5-1,0),size=(3,5))
G=np.maximum(prio/(prio+1.0),10**(-30/20)); G=uniform_filter(G,size=(3,3))
_,y=istft(X*G,SR,nperseg=nper,noverlap=nper-hop); y=y[:len(x)]
db=lambda s:20*np.log10(np.sqrt((s**2).mean())+1e-12)
Pl=np.abs(istft(X*G,SR,nperseg=nper,noverlap=nper-hop)[1][:len(x)])
fr=int(0.05*SR); e=np.array([db(y[i:i+fr]) for i in range(0,len(y)-fr,fr)])
speech=e>np.percentile(e,65); 
sp=np.concatenate([y[i*fr:(i+1)*fr] for i in np.where(speech)[0]]); gain=-21-db(sp)
nz=np.concatenate([y[i*fr:(i+1)*fr] for i in np.where(e<np.percentile(e,20))[0]]); nz0=np.concatenate([x[i*fr:(i+1)*fr] for i in np.where(e<np.percentile(e,20))[0]])
print(f'speech {db(sp):.1f} dB, noise before {db(nz0):.1f} -> after {db(nz):.1f} dB (noise reduced {db(nz0)-db(nz):.1f} dB), gain +{gain:.1f} dB, SNR after {db(sp)-db(nz):.1f} dB')
wavfile.write('work/_den_unity.wav',SR,(np.clip(y,-1,1)*32767).astype(np.int16))
dur=len(y)/SR
af=(f"volume=0:enable='lt(t,1.0)',highpass=f=75,volume={gain:.1f}dB,agate=threshold=0.02:ratio=3:attack=4:release=150:range=0.08,"
    "equalizer=f=220:t=q:w=1:g=-2.5,equalizer=f=3200:t=q:w=1:g=2.5,equalizer=f=7500:t=q:w=1:g=-2,"
    "acompressor=threshold=-22dB:ratio=3:attack=10:release=150:makeup=2,alimiter=limit=0.89,"
    f"afade=t=in:st=0:d=0.05,afade=t=out:st={dur-0.15:.2f}:d=0.15")
subprocess.run([FF,'-y','-loglevel','error','-i','work/_den_unity.wav','-af',af,'-ar',str(SR),dst],check=True)
