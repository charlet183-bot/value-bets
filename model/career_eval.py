"""Quelle façon d'estimer le service/retour prédit le mieux le match suivant ?
Mesure : erreur sur le % de points gagnés au service par chaque joueur dans le match (2024-2026 = test)."""
import pickle, numpy as np, pandas as pd, itertools, json
D = pickle.load(open("/home/claude/data/career.pkl", "rb")); K = D["K"]; I = {k: i for i, k in enumerate(K)}; R = D["rows"]
AVG_S = .64
yr = np.array([r["year"] for r in R]); test = yr >= 2024; train = (yr >= 2009) & (yr <= 2023)

def est_career(c, h, k_surf, m_prior, key):
    acc = c["w"][h]
    if key == "spw": num, den, prior = acc[I["sw"]], acc[I["sv"]], AVG_S
    else: num, den, prior = acc[I["rw"]], acc[I["rv"]], 1 - AVG_S
    base = (num + m_prior * prior) / (den + m_prior)
    s, t = c["surf"], c["tot"]
    if s and s[I["sv"]] > 0 and t[I["sv"]] > 0:
        if key == "spw": ds = s[I["sw"]] / s[I["sv"]] - t[I["sw"]] / t[I["sv"]]
        else: ds = (s[I["rw"]] / s[I["rv"]] - t[I["rw"]] / t[I["rv"]]) if s[I["rv"]] > 0 and t[I["rv"]] > 0 else 0
        ns = s[I["m"]]; base += ds * ns / (ns + k_surf)
    return base

def score(pa_hat, pb_hat, mask):
    ya = np.array([r["y_spwA"] for r in R]); yb = np.array([r["y_spwB"] for r in R])
    wa = np.array([r["svA"] for r in R]); wb = np.array([r["svB"] for r in R])
    e = (wa * (pa_hat - ya) ** 2 + wb * (pb_hat - yb) ** 2)[mask].sum() / (wa + wb)[mask].sum()
    return e

cur_pa = np.array([r["nA"]["spw"] - r["nB"]["rpw"] + 1 - AVG_S for r in R])
cur_pb = np.array([r["nB"]["spw"] - r["nA"]["rpw"] + 1 - AVG_S for r in R])
res = {"Actuel (20 derniers + 52 sem. surface)": {"train": score(cur_pa, cur_pb, train), "test": score(cur_pa, cur_pb, test)}}
best = None
for h, ks, mp in itertools.product(D["HL"], (3, 10, 30, 1e9), (0, 100, 300)):
    pa = np.array([est_career(r["cA"], h, ks, mp, "spw") - est_career(r["cB"], h, ks, mp, "rpw") + 1 - AVG_S for r in R])
    pb = np.array([est_career(r["cB"], h, ks, mp, "spw") - est_career(r["cA"], h, ks, mp, "rpw") + 1 - AVG_S for r in R])
    e = score(pa, pb, train)
    if best is None or e < best[0]: best = (e, h, ks, mp, pa, pb)
e, h, ks, mp, pa, pb = best
res[f"Carrière (demi-vie {h} an, surface k={ks}, a priori {mp} pts)"] = {"train": e, "test": score(pa, pb, test)}
# mélange carrière + forme récente
for a in (0, .1, .2, .3, .4, .5):
    qa, qb = a * cur_pa + (1 - a) * pa, a * cur_pb + (1 - a) * pb
    res[f"Mélange {int(a*100)} % récent / {int(100-a*100)} % carrière"] = {"train": score(qa, qb, train), "test": score(qa, qb, test)}
base = score(np.full(len(R), AVG_S), np.full(len(R), AVG_S), test)
print("Erreur (×10⁴) sur le % de points gagnés au service, plus bas = mieux ; « tout le monde à 64 % » =", round(base * 1e4, 2))
for k, v in res.items(): print(f"  {k:62s} entraînement {v['train']*1e4:6.2f}   test 2024-26 {v['test']*1e4:6.2f}")
json.dump({"best": {"h": h, "k_surf": ks, "prior": mp}, "res": res}, open("/home/claude/value-bets/model/career_eval.json", "w"), indent=1, default=float)
