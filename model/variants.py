exec(open("train.py").read().split("# régularisation choisie")[0])
from scipy.optimize import minimize
from sklearn.metrics import log_loss
fm=(year>=2008)&(year<=2023)
# 1) grille de régularisation plus large
for C in [0.001,0.003,0.01,0.03]:
    m=fit(FEATS,fm,C);p=m.predict_proba(Xs.loc[test,FEATS])[:,1]
    print("C",C,"test logloss %.4f acc %.3f"%(log_loss(y[test],p),((p>.5)==y[test]).mean()))
# 2) signes imposés : une stat « meilleure » ne peut pas faire baisser la chance
POS=["elo","serve","form","trend","bp","tb","dec","cb","fi","fw","sw","surf","lvl","rank","h2h"]
NEG=["df","n14","lastmin","rust35","rust60"]
def bounded(cols,mask,lam=1.0):
    Xm=Xs.loc[mask,cols].values;ym=y[mask]
    def f(w):
        z=Xm@w;pz=1/(1+np.exp(-z));eps=1e-9
        ll=-np.mean(ym*np.log(pz+eps)+(1-ym)*np.log(1-pz+eps))+lam*np.sum(w*w)/len(ym)
        g=Xm.T@(pz-ym)/len(ym)+2*lam*w/len(ym);return ll,g
    b=[(0,None) if c in POS else (None,0) if c in NEG else (None,None) for c in cols]
    r=minimize(f,np.zeros(len(cols)),jac=True,bounds=b,method="L-BFGS-B");return r.x
for lam in [1,30,100]:
    w=bounded(FEATS,fm,lam);p=1/(1+np.exp(-(Xs.loc[test,FEATS].values@w)))
    print("signes imposés lam",lam,"logloss %.4f acc %.3f"%(log_loss(y[test],p),((p>.5)==y[test]).mean()))
    print({f:round(v,3) for f,v in zip(FEATS,w) if abs(v)>1e-4})
# 3) corrélations utiles
print(Xs.loc[fm,["elo","serve","rank","bp","tb","dec","surf","age","form","trend"]].corr().round(2))
