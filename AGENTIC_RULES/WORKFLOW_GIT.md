# Git et GitHub

Appliquer ce workflow lorsqu'un dépôt Git existe. Dans un espace non versionné,
préserver les originaux et fournir des changements locaux vérifiables ; ne pas
créer un dépôt, des issues ou un Project uniquement pour appliquer la procédure.

## Branches et changements locaux

- Lire l'état réel : dépôt, branche, modifications locales, dépôt distant et
  branche cible. Préserver le travail existant et ne pas réassigner une issue
  déjà attribuée à quelqu'un d'autre.
- Travailler sur une branche dédiée à partir de la cible effective : `main`
  dans le flux nominal, ou la branche RC du train actif. Réutiliser une branche
  de travail appropriée si elle existe déjà.
- Aucun commit direct, merge local ni push forcé sur `main` ou une branche
  partagée d'intégration. Les merges de ces branches passent par une PR GitHub.
  Mettre à jour un `main` local propre avec `git pull --ff-only`.
- Avant la PR, récupérer les changements distants et examiner l'écart avec la
  cible. Rebase ou synchronisation seulement si nécessaire, selon la convention
  du dépôt. Ne pas réécrire une branche partagée. Sur sa propre branche publiée,
  vérifier qu'aucun travail tiers ne sera écrasé avant tout `--force-with-lease`.
- Faire des commits cohérents, limités au besoin. Inspecter le diff indexé pour
  exclure secrets, fichiers temporaires et modifications étrangères à la tâche.

## Issues, PR et publication

Une issue décrit le besoin et ses critères d'acceptation ; une PR décrit le
changement et ses vérifications. Réutiliser les issues existantes. Créer une
issue si le besoin nécessite un suivi distinct, pas systématiquement pour
une correction éditoriale autonome. Un EPIC conserve des issues enfants.

Dans le périmètre demandé, les commits, pushs, créations ou mises à jour d'issues
et de PR ne nécessitent pas de GO. Publier les commentaires et revues lorsque
la demande ou une consigne explicite du projet le prévoit ; ne pas transformer
une analyse locale en communication externe par défaut.

La PR présente le problème, le résultat obtenu, les tests réels et les risques
utiles au relecteur. Utiliser la langue publique du projet déclarée par `project.public_language`,
ou à défaut la langue de l'utilisateur. Garder les
arbitrages privés, données clients et informations confidentielles hors des
artefacts publics. Pour un corps multiligne en CLI, préférer `--body-file`.

Pour lier une issue :

- `Closes #N` dans le corps d'une PR vers la branche par défaut, uniquement si
  ses critères d'acceptation sont satisfaits par le changement.
- `Refs #N` ou `Related to #N` pour une dépendance, un contexte ou un travail
  partiel. Ces références ne constituent pas une preuve de résolution.
- Vers une branche RC, utiliser `Refs #N` ; réserver les clôtures à la PR de
  release vers `main`. Éviter les mots de clôture dans les commits intermédiaires.
- Ne pas placer un motif de clôture dans une explication qui veut justement
  laisser l'issue ouverte. Formulation sûre : `Refs #N — issue remains open`.
  Ne pas compter sur une négation ou un bloc de code pour neutraliser le motif.

Vérifier le lien réel sur GitHub ; un titre de PR ne suffit pas. Après merge,
vérifier les clôtures attendues et corriger une clôture manifestement accidentelle
en laissant une explication. Ne pas conclure sur la seule sortie de la commande.

## Revue de PR

Lire le diff, les discussions utiles depuis la dernière revue, les contrôles CI
et les critères de l'issue. Appliquer `WORKFLOW_ENGINEERING.md`. Formuler les
constats avec gravité, emplacement, effet et correction attendue. Conserver le
verdict et la révision examinée ; publier la revue lorsque cette publication
fait partie du mandat. Si la revue formelle est refusée, un commentaire autorisé
peut porter les mêmes constats, sans être présenté comme une approbation formelle.

Traiter comme bloquant tout constat qui exige une correction avant merge,
même sans marqueur particulier. Les discussions de code restent dans la PR ;
les changements de périmètre et de critères restent traçables dans l'issue.
Si un Project est utilisé, appliquer les statuts de `WORKFLOW_GIT_EPIC.md`.

## Merge : seul GO humain

Avant de solliciter le GO défini dans `MAIN_RULES.md`, rendre la PR concrètement
prête : contenu final, CI requise réussie, revue au niveau requis, blocages levés
et liens corrects. Fournir la PR, la cible, le SHA examiné et les limites utiles.

Après le GO, vérifier que le contenu et la cible n'ont pas changé, que les
contrôles applicables restent valides et que les protections GitHub sont
satisfaites. Merger sur GitHub sans contourner ces protections. Ne pas demander
un second GO pour le même merge inchangé ; ne pas étendre ce GO à une autre PR.

Après merge, vérifier la PR, les issues concernées et le Project s'il est utilisé.
Nettoyer uniquement les branches devenues inutiles, sans supprimer du travail
non intégré. Un merge ne prouve ni une publication ni un déploiement.
