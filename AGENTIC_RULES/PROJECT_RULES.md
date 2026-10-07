# Mémoire du projet

## Configuration unique

**Live Memory est obligatoire** : mémoire externe persistante de travail,
accessible en lecture et en écriture. Les fichiers locaux et le chat ne la
remplacent pas. Graph Memory complète cette mémoire par un index documentaire.

Les identifiants ne sont pas écrits dans ces règles. Ils sont lus dans
`AGENTIC_RULES/project.config.yml`. La notation `<clé>` ci-dessous désigne la
valeur de cette clé dans ce fichier ; ne jamais appeler un service avec la
notation littérale, une valeur vide, un `TO_FILL` ou un identifiant deviné.
La copie de ces règles ne configure aucun serveur MCP et ne crée aucun espace.
Le serveur qui héberge réellement l'espace est déterminé au démarrage, selon
« Trouver l'espace du projet ». La création éventuelle de l'espace a lieu à ce
moment, selon « Espace mémoire absent ».

| Usage | Serveur MCP | Identifiant |
| --- | --- | --- |
| Mémoire de travail | serveur effectif, voir ci-dessous | `space_id="<memory.live.space_id>"` |
| Index sémantique durable | `<memory.graph.server>` | `memory_id="<memory.graph.memory_id>"` |

Utiliser ces espaces et leur casse exacte. Ne jamais substituer un espace
personnel ou celui d'un autre projet en cas d'erreur. Les secrets de connexion
restent dans la configuration MCP ou le coffre ; ne pas les recopier ici.
Utiliser un service mémoire autorisé pour les données du projet. N'y écrire
ni secrets, ni données personnelles de clients, ni extraits sensibles de
production ; conserver seulement le contexte utile et des références autorisées.

Pour les appels `space_*`, `bank_*` et `live_*`, cibler explicitement le serveur
effectif retenu par « Trouver l'espace du projet ». Une fois ce serveur retenu,
ne pas sélectionner un outil homonyme sur un autre serveur. Vérifier les noms
et paramètres dans le schéma réellement exposé par le serveur choisi avant
le premier appel. Les notations ci-dessous décrivent ses arguments, pas des
commandes shell. Si `bank_list` n'est pas disponible, utiliser `bank_read_all`
plutôt qu'inventer un appel ou un chemin de fichier.

La banque résume le travail courant. Graph Memory retrouve des documents et
relations historiques. Confirmer les faits utiles dans leur source canonique
avant d'agir. Le focus d'une ancienne session ne remplace pas la demande actuelle.

Si le projet n'utilise pas cet index, porter `disabled` sur les clés
`memory.graph.*` de `project.config.yml` et ignorer la section Graph Memory.
Ne pas retirer cette section des règles : leur contenu est identique dans tous
les dépôts, la variation passe par la configuration. Live Memory et son
protocole restent obligatoires dans tous les cas.

## Trouver l'espace du projet

`memory.live.space_id` nomme l'espace, pas le serveur qui l'héberge. Plusieurs
serveurs Live Memory peuvent être configurés dans une session, et un même
identifiant peut vivre sur plusieurs d'entre eux avec des contenus différents.
Résoudre le serveur effectif avant tout le reste.

Chercher l'identifiant **exact** de `memory.live.space_id` sur chaque serveur
Live Memory exposé dans la session, `<memory.live.server>` compris, avec
l'inspection d'espace que le serveur expose : `space_list` quand il énumère les
espaces accessibles, sinon `space_info` sur l'identifiant. Vérifier ces noms dans
le schéma réellement exposé, comme pour `bank_list`. Ne pas dériver l'identifiant
ni en essayer une variante, et ne pas s'arrêter au premier serveur qui répond.

Un serveur qui oppose un **refus d'accès** ne répond pas « absent » : il ne
distingue pas un espace inexistant d'un espace hors des droits du jeton. Ne pas
le compter comme « pas trouvé ». Le signaler, et tant qu'un refus n'est pas
élucidé, ne rien créer : appliquer « Mémoire absente ou en panne ». Créer après
un refus produirait le doublon vide que cette section existe pour éviter. Un
refus sur un serveur n'empêche pas, en revanche, de retenir un espace trouvé sans
ambiguïté sur un autre : il interdit la création, pas la rétention.

Selon ce que la recherche établit :

