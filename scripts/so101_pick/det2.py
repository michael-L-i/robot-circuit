import cv2, numpy as np, sys
def blocks(img):
    s=img.shape[1]/720
    hsv=cv2.cvtColor(img,cv2.COLOR_BGR2HSV)
    dark=((hsv[...,2]<75)&(hsv[...,1]<100)).astype(np.uint8)*255
    dark=cv2.morphologyEx(dark,cv2.MORPH_CLOSE,np.ones((int(11*s),)*2,np.uint8))
    cs,_=cv2.findContours(dark,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE); out=[]
    for c in cs:
        (cx,cy),(w,h),ang=cv2.minAreaRect(c); L,S=max(w,h),min(w,h)
        if 85*s<L<170*s and 28*s<S<70*s and cv2.contourArea(c)>0.55*w*h: out.append(((cx,cy),(w,h),ang,cv2.boxPoints(((cx,cy),(w,h),ang))))
    return out
def copper_gap(img):
    hsv=cv2.cvtColor(img,cv2.COLOR_BGR2HSV)
    m=((hsv[...,0]>=3)&(hsv[...,0]<=22)&(hsv[...,1]>70)&(hsv[...,2]>110)).astype(np.uint8)
    m=cv2.morphologyEx(m,cv2.MORPH_OPEN,np.ones((5,5),np.uint8))
    n,lab,st,_=cv2.connectedComponentsWithStats(m)
    big=[i for i in range(1,n) if st[i,4]>1500]
    if not big: return None
    keep=np.isin(lab,big); ys,xs=np.nonzero(keep); x0,x1,y0,y1=xs.min(),xs.max(),ys.min(),ys.max()
    band=keep[y0:y0+int((y1-y0)*0.5),x0:x1+1].sum(0).astype(float)
    band=np.convolve(band,np.ones(5)/5,'same'); lo,hi=int(len(band)*.25),int(len(band)*.75)
    gx=x0+lo+int(np.argmin(band[lo:hi]))
    return gx,(x0,y0,x1,y1)
if __name__=='__main__':
    im=cv2.imread(sys.argv[1]); b=blocks(im); g=copper_gap(im); print([ (np.round(x[0]),np.round(x[1]),round(x[2])) for x in b], g)
    for x in b: cv2.drawContours(im,[np.int32(x[3])],0,(0,255,0),2)
    if g: cv2.line(im,(g[0],g[1][1]),(g[0],g[1][3]),(255,0,255),2); cv2.rectangle(im,g[1][:2],g[1][2:],(255,255,0),1)
    cv2.imwrite(sys.argv[2],im)
