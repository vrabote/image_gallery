"""80s 'space' synth music (Jarre / Vangelis / Moroder flavour): analog arpeggio, lush detuned pads with chorus, pulsing bass,
drum machine, echo lead, riser. D minor, 110 bpm, 20 bars (~43.6 s) -> music/space80s.wav
Structure: bars 1-4 pad+arp (float in) | 5-12 bass+drums build | 13-18 drums drop out (room for tape sounds), lead+arp | 19-20 pad ring-out."""
import numpy as np, os
from scipy.io import wavfile
from scipy.signal import butter, sosfilt, fftconvolve, resample_poly
SR=48000; BPM=110; beat=60/BPM; bar=4*beat; NB=20; DUR=NB*bar
rng=np.random.default_rng(80)
N=int((DUR+5)*SR)
def bus(): return np.zeros(N),np.zeros(N)
pad,arp,lead,bass,drum,send=bus(),bus(),bus(),bus(),bus(),bus()
mf=lambda m:440*2**((m-69)/12)
def lp(x,fc,o=2): return sosfilt(butter(o,min(fc,SR/2-500),'low',fs=SR,output='sos'),x)
def hp(x,fc,o=2): return sosfilt(butter(o,fc,'high',fs=SR,output='sos'),x)
def bp(x,lo,hi,o=3): return sosfilt(butter(o,[lo,min(hi,SR/2-500)],'band',fs=SR,output='sos'),x)
def put(b,x,t0,pan=0.5,g=1.0,snd=0.0):
    s=int(t0*SR)
    if s<0 or s>=N: return
    e=min(N,s+len(x)); x=x[:e-s]*g; c,sn=np.cos(pan*np.pi/2),np.sin(pan*np.pi/2)
    b[0][s:e]+=x*c; b[1][s:e]+=x*sn
    if snd: send[0][s:e]+=x*c*snd; send[1][s:e]+=x*sn*snd
def osc(kind,f,n,ph0=0.0,w=0.5,over=4):
    t=np.arange(n*over)/(SR*over); ph=(f*t+ph0)%1
    y=(2*ph-1) if kind=='saw' else np.where(ph<w,1.0,-1.0)
    return resample_poly(y,1,over)
def adsr(n,a,d,s,r):
    t=np.arange(n)/SR; dur=n/SR
    e=np.minimum(1,t/max(a,1e-4))*(s+(1-s)*np.exp(-np.maximum(t-a,0)/max(d,1e-4)))
    return e*np.minimum(1,np.maximum(dur-t,0)/max(r,1e-4))
def filt_env(x,hi,lo,tau):          # 'analog' filter decay: crossfade between bright and dark versions
    t=np.arange(len(x))/SR; e=np.exp(-t/tau); return e*lp(x,hi)+(1-e)*lp(x,lo)
chords=[dict(r=38,bass=38,pad=[50,53,57,62],arp=[62,65,69,74]),    # Dm
        dict(r=34,bass=34,pad=[46,53,58,62],arp=[58,62,65,70]),    # Bb
        dict(r=41,bass=41,pad=[48,53,57,60],arp=[65,69,72,77]),    # F
        dict(r=36,bass=36,pad=[48,52,55,60],arp=[60,64,67,72])]    # C
def chord(b): return chords[b%4] if b<NB-1 else chords[0]
mel=[[(0,69,2),(2,74,1),(3,72,1)],[(0,70,2),(2,74,1),(3,77,1)],[(0,72,1.5),(1.5,69,.5),(2,72,2)],[(0,72,1),(1,76,1),(2,79,2)]]
# ---------- pad ----------
for b in range(NB):
    c=chord(b); t0=b*bar-0.9 if b else 0; dur=bar+1.8+(2.5 if b==NB-1 else 0); n=int(dur*SR)
    mix=np.zeros(n)
    for m in c['pad']:
        for d in(-0.0045,0.0045): mix+=osc('saw',mf(m)*(1+d),n,rng.random(),over=1)
    mix=lp(mix,1100+500*np.sin(b*0.5))*adsr(n,1.3,5,1,1.6)*0.05
    put(pad,mix,max(t0,0),0.5,1.0,snd=0.55)
# chorus on pad bus
def chorus(x,rate=0.35,depth=0.006):
    t=np.arange(len(x))/SR; d=(0.016+depth*np.sin(2*np.pi*rate*t))*SR
    idx=np.arange(len(x))-d; idx=np.clip(idx,0,len(x)-1); return np.interp(idx,np.arange(len(x)),x)
pad=(0.65*pad[0]+0.5*chorus(pad[0],0.31),0.65*pad[1]+0.5*chorus(pad[1],0.43,0.007))
# ---------- arpeggio (16ths, filter sweeps open then closes) ----------
step=beat/4; pat=[0,1,2,3,2,1,2,3,0,1,2,3,2,3,2,1]
for b in range(NB):
    c=chord(b)
    m=np.interp(b,[0,4,12,17,19],[0.45,0.75,1.25,1.1,0.6]); vel=np.interp(b,[0,3,6],[0.35,0.7,1.0]) if b<6 else (1.0 if b<18 else 0.7)
    for i in range(16):
        f=mf(c['arp'][pat[i]]); n=int(step*1.1*SR)
        x=0.6*osc('saw',f,n)+0.4*osc('pulse',f,n,w=0.35)
        x=filt_env(x,4200*m,700*m,0.09)*adsr(n,0.002,0.1,0.35,0.03)
        put(arp,x,b*bar+i*step,0.35+0.3*(i%2),0.16*vel*(1.0 if i%4==0 else 0.8),snd=0.3)