1. Trouvé sur plusieurs serveurs : **demander à l'utilisateur lequel retenir**,
   et attendre sa réponse. Deux espaces homonymes portent deux mémoires
   distinctes ; en choisir un revient à ignorer l'autre, et ce choix n'appartient
   pas à l'agent.
2. Trouvé sur un seul serveur : lire d'abord sa description et son
   propriétaire, et les dire. S'ils désignent le projet, ou ne le contredisent
   pas, retenir ce serveur sans rien demander, même si ce n'est pas celui que
   `memory.live.server` déclare. S'ils désignent manifestement un autre projet,
   ce n'est pas l'espace cherché mais une collision d'identifiant : **arrêter**,
   au sens défini ci-dessous. « Ne jamais substituer un espace personnel ou celui
   d'un autre projet » vaut ici comme ailleurs, et un identifiant qui coïncide ne
   vaut pas identité. Description et propriétaire tous deux vides ne contredisent
   rien : retenir, en disant qu'aucune information d'identité n'était lisible.
3. Trouvé sur aucun serveur, sans refus d'accès en suspens : appliquer
   « Espace mémoire absent ». La création a lieu sur
   `<memory.live.server>`.

Une collision arrête le travail avec la portée d'un blocage mémoire : arrêt du
travail courant y compris local, aucune édition de code, opération Git ou action
de livraison. Elle n'en partage pas le remède. Ne rien créer, ne pas relancer la
recherche et ne pas demander l'ouverture d'un accès à cet espace : il n'y a rien
à élucider, l'identité est tranchée, et c'est `memory.live.space_id` qui désigne
le mauvais espace. Seule une personne peut corriger ce champ.

Le serveur retenu est le serveur effectif ; toute la suite de la session le
cible, lui et pas un autre. Dire lequel a été retenu, dans tous les cas.

Une fois l'espace accessible, comparer le serveur effectif à
`memory.live.server`. S'ils diffèrent, le dire, et corriger cette clé dans
`project.config.yml`, qui est le seul fichier de `AGENTIC_RULES/` qu'un dépôt a
le droit de modifier. Une configuration qui se trompe sur l'emplacement de la
mémoire ferait retomber chaque session suivante dans la même recherche.

Cette correction change le serveur que cibleront les sessions suivantes : c'est
un changement de configuration qui modifie l'exécution, au sens de
`WORKFLOW_ENGINEERING.md`, et non une retouche éditoriale. Elle désigne où vivent les
données persistées du projet, donc elle relève de la dernière ligne du tableau de
`WORKFLOW_ENGINEERING.md` : revue indépendante du plan avant exécution, puis du
résultat. Elle passe par une **PR dédiée**, jamais par un commit direct et jamais
mêlée à la branche d'une autre tâche, que `WORKFLOW_GIT.md` demande de garder
limitée à son besoin. Tant qu'elle n'est pas fusionnée, la recherche se refait à
chaque session ; c'est le prix de la traçabilité, pas un défaut à contourner.

## Au démarrage

1. Résoudre le serveur effectif selon « Trouver l'espace du projet », puis
   vérifier qu'il est disponible et que les droits sur l'espace couvrent la
   lecture et l'écriture de notes. Ne pas confondre présence d'un outil et accès
   réel à cet espace. Une session de revue indépendante, qui n'écrit jamais,
   s'arrête à la lecture : voir l'exception nommée dans `MAIN_RULES.md`.
2. Lire `space_rules(space_id="<memory.live.space_id>")` une fois pour connaître la structure.
3. Charger le contexte courant et les décisions utiles. Utiliser `bank_read_all`
   si la banque est compacte ; sinon `bank_list` puis `bank_read` sur le contexte
   actif et les fichiers pertinents. Ne pas supposer une arborescence non vérifiée.
4. Lire les notes récentes avec `live_read(space_id="<memory.live.space_id>")`. Si le résultat est
   limité, remonter aux notes utiles à la tâche avec les filtres de l'outil.
5. Après une perte effective de contexte ou une consolidation, recharger ce
   qui manque ou a changé ; ne pas recommencer à chaque message.

Lors de l'installation, vérifier l'écriture avec une première note utile de
cadrage du projet, puis la relire. Une banque initialement vide est acceptable
si l'espace est accessible et si ce contexte initial est enregistré. Un espace
introuvable sur tous les serveurs relève de la section « Espace mémoire absent ».
Ne pas créer de notes de test à chaque session ; réutiliser une preuve d'accès
valide et tenir compte immédiatement de toute erreur ultérieure.

