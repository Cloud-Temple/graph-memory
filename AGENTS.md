# Instructions des agents

Les règles canoniques du projet se trouvent dans `AGENTIC_RULES/`. Elles sont
identiques dans tous les dépôts de la flotte et proviennent du dépôt
`Cloud-Temple/agentic-rules`. Les valeurs propres à ce dépôt se trouvent dans
`AGENTIC_RULES/project.config.yml`.

Au début de la session, lire `AGENTIC_RULES/MAIN_RULES.md`, puis
`AGENTIC_RULES/PROJECT_RULES.md` et effectuer le démarrage mémoire obligatoire.
Sans mémoire externe opérationnelle, arrêter le travail courant ; seules les
actions de rétablissement délimitées dans les règles mémoire restent permises.

Charger ensuite les autres compléments selon l'index et la tâche en cours.
Ne pas charger tous les fichiers par défaut ni relire ceux déjà présents et
à jour dans le contexte. Appliquer les règles pertinentes à l'ensemble du projet.

Ne pas modifier les fichiers de `AGENTIC_RULES/` dans ce dépôt, à l'exception de
`project.config.yml`. Toute autre modification est une dérive : elle fait échouer
le contrôle de conformité et sera écrasée à la prochaine mise à jour. Un besoin
d'évolution des règles passe par une PR sur `Cloud-Temple/agentic-rules`.
