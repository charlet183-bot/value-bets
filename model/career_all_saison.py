"""Tous les calculs avec toute la carrière : vainqueur (stat service/retour), total de jeux, jeux par joueur, aces.
Compare avec l'appli actuelle (20 derniers matchs) sur 2024-2026, puis donne les nouveaux coefficients."""
import pickle, json, math, sys
import numpy as np, pandas as pd
from functools import lru_cache
from scipy.optimize import minimize
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss
exec(open("/home/claude/data/games.py").read().split("# ---------- chargement et boucle")[0])

D = pickle.load(open("/home/claude/data/career.pkl", "rb")); K = D["K"]; I = {k: i for i, k in enumerate(K)}; R = D["rows"]
P = json.load(open("/home/claude/value-bets/model/career_eval.json"))["best"]; H, KS, MP, AVG_S, MIX = P["h"], P["k_surf"], P["prior"], .64, .5
def est(c, key):
    y = c["y_cur"]; mp = 600
    if key == "spw": return ((y[I["sw"]] if y else 0) + mp * AVG_S) / ((y[I["sv"]] if y else 0) + mp)
    return ((y[I["rw"]] if y else 0) + mp * (1 - AVG_S)) / ((y[I["rv"]] if y else 0) + mp)
def est_career_unused(c, key):
    acc = c["w"][H]
    num, den, prior = (acc[I["sw"]], acc[I["sv"]], AVG_S) if key == "spw" else (acc[I["rw"]], acc[I["rv"]], 1 - AVG_S)
    base = (num + MP * prior) / (den + MP); s, t = c["surf"], c["tot"]
    if s and s[I["sv"]] > 0 and s[I["rv"]] > 0:
        ds = (s[I["sw"]] / s[I["sv"]] - t[I["sw"]] / t[I["sv"]]) if key == "spw" else (s[I["rw"]] / s[I["rv"]] - t[I["rw"]] / t[I["rv"]])
        base += ds * s[I["m"]] / (s[I["m"]] + KS)
    return base
def ace_rate(c, mp=600, prior=.07):
    acc = c["y_cur"] or [0.0] * len(K); return (acc[I["ace"]] + mp * prior) / (acc[I["sv"]] + mp)
cl = lambda x: min(.85, max(.35, x))

@lru_cache(maxsize=None)
def dists(pa, pb, bo5):
    ha, hb = hold_p(pa), hold_p(pb)
    first, final = match_dist(round(ha, 3), round(hb, 3), round(tb_p(pa, pb), 3), bool(bo5))
    tot = defaultdict(float); ga = defaultdict(float)
    for (a, b), p in final.items(): tot[a + b] += p; ga[a] += p
    return dict(tot), dict(ga)
over = lambda d, L: sum(p for g, p in d.items() if g > L)
mean = lambda d: sum(g * p for g, p in d.items())

rows = []
for n, r in enumerate(R):
    sA = MIX * r["nA"]["spw"] + (1 - MIX) * est(r["cA"], "spw"); sB = MIX * r["nB"]["spw"] + (1 - MIX) * est(r["cB"], "spw")
    rA = MIX * r["nA"]["rpw"] + (1 - MIX) * est(r["cA"], "rpw"); rB = MIX * r["nB"]["rpw"] + (1 - MIX) * est(r["cB"], "rpw")
    pa, pb = round(cl(sA - rB + 1 - AVG_S), 3), round(cl(sB - rA + 1 - AVG_S), 3)
    oa, ob = round(cl(r["nA"]["spw"] - r["nB"]["rpw"] + 1 - AVG_S), 3), round(cl(r["nB"]["spw"] - r["nA"]["rpw"] + 1 - AVG_S), 3)
    tn, gn = dists(pa, pb, r["bo5"]); to, go = dists(oa, ob, r["bo5"])
    # vainqueur d'après le service/retour
    sn = serve_model(sA, rA, sB, rB, bool(r["bo5"]))
    so = serve_model(r["nA"]["spw"], r["nA"]["rpw"], r["nB"]["spw"], r["nB"]["rpw"], bool(r["bo5"]))
    row = {"year": r["year"], "date": r["date"], "bo5": r["bo5"], "surface": r["surface"], "winA": r["winA"], "flip": r["flip"],
           "wid": r["wid"], "lid": r["lid"], "serve_new": sn, "serve_old": so, "total": r["total"], "gamesA": r["gamesA"],
           "E_new": mean(tn), "E_old": mean(to), "pa": pa, "rpwB_new": rB, "rpwB_old": r["nB"]["rpw"],
           "acesA": r["acesA"], "ace_new": (MIX * r["nA"]["ace"] + (1 - MIX) * ace_rate(r["cA"])) * (mean(tn) / 2) * pts_per_game(pa),
           "ace_old": r["nA"]["ace"] * (mean(to) / 2) * pts_per_game(oa)}
    base = math.floor(row["E_new"]) + .5
    for j, off in enumerate((-2, 0, 2)):
        L = base + off; row[f"t{j}_y"] = int(r["total"] > L); row[f"t{j}_new"] = over(tn, L); row[f"t{j}_old"] = over(to, L)
    baseA = math.floor(mean(gn)) + .5
    for j, off in enumerate((-1, 0, 1)):
        L = baseA + off; row[f"g{j}_y"] = int(r["gamesA"] > L); row[f"g{j}_new"] = over(gn, L); row[f"g{j}_old"] = over(go, L)
    rows.append(row)
    if n % 5000 == 0: print(n, file=sys.stderr)
