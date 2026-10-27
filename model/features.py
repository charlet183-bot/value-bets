"""Recalcule, pour chaque match ATP, les stats de chaque joueur TELLES QU'ELLES ÉTAIENT AVANT le match,
avec les mêmes définitions que l'appli (relais tennis-serve + onglet Gagnant).
Sortie : features.csv (une ligne par match, joueur A = vainqueur ; l'orientation est mélangée à l'entraînement)."""
import csv, math, sys, glob, os
from collections import defaultdict
from datetime import date, timedelta

DATA = "/home/claude/data/TML-Database"
FIRST_YEAR, OUT_FROM = 2000, 2008  # Elo chauffé depuis 2000, features écrites à partir de 2008

# ---------- mêmes constantes que l'appli
AVG_SPW = 0.64
SHRINK = {"bp": (20, 0.62), "tb": (6, 0.5), "dec": (6, 0.5), "cb": (6, 0.3), "surf": (6, 0.5), "lvl": (6, 0.5)}

def shrunk(w, n, key):
    k, prior = SHRINK[key]
    return (w + k * prior) / (n + k)

def logit(p):
    p = min(0.97, max(0.03, p))
    return math.log(p / (1 - p))

def unlogit(x):
    return 1 / (1 + math.exp(-x))

def hold_p(p):
    q = 1 - p
    return p ** 4 * (1 + 4 * q + 10 * q * q) + 20 * p ** 3 * q ** 3 * (p * p / (1 - 2 * p * q))

