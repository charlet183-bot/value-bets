"""Entraîne les poids de chaque stat (régression logistique sans constante, sur les différences A − B),
les teste sur des saisons jamais vues, et mesure l'apport de chaque groupe de stats."""
import json, math
import numpy as np, pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss, accuracy_score, brier_score_loss

d = pd.read_csv("/home/claude/data/features.csv")
d = d[(d.n_A >= 5) & (d.n_B >= 5)].copy()  # joueurs avec un minimum d'historique, comme dans l'appli

L = lambda p: np.log(np.clip(p, .03, .97) / (1 - np.clip(p, .03, .97)))
def diff_logit(a, b): return (L(d[a].fillna(.5)) - L(d[b].fillna(.5)))
def diff_raw(a, b): return (d[a] - d[b]).fillna(0)

X = pd.DataFrame(index=d.index)
X["elo"] = (d.elo_A - d.elo_B) * math.log(10) / 400
X["serve"] = L(d.serve_p.fillna(.5)).where(d.serve_p.notna(), 0)
X["form"] = diff_raw("perf_A", "perf_B")
X["trend"] = diff_raw("trend_A", "trend_B")
for k in ("bp", "tb", "dec", "cb", "surf", "lvl"): X[k] = diff_logit(f"{k}_A", f"{k}_B")
for k in ("fi", "fw", "sw", "df"): X[k] = diff_raw(f"{k}_A", f"{k}_B") * 10  # en dizaines de %
X["rank"] = np.log(d.rankB.fillna(500).clip(1, 2000)) - np.log(d.rankA.fillna(500).clip(1, 2000))
X["n14"] = d.n14_A.clip(0, 10) - d.n14_B.clip(0, 10)
X["lastmin"] = (d.lastMin_A.fillna(100).clip(0, 300) - d.lastMin_B.fillna(100).clip(0, 300)) / 60
X["rust35"] = (d.days_A.fillna(0) > 35).astype(int) - (d.days_B.fillna(0) > 35).astype(int)
X["rust60"] = (d.days_A.fillna(0) > 60).astype(int) - (d.days_B.fillna(0) > 60).astype(int)
X["h2h"] = (d.h2h_a - d.h2h_b) / (d.h2h_a + d.h2h_b + 2)
X["lefty"] = d.lefA - d.lefB
ageA, ageB = d.ageA.fillna(26), d.ageB.fillna(26)
X["age"] = ageA - ageB
X["age2"] = ((ageA - 26) ** 2 - (ageB - 26) ** 2) / 10
X["ht"] = (d.htA.fillna(186) - d.htB.fillna(186)) / 10

GROUPS = {
    "Elo sur la surface": ["elo"], "Service contre retour": ["serve"], "Forme (adversaires pris en compte)": ["form"],
    "Tendance": ["trend"], "Mental": ["bp", "tb", "dec", "cb"], "Détail du service": ["fi", "fw", "sw", "df"],
    "Bilan sur la surface": ["surf"], "Niveau du tournoi": ["lvl"], "Classement": ["rank"],
    "Fatigue et reprise": ["n14", "lastmin", "rust35", "rust60"], "Face-à-face": ["h2h"], "Physique (main, âge, taille)": ["lefty", "age", "age2", "ht"],
}
FEATS = [f for g in GROUPS.values() for f in g]

# orientation aléatoire : la moitié des lignes est inversée (A devient le perdant)
rng = np.random.default_rng(42)
flip = rng.random(len(d)) < .5
Xs = X.copy(); Xs[flip] = -Xs[flip]
y = (~flip).astype(int)
year = d.year.values

def fit(cols, mask, C=1.0):
    m = LogisticRegression(fit_intercept=False, C=C, max_iter=2000)
    m.fit(Xs.loc[mask, cols], y[mask]); return m
def evaluate(p, mask):
    return {"accuracy": accuracy_score(y[mask], p > .5), "logloss": log_loss(y[mask], p), "brier": brier_score_loss(y[mask], p)}

train = (year >= 2008) & (year <= 2022)
valid = year == 2023
test = (year >= 2024)

