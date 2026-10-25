import numpy as np
R=np.array([(0.28,0.04),(0.27,-0.05),(0.23,0.08),(0.23,-0.02),(0.25,0.10)])
P=np.array([(220,560),(248,382),(315,660),(322,440),(280,690)],float)
A=np.c_[P,np.ones(len(P))]; M,res,_,_=np.linalg.lstsq(A,R,rcond=None)   # pixel -> robot
def px2robot(u,v): return np.array([u,v,1.0])@M
if __name__=='__main__':
    print('residual mm', np.round((A@M-R)*1000,1))
    for name,p in [('socket',(255,650)),('copper gap',(402,478))]: print(name, np.round(px2robot(*p),3))
