"""Rejoue la saison ATP 2025 avec la règle de Kobah :
parier 10 € (pari simple) sur le gagnant probable seulement quand les stats et Pinnacle sont d'accord
et que l'avis combiné (65 % Pinnacle, 35 % stats) dépasse 70 %.
Poids des stats réappris SANS 2025 (2008-2024), pour ne pas tricher."""
import csv, glob, json, math, re, unicodedata
import numpy as np, pandas as pd

exec(open("/home/claude/data/variants.py").read().split("for lam in")[0])  # X, Xs, y, flip, year, FEATS, bounded…

# ---- 1. poids appris sur 2008-2024 uniquement
fm = (year >= 2008) & (year <= 2024)
w = bounded(FEATS, fm, 30)

# probabilité « stats » du VAINQUEUR réel pour chaque match (features non retournées)
Xw = X[FEATS].values  # X = différences vainqueur − perdant (avant le mélange aléatoire)
p_stats_w = 1 / (1 + np.exp(-(Xw @ w)))
d2 = d.copy(); d2["p_stats_w"] = p_stats_w

# ---- 2. noms des joueurs (id TML -> nom)
names = {}
for f in glob.glob("/home/claude/data/TML-Database/20*.csv"):
    with open(f, newline="", encoding="utf-8", errors="replace") as fh:
        for r in csv.DictReader(fh):
            names[r["winner_id"]] = r["winner_name"]; names[r["loser_id"]] = r["loser_name"]
norm = lambda s: re.sub(r"[^a-z]", "", unicodedata.normalize("NFD", str(s)).encode("ascii", "ignore").decode().lower())
d2 = d2[d2.year == 2025].copy()
d2["wname"] = d2.A.map(names); d2["lname"] = d2.B.map(names)
d2["date"] = pd.to_datetime(d2.date)

# ---- 3. cotes 2025 (tennis-data.co.uk)
td = pd.read_excel("/home/claude/data/tennis-predictions/data_files/2025.xlsx")
def key(td_name):
    """« Auger-Aliassime F. » -> (nom normalisé, initiale)"""
    parts = str(td_name).strip().split()
    ini = parts[-1].replace(".", "")[:1].lower() if len(parts) > 1 else ""
    return norm(" ".join(parts[:-1]) if len(parts) > 1 else parts[0]), ini
def same(full, k):
    n = norm(full); return bool(k[0]) and n.endswith(k[0]) and (not k[1] or n.startswith(k[1]))

rows = []
for t in td.itertuples():
    kw, kl = key(t.Winner), key(t.Loser)
    cand = d2[(d2.date <= t.Date) & (d2.date >= t.Date - pd.Timedelta(days=16))]
    m = cand[cand.wname.map(lambda n: same(n, kw)).astype(bool).values & cand.lname.map(lambda n: same(n, kl)).astype(bool).values]
    if len(m) != 1: continue
    r = m.iloc[0]
    rows.append({"date": t.Date, "tour": t.Tournament, "series": t.Series, "winner": r.wname, "loser": r.lname,
                 "comment": t.Comment, "PSW": t.PSW, "PSL": t.PSL, "B365W": t.B365W, "B365L": t.B365L,
                 "AvgW": t.AvgW, "AvgL": t.AvgL, "MaxW": t.MaxW, "MaxL": t.MaxL, "p_stats_w": r.p_stats_w})
B = pd.DataFrame(rows)
print("matchs 2025 avec cotes :", len(td), "| reliés à l'historique de stats :", len(B))

