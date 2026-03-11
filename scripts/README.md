# 💻 MCP Memory CLI

Client en ligne de commande pour piloter le serveur **Graph Memory MCP**.

Deux modes d'utilisation :
- **Mode Click** (scriptable) : commandes directes avec arguments et options
- **Mode Shell** (interactif) : autocomplétion, historique, commandes contextuelles

---

## Prérequis

```bash
# Dépendances CLI
pip install httpx click rich prompt_toolkit

# Serveur MCP Memory démarré
docker compose up -d
```

## Configuration

### Variables d'environnement

La CLI utilise deux jeux de variables, par ordre de priorité :

| Priorité | Variable URL | Variable Token | Usage |
| :------: | ------------ | -------------- | ----- |
| **1** (recommandé) | `MCP_URL` | `MCP_TOKEN` | **Variables dédiées CLI** — n'interfèrent pas avec le `.env` serveur |
| 2 (fallback) | `MCP_SERVER_URL` | `ADMIN_BOOTSTRAP_KEY` | Compatibilité — lues aussi depuis le `.env` local |

**Défaut** : `http://localhost:8080` (URL) et `admin_bootstrap_key_change_me` (token).

Ou passez-les en options : `--url` et `--token`.

### Usage en développement (serveur local)

En dev, le `.env` à la racine contient `ADMIN_BOOTSTRAP_KEY` — la CLI le charge automatiquement via `load_dotenv()`.
Rien à configurer, ça marche directement :

```bash
python scripts/mcp_cli.py health
# → URL: http://localhost:8080, token lu depuis .env
```

### Usage en production (serveur distant)

Pour piloter un serveur de production, utilisez `MCP_URL` et `MCP_TOKEN` :

```bash
# Option 1 : Variables d'environnement (recommandé)
export MCP_URL=https://mcp-memory.example.com
export MCP_TOKEN=votre_bootstrap_key_production
python scripts/mcp_cli.py health

# Option 2 : Inline (ponctuel)
MCP_URL=https://mcp-memory.example.com \
MCP_TOKEN=votre_bootstrap_key_production \
python scripts/mcp_cli.py memory list

# Option 3 : Options CLI
python scripts/mcp_cli.py --url https://mcp-memory.example.com \
  --token votre_bootstrap_key_production health
```

> **⚠️ Important** : Ne mettez PAS `MCP_URL`/`MCP_TOKEN` dans le `.env` du serveur !  
> Le `.env` contient la config **serveur** (S3, Neo4j, etc.). Les variables CLI sont pour le **poste client**.  
> Si vous voulez un fichier de config CLI persistant, créez un `~/.env.mcp-cli` :
> ```bash
> # ~/.env.mcp-cli — Configuration CLI production
> MCP_URL=https://mcp-memory.example.com
> MCP_TOKEN=votre_bootstrap_key_production
> ```
> Puis sourcez-le : `source ~/.env.mcp-cli && python scripts/mcp_cli.py health`

### Pourquoi deux jeux de variables ?

Le `.env` local est chargé par `load_dotenv()` au démarrage de la CLI. Si vous avez un `.env` de développement avec `ADMIN_BOOTSTRAP_KEY=admin_bootstrap_key_change_me`, cette valeur serait utilisée pour la production — ce qui échouerait avec une erreur 401.

`MCP_URL` et `MCP_TOKEN` sont **prioritaires** et ne sont jamais dans le `.env` serveur, ce qui évite tout conflit dev/prod.

---

## Mode Click (scriptable)

Point d'entrée : `python scripts/mcp_cli.py [COMMANDE] [OPTIONS]`

### Serveur

```bash
# Identité et capacités du service (28 outils, 5 ontologies, services, mémoires)
python scripts/mcp_cli.py about

# État du serveur
python scripts/mcp_cli.py health
```

### Mémoires

