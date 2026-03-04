# Changelog

## [1.4.0] - 2026-04-03

### 🔄 Migration SSE → Streamable HTTP (issue #1)

**Migration complète** du transport MCP de SSE (déprécié dans la spec MCP 2025-03-26) vers **Streamable HTTP**. Migration propre sans rétrocompatibilité.

| Composant            | Avant (SSE)                                         | Après (Streamable HTTP)                                        |
| -------------------- | --------------------------------------------------- | -------------------------------------------------------------- |
| **server.py**        | `mcp.sse_app()` → endpoints `/sse` + `/messages`    | `mcp.streamable_http_app()` → endpoint unique `/mcp`           |
| **client.py**        | `from mcp.client.sse import sse_client`             | `from mcp.client.streamable_http import streamablehttp_client` |
| **middleware.py**    | `HostNormalizerMiddleware` (workaround Host header) | Supprimé (plus nécessaire)                                     |
| **requirements.txt** | `mcp>=1.0.0`                                        | `mcp>=1.8.0`                                                   |
| **waf/Caddyfile**    | Routes `/sse*` + `/messages/*` séparées             | Route unique `/mcp*`                                           |
| **Rate limiting**    | SSE 10/min + messages 60/min + global 200/min       | MCP 200/min + global 500/min                                   |
| **Dockerfile**       | Healthcheck `/sse`, VERSION non copié               | Healthcheck `/health`, `COPY VERSION .`                        |
| **Health endpoint**  | Version hardcodée `"1.1.0"`                         | Lecture dynamique fichier `VERSION`                            |

#### Modifié
- **`src/mcp_memory/server.py`** — `mcp.streamable_http_app()` remplace `mcp.sse_app()`, endpoint unique `/mcp`
- **`scripts/cli/client.py`** — `streamablehttp_client` remplace `sse_client`
- **`src/mcp_memory/auth/middleware.py`** — Suppression de `HostNormalizerMiddleware` (plus nécessaire avec Streamable HTTP). Version `/health` lue dynamiquement depuis le fichier `VERSION`
- **`requirements.txt`** — `mcp>=1.8.0` (SDK Streamable HTTP)
- **`waf/Caddyfile`** — Route unique `/mcp*` (remplace `/sse*` + `/messages/*`). Rate limiting ajusté : 200 req/min pour `/mcp` (×3 car chaque appel MCP = 3 requêtes HTTP), 500 global
- **`Dockerfile`** — `COPY VERSION .` ajouté, healthcheck pointe vers `/health` (au lieu de `/sse`)
- **`README.md`** — SSE → Streamable HTTP partout (architecture, intégration, exemples de code, dépannage)
- **`README.en.md`** — Traduction anglaise complète et fidèle du README.md français
- **`scripts/README.md`** — SSE → Streamable HTTP
- **`starter-kit/boilerplate/`** — Tous les fichiers alignés sur Streamable HTTP (server.py, client.py, middleware.py, Caddyfile, requirements.txt)

#### Ajouté
- **`scripts/test_service.py`** — Script de test end-to-end officiel (27 tests, 9 catégories, nettoyage automatique)
- **`DESIGN/MIGRATION_STREAMABLE_HTTP.md`** — Guide de migration détaillé (pour Live Memory et autres services)
- **`CHANGELOG.en.md`** — Version anglaise du changelog