# ---------- bass ----------
for b in range(4,NB):
    c=chord(b); r=mf(c['bass'])
    if b>=18: 
        n=int(bar*SR*1.3); x=lp(osc('saw',r,n),500)*adsr(n,0.02,5,1,0.8)*0.5+0.4*np.sin(2*np.pi*r*np.arange(n)/SR)*adsr(n,0.02,5,1,0.8)
        put(bass,x,b*bar,0.5,0.5); continue
    for i in range(8):
        f=r*(2 if i in(3,7) else 1); n=int(beat/2*0.92*SR)
        x=filt_env(osc('saw',f,n),900,230,0.07)*adsr(n,0.003,0.08,0.6,0.02)+0.5*np.sin(2*np.pi*f*np.arange(n)/SR)*adsr(n,0.003,0.1,0.8,0.02)
        put(bass,x,b*bar+i*beat/2,0.5,0.42*(1.0 if i%2==0 else 0.8))
# ---------- drums ----------
def kick():
    n=int(0.4*SR); t=np.arange(n)/SR; f=45+110*np.exp(-t/0.03); ph=2*np.pi*np.cumsum(f)/SR
    return (np.sin(ph)*np.exp(-t/0.16)+0.25*bp(rng.standard_normal(n),1500,5000)*np.exp(-t/0.006))
def clap():
    n=int(0.45*SR); x=np.zeros(n); t=np.arange(n)/SR
    for o in(0,0.011,0.022): s=int(o*SR); k=int(0.1*SR); x[s:s+k]+=bp(rng.standard_normal(k),900,5500)*np.exp(-np.arange(k)/SR/0.02)
    x[int(0.03*SR):]+=bp(rng.standard_normal(n-int(0.03*SR)),900,4500)*np.exp(-t[:n-int(0.03*SR)]/0.12)*0.4
    return x
def hat(op=False):
    n=int((0.22 if op else 0.05)*SR); return hp(rng.standard_normal(n),7000)*np.exp(-np.arange(n)/SR/(0.09 if op else 0.015))
for b in range(4,12):
    for q in range(4):
        put(drum,kick(),b*bar+q*beat,0.5,0.75)
        put(drum,hat(),b*bar+q*beat+beat/2,0.6,0.16)
        if b>=8 and q in(1,3): put(drum,clap(),b*bar+q*beat,0.5,0.28,snd=0.5)
        if b>=8: put(drum,hat(),b*bar+q*beat,0.4,0.07)
    if b>=8: put(drum,hat(True),b*bar+3.5*beat,0.55,0.12)
# ---------- lead (echo synth), bars 9-18 ----------
for b in range(8,18):
    for (bt,m,d) in mel[b%4]:
        f=mf(m+(12 if b>=12 and b%4==3 else 0)); n=int(d*beat*1.05*SR+0.5*SR); t=np.arange(n)/SR
        vib=1+0.004*np.sin(2*np.pi*5.2*t)*np.minimum(1,t/0.4); ph=np.cumsum(f*vib)/SR
        x=0.5*(2*((ph)%1)-1)+0.5*(2*((ph*1.004)%1)-1); x=lp(x,2600)*adsr(n,0.02,5,1,0.35)
        put(lead,x,b*bar+bt*beat,0.58,0.1,snd=0.35)
# ---------- riser into the tape rip (music time ~24.0 -> 27.0 s) ----------
rs,re=24.0,27.0; n=int((re-rs)*SR); x=np.zeros(n); blk=int(0.1*SR)
for i in range(0,n-blk,blk):
    fc=300*(25**(i/n)); seg=bp(rng.standard_normal(blk),fc*0.7,fc*1.5,2); x[i:i+blk]=seg*(i/n)**2
put(send,x*0.5,rs,0.5,1.0)
# ---------- echo / reverb ----------
def delay(x,time,fb,n=4,tone=3500):
    y=np.zeros(len(x)); cur=lp(x,tone)
    for k in range(1,n+1):
        s=int(k*time*SR); cur=lp(cur,tone)*fb; y[s:]+=cur[:len(x)-s]
    return y
dl=lambda b:delay(b[0],0.75*beat,0.5)
arp_e=(arp[0]+0.5*delay(arp[1],0.75*beat,0.5), arp[1]+0.5*delay(arp[0],0.75*beat,0.5))
lead_e=(lead[0]+0.7*delay(lead[1],0.75*beat,0.55,5), lead[1]+0.7*delay(lead[0],0.75*beat,0.55,5))
def ir(sec=2.8):
    n=int(sec*SR); t=np.arange(n)/SR; x=rng.standard_normal(n)*np.exp(-t/0.7); x=lp(x,6000)
    x[:int(0.015*SR)]*=np.linspace(0,1,int(0.015*SR)); return x/np.sqrt((x**2).sum())
snd_wet=(fftconvolve(send[0],ir())[:N],fftconvolve(send[1],ir())[:N])
M=int(DUR*SR)
L=pad[0]+arp_e[0]+lead_e[0]+bass[0]+drum[0]+1.8*snd_wet[0]
R=pad[1]+arp_e[1]+lead_e[1]+bass[1]+drum[1]+1.8*snd_wet[1]
y=np.stack([L[:M],R[:M]],1)
t=np.arange(M)/SR
y*=np.minimum(1,t/1.2)[:,None]*np.minimum(1,(DUR-t)/3.5)[:,None]
y=hp(y.T,35).T
y*=0.11/np.sqrt((y**2).mean()); y=np.tanh(y*1.4)*0.92
print('peak',np.abs(y).max().round(3),'rms dB',round(20*np.log10(np.sqrt((y**2).mean())),1),'dur',round(DUR,2))
os.makedirs('music',exist_ok=True); wavfile.write('music/space80s.wav',SR,(y*32767).astype(np.int16))
