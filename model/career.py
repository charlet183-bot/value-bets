"""Pour chaque match ATP 2008-2026, reconstitue ce que l'appli peut voir AVANT le match :
- l'actuel : 20 derniers matchs (corrigés selon l'adversaire) + surface sur 52 semaines
- le nouveau : toute la carrière, saison par saison (comme les tableaux « tour-years » de Tennis Abstract)
  et par surface (comme « career-splits »)
et ce qui s'est passé (points gagnés au service, jeux du 1er set, total de jeux...).
Sortie : career.pkl"""
import csv, glob, os, sys, math, random, pickle
from collections import defaultdict, deque
exec(open("/home/claude/data/features.py").read().split("# ---------- chargement")[0])

rows = []
for f in sorted(glob.glob(os.path.join(DATA, "[12][0-9][0-9][0-9].csv"))):
    if int(os.path.basename(f)[:4]) < 1995: continue
    with open(f, newline="", encoding="utf-8", errors="replace") as fh:
        for r in csv.DictReader(fh):
            if r.get("tourney_level") == "D": continue
            try: r["_d"] = parse_date(r["tourney_date"])
            except Exception: continue
            rows.append(r)
rows.sort(key=lambda r: (r["_d"], r["tourney_id"], ROUND_ORD.get(r["round"], 5), int(fnum(r["match_num"]) or 0)))
print("matchs :", len(rows), file=sys.stderr)

K = ("m", "sv", "sw", "rv", "rw", "sg", "hd", "rg", "br", "ace", "tbw", "tbn", "gw", "gl", "st", "s1n", "s1g", "s1o", "lo", "lr", "lm")
year = defaultdict(lambda: defaultdict(lambda: [0.0] * len(K)))   # joueur -> année -> compteurs
surfc = defaultdict(lambda: defaultdict(lambda: [0.0] * len(K)))  # joueur -> surface -> compteurs (carrière)
recent = defaultdict(lambda: deque(maxlen=120))                     # derniers matchs (pour l'actuel)
elo = defaultdict(lambda: 1500.0); elo_n = defaultdict(int)
selo = defaultdict(lambda: 1500.0); selo_n = defaultdict(int)
HL = (0.5, 1, 1.5, 2, 3, 5, 1000)
I = {k: i for i, k in enumerate(K)}

def sets_of(score):
    if not score or any(t in score.upper() for t in ("RET", "W/O", "DEF", "ABD", "ABN", "UNK")): return None
    out = []
    for t in score.split():
        t = t.split("(")[0]
        if "-" in t:
            a, b = t.split("-")[:2]
            if a.isdigit() and b.isdigit(): out.append((int(a), int(b)))
    return out or None

def career(pid, d, surface):
    """Estimations « toute la carrière » pour plusieurs demi-vies + bilans par surface."""
    Y = year[pid]; out = {}
    if not Y: return None
    t = d.year + (d.timetuple().tm_yday - 1) / 365
    for h in HL:
        acc = [0.0] * len(K)
        for y, c in Y.items():
            age = (t - y) / 2 if y == d.year else t - (y + 0.5)  # saison en cours : milieu de la partie jouée
            w = 0.5 ** (age / h)
            for i in range(len(K)): acc[i] += w * c[i]
        out[h] = acc
    tot = [sum(c[i] for c in Y.values()) for i in range(len(K))]
    sc = surfc[pid].get(surface)
    return {"w": out, "tot": tot, "surf": list(sc) if sc else None, "y_cur": list(Y[d.year]) if d.year in Y else None,
            "nyears": len(Y)}

