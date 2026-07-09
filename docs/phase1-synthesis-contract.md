# Phase 1 Synthesis Contract

> Source: stable advisor `advisor run review --advisor fable --single-ok` on the two SOTA reports.
> Artifact: `/home/sina/.advisor/sessions/20260709T204615-review`.
> This is the input contract for Phase 2 benchmark design.

# advisor review

## Résultats

### fable — ok — claude-fable-5

## Blockers
- **Gel du juge avant toute exécution Phase 2.** sonnet et fable apparaissent déjà comme synthétiseurs *dans les runs SOTA eux-mêmes* (sections « Vérification des synthèses » des deux rapports) et seront à la fois advisors candidats et juges potentiels. Sans configuration juge figée (modèle + version exacte, prompt, température, rubrique, hash) stockée hors des sorties de dev **avant** le premier run candidat, tous les résultats Phase 2 sont invalidés par le self-preference bias — mesurable et non corrélé à la capacité du modèle (run 1, E8/E14).
- **Les métriques spécifiques code-review sont non sourcées.** Le run 2 a une couverture quasi nulle (pollution de requête « harness » → Harness.io) : recall/precision/actionabilité des sections Blockers et Minimal fix plan n'ont **aucun** appui SOTA. Le contrat doit les étiqueter « hypothèses de conception à valider localement », jamais « méthodes établies ». Les présenter comme sourcées serait une erreur irréversible de fondation.
- **Aucun chiffre mono-source comme paramètre de design.** 31,5 % de réduction SPB (E8), 10–30 pp de shift positionnel (E13, blog faible), 35 gaps TRACE (E10) : interdits pour dimensionner échantillons ou seuils. Le budget de 2 runs @sota-deep est consommé — ces trous se comblent par pilote local, pas par re-recherche.

## Important issues
- **Aucun golden set de défauts de code injectés n'existe dans l'evidence** (confirmé par les deux runs). Il doit être construit localement ; la validité même des défauts injectés comme proxy de vrais défauts est une hypothèse, pas un acquis.
- **Direction du position bias non consensuelle** (run 1, E13) : certains modèles préfèrent la première option, d'autres la seconde. Pas de correction fixe possible → swap-and-average obligatoire par paire, pas globalement.
- **Ambiguïté E9/E17** (JudgeBiasBench vs CALM, même taxonomie à 12 biais ?) : citer la taxonomie génériquement, sans attribution ferme.
- **Le run 2 [E7] décrit une séparation de rôles pour la *génération*, pas générateur/juge** — extrapolation marquée faible dans le rapport lui-même. Ne pas la citer comme précédent du protocole anti-SPB.

## Preferences
- Scorers déterministes d'abord (présence/parsabilité des sections, mapping Blockers↔manifeste de défauts), LLM-judge en second — run 2 [E3] est la seule source medium topicale.
- Pattern `benchmarks/frozen/` pour geler golden set + config juge (run 2 [E7], inspiration faible mais peu coûteuse).
- Reporting coût/latence par cas dès le premier pilote, pas en rétrofit.

## Minimal fix plan
1. Rédiger et committer le contrat ci-dessous dans le repo (ex. `docs/phase1-synthesis-contract.md`), avec les caveats mono-source et le statut « hypothèse » explicite sur chaque métrique.
2. Créer `benchmarks/frozen/judge-v1.json` (modèle, version, prompt, params, hash) avant tout run candidat ; toute modification = nouvelle version, jamais d'édition en place.
3. Construire un mini golden set (10–20 cas) : diffs propres + défauts injectés étiquetés (id, localisation, sévérité) dans un manifeste séparé des cas.
4. Implémenter le scorer déterministe (parse des 4 sections, matching manifeste) et le harnais swap (chaque comparaison paire dans les deux ordres).
5. Pilote de calibration : ~20 cas jugés par juge LLM figé + labels humains (auteur), calcul de l'accord ; seuil d'acceptation du juge fixé *avant* de voir les résultats.

---

## Directions retained
1. **Architecture harness** : golden set figé → runner déterministe → évaluateurs mixtes (assertions déterministes + LLM-judge) → comparateur baseline → rapport par cas + gate (run 2, E2/E3).
2. **Golden set local à défauts injectés**, en transposant le concept d'injection de JudgeBiasBench (run 1, E9) des biais de présentation vers des défauts de code — transposition assumée comme originale, non sourcée.
3. **Positionally consistent accuracy** comme métrique centrale du juge (run 1, E10) + swap-and-average avec tie forcé si non robuste à l'inversion (run 1, E13).
4. **Séparation stricte générateur/juge** + validation du juge contre labels humains sur échantillon (run 1, E11/E12 — source vendor, mais peu coûteuse à appliquer).
5. **Mesure SPB par paires de qualité contrôlée** (run 1, E8) adaptée aux sorties advisor.

