# Journal des décisions de conception

Chiffres mesurés par backtest sur l'historique du marché (383 ticks, du 08/09 au 26/11/2026),
chaque produit isolé (1 000 d'argent + 1 000 unités au départ), ordre exécuté au tick suivant,
sans frais. Référence = « ne rien faire ».

| Date | Décision | Choix | Justification mesurée |
|---|---|---|---|
| 2026-11-26 | Confidentialité | Lire uniquement mon portefeuille et ceux des 3 baselines | Le leaderboard annonce les positions individuelles comme privées (alors qu'elles sont lisibles dans le dépôt public) |
| 2026-11-26 | Objectif (D2) | Gain maximal ; la pire baisse reste mesurée et affichée | Choix personnel ; le risque est suivi pour vérifier que le gain ne vient pas d'un pari dangereux |
| 2026-11-26 | Signal A | Retour à la moyenne, z-score, fenêtre 48 | +8 415 vs rien faire (14 215 vs 5 800) ; pire baisse −21,3 % vs −24,3 % ; fenêtre ≈ durée du cycle (~48 ticks) |
| 2026-11-26 | Signal B | Garder (signal 0), vente finale éventuelle en manuel | Le z-score perd dans tous les réglages (−5 963 à −102) : la tendance haussière domine |
| 2026-11-26 | Signal B (révisé) | Momentum, fenêtre 10 : +1 si prix > moyenne 10 ET moyenne en hausse (vs 5 ticks avant), −1 si prix < moyenne ET moyenne en baisse, sinon 0 | Intuition visuelle (cycle ~100 ticks sur tendance) testée : +3 512 vs garder sur 384 ticks, pire baisse −8,9 % vs −17,8 %. **Robustesse** : plateau de 3 à 10 (+3 450 à +3 786), descente régulière ensuite (moyenne 50 : −5 285, retard). **Hors échantillon** : fenêtre choisie sur ticks 1-192 (10), jugée sur 193-384 : +1 681, pire baisse −8,5 % vs −17,8 %. Oracle (triche, 25 ticks d'avance) : +10 907 → le momentum 20 en capte ~15 % (biais du recul) |
| 2026-11-26 | Signal C | Retour à la moyenne, z-score, fenêtre 20 | +5 542 vs rien faire (7 764 vs 2 223) ; pire baisse −24,7 % vs −58,4 % ; exploite le cycle rapide (~22 ticks) malgré la baisse |

Formule du signal : `z = (prix − moyenne_N) / écart-type_N`, `signal = −z / 2`, borné à [−1, +1].

## Vérifications en conditions réelles

| Date | Vérification | Résultat |
|---|---|---|
| 2026-11-27 | 1er tick tradé (385) : décision A +0,15 / B +0,695 / C −0,1 | Unités 1 015 / 1 069,5 / 990, argent 51,51 : exécuté exactement. L'argent ne tombe juste qu'avec les prix du tick 385 → **le marché exécute au prix du tick suivant**, hypothèse de tous les backtests confirmée |
| 2026-11-27 | Contrainte d'argent | Après l'achat de B, argent ≈ réserve : B « rien (pas d'argent) », C réduit à 1,4. Comportement attendu (backtest : 91 ticks « à court » sur 383) |

## Incidents

| Date | Incident | Cause | Correction | Vérification |
|---|---|---|---|---|
| 2026-11-26 | Run #2 en échec (étape commit/push) | 2 runs lancés à 6 s d'écart modifient la même ligne `updated_at` → conflit au `git pull --rebase` | `concurrency: auto-decide` (file d'attente) | Run #4 : a bien attendu #3… mais échoue encore |
| 2026-11-26 | Run #4 en échec malgré la file d'attente | Un run manuel est figé sur le commit du clic ; il récupérait l'ancienne version de `main` | `actions/checkout` avec `ref: main` | Runs #5 et #6 (double clic volontaire) : tous deux verts |

| 2026-11-27 | Cron très peu fiable : 2 runs seulement entre le 26/11 22:00 et le 27/11 09:49 (au lieu de ~38) ; tick 386 non journalisé | Créneaux :00/:30 surchargés chez GitHub | Cron déplacé à `7,37 * * * *` ; « Run workflow » manuel après un tick en secours | À observer |
| 2026-11-27 | La ligne « tick 384 » du journal indique « B gardé » alors que la décision exécutée au tick 385 était B +0,695 | `log_history` ignorait les runs suivants d'un même tick → le journal gardait le 1er calcul, pas le dernier | La ligne du tick est désormais **remplacée** par le dernier calcul | Ligne 384 corrigée le 27/11 avec la décision réellement lue par le marché : `decision.json` du commit d08ca3c (run #7 : A 0,15 / B 0,695 / C −0,1), phrase recalculée avec le code de production sur les prix ≤ 384 et argent 1 000 (décision recalculée = décision publiée, vérifié). Le dashboard contrôle à chaque tick ordres constatés = signal × 100 × ticks écoulés (✅/⚠️) |
| 2026-11-27 | Aucun run du bot entre 04:40 et ~15:00 (≈ 20 créneaux cron `7,37` sautés) → la décision du tick 385 a été appliquée 2 fois (ticks 386 et 387) alors que l'argent était remonté à 184,6 | Cron GitHub non garanti (best effort) | « Run workflow » manuel ; fiabilisation à décider | Visible dans le journal : ordres du tick 387 = 2 × décision |

Erreurs de l'IA relevées : doute injustifié sur l'existence de `actions/checkout@v7` (vérifié : v7.0.1 existe) ;
affirmation fausse « une fenêtre de 20 donne un signal quasi nul sur A » (mesuré : +7 713) ;
commandes Git données dans le mauvais ordre (pull avant commit) ; première correction du conflit incomplète ;
prédiction « le partage de l'argent coûtera cher » (mesuré : gain combiné ≈ somme des gains séparés) ;
journal qui gardait le premier calcul d'un tick au lieu du dernier ; tuile « décision en cours » lue dans le journal au lieu de decision.json ;
« (réduit : argent) » affiché à tort quand seul l'arrondi changeait le signal (0,15 vs 0,1501) ;
1re réponse à l'écart journal/exécution = un ⚠️ et une phrase longue qui cassait la mise en page, au lieu de corriger le journal depuis la source (historique Git) ;
journal du dashboard construit par run du bot au lieu de par tick du marché (tick 386 absent, ordres de 2 ticks cumulés en « vente 26 »).

Limites connues : fenêtres choisies sur les mêmes données que le test (risque de surapprentissage),
pas de frais de transaction, impact de nos ordres sur le prix supposé nul.
