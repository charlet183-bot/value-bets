"""Calcule, pour chaque match ATP, ce que les modèles de JEUX prévoyaient avant le match, et ce qui s'est passé.
- ancien : comme l'appli aujourd'hui (jeux de service gagnés bruts, tie-break au jugé, 1er set mélangé à l'historique)
- nouveau : point par point, service de A face au retour de B (corrigés selon les adversaires, surface), tie-break exact
Sortie : games.csv"""
import csv, math, sys, glob, os, random
from collections import defaultdict
from datetime import timedelta
exec(open("/home/claude/data/features.py").read().split("# ---------- chargement")[0])

# ---------- distributions exactes
def set_dist(pa, pb, ptb, a_starts):
    """{(jeux A, jeux B): proba} pour un set ; pa = A gagne un point... ici pa/pb = proba de GARDER son service (jeu)."""
    P = {(0, 0): 1.0}; out = defaultdict(float)
    for k in range(13):
        nx = defaultdict(float)
        for (a, b), pr in P.items():
            if a == 6 and b == 6:
                out[(7, 6)] += pr * ptb; out[(6, 7)] += pr * (1 - ptb); continue
            ph = pa if ((k % 2 == 0) == a_starts) else 1 - pb
            for na, nb, q in ((a + 1, b, ph), (a, b + 1, 1 - ph)):
                if (na >= 6 or nb >= 6) and abs(na - nb) >= 2: out[(na, nb)] += pr * q
                else: nx[(na, nb)] += pr * q
        P = nx
        if not P: break
    return out

def match_dist(ha, hb, ptb, bo5):
    """Distribution jointe (jeux totaux, jeux A) + 1er set, en suivant qui sert au début de chaque set."""
    need = 3 if bo5 else 2
    sd = {True: set_dist(ha, hb, ptb, True), False: set_dist(ha, hb, ptb, False)}
    first = defaultdict(float)
    for st in (True, False):
        for (a, b), p in sd[st].items(): first[a + b] += p / 2
    # état : (sets A, sets B, A commence le set, jeux A, jeux B)
    states = defaultdict(float)
    states[(0, 0, True, 0, 0)] += .5; states[(0, 0, False, 0, 0)] += .5
    final = defaultdict(float)  # (jeux A, jeux B) -> p
    while states:
        nx = defaultdict(float)
        for (sa, sb, st, ga, gb), pr in states.items():
            for (a, b), p in sd[st].items():
                nsa, nsb = sa + (a > b), sb + (b > a)
                nst = st if (a + b) % 2 == 0 else not st
                key = (ga + a, gb + b)
                if nsa == need or nsb == need: final[key] += pr * p
                else: nx[(nsa, nsb, nst, ga + a, gb + b)] += pr * p
        states = nx
    return first, final

def pts_per_game(p):
    """Nombre moyen de points dans un jeu de service quand le serveur gagne chaque point avec la proba p."""
    q = 1 - p; e = 0.0
    for n, (w, l) in ((4, (4, 0)), (5, (4, 1)), (6, (4, 2))):
        e += n * (math.comb(n - 1, 3) * (p ** 4 * q ** (n - 4)) + math.comb(n - 1, 3) * (q ** 4 * p ** (n - 4)))
    pd = 20 * p ** 3 * q ** 3
    e += pd * (6 + 2 / (p * p + q * q))
    return e

def ptb_heuristic(ha, hb): return min(.8, max(.2, .5 + (ha - hb) * 1.2))

# ---------- chargement et boucle chronologique (comme features.py)
rows = []
for f in sorted(glob.glob(os.path.join(DATA, "[12][0-9][0-9][0-9].csv"))):
    if int(os.path.basename(f)[:4]) < FIRST_YEAR: continue
    with open(f, newline="", encoding="utf-8", errors="replace") as fh:
        for r in csv.DictReader(fh):
            if r.get("tourney_level") == "D": continue
            try: r["_d"] = parse_date(r["tourney_date"])
            except Exception: continue
            rows.append(r)
rows.sort(key=lambda r: (r["_d"], r["tourney_id"], ROUND_ORD.get(r["round"], 5), int(fnum(r["match_num"]) or 0)))

hist = defaultdict(list)
elo = defaultdict(lambda: 1500.0); elo_n = defaultdict(int)
selo = defaultdict(lambda: 1500.0); selo_n = defaultdict(int)
rnd = random.Random(7)

def feats(pid, surface):
    H = hist[pid]; last20 = H[-20:]; last60 = H[-60:]
    st20 = [m for m in last20 if m["spw"] is not None]
    if len(st20) < 5: return None
    def blend(key, adj=True):
        f = (lambda m: m[key] - opp_adj(m["orank"])) if adj else (lambda m: m[key])
        base = [f(m) for m in st20 if m[key] is not None]
        if len(base) < 3: return None
        b = sum(base) / len(base)
        g = [f(m) for m in last60 if m["surface"] == surface and m[key] is not None]
        if len(g) < 3: return b
        return (len(g) * (sum(g) / len(g)) + 6 * b) / (len(g) + 6)
    s1 = [m["set1"] for m in last20 if m["set1"]]
    return {"spw": blend("spw"), "rpw": blend("rpw"), "spw_raw": sum(m["spw"] for m in st20) / len(st20),
            "ace": blend("ace", adj=False), "ace_raw": sum(m["ace"] for m in st20 if m["ace"] is not None) / max(1, sum(1 for m in st20 if m["ace"] is not None)),
            "s1hist": (sum(1 for x in s1 if x >= 10) / len(s1)) if len(s1) >= 3 else None}

