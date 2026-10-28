"""Saison en cours seulement : comparaison avec la carrière et les 20 derniers matchs (test 2024-2026)."""
exec(open("career_eval.py").read().split("cur_pa = ")[0])
def est_season(c, key, mp):
    y = c["y_cur"]
    if key == "spw": num, den, prior = (y[I["sw"]], y[I["sv"]], AVG_S) if y else (0, 0, AVG_S)
    else: num, den, prior = (y[I["rw"]], y[I["rv"]], 1 - AVG_S) if y else (0, 0, 1 - AVG_S)
    return (num + mp * prior) / (den + mp)
cur_pa = np.array([r["nA"]["spw"] - r["nB"]["rpw"] + 1 - AVG_S for r in R]); cur_pb = np.array([r["nB"]["spw"] - r["nA"]["rpw"] + 1 - AVG_S for r in R])
print("20 derniers (ancienne appli)  test", round(score(cur_pa, cur_pb, test) * 1e4, 2))
pa = np.array([est_career(r["cA"], 1, 30, 300, "spw") - est_career(r["cB"], 1, 30, 300, "rpw") + .36 for r in R]); pb = np.array([est_career(r["cB"], 1, 30, 300, "spw") - est_career(r["cA"], 1, 30, 300, "rpw") + .36 for r in R])
print("carrière 70 % + récent 30 %    test", round(score(.3 * cur_pa + .7 * pa, .3 * cur_pb + .7 * pb, test) * 1e4, 2))
for mp in (100, 300, 600, 1000):
    sa = np.array([est_season(r["cA"], "spw", mp) - est_season(r["cB"], "rpw", mp) + .36 for r in R]); sb = np.array([est_season(r["cB"], "spw", mp) - est_season(r["cA"], "rpw", mp) + .36 for r in R])
    for a in (0, .3, .5):
        print(f"saison seule (a priori {mp}) + {int(a*100)} % récent   entr. {score(a*cur_pa+(1-a)*sa, a*cur_pb+(1-a)*sb, train)*1e4:.2f}  test {score(a*cur_pa+(1-a)*sa, a*cur_pb+(1-a)*sb, test)*1e4:.2f}")
# par période de la saison (test, a priori 300, sans récent)
sa = np.array([est_season(r["cA"], "spw", 300) - est_season(r["cB"], "rpw", 300) + .36 for r in R]); sb = np.array([est_season(r["cB"], "spw", 300) - est_season(r["cA"], "rpw", 300) + .36 for r in R])
mo = np.array([r["date"].month for r in R])
for lab, m in (("janv-mars", mo <= 3), ("avr-juin", (mo >= 4) & (mo <= 6)), ("juil-déc", mo >= 7)):
    print(lab, "saison", round(score(sa, sb, test & m) * 1e4, 2), "| carrière", round(score(.3*cur_pa+.7*pa, .3*cur_pb+.7*pb, test & m) * 1e4, 2), "| 20 derniers", round(score(cur_pa, cur_pb, test & m) * 1e4, 2))
