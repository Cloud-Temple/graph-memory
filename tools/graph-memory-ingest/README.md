# graph-memory-ingest

CLI Go d’ingestion de fichiers vers **Graph Memory** ou **Hivemind**, porté depuis
`hivemind-private/tools/hivemind-ingest` le 31 août 2026. Il utilise MCP Streamable
HTTP, avec initialisation de session, réponses JSON ou SSE et suivi des jobs.

## Compilation et tests

Go 1.27 ou supérieur ; aucune dépendance au SDK Python du serveur.

```bash
cd tools/graph-memory-ingest
go build -o bin/graph-memory-ingest .
go test -count=1 ./...
go test -count=1 -race ./...
git diff --check
```

Le binaire fonctionne sous macOS et Linux. Aucun serveur n’est nécessaire pour
les tests unitaires : ils utilisent des serveurs HTTP locaux et des fichiers
temporaires. L’extraction réelle nécessite les accès LLM et embeddings du serveur.

## Configuration

Aucun endpoint, token ou espace n’est prédéfini. Priorité : **flags CLI**, puis
**variables d’environnement**, puis **fichier YAML**. Les variables `GRAPH_MEMORY_*`
priment sur leurs alias `HIVEMIND_*`.

```bash
export GRAPH_MEMORY_ENDPOINT='http://127.0.0.1:8070/mcp'
export GRAPH_MEMORY_TOKEN='votre-jeton'
export GRAPH_MEMORY_SPACE='ma-memoire'

./bin/graph-memory-ingest config test --json
./bin/graph-memory-ingest config get --json  # token masqué
```

Le fichier par défaut est `~/.config/graph-memory/config.yaml` :

```yaml
endpoint: http://127.0.0.1:8070/mcp
space_id: ma-memoire
batch_size_mb: 50
allowed_extensions: [.md, .txt, .json, .yaml, .yml, .py, .go, .ts, .js, .pdf]
watch_jobs: true
timeout_seconds: 600
threshold_other: 25
```

`config set --endpoint URL --space ID` enregistre la configuration atomiquement,
avec fichier en mode `0600` et répertoire en `0700`. Préférer une variable
d’environnement au flag `--token` pour éviter de laisser le jeton dans l’historique
shell ou la liste des processus.

| Variable `GRAPH_MEMORY_*` | Usage |
|---|---|
| `CONFIG_PATH` ou `CONFIG` | Chemin du fichier YAML |
| `ENDPOINT`, `TOKEN` | Connexion MCP et authentification Bearer |
| `SPACE_ID` ou `SPACE` | Mémoire Graph Memory / espace Hivemind |
| `ONTOLOGY` | Ontologie par défaut |
| `BATCH_SIZE_MB` | Taille maximale des données brutes d’un lot, défaut 50 Mio |
| `TIMEOUT_SECONDS` | Délai HTTP / suivi d’un job, défaut 600 s |
| `EXTENSIONS` | Extensions autorisées séparées par des virgules |
| `THRESHOLD_OTHER` | Tolérance d’évaluation de 0 à 100 %, défaut 25 |

Les mêmes suffixes existent sous `HIVEMIND_*`. Le fichier Hivemind n’est pas chargé
implicitement ; on peut le sélectionner explicitement avec `HIVEMIND_CONFIG_PATH`.

## Ingestion

```bash
# Simulation entièrement locale, sans connexion ni écriture serveur
./bin/graph-memory-ingest run --path ./docs --space ma-memoire --dry-run --json

# Ingestion et attente de la fin des jobs
./bin/graph-memory-ingest run --path ./docs --space ma-memoire --watch

# Création d’une mémoire Graph Memory avec une ontologie nommée du serveur
./bin/graph-memory-ingest run --path ./docs --space nouvelle-memoire \
  --create-space-if-missing --ontology technical --watch

# Automatisation : JSON uniquement sur stdout, sans interaction
./bin/graph-memory-ingest run --path ./docs --space ma-memoire \
  --non-interactive --json
```

Le scan est récursif. Il exclut les entrées cachées, les liens symboliques et les
fichiers spéciaux. Un contenu binaire n’est accepté que pour un format documentaire
explicitement autorisé : PDF, DOCX, XLSX, PPTX, ODT, ODS ou ODP. Les extensions hors
liste sont ignorées. Les fichiers dépassant la limite d’un lot sont refusés.

La déduplication SHA-256 s’applique aux fichiers locaux et au catalogue distant.
`--replace` la désactive. Une erreur de catalogue (droits, transport, réponse
invalide) interrompt l’exécution ; seul un outil explicitement absent permet de
continuer sans catalogue. Les documents dont l’ingestion a échoué restent éligibles.