def tb_p(pa, pb):
    tot = 0
    for a_first in (True, False):
        P = {(0, 0): 1.0}; win = 0
        for k in range(12):
            nx = defaultdict(float)
            for (a, b), pr in P.items():
                a_srv = ((k + 1) // 2 % 2 == 0) == a_first
                p = pa if a_srv else 1 - pb
                for na, nb, q in ((a + 1, b, p), (a, b + 1, 1 - p)):
                    if na == 7: win += pr * q
                    elif nb != 7: nx[(na, nb)] += pr * q
            P = nx
        x, y = pa * (1 - pb), (1 - pa) * pb
        win += P.get((6, 6), 0) * x / (x + y)
        tot += win / 2
    return tot

def set_p(ha, hb, ptb):
    tot = 0
    for a_starts in (True, False):
        P = {(0, 0): 1.0}; w = 0
        for k in range(12):
            nx = defaultdict(float)
            for (a, b), pr in P.items():
                pa = ha if ((k % 2 == 0) == a_starts) else 1 - hb
                for na, nb, q in ((a + 1, b, pa), (a, b + 1, 1 - pa)):
                    if (na >= 6 or nb >= 6) and abs(na - nb) >= 2:
                        if na > nb: w += pr * q
                    else: nx[(na, nb)] += pr * q
            P = nx
        w += P.get((6, 6), 0) * ptb
        tot += w / 2
    return tot

def match_p(s, bo5):
    return s ** 3 * (1 + 3 * (1 - s) + 6 * (1 - s) ** 2) if bo5 else s * s * (3 - 2 * s)

serve_cache = {}
def serve_model(sA, rA, sB, rB, bo5):
    cl = lambda x: min(0.85, max(0.35, x))
    pa, pb = cl(sA - rB + (1 - AVG_SPW)), cl(sB - rA + (1 - AVG_SPW))
    key = (round(pa, 3), round(pb, 3), bo5)
    if key not in serve_cache:
        ha, hb = hold_p(key[0]), hold_p(key[1])
        serve_cache[key] = match_p(set_p(ha, hb, tb_p(key[0], key[1])), bo5)
    return serve_cache[key]

exp_win = lambda rk, vrk: 1 / (1 + (rk / vrk) ** 0.8)
opp_adj = lambda vrk: 0.015 * math.log(min(1000, max(1, vrk)) / 100)

def score_info(score, win_is_winner=True):
    """Infos du point de vue du VAINQUEUR (le score est écrit pour lui)."""
    if not score or any(t in score.upper() for t in ("RET", "W/O", "DEF", "ABD", "ABN", "UNK")): return None
    sets = []
    for t in score.split():
        t = t.split("(")[0]
        if "-" in t:
            a, b = t.split("-")[:2]
            if a.isdigit() and b.isdigit(): sets.append((int(a), int(b)))
    if not sets: return None
    wsets = sum(1 for a, b in sets if a > b)
    decider = (wsets == 2 and len(sets) == 3) or (wsets == 3 and len(sets) == 5)
    tbs = [(a, b) for a, b in sets if (a, b) in ((7, 6), (6, 7))]
    return {"tb_w_winner": sum(1 for a, b in tbs if a > b), "tbN": len(tbs), "decider": decider, "first_lost_winner": sets[0][0] < sets[0][1]}

ROUND_DAY = {"R128": 1, "R64": 2, "R32": 3, "R16": 4, "QF": 5, "SF": 6, "F": 7, "RR": 3, "BR": 6, "ER": 1, "Q1": 0, "Q2": 0, "Q3": 0}
ROUND_ORD = {"Q1": 0, "Q2": 1, "Q3": 2, "ER": 3, "RR": 4, "R128": 5, "R64": 6, "R32": 7, "R16": 8, "QF": 9, "SF": 10, "BR": 11, "F": 12}

def fnum(x):
    try:
        v = float(x); return v if math.isfinite(v) else None
    except (TypeError, ValueError): return None

def parse_date(s):
    s = str(s)[:8]
    return date(int(s[:4]), int(s[4:6]), int(s[6:8]))

# ---------- chargement
rows = []
for f in sorted(glob.glob(os.path.join(DATA, "[12][0-9][0-9][0-9].csv"))):
    y = int(os.path.basename(f)[:4])
    if y < FIRST_YEAR: continue
    with open(f, newline="", encoding="utf-8", errors="replace") as fh:
        for r in csv.DictReader(fh):
            if r.get("tourney_level") == "D": continue  # Coupe Davis : exclue
            try: r["_d"] = parse_date(r["tourney_date"])
            except Exception: continue
            rows.append(r)
rows.sort(key=lambda r: (r["_d"], r["tourney_id"], ROUND_ORD.get(r["round"], 5), int(fnum(r["match_num"]) or 0)))
print("matchs chargés :", len(rows), file=sys.stderr)

# ---------- état par joueur
hist = defaultdict(list)       # liste de dicts (plus récent à la fin)
elo = defaultdict(lambda: 1500.0); elo_n = defaultdict(int)
selo = defaultdict(lambda: 1500.0); selo_n = defaultdict(int)  # clé (joueur, surface)
h2h = defaultdict(lambda: [0, 0])  # (a,b) trié -> victoires de a, victoires de b
info = {}

def player_feats(pid, surface, level, now, opp_id):
    H = hist[pid]
    F = {}
    last20 = H[-20:]; last60 = H[-60:]
    st20 = [m for m in last20 if m["spw"] is not None]
    # service / retour corrigés selon l'adversaire, mélangés vers la surface (comme l'appli)
    def blend(key):
        base = [m[key] - opp_adj(m["orank"]) for m in st20 if m[key] is not None]
        if len(base) < 3: return None
        b = sum(base) / len(base)
        g = [m[key] - opp_adj(m["orank"]) for m in last60 if m["surface"] == surface and m[key] is not None]
        if len(g) < 3: return b
        return (len(g) * (sum(g) / len(g)) + 6 * b) / (len(g) + 6)
    F["spw"] = blend("spw"); F["rpw"] = blend("rpw")
    # forme pondérée par les adversaires + tendance
    q = [m for m in last20 if m["rank"] and m["orank"]]
    if len(q) >= 5:
        res = [(1 if m["win"] else 0) - exp_win(m["rank"], m["orank"]) for m in reversed(q)]
        ws = [0.93 ** i for i in range(len(res))]
        F["perf"] = sum(w * r for w, r in zip(ws, res)) / sum(ws)
        F["trend"] = sum(res[:5]) / 5 - sum(res) / len(res)
    else:
        F["perf"] = None; F["trend"] = None
    # mental
    bps = sum(m["bps"] for m in last60 if m["bps"] is not None); bpf = sum(m["bpf"] for m in last60 if m["bpf"] is not None)
    F["bp"] = shrunk(bps, bpf, "bp") if bpf else None
    tbw = sum(m["tbW"] for m in last60); tbn = sum(m["tbN"] for m in last60)
    F["tb"] = shrunk(tbw, tbn, "tb")
    dec = [m for m in last60 if m["decider"]]; F["dec"] = shrunk(sum(m["win"] for m in dec), len(dec), "dec")
    cb = [m for m in last60 if m["firstLost"]]; F["cb"] = shrunk(sum(m["win"] for m in cb), len(cb), "cb")
    # détail du service
    sv = [m for m in last60 if m["fi"] is not None]
    if len(sv) >= 3:
        for k in ("fi", "fw", "sw", "df"):
            vals = [m[k] for m in sv if m[k] is not None]
            F[k] = sum(vals) / len(vals) if vals else None
    else:
        for k in ("fi", "fw", "sw", "df"): F[k] = None
    # bilan surface et niveau
    s = [m for m in last60 if m["surface"] == surface]; F["surf"] = shrunk(sum(m["win"] for m in s), len(s), "surf") if H else None
    l = [m for m in last60 if m["lvl"] == level]; F["lvl"] = shrunk(sum(m["win"] for m in l), len(l), "lvl") if H else None
    # fatigue (dates = début du tournoi, comme Tennis Abstract)
    rec = [m for m in H[-20:] if 0 <= (now - m["d"]).days <= 14]
    F["n14"] = len(rec)
    F["lastMin"] = H[-1]["mins"] if H and H[-1]["mins"] else None
    F["days"] = (now - H[-1]["d"]).days if H else None
    F["n"] = len(H)
    return F

out = open("/home/claude/data/features.csv", "w", newline="")
cols = ["year", "date", "level", "surface", "bo5", "A", "B", "elo_A", "elo_B", "serve_p", "rankA", "rankB", "h2h_a", "h2h_b",
        "ageA", "ageB", "htA", "htB", "lefA", "lefB"] + [f"{k}_{s}" for k in ("perf", "trend", "bp", "tb", "dec", "cb", "fi", "fw", "sw", "df", "surf", "lvl", "n14", "lastMin", "days", "n", "spw", "rpw") for s in "AB"]
wr = csv.writer(out); wr.writerow(cols)
written = 0
for r in rows:
    w, l = r["winner_id"], r["loser_id"]
    surface = r["surface"] or "Hard"
    lvl = "top" if r["tourney_level"] in ("G", "M", "F") else "tour"
    bo5 = (r.get("best_of") or "3").strip() == "5"
    now = r["_d"] + timedelta(days=ROUND_DAY.get(r["round"], 3) * (2 if bo5 else 1))
    wrk, lrk = fnum(r["winner_rank"]), fnum(r["loser_rank"])
    score = r["score"] or ""
    walkover = "W/O" in score.upper() or not score.strip()

    if not walkover and r["_d"].year >= OUT_FROM and r["round"] not in ("Q1", "Q2", "Q3"):
        FA = player_feats(w, surface, lvl, now, l); FB = player_feats(l, surface, lvl, now, w)
        ek = lambda p: (elo[p] + selo[(p, surface)]) / 2
        sp = serve_model(FA["spw"], FA["rpw"], FB["spw"], FB["rpw"], bo5) if None not in (FA["spw"], FA["rpw"], FB["spw"], FB["rpw"]) else ""
        key = tuple(sorted((w, l))); hh = h2h[key]; ha, hb = (hh[0], hh[1]) if key[0] == w else (hh[1], hh[0])
        rowv = [r["_d"].year, r["_d"].isoformat(), lvl, surface, int(bo5), w, l, ek(w), ek(l), sp, wrk or "", lrk or "", ha, hb,
                r["winner_age"], r["loser_age"], r["winner_ht"], r["loser_ht"], int(r["winner_hand"] == "L"), int(r["loser_hand"] == "L")]
        for k in ("perf", "trend", "bp", "tb", "dec", "cb", "fi", "fw", "sw", "df", "surf", "lvl", "n14", "lastMin", "days", "n", "spw", "rpw"):
            rowv += ["" if FA[k] is None else FA[k], "" if FB[k] is None else FB[k]]
        wr.writerow(rowv); written += 1

    if walkover: continue
    # ---------- mise à jour après le match
    si = score_info(score)
    def side(pid, won, me, opp, rk, ork):
        svpt = fnum(r[me + "svpt"]); fi = fnum(r[me + "1stIn"]); fw = fnum(r[me + "1stWon"]); sw2 = fnum(r[me + "2ndWon"])
        osv = fnum(r[opp + "svpt"]); ofw = fnum(r[opp + "1stWon"]); osw = fnum(r[opp + "2ndWon"])
        ok = svpt and fi is not None and fw is not None and sw2 is not None and svpt > fi and fi > 0
        d = {"d": r["_d"], "surface": surface, "lvl": lvl, "win": won, "rank": rk, "orank": ork or 500,
             "spw": (fw + sw2) / svpt if ok else None,
             "rpw": 1 - (ofw + osw) / osv if (osv and ofw is not None and osw is not None) else None,
             "fi": fi / svpt if ok else None, "fw": fw / fi if ok else None, "sw": sw2 / (svpt - fi) if ok else None,
             "df": (fnum(r[me + "df"]) or 0) / svpt if ok else None,
             "bps": fnum(r[me + "bpSaved"]), "bpf": fnum(r[me + "bpFaced"]), "mins": fnum(r["minutes"]),
             "tbN": si["tbN"] if si else 0, "tbW": (si["tb_w_winner"] if won else si["tbN"] - si["tb_w_winner"]) if si else 0,
             "decider": bool(si and si["decider"]), "firstLost": bool(si and (si["first_lost_winner"] if won else not si["first_lost_winner"]))}
        hist[pid].append(d)
        if len(hist[pid]) > 80: del hist[pid][:-80]
    side(w, True, "w_", "l_", wrk, lrk); side(l, False, "l_", "w_", lrk, wrk)
    # Elo (formule Tennis Abstract / FiveThirtyEight)
    for E, N, kw, kl in ((elo, elo_n, w, l), (selo, selo_n, (w, surface), (l, surface))):
        ew = 1 / (1 + 10 ** ((E[kl] - E[kw]) / 400))
        Kw = 250 / ((N[kw] + 5) ** 0.4); Kl = 250 / ((N[kl] + 5) ** 0.4)
        E[kw] += Kw * (1 - ew); E[kl] -= Kl * (1 - ew); N[kw] += 1; N[kl] += 1
    key = tuple(sorted((w, l))); h2h[key][0 if key[0] == w else 1] += 1
out.close()
print("lignes écrites :", written, file=sys.stderr)