def sets_of(score):
    if not score or any(t in score.upper() for t in ("RET", "W/O", "DEF", "ABD", "ABN", "UNK")): return None
    out = []
    for t in score.split():
        t = t.split("(")[0]
        if "-" in t:
            a, b = t.split("-")[:2]
            if a.isdigit() and b.isdigit(): out.append((int(a), int(b)))
    return out or None

out = open("/home/claude/data/games.csv", "w", newline=""); wr = csv.writer(out)
wr.writerow(["year", "surface", "bo5", "elo_diff", "pa", "pb", "ha_old", "hb_old", "s1hist_A", "s1hist_B",
             "aceA", "aceB", "aceA_raw", "aceB_raw", "rpwA", "rpwB",
             "set1", "total", "gamesA", "acesA", "acesB", "svptA", "svptB"])
for r in rows:
    w, l = r["winner_id"], r["loser_id"]; surface = r["surface"] or "Hard"
    bo5 = (r.get("best_of") or "3").strip() == "5"
    score = r["score"] or ""; sets = sets_of(score)
    wrk, lrk = fnum(r["winner_rank"]), fnum(r["loser_rank"])
    if sets and r["_d"].year >= OUT_FROM and r["round"] not in ("Q1", "Q2", "Q3"):
        # orientation aléatoire (A n'est pas forcément le vainqueur)
        flip = rnd.random() < .5
        A, B = (l, w) if flip else (w, l)
        FA, FB = feats(A, surface), feats(B, surface)
        if FA and FB and None not in (FA["spw"], FA["rpw"], FB["spw"], FB["rpw"]):
            pa = min(.85, max(.35, FA["spw"] - FB["rpw"] + (1 - AVG_SPW)))
            pb = min(.85, max(.35, FB["spw"] - FA["rpw"] + (1 - AVG_SPW)))
            ek = lambda p: (elo[p] + selo[(p, surface)]) / 2
            gw = sum(a for a, b in sets); gl = sum(b for a, b in sets)
            aw, al = fnum(r["w_ace"]), fnum(r["l_ace"]); sw_, sl_ = fnum(r["w_svpt"]), fnum(r["l_svpt"])
            wr.writerow([r["_d"].year, surface, int(bo5), ek(A) - ek(B), pa, pb, hold_p(FA["spw_raw"]), hold_p(FB["spw_raw"]),
                         FA["s1hist"] if FA["s1hist"] is not None else "", FB["s1hist"] if FB["s1hist"] is not None else "",
                         FA["ace"] or "", FB["ace"] or "", FA["ace_raw"], FB["ace_raw"], FA["rpw"], FB["rpw"],
                         sets[0][0] + sets[0][1], gw + gl, gl if flip else gw,
                         (al if flip else aw) if aw is not None else "", (aw if flip else al) if al is not None else "",
                         (sl_ if flip else sw_) or "", (sw_ if flip else sl_) or ""])
    if "W/O" in score.upper() or not score.strip(): continue
    # mise à jour de l'historique
    def side(pid, won, me, opp, rk, ork):
        svpt = fnum(r[me + "svpt"]); fw = fnum(r[me + "1stWon"]); sw2 = fnum(r[me + "2ndWon"])
        osv = fnum(r[opp + "svpt"]); ofw = fnum(r[opp + "1stWon"]); osw = fnum(r[opp + "2ndWon"])
        ok = svpt and fw is not None and sw2 is not None and svpt > 0
        st = sets_of(score)
        hist[pid].append({"surface": surface, "orank": ork or 500,
                          "spw": (fw + sw2) / svpt if ok else None,
                          "rpw": 1 - (ofw + osw) / osv if (osv and ofw is not None and osw is not None) else None,
                          "ace": (fnum(r[me + "ace"]) or 0) / svpt if ok else None,
                          "set1": (st[0][0] + st[0][1]) if st else None})
        if len(hist[pid]) > 80: del hist[pid][:-80]
    side(w, True, "w_", "l_", wrk, lrk); side(l, False, "l_", "w_", lrk, wrk)
    for E, N, kw, kl in ((elo, elo_n, w, l), (selo, selo_n, (w, surface), (l, surface))):
        ew = 1 / (1 + 10 ** ((E[kl] - E[kw]) / 400))
        E[kw] += 250 / ((N[kw] + 5) ** 0.4) * (1 - ew); E[kl] -= 250 / ((N[kl] + 5) ** 0.4) * (1 - ew); N[kw] += 1; N[kl] += 1
out.close()
print("ok", file=sys.stderr)