```bash
# Lister les mémoires
python scripts/mcp_cli.py memory list

# Créer une mémoire (ontologie obligatoire)
python scripts/mcp_cli.py memory create JURIDIQUE -n "Corpus Juridique" -d "Contrats CT" -o legal

# Supprimer une mémoire (avec confirmation, ou -f pour forcer)
python scripts/mcp_cli.py memory delete JURIDIQUE
python scripts/mcp_cli.py memory delete JURIDIQUE -f

# Info / statistiques
python scripts/mcp_cli.py memory info JURIDIQUE

# Graphe complet (table ou JSON)
python scripts/mcp_cli.py memory graph JURIDIQUE
python scripts/mcp_cli.py memory graph JURIDIQUE -f json

# Entités par type (avec documents sources)
python scripts/mcp_cli.py memory entities JURIDIQUE

# Contexte d'une entité (relations, voisins, documents)
python scripts/mcp_cli.py memory entity JURIDIQUE "Cloud Temple"

# Relations par type (résumé ou détail)
python scripts/mcp_cli.py memory relations JURIDIQUE
python scripts/mcp_cli.py memory relations JURIDIQUE -t DEFINES
```

### Documents

```bash
# Lister les documents d'une mémoire
python scripts/mcp_cli.py document list JURIDIQUE

# Ingérer un document
python scripts/mcp_cli.py document ingest JURIDIQUE /path/to/contrat.docx

# Ingérer avec un chemin source personnalisé (ex: chemin relatif dans un repo)
python scripts/mcp_cli.py document ingest JURIDIQUE /path/to/contrat.docx --source-path "legal/contracts/contrat.docx"

# Ingérer un document (forcer la ré-ingestion)
python scripts/mcp_cli.py document ingest JURIDIQUE /path/to/contrat.docx -f

# Ingérer un répertoire entier (récursif)
# → source_path (chemin relatif) et source_modified_at (mtime) passés automatiquement
python scripts/mcp_cli.py document ingest-dir JURIDIQUE ./MATIERE/JURIDIQUE
python scripts/mcp_cli.py document ingest-dir JURIDIQUE ./docs -e '*.tmp' --force

# Supprimer un document
python scripts/mcp_cli.py document delete JURIDIQUE <document_id>
```

### Question/Réponse

```bash
# Poser une question sur une mémoire (réponse LLM)
python scripts/mcp_cli.py ask JURIDIQUE "Quelles sont les conditions de résiliation ?"

# Avec debug (affiche le JSON brut)
python scripts/mcp_cli.py ask JURIDIQUE "Quelles obligations ?" -d

# Limiter le nombre d'entités recherchées
python scripts/mcp_cli.py ask JURIDIQUE "Quelles garanties ?" -l 20

# Interrogation structurée SANS LLM (données brutes pour agents IA)
python scripts/mcp_cli.py query JURIDIQUE "réversibilité des données"
python scripts/mcp_cli.py query JURIDIQUE "durée du contrat" -l 20
```

### Stockage S3

```bash
# Vérifier la cohérence S3/graphe
python scripts/mcp_cli.py storage check
python scripts/mcp_cli.py storage check JURIDIQUE

# Nettoyer les orphelins S3 (dry run par défaut)
python scripts/mcp_cli.py storage cleanup
python scripts/mcp_cli.py storage cleanup -f   # Suppression réelle
```

### Ontologies

```bash
# Lister les ontologies disponibles
python scripts/mcp_cli.py ontologies
```

### 💾 Backup / Restore

```bash
# Créer un backup complet (graphe + vecteurs Qdrant + manifest)
python scripts/mcp_cli.py backup create JURIDIQUE
python scripts/mcp_cli.py backup create JURIDIQUE -d "Avant migration v2"

# Lister les backups (tous ou par mémoire)
python scripts/mcp_cli.py backup list
python scripts/mcp_cli.py backup list JURIDIQUE

# Restaurer depuis un backup S3 (la mémoire ne doit pas exister)
python scripts/mcp_cli.py backup restore "JURIDIQUE/2026-02-16T15-33-48"

# Télécharger un backup en archive tar.gz
python scripts/mcp_cli.py backup download "JURIDIQUE/2026-02-16T15-33-48"

# Télécharger AVEC les documents originaux (PDF, DOCX…) pour restore offline
python scripts/mcp_cli.py backup download "JURIDIQUE/2026-02-16T15-33-48" --include-documents

# Spécifier un fichier de sortie
python scripts/mcp_cli.py backup download "JURIDIQUE/2026-02-16T15-33-48" -o backup-juridique.tar.gz

# Supprimer un backup
python scripts/mcp_cli.py backup delete "JURIDIQUE/2026-02-16T15-33-48"
python scripts/mcp_cli.py backup delete "JURIDIQUE/2026-02-16T15-33-48" -f  # Sans confirmation

# Restaurer depuis une archive tar.gz locale (cycle complet offline)
python scripts/mcp_cli.py backup restore-file ./backup-juridique.tar.gz
```