def current(pid, surface, d):
    """Comme le relais aujourd'hui : 20 derniers matchs corrigés selon l'adversaire, + 52 semaines sur la surface."""
    H = [m for m in recent[pid] if m["spw"] is not None]
    last = H[-20:]
    if len(last) < 3: return None
    spw = sum(m["spw"] - opp_adj(m["ork"]) for m in last) / len(last)
    rr = [m["rpw"] - opp_adj(m["ork"]) for m in last if m["rpw"] is not None]
    rpw = sum(rr) / len(rr) if rr else None
    off_s = spw - sum(m["spw"] for m in last) / len(last)
    g = [m for m in H if m["surface"] == surface and (d - m["d"]).days <= 365]
    s52 = None
    if len(g) >= 3:
        sv = sum(m["sv"] for m in g); s52 = {"n": len(g), "spw": sum(m["sv"] * m["spw"] for m in g) / sv + off_s,
                                              "rpw": (sum(m["rv"] * m["rpw"] for m in g if m["rpw"] is not None) / max(1, sum(m["rv"] for m in g if m["rpw"] is not None))) if any(m["rpw"] is not None for m in g) else None}
    def bl(k, base):
        if base is None: return None
        if not s52 or s52.get(k) is None: return base
        return (s52["n"] * s52[k] + 6 * base) / (s52["n"] + 6)
    s1 = [m["s1"] for m in H[-21:] if m["s1"]]
    ace = sum(m["ace"] for m in last) / max(1, sum(m["sv"] for m in last))
    cy = [m for m in list(recent[pid])[-21:] if m["d"].year == d.year]
    ml21 = (sum(math.log(min(1000, max(1, m["ork"])) / 100) for m in cy) / len(cy)) if cy else None
    return {"spw": bl("spw", spw), "rpw": bl("rpw", rpw), "n": len(last), "ace": ace, "ml21": ml21, "n21": len(cy),
            "s1o_recent": (sum(1 for x in s1 if x >= 10) / len(s1)) if len(s1) >= 3 else None,
            "s1m_recent": (sum(s1) / len(s1)) if len(s1) >= 3 else None}