## Espace mémoire absent

Cette section s'applique quand la recherche de « Trouver l'espace du projet »
n'a rien trouvé sur aucun serveur et qu'aucun refus d'accès ne reste en suspens.
Un refus non élucidé interdit la création, quelle que soit la suite. Un dépôt fraîchement mis en conformité
déclare un `memory.live.space_id` qui n'existe encore nulle part. Ce cas n'est
pas une panne, et il ne doit pas arrêter le travail.

Une session de revue indépendante ne crée pas cet espace : elle n'écrit jamais,
et `MAIN_RULES.md` nomme cette exception. Pour elle seule, un espace introuvable
sur tous les serveurs arrête la revue avec la portée d'un blocage mémoire. Elle
n'en partage le remède d'aucune section, ni celui-ci ni celui de « Mémoire
absente ou en panne » : tous deux supposent une écriture. Elle signale l'absence
et s'arrête sans rendre de verdict. La création revient à une session ordinaire.

Le serveur ne distingue pas un espace absent d'un espace existant hors des
droits du jeton : les deux rendent le même refus d'accès. C'est la tentative de
création qui lève l'ambiguïté, parce qu'elle n'écrase jamais un espace existant.

Quand l'espace configuré n'est pas accessible, tenter `space_create` avec
l'identifiant **exact** de `memory.live.space_id` et une description tirée du
projet. Ne jamais inventer un identifiant, ni le dériver, ni y ajouter un
suffixe : il est renseigné par une personne. Laisser les `rules` vides pour que
le serveur applique sa structure par défaut ; elles sont immuables après
création, et une structure improvisée resterait définitive.

Lire ensuite la réponse en entier, pas seulement son statut. Un espace existant
n'est pas forcément celui d'un tiers : le serveur répare l'accès du jeton qui
l'a créé, et l'annonce dans un champ distinct du statut. Sur Live Memory ces
champs sont aujourd'hui `creator_access_repair` et `creator_access_pending` ;
vérifier les noms réellement exposés par le serveur avant de s'y fier.

- Accès créateur annoncé comme non assuré : l'espace existe mais le droit n'est
  pas encore écrit. Le serveur demande alors de rejouer exactement le même
  appel ; le faire **une fois**. Si la réserve persiste, arrêter et signaler.
- « Existe déjà » sans réparation d'accès annoncée : l'espace appartient à un
  autre jeton. **Arrêter** et demander l'ouverture de l'accès. Ne pas contourner
  en créant une variante de l'identifiant.
- Création réussie, ou « existe déjà » avec réparation d'accès annoncée :
  l'espace est utilisable par ce jeton. Poursuivre le démarrage normal.
- Le serveur réclame des `rules` faute de modèle par défaut : c'est un défaut de
  configuration du serveur, pas un espace manquant. **Arrêter** et le signaler.
  Ne pas improviser une structure pour débloquer l'appel.
- Tout autre échec, ou une réponse qu'on ne sait pas classer : appliquer la
  section suivante. L'ambiguïté conduit à l'arrêt, jamais à une interprétation
  par défaut.

Une réponse encourageante ne vaut pas accès. Une issue « poursuivre » reprend le
démarrage à son étape 1 ; c'est la lecture, puis la note de cadrage écrite et
relue, qui établissent l'accès, pas le retour de la création.

Cette création ne porte que sur l'espace configuré, et s'arrête après cette
seconde tentative. Aucun réessai en boucle.

## Mémoire absente ou en panne

Si Live Memory n'est pas configuré, si son contexte ne peut pas être chargé ou
si une écriture requise échoue, **signaler le blocage et arrêter le travail
courant**, même local ou réversible. Cette règle s'applique au démarrage comme
en cours de session. Ne pas continuer sur le seul chat, cache ou dépôt local.

Pendant ce blocage, les seules actions permises dans le mandat sont :
lire les consignes et paramètres d'accès mémoire sans exposer les secrets,
vérifier la connectivité et les accès aux serveurs Live Memory concernés par la
recherche, corriger sa configuration
d'accès si demandé, puis vérifier une écriture utile et sa relecture. Aucune
édition de code métier, opération Git/GitHub ou action de livraison ne relève
de cette exception. Un refus d'accès n'est pas la preuve d'un espace inexistant :
les seules actions admises pour trancher sont la recherche sur les autres
serveurs décrite en « Trouver l'espace du projet », puis la tentative de création
bornée décrite en « Espace mémoire absent ». Ne pas changer d'espace, élargir les
droits ni réessayer en boucle. Si une intervention externe est nécessaire, l'indiquer.

