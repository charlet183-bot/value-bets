"""Nombre de jeux du 1er set : distribution complète (6, 7, 8, 9, 10, 12, 13 jeux), pour toutes les lignes.
Compare l'appli actuelle, le modèle point par point nourri par toute la carrière, et ce modèle corrigé
par ce qu'on sait en plus (habitudes des joueurs au 1er set sur toute la carrière, écart de niveau, cote Pinnacle).
Entraînement 2009-2023, test 2024-2026."""
import pickle, json, math, re, unicodedata, sys
import numpy as np, pandas as pd
from functools import lru_cache
from scipy.optimize import minimize
exec(open("/home/claude/data/features.py").read().split("# ---------- chargement")[0])

D = pickle.load(open("/home/claude/data/career.pkl", "rb")); K = D["K"]; I = {k: i for i, k in enumerate(K)}; R = D["rows"]
P = json.load(open("/home/claude/value-bets/model/career_eval.json"))["best"]
H, KS, MP, AVG_S, MIX = P["h"], P["k_surf"], P["prior"], .64, .3
VALS = [6, 7, 8, 9, 10, 12, 13]
LINES = [6.5, 7.5, 8.5, 9.5, 10.5, 12.5]

def est(c, key):
    acc = c["w"][H]
    num, den, prior = (acc[I["sw"]], acc[I["sv"]], AVG_S) if key == "spw" else (acc[I["rw"]], acc[I["rv"]], 1 - AVG_S)
    base = (num + MP * prior) / (den + MP)
    s, t = c["surf"], c["tot"]
    if s and s[I["sv"]] > 0 and s[I["rv"]] > 0:
        ds = (s[I["sw"]] / s[I["sv"]] - t[I["sw"]] / t[I["sv"]]) if key == "spw" else (s[I["rw"]] / s[I["rv"]] - t[I["rw"]] / t[I["rv"]])
        base += ds * s[I["m"]] / (s[I["m"]] + KS)
    return base

@lru_cache(maxsize=None)
def set1_dist(pa, pb):
    ha, hb, ptb = hold_p(pa), hold_p(pb), tb_p(pa, pb)
    out = defaultdict(float)
    for a_starts in (True, False):
        Pm = {(0, 0): .5}
        for k in range(13):
            nx = defaultdict(float)
            for (a, b), pr in Pm.items():
                if a == 6 and b == 6: out[13] += pr; continue
                ph = ha if ((k % 2 == 0) == a_starts) else 1 - hb
                for na, nb, q in ((a + 1, b, ph), (a, b + 1, 1 - ph)):
                    if (na >= 6 or nb >= 6) and abs(na - nb) >= 2: out[na + nb] += pr * q
                    else: nx[(na, nb)] += pr * q
            Pm = nx
            if not Pm: break
    return tuple(out.get(v, 0.0) for v in VALS)

cl = lambda x: min(.85, max(.35, x))
rows = []
for r in R:
    sA, rA, sB, rB = est(r["cA"], "spw"), est(r["cA"], "rpw"), est(r["cB"], "spw"), est(r["cB"], "rpw")
    sA, sB = MIX * r["nA"]["spw"] + (1 - MIX) * sA, MIX * r["nB"]["spw"] + (1 - MIX) * sB
    rA, rB = MIX * r["nA"]["rpw"] + (1 - MIX) * rA, MIX * r["nB"]["rpw"] + (1 - MIX) * rB
    pa, pb = round(cl(sA - rB + 1 - AVG_S), 3), round(cl(sB - rA + 1 - AVG_S), 3)
    oa = round(cl(r["nA"]["spw"] - r["nB"]["rpw"] + 1 - AVG_S), 3); ob = round(cl(r["nB"]["spw"] - r["nA"]["rpw"] + 1 - AVG_S), 3)
    # habitudes au 1er set sur toute la carrière (pondérées par la demi-vie) et sur les 21 derniers matchs
    def s1(c):
        a = c["w"][H]; n = a[I["s1n"]]
        return ((a[I["s1o"]] + 5 * .5) / (n + 5), (a[I["s1g"]] + 5 * 9.6) / (n + 5),
                (a[I["gw"]] + a[I["gl"]] + 5 * 9.6 * 2.4) / (a[I["st"]] + 5 * 2.4), (a[I["tbn"]] + 5 * .2) / (a[I["st"]] + 5))
    a1, b1 = s1(r["cA"]), s1(r["cB"])
    rows.append({"year": r["year"], "date": r["date"], "surface": r["surface"], "bo5": r["bo5"], "wname": r["wname"], "lname": r["lname"], "flip": r["flip"],
                 "new": set1_dist(pa, pb), "old": set1_dist(oa, ob), "set1": r["set1"],
                 "s1o": a1[0] + b1[0] - 1, "s1g": (a1[1] + b1[1]) / 2 - 9.6, "gps": (a1[2] + b1[2]) / 2 - 9.6, "tbr": a1[3] + b1[3] - .4,
                 "recent_s1o": ((r["nA"]["s1o_recent"] or .5) + (r["nB"]["s1o_recent"] or .5)) - 1,
                 "aelo": abs(r["elo_diff"]) / 400})
