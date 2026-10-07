# Contexte du projet Graph Memory

Graph Memory fournit une mémoire documentaire multi-tenant, avec Neo4j pour
le graphe, Qdrant pour les vecteurs et S3 pour les octets originaux. La
[spécification](SPECIFICATION.md) et le
[design d'ingestion asynchrone](INGESTION_ASYNCHRONE.md) décrivent les contrats
actuels. Les jetons sont actuellement dans Neo4j ; la file d'ingestion reste
en mémoire vive, avec l'idempotence documentaire portée par Document.

[Mission #836](https://github.com/Cloud-Temple/mcp-mission/issues/836) rétablit
les prérequis du dépôt : règles canoniques, rattachement exact à sa mémoire de
travail existante et démarrage de session démontré. L'espace Live Memory
`graph-mem`, sur `my-live-memory`, appartient à Christophe Lesur. Cet identifiant
est un `space_id` de mémoire de travail, pas un `memory_id` Graph Memory.
Aucun identifiant d'index documentaire durable du dépôt n'est établi ; les deux
clés de cet index optionnel sont explicitement désactivées dans la configuration
du dépôt. Aucun espace, accès ou stockage serveur n'est modifié par ce lot.

[L'EPIC Mission #824](https://github.com/Cloud-Temple/mcp-mission/issues/824)
borne les futurs travaux PostgreSQL aux métadonnées applicatives pertinentes.
Il conserve Neo4j, Qdrant et S3, sans duplication d'autorité du graphe, du
catalogue documentaire ou des vecteurs. Les futurs lots propriétaires sont
actuellement suivis dans [Mission #839](https://github.com/Cloud-Temple/mcp-mission/issues/839)
et [Mission #840](https://github.com/Cloud-Temple/mcp-mission/issues/840).
Leur transfert et la vérification finale des dépendances/historiques relèvent
de la coordination Mission. Aucun développement métier PostgreSQL ne relève
de #836, ni ne peut être présenté comme déjà livré par ce rétablissement.

Les issues et PR du dépôt constituent le suivi propriétaire existant ; aucun
Project Graph Memory dédié n'a été établi. Les PR Makefile, logs, CI et Docker
ainsi que les mises à jour de dépendances ouvertes restent des travaux distincts,
sans intégration implicite.

La langue publique est le français, avec un README et des guides en anglais.
Les règles du dépôt et ses valeurs sont accessibles par
[AGENTS.md](../AGENTS.md) et [project.config.yml](../AGENTIC_RULES/project.config.yml).