Une session de revue indépendante ne mène que celles de ces actions qui
n'écrivent rien. Elle ne corrige aucune configuration, ne tente aucune création
et ne vérifie aucune écriture, quelle que soit la cause du blocage, y compris un
refus d'accès non élucidé. Elle le signale et s'arrête sans rendre de verdict :
voir l'exception nommée dans `MAIN_RULES.md`.

Après rétablissement, recharger le contexte et les notes utiles avant de
reprendre. Après un timeout d'écriture, vérifier si la note existe déjà avant
de soumettre un doublon. Le contexte de la session peut conserver la note dont
l'écriture a échoué, uniquement pour achever cette écriture après vérification
des faits dans leur source. Ce n'est pas une mémoire de remplacement ni une
reconstruction de l'historique perdu. Enregistrer cette note avant de poursuivre ;
ne pas annoncer une sauvegarde qui n'a pas eu lieu.

## Notes et taille de la banque

Écrire une note courte avec `live_note` lorsqu'une décision, un fait durable,
un blocage, un jalon ou une prochaine action doit survivre à la session.
Une note porte un sujet, sa source et les conséquences utiles. Employer les
catégories de l'outil : `observation`, `decision`, `progress`, `issue`, `todo`,
`insight`, `question`. Toujours renseigner `space_id="<memory.live.space_id>"`.

Éviter les sorties de commande intégrales, le polling, les secrets et les
doublons de documents. Si le fait est déjà documenté, un lien suffit lorsqu'il
change le travail en cours. Ne pas créer de note sans information nouvelle.

Garder le contexte actif limité aux priorités, décisions ouvertes, blocages et
prochaines actions. Le journal de progression conserve des jalons récents ;
l'historique détaillé reste dans les documents canoniques. Suivre les budgets
de taille définis par `space_rules`, sans multiplier les seuils dans ces règles.

## Consolidation

Consolider sur demande de mise à jour de la banque, ou lorsque les nouvelles
notes rendent son résumé obsolète. Écrire d'abord les éléments durables encore
absents. Aucun GO humain supplémentaire n'est requis et une fin de session
n'impose pas à elle seule une consolidation.

Appeler `bank_consolidate(space_id="<memory.live.space_id>")` une seule fois, puis suivre la
réponse du service. Un accusé `queued` ou `running` signifie « consolidation
demandée », pas « consolidation terminée ». Si le service demande de retourner
sans polling, respecter cette consigne. Après un timeout ambigu, vérifier le
statut disponible avant de soumettre un doublon.

L'écriture directe dans la banque est réservée à une tâche de maintenance
identifiée, avec sauvegarde du contenu à modifier. Le flux normal passe par
les notes et la consolidation.

## Graph Memory

Cibler le serveur `<memory.graph.server>` avec l'identifiant
`memory_id="<memory.graph.memory_id>"`, jamais un outil homonyme d'un autre serveur.

- Rechercher dans Graph Memory pour retrouver un incident, une décision passée
  ou une relation entre documents. Si le chemin est déjà connu, lire directement
  le document ; si le graphe est indisponible, faire une recherche locale ciblée
  uniquement tant que Live Memory reste opérationnelle.
- Utiliser les résultats comme pointeurs. Relire la source canonique pertinente
  et signaler une divergence qui affecte le travail.
- Ingérer seulement les documents canoniques stables utiles au besoin, via le
  pipeline existant s'il existe. Garder un `source_path` stable ; éviter de
  réingérer un contenu inchangé et vérifier le statut après un timeout.
- Ne jamais ingérer la banque, le contexte actif ou le journal de progression.
  Ne pas déclencher `graph_push`, `graph_connect` ni modifier la liaison entre
  services comme effet secondaire d'une consolidation. Une tâche portant sur
  cette liaison suit son propre périmètre. L'ontologie appartient au service.

Les mutations d'exploitation sont tracées dans le journal opérationnel du
projet s'il existe, selon la discipline d'ingénierie. Ne pas imposer un chemin
MCO ou un espace mémoire provenant d'un autre projet.
