# Discipline d'ingénierie

Ce fichier définit les contrôles techniques. L'autorisation humaine est définie
uniquement dans `MAIN_RULES.md` ; Git et les releases ont leurs propres fichiers.

## Cycle proportionné au risque

Comprendre le besoin et lire les éléments concernés, faire la modification
minimale, vérifier le résultat, revoir le diff final, puis livrer dans le cadre
du workflow applicable. Adapter les contrôles à l'effet réel de la modification :

| Changement | Vérification et revue |
| --- | --- |
| Texte ou présentation sans effet de comportement | Relecture locale et contrôle du rendu ou des liens concernés. |
| Comportement applicatif courant | Tests pertinents et une revue indépendante du diff final. |
| Données persistées, autorisations, secrets, CI, suppression, migration, production, contrat public ou règles de pilotage | Revue indépendante du plan avant exécution, puis du résultat ; vérification des invariants et du retour arrière. |

Une correction de faute dans une règle reste éditoriale. Un changement de
configuration qui modifie l'exécution ne l'est pas. En cas de doute sur l'impact,
examiner le composant concerné avant de choisir les contrôles.

Le code qui compte va dans un fichier. Une commande d'inspection jetable reste
une commande, et une vérification ponctuelle aussi. Deux choses basculent dans un
fichier, même temporaire, et pour deux raisons indépendantes.

Le code qui sera rejoué ou qui modifie un état, parce qu'il doit être relu :
passé au shell dans un bloc de texte, il n'apparaît dans aucun diff, ne se teste
pas séparément et échappe aux contrôles de ce tableau. Et la commande longue,
quel que soit son avenir, parce qu'elle se fait tronquer : une commande tronquée
échoue à moitié, ou pire, réussit à moitié.

Le premier motif porte sur ce que quelqu'un devra relire, le second sur ce qui
arrive à l'envoi. Ni l'un ni l'autre ne se mesure en nombre de lignes, mais une
commande assez longue pour qu'on se demande si elle passera entière a déjà
répondu à la question.

Ne pas dupliquer la même revue avant et après commit : associer la revue à une
révision précise, par SHA ou diff conservé. Après une modification, revoir le
delta et relancer les contrôles qu'il affecte. Un simple changement de SHA sans
changement de contenu n'impose pas de répéter toute la revue ; la validité des
contrôles d'intégration doit néanmoins être vérifiée.

## Revue indépendante

Le pilote produit le changement ; le relecteur le conteste dans une session
distincte, en lecture seule. Le relecteur est un autre modèle que le pilote.
`REVIEWERS.md` donne le modèle à employer pour chaque fournisseur disponible et
les contraintes d'invocation ; `review.reviewer_provider` de `project.config.yml`
désigne celui que ce dépôt utilise. Ne pas présenter une auto-relecture comme une
validation indépendante, ni affirmer une diversité de modèles non vérifiée.

Fournir au relecteur le besoin, le plan ou le diff réel, les éléments de contexte
nécessaires, les vérifications effectuées et les risques à challenger. Pour une
tâche déléguée, vérifier aussi que le livrable répond au mandat initial.

Conserver le verdict original avec l'identité effectivement fournie par l'outil,
la révision, les constats, leur gravité et les limites de la revue. Vérifier les
constats contre les faits ; corriger les blocages ou expliquer avec preuves
pourquoi ils ne s'appliquent pas. Une préférence de style ne devient pas un blocage.

Le relecteur et sa commande proviennent d'une configuration vérifiée. Ne pas
déduire le modèle exécuté d'un nom écrit dans ces règles. Employer une invocation
non interactive et bornée ; ne pas contourner un refus d'outil ou de confidentialité.

Si la revue indépendante est indisponible, le signaler et poursuivre la
préparation locale réversible avec une auto-relecture déclarée, uniquement si
le prérequis mémoire de `MAIN_RULES.md` est satisfait. Les changements
qui exigent une revue indépendante restent non prêts au merge ou à l'exécution
sur un système partagé tant que cette revue manque. Aucun verdict ne s'invente.

## Réglages et publics

Une valeur qui gouverne un comportement en exploitation se règle : délai
d'expiration, nombre de tentatives, taille de page, seuil. Elle vit dans la
configuration ou l'environnement, avec un défaut explicite. Une constante qui
définit un format reste dans le code : constante de protocole, longueur d'un
condensat, code d'erreur. La frontière n'est pas « est-ce un nombre », c'est de
savoir si deux déploiements du même service auraient besoin de valeurs
différentes. Une valeur dont on imagine seulement qu'elle pourrait un jour
changer reste dans le code : le point 2 du contrat de travail continue d'y
interdire le paramètre sans besoin actuel. Un seuil figé, lui, se découvre en
production et pas en revue.

