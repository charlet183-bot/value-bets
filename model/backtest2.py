exec(open("backtest.py").read().split("out = {")[0])
def run(mask, book, lab):
    s = B[mask].copy()
    s["o"] = np.where(s.won, s[book+"W"], s[book+"L"]); s = s[s.o.notna() & ~s.void]
    pnl = np.where(s.won, 10*(s.o-1), -10.0)
    print(f"{lab:62s} {len(s):4d} paris · réussite {s.won.mean():.1%} · cote moy {s.o.mean():.2f} · résultat {pnl.sum():+8.2f} € · ROI {pnl.sum()/(10*len(s)) if len(s) else 0:+.1%}")
pick_odds = lambda book: np.where(fav_w, B[book+"W"], B[book+"L"])
for book, nm in (("Avg","cote moyenne"),("Max","meilleure cote")):
    edge = pick_odds(book) * B.p_pick - 1
    run(agree & (B.p_pick > .70) & (edge > .02), book, f"D'accord >70 % ET value >2 % ({nm})")
    run(agree & (edge > .02), book, f"D'accord, toute proba, value >2 % ({nm})")
# value sur l'un ou l'autre joueur selon l'avis combiné (règle de l'onglet Gagnant)
for book, nm in (("Avg","cote moyenne"),("Max","meilleure cote")):
    eW = B[book+"W"]*B.p_comb_w-1; eL = B[book+"L"]*(1-B.p_comb_w)-1
    s1 = (eW > .02) & (eW >= eL); s2 = (eL > .02) & (eL > eW)
    tmp = B.copy(); tmp["won"] = True; m1 = s1.values
    o = np.where(s1, B[book+"W"], np.where(s2, B[book+"L"], np.nan)); won = np.where(s1, True, False)
    ok = (s1 | s2).values & ~np.isnan(o) & ~B.void.values
    pnl = np.where(won, 10*(o-1), -10.0)[ok]
    print(f"{'Règle de l onglet Gagnant : value >2 % sur l avis combiné ('+nm+')':62s} {ok.sum():4d} paris · réussite {won[ok].mean():.1%} · cote moy {np.nanmean(o[ok]):.2f} · résultat {pnl.sum():+8.2f} € · ROI {pnl.sum()/(10*ok.sum()):+.1%}")