# ---- 4. règle de pari
B = B[B.PSW.notna() & B.PSL.notna()].copy()
iw, il = 1 / B.PSW, 1 / B.PSL
B["p_pin_w"] = iw / (iw + il)                                 # Pinnacle sans marge
L = lambda p: np.log(np.clip(p, .03, .97) / (1 - np.clip(p, .03, .97)))
B["p_comb_w"] = 1 / (1 + np.exp(-(.65 * L(B.p_pin_w) + .35 * L(B.p_stats_w))))
agree = (B.p_stats_w > .5) == (B.p_pin_w > .5)
fav_w = B.p_comb_w > .5
B["p_pick"] = np.where(fav_w, B.p_comb_w, 1 - B.p_comb_w)
B["won"] = fav_w                                               # le favori combiné est-il le vrai vainqueur ?
B["void"] = B.comment.astype(str).str.contains("Retired|Walkover|Disq", case=False)  # abandons : pari annulé
sel = B[agree & (B.p_pick > .70)].copy()

def result(sel, book):
    o = np.where(sel.won, sel[book + "W"], sel[book + "L"])
    ok = ~np.isnan(o) & ~sel.void.values
    stake = 10.0
    pnl = np.where(sel.won.values, stake * (o - 1), -stake)[ok]
    n = int(ok.sum()); wins = int(sel.won.values[ok].sum())
    return {"paris": n, "gagnés": wins, "réussite": wins / n, "misé": n * stake, "gain_net": float(pnl.sum()),
            "roi": float(pnl.sum() / (n * stake)), "cote_moy": float(np.nanmean(o[ok])),
            "pire_serie": int(max((len(s) for s in "".join("W" if x else "L" for x in sel.won.values[ok]).split("W")), default=0)),
            "cumul": np.cumsum(pnl).tolist()}

out = {"n_matchs": int(len(B)), "n_selection": int(len(sel)), "annules": int(sel.void.sum())}
for book, lab in (("PS", "Pinnacle"), ("B365", "Bet365"), ("Avg", "Moyenne du marché"), ("Max", "Meilleure cote du marché")):
    r = result(sel, book); out[lab] = r
    print(f"{lab:26s} {r['paris']} paris · {r['gagnés']} gagnés ({r['réussite']:.1%}) · cote moy {r['cote_moy']:.2f} · "
          f"misé {r['misé']:.0f} € · résultat {r['gain_net']:+.2f} € · ROI {r['roi']:+.1%} · pire série {r['pire_serie']} défaites")
# Winamax ≈ marge plus forte que la moyenne : on applique −3 % aux cotes moyennes (ordre de grandeur des books français)
sel2 = sel.copy(); sel2["WinaW"] = 1 + (sel2.AvgW - 1) * .94; sel2["WinaL"] = 1 + (sel2.AvgL - 1) * .94
r = result(sel2, "Wina"); out["Estimation Winamax"] = r
print(f"{'Estimation Winamax (−6 % de gain par cote)':26s} {r['paris']} paris · résultat {r['gain_net']:+.2f} € · ROI {r['roi']:+.1%}")
# repères : même règle mais en pariant tous les favoris Pinnacle > 70 %, sans les stats
fav = B[(np.where(B.p_pin_w > .5, B.p_pin_w, 1 - B.p_pin_w) > .70)].copy()
fav["won"] = fav.p_pin_w > .5
r = result(fav, "Avg"); out["Repère : tous les favoris Pinnacle > 70 %, cote moyenne"] = r
print(f"Repère favoris Pinnacle >70 % (cote moyenne) : {r['paris']} paris · résultat {r['gain_net']:+.2f} € · ROI {r['roi']:+.1%}")
# par mois
sel["mois"] = pd.to_datetime(sel.date).dt.month
o = np.where(sel.won, sel.AvgW, sel.AvgL); ok = ~np.isnan(o) & ~sel.void.values
sel["pnl"] = np.where(sel.won, 10 * (o - 1), -10.0); sel.loc[~ok, "pnl"] = 0
out["par_mois"] = sel.groupby("mois").pnl.sum().round(2).to_dict()
print("par mois (cote moyenne) :", out["par_mois"])
json.dump(out, open("/home/claude/data/backtest_2025.json", "w"), ensure_ascii=False, default=float)
