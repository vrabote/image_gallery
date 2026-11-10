"""Generates alternative tape/sticker sounds into sfx_options/ (WAV + MP3) and one demo file with all of them in order."""
import numpy as np, os, subprocess, imageio_ffmpeg
from scipy.signal import butter, sosfilt
from scipy.io import wavfile
SR=48000; rng=np.random.default_rng(11)
def bp(x,lo,hi,o=4): return sosfilt(butter(o,[lo,hi],btype='band',fs=SR,output='sos'),x)
def lp(x,f,o=2): return sosfilt(butter(o,f,btype='low',fs=SR,output='sos'),x)
def smooth(m,w): 
    s=np.convolve(rng.random(m),np.ones(w)/w,'same'); return (s-s.min())/(np.ptp(s)+1e-9)
def peel(dur,lo=1800,hi=9500,r0=70,r1=130,body=0.12,crack=0.5,sq=0.0):
    m=int(dur*SR); t=np.arange(m)/SR
    noise=bp(rng.standard_normal(m),lo,hi)
    ph=np.cumsum(r0+(r1-r0)*t/dur+rng.normal(0,18,m).clip(-40,40))/SR
    st=np.abs(np.sin(np.pi*ph))**3*(0.55+0.45*rng.random(m))
    env=(0.35+0.65*smooth(m,900))*np.minimum(1,t/0.05)*np.minimum(1,(dur-t)/0.08+0.25)*(0.6+0.4*t/dur)
    cr=np.zeros(m); i=rng.random(m)<(0.0015+0.004*t/dur); cr[i]=rng.uniform(-1,1,i.sum()); cr=bp(cr,2500,12000,2)*6
    y=0.55*noise*st*env+crack*cr*env+body*bp(rng.standard_normal(m),300,1200)*env
    if sq: y+=sq*bp(rng.standard_normal(m),3500,5200,3)*env*(0.5+0.5*np.sin(2*np.pi*(2+3*t/dur)*t))
    return y
def press(k=0.25,thump=0.85,click=0.55,rub=0.25,f0=95):
    n=int(k*SR); t=np.arange(n)/SR
    th=np.sin(2*np.pi*(f0-40*t/k)*t)*np.exp(-t/0.045)
    ck=bp(rng.standard_normal(n),1200,7000)*np.exp(-t/0.012)
    rb=bp(rng.standard_normal(n),2000,6000)*np.exp(-t/0.06)
    return thump*th+click*ck+rub*rb
def norm(y,peak=0.85): y=np.tanh(y*1.3)/np.tanh(1.3); return y/np.abs(y).max()*peak
def sticker(pdur,**kw):   # peel then press at the end; returns (audio, press_time)
    p=peel(pdur,**{k:v for k,v in kw.items() if k in('lo','hi','r0','r1','body','crack','sq')})
    pr=press(**{k:v for k,v in kw.items() if k in('k','thump','click','rub','f0')})
    y=np.zeros(len(p)+len(pr)); y[:len(p)]=p; y[len(p)-int(0.0*SR):len(p)-int(0.0*SR)+len(pr)]+=pr
    return norm(y),pdur
def paper_pat():
    rub=bp(rng.standard_normal(int(0.28*SR)),1500,5500)*np.exp(-np.arange(int(0.28*SR))/SR/0.09)
    y=np.zeros(int(0.5*SR)); y[:len(rub)]+=0.5*rub*np.minimum(1,np.arange(len(rub))/SR/0.03)
    s=int(0.2*SR); pr=press(0.2,thump=0.55,click=0.25,rub=0.1,f0=130); y[s:s+len(pr)]+=pr
    return norm(y),0.2
def transition_rip(dur=1.5,whoosh=False,snip=False):
    p=peel(dur,r0=45,r1=160,body=0.2,crack=0.6); n=len(p); t=np.arange(n)/SR
    p*=np.minimum(1,t/0.25)**1.5                          # starts soft, gets louder
    y=p.copy()
    if whoosh:
        w=bp(rng.standard_normal(n),200,3000)*(np.sin(np.pi*np.clip(t/dur,0,1))**2)*0.45; y+=w
    tail=int(0.4*SR); y=np.concatenate([y,np.zeros(tail)])
    if snip:
        for off,f in((0.0,0.0),(0.09,0.0)):
            s=n+int(off*SR); cl=bp(rng.standard_normal(int(0.04*SR)),2500,9000)*np.exp(-np.arange(int(0.04*SR))/SR/0.008)
            y[s:s+len(cl)]+=1.0*cl
    else:
        pr=press(0.3,thump=0.6,click=0.3,rub=0.15,f0=70); y[n-int(0.05*SR):n-int(0.05*SR)+len(pr)]+=pr
    return norm(y),dur
def dispenser(dur=1.4):
    n=int(dur*SR); t=np.arange(n)/SR
    y=peel(dur,lo=2500,hi=11000,r0=140,r1=240,body=0.05,crack=0.9,sq=0.2)
    ratchet=np.zeros(n); 
    for tt in np.arange(0.05,dur-0.1,0.045):
        s=int(tt*SR); c=bp(rng.standard_normal(int(0.012*SR)),1500,6000)*np.exp(-np.arange(int(0.012*SR))/SR/0.003); ratchet[s:s+len(c)]+=c*0.9
    y=y+ratchet; y=np.concatenate([y,np.zeros(int(0.35*SR))])
    s=n; cl=bp(rng.standard_normal(int(0.05*SR)),2500,9000)*np.exp(-np.arange(int(0.05*SR))/SR/0.01); y[s:s+len(cl)]+=1.3*cl
    return norm(y),dur
sounds={
 'sticker_A_classic':sticker(0.62),
 'sticker_B_quick_snap':sticker(0.22,r0=110,r1=180,thump=1.0,click=0.8),
 'sticker_C_slow_peel':sticker(1.05,r0=40,r1=90,body=0.2,thump=0.7,rub=0.35),
 'sticker_D_packing_tape':sticker(0.7,lo=2500,hi=11000,r0=60,r1=100,crack=0.9,sq=0.5,thump=0.6,click=0.7),
 'sticker_E_soft_paper':paper_pat(),
 'transition_1_long_rip':transition_rip(1.5),
 'transition_2_rip_whoosh':transition_rip(1.8,whoosh=True),
 'transition_3_dispenser_snip':dispenser(1.4),
}
os.makedirs('sfx_options',exist_ok=True); ff=imageio_ffmpeg.get_ffmpeg_exe(); demo=[]; lines=[]
for n,(y,pt) in sounds.items():
    wavfile.write(f'sfx_options/{n}.wav',SR,(y*32767).astype(np.int16))
    subprocess.run([ff,'-y','-loglevel','error','-i',f'sfx_options/{n}.wav','-b:a','192k',f'sfx_options/{n}.mp3'])
    demo+= [y,np.zeros(int(1.2*SR))]; lines.append(f'{n}  ({len(y)/SR:.2f} s, press/cut at {pt:.2f} s)')
d=np.concatenate(demo); wavfile.write('sfx_options/_demo_all_in_order.wav',SR,(d*32767).astype(np.int16))
subprocess.run([ff,'-y','-loglevel','error','-i','sfx_options/_demo_all_in_order.wav','-b:a','192k','sfx_options/_demo_all_in_order.mp3'])
open('sfx_options/README.txt','w').write('Demo file plays all sounds in this order, 1.2 s apart:\n'+'\n'.join(f'{i+1}. {l}' for i,l in enumerate(lines))+'\n')
print(open('sfx_options/README.txt').read()); 
