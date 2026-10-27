exec(open("backtest.py").read().split("out = {")[0])
for book, nm in (("B365","Bet365"),("Avg","cote moyenne"),("Max","meilleure cote du marché")):
  for thr in (.02,.05):
    eW = B[book+"W"]*B.p_pin_w-1; eL = B[book+"L"]*(1-B.p_pin_w)-1
    s1 = (eW > thr) & (eW >= eL); s2 = (eL > thr) & (eL > eW)
    o = np.where(s1, B[book+"W"], np.where(s2, B[book+"L"], np.nan)); won = s1.values
    ok = (s1 | s2).values & ~np.isnan(o) & ~B.void.values
    pnl = np.where(won, 10*(o-1), -10.0)[ok]
    print(f"Onglet Value, avantage >{thr:.0%} ({nm:25s}) {ok.sum():4d} paris · cote moy {np.nanmean(o[ok]):.2f} · résultat {pnl.sum():+8.2f} € · ROI {pnl.sum()/(10*max(1,ok.sum())):+.1%}")