## Testable hypotheses
- **H1 (position)** : l'inversion d'ordre des deux sorties change le verdict du juge sur une fraction mesurable des paires ; ampleur inconnue localement (les 10–30 pp du store sont indicatifs seulement).
- **H2 (SPB)** : fable/sonnet en juge préfèrent la sortie de leur propre famille à qualité appariée (taux de préférence ≠ 50 % sur paires contrôlées).
- **H3 (proxy déterministe)** : les checks déterministes (Blockers présents, étapes du fix plan parsables et vérifiables) corrèlent suffisamment avec le jugement humain d'actionabilité pour servir de gate bon marché.
- **H4 (recall)** : les défauts injectés de sévérité connue sont rappelés dans la section Blockers à un taux mesurable qui discrimine les configurations d'advisor.
- **H5 (capacité ≠ biais)** : le juge le moins cher, après débiaising par swap, n'est pas significativement moins fiable que le plus cher (test local du résultat contre-intuitif de E8).

## Proposed metrics
Toutes en statut **hypothèse**, à valider au pilote (étape 5) :
- **Recall@Blockers** : part des défauts injectés signalés comme bloquants ; **precision** : part des blockers annoncés qui mappent au manifeste.
- **Exactitude de sévérité** : bon classement bloquant/important/préférence vs label du manifeste.
- **Actionabilité du Minimal fix plan** : proportion d'étapes parsables et vérifiables (fichiers référencés existants, étapes ordonnées) ; spot-check humain sur échantillon.
- **Positionally consistent accuracy** pour tout jugement pairwise.
- **Score SPB** : écart à 50 % de préférence pour la sortie de sa propre famille à qualité appariée.
- **Accord juge-humain** (kappa ou % brut) sur le set de calibration.
- **Coût/latence par cas** et **coût par vrai blocker détecté**.

## Required tooling
- Générateur de golden set : injection de défauts étiquetés dans des diffs propres, manifeste séparé (id, localisation, sévérité).
- Scorer déterministe des 4 sections du format advisor + matching manifeste.
- Harnais de swap (double ordre, calcul de consistance, tie forcé).
- Config juge gelée versionnée sous `benchmarks/frozen/`, hors arbre de dev.
- Traces JSONL par appel avec coût/latence.
- Set de calibration humain (~20 cas) — labellisé par l'auteur, biais assumé et documenté.

## Risks of self-evaluation bias
- **Double rôle candidat/juge (sonnet/fable)** : risque principal, cf. blocker 1. Mitigation : matrice juge×candidat rapportée intégralement, juge cross-provider quand possible, config gelée.
- **Biais méta du concepteur** : le benchmark est conçu avec fable, et la rubrique risque d'encoder le style de sortie de la famille Claude — notamment le format Blockers/Important/Preferences est *le format maison de l'advisor*. Un check déterministe de conformité au format récompense structurellement les modèles in-family. Correction : séparer explicitement métrique de **conformité au format** et métrique de **qualité du contenu**, et ne comparer les providers que sur la seconde.
- **Golden set auteur-fabriqué** : les défauts choisis peuvent refléter ce que les modèles trouvent facilement. Mitigation partielle : dériver une partie des défauts de bugs réels du repo/historique.
- **Verbosity bias** : des fix plans plus longs risquent d'être surnotés par le juge LLM (run 1, E12) ; normaliser ou plafonner la longueur dans la rubrique.
- **Contamination** : aucune sortie de dev ne doit entrer dans le contexte du juge hors du cas évalué.

## Artifact/session path
- Evidence : `/home/sina/.advisor/sessions/20260709T200534-sota/report.md` (run 1, couverture utile) et `/home/sina/.advisor/sessions/20260709T202545-sota/report.md` (run 2, couverture quasi nulle — à citer uniquement pour l'architecture harness E2/E3 et la leçon de pollution de requête).
- Contrat à persister (recommandation informative) : `docs/phase1-synthesis-contract.md` dans advisor-dev, avec `benchmarks/frozen/` réservé aux artefacts gelés.
