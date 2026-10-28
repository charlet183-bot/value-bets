# Poids du modèle « Gagnant »

Appris sur l'historique ATP 2008-2026 (base TML-Database, format Jeff Sackmann).

1. `features.py` : recalcule les stats de chaque joueur telles qu'elles étaient avant chaque match.
2. `train.py` puis `variants.py` : régression logistique, test sur 2024-2026, apport de chaque groupe.
3. `final.py` : version finale à signes imposés, entraînée sur toutes les saisons → `model.json` (`final.coefs`).

Les coefficients de `final.coefs` sont recopiés dans `index.html` (constante `LEARNED`).

## Jeux et aces (onglets Jeux et Comparer)

4. `games.py` : pour chaque match, prévision de l'ancien et du nouveau calcul (point par point, service face au retour adverse).
5. `eval_games.py` : test sur 2024-2026 et correction logistique par marché (1er set, total, jeux d'un joueur) + correction des aces → `games_model.json`.

Les coefficients sont recopiés dans `index.html` (constantes `GCAL` et `ACECAL`).

## Toute la carrière + 1er set (27/10/2026)
- `career.py` → reconstitue, avant chaque match ATP 2008-2026, les stats de toute la carrière saison par saison (comme les tableaux Tennis Abstract « tour-years », « chall-years », « career-splits ») et les 20 derniers matchs.
- `career_eval.py` → meilleure pondération : demi-vie 1 an, 300 points d'a priori, écart de surface réduit (k = 30), mélange 70 % carrière / 30 % récent. Erreur sur le service du match suivant (test 2024-26) : 50,4 → 47,4 (×10⁻⁴), base 60,2.
- `set1.py` → distribution complète des jeux du 1er set (modèle ordinal). Erreur sur la distribution 1,799 → 1,737 ; ligne 9,5 : ~57 % de bon sens. Habitudes des joueurs, Elo et cote Pinnacle n'ajoutent presque rien.
- `career_all.py` → total de jeux, jeux par joueur (61,8 → 62,5 %), aces (3,18 → 3,10 d'erreur), vainqueur par le service (0,651 → 0,628).
- `learned2.py` → poids du vainqueur réappris avec le service carrière : 64,8 → 65,1 % sur 2024-26.

## Saison en cours seulement (28/10/2026, à la demande)
Les calculs utilisent la saison en cours (circuit + Challengers, 600 points d'a priori) mélangée à 50 % avec la forme récente et la surface, au lieu de toute la carrière.
Test 2024-26 (`season_eval.py`, `*_saison.py`) : erreur service 48,1 (carrière 47,4 ; ancienne appli 50,4). Faible en janvier-mars (peu de matchs).
1er set : distribution 1,740 (ancienne 1,799) ; jeux par joueur 62,6 % ; aces 3,14 ; vainqueur 64,9 %.

## Force des adversaires (28/10/2026)
`oppadj_eval.py` : stats de la saison corrigées de 0,025 × log(classement adverse / 100). Circuit principal (test 2024-26) : 48,3 → 48,1. Effet plus fort attendu pour les joueurs qui jouent des Challengers (non mesurable, pas de données Challenger).

## Retour selon la puissance du serveur (28/10/2026)
`return_power.py` : 124 000 services, puissance = taux d'aces du serveur. Effet personnel du retourneur face aux gros serveurs : corrélation passé → futur de 0,01 (bruit). Erreur test 2024-26 : 51,00 (base) → 50,88 (pente commune) → 50,88 (profil sur 21 matchs, poids 0) / 50,87 (toute la carrière). Non intégré au calcul ; affiché à titre indicatif.
