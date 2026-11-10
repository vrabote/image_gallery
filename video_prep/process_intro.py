"""Cleans the intro video (voice): denoises audio, normalises loudness, gently improves light/colour.
Usage: python process_intro.py input.mp4 intro_clean.mp4"""
import sys, subprocess, imageio_ffmpeg
src,dst=sys.argv[1],sys.argv[2]
af=("highpass=f=80,afftdn=nr=18:nf=-30:tn=1,"            # remove steady noise (hiss/hum/room)
    "lowpass=f=14000,acompressor=threshold=-21dB:ratio=3:attack=15:release=200,"
    "equalizer=f=250:t=q:w=1:g=-2,equalizer=f=3500:t=q:w=1:g=2,"   # clarity for voice
    "loudnorm=I=-16:TP=-1.5:LRA=9")
vf=("hqdn3d=2:2:3:3,"                                       # light video denoise
    "eq=brightness=0.04:contrast=1.08:saturation=1.08:gamma=1.06,"
    "unsharp=5:5:0.4")
subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-y','-i',src,'-vf',vf,'-af',af,'-c:v','libx264','-crf','16','-preset','slow',
                '-pix_fmt','yuv420p','-c:a','aac','-b:a','192k','-movflags','+faststart',dst],check=True)
