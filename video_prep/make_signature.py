"""Cuts the artist signature out of the painting -> signature.png (RGBA, light cream ink, transparent bg)."""
import cv2, numpy as np
o=cv2.imread('original.jpg'); c=o[3100:3493,40:420].astype(np.float32)
L=c.mean(2)
bgL=cv2.GaussianBlur(cv2.morphologyEx(L,cv2.MORPH_CLOSE,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(71,71))),(0,0),15)
d=bgL-L                                            # how much darker than the paper
a=np.clip((d-22)/(85-22),0,1); a[:25]=0; a[-25:]=0; a[:,:25]=0; a[:,-25:]=0
a[:60,:]*=1                                        # keep everything; tiny white speck removed below
spk=cv2.morphologyEx((a>0.3).astype(np.uint8),cv2.MORPH_OPEN,np.ones((3,3),np.uint8))
n,lab,st,_=cv2.connectedComponentsWithStats(spk)
for i in range(1,n):
    if st[i,4]<400: a[lab==i]=0
ys,xs=np.where(a>0.05); p=12
y0,y1,x0,x1=ys.min()-p,ys.max()+p,xs.min()-p,xs.max()+p
a=a[y0:y1,x0:x1]; a=cv2.resize(a,None,fx=2,fy=2,interpolation=cv2.INTER_CUBIC).clip(0,1)
ink=np.array([196,222,238],np.float32)             # BGR warm cream
rgba=np.dstack([np.full(a.shape+(3,),ink),a*255]).astype(np.uint8)
cv2.imwrite('signature.png',rgba); print(rgba.shape)
prev=(np.full(a.shape+(3,),0,np.float32)*(1-a[...,None])+ink*a[...,None]).astype(np.uint8)
cv2.imwrite('work/sig_preview.png',prev)
