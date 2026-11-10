"""Voice cleanup: (1) Wiener-style spectral-subtraction denoise (noise profile = quietest frames of the same recording),
(2) auto-EQ toward a natural, clear speech spectrum (the raw voice is very bass-heavy and dull), (3) gate / compress / limit / fades.
Usage: python clean_voice.py input.(mp4|mov|wav) out.wav [max_seconds] [mute_first_seconds]"""
import sys, subprocess, numpy as np, imageio_ffmpeg
from scipy.io import wavfile
from scipy.signal import stft, istft, welch
from scipy.ndimage import uniform_filter
FF=imageio_ffmpeg.get_ffmpeg_exe(); SR=48000
src,dst=sys.argv[1],sys.argv[2]; maxs=float(sys.argv[3]) if len(sys.argv)>3 else 60; mute=float(sys.argv[4]) if len(sys.argv)>4 else 0.0
subprocess.run([FF,'-y','-loglevel','error','-i',src,'-t',str(maxs),'-vn','-ac','1','-ar',str(SR),'work/_raw_mono.wav'],check=True)
sr,x=wavfile.read('work/_raw_mono.wav'); x=x.astype(np.float64)/32768
db=lambda s:20*np.log10(np.sqrt((s**2).mean())+1e-12)
# ---- 1. denoise ----
nper,hop=2048,512
f,t,X=stft(x,SR,nperseg=nper,noverlap=nper-hop); P=np.abs(X)**2
band=(f>100)&(f<6000); fe=P[band].sum(0); quiet=fe<=np.percentile(fe,25)
Nn=np.percentile(P[:,quiet],75,axis=1)[:,None]
prio=uniform_filter(np.maximum(P/(Nn+1e-20)/2.2-1,0),size=(3,5))
G=np.maximum(prio/(prio+1.0),10**(-28/20)); G=uniform_filter(G,size=(3,3))
_,y=istft(X*G,SR,nperseg=nper,noverlap=nper-hop); y=y[:len(x)]
fr=int(0.05*SR); e=np.array([db(y[i:i+fr]) for i in range(0,len(y)-fr,fr)])
lo=np.where(e<np.percentile(e,20))[0]
nz=np.concatenate([y[i*fr:(i+1)*fr] for i in lo]); nz0=np.concatenate([x[i*fr:(i+1)*fr] for i in lo])
print(f'noise {db(nz0):.1f} -> {db(nz):.1f} dB (reduced {db(nz0)-db(nz):.1f} dB)')
# ---- 2. auto-EQ ----
BANDS=[(0,150),(150,500),(500,2000),(2000,5000),(5000,12000)]; CEN=[75,300,1100,3200,8500]
TARGET=[-14,-6,-7,-10.5,-16]                  # long-term speech spectrum, dB relative to total power
def speech_seg(sig):
    ee=np.array([db(sig[i:i+fr]) for i in range(0,len(sig)-fr,fr)]); k=ee>np.percentile(ee,60)
    return np.concatenate([sig[i*fr:(i+1)*fr] for i in np.where(k)[0]])
def band_levels(sig):
    f_,Pw=welch(speech_seg(sig),SR,nperseg=4096); tot=Pw.sum()
    return np.array([10*np.log10(Pw[(f_>=a)&(f_<b)].sum()/tot+1e-12) for a,b in BANDS]),(f_*Pw).sum()/tot
def apply_eq(sig,gains):
    Y=np.fft.rfft(sig); fq=np.fft.rfftfreq(len(sig),1/SR)
    gdb=np.interp(np.log10(np.maximum(fq,20)),np.log10(CEN),gains); gdb=np.where(fq<60,gdb-25,gdb)
    return np.fft.irfft(Y*10**(gdb/20),len(sig))
print('bands before EQ',band_levels(y)[0].round(1),'centroid',round(band_levels(y)[1]))
gains=np.zeros(5)
for it in range(4): gains=np.clip(gains+(np.array(TARGET)-band_levels(apply_eq(y,gains))[0])*0.9,-20,16)
y=apply_eq(y,gains); bl,cen=band_levels(y)
print('auto-EQ gains dB',gains.round(1),'-> bands',bl.round(1),'centroid',round(cen))
sp=speech_seg(y); gain=-21-db(sp)
nz=np.concatenate([y[i*fr:(i+1)*fr] for i in lo])
print(f'speech {db(sp):.1f} dB, noise {db(nz):.1f} dB -> SNR {db(sp)-db(nz):.1f} dB, gain +{gain:.1f} dB')
wavfile.write('work/_den_unity.wav',SR,(np.clip(y,-1,1)*32767).astype(np.int16))
dur=len(y)/SR
af=(f"volume=0:enable='lt(t,{mute})',highpass=f=90,volume={gain:.1f}dB,agate=threshold=0.02:ratio=3:attack=4:release=150:range=0.08,"
    "acompressor=threshold=-22dB:ratio=3:attack=10:release=150:makeup=2,alimiter=limit=0.89:level=0,"
    f"afade=t=in:st=0:d=0.05,afade=t=out:st={dur-0.15:.2f}:d=0.15")
subprocess.run([FF,'-y','-loglevel','error','-i','work/_den_unity.wav','-af',af,'-ar',str(SR),dst],check=True)