Chaque lot envoie `content_base64`, `sha256`, `filename`, `source_path` et les
métadonnées de format. Le hash est recalculé sur les octets envoyés. La taille du
lot désigne les données **avant** base64 : prévoir environ un tiers de plus, plus
l’enveloppe JSON, dans les limites HTTP du serveur et du proxy.

| Fonction | Hivemind | Graph Memory standalone |
|---|---|---|
| Vérification / création | `space_info` / `space_create` | `memory_list` / `memory_create` |
| Catalogue | `long_document_list` paginé | `document_list` sans pagination |
| Lot | `long_ingest_async` | `memory_ingest_batch_async` |
| Jobs actifs | `long_ingest_list` | `ingest_job_list` |
| Suivi | `long_ingest_status`, sinon `long_ingest_job_status` | `ingest_job_status` |

Les replis ne sont tentés que si l’outil précédent est absent. Un refus d’accès ou
un échec serveur ne déclenche pas une deuxième soumission. `--ontology` choisit
l’ontologie lors de la **création d’une mémoire Graph Memory** ; il ne modifie pas
une mémoire existante. Hivemind utilise l’ontologie de son espace.

Chaque fichier doit recevoir un résultat unique. Les chemins inconnus, réponses
manquantes, noms ambigus, job IDs dupliqués et statuts inconnus sont refusés.
Les statuts `succeeded`, `completed`, `skipped`, `changed_skipped`, `queued`,
`running`, `failed`, `error`, `queue_full` et `cancelled` sont traités explicitement.

Avec `--no-poll` (ou `--watch=false`), le code 0 signifie que les soumissions ont
été acceptées. Les jobs encore en attente ne sont **pas** comptés dans
`total_succeeded`. Un timeout client n’annule pas les jobs déjà soumis au serveur.
Le terminal affiche la progression ; `--json` fournit un rapport structuré sans
séquences ANSI. `NO_COLOR` désactive les couleurs.

## Évaluation d’ontologie

`eval`, `test` et `test-ontology` désignent la même commande :

```bash
./bin/graph-memory-ingest eval --path ./docs --ontology ./ontology.yaml \
  --sample-size 5 --threshold-other 20 --json
```

L’échantillon correspond aux premiers fichiers éligibles, dans l’ordre du scan.
Le CLI crée un espace `tmp-eval-...`, valide le YAML par `ontology_validate`,
soumet les documents avec `options.ontology_yaml`, suit les jobs, puis lit
`long_status(include_graph=true)`. Il calcule la proportion d’entités **Other +
Generic**, détaille les types et propose d’enrichir l’ontologie si le seuil est
dépassé. Une distribution absente ou incohérente est une erreur, jamais un score
positif par défaut.

L’espace créé est supprimé après succès ou erreur, sauf avec `--keep-memory`.
Un échec de nettoyage est signalé avec l’identifiant de l’espace à reprendre.
`--space` peut fixer le nom de cet espace ; il doit être nouveau pour éviter de
mélanger les statistiques avec un corpus existant. `--timeout` borne l’évaluation
complète ; le nettoyage dispose ensuite de son propre délai de 30 secondes.

**Limite d’intégration constatée au portage :** Graph Memory standalone ne fournit
pas ce workflow (`space_create`, `ontology_validate`, `long_status`). Le backend
Hivemind consulté ignore encore `options.ontology_yaml` et n’expose pas
`graph_stats.entity_types`. Le module CLI et ses tests sont portés, mais une
évaluation réelle exige que le backend applique le YAML demandé et fournisse la
distribution des types. La version consultée est refusée au moment du calcul,
sans produire de faux score. Ce portage ne modifie pas le serveur Hivemind.

## Protocole et codes de retour

L’initialisation suit `initialize` puis `notifications/initialized`. Les versions
acceptées sont strictement `2024-11-05` et `2024-10-07`, conformément à la source
transmise. Le client conserve `mcp-session-id` et `mcp-protocol-version`. Les flux
SSE peuvent contenir des notifications avant la réponse et plusieurs lignes
`data:` par événement ; le client termine à réception du résultat correspondant.
La réponse est limitée à 16 Mio. La reconnexion avec rejeu automatique et l’ancien
transport SSE à deux endpoints ne sont pas pris en charge.

| Code | Signification |
|---|---|
| 0 | Succès ; avec `--no-poll`, soumission acceptée seulement |
| 1 | Arguments ou fichiers invalides |
| 2 | Connexion, authentification ou vérification serveur impossible |
| 3 | Échec d’ingestion, d’évaluation, de nettoyage ou seuil dépassé |