#### Supprimé
- **`HostNormalizerMiddleware`** — Plus nécessaire (Streamable HTTP n'a pas la validation DNS rebinding de SSE)

#### Tests de qualification
`scripts/test_service.py` — **27/27 PASS en ~10s**

#### Notes de migration
- **Clients MCP** : remplacer `url: "http://host:8080/sse"` par `url: "http://host:8080/mcp"` dans la configuration
- **SDK Python** : `mcp>=1.8.0` requis, utiliser `streamablehttp_client` au lieu de `sse_client`
- **Rate limiting** : chaque appel d'outil MCP en Streamable HTTP = 3 requêtes HTTP (POST init + POST call + DELETE close), d'où les limites plus élevées

---

## [1.3.7] - 2026-02-19

### 🧠 Ontologie `general.yaml` v1.0 → v1.1 — Réduction "Other" pour REFERENTIEL

**Problème** : La mémoire REFERENTIEL (2727 entités, 20 documents) contenait **299 entités "Other" (11%)**, principalement issues des textes réglementaires NIS2 (107), rapport NEURONES (90), DORA (67), PAMS ANSSI (20).

**Analyse** : Script `analyze_entities.py` + `analyze_others.py` + script REST ad hoc pour catégoriser les 299 "Other" en 14 patterns : articles de loi (~120), secteurs réglementés (~30), stakeholders RSE (~20), sanctions (~15), deadlines/durées (~20), résolutions AG (~15), impacts RSE (~12), rapports (~8), zones sécurité PAMS (~14), qualifications ANSSI (~4), etc.

**Corrections ontologie `general.yaml` v1.0 → v1.1** :
- **+4 types d'entités** : `LegalProvision` (articles de loi, considérants, annexes), `Sector` (secteurs/sous-secteurs NIS2, DORA, NACE), `Sanction` (amendes, astreintes, suspensions), `Stakeholder` (parties prenantes RSE/matérialité)
- **+2 types de relations** : `APPLIES_TO` (réglementation→secteur), `IMPOSES` (provision→sanction)
- **~50 lignes de `special_instructions`** additionnelles : règles pour textes réglementaires (articles→LegalProvision, secteurs→Sector, sanctions→Sanction), règles RSE (stakeholders, impacts→KPI, résolutions AG→Action), 15 mappings obligatoires supplémentaires (qualifications ANSSI→Certification, rapports→Evidence, zones sécurité→Topic, comités→Organization, réunions→Action, rôles non nommés→ignorer, acronymes→Definition, deadlines/durées/fréquences/limites financières→intégrés dans entité parent, status→ignorer)
- **+1 exemple d'extraction** réglementaire (Article NIS2 + sanctions + secteurs)
- **`priority_entities`** enrichi : +LegalProvision, +Sanction
- Total : 28 types d'entités (vs 24), 24 types de relations (vs 22)

**Action requise** : Redéployer en production puis ré-ingérer les 7 documents problématiques (NIS2, DORA, NEURONES, PAMS, SecNumCloud, HDS, DiagCarbone) avec `--force`.

## [1.3.6] - 2026-02-18

### 🧠 Qualité ontologies — Réduction "Other" à 0%

- **cloud.yaml v1.2** : +2 types (`Role`, `SLALevel`), 12 mappings obligatoires (Endpoint→API, Licence→PricingModel, HA→Technology, etc.), 8 catégories d'exclusion (CLI flags, variables, erreurs, paramètres)
- **presales.yaml v1.1** : mapping MonetaryAmount/Duration vers ClientReference/PricingModel
- **extractor.py** : logging des types LLM rejetés vers `Other` (aide au diagnostic ontologie)
- **Tests** : 4/4 documents ré-ingérés = 0 "Other" (vs 9-12 avant)

### 📚 Nouvelle ontologie `general` (v1.0)

- **`ONTOLOGIES/general.yaml`** : ontologie universelle pour tout document ne rentrant pas dans les ontologies spécialisées (legal, cloud, presales, technical, managed-services)
- **24 types d'entités** en 5 familles : Connaissance (Topic, Question, Answer, Definition, Fact), Organisations (Organization, Person, ClientReference, Partner), Produits & Tech (Product, ProductModel, Technology, Specification, PricingInfo), Conformité (Certification, Regulation, Requirement, SLA), Indicateurs (KPI, Target, Action, Evidence)
- **22 types de relations** en 5 familles : Connaissance (ANSWERS, COVERS, DEFINES, PROVEN_BY), Capacité (PROVIDES, HAS_CERTIFICATION, COMPLIANT_WITH, HAS_SLA, REQUIRES), Technique (USES_TECHNOLOGY, HAS_MODEL, HAS_SPEC, PRICED_AT, INTEGRATES_WITH), Références (DEPLOYED_FOR, PARTNERED_WITH), Stratégie (MEASURED_BY, TARGETS, ADDRESSES), Structure (PART_OF, RELATED_TO, SUPERSEDES)
- Optimisée pour FAQ/Q&A, référentiels normatifs, certifications, bilans RSE, specs produits, knowledge bases
- Mappings stricts anti-"Other" (MonetaryAmount→PricingInfo, Duration→intégré, Date→intégré, Section→ignoré)

### 🧹 Suppression de l'ontologie `technical`

- **`ONTOLOGIES/technical.yaml` supprimée** — Redondante avec l'ontologie `general` qui couvre un spectre plus large (FAQ, documentation technique, certifications, specs produits)

### 🖥️ CLI — Colonne Répertoire

- **`docs` / `document list`** : nouvelle colonne "Répertoire" (bleu) affichant le dossier source de chaque fichier (extrait de `source_path`)
- Fonction partagée `show_documents_table()` : identique en CLI Click et Shell interactif

## [1.3.5] - 2026-02-18

### 🧠 Outil system_about + Starter Kit développeur + Robustification client.py

**Nouvel outil MCP `system_about`** — Carte d'identité complète du service, accessible sans authentification :
- Identité : nom, version, description, objectif, approche Graph-First, repo GitHub
- Capacités : 28 outils répartis en 8 catégories, 5 ontologies, 6 formats supportés
- Mémoires actives : ID, nom, ontologie, compteurs docs/entités/relations
- Services : état de chaque backend (Neo4j, S3, Qdrant, LLMaaS, Embedding)
- Configuration : modèle LLM, embedding, seuil RAG, taille chunks, rétention backups

**CLI enrichie** :
- Nouvelle commande `about` dans la CLI Click (`python scripts/mcp_cli.py about`)
- Nouvelle commande `about` dans le shell interactif
- Affichage Rich complet : 5 panels (identité, services, capacités, mémoires, configuration)
- `show_about()` dans `display.py` (fonction partagée Click/Shell)

**Starter Kit développeur** (`starter-kit/`) :
- Guide complet `README.md` : processus en 4 étapes pour ajouter un nouvel outil MCP
- Boilerplate fonctionnel dans `starter-kit/boilerplate/` (Docker, WAF, CLI, auth)
- `system_about` sert d'exemple réel pour le guide (4 fichiers modifiés documentés)

**Robustification `client.py`** :
- `call_tool()` gère maintenant `isError=True` du protocole MCP (au lieu de crash `json.loads`)
- Gestion réponse vide (`content` absent ou vide)
- Gestion réponse non-JSON (texte brut du serveur)
- Messages d'erreur exploitables au lieu d'exceptions cryptiques

**Fichiers ajoutés** : `starter-kit/README.md`, `starter-kit/boilerplate/` (13 fichiers)
**Fichiers modifiés** : `src/mcp_memory/server.py`, `scripts/cli/commands.py`, `scripts/cli/shell.py`, `scripts/cli/display.py`, `scripts/cli/client.py`, `VERSION`, `src/mcp_memory/__init__.py`

---

## [1.3.4] - 2026-02-18

### CLI — Progression temps réel pour ingestdir + Fix parsing --exclude

**Alignement UX** : `ingestdir` (batch) affiche maintenant la même progression temps réel que `ingest` (unitaire) pour chaque fichier ingéré. Appliqué dans les deux interfaces (Shell interactif et CLI Click).

**Corrigé** :
- **Parser `--exclude` cassé dans le shell** — L'ancien parser artisanal (recherche de sous-chaîne dans la ligne brute) avait 3 bugs :
  1. **Typos d'options non détectées** : `--excluse` restait collé au chemin du répertoire → `os.path.isdir("DOCS --excluse ...")` → erreur
  2. **Guillemets non strippés** : `"llmaas/licences/*"` passé tel quel à `fnmatch` (avec les `"`) → aucun match
  3. **Options inconnues silencieuses** : tout ce qui n'est pas reconnu finissait dans le chemin
- **Fix** : réécriture complète avec `shlex.split()` (parsing POSIX des guillemets) + itération par tokens avec détection d'options inconnues → message d'erreur clair

**Amélioré** :
- **Progression temps réel par fichier** (`run_ingest_with_progress`) : chaque fichier du batch affiche barres ASCII extraction LLM (`█████░░░░░ 50%`), embedding, compteurs entités/relations, timer `⏱ mm:ss`
- **Header enrichi par fichier** : `[3/15] 📥 bastion/concepts.md (12.4 KB)` (numéro, chemin relatif, taille)
- **Résumé par fichier** : `✅ concepts.md: 12+3 entités, 8+2 relations (45.2s)` (new+merged, durée)
- **Autocomplétion shell** : `--exclude` et `--confirm` ajoutés à `SHELL_COMMANDS`
- **CLI Click non affectée** : Click gère nativement `@click.option("--exclude", multiple=True)`

**Fichiers modifiés** : `scripts/cli/shell.py`, `scripts/cli/commands.py`, `VERSION`, `src/mcp_memory/__init__.py`

---

## [1.3.3] - 2026-02-18

### Ontologie cloud.yaml v1.1 — Couverture fiches produits et documentation technique

**Audit et enrichissement** de l'ontologie `cloud.yaml` après confrontation avec le contenu réel de ~30 documents `DOCS/` et ~15 fiches produits `PRODUCT/`.

**Ajouté** :
- **+4 types d'entités** (20→24) : `PricingModel` (tarification omniprésente dans PRODUCT), `StorageClass` (5 classes IOPS Cloud Temple), `BackupSolution` (IBM SPP, VMware Replication, Global Mirror), `AIModel` (LLMaaS, modèles IA)
- **+5 types de relations** (14→19) : `COMPATIBLE_WITH`, `SUPPORTS`, `PART_OF`, `DEPENDS_ON`, `HAS_PRICING` — aligné avec les patterns des autres ontologies
- **`priority: high`** ajouté sur `CloudService` et `Technology` (en plus de `Certification` et `SLA`)
- **`priority_entities`** enrichi : +`StorageClass`, +`PricingModel`
- **+1 exemple d'extraction** basé fiche produit (Bastion, StorageClass, pricing, backup)
- **Contexte LLM enrichi** : consignes spécifiques pour fiches produits (tarification, compatibilités, modèles IA)
- **Exemples d'entités enrichis** : noms réels Cloud Temple (PAR7S, TH3S, Cisco UCS B200, Intel Xeon Gold, Thales Luna S790, ISAE 3402, XCP-ng, etc.)

**Nettoyé** :
- Suppression de 4 champs `extraction_rules` non reconnus par le code (`include_metrics`, `include_durations`, `include_amounts`, `extract_implicit_relations`)
- Suppression du script `scripts/validate_ontology.py` (utilitaire ponctuel, validation terminée)

**Validé en conditions réelles** (ingestion de 2 fiches produits) :
- IaaS VMware (13.6 KB) : **40 entités, 52 relations, 0 "Other"** — StorageClass:6, PricingModel:1, BackupSolution:1 ✅
- LLMaaS (19.5 KB) : **33 entités, 36 relations, 2 "Other" (6%)** — AIModel:6, PricingModel:4 ✅
- **Total : 73 entités, 97.3% correctement typées**, 18/24 types utilisés, 88 relations

**Fichiers modifiés** : `ONTOLOGIES/cloud.yaml` (v1.0→v1.1), `VERSION`, `src/mcp_memory/__init__.py`
**Fichiers supprimés** : `scripts/validate_ontology.py`

---

## [1.3.2] - 2026-02-18

### Refactoring — L'ontologie est la seule source de vérité pour les types d'entités

- `extractor.py` : `_normalize_entity_type()` simplifiée de 50 lignes → 8 lignes.
  Suppression du mapping hardcodé de 12 types "de base" et de l'acceptation libre
  de tout type alphanumérique. La règle est désormais unique et stricte :
  - Type retourné par le LLM **dans l'ontologie** → retourné avec la casse exacte de l'ontologie
  - Type **hors ontologie** → `"Other"`, sans exception

  Les 12 types de base (Person, Organization, Concept...) continuent de fonctionner
  car ils sont définis dans chaque ontologie — c'est l'ontologie qui les déclare,
  pas le code Python.

---

## [1.3.1] - 2026-02-18

### Bugfix critique — Types d'entités dynamiques par ontologie

**Problème** : Sur 29 documents ingérés avec l'ontologie `presales`, 277 entités
étaient classifiées `Other` au lieu d'utiliser les 28 types définis (Differentiator,
Platform, KPI, Persona, PresalesDomain, etc.).