# régularisation choisie sur 2023
best_C = min([0.01, 0.03, 0.1, 0.3, 1, 3], key=lambda C: log_loss(y[valid], fit(FEATS, train, C).predict_proba(Xs.loc[valid, FEATS])[:, 1]))
fitmask = train | valid
full = fit(FEATS, fitmask, best_C)
res = {"C": best_C, "n_train": int(fitmask.sum()), "n_test": int(test.sum())}

# modèles de référence sur le test (2024-2026)
res["test"] = {
    "Classement seul": evaluate(fit(["rank"], fitmask).predict_proba(Xs.loc[test, ["rank"]])[:, 1], test),
    "Elo seul": evaluate(fit(["elo"], fitmask).predict_proba(Xs.loc[test, ["elo"]])[:, 1], test),
}
# calcul actuel de l'appli (poids faits main) : 45 % Elo, 35 % service/retour, 20 % forme + fatigue + face-à-face
t = Xs.loc[test]
p_elo = 1 / (1 + np.exp(-t.elo)); p_srv = 1 / (1 + np.exp(-t.serve)); p_form = 1 / (1 + np.exp(-3 * t.form))
base = .45 * L(p_elo) + .35 * L(p_srv) + .2 * L(p_form)
fat = -(.05 * np.clip(t.n14, -10, 10) * 0)  # malus sans équivalent direct : on garde la base + face-à-face
p_app = 1 / (1 + np.exp(-(base + .3 * t.h2h)))
res["test"]["Calcul actuel de l'appli"] = evaluate(p_app.values, test)
res["test"]["Nouveau modèle (toutes les stats)"] = evaluate(full.predict_proba(Xs.loc[test, FEATS])[:, 1], test)

# apport de chaque groupe : on le retire, on réentraîne, on regarde la perte sur le test
p_full = full.predict_proba(Xs.loc[test, FEATS])[:, 1]
ll_full = log_loss(y[test], p_full)
contrib = {}
for g, cols in GROUPS.items():
    keep = [f for f in FEATS if f not in cols]
    m = fit(keep, fitmask, best_C)
    p = m.predict_proba(Xs.loc[test, keep])[:, 1]
    contrib[g] = {"logloss_sans": log_loss(y[test], p), "gain": log_loss(y[test], p) - ll_full,
                  "accuracy_sans": accuracy_score(y[test], p > .5)}
res["apport"] = contrib

# poids = coefficient × écart-type de la stat (part de l'influence), et coefficients bruts pour l'appli
coefs = dict(zip(FEATS, full.coef_[0]))
sd = Xs.loc[fitmask, FEATS].std()
infl = {f: abs(coefs[f]) * sd[f] for f in FEATS}
tot = sum(infl.values())
res["poids_groupes"] = {g: sum(infl[f] for f in cols) / tot for g, cols in GROUPS.items()}
res["coefs"] = coefs

# calibration : quand le modèle dit 70 %, gagne-t-on 70 % du temps ?
bins = pd.cut(p_full, [0, .2, .35, .5, .65, .8, 1])
cal = pd.DataFrame({"p": p_full, "y": y[test], "b": bins}).groupby("b", observed=True).agg(pred=("p", "mean"), reel=("y", "mean"), n=("y", "size"))
res["calibration"] = cal.round(3).reset_index().astype(str).to_dict("records")

# modèle final pour l'appli : entraîné sur tout (2008-2026)
final = fit(FEATS, np.ones(len(year), bool), best_C)
res["coefs_final"] = dict(zip(FEATS, final.coef_[0]))
json.dump(res, open("/home/claude/data/model.json", "w"), indent=1, ensure_ascii=False, default=float)

print("C =", best_C, "| entraînement :", res["n_train"], "matchs | test 2024-26 :", res["n_test"])
for k, v in res["test"].items(): print(f"{k:38s} réussite {v['accuracy']:.1%}  logloss {v['logloss']:.4f}  brier {v['brier']:.4f}")
print("\nApport de chaque groupe (perte si on le retire, en logloss ×1000) et poids :")
for g in sorted(GROUPS, key=lambda g: -contrib[g]["gain"]):
    print(f"  {g:38s} apport {contrib[g]['gain']*1000:+6.2f}   poids {res['poids_groupes'][g]:.1%}")
print("\nCoefficients finaux :", {k: round(v, 3) for k, v in res["coefs_final"].items()})
print("\nCalibration :"); print(cal.round(3))