OUT = []
rnd = random.Random(11)
for r in rows:
    w, l = r["winner_id"], r["loser_id"]; surface = r["surface"] or "Hard"; d = r["_d"]
    bo5 = (r.get("best_of") or "3").strip() == "5"; score = r["score"] or ""; sets = sets_of(score)
    wrk, lrk = fnum(r["winner_rank"]) or 500, fnum(r["loser_rank"]) or 500
    st = {}
    for me, opp, pid in (("w_", "l_", w), ("l_", "w_", l)):
        sv, f1, f2 = fnum(r[me + "svpt"]), fnum(r[me + "1stWon"]), fnum(r[me + "2ndWon"])
        osv, of1, of2 = fnum(r[opp + "svpt"]), fnum(r[opp + "1stWon"]), fnum(r[opp + "2ndWon"])
        ok = bool(sv) and f1 is not None and f2 is not None and sv > 0
        ook = bool(osv) and of1 is not None and of2 is not None and osv > 0
        st[pid] = {"sv": sv if ok else 0, "sw": (f1 + f2) if ok else 0, "rv": osv if ook else 0, "rw": (osv - of1 - of2) if ook else 0,
                   "sg": fnum(r[me + "SvGms"]) or 0, "bf": fnum(r[me + "bpFaced"]) or 0, "bs": fnum(r[me + "bpSaved"]) or 0,
                   "og": fnum(r[opp + "SvGms"]) or 0, "obf": fnum(r[opp + "bpFaced"]) or 0, "obs": fnum(r[opp + "bpSaved"]) or 0,
                   "ace": fnum(r[me + "ace"]) or 0, "ok": ok and ook}
    # ---- ligne de sortie (avant mise à jour)
    if d.year >= 2008 and sets and r["round"] not in ("Q1", "Q2", "Q3") and st[w]["ok"] and st[l]["ok"]:
        flip = rnd.random() < .5
        A, B = (l, w) if flip else (w, l)
        cA, cB = career(A, d, surface), career(B, d, surface)
        nA, nB = current(A, surface, d), current(B, surface, d)
        if cA and cB and nA and nB and nA["rpw"] is not None and nB["rpw"] is not None:
            s1 = sets[0]; gw = sum(a for a, b in sets); gl = sum(b for a, b in sets)
            ek = lambda p: (elo[p] + selo[(p, surface)]) / 2
            OUT.append({"date": d, "year": d.year, "surface": surface, "bo5": int(bo5), "A": A, "B": B,
                        "wname": r["winner_name"], "lname": r["loser_name"], "flip": flip,
                        "cA": cA, "cB": cB, "nA": nA, "nB": nB, "elo_diff": ek(A) - ek(B),
                        "rankA": lrk if flip else wrk, "rankB": wrk if flip else lrk,
                        "y_spwA": st[A]["sw"] / st[A]["sv"], "y_spwB": st[B]["sw"] / st[B]["sv"], "svA": st[A]["sv"], "svB": st[B]["sv"], "acesA": st[A]["ace"], "acesB": st[B]["ace"],
                        "wid": w, "lid": l,
                        "set1": s1[0] + s1[1], "set1_tb": int(s1[0] + s1[1] == 13), "set1_winA": int((s1[0] > s1[1]) != flip),
                        "total": gw + gl, "gamesA": gl if flip else gw, "winA": int(not flip)})
    # ---- mise à jour
    if "W/O" in score.upper() or not score.strip(): continue
    tbs = [(a, b) for a, b in (sets or []) if a + b == 13]
    for pid, opp_rank, won in ((w, lrk, True), (l, wrk, False)):
        s = st[pid]; c = [0.0] * len(K)
        c[I["m"]] = 1
        if s["ok"]:
            c[I["sv"]], c[I["sw"]], c[I["rv"]], c[I["rw"]] = s["sv"], s["sw"], s["rv"], s["rw"]
            c[I["sg"]], c[I["hd"]] = s["sg"], s["sg"] - (s["bf"] - s["bs"])
            c[I["rg"]], c[I["br"]] = s["og"], s["obf"] - s["obs"]
            c[I["ace"]] = s["ace"]
            lk = math.log(min(1000, max(1, opp_rank)) / 100)   # force de l'adversaire (log du classement)
            c[I["lo"]], c[I["lr"]] = s["sv"] * lk, s["rv"] * lk
        c[I["lm"]] = math.log(min(1000, max(1, opp_rank)) / 100)
        if sets:
            c[I["tbn"]] = len(tbs); c[I["tbw"]] = sum(1 for a, b in tbs if (a > b) == won)
            gwn = sum(a for a, b in sets); gls = sum(b for a, b in sets)
            c[I["gw"]], c[I["gl"]] = (gwn, gls) if won else (gls, gwn)
            c[I["st"]] = len(sets)
            c[I["s1n"]] = 1; c[I["s1g"]] = sets[0][0] + sets[0][1]; c[I["s1o"]] = int(sets[0][0] + sets[0][1] >= 10)
        for tgt in (year[pid][d.year], surfc[pid][surface]):
            for i in range(len(K)): tgt[i] += c[i]
        recent[pid].append({"d": d, "surface": surface, "ork": opp_rank, "sv": s["sv"], "rv": s["rv"], "ace": s["ace"] if s["ok"] else 0,
                            "spw": s["sw"] / s["sv"] if s["ok"] else None, "rpw": s["rw"] / s["rv"] if s["ok"] else None,
                            "s1": (sets[0][0] + sets[0][1]) if sets else None})
    for E, N, kw, kl in ((elo, elo_n, w, l), (selo, selo_n, (w, surface), (l, surface))):
        ew = 1 / (1 + 10 ** ((E[kl] - E[kw]) / 400))
        E[kw] += 250 / ((N[kw] + 5) ** 0.4) * (1 - ew); E[kl] -= 250 / ((N[kl] + 5) ** 0.4) * (1 - ew); N[kw] += 1; N[kl] += 1
pickle.dump({"K": K, "HL": HL, "rows": OUT}, open("/home/claude/data/career.pkl", "wb"))
print("lignes :", len(OUT), file=sys.stderr)