**Options de `backup download` :**

| Option                  | Description                                                  | Exemple                            |
| ----------------------- | ------------------------------------------------------------ | ---------------------------------- |
| `--include-documents`   | Inclut les docs originaux (PDF, DOCX…) dans l'archive tar.gz | `--include-documents`              |
| `-o` / `--output`       | Chemin du fichier de sortie                                  | `-o backup-juridique.tar.gz`       |

> **Note v1.2.0** : Sans `--include-documents`, l'archive contient uniquement les métadonnées (graphe + vecteurs). Avec l'option, elle permet un restore complet hors-ligne via `restore-file`.

### 🔑 Tokens d'accès

```bash
# Lister les tokens actifs (affiche le hash complet pour copier-coller)
python scripts/mcp_cli.py token list

# Créer un token
python scripts/mcp_cli.py token create quoteflow
python scripts/mcp_cli.py token create quoteflow --email user@example.com
python scripts/mcp_cli.py token create quoteflow -p read,write -m JURIDIQUE,CLOUD
python scripts/mcp_cli.py token create admin-bot -p admin -e 30

# Révoquer un token (par hash, copiez-le depuis 'token list')
python scripts/mcp_cli.py token revoke <hash>
python scripts/mcp_cli.py token revoke <hash> -f   # Sans confirmation

# Autoriser un token à accéder à des mémoires
python scripts/mcp_cli.py token grant <hash> JURIDIQUE CLOUD

# Retirer l'accès à des mémoires
python scripts/mcp_cli.py token ungrant <hash> JURIDIQUE

# Remplacer toute la liste des mémoires (vide = accès à toutes)
python scripts/mcp_cli.py token set-memories <hash> JURIDIQUE CLOUD
python scripts/mcp_cli.py token set-memories <hash>   # Accès à toutes

# Promouvoir/rétrograder les permissions d'un token
python scripts/mcp_cli.py token promote <hash> admin,read,write  # Promouvoir en admin
python scripts/mcp_cli.py token promote <hash> read,write         # Rétrograder en client normal
python scripts/mcp_cli.py token promote <hash> read                # Passer en read-only
```

> **Note v1.6.0** : Un token avec la permission `admin` a les mêmes droits que la bootstrap key :
> il peut créer/révoquer des tokens, gérer les permissions, accéder à toutes les mémoires et utiliser les outils de diagnostic globaux.
> **Chaîne de confiance** : bootstrap → admin délégué → sous-tokens.

**Options de `document ingest` :**

| Option           | Description                                                  | Exemple                          |
| ---------------- | ------------------------------------------------------------ | -------------------------------- |
| `--source-path`  | Chemin source personnalisé (sinon: chemin absolu du fichier) | `--source-path "legal/CGA.docx"` |
| `-f` / `--force` | Forcer la ré-ingestion même si le hash existe                | `-f`                             |

> **Note v0.6.0** : `source_path` et `source_modified_at` (date de modification du fichier) sont passés automatiquement au serveur lors de l'ingestion. Cela permet au LLM de détecter si un fichier a changé sans télécharger le contenu.

**Options de `token create` :**

| Option                 | Description                    | Exemple                         |
| ---------------------- | ------------------------------ | ------------------------------- |
| `--email`              | Email du propriétaire          | `--email user@cloud-temple.com` |
| `-p` / `--permissions` | Permissions (virgules)         | `-p read,write,admin`           |
| `-m` / `--memories`    | Mémoires autorisées (virgules) | `-m JURIDIQUE,CLOUD`            |
| `-e` / `--expires`     | Expiration en jours            | `-e 90`                         |

---

## Mode Shell (interactif)

```bash
python scripts/mcp_cli.py shell
```

Fonctionnalités :
- **Tab** : autocomplétion des commandes
- **↑/↓** : historique persistant
- **Ctrl+A/E** : début/fin de ligne
- **Ctrl+W** : supprimer un mot
- **Ctrl+C** : annuler la ligne en cours

