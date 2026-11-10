"""Synthesises a calm, fragile ambient piece (soft piano-like arpeggios + airy pad, A minor, 64 bpm) -> music/ambient_fragile.wav
Usage: python make_music.py [seconds]"""
import sys, numpy as np
from scipy.io import wavfile
from scipy.signal import fftconvolve, butter, sosfilt
SR=48000; rng=np.random.default_rng(5)
DUR=float(sys.argv[1]) if len(sys.argv)>1 else 48.0
BPM=64; beat=60/BPM; bar=4*beat
N=int((DUR+6)*SR); L=np.zeros(N); R=np.zeros(N)
mf=lambda m:440*2**((m-69)/12)
def add(sig,t0,pan=0.5,g=1.0):
    s=int(t0*SR)
    if s>=N: return
    e=min(N,s+len(sig)); sig=sig[:e-s]*g
    L[s:e]+=sig*np.cos(pan*np.pi/2); R[s:e]+=sig*np.sin(pan*np.pi/2)
def pluck(m,dur=3.0,vel=1.0,bright=1.0):
    f=mf(m); n=int(dur*SR); t=np.arange(n)/SR; y=np.zeros(n)
    for k in range(1,9):
        fk=f*k*np.sqrt(1+0.0004*k*k)
        y+=np.sin(2*np.pi*fk*t+rng.uniform(0,6.28))*(1/k**(1.15/bright))*np.exp(-t*(1.1+0.9*k)/ (1+0.5*f/220))
        y+=np.sin(2*np.pi*fk*1.0015*t)*(0.4/k**(1.15/bright))*np.exp(-t*(1.1+0.9*k)/(1+0.5*f/220))
    y*=np.minimum(1,t/0.004)
    click=sosfilt(butter(2,[1500,6000],'band',fs=SR,output='sos'),rng.standard_normal(n))*np.exp(-t/0.01)*0.02
    return (y+click)*vel*0.3
def bell(m,dur,vel=1.0):
    f=mf(m); n=int(dur*SR); t=np.arange(n)/SR
    y=np.sin(2*np.pi*f*t)+0.35*np.sin(2*np.pi*2*f*t)*np.exp(-t/0.8)+0.12*np.sin(2*np.pi*3.01*f*t)*np.exp(-t/0.4)
    env=np.minimum(1,t/0.03)*np.exp(-t/(dur*0.55)); return y*env*vel*0.22
def padnote(m,dur,vel=1.0):
    n=int(dur*SR); t=np.arange(n)/SR; f=mf(m); y=np.zeros(n)
    for d in(-0.006,0,0.006):
        y+=np.sin(2*np.pi*f*(1+d)*t+rng.uniform(0,6.28))+0.3*np.sin(2*np.pi*2*f*(1+d)*t)
    y*=(0.8+0.2*np.sin(2*np.pi*0.18*t+rng.uniform(0,6.28)))
    a=1.4; env=np.minimum(1,t/a)*np.minimum(1,(dur-t)/a); return y*env*vel*0.05
chords=[dict(b=45,pad=[57,60,64],arp=[57,60,64,69,72]),   # Am
        dict(b=41,pad=[53,57,60],arp=[53,57,60,65,69]),   # F
        dict(b=48,pad=[55,60,64],arp=[55,60,64,67,72]),   # C
        dict(b=43,pad=[50,55,59],arp=[50,55,59,62,67])]   # G
mel=[[(0,76,2),(2,72,1),(3,74,1)],[(0,72,2),(2,69,1.5)],[(0,76,1.5),(2,79,2)],[(0,74,2),(2,71,2)]]
patt=[0,1,2,3,2,1,2,4]
nb=int(np.ceil(DUR/bar))+1
for b in range(nb):
    c=chords[b%4] if b<nb-2 else chords[0]; t0=b*bar
    for m in c['pad']: add(padnote(m-0+0,bar+2.4),t0-1.2 if b else t0,pan=rng.uniform(.3,.7))
    add(pluck(c['b'],4.5,0.9,0.6),t0,0.5)
    if b>=2:                                   # arpeggio enters on bar 3
        for i,pi in enumerate(patt):
            add(pluck(c['arp'][pi],2.6,rng.uniform(.5,.85)),t0+i*beat/2+rng.normal(0,0.004),pan=0.35+0.3*(pi/4))
    elif b==1: 
        for i,pi in enumerate([2,4]): add(pluck(c['arp'][pi],3.5,0.5),t0+i*2*beat,0.55)
    if b>=4:
        for (bt,m,d) in mel[b%4]: add(bell(m+(12 if b>=8 and b%4==2 else 0),d*beat*1.6,0.9),t0+bt*beat,pan=0.62)
# reverb (long, soft) on a stereo mix
def ir(sec=3.2):
    n=int(sec*SR); t=np.arange(n)/SR
    x=rng.standard_normal(n)*np.exp(-t/0.75); x=sosfilt(butter(2,5500,'low',fs=SR,output='sos'),x); x[:int(0.02*SR)]*=np.linspace(0,1,int(0.02*SR)); return x/np.sqrt((x**2).sum())
wl,wr=fftconvolve(L,ir())[:N],fftconvolve(R,ir())[:N]
mixL=0.72*L+0.55*wl*3.0; mixR=0.72*R+0.55*wr*3.0
M=int(DUR*SR); y=np.stack([mixL[:M],mixR[:M]],1)
t=np.arange(M)/SR
y*=np.minimum(1,t/2.0)[:,None]*np.minimum(1,(DUR-t)/4.0)[:,None]    # fade in / out
y=sosfilt(butter(2,80,'high',fs=SR,output='sos'),y,axis=0)
y*=0.12/np.sqrt((y**2).mean())                                       # RMS about -18 dBFS
y=np.tanh(y*1.2)/np.tanh(1.2)
print('peak',np.abs(y).max().round(3),'rms dB',(20*np.log10(np.sqrt((y**2).mean()))).round(1))
import os; os.makedirs('music',exist_ok=True)
wavfile.write('music/ambient_fragile.wav',SR,(y*32767).astype(np.int16))
