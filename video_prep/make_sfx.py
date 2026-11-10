"""Synthesises a 'sticker tape' sound: tape peel (crackly hiss) + soft press/slap at the end."""
import numpy as np
from scipy.signal import butter, sosfilt
from scipy.io import wavfile
SR=48000; rng=np.random.default_rng(7)
def bp(x,lo,hi,order=4): return sosfilt(butter(order,[lo,hi],btype='band',fs=SR,output='sos'),x)
def make(peel=0.62,tail=0.35):
    n=int((peel+tail)*SR); t=np.arange(n)/SR; y=np.zeros(n)
    # --- peel: sticky tape unrolling = band noise modulated by fast irregular pulses ---
    m=int(peel*SR); tp=np.arange(m)/SR
    noise=bp(rng.standard_normal(m),1800,9500)
    rate=70+60*tp/peel                       # fibre "stutter" speeds up
    ph=np.cumsum(rate+rng.normal(0,18,m).clip(-40,40))/SR
    stut=np.abs(np.sin(np.pi*ph))**3*(0.55+0.45*rng.random(m))
    slow=np.convolve(rng.random(m),np.ones(900)/900,'same'); slow=(slow-slow.min())/(np.ptp(slow)+1e-9)
    env=(0.35+0.65*slow)*np.minimum(1,tp/0.05)*np.minimum(1,(peel-tp)/0.08+0.25)*(0.6+0.4*tp/peel)
    crack=np.zeros(m)                         # tiny sharp clicks
    idx=rng.random(m)<(0.0015+0.004*tp/peel); crack[idx]=rng.uniform(-1,1,idx.sum())
    crack=bp(crack,2500,12000,2)*6
    y[:m]+=0.55*noise*stut*env+0.5*crack*env
    # low body of the peel
    y[:m]+=0.12*bp(rng.standard_normal(m),300,1200)*env
    # --- press / slap at t=peel ---
    s=int(peel*SR); k=int(0.25*SR); ts=np.arange(k)/SR
    thump=np.sin(2*np.pi*(95-40*ts/0.25)*ts)*np.exp(-ts/0.045)
    click=bp(rng.standard_normal(k),1200,7000)*np.exp(-ts/0.012)
    rub=bp(rng.standard_normal(k),2000,6000)*np.exp(-ts/0.06)*0.25
    y[s:s+k]+=0.85*thump+0.55*click+rub
    y=np.tanh(y*1.3)/np.tanh(1.3)
    return (y/np.abs(y).max()*0.85)
if __name__=='__main__':
    y=make(); wavfile.write('sfx/tape_sticker.wav',SR,(y*32767).astype(np.int16))
    print(len(y)/SR,'s')