### Commandes disponibles

#### Navigation

| Commande             | Description                   |
| -------------------- | ----------------------------- |
| `about`              | Identité et capacités du service |
| `health`             | État du serveur               |
| `list`               | Lister les mémoires           |
| `use <id>`           | Sélectionner une mémoire      |
| `create <id> <onto>` | Créer une mémoire             |
| `info`               | Résumé de la mémoire courante |
| `graph`              | Graphe complet                |
| `delete [id]`        | Supprimer une mémoire         |

#### Documents

| Commande           | Description                                                                                                                    |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------ |
| `docs`             | Lister les documents                                                                                                           |
| `ingest <path>`    | Ingérer un fichier (`--force` pour ré-ingérer). Passe automatiquement `source_path` et `source_modified_at`.                   |
| `ingestdir <path>` | Ingérer un répertoire (`--exclude PATTERN`, `--confirm`, `--force`). Progression temps réel par fichier. Passe `source_path` (relatif) + `source_modified_at` par fichier. |
| `deldoc <id>`      | Supprimer un document                                                                                                          |

#### Exploration

| Commande           | Description                                                |
| ------------------ | ---------------------------------------------------------- |
| `entities`         | Entités par type (avec documents sources)                  |
| `entity <nom>`     | Contexte d'une entité (relations, voisins, documents)      |
| `relations [TYPE]` | Sans argument : résumé. Avec type : détail                 |
| `ask <question>`   | Poser une question (réponse LLM)                           |
| `query <question>` | Données structurées sans LLM (entités, chunks RAG, scores) |

#### Stockage

| Commande            | Description                  |
| ------------------- | ---------------------------- |
| `check [id]`        | Vérifier cohérence S3/graphe |
| `cleanup [--force]` | Nettoyer les orphelins S3    |
| `ontologies`        | Lister les ontologies        |

#### 🔑 Tokens

| Commande                                                  | Description                                      |
| --------------------------------------------------------- | ------------------------------------------------ |
| `tokens`                                                  | Lister les tokens actifs (hash complet copiable) |
| `token-create <client> [perms] [mémoires] [--email addr]` | Créer un token                                   |
| `token-revoke <hash>`                                     | Révoquer un token                                |
| `token-grant <hash> <mem1> [mem2]`                        | Ajouter des mémoires à un token                  |
| `token-ungrant <hash> <mem1> [mem2]`                      | Retirer des mémoires                             |
| `token-set <hash> [mem1] [mem2]`                          | Remplacer les mémoires (vide = toutes)           |
| `token-promote <hash> <perms>`                            | Modifier les permissions (admin, read, write)    |

#### 💾 Backup / Restore

| Commande                                 | Description                                                      |
| ---------------------------------------- | ---------------------------------------------------------------- |
| `backup-create [id] [description]`       | Créer un backup (mémoire courante ou spécifiée)                  |
| `backup-list [id]`                       | Lister les backups disponibles                                   |
| `backup-restore <backup_id>`             | Restaurer depuis un backup S3                                    |
| `backup-download <backup_id> [fichier]`  | Télécharger en tar.gz (`--include-documents` pour offline)       |
| `backup-delete <backup_id>`              | Supprimer un backup                                              |

> **`--include-documents`** : ajouter à `backup-download` pour inclure les documents originaux (PDF, DOCX…) dans l'archive. Sans cette option, seuls graphe + vecteurs sont inclus.

**Exemples backup dans le shell :**

```
🧠 JURIDIQUE: backup-create
🧠 JURIDIQUE: backup-create JURIDIQUE "Avant migration v2"
🧠 JURIDIQUE: backup-list
🧠 JURIDIQUE: backup-download JURIDIQUE/2026-02-16T15-33-48 --include-documents
🧠 JURIDIQUE: backup-restore JURIDIQUE/2026-02-16T15-33-48
🧠 JURIDIQUE: backup-delete JURIDIQUE/2026-02-16T15-33-48
```

**Exemples token dans le shell :**

