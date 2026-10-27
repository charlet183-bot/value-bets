"""Compare l'ancien et le nouveau calcul des jeux/aces sur l'historique, puis apprend une petite correction."""
import json, math
import numpy as np, pandas as pd
from functools import lru_cache
from scipy.optimize import minimize
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss, brier_score_loss
exec(open("/home/claude/data/games.py").read().split("# ---------- chargement et boucle")[0])

d = pd.read_csv("/home/claude/data/games.csv")
d = d[(d.total >= 12)].reset_index(drop=True)  # matchs terminés normalement

@lru_cache(maxsize=None)
def dists(ha, hb, ptb, bo5):
    first, final = match_dist(ha, hb, ptb, bool(bo5))
    tot = defaultdict(float); ga = defaultdict(float)
    for (a, b), p in final.items(): tot[a + b] += p; ga[a] += p
    return first, tot, ga
def cdf_over(dist, L): return sum(p for g, p in dist.items() if g > L)
def mean(dist): return sum(g * p for g, p in dist.items())

R = []
for r in d.itertuples():
    pa, pb = round(r.pa, 3), round(r.pb, 3)
    nh = (round(hold_p(pa), 3), round(hold_p(pb), 3), round(tb_p(pa, pb), 3))
    oh = (round(r.ha_old, 3), round(r.hb_old, 3)); oh = oh + (round(ptb_heuristic(*oh), 3),)
    f_new, t_new, g_new = dists(*nh, r.bo5)
    f_old, t_old, g_old = dists(*oh, r.bo5)
    E_new, E_old, EA_new = mean(t_new), mean(t_old), mean(g_new)
    hist = [x for x in (r.s1hist_A, r.s1hist_B) if not pd.isna(x)]
    s1_old_model = cdf_over(f_old, 9.5)
    s1_old = (s1_old_model + sum(hist) / len(hist)) / 2 if len(hist) == 2 else s1_old_model
    row = {"year": r.year, "bo5": r.bo5, "surface": r.surface, "elo_diff": r.elo_diff,
           "s1_y": int(r.set1 >= 10), "s1_old": s1_old, "s1_new": cdf_over(f_new, 9.5),
           "E_new": E_new, "E_old": E_old, "total": r.total, "EA_new": EA_new, "gamesA": r.gamesA,
           "pa": pa, "pb": pb}
    base = math.floor(E_new) + .5
    for j, off in enumerate((-2, 0, 2)):
        L = base + off; row[f"t{j}_L"] = L; row[f"t{j}_y"] = int(r.total > L)
        row[f"t{j}_new"] = cdf_over(t_new, L); row[f"t{j}_old"] = cdf_over(t_old, L)
    baseA = math.floor(EA_new) + .5
    for j, off in enumerate((-1, 0, 1)):
        L = baseA + off; row[f"g{j}_y"] = int(r.gamesA > L); row[f"g{j}_new"] = cdf_over(g_new, L)
        row[f"g{j}_old"] = cdf_over(g_old, L)
    # aces : ancien = aces par jeu de service × la moitié des jeux ; nouveau = taux d'aces × points servis attendus
    if not pd.isna(r.acesA) and not pd.isna(r.aceA):
        row["ace_y"] = r.acesA
        row["ace_old"] = r.aceA_raw * 6.3 * E_old / 2
        row["ace_new"] = r.aceA * (E_new / 2) * pts_per_game(pa)
        row["rpwB"] = r.rpwB
    R.append(row)
X = pd.DataFrame(R)
train, test = X.year <= 2023, X.year >= 2024
res = {"n_train": int(train.sum()), "n_test": int(test.sum())}
clip = lambda p: np.clip(p, .01, .99)
L_ = lambda p: np.log(clip(p) / (1 - clip(p)))