X = pd.DataFrame(rows); train, test = (X.year >= 2009) & (X.year <= 2023), X.year >= 2024
clip = lambda p: np.clip(p, .01, .99); L_ = lambda p: np.log(clip(p) / (1 - clip(p)))
OUT = {}
OLD_GCAL = {"total": {"intercept": -0.3443, "lp": 0.667, "bo5": -0.1184, "clay": 0.0623, "grass": 0.0842},
            "games": {"intercept": -0.213, "lp": 0.851, "bo5": -0.1834, "clay": 0.0876, "grass": 0.0905}}
def stack(mask, pfx_list, which):
    parts = []
    for pfx in pfx_list:
        s = X[mask]
        parts.append(pd.DataFrame({"lp": L_(s[f"{pfx}_{which}"]), "bo5": s.bo5, "clay": (s.surface == "Clay").astype(int),
                                   "grass": (s.surface == "Grass").astype(int), "y": s[f"{pfx}_y"]}))
    return pd.concat(parts)
cols = ["lp", "bo5", "clay", "grass"]
for kind, pfx in (("total", ["t0", "t1", "t2"]), ("games", ["g0", "g1", "g2"])):
    trn, ten, teo = stack(train, pfx, "new"), stack(test, pfx, "new"), stack(test, pfx, "old")
    m = LogisticRegression(C=10, max_iter=1000).fit(trn[cols], trn.y); pn = m.predict_proba(ten[cols])[:, 1]
    c = OLD_GCAL[kind]; po = 1 / (1 + np.exp(-(c["intercept"] + c["lp"] * teo.lp + c["bo5"] * teo.bo5 + c["clay"] * teo.clay + c["grass"] * teo.grass)))
    full = stack(train | test, pfx, "new"); mf = LogisticRegression(C=10, max_iter=1000).fit(full[cols], full.y)
    OUT[kind] = {"appli_actuelle": {"logloss": log_loss(teo.y, clip(po)), "bon_sens": float(((po > .5) == teo.y).mean())},
                 "nouveau": {"logloss": log_loss(ten.y, clip(pn)), "bon_sens": float(((pn > .5) == ten.y).mean())},
                 "coef": dict(zip(["intercept"] + cols, [float(mf.intercept_[0])] + list(map(float, mf.coef_[0]))))}
te = X[test]
OUT["total_erreur_moy"] = {"appli_actuelle": float(np.mean(np.abs(te.E_old - 0.9 - te.total))), "nouveau_brut": float(np.mean(np.abs(te.E_new - te.total))),
                           "biais_nouveau": float(np.mean(te.E_new - te.total))}
# aces : même correction log-linéaire que l'appli (multiplicateur, retour adverse, 5 sets), réapprise
A = X[X.ace_new > 0]; atr, ate = A[A.year <= 2023], A[A.year >= 2024]
def mu(b, Dd, col, rp): return Dd[col] * np.exp(b[0] + b[1] * (Dd[rp] - .36) * 10 + b[2] * Dd.bo5)
def nll(b, Dd, col, rp): m = mu(b, Dd, col, rp); return float(np.mean(m - Dd.acesA * np.log(m + 1e-9)))
OLD_ACE = [0.0062, -0.3236, 0.0072]
bn = minimize(lambda b: nll(b, atr, "ace_new", "rpwB_new"), np.zeros(3)).x
OUT["aces"] = {"appli_actuelle_mae": float(np.mean(np.abs(mu(OLD_ACE, ate, "ace_old", "rpwB_old") - ate.acesA))),
               "nouveau_mae": float(np.mean(np.abs(mu(bn, ate, "ace_new", "rpwB_new") - ate.acesA))),
               "coef": list(map(float, minimize(lambda b: nll(b, A, "ace_new", "rpwB_new"), np.zeros(3)).x))}
# vainqueur : la stat service/retour seule
OUT["vainqueur_service_seul"] = {k: {"logloss": log_loss(te.winA, clip(te[c])), "bon_sens": float(((te[c] > .5) == te.winA).mean())}
                                 for k, c in (("appli_actuelle", "serve_old"), ("nouveau", "serve_new"))}
X[["date", "wid", "lid", "flip", "serve_new"]].to_pickle("/home/claude/data/serve_season.pkl")
json.dump(OUT, open("/home/claude/value-bets/model/season_all.json", "w"), indent=1, default=float)
print(json.dumps(OUT, indent=1, default=lambda x: round(float(x), 4)))