Une même capacité s'expose souvent à deux publics : un agent par les outils MCP,
une personne par une console, une interface en ligne de commande ou un shell.
Quand une capacité est livrée à l'un, poser la question de l'autre, et y
répondre : comment une personne inspecte ou administre ce qu'un agent vient
d'obtenir, et l'inverse. La question se pose, la duplication ne s'impose pas.
« Ce public n'a pas besoin de cette opération » est une réponse valide, à
condition d'avoir été posée et dite. Sans elle, une capacité n'existe que d'un
côté sans que personne l'ait décidé.

## Tests utiles

- Pour un défaut de comportement, reproduire l'échec puis montrer la réussite
  avec la correction. Si le test avant correction n'est pas réalisable, expliquer
  pourquoi et fournir la meilleure preuve disponible ; ne pas inventer un RED.
- Tester le résultat métier, les limites, les erreurs et les autorisations
  pertinentes. Pour l'état persistant, vérifier l'état final, pas seulement le
  code de retour. Un test qui passe sans la correction n'en prouve pas l'efficacité.
- Réutiliser les tests, fixtures et contrôles CI existants. Respecter les contrôles
  requis sans ajouter un dispositif de couverture pour satisfaire ces règles.
- Ne pas affaiblir un test ou un contrôle pour masquer une régression. Une évolution
  légitime du contrat doit être justifiée et revue avec les attentes correspondantes.
- Pour une modification documentaire, vérifier le contenu, les liens et les exemples
  concernés. Ne pas écrire de tests logiciels sans comportement à protéger.
- Rapporter les contrôles exécutés et leurs résultats réels. Après leur réussite,
  élargir les vérifications seulement si un changement ou un doute le justifie.

## État persistant et exploitation

- Une suppression ou un retrait d'état exige une intention explicite et une preuve
  provenant de l'autorité pertinente. Un accès refusé, un timeout ou une liste
  partielle ne prouve pas une absence. En cas d'incertitude, préserver l'état et
  produire un diagnostic exploitable, sans annoncer un succès trompeur.
- Une lecture paginée n'est exploitable qu'une fois prouvée complète. Demander une
  limite supérieure au volume attendu, puis comparer le nombre d'éléments rendus
  au total annoncé par la source. S'ils diffèrent, la lecture est tronquée et rien
  ne s'en conclut, ni diagnostic, ni vérification après écriture. Une limite
  choisie à la main parce qu'elle paraissait large se fait rattraper par la
  croissance : c'est la comparaison qui protège, pas le nombre.
- Une vérification ne vaut que ce que son moment garantit. Relire juste après
  avoir écrit ne prouve que l'instant : la valeur peut se retrouver ailleurs
  ensuite, sans qu'aucune erreur soit rendue, qu'une autre main l'ait déplacée ou
  qu'un effet différé de la plateforme s'applique. Sur une ressource écrite par
  plusieurs sous un même jeton, l'audit ne tranche pas : toutes les écritures y
  portent le même acteur et le même type, et l'origine reste indéterminable.
  Relire une seconde fois avant de tenir la tâche pour finie, une fois les autres
  mutations passées. Cette seconde lecture ne protège que s'il s'est passé quelque
  chose entre les deux : enchaînée à la première, elle rend le même résultat.
  Quand rien ne suit la mutation, faire passer le reste du travail d'abord et
  relire en dernier ; à défaut, dire que la persistance n'est pas établie plutôt
  que de présenter la relecture immédiate comme une preuve qu'elle n'est pas.
- Distinguer une valeur non renseignée d'une valeur explicitement demandée.
  Ne pas laisser le mapping ou la sérialisation décider d'une suppression sur
  la base d'un signal ambigu.
- Avant une mutation importante, identifier la cible, les préconditions, l'impact,
  la vérification et le retour arrière possible. Vérifier l'état réel après
  l'action. Après un échec partiel ou un timeout, le relire avant de réessayer.
- Réutiliser les procédures d'exploitation existantes. Sur un système partagé,
  borner les sondes et arrêter une action si elle dégrade le service. Ne pas
  improviser de boucle de charge sur la production.
- Tracer une mutation réelle dans le journal opérationnel existant : date UTC,
  cible, action, résultat, preuve, impact résiduel et rollback ou suivi. Une
  préparation locale ou une inspection n'est pas une mutation de production.

Mettre à jour les documents affectés : README pour l'usage et l'installation,
DESIGN pour l'architecture et les contrats, changelog pour les changements
livrés. Lors d'une livraison, aligner VERSION, les exemples et les métadonnées
concernées. Distinguer version préparée, commit intégré, tag créé et release
effectivement publiée ; ne jamais annoncer l'un comme preuve de l'autre.
Ne pas ajouter automatiquement de signature d'outil ou de coauteur artificiel.