```
🧠 no memory: tokens
🧠 no memory: token-create quoteflow --email user@example.com
🧠 no memory: token-create quoteflow read,write JURIDIQUE,CLOUD
🧠 no memory: token-revoke e4914bbb828ae97fa25c9adf0cc229273dff401b088cb2aaac900bfa1c650a24
🧠 no memory: token-grant e4914bbb... JURIDIQUE CLOUD
🧠 no memory: token-promote e4914bbb... admin,read,write
```

#### Configuration

| Commande    | Description                                                 |
| ----------- | ----------------------------------------------------------- |
| `limit [N]` | Voir/changer le nombre d'entités par recherche (défaut: 10) |
| `debug`     | Activer/désactiver le mode debug                            |
| `clear`     | Effacer l'écran                                             |
| `help`      | Aide                                                        |
| `exit`      | Quitter                                                     |

#### Option `--json` (v0.6.5)

Ajoutez `--json` à n'importe quelle commande de consultation pour obtenir le JSON brut du serveur **sans formatage Rich**. Idéal pour le scripting ou le pipe vers `jq`.

```bash
# Exemples dans le shell interactif
🧠 JURIDIQUE: query --json réversibilité des données
🧠 JURIDIQUE: ask --json quelles sont les garanties ?
🧠 JURIDIQUE: entities --json
🧠 JURIDIQUE: list --json
🧠 JURIDIQUE: --json graph          # --json peut être n'importe où
```

**Commandes supportées** : `list`, `info`, `graph`, `docs`, `entities`, `entity`, `relations`, `ask`, `query`.

---

## Architecture

```
scripts/
├── mcp_cli.py                   # Point d'entrée CLI (Click)
├── README.md                    # Ce fichier
├── README.en.md                 # Version anglaise
├── test_recette.py              # Recette complète (119 tests, 7 phases)
├── audit_ontology.py            # Audit qualité ontologie sur une mémoire
├── check_param_descriptions.py  # Vérification descriptions paramètres MCP
├── cli/                         # Package CLI
│   ├── __init__.py              # Configuration (URL, token)
│   ├── client.py                # Client Streamable HTTP vers le serveur MCP
│   ├── ingest_progress.py       # Progression ingestion temps réel (Rich Live)
│   ├── commands.py              # Commandes Click (mode scriptable)
│   ├── display.py               # Affichage Rich (tables, panels, graphe, tokens)
│   └── shell.py                 # Shell interactif prompt_toolkit
└── tests/                       # Modules de test (recette)
    ├── __init__.py              # Framework de test (helpers, compteurs)
    ├── test_system.py           # Tests système (health, about, ontology)
    ├── test_tokens.py           # Tests tokens (CRUD, isolation, promotion admin)
    ├── test_memories.py         # Tests mémoires (CRUD, auto-ajout, isolation)
    ├── test_documents.py        # Tests documents (ingest, list, get, delete, dédup)
    ├── test_search.py           # Tests recherche (search, Q&A, query, context, graph)
    ├── test_backup.py           # Tests backup/storage (CRUD, check, cleanup)
    └── test_cleanup.py          # Tests suppression + nettoyage
```

### Client MCP (`client.py`)

Le client communique avec le serveur via **Streamable HTTP** en utilisant le protocole MCP. Il encapsule :

- `list_memories()` → outil `memory_list`
- `get_graph(memory_id)` → outil `memory_graph`
- `call_tool(name, args)` → appel MCP générique

### Affichage (`display.py`)

Utilise [Rich](https://rich.readthedocs.io/) pour un affichage élégant :
- Tables colorées (mémoires, documents, entités, tokens)
- Panels (résumé graphe, création token, erreurs)
- Markdown (réponses Q&A)

---

## Codes de retour

| Code | Signification                       |
| ---- | ----------------------------------- |
| 0    | Succès                              |
| 1    | Erreur (serveur, réseau, paramètre) |

---

## Dépannage

### "Le serveur ne répond pas"

```bash
docker compose ps
docker compose logs mcp-memory --tail 20
```

### "401 Unauthorized"

Vérifiez votre token dans `.env` :
```bash
grep ADMIN_BOOTSTRAP_KEY .env
```

Ou passez-le en option :
```bash
python scripts/mcp_cli.py --token <votre_token> health
```

### "ModuleNotFoundError: No module named 'httpx'"

```bash
pip install httpx click rich prompt_toolkit
```

---

*Graph Memory CLI v1.6.0 — Mars 2026*
