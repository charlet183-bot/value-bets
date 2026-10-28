"""Réapprend les poids du vainqueur en remplaçant la stat service/retour (20 derniers matchs) par la version carrière."""
exec(open("variants.py").read().split("for lam in")[0].replace("# 1) grille","if False:\n  # 1) grille").replace("for C in [0.001","  for C in [0.001"))
import json
from sklearn.metrics import accuracy_score
S = pd.read_pickle("/home/claude/data/serve_season.pkl")
S["pw"] = np.where(S.flip, 1 - S.serve_new, S.serve_new)          # proba du vainqueur
S["key"] = pd.to_datetime(S.date).dt.strftime("%Y-%m-%d") + "|" + S.wid + "|" + S.lid
key = pd.to_datetime(d.date).dt.strftime("%Y-%m-%d") + "|" + d.A.astype(str) + "|" + d.B.astype(str)
m = key.map(dict(zip(S.key, S.pw)))
print("matchs reliés :", round(m.notna().mean(), 3))
fm = (year >= 2008) & (year <= 2023)
w0 = bounded(FEATS, fm, 30); p0 = 1 / (1 + np.exp(-(Xs.loc[test, FEATS].values @ w0)))
old_serve = Xs["serve"].copy()
newv = L(m.clip(.03, .97)).where(m.notna(), X["serve"])
Xs["serve"] = np.where(flip, -newv, newv)
w1 = bounded(FEATS, fm, 30); p1 = 1 / (1 + np.exp(-(Xs.loc[test, FEATS].values @ w1)))
res = {k: {"logloss": log_loss(y[test], p), "bon_sens": accuracy_score(y[test], p > .5)} for k, p in (("avant", p0), ("carrière", p1))}
print(res)
sd = Xs.loc[fm, FEATS].std(); infl = {f: abs(v) * sd[f] for f, v in zip(FEATS, w1)}; tot = sum(infl.values())
poids = {g: sum(infl[f] for f in cols) / tot for g, cols in GROUPS.items()}
w_all = bounded(FEATS, np.ones(len(year), bool), 30)
json.dump({"test": res, "coefs": dict(zip(FEATS, map(float, w_all))), "poids": poids}, open("learned_saison.json", "w"), indent=1, ensure_ascii=False, default=float)
for g in sorted(poids, key=lambda g: -poids[g]): print(f"  {g:36s} {poids[g]:.1%}")
print({k: round(v, 4) for k, v in zip(FEATS, w_all)})