**Cause racine** : `ExtractedEntity.type` était un `EntityType` Enum Python avec
12 valeurs fixes hardcodées. Toute réponse du LLM avec un type ontologique
inconnu (ex: `Differentiator`, `ClientReference`) tombait dans `EntityType.OTHER`
via un `dict.get(..., OTHER)`. Les relations fonctionnaient déjà correctement
(via `_parse_relation_type` dynamique) mais les entités non.

**Corrections** :
- `models.py` : `ExtractedEntity.type` → `str` (string libre, comme `ExtractedRelation.type`)
- `extractor.py` : `_parse_entity_type` remplacée par `_normalize_entity_type(type_str, known_types=None)` :
  1. Mapping de compatibilité base (12 types existants)
  2. Recherche dans les types de l'ontologie chargée (insensible à la casse)
  3. Acceptation de tout type alphanumérique valide (PascalCase, CamelCase, UPPER)
  4. Fallback `"Other"` uniquement en dernier recours
- `_parse_extraction()` : nouveau param `known_entity_types` propagé à `_normalize_entity_type`
- `extract_with_ontology()` : construit `ontology_entity_types = {et.name for et in ontology.entity_types}` et le passe au parser
- `extract_with_ontology_chunked()` : idem, propagé à chaque chunk
- `_build_cumulative_context()` : simplifié `e.type.value → e.type` (str direct)
- `server.py` : simplifié `e.type.value if hasattr... → e.type` (str direct)

**Impact** : Les nouvelles ingestions avec ontologie `presales` (ou toute autre
ontologie) utiliseront correctement les types d'entités définis. Les données
existantes (277 `Other`) doivent être réingérées pour bénéficier de la correction.


Toutes les modifications notables de ce projet sont documentées dans ce fichier.