def calib(prefix_list, name):
    """Correction logistique : logit(p_new), 5 sets, surface. Apprise sur 2008-2023, testée sur 2024-2026."""
    def stack(mask):
        parts = []
        for pfx in prefix_list:
            sub = X[mask]
            parts.append(pd.DataFrame({"lp": L_(sub[pfx + "_new"]), "bo5": sub.bo5, "clay": (sub.surface == "Clay").astype(int),
                                       "grass": (sub.surface == "Grass").astype(int), "y": sub[pfx + "_y"],
                                       "old": sub[pfx + "_old"], "new": sub[pfx + "_new"]}))
        return pd.concat(parts)
    tr, te = stack(train), stack(test)
    cols = ["lp", "bo5", "clay", "grass"]
    m = LogisticRegression(C=10, max_iter=1000).fit(tr[cols], tr.y)
    p_cal = m.predict_proba(te[cols])[:, 1]
    out = {}
    for lab, p in (("ancien calcul", te.old), ("nouveau (brut)", te.new), ("nouveau corrigé", p_cal)):
        out[lab] = {"logloss": log_loss(te.y, clip(p)), "brier": brier_score_loss(te.y, clip(p)), "precision": float(((p > .5) == te.y).mean())}
    out["coef"] = dict(zip(["intercept"] + cols, [float(m.intercept_[0])] + list(map(float, m.coef_[0]))))
    bins = pd.cut(p_cal, [0, .3, .45, .55, .7, 1])
    out["calibration"] = pd.DataFrame({"p": p_cal, "y": te.y.values, "b": bins}).groupby("b", observed=True).agg(prevu=("p", "mean"), reel=("y", "mean"), n=("y", "size")).round(3).reset_index().astype(str).to_dict("records")
    res[name] = out
    print(f"\n== {name} ==")
    for lab in ("ancien calcul", "nouveau (brut)", "nouveau corrigé"):
        v = out[lab]; print(f"  {lab:18s} logloss {v['logloss']:.4f}  brier {v['brier']:.4f}  bon sens {v['precision']:.1%}")
    print("  coefs", {k: round(v, 3) for k, v in out["coef"].items()})
    print("  calibration", out["calibration"])

calib(["s1"], "1er set à 10 jeux ou plus")
calib(["t0", "t1", "t2"], "Total de jeux du match")
calib(["g0", "g1", "g2"], "Jeux gagnés par un joueur")

# total attendu : erreur moyenne
for lab, col in (("ancien", "E_old"), ("nouveau", "E_new")):
    print(f"Total de jeux, erreur moyenne {lab} : {np.mean(np.abs(X.loc[test, col] - X.loc[test, 'total'])):.2f} jeux, biais {np.mean(X.loc[test, col] - X.loc[test, 'total']):+.2f}")
res["total_mae"] = {lab: float(np.mean(np.abs(X.loc[test, col] - X.loc[test, "total"]))) for lab, col in (("ancien", "E_old"), ("nouveau", "E_new"))}

# aces : correction log-linéaire (multiplicateur + retour adverse + 5 sets), Poisson
A = X.dropna(subset=["ace_y", "ace_new"]); A = A[A.ace_new > 0]
atr, ate = A[A.year <= 2023], A[A.year >= 2024]
def mu(b, D): return D.ace_new * np.exp(b[0] + b[1] * (D.rpwB - .36) * 10 + b[2] * D.bo5)
def nll(b, D): m = mu(b, D); return float(np.mean(m - D.ace_y * np.log(m + 1e-9)))
b = minimize(lambda b: nll(b, atr), np.zeros(3)).x
def dev(m, D): y = D.ace_y; return float(np.mean(2 * (np.where(y > 0, y * np.log(np.maximum(y, 1e-9) / m), 0) - (y - m))))
res["aces"] = {"coef": list(map(float, b)),
               "mae_ancien": float(np.mean(np.abs(ate.ace_old - ate.ace_y))), "mae_nouveau": float(np.mean(np.abs(ate.ace_new - ate.ace_y))),
               "mae_corrige": float(np.mean(np.abs(mu(b, ate) - ate.ace_y))),
               "dev_ancien": dev(np.maximum(ate.ace_old, .05), ate), "dev_corrige": dev(mu(b, ate), ate)}
print("\n== Aces ==", {k: (round(v, 3) if isinstance(v, float) else [round(x, 3) for x in v]) for k, v in res["aces"].items()})
json.dump(res, open("/home/claude/data/games_model.json", "w"), indent=1, ensure_ascii=False, default=float)
