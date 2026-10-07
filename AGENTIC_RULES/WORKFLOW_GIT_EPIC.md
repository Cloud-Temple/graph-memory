# EPIC, Project et releases

Charger ce complément si la tâche utilise un EPIC, un GitHub Project ou un train
RC. Réutiliser le mode de pilotage et de livraison existant. Pour un nouveau
projet, la PR vers `main` suffit par défaut ; un train RC répond à un besoin
d'intégration ou de validation de version explicite, pas au seul nombre de clients.

## EPIC et traçabilité

Un EPIC définit l'objectif, le périmètre, les critères de réussite et la cible
de livraison. Ses issues enfants portent les problèmes concrets ; les PR liées
portent l'exécution. Garder visibles les enfants actifs et la PR de release
éventuelle, sans recopier toutes les discussions dans l'EPIC.

Utiliser la relation native de sous-issue GitHub lorsqu'elle est disponible.
Une mention textuelle ne suffit pas à établir cette relation. Vérifier les
enfants réels, avec pagination si nécessaire ; un total seul ne prouve pas leur
identité. Une PR reste liée à une issue, elle ne devient pas une sous-issue.

Fermer l'EPIC quand ses critères sont atteints et que ses enfants nécessaires
sont terminés ou explicitement sortis du périmètre avec justification.

## Project : un état par objet

Ne pas créer un Project ou des champs supplémentaires sans besoin de suivi.
Si un Project existe, lire sa structure et utiliser son champ `Status` ; ne pas
créer des labels de statut concurrents. Employer les valeurs ci-dessous si
elles existent, ou leur équivalent documenté, sans réorganiser le board au passage.

| Statut | Sens |
| --- | --- |
| `Plan` | Cadrage actif ; jamais le backlog. Un EPIC global n'hérite pas du statut d'un enfant. |
| `Todo` | Travail identifié, non commencé. |
| `Draft` | Livrable concret en brouillon, sans exécution ou correction active. |
| `In Progress` | Travail ou correction en cours, y compris après une revue bloquante. |
| `Review` | Livrable prêt dont seule la revue reste à faire, sans correction bloquante à traiter. |
| `Blocked` | Progression impossible sans un événement externe identifié. |
| `Awaiting release` | Travail vérifié et intégré, en attente du jalon de livraison défini ci-dessous. |
| `Done` | Critères de fin de l'objet atteints ; préciser si clôturé sans livraison ou abandonné. |

Une issue et sa PR ont des états distincts. Une issue peut rester en cours
pendant la revue de sa PR. Une PR fusionnée est terminée, mais cela ne prouve
pas que la fonctionnalité est livrée en production.

Après un constat bloquant, remettre la PR en `In Progress`. Après correction
et vérification, signaler explicitement qu'elle est prête à être relue ; une
demande de relecture suffit, sans commentaire supplémentaire imposé. L'attente
du relecteur utilise `Review`. Réserver `Blocked` à une dépendance externe qui
empêche réellement d'avancer.

Les champs `Workstream`/`Lot`, `Risk` et `Priority`, s'ils existent, décrivent
respectivement le domaine, la nature du risque et l'ordre de traitement.
Respecter leurs valeurs existantes. Ne pas publier les arbitrages privés ou
les données clients. Distinguer responsable de pilotage et personne assignée.

Pour une mise à jour du Project : lire l'état, appliquer seulement les changements
nécessaires, puis vérifier par une lecture distincte. Ces deux lectures paginent,
et elles peuvent être tronquées de la même façon : la vérification confirmerait
alors la troncature. Un board est par ailleurs écrit par plusieurs mains, et une
relecture immédiate ne prouve que l'instant. Prouver ces lectures complètes, et
relire les objets touchés une seconde fois en fin de lot, ou en dernier quand la
mise à jour tient en une écriture, selon `WORKFLOW_ENGINEERING.md`. Avant un lot
important, vérifier le quota disponible. Après une erreur partielle, relire l'état et
reprendre les seules opérations manquantes. Ne pas déplacer les objets hors
périmètre pour faire du rangement. Signaler les écarts pertinents non corrigés.

## Train RC, seulement s'il est utilisé

1. Définir le périmètre du train et le jalon signifiant « livré » : intégration
   dans `main`, publication d'une version ou déploiement, selon le projet.
   Ne pas changer un train en cours pour adopter le flux nominal.
2. Partir d'une branche `rc/vX.Y.Z` pour les PR du train. Elle reste une branche
   d'intégration ; elle ne devient pas la branche par défaut. Chaque merge de
   PR vers cette branche exige le GO humain de `MAIN_RULES.md`.
3. Référencer les issues avec `Refs #N`. Une issue dont tout le travail est
   vérifié et intégré peut attendre la livraison ; une PR fusionnée est `Done`.
4. Préparer une PR RC vers `main` avec les changements, les vérifications,
   les risques de mise à niveau et la liste des issues réellement résolues.
5. Valider le contenu final sur son SHA avec la CI requise et les contrôles
   d'intégration pertinents. Inscrire la preuve dans la PR, par exemple
   `RC-VALIDATION: OK <branche> <sha>`, avec résultats et risques résiduels.
   Le marqueur résume une preuve ; il ne la remplace pas.
6. Tout nouveau commit invalide la validation de la RC : vérifier les contrôles
   sur le nouveau SHA et mettre à jour la preuve avant le GO et le merge.
   La validation technique n'ajoute pas de demande de permission humaine.
7. Après merge autorisé vers `main`, vérifier les clôtures et l'état de livraison.
   Créer les tags et releases depuis des commits présents dans `main`, si la
   livraison le prévoit. Ne pas publier une release depuis la branche RC.
   Retirer la branche RC devenue inutile, sans la réutiliser pour un autre train.

### Issues à clôturer

Recenser toutes les PR intégrées au train, puis les issues qu'elles référencent.
Dédupliquer et **vérifier les critères d'acceptation de chaque issue**. Une
dépendance, une mention contextuelle, un travail partiel ou l'appartenance au
train ne suffit pas à autoriser sa clôture.

Placer `Closes #N` dans la PR vers `main` uniquement pour les issues dont les
critères sont alors atteints. Si une issue exige une publication ou un déploiement,
garder `Refs #N` jusqu'à la preuve de ce jalon et la fermer à ce moment. Vérifier
les liens et clôtures réels quel que soit le mode de merge autorisé par le dépôt.

### Hotfix

Une urgence peut passer par une PR directe vers `main`, avec le problème,
les vérifications et les risques documentés. Le GO du merge reste nécessaire,
sans second marqueur d'approbation spécifique au hotfix. Reporter ensuite le
correctif dans toute RC active concernée par une PR dédiée, puis actualiser
la validation RC et les notes de livraison.
