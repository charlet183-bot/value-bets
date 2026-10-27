# Poids du modèle « Gagnant »

Appris sur l'historique ATP 2008-2026 (base TML-Database, format Jeff Sackmann).

1. `features.py` : recalcule les stats de chaque joueur telles qu'elles étaient avant chaque match.
2. `train.py` puis `variants.py` : régression logistique, test sur 2024-2026, apport de chaque groupe.
3. `final.py` : version finale à signes imposés, entraînée sur toutes les saisons → `model.json` (`final.coefs`).

Les coefficients de `final.coefs` sont recopiés dans `index.html` (constante `LEARNED`).