Le format est basé sur [Keep a Changelog](https://keepachangelog.com/fr/1.0.0/),
et ce projet adhère au [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.3.0] — 2026-02-17

### 🧠 Ontologie Presales + Uniformisation des limites d'extraction

#### Ajouté
- **Nouvelle ontologie `presales`** (`ONTOLOGIES/presales.yaml`) — Ontologie dédiée à l'analyse de documents avant-vente (RFP, RFI, propositions commerciales, études de cas) :
  - **28 types d'entités** en 6 familles : Acteurs & Personnes (Organization, Person, Role, Team, Persona), Sécurité & Conformité (Certification, Regulation, SecurityPolicy), Technique & Infrastructure (Platform, Technology, Infrastructure, Service, Methodology), Gouvernance & Méthodologie (Governance, ProjectPhase, Deliverable), Commercial & Valeur (Differentiator, ValueProposition, SLA, PricingModel, Quote, Constraint, Requirement, ClientReference), Contexte & Indicateurs (KPI, PresalesDomain, Evidence, ProposalSection)
  - **30 types de relations** en 5 familles : Capacité & Conformité (PROVIDES, HAS_CERTIFICATION, COMPLIANT_WITH, GUARANTEES, REQUIRES), Technique (RUNS_ON, HOSTED_AT, INTEGRATES_WITH, MANAGED_BY, POWERED_BY), Gouvernance (FOLLOWS_METHODOLOGY, GOVERNED_BY, RESPONSIBLE_FOR, INCLUDES_PHASE, DELIVERS), Commerciale (DIFFERENTIATES_FROM, TARGETS_PERSONA, PRICED_AS, HAS_SLA, REFERENCED_BY, ANSWERED_BY), Structurelle & Contexte (PART_OF_DOMAIN, RELATED_TO, SUPERSEDES, CONTAINS, MEASURES, ADDRESSES_RISK, DEPENDS_ON, PROVEN_BY, CONSTRAINED_BY)
  - Entités prioritaires : `Service`, `Certification`, `Differentiator`, `Requirement`, `SLA`, `ClientReference`
  - Relations prioritaires : `HAS_CERTIFICATION`, `GUARANTEES`, `TARGETS_PERSONA`, `ANSWERED_BY`, `PART_OF_DOMAIN`, `PROVEN_BY`
  - Limites `max_entities: 60` / `max_relations: 80` alignées sur le nouveau standard

#### Modifié
- **Uniformisation des limites d'extraction** (`ONTOLOGIES/*.yaml`, `src/mcp_memory/core/ontology.py`) — Toutes les ontologies ont maintenant les mêmes limites :

  | Ontologie               | Avant  | Après |
  | ----------------------- | ------ | ----- |
  | `legal.yaml`            | absent | 60/80 |
  | `cloud.yaml`            | 50/60  | 60/80 |
  | `technical.yaml`        | 60/70  | 60/80 |
  | `managed-services.yaml` | 50/60  | 60/80 |
  | `presales.yaml`         | 60/80  | 60/80 |

- **Défauts Python** (`core/ontology.py`) — `ExtractionRules.max_entities` 30→**60**, `ExtractionRules.max_relations` 40→**80** (pour les ontologies futures qui n'expliciteraient pas ces valeurs)

#### Corrigé
- **Syntaxe YAML invalide dans `presales.yaml`** — Le pattern `- "Texte" (annotation)` était illégal (scalaire inattendu après string terminée). Corrigé en `- "Texte (annotation)"` sur 8 blocs (Organization, Person, Persona, Methodology, Technology, KPI, PresalesDomain).

#### Fichiers ajoutés/modifiés
`ONTOLOGIES/presales.yaml` (nouveau), `ONTOLOGIES/legal.yaml`, `ONTOLOGIES/cloud.yaml`, `ONTOLOGIES/technical.yaml`, `ONTOLOGIES/managed-services.yaml`, `src/mcp_memory/core/ontology.py`, `VERSION`, `src/mcp_memory/__init__.py`

---

## [1.2.4] — 2026-02-17

### 🔧 Factorisation CLI Click / Shell interactif

#### Refactorisé
- **Nouveau module `scripts/cli/ingest_progress.py`** — Toute la mécanique de progression d'ingestion temps réel (Rich Live + parsing SSE) extraite en 4 fonctions réutilisables :
  - `create_progress_state()` : état initial de progression
  - `make_progress_bar(current, total)` : barre ASCII `█████░░░░░ 50%`
  - `create_progress_callback(state)` : parser async des messages serveur via regex
  - `run_ingest_with_progress(client, params)` : coroutine complète (Rich Live display + appel MCP `memory_ingest`)
- **`display.py` enrichi** — 4 nouvelles fonctions partagées entre CLI Click et shell interactif :
  - `format_size()` : rendue publique (3 copies `_format_size` / `_format_size_simple` / `_fmt_size` → 1 seule)
  - `show_ingest_preflight()` : panel pré-vol d'ingestion (fichier, taille, type, mémoire, mode force)
  - `show_entities_by_type()` : entités groupées par type avec documents sources (mapping MENTIONS)
  - `show_relations_by_type()` : relations par type — résumé (compteurs + exemples) ou détail filtré par type
- **`commands.py` simplifié** — Les commandes `ingest`, `entities`, `relations` appellent les fonctions partagées au lieu de dupliquer le code.
- **`shell.py` simplifié** — Les handlers `cmd_ingest`, `cmd_entities`, `cmd_relations` appellent les mêmes fonctions partagées.
- **~300 lignes de duplication supprimées**, 0 changement fonctionnel.

#### Architecture CLI résultante
```
scripts/cli/
├── __init__.py           # Configuration (URL, token)
├── client.py             # Client HTTP/SSE vers le serveur MCP
├── display.py            # Affichage Rich partagé (tables, panels, entités, relations, format_size)
├── ingest_progress.py    # Progression ingestion temps réel partagée (Rich Live + SSE)
├── commands.py           # Commandes Click (mode scriptable)
└── shell.py              # Shell interactif prompt_toolkit
```

#### Fichiers ajoutés/modifiés
`scripts/cli/ingest_progress.py` (nouveau), `scripts/cli/display.py`, `scripts/cli/commands.py`, `scripts/cli/shell.py`, `VERSION`, `src/mcp_memory/__init__.py`

---

## [1.2.3] — 2026-02-17

### 📊 Alignement Shell interactif — Progression ingestion temps réel

#### Ajouté
- **Progression ingestion temps réel dans le shell** (`scripts/cli/shell.py`) — La commande `ingest` du shell interactif affiche désormais la même progression riche que la CLI Click :
  - Rich Live display rafraîchi 4x/seconde
  - Barres ASCII `█████████░░░░░░░░░░░ 45%` pour l'extraction LLM (chunk par chunk) et l'embedding (batch par batch)
  - Compteurs en temps réel : nombre d'entités et relations détectées pendant l'extraction
  - Phases détaillées : ⏳ Connexion → 📤 Upload S3 → 📄 Extraction texte → 🔍 Extraction LLM → 📊 Neo4j → 🧩 Chunking → 🔢 Embedding → 📦 Qdrant → 🏁 Terminé
  - Callback `on_progress` branché sur les notifications SSE du serveur (`ctx.info()`)

#### Corrigé
- **Shell `ingest` affichait un simple spinner** — Remplacé par la progression riche temps réel identique à la CLI Click.

#### Fichiers modifiés
`scripts/cli/shell.py`, `VERSION`, `src/mcp_memory/__init__.py`

---

## [1.2.2] — 2026-02-17

### 🔀 Fix HTTP 421 — Connexion client à serveur distant (reverse proxy)

#### Corrigé
- **HTTP 421 "Invalid Host header" sur /sse et /messages** (`src/mcp_memory/server.py`, `src/mcp_memory/auth/middleware.py`) — Le SDK MCP Python v1.26+ (`FastMCP`) utilise `host="127.0.0.1"` par défaut. Quand host est localhost, le SDK active automatiquement `TransportSecurityMiddleware` avec `allowed_hosts=["127.0.0.1:*", "localhost:*"]`. Derrière un reverse proxy (nginx → Caddy → MCP), le `Host` header contient le domaine public (`graph-mem.mcp.cloud-temple.app`) → rejeté avec 421.
  - **Cause racine** : `mcp/server/fastmcp/server.py` ligne 166 + `mcp/server/transport_security.py`
  - **Fix principal** : `FastMCP(host=settings.mcp_server_host)` → `host="0.0.0.0"` n'est pas dans la liste `("127.0.0.1", "localhost", "::1")`, donc `TransportSecurityMiddleware` n'est pas activé.
  - **Ceinture de sécurité** : Nouveau `HostNormalizerMiddleware` ASGI normalise le Host header vers `localhost` avant le MCP SDK. Log `🔀 [Host]`.
  - Note : les routes `/api/*` n'étaient pas affectées car interceptées par `StaticFilesMiddleware` avant Starlette.

#### Amélioré
- **Messages d'erreur client** (`scripts/cli/client.py`) — Nouvelle méthode `_extract_root_cause()` qui descend récursivement dans les `ExceptionGroup`/`TaskGroup` pour extraire le vrai message d'erreur. Avant : message cryptique `"unhandled errors in a TaskGroup (1 sub-exception)"`. Après : message clair avec suggestion de diagnostic (`HostNormalizerMiddleware`, HTTP 421).

#### Corrigé
- **Healthcheck Docker unhealthy en permanence** (`Dockerfile`, `docker-compose.yml`) — Le healthcheck ciblait `/sse` (endpoint SSE = flux infini). curl recevait le HTTP 200 puis attendait le flux → timeout (`--max-time 5`) → exit code 28 → Docker considérait le check comme échoué → unhealthy après 3 retries.
  - **Fix** : On accepte désormais exit code 28 (timeout après connexion réussie) en plus de exit 0. Commande : `curl ... --max-time 2; rc=$?; [ $rc -eq 0 ] || [ $rc -eq 28 ]`.
  - Appliqué dans le Dockerfile (pour les builds) ET dans docker-compose.yml (override immédiat, pas de rebuild nécessaire).

#### Fichiers modifiés
`src/mcp_memory/auth/middleware.py`, `src/mcp_memory/server.py`, `scripts/cli/client.py`, `Dockerfile`, `docker-compose.yml`, `VERSION`, `src/mcp_memory/__init__.py`

---

## [1.2.1] — 2026-02-17

### 🐛 Fix CLI production — Variables MCP_URL / MCP_TOKEN

#### Corrigé
- **CLI 401 sur serveur de production** (`scripts/cli/__init__.py`, `scripts/cli/commands.py`) — La CLI ne pouvait pas se connecter à un serveur de production distant. Double conflit de variables d'environnement :
  1. `__init__.py` lisait `MCP_SERVER_URL` (pas `MCP_URL`) comme variable d'environnement.
  2. Click déclarait `envvar="ADMIN_BOOTSTRAP_KEY"` → `load_dotenv()` chargeait le `.env` local dev (`admin_bootstrap_key_change_me`) qui écrasait le token production.
  - **Fix** : `MCP_URL` et `MCP_TOKEN` sont désormais prioritaires (fallback sur `MCP_SERVER_URL` / `ADMIN_BOOTSTRAP_KEY`). Click accepte une liste ordonnée `envvar=["MCP_TOKEN", "ADMIN_BOOTSTRAP_KEY"]`.

#### Ajouté
- **Documentation CLI production** (`scripts/README.md`) — Section Configuration réécrite : deux jeux de variables (CLI vs serveur), usage dev vs prod, fichier `~/.env.mcp-cli`.
- **Guide déploiement §15** (`DESIGN/DEPLOIEMENT_PRODUCTION.md`) — Nouvelle section "Utiliser la CLI depuis un poste distant" avec 3 options de configuration et schéma de résolution des variables.
- **`.env.example`** — Section CLI avec `MCP_URL` / `MCP_TOKEN` commentés et documentés.

#### Fichiers modifiés
`scripts/cli/__init__.py`, `scripts/cli/commands.py`, `scripts/README.md`, `DESIGN/DEPLOIEMENT_PRODUCTION.md`, `.env.example`, `VERSION`, `src/mcp_memory/__init__.py`

---

## [1.2.0] — 2026-02-16

### 💾 Backup / Restore complet + Fix storage_check

#### Ajouté
- **Système de Backup/Restore** (`backup.py`, `server.py`, `commands.py`, `shell.py`, `display.py`) — 7 nouveaux outils MCP :
  - `backup_create` : Exporte graphe Neo4j (entités, relations, documents) + vecteurs Qdrant → S3. Politique de rétention configurable (`BACKUP_RETENTION_COUNT`).
  - `backup_list` : Liste les backups disponibles avec statistiques (entités, relations, vecteurs, docs).
  - `backup_restore` : Restaure depuis un backup S3 (graphe + vecteurs), sans re-extraction LLM (~0.3s).
  - `backup_download` : Télécharge un backup en archive tar.gz (light ou avec documents originaux).
  - `backup_delete` : Supprime un backup de S3.
  - `backup_restore_archive` : **Restaure depuis une archive tar.gz locale** — re-uploade les documents S3 inclus dans l'archive + restaure graphe + vecteurs. Cycle complet validé : backup → download tar.gz → suppression totale serveur → restore depuis fichier local.
- **CLI backup complète** — 6 commandes Click (`backup create/list/restore/download/delete/restore-file`) + commandes shell interactif correspondantes.
- **Affichage Rich** (`display.py`) — `show_backup_result`, `show_backups_table`, `show_restore_result` pour un rendu formaté des opérations backup.
- **Configuration backup** (`.env.example`, `config.py`) — `BACKUP_RETENTION_COUNT` (défaut: 5 backups par mémoire).

#### Corrigé
- **`storage_check` : faux-positifs orphelins quand scopé** — `storage check JURIDIQUE` signalait 42 "orphelins" (les documents des AUTRES mémoires + les backups). Deux fixes :
  - Les fichiers `_backups/` sont maintenant exclus de la détection d'orphelins (gérés par `backup_list`).
  - Quand scopé à une mémoire, la détection d'orphelins charge les URIs de TOUTES les mémoires (pas seulement la scopée). Les documents des autres mémoires ne sont plus signalés à tort.

#### Architecture backup
- Format backup S3 : `_backups/{memory_id}/{timestamp}/` contenant `manifest.json`, `graph_data.json`, `qdrant_vectors.jsonl`, `document_keys.json`.
- Format archive tar.gz : même structure + dossier optionnel `documents/` avec les fichiers originaux.
- Couplage strict : si Qdrant ou Neo4j échoue pendant la restauration, l'opération est annulée.
- Checksum SHA-256 vérifié lors de la restauration depuis archive.

#### Fichiers ajoutés/modifiés
`src/mcp_memory/core/backup.py` (nouveau), `src/mcp_memory/server.py`, `src/mcp_memory/config.py`, `scripts/cli/commands.py`, `scripts/cli/shell.py`, `scripts/cli/display.py`, `.env.example`, `VERSION`, `src/mcp_memory/__init__.py`

---

## [1.1.0] — 2026-02-16

### 🔒 Rate Limiting + Analyse de Risques Sécurité

#### Ajouté
- **Rate Limiting WAF** (`waf/Caddyfile`, `waf/Dockerfile`) — Module `caddy-ratelimit` compilé dans l'image WAF via `xcaddy`. 4 zones de limitation par IP :
  - `/sse*` : 10 connexions/min (SSE longue durée)
  - `/messages/*` : 60 appels/min (outils MCP, burst d'un agent actif)
  - `/api/*` : 30 requêtes/min (interface web)
  - Global : 200 requêtes/min (toutes routes confondues)
  - Requêtes excédentaires → HTTP 429 (Too Many Requests)
- **Analyse de Risques Sécurité** (`DESIGN/ANALYSE_RISQUES_SECURITE.md`) — Document complet :
  - Matrice de risques par route (/sse, /messages, /api, /public)
  - Vecteurs d'attaque avec probabilité, impact, risque, mitigation
  - Risques transversaux : prompt injection, token compromise, DoS, CSP unsafe-inline
  - Conformité OWASP Top 10, SecNumCloud, RGPD
  - Recommandations priorisées (haute/moyenne/basse)
- **Script de test rate limiting** (`scripts/test_rate_limit.sh`) — Envoie 35 requêtes rapides sur `/api/memories`, vérifie que les 30 premières passent et les suivantes reçoivent HTTP 429.

#### Modifié
- **WAF Dockerfile** — Ajout du plugin `caddy-ratelimit` dans la compilation `xcaddy`.

#### Fichiers ajoutés/modifiés
`waf/Dockerfile`, `waf/Caddyfile`, `DESIGN/ANALYSE_RISQUES_SECURITE.md` (nouveau), `scripts/test_rate_limit.sh` (nouveau), `VERSION`, `src/mcp_memory/__init__.py`, `src/mcp_memory/auth/middleware.py`

---

## [1.0.0] — 2026-02-16

### 🎉 Version 1.0 — Production Ready

#### Architecture sécurisée
- **Coraza WAF** (`waf/Dockerfile`, `waf/Caddyfile`) — Image custom buildée via `xcaddy` + plugin `coraza-caddy/v2` avec OWASP Core Rule Set embarqué. Protection OWASP Top 10 (injections SQL/XSS, SSRF, path traversal, scanners).
- **Architecture réseau durcie** — Seul le port 8080 (WAF) est exposé. Neo4j, Qdrant et le service MCP sont sur un réseau Docker interne isolé (`mcp-network`). Container MCP non-root (`USER mcp`).
- **TLS Let's Encrypt natif** — Caddy gère nativement ACME/Let's Encrypt. Variable `SITE_ADDRESS` pour basculer dev (`:8080` HTTP) ↔ prod (`domaine.com` HTTPS automatique).
- **Headers de sécurité** — CSP (Content-Security-Policy), X-Frame-Options DENY, X-Content-Type-Options nosniff, Referrer-Policy, Permissions-Policy.

#### Routage WAF intelligent
- **Routes SSE/MCP sans WAF** (`handle /sse*`, `handle /messages/*`) — Coraza bufférise les réponses pour les inspecter, ce qui est incompatible avec le streaming SSE. Ces routes sont servies en reverse proxy direct (authentification gérée côté serveur MCP par token Bearer).
- **Routes web avec WAF** (`handle`) — API REST (`/api/*`), fichiers statiques, health et graphe protégés par Coraza WAF + OWASP CRS.
- **Timeouts calibrés** — SSE : timeout 0 (connexions MCP longues), ingestion : 1800s (30 min pour gros documents), API REST : 300s.

#### CLI adaptée
- **Port par défaut 8080** — La CLI pointe désormais sur le WAF (`http://localhost:8080`) au lieu du service interne (`http://localhost:8002`).

#### Fichiers ajoutés/modifiés
`waf/Dockerfile` (nouveau), `waf/Caddyfile`, `docker-compose.yml`, `Dockerfile`, `scripts/cli/__init__.py`, `scripts/view_graph.py`, `scripts/README.md`, `src/mcp_memory/auth/middleware.py`, `VERSION`

---

## [0.6.6] — 2026-02-16

### Audit sécurité + WAF Coraza + Hardening Docker

#### Ajouté
- **Coraza WAF** (`waf/Caddyfile`, `docker-compose.yml`) — Reverse proxy sécurisé avec OWASP Core Rule Set (CRS). Protection contre injections SQL/XSS, path traversal, SSRF, scanners. Headers de sécurité (CSP, HSTS, X-Frame-Options, Permissions-Policy). Seul port exposé : 8080 (WAF).
- **Support TLS Let's Encrypt natif** — Caddy (intégré dans l'image Coraza CRS) gère nativement ACME/Let's Encrypt. Variable `SITE_ADDRESS` pour basculer dev (`:8080` HTTP) ↔ prod (`domaine.com` HTTPS automatique). Pas besoin de nginx/certbot.
- **Rapport d'audit** (`AUDIT_SECURITE_2026-02-16.md`) — Audit complet : 3 vulnérabilités critiques, 5 élevées, 7 moyennes identifiées et corrigées.

#### Corrigé (sécurité)
- **Container root** (`Dockerfile`) — Ajout `USER mcp` non-root (le service tournait en root dans le container).
- **Ports Neo4j/Qdrant exposés** (`docker-compose.yml`) — Supprimés. Neo4j et Qdrant ne sont plus accessibles depuis l'extérieur (réseau Docker interne uniquement). Ports debug commentés sur 127.0.0.1.
- **Timeouts WAF calibrés** — SSE : timeout 0 (connexions MCP longues), ingestion : 1800s (30 min pour gros documents avec chain-of-thought LLM), API REST : 300s.

#### Corrigé (config)
- **`EXTRACTION_MAX_TEXT_LENGTH` refactorisé** (`extractor.py`) — N'était plus utile avec le chunking (code mort). Transformé en garde-fou explicite : rejette avec `ValueError` les documents trop volumineux AVANT le chunking, au lieu de tronquer silencieusement.
- **`.env.example` : `EXTRACTION_CHUNK_SIZE`** — Corrigé de 200000 → **25000** (valeur réelle dans config.py depuis v0.6.1).
- **`.env` nettoyé** — Supprimé le override `EXTRACTION_MAX_TEXT_LENGTH=120000`, les défauts config.py (950K) sont maintenant utilisés. Structure alignée sur `.env.example`.

#### Fichiers modifiés/créés
`Dockerfile`, `docker-compose.yml`, `waf/Caddyfile` (nouveau), `.env`, `.env.example`, `extractor.py`, `AUDIT_SECURITE_2026-02-16.md` (nouveau), `VERSION`

---

## [0.6.5] — 2026-02-16

### Tool memory_query + Option --json CLI

#### Ajouté
- **Tool MCP `memory_query`** (`server.py`) — Interrogation structurée sans LLM. Même pipeline que `question_answer` (graphe fulltext + RAG vectoriel) mais retourne les données brutes : entités enrichies (relations, voisins, documents sources), chunks RAG avec scores, statistiques. Idéal pour les agents IA qui construisent leur propre réponse.
- **Commande CLI `query`** (`shell.py`, `commands.py`) — Nouvelle commande dans le shell interactif et en mode Click. Affichage formaté Rich avec entités, chunks RAG triés par score, et documents sources.
- **Affichage `show_query_result()`** (`display.py`) — Rendu Rich dédié pour les résultats de `memory_query` : panel par entité (relations, voisins), table RAG chunks, panel documents sources.
- **Option `--json` globale** (`shell.py`) — Utilisable sur toute commande de consultation (`list`, `info`, `graph`, `docs`, `entities`, `entity`, `relations`, `ask`, `query`). Affiche le JSON brut du serveur sans formatage Rich. Détection automatique n'importe où dans la ligne (`query --json ma question` ou `--json list`). Idéal pour scripting et pipe vers `jq`.

#### Corrigé
- **Erreur TaskGroup sur `query`** — Le serveur Docker n'avait pas le nouveau code (`memory_query` non enregistré). Rebuild Docker nécessaire après ajout de nouveaux tools MCP.

#### Fichiers modifiés
`server.py`, `shell.py`, `display.py`, `commands.py`

---

## [0.6.4] — 2026-02-16

### Panneau ASK amélioré + Fix toggle Documents

#### Ajouté
- **Panneau ASK redimensionnable** (`ask.js`, `graph.css`, `graph.html`) — Poignée de drag en haut du panneau ASK. Tirer vers le haut = panneau plus grand (graphe plus petit), vers le bas = l'inverse. Limites min 100px, max 80% du conteneur. Barre verte au survol, body scrollable indépendant.
- **Export HTML de la réponse** (`ask.js`) — Bouton "📥 Export HTML" affiché après chaque réponse. Génère un fichier HTML autonome avec CSS inline, branding Cloud Temple, question posée, réponse formatée Markdown (tableaux, code, blockquotes), entités identifiées, documents sources. Compatible impression (`@media print`). Nommé `graph-memory-YYYY-MM-DD-HHmm.html`.
- **Barre d'actions unifiée** (`ask.js`, `graph.css`) — Les boutons "🔬 Isoler le sujet" et "📥 Export HTML" sont regroupés dans un conteneur `ask-actions` sous la réponse.

#### Corrigé
- **Toggle Documents inefficace en mode isolation** (`config.js`) — En mode Focus (après "🔬 Isoler le sujet"), les nœuds Document étaient dans `filterState.isolatedNodes`, et le `return true` de l'isolation court-circuitait le test `showMentions`. Les carrés rouges restaient visibles même avec le toggle OFF. Corrigé en plaçant le test `showMentions` **avant** le test d'isolation.

#### Fichiers modifiés
`config.js`, `ask.js`, `graph.css`, `graph.html`

---

## [0.6.3] — 2026-02-15

### Recherche accent-insensitive + Calibrage seuil RAG

#### Ajouté
- **Index fulltext Neo4j `standard-folding`** (`graph.py`) — Recherche accent-insensitive via un index Lucene avec ASCII folding (é→e, ç→c, ü→u). `"réversibilité"`, `"reversibilite"`, `"REVERSIBILITE"` matchent tous les 3. Lazy init idempotent au premier appel de `search_entities()`.
- **`_search_fulltext()`** — Recherche principale via l'index Lucene avec scoring par pertinence, filtrée par `memory_id`.
- **`_search_contains()` amélioré** — Fallback CONTAINS qui envoie les tokens raw (avec accents) ET normalisés (sans accents) à Neo4j.
- **`_escape_lucene()`** — Échappement des caractères spéciaux Lucene (`+`, `-`, `*`, `?`, `~`, etc.).

#### Corrigé
- **Recherche "réversibilité" → 0 résultats** — Python normalisait les accents (`reversibilite`) mais `toLower()` de Neo4j les conservait (`réversibilité`). Désalignement corrigé par l'index fulltext `standard-folding` (principal) + fallback CONTAINS avec double tokens.
- **RAG quasi inactif (seuil 0.65 trop élevé)** — BGE-M3 produit des scores cosinus ~0.55-0.63 pour les meilleurs chunks. Le seuil 0.65 éliminait 93% des chunks pertinents. Abaissé à **0.58** après benchmark comparatif sur 5 questions × 5 seuils (`scripts/test_rag_thresholds.py`).

#### Modifié
- **`RAG_SCORE_THRESHOLD` 0.65 → 0.58** — Calibré pour BGE-M3 via benchmark (0.50/0.55/0.58/0.60/0.65 testés sur 5 requêtes × 15 chunks).

#### Refactorisé
- **`search_entities()`** — Stratégie en 2 niveaux : fulltext Lucene (scoring) → fallback CONTAINS (raw+normalized). 3 nouvelles méthodes privées.

#### Fichiers modifiés
`graph.py`, `config.py`, `.env.example`, `README.md`

---

## [0.6.2] — 2026-02-15

### Interface web graphe améliorée + Progression CLI

#### Ajouté
- **Toggle MENTIONS** (📄) — Nouveau bouton toggle dans le header du client web pour masquer/afficher les nœuds Document et les arêtes MENTIONS. Permet de visualiser uniquement les relations sémantiques entre entités (`displayOptions.showMentions` dans `config.js`).
- **Progression CLI avec barres %** — L'ingestion en ligne de commande affiche des barres de progression ASCII pour l'extraction LLM (chunk par chunk) et l'embedding (batch par batch), avec compteur d'entités/relations en temps réel.

#### Corrigé
- **Exit isolation automatique avant ASK** — Quand l'utilisateur pose une nouvelle question alors que le mode Focus est actif, le graphe repasse automatiquement en vue globale. Plus de filtrage résiduel entre deux questions.

#### Fichiers modifiés
`config.js`, `graph.html`, `app.js`, `ask.js`, `commands.py`

---

## [0.6.1] — 2026-02-15

### Stabilisation ingestion gros documents + Observabilité

#### Corrigé
- **Boucle infinie chunker** (`chunker.py`) — `_split_group_with_overlap()` pouvait boucler infiniment quand overlap + prochaine phrase dépassait `chunk_size` → millions de chunks → 7.47GB RAM → OOM Kill (exit 137). Corrigé en vidant l'overlap si nécessaire.
- **Healthcheck Docker OOM** (`Dockerfile`) — Remplacé `python -c "import httpx; ..."` par `curl` (économise ~50MB RAM par check toutes les 30s).

#### Modifié
- **`EXTRACTION_CHUNK_SIZE` réduit** (`config.py`) — 200K → **25K chars** (~6K tokens par chunk). Un document de 135K chars → 7 chunks au lieu de 1.

#### Ajouté
- **Libération mémoire proactive** (`server.py`) — `del content_base64` + `del content` + `gc.collect()`. Monitoring RSS dans chaque log `[RSS=XXmb]`.
- **Logs chunker détaillés** (`chunker.py`) — 3 passes avec détail section par section (titre, chars, level). `sys.stderr.flush()` systématique.
- **Progression CLI temps réel** (`client.py` + `commands.py`) — Notifications MCP `ctx.info()` capturées côté client via monkey-patch `_received_notification`. Rich Live display avec étapes + timer.
- **Déduplication vérifiée** — Deux niveaux : extracteur (`_merge_extraction_results` : par nom+type) + Neo4j (`MERGE` Cypher sur `{name, memory_id}`).

#### Fichiers modifiés
`chunker.py`, `Dockerfile`, `config.py`, `server.py`, `client.py`, `commands.py`

---

## [0.6.0] — 2026-02-13

### Chunked Graph Extraction + Métadonnées enrichies

#### Ajouté
- **Extraction chunked séquentielle** (`extractor.py`) — Documents longs découpés en chunks extraits séquentiellement avec contexte cumulatif. Fusion finale avec déduplication par (nom, type).
- **Métadonnées enrichies** — Nœud Document Neo4j : `source_path`, `source_modified_at`, `size_bytes`, `text_length`, `content_type`.
- **`document_get` optimisé** — Paramètre `include_content=False` (défaut), pas de téléchargement S3 pour les métadonnées.
- **CLI enrichi** — `document ingest --source-path`, `document ingest-dir` passent automatiquement les métadonnées.
- **Paramètre** `EXTRACTION_CHUNK_SIZE` (défaut 200K chars, configurable via `.env`).
- **Documentation** — `DESIGN/chunking_methodology.md`.

#### Modifié
- **Timeout LLM** — 120s → **600s** (gpt-oss:120b chain-of-thought).
- **Résilience** — Si un chunk d'extraction timeout, l'ingestion continue avec les suivants.

#### Fichiers modifiés
`extractor.py`, `ontology.py`, `graph.py`, `server.py`, `config.py`, `commands.py`, `shell.py`, `.env.example`

---

## [0.5.2] — 2026-02-09

### Q&A — Fallback RAG-only + Tokeniser robuste

#### Corrigé
- **Tokeniser de recherche** (`graph.py`) — Ponctuation retirée avec `re.findall(r'[a-zA-ZÀ-ÿ]+', ...)`.
- **Normalisation des accents** — `unicodedata.normalize('NFKD', ...)` pour matcher `"résiliation"` ↔ `"RESILIATION"`.

#### Ajouté
- **Fallback RAG-only** — 0 entités graphe → recherche Qdrant sur tous les chunks (au lieu de "pas d'infos").
- **Seuil de pertinence RAG** (`RAG_SCORE_THRESHOLD=0.65`).
- **Limite de chunks configurable** (`RAG_CHUNK_LIMIT=8`).
- **Logs décisionnels Q&A** — Tokenisation → Graphe → RAG → Contexte LLM.
- **Scores de similarité** dans les logs Docker.
- **Stop words enrichis** (~45 mots français).
- **Modules RAG** — `chunker.py`, `embedder.py`, `vector_store.py`.

#### Modifié
- **Qdrant épinglé** `v1.16.2` (au lieu de `latest`).

#### Fichiers modifiés
`graph.py`, `server.py`, `config.py`, `docker-compose.yml`, `.env.example`, `chunker.py`, `embedder.py`, `vector_store.py`, `models.py`, `requirements.txt`

---

## [0.5.1] — 2026-02-09

### Tokens — Champ email + Hash complet

#### Ajouté
- Champ **email** (optionnel) lors de la création de tokens.
- **Hash complet** (SHA256, 64 chars) dans `token list`.
- Colonne **Email** dans les tables CLI + Shell.
- Fichier `VERSION`.
- Documentation CLI (`scripts/README.md`).

#### Fichiers modifiés
`models.py`, `token_manager.py`, `server.py`, `display.py`, `commands.py`, `shell.py`

---

## [0.5.0] — 2026-02-01

### Version initiale publique

#### Ajouté
- Extraction d'entités/relations guidée par ontologie (LLM).
- Graphe de connaissances Neo4j avec isolation par namespace (multi-tenant).
- Stockage S3 (Dell ECS, AWS, MinIO).
- Interface web interactive (vis-network) avec filtrage avancé et panneau ASK.
- CLI complète (Click + Shell interactif avec prompt_toolkit).
- Authentification Bearer Token avec gestion des tokens.
- Vérification et nettoyage cohérence S3/graphe.
- Question/Réponse avec citation des documents sources.
- 14 outils MCP exposés via HTTP/SSE.
- Support des formats : PDF, DOCX, Markdown, TXT, HTML, CSV.
- 4 ontologies : legal, cloud, managed-services, technical.
