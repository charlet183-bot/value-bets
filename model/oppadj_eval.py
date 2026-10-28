"""Correction des stats de la saison selon la force des adversaires (log du classement adverse).
Exact : chaque match corrigé. Approché (faisable dans l'appli) : moyenne des ~21 derniers matchs de la saison."""
exec(open("career_eval.py").read().split("cur_pa = ")[0])
MP = 600
def season(c, key, cc, mode, r_n):
    y = c["y_cur"]
    if not y: return AVG_S if key == "spw" else 1 - AVG_S
    if key == "spw": num, den, lsum, prior = y[I["sw"]], y[I["sv"]], y[I["lo"]], AVG_S
    else: num, den, lsum, prior = y[I["rw"]], y[I["rv"]], y[I["lr"]], 1 - AVG_S
    if mode == "exact": num -= cc * lsum
    elif mode == "approx" and r_n["ml21"] is not None: num -= cc * r_n["ml21"] * den
    return (num + MP * prior) / (den + MP)
ys = lambda k: np.array([r[k] for r in R])
cur_pa = np.array([r["nA"]["spw"] - r["nB"]["rpw"] + 1 - AVG_S for r in R]); cur_pb = np.array([r["nB"]["spw"] - r["nA"]["rpw"] + 1 - AVG_S for r in R])
res = {}
for mode in ("exact", "approx"):
    for cc in (0, .005, .01, .015, .02, .03, .04):
        sa = np.array([season(r["cA"], "spw", cc, mode, r["nA"]) - season(r["cB"], "rpw", cc, mode, r["nB"]) for r in R])
        sb = np.array([season(r["cB"], "spw", cc, mode, r["nB"]) - season(r["cA"], "rpw", cc, mode, r["nA"]) for r in R])
        qa, qb = .5 * cur_pa + .5 * (sa + 1 - AVG_S), .5 * cur_pb + .5 * (sb + 1 - AVG_S)
        # constante recalée sur l'entraînement (la correction déplace la moyenne)
        k = np.mean(np.r_[ys("y_spwA")[train] - qa[train], ys("y_spwB")[train] - qb[train]])
        res[(mode, cc)] = (score(qa + k, qb + k, train), score(qa + k, qb + k, test), k)
        print(f"{mode:6s} c={cc:.3f}  entr. {res[(mode,cc)][0]*1e4:.2f}  test {res[(mode,cc)][1]*1e4:.2f}  constante {k:+.4f}")
mo = np.array([r["date"].month for r in R])
best = min((v[0], k) for k, v in res.items() if k[0] == "approx")[1]
print("meilleur approché :", best)
import json; json.dump({"best_approx": best[1], "res": {f"{k[0]}_{k[1]}": v for k, v in res.items()}}, open("oppadj_eval.json", "w"), indent=1)