X = pd.DataFrame(rows)
print("matchs :", len(X), file=sys.stderr)

# ---------- cotes Pinnacle (tennis-data), pour l'écart de niveau vu par le marché
norm = lambda s: re.sub(r"[^a-z]", "", unicodedata.normalize("NFD", str(s)).encode("ascii", "ignore").decode().lower())
O = pd.read_pickle("/home/claude/data/odds/all.pkl"); O = O[O.PSW.notna() & O.PSL.notna()]
def tkey(n):
    p = str(n).strip().split(); return (norm(" ".join(p[:-1]) if len(p) > 1 else p[0]), p[-1][:1].lower() if len(p) > 1 else "")
idx = defaultdict(list)
for t in O.itertuples(): idx[(tkey(t.Winner)[0], tkey(t.Loser)[0])].append(t)
def fkey(full):
    parts = str(full).split(); return parts
pin = []
for r in X.itertuples():
    wn, ln = norm(r.wname), norm(r.lname); found = None
    for (kw, kl), lst in ((k, v) for k, v in ()):
        pass
    # surnoms tennis-data = fin du nom complet ; on essaie les 1 à 3 derniers mots
    wp, lp = str(r.wname).split(), str(r.lname).split()
    for i in range(1, 4):
        for j in range(1, 4):
            lst = idx.get((norm(" ".join(wp[-i:])), norm(" ".join(lp[-j:]))))
            if lst:
                for t in lst:
                    dd = (t.Date - pd.Timestamp(r.date)).days
                    if 0 <= dd <= 16: found = t; break
            if found: break
        if found: break
    if found:
        iw, il = 1 / found.PSW, 1 / found.PSL; pw = iw / (iw + il)
        pin.append(abs(pw - .5) * 2)
    else: pin.append(np.nan)
X["pin_gap"] = pin
print("cotes reliées :", X.pin_gap.notna().mean().round(3), file=sys.stderr)

train, test = (X.year >= 2009) & (X.year <= 2023), X.year >= 2024
L = lambda p: np.log(np.clip(p, 1e-4, 1 - 1e-4) / (1 - np.clip(p, 1e-4, 1 - 1e-4)))
def cdf_over(dist, li): return np.array([sum(p for v, p in zip(VALS, d) if v > LINES[li]) for d in dist])
GCAL = {"intercept": -0.0084, "lp": 0.6759, "bo5": -0.0866, "clay": -0.0023, "grass": 0.1112}
def app_now(sub, li):
    p = cdf_over(sub.old, li)
    z = GCAL["intercept"] + GCAL["lp"] * L(p) + GCAL["bo5"] * sub.bo5 + GCAL["clay"] * (sub.surface == "Clay") + GCAL["grass"] * (sub.surface == "Grass")
    return 1 / (1 + np.exp(-z))

FEATS = {"base": [], "+habitudes carrière": ["s1o", "gps", "tbr"], "+habitudes +écart Elo": ["s1o", "gps", "tbr", "aelo"],
         "+habitudes +Elo +Pinnacle": ["s1o", "gps", "tbr", "aelo", "pin_gap"]}
def design(sub, li, cols):
    p = cdf_over(sub["new"], li)
    M = [L(p), sub.bo5.values, (sub.surface == "Clay").values, (sub.surface == "Grass").values]
    M += [sub[c].fillna(0).values for c in cols]
    return np.column_stack(M).astype(float)

def fit(cols, mask):
    """Modèle ordinal : P(jeux > ligne) = σ(a_ligne + b·logit(p_modèle) + c·x), mêmes coefficients pour toutes les lignes."""
    sub = X[mask]; Ms = [design(sub, li, cols) for li in range(len(LINES))]
    ys = [(sub.set1.values > LINES[li]).astype(float) for li in range(len(LINES))]
    nf = Ms[0].shape[1]
    def nll(th):
        a, b = th[:len(LINES)], th[len(LINES):]
        tot = 0
        for li in range(len(LINES)):
            z = a[li] + Ms[li] @ b; p = 1 / (1 + np.exp(-z)); p = np.clip(p, 1e-6, 1 - 1e-6)
            tot -= np.sum(ys[li] * np.log(p) + (1 - ys[li]) * np.log(1 - p))
        return tot / len(sub) + 1e-3 * np.sum(b[4:] ** 2)
    th0 = np.zeros(len(LINES) + nf); th0[len(LINES)] = 1
    return minimize(nll, th0, method="L-BFGS-B").x

