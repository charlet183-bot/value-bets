exec(open("variants.py").read().split("for lam in")[0].replace("# 1) grille","if False:\n  # 1) grille").replace("for C in [0.001","  for C in [0.001"))
import json
from sklearn.metrics import accuracy_score, brier_score_loss
fm=(year>=2008)&(year<=2023)
w_tr=bounded(FEATS,fm,30); p=1/(1+np.exp(-(Xs.loc[test,FEATS].values@w_tr)))
res=json.load(open("model.json"))
res["test"]["Nouveau modèle, signes imposés"]={"accuracy":accuracy_score(y[test],p>.5),"logloss":log_loss(y[test],p),"brier":brier_score_loss(y[test],p)}
# apport de chaque groupe dans la version finale
ll=log_loss(y[test],p);app={}
for g,cols in GROUPS.items():
    keep=[f for f in FEATS if f not in cols];w=bounded(keep,fm,30);pp=1/(1+np.exp(-(Xs.loc[test,keep].values@w)))
    app[g]={"gain":log_loss(y[test],pp)-ll,"acc_sans":accuracy_score(y[test],pp>.5)}
sd=Xs.loc[fm,FEATS].std();infl={f:abs(v)*sd[f] for f,v in zip(FEATS,w_tr)};tot=sum(infl.values())
poids={g:sum(infl[f] for f in cols)/tot for g,cols in GROUPS.items()}
w_all=bounded(FEATS,np.ones(len(year),bool),30)
res["final"]={"coefs":dict(zip(FEATS,map(float,w_all))),"poids":poids,"apport":app}
json.dump(res,open("model.json","w"),indent=1,ensure_ascii=False,default=float)
print("test :",res["test"]["Nouveau modèle, signes imposés"])
for g in sorted(GROUPS,key=lambda g:-poids[g]):print(f"  {g:38s} poids {poids[g]:6.1%}  apport {app[g]['gain']*1000:+6.2f}")
print({k:round(v,4) for k,v in res["final"]["coefs"].items()})
