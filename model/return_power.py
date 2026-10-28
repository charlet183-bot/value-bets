"""Un joueur retourne-t-il mieux (ou moins bien) que prévu face aux gros serveurs, de façon durable ?
Puissance du serveur = son taux d'aces sur ses 30 matchs précédents (l'historique n'a pas la vitesse).
Pour chaque retourneur : écart entre ce qu'il a fait au retour et ce que prévoyait le modèle de base,
en fonction de la puissance du serveur en face -> « sensibilité » personnelle. Est-ce qu'elle prédit les matchs suivants ?
Fenêtres testées : ~21 derniers matchs (ce que l'appli voit) et tout l'historique. Test 2024-2026."""
import csv, glob, os, sys, math, json
from collections import defaultdict, deque
import numpy as np
exec(open("/home/claude/data/features.py").read().split("# ---------- chargement")[0])
rows = []
for f in sorted(glob.glob(os.path.join(DATA, "[12][0-9][0-9][0-9].csv"))):
    if int(os.path.basename(f)[:4]) < 2000: continue
    with open(f, newline="", encoding="utf-8", errors="replace") as fh:
        for r in csv.DictReader(fh):
            if r.get("tourney_level") == "D": continue
            try: r["_d"] = parse_date(r["tourney_date"])
            except Exception: continue
            rows.append(r)
rows.sort(key=lambda r: (r["_d"], r["tourney_id"], ROUND_ORD.get(r["round"], 5), int(fnum(r["match_num"]) or 0)))
H = defaultdict(lambda: deque(maxlen=60))      # stats par match : spw, rpw, ace rate
RES = defaultdict(lambda: deque(maxlen=400))   # pour le retourneur : (puissance serveur centrée, écart au retour)
out = []
def base(pid, k, n=30):
    xs = [m[k] for m in list(H[pid])[-n:] if m[k] is not None]
    return (sum(xs) / len(xs), len(xs)) if xs else (None, 0)
for r in rows:
    w, l = r["winner_id"], r["loser_id"]
    st = {}
    for me, op, pid in (("w_", "l_", w), ("l_", "w_", l)):
        sv, f1, f2, ac = fnum(r[me + "svpt"]), fnum(r[me + "1stWon"]), fnum(r[me + "2ndWon"]), fnum(r[me + "ace"])
        st[pid] = (f1 + f2) / sv if sv and f1 is not None and f2 is not None else None, (ac / sv) if sv and ac is not None else None, sv
    ok = st[w][0] is not None and st[l][0] is not None
    if ok:
        for S, R in ((w, l), (l, w)):   # S sert, R retourne
            sS, nS = base(S, "spw"); rR, nR = base(R, "rpw"); aS, nA = base(S, "ace")
            if nS >= 8 and nR >= 8 and nA >= 8:
                pred = sS - rR + .36                       # points gagnés au service par S (modèle de base)
                z = (aS - .075) / .035                     # puissance du serveur, centrée-réduite
                actual = st[S][0]
                # sensibilité personnelle du retourneur : pente de ses écarts selon la puissance du serveur
                def sens(n, lam):
                    xs = list(RES[R])[-n:] if n else list(RES[R])
                    sxy = sum(a * b for a, b in xs); sxx = sum(a * a for a, b in xs)
                    return sxy / (sxx + lam), len(xs)
                b21, n21 = sens(21, 10); ball, nall = sens(0, 20)
                out.append((r["_d"].year, pred, z, actual, st[S][2], b21, ball, n21, nall))
                RES[R].append((z, actual - pred))   # mis à jour APRÈS la prévision
    for pid, (spw, ace, sv) in st.items():
        opp = l if pid == w else w
        H[pid].append({"spw": spw, "ace": ace, "rpw": (1 - st[opp][0]) if st[opp][0] is not None else None})
X = np.array([o[:7] for o in out], float); n21 = np.array([o[7] for o in out]); nall = np.array([o[8] for o in out])
yr, pred, z, act, wgt, b21, ball = X.T
tr, te = (yr >= 2008) & (yr <= 2023), yr >= 2024
def mse(p, m): return float(np.sum(wgt[m] * (act[m] - p[m]) ** 2) / np.sum(wgt[m]))
res = {"base": (mse(pred, tr), mse(pred, te))}
# pente commune (effet général des gros serveurs, déjà en partie dans le modèle)
g = np.sum(wgt[tr] * z[tr] * (act[tr] - pred[tr])) / np.sum(wgt[tr] * z[tr] ** 2)
pg = pred + g * z; res["pente commune"] = (mse(pg, tr), mse(pg, te))
for lab, bb in (("perso 21 derniers matchs", b21), ("perso tout l'historique", ball)):
    best = None
    for k in (0, .25, .5, .75, 1, 1.5):
        p = pg + k * bb * z; e = mse(p, tr)
        if best is None or e < best[0]: best = (e, k, mse(p, te))
    res[lab] = (best[0], best[2], best[1])
print(f"{len(out)} services analysés (test 2024-26 : {int(te.sum())}) · pente commune {g:+.4f} par écart-type de puissance")
for k, v in res.items(): print(f"  {k:28s} entraînement {v[0]*1e4:.3f}  test {v[1]*1e4:.3f}" + (f"  (force retenue {v[2]})" if len(v) > 2 else ""))
# la sensibilité persiste-t-elle ? corrélation entre la sensibilité passée et l'écart du match suivant
r_all = np.corrcoef(ball[te] * z[te], (act - pg)[te])[0, 1]; r21 = np.corrcoef(b21[te] * z[te], (act - pg)[te])[0, 1]
print(f"  corrélation sensibilité passée × écart suivant : 21 matchs {r21:+.3f} · tout l'historique {r_all:+.3f}")
json.dump({"n": len(out), "pente_commune": g, "res": res, "corr21": r21, "corr_all": r_all}, open("return_power.json", "w"), indent=1)