def predict(th, sub, cols):
    out = []
    for li in range(len(LINES)):
        z = th[li] + design(sub, li, cols) @ th[len(LINES):]; out.append(1 / (1 + np.exp(-z)))
    P_ = np.column_stack(out)
    return np.minimum.accumulate(P_, axis=1)  # P(>6,5) ≥ P(>7,5) ≥ ...

def metrics(P_, sub):
    y = sub.set1.values; res = {}
    # distribution complète -> log-loss multiclasse
    cdf = np.column_stack([np.ones(len(sub)), P_, np.zeros(len(sub))])
    probs = cdf[:, :-1] - cdf[:, 1:]  # P(=6), P(=7) ... P(=13)
    k = np.array([VALS.index(v) if v in VALS else -1 for v in y]); ok = k >= 0
    res["logloss_distribution"] = float(-np.mean(np.log(np.clip(probs[ok, k[ok]], 1e-6, 1))))
    for li, Lv in enumerate(LINES):
        yy = (y > Lv).astype(int); p = np.clip(P_[:, li], 1e-6, 1 - 1e-6)
        res[f"{Lv}"] = {"logloss": float(-np.mean(yy * np.log(p) + (1 - yy) * np.log(1 - p))), "bon_sens": float(((p > .5) == yy).mean()),
                        "brier": float(np.mean((p - yy) ** 2)), "reel": float(yy.mean()), "prevu": float(p.mean())}
    return res

R_ = {}
te = X[test]
R_["Appli actuelle"] = metrics(np.column_stack([app_now(te, li) for li in range(len(LINES))]), te)
R_["Fréquence moyenne (sans modèle)"] = metrics(np.tile([(X[train].set1 > Lv).mean() for Lv in LINES], (len(te), 1)), te)
COEF = {}
for name, cols in FEATS.items():
    msk = train & (X.pin_gap.notna() if "pin_gap" in cols else True)
    th = fit(cols, msk); COEF[name] = {"a": th[:len(LINES)].tolist(), "b": th[len(LINES):].tolist(), "cols": cols}
    tsub = te[te.pin_gap.notna()] if "pin_gap" in cols else te
    R_["Nouveau : " + name] = metrics(predict(th, tsub, cols), tsub)
# même sous-ensemble pour comparer honnêtement le gain de la cote Pinnacle
tp = te[te.pin_gap.notna()]
R_["(sous-ensemble avec cote) Nouveau +habitudes +Elo"] = metrics(predict(np.array(COEF["+habitudes +écart Elo"]["a"] + COEF["+habitudes +écart Elo"]["b"]), tp, FEATS["+habitudes +écart Elo"]), tp)
R_["(sous-ensemble avec cote) Appli actuelle"] = metrics(np.column_stack([app_now(tp, li) for li in range(len(LINES))]), tp)

print(f"Test 2024-2026 : {int(test.sum())} matchs | jeux du 1er set : " + ", ".join(f"{v}: {np.mean(te.set1 == v):.1%}" for v in VALS))
for k, v in R_.items():
    print(f"{k:52s} distribution {v['logloss_distribution']:.4f} | " + " ".join(f"{Lv}: {v[str(Lv)]['logloss']:.4f}/{v[str(Lv)]['bon_sens']:.1%}" for Lv in (8.5, 9.5, 10.5)))
# calibration ligne 9,5 du meilleur modèle sans cote
th = np.array(COEF["+habitudes +écart Elo"]["a"] + COEF["+habitudes +écart Elo"]["b"]); p = predict(th, te, FEATS["+habitudes +écart Elo"])[:, 3]
cal = pd.DataFrame({"p": p, "y": (te.set1 > 9.5).values}).groupby(pd.cut(p, [0, .3, .4, .5, .6, .7, 1]), observed=True).agg(prevu=("p", "mean"), reel=("y", "mean"), n=("y", "size")).round(3)
print(cal)
json.dump({"params": P, "mix": MIX, "lines": LINES, "vals": VALS, "coef": COEF, "test": R_, "cal95": cal.reset_index().astype(str).to_dict("records")},
          open("/home/claude/value-bets/model/set1_model.json", "w"), indent=1, default=float)
X.drop(columns=["new", "old"]).to_pickle("/home/claude/data/set1_rows.pkl")
