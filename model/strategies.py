"""Cherche des règles de pari rentables sur 2011-2022, les vérifie sur 2023-2024, puis sur 2025 (jamais utilisé pour choisir).
Pari simple de 10 €. Abandons/forfaits = pari annulé. Cotes de clôture tennis-data.co.uk."""
import numpy as np, pandas as pd
D = pd.read_pickle("/home/claude/data/odds/all.pkl")
D = D[D.year != 2026]
D = D[D.PSW.notna() & D.PSL.notna() & (D.PSW > 1) & (D.PSL > 1)].copy()
D["void"] = D.Comment.astype(str).str.contains("Retired|Walkover|Disq|Award", case=False)
D = D[~D.void]
# une ligne par joueur
def side(w):
    s, o = ("W", "L") if w else ("L", "W")
    x = pd.DataFrame({"year": D.year, "series": D.Series, "round": D.Round, "surface": D.Surface, "bo5": D["Best of"] == 5,
                      "won": w, "ps": D["PS" + s], "pso": D["PS" + o], "b365": D["B365" + s], "avg": D["Avg" + s],
                      "max": D["Max" + s], "rank": D[s + "Rank"], "orank": D[o + "Rank"]})
    return x
S = pd.concat([side(True), side(False)], ignore_index=True)
S["p"] = (1 / S.ps) / (1 / S.ps + 1 / S.pso)                 # proba Pinnacle sans marge
S["wina"] = 1 + (S.avg - 1) * .94                             # estimation Winamax
S["rank"] = pd.to_numeric(S["rank"], errors="coerce"); S["orank"] = pd.to_numeric(S["orank"], errors="coerce")

PER = {"2011-22 (recherche)": (S.year >= 2011) & (S.year <= 2022), "2023-24 (contrôle)": S.year.isin([2023, 2024]), "2025 (test)": S.year == 2025}
def roi(mask, book):
    sub = S[mask & S[book].notna() & (S[book] > 1)]
    pnl = np.where(sub.won, sub[book] - 1, -1.0) * 10
    return len(sub), pnl.sum(), (pnl.sum() / (10 * len(sub)) if len(sub) else np.nan), (sub[book].mean() if len(sub) else np.nan)

rules = {}
for book in ("wina", "avg", "b365", "max"):
    for t in (0, .02, .05, .08, .12):
        rules[f"Value {book} > {t:.0%} (vs Pinnacle)"] = (S[book] * S.p - 1 > t, book)
        for lo, hi, lab in ((1, 2, "cote < 2"), (2, 3.5, "cote 2-3.5"), (3.5, 99, "cote > 3.5")):
            rules[f"Value {book} > {t:.0%}, {lab}"] = ((S[book] * S.p - 1 > t) & (S[book] >= lo) & (S[book] < hi), book)
for lo, hi in ((1, 1.15), (1.15, 1.3), (1.3, 1.5), (1.5, 1.8), (1.8, 2.2), (2.2, 3), (3, 5), (5, 99)):
    for book in ("wina", "avg", "b365", "ps"):
        rules[f"Tout parier cote Pinnacle {lo}-{hi} @ {book}"] = ((S.ps >= lo) & (S.ps < hi), book)
for ser in S.series.dropna().unique():
    rules[f"Favori Pinnacle, {ser} @ avg"] = ((S.p > .5) & (S.series == ser), "avg")
    rules[f"Outsider Pinnacle, {ser} @ avg"] = ((S.p < .5) & (S.series == ser), "avg")
rules["Favori Pinnacle, 5 sets @ avg"] = ((S.p > .5) & S.bo5, "avg")
rules["Mieux classé mais outsider @ avg"] = ((S["rank"] < S.orank) & (S.p < .5), "avg")
rules["Mieux classé mais outsider @ max"] = ((S["rank"] < S.orank) & (S.p < .5), "max")
rules["Moins bien classé mais favori @ avg"] = ((S["rank"] > S.orank) & (S.p > .5), "avg")
rules["Bet365 trop haut vs Pinnacle (>5%), gros favori"] = ((S.b365 * S.p - 1 > .05) & (S.p > .6), "b365")

rows = []
for name, (m, book) in rules.items():
    r = {"règle": name}
    for lab, pm in PER.items():
        n, pnl, ro, co = roi(m & pm, book)
        r[lab + " n"] = n; r[lab + " roi"] = ro; r[lab + " €"] = pnl
        if lab.startswith("2025"): r["cote moy 2025"] = co
    # régularité : part des années 2011-22 positives
    yrs = [roi(m & (S.year == y), book)[2] for y in range(2011, 2023) if y != 2014]
    r["années + (2011-22)"] = f"{sum(1 for v in yrs if v and v > 0)}/{len([v for v in yrs if v == v])}"
    rows.append(r)
R = pd.DataFrame(rows)
R.to_csv("/home/claude/value-bets/model/strategies.csv", index=False)
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 300); pd.set_option("display.max_colwidth", 48)
cols = ["règle", "2011-22 (recherche) n", "2011-22 (recherche) roi", "années + (2011-22)", "2023-24 (contrôle) n", "2023-24 (contrôle) roi", "2025 (test) n", "2025 (test) roi", "2025 (test) €", "cote moy 2025"]
good = R[(R["2011-22 (recherche) roi"] > 0) & (R["2011-22 (recherche) n"] >= 100)].sort_values("2011-22 (recherche) roi", ascending=False)
print("== Règles positives sur 2011-22 (≥100 paris) ==")
print(good[cols].round(3).to_string(index=False))
print("\n== Bandes de cotes (tout parier) ==")
print(R[R.règle.str.startswith("Tout parier")][cols].round(3).to_string(index=False))

print("\n== Détail par année des règles retenues ==")
pick = {"A. Meilleure cote > Pinnacle +5 %, cote 2-3,5": ((S["max"] * S.p - 1 > .05) & (S["max"] >= 2) & (S["max"] < 3.5), "max"),
        "B. Meilleure cote > Pinnacle +2 %, cote < 2": ((S["max"] * S.p - 1 > .02) & (S["max"] < 2), "max"),
        "C. Cote type Winamax > Pinnacle (value > 0)": (S.wina * S.p - 1 > 0, "wina"),
        "D. Bet365 > Pinnacle +2 %, cote 2-3,5": ((S.b365 * S.p - 1 > .02) & (S.b365 >= 2) & (S.b365 < 3.5), "b365")}
for k, (m, b) in pick.items():
    line = []
    for y in sorted(S.year.unique()):
        n, pnl, ro, _ = roi(m & (S.year == y), b); line.append(f"{y}:{n}p {pnl:+.0f}€")
    print(k); print("   ", " | ".join(line))
