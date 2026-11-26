# Journal des décisions de conception

Chiffres mesurés par backtest sur l'historique du marché (383 ticks, du 08/09 au 26/11/2026),
chaque produit isolé (1 000 d'argent + 1 000 unités au départ), ordre exécuté au tick suivant,
sans frais. Référence = « ne rien faire ».

| Date | Décision | Choix | Justification mesurée |
|---|---|---|---|
| 2026-11-26 | Confidentialité | Lire uniquement mon portefeuille et ceux des 3 baselines | Le leaderboard annonce les positions individuelles comme privées (alors qu'elles sont lisibles dans le dépôt public) |
| 2026-11-26 | Signal A | Retour à la moyenne, z-score, fenêtre 48 | +8 415 vs rien faire (14 215 vs 5 800) ; pire baisse −21,3 % vs −24,3 % ; fenêtre ≈ durée du cycle (~48 ticks) |
| 2026-11-26 | Signal B | Garder (signal 0), vente finale éventuelle en manuel | Le z-score perd dans tous les réglages (−5 963 à −102) : la tendance haussière domine |
| 2026-11-26 | Signal C | Retour à la moyenne, z-score, fenêtre 20 | +5 542 vs rien faire (7 764 vs 2 223) ; pire baisse −24,7 % vs −58,4 % ; exploite le cycle rapide (~22 ticks) malgré la baisse |

Formule du signal : `z = (prix − moyenne_N) / écart-type_N`, `signal = −z / 2`, borné à [−1, +1].

Limites connues : fenêtres choisies sur les mêmes données que le test (risque de surapprentissage),
pas de frais de transaction, impact de nos ordres sur le prix supposé nul.
