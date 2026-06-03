# Design — Ingestion asynchrone, idempotente et observable

> **Statut** : ✅ Design figé — révisé et arbitré après revue Codex (cf. §11)
> **Date** : 3 juin 2026
> **Auteur** : Christophe Lesur & Cloud Temple
> **Cible** : Graph Memory v3.1.0
> **Inspiration** : `live-mem/core/consolidation_queue.py` (Live Memory, issue #20)

---

## 1. Contexte & problème

L'ingestion Graph Memory est aujourd'hui **entièrement synchrone** ([`memory_ingest`](../src/mcp_memory/server.py)). Le client tient la connexion ouverte pendant tout le pipeline :

```
décodage base64 → validation → dédup SHA-256 → upload S3 → extraction texte
→ extraction LLM (chunked, jusqu'à 600 s/chunk) → Neo4j (doc + entités/relations)
→ chunking sémantique → embeddings LLMaaS → Qdrant → réponse
```

Sur un lot de routine LLMaaS (~45 fichiers Markdown, ~560 KB), l'extraction LLM + embeddings par document rend ce mode impilotable :

- le client peut **dépasser son timeout** ;
- il reste **silencieux longtemps**, sans visibilité sur la progression ;
- s'il est **interrompu**, le serveur poursuit partiellement sans état récupérable.

### 1.1 Trois écarts structurants vs. l'état actuel

1. **Déduplication par hash, pas par `source_path`.** La clé actuelle est le SHA-256 du *contenu* (`get_document_by_hash`). `source_path` est stocké sur le nœud `Document` mais **n'est jamais une clé de recherche**. La demande veut en faire la **clé métier stable**.
2. **Aucun découplage soumission / exécution.** Pas de réponse immédiate, pas de reprise après timeout.
3. **Aucune notion de job** (statut, progression, annulation, listing).

---

## 2. Objectifs

Ajouter une **API d'ingestion asynchrone, idempotente et observable**, en réutilisant le pipeline existant (aucune réécriture de l'extraction).

### 2.1 Critères d'acceptation

- Un client peut soumettre 50 documents et **récupérer immédiatement la main**.
- Un **timeout client ne casse pas** l'ingestion serveur.
- On peut **reprendre le suivi** par `job_id` **ou** par `source_path`.
- Les **relances sont sûres** : pas de doublon si `source_path` + checksum identiques.
- Les **remplacements sont explicites** si checksum différent.
- `document_list` expose `source_path`, checksum, statut d'ingestion, date, job associé.
- `storage_check` **ne signale aucun orphelin** après succès d'un job.

---

## 3. Décisions d'architecture

| # | Décision | Choix retenu | Justification |
|---|----------|--------------|---------------|
| D1 | **Stockage de l'état des jobs** | **Queue in-memory best-effort** (calqué sur Live Memory) **+ marqueur `ingestion_status` durable sur le nœud `Document`** (arbitrage A, §11.2) | Pattern éprouvé, livraison rapide ; le marqueur durable supprime le risque de faux `skipped` sur ingestion partielle. Voir §3.1. |
| D2 | **Clé d'idempotence** | **`source_path` primaire + `sha256` détecteur de changement**, fallback hash pour le legacy | Conforme à la demande ; tolère les documents historiques ingérés sans `source_path`. |
| D3 | **Périmètre de livraison** | **MCP + CLI (Click + shell) + recette de tests** ; **console `/admin` ajoutée** (page « Ingest Jobs ») | Règle d'alignement 3 couches respectée. La page `/admin` (initialement reportée) a finalement été livrée : listing avec rafraîchissement auto (polling 3 s), filtres mémoire/statut, barre de progression, annulation, détail, et soumission asynchrone (SHA-256 calculé navigateur). |
| D4 | **Modèle de parallélisme** | **Un worker `asyncio` par `memory_id`** | Sérialise les écritures Neo4j/Qdrant d'une même mémoire (zéro conflit), tout en permettant le parallélisme entre mémoires distinctes. |

### 3.1 Nuance importante sur le choix in-memory (D1)

L'**historique des jobs est éphémère** : un redémarrage du conteneur perd les jobs `queued`/`running`. **Mais l'idempotence documentaire, elle, est durable** car `source_path` + `sha256` vivent dans Neo4j.

Conséquence : après un restart, le client **re-soumet** son lot → il obtient `skipped` pour tout ce qui était déjà ingéré. **La reprise *fonctionnelle* survit même si le *journal de jobs* ne survit pas.** C'est ce qui rend le choix in-memory défendable.

Garantie annoncée explicitement dans chaque réponse : `guarantee: "in_memory_best_effort"`.

> **Évolution future possible** : journal des jobs persisté dans un nœud `:IngestJob` Neo4j (survie au restart), sans changer l'API. Hors périmètre v3.1.0.

---

## 4. Architecture cible

### 4.1 Vue d'ensemble

```
                      ┌─────────────────────────────────────────────┐
  memory_ingest_async │  IngestQueueService (in-memory)             │
  ───────────────────▶│                                             │
                      │  deque FIFO par memory_id                   │
                      │  ┌──────────┐   ┌──────────┐                │
  ingest_job_status   │  │ worker   │   │ worker   │  1 par         │
  ◀───────────────────│  │ mem A    │   │ mem B    │  memory_id     │
                      │  └────┬─────┘   └────┬─────┘                │
  ingest_job_list     │       │              │                      │
  ingest_job_cancel   │       ▼              ▼                      │
                      │   _run_ingest_pipeline(progress_cb,         │
                      │                       cancel_check)         │
                      └───────────────┬─────────────────────────────┘
                                      ▼
                       S3 ─ texte ─ LLM ─ Neo4j ─ Qdrant
```

### 4.2 Refactor préalable (zéro régression)

Le corps du pipeline est extrait dans une coroutine réutilisable :

```
core/ingest_pipeline.py
  async def run_ingest_pipeline(..., progress_cb=None, cancel_check=None) -> dict
```

- Le `memory_ingest` synchrone actuel l'appelle (comportement **inchangé**).
- Le worker asynchrone l'appelle aussi.
- **Le pipeline n'est écrit qu'une seule fois.**

### 4.3 Module `core/ingest_queue.py`

Transposition directe de `consolidation_queue.py` :

```python
@dataclass
class IngestJob:
    job_id: str
    memory_id: str
    source_path: str
    sha256: str
    filename: str
    status: str                 # queued|running|succeeded|failed|cancelled|skipped
    current_step: str
    progress_percent: int
    created_entities: int
    created_relations: int
    document_id: str | None
    batch_id: str | None
    created_at / started_at / updated_at / finished_at: str | None
    error: str | None
    guarantee: str = "in_memory_best_effort"
    # + payload d'entrée stocké (content_base64, metadata, source_modified_at, replace_existing)
    cancel_requested: bool = False
```

`IngestQueueService` :
- `deque` FIFO + un worker `asyncio.Task` **par `memory_id`** ;
- `_state_lock` (`asyncio.Lock`) protège toutes les transitions ;
- **coalescing** : un job en attente pour le même `(memory_id, source_path, sha256)` est renvoyé tel quel (pas de doublon de job) ;
- trim d'historique (`max_history`), comme Live Memory ;
- contrat **no-auto-polling** repris de Live Memory (l'agent ne doit pas poller en boucle).

### 4.4 Annulation coopérative (best effort, sans corruption)

`cancel_check()` est testé **aux frontières de phase** :

| Moment de l'annulation | Comportement |
|------------------------|--------------|
| Avant écriture Neo4j (S3, texte, LLM) | **Abandon propre** : rollback de l'objet S3 éventuellement uploadé, statut `cancelled`. |
| Après début d'écriture Neo4j/Qdrant | La phase en cours se **termine**, puis `delete_document` retire doc + entités orphelines + chunks Qdrant + objet S3 → **aucun orphelin**. |

### 4.5 Mapping de la progression

| Phase | `current_step` | `progress_percent` |
|-------|----------------|--------------------|
| Décodage base64 | `decode` | 5 |
| Upload S3 | `s3_upload` | 10 |
| Extraction texte | `text_extract` | 15 |
| Extraction LLM | `llm_extract` | 15 → 60 (proportionnel aux chunks) |
| Neo4j (doc + entités/relations) | `graph_write` | 70 |
| Chunking sémantique | `chunking` | 75 |
| Embeddings LLMaaS | `embedding` | 75 → 95 (par batch) |
| Qdrant | `vector_store` | 98 |
| Terminé | `done` | 100 |

Les `_log()` existants du pipeline alimentent directement `current_step`.

---

## 5. Idempotence documentaire (D2)

### 5.1 Nouveau lookup graphe

`core/graph.py` :
- `get_document_by_source_path(memory_id, source_path) -> Document | None`
- index Neo4j sur `(memory_id, source_path)`.

### 5.2 Garde d'intégrité du checksum

Le serveur **recalcule** le SHA-256 du contenu décodé et le compare au `sha256` fourni → **rejet** si divergence. Le checksum obligatoire de la demande sert réellement de contrôle d'intégrité de transport.

### 5.3 Table de décision

| Cas | Action | Statut |
|-----|--------|--------|
| `source_path` inconnu | ingestion normale | `succeeded` |
| connu + **même** `sha256` + `ingestion_status == succeeded` | aucun travail | `skipped` |
| connu + même `sha256` mais `ingestion_status != succeeded` | ingestion partielle/incomplète → ré-ingestion | `succeeded` |
| connu + `sha256` **différent** + `replace_existing=false` (**défaut**) | refus prudent, conflit signalé sans rien écraser | `changed_skipped` |
| connu + `sha256` différent + `replace_existing=true` (explicite) | `delete_document_everywhere()` puis ré-ingestion | `succeeded` |
| `source_path` absent (legacy) | fallback sur la dédup SHA-256 actuelle | selon hash |

`skipped` n'est renvoyé **que si `ingestion_status == succeeded`** (arbitrage A). Le remplacement passe par `delete_document_everywhere()` (cf. §11.1, B2) → **pas de doublon, pas d'orphelin**, et `storage_check` reste cohérent.

---

## 6. Surface d'API MCP

### 6.1 Nouveaux outils (5)

| Outil | Entrée | Permission | Réponse |
|-------|--------|------------|---------|
| `memory_ingest_async` | compat. `memory_ingest` + `source_path` **obligatoire**, `sha256` **obligatoire**, `job_id?`, `replace_existing=false` (défaut) | 🔑 write | `{job_id, status (queued\|running\|skipped\|changed_skipped), document_id?, message}` — immédiate |
| `ingest_job_status` | `job_id` | 🔑 read | `status, current_step, progress_percent, created_entities, created_relations, started_at, updated_at, finished_at, error?` |
| `ingest_job_list` | `memory_id, status?, source_path?` | 🔑 read | liste des jobs (reprise après timeout) |
| `ingest_job_cancel` | `job_id` | 🔑 write | best effort |
| `memory_ingest_batch_async` | `memory_id, documents[], replace_existing?` | 🔑 write | `batch_id`, liste des `job_id`, agrégat |

`memory_ingest_async` : si `source_path` + `sha256` déjà présents en base → réponse `skipped` **immédiate sans créer de job**.

### 6.2 Contrat du batch

`memory_ingest_batch_async` expose :
- nombre **total** ;
- compteurs **queued / running / succeeded / failed / skipped** ;
- **liste des documents en erreur** ;
- **reprise sans duplication** (chaque document est résolu par `source_path` + `sha256`).

### 6.3 Enrichissement de `document_list`

Exposer pour chaque document : `source_path`, `sha256` (checksum), **statut d'ingestion**, **date**, **`job_id` associé**.

### 6.4 Impact sur `system_about`

Décompte des outils MCP : **35 → 40**, nouvelle sous-catégorie « Ingestion asynchrone ».

---

## 7. Alignement CLI (règle des 3 couches)

API MCP → CLI Click → Shell interactif, comme pour tout outil du projet :

| Couche | Commandes |
|--------|-----------|
| CLI Click | `ingest-async`, `job-status`, `job-list`, `job-cancel`, `ingest-batch-async` |
| Shell interactif | équivalents + autocomplétion + aide |
| Affichage Rich | barre de progression, table des jobs, agrégat batch |

Option humaine `--watch` : poll local côté CLI (le contrat **no-auto-polling** reste valable pour les agents MCP).

---

## 8. Tests de recette (`scripts/test_recette.py`)

- soumission renvoie immédiatement un `job_id` ;
- `skipped` si `source_path` + `sha256` identiques ;
- remplacement **sans doublon** si `sha256` différent ;
- reprise du suivi par `source_path` ;
- annulation propre (aucun orphelin) ;
- agrégat batch correct (total / queued / running / succeeded / failed / skipped) ;
- **`storage_check` sans orphelin** après succès et après rollback d'échec.

---

## 9. Fichiers touchés

| Fichier | Nature |
|---------|--------|
| `src/mcp_memory/core/ingest_pipeline.py` | **nouveau** — pipeline réutilisable |
| `src/mcp_memory/core/ingest_queue.py` | **nouveau** — queue + worker (pattern live-mem) |
| `src/mcp_memory/core/graph.py` | `get_document_by_source_path` + index |
| `src/mcp_memory/server.py` | 5 outils MCP + enrichissement `document_list` + `system_about` |
| `scripts/cli/{commands,shell,display}.py` | alignement CLI 3 couches |
| `scripts/test_recette.py` | nouveaux tests |
| `README.md` / `CHANGELOG.md` / `DESIGN/SPECIFICATION.md` | documentation |

---

## 10. Risques & points de vigilance

- **Pression mémoire** : le payload `content_base64` est conservé dans `IngestJob` jusqu'à traitement → libérer (`del`) dès consommation par le worker, comme le fait déjà le pipeline synchrone.
- **Backpressure batch** : 50 documents en file pour une même mémoire = traitement séquentiel (un worker/mémoire). Acceptable et voulu ; le `ingest_job_list` donne la position en file.
- **Cohérence `storage_check`** : impérativement valider le rollback S3 sur échec/annulation après upload mais avant fin de pipeline.
- **Compatibilité legacy** : documents sans `source_path` → fallback hash ; prévoir un éventuel backfill de `source_path` ultérieur.

---

## 11. Revue Codex & corrections (3 juin 2026)

Revue critique du design confronté au code réel. Synthèse priorisée et résolutions retenues.

### 11.1 Corrections intégrées (sans nouvel arbitrage)

| # | Constat (vérifié dans le code) | Correction retenue |
|---|--------------------------------|--------------------|
| **B2** | `GraphService.delete_document` ([graph.py:476](../src/mcp_memory/core/graph.py)) **ne supprime que Neo4j**. L'orchestrateur multi-backend réel est l'outil `document_delete` ([server.py:1798](../src/mcp_memory/server.py)), qui supprime S3 **avant** Qdrant (incohérence possible si Qdrant échoue). | Créer un service **`delete_document_everywhere()`** ordonné et compensable (**Qdrant, puis Neo4j, puis S3 — S3 en dernier** pour ne pas créer d'orphelin vu par storage_check ; statut `cleanup_pending` si une étape échoue). Le remplacement et l'annulation s'appuient sur **lui**, pas sur `delete_document`. Mon affirmation initiale « delete_document retire S3+Qdrant+Neo4j » était **fausse** au niveau graph.py. |
| **B1** | `add_document` crée en `CREATE` sans verrou ; un simple index n'empêche pas deux docs avec le même `source_path` sous concurrence (sync + async, plusieurs workers Uvicorn). | **Contrainte d'unicité** Neo4j sur `(memory_id, source_path_normalisé)` + normalisation de `source_path` + check-then-create dans **une transaction unique**. Détection/migration des doublons existants au déploiement. |
| **B3** | `add_entities_and_relations` ([graph.py:589](../src/mcp_memory/core/graph.py)) incrémente `mention_count`, enrichit `source_docs`, descriptions et poids de relations ; `delete_document` ne décrémente pas proprement les entités **partagées**. L'annulation « sans corruption » est donc trop forte. | Reformuler la garantie : l'annulation **après début d'écriture graphe** laisse le pipeline **terminer le document courant** puis le supprime via `delete_document_everywhere()`. On **n'interrompt jamais en plein milieu** d'une transaction d'enrichissement. Cible moyen terme : provenance par document + compteurs dérivés des relations `MENTIONS`. |
| **I5** | `storage_check` ne couvre aujourd'hui que Neo4j ↔ S3. Il ne détecte ni chunks Qdrant orphelins/manquants, ni doublons `source_path`, ni ingestion partielle. | Étendre `storage_check` (ou ajouter `consistency_check`) : S3 + Neo4j + **Qdrant** + doublons `source_path` + documents `ingestion_status != succeeded` + chunks attendus vs présents. |
| **I7** | Le coalescing ne couvrait que le job *en attente*. | Verrou logique par `(memory_id, source_path_normalisé)` : job *running* pour le même `source_path` → nouveau job mis en file derrière ; deux versions du même fichier dans un batch → sérialisées ; `job_id` client identique → idempotent. |
| **I8** | Stocker `content_base64` dans `IngestJob` peut faire exploser la RSS (50 docs en base64). | Quotas **`max_queued_jobs`** et **`max_queued_bytes`** (par mémoire + global), rejet explicite **`queue_full`**, libération immédiate du base64 dès consommation par le worker. |
| **m9** | Statuts terminaux à expliciter pour le trim d'historique. | Statuts terminaux = `{succeeded, failed, cancelled, skipped, changed_skipped}` ; seuls eux sont éligibles au trim. |
| **m11** | Tests « succès/skipped/remplacement » trop complaisants. | Ajouter des **tests de panne injectée** : après upload S3, après `add_document`, après quelques entités, pendant Qdrant, pendant annulation, et **restart simulé**. |

### 11.2 Arbitrages tranchés (Christophe, 3 juin 2026)

**A — Marqueur d'ingestion durable sur le nœud `Document` (findings I4 + m10). ✅ ADOPTÉ.**
Constat : avec un état purement in-memory, un crash entre l'écriture Neo4j et Qdrant ferait répondre **`skipped` à une re-soumission alors que les vecteurs manquent** (incomplétude silencieuse).
**Décision** : la **queue** reste in-memory (D1), mais on persiste sur le nœud `Document` un **état d'ingestion durable** : `ingestion_status` (`succeeded` uniquement si Qdrant OK), `last_ingest_job_id`, `checksum`, `ingested_at`, `chunk_count`. Règle ferme : **`skipped` uniquement si `ingestion_status == succeeded`**. Compromis léger (pas le store de jobs persistant complet) qui supprime le risque #4.

**B — Défaut de `replace_existing` (finding I6). ✅ ADOPTÉ.**
**Décision** : défaut = **`false`**. Sur `source_path` connu + checksum différent → statut **`changed_skipped`** sans rien écraser ; le remplacement exige `replace_existing=true` explicite. Conforme au critère « remplacements explicites ».

### 11.3 Verdict Codex

> « La direction est bonne pour la queue et l'observabilité, mais le design surestimait la sûreté actuelle du pipeline. Deux corrections structurantes : idempotence durable avec contrainte/transaction sur `source_path`, et un modèle distinguant `succeeded` des états partiels. »

### 11.4 Corrections appliquées après la 2ᵉ revue Codex (sur le code implémenté)

Revue complète du code v3.1.0 ; verdict initial « non mergeable ». Correctifs appliqués (recette 202/202 PASS après correction) :

| # | Sévérité | Correctif |
|---|----------|-----------|
| 1 | 🔴 Bloquant | **TOCTOU idempotence** : la décision `resolve_ingestion` est désormais **re-jouée dans le worker** juste avant le pipeline (sous sérialisation 1 worker/mémoire). `skip`/`conflict` deviennent des statuts terminaux du job sans lancer le pipeline. |
| 2 | 🔴 Bloquant | **Annulation coopérative complète** : ajout de checkpoints `cancel_check` après l'écriture graphe, **entre chaque batch d'embeddings**, et avant la finalisation. `IngestCancelled` propage (non masquée par le `except` Qdrant) → rollback complet via `delete_document_everywhere`. |
| 4 | 🔴 Bloquant | **Contrainte d'unicité** : `ensure_document_constraints` est appelé depuis `add_document` → couvre les **deux** chemins (sync + async). Le flag n'est pas marqué prêt en cas d'échec (retry). Log clarifié : l'unicité n'est PAS garantie tant que la contrainte n'existe pas. |
| 5 | 🟠 Important | `delete_document_everywhere` : docstrings alignées sur l'ordre réel **Qdrant → Neo4j → S3** (S3 en dernier pour ne pas créer d'orphelin vu par `storage_check`). |
| 9 | 🟠 Important | `--watch` (CLI + shell) : `time.sleep` → `await asyncio.sleep` (ne bloque plus l'event loop). |
| 10 | 🔵 Mineur | `submit` : l'idempotence sur `job_id` client est vérifiée **avant** les quotas (un resubmit ne reçoit plus `queue_full`). |

### 11.5 Scope étendu traité (3ᵉ passe)

| # | Sévérité | Correctif |
|---|----------|-----------|
| 3 | 🟠 | **`cleanup_pending` durable** : `_rollback` renvoie les erreurs de `delete_document_everywhere` ; si le nœud Neo4j survit à un rollback incomplet, il est marqué `ingestion_status="cleanup_pending"` (visible dans `storage_check.consistency.partial_ingestions`). Les erreurs de rollback sont remontées dans le résultat du job. |
| 6 | 🟠 | **`storage_check` étendu** : nouvelle section `consistency` couvrant les **vecteurs Qdrant orphelins** (chunks sans Document Neo4j), les **chunks manquants** (doc `succeeded` + `chunk_count>0` mais 0 vecteur), les **doublons `source_path`** et les **ingestions partielles** (`running`/`failed`/`cleanup_pending`). Nouvelles méthodes `VectorStoreService.count_document_chunks` / `list_doc_ids`. Statut global inchangé (`ok`) ; les findings vivent dans `consistency.issues`. |
| 11 | 🔵 | **Suivi batch complet** : les items `skipped`/`changed_skipped` d'un lot sont désormais enregistrés comme **jobs terminaux** → `ingest_job_list(batch_id=…)` reflète l'intégralité du lot. |
| 12 | 🔵 | **Tests de panne** : test 8.14 (document vide → échec d'ingestion → `storage_check` sans orphelin ni incohérence), test 8.13 renforcé sur la section `consistency`. Recette portée à **205/205 PASS**. |

**Restant assumé (choix, hors périmètre)** : `memory_ingest` synchrone conserve la dédup par hash (rétro-compat ; l'idempotence `source_path` est l'apanage de l'API async) ; le rollback graphe ne décrémente pas l'enrichissement des entités partagées (limite documentée, cf. B3 — garantie « best-effort, sans orphelin », pas « sans altération d'entité partagée »).

### 11.6 Durcissement (3ᵉ revue Codex)

3ᵉ revue → nouveaux correctifs (recette 205/205 PASS) :

| # | Sévérité | Correctif |
|---|----------|-----------|
| 1 | 🔴 | **TOCTOU skip/conflict** : la décision terminale `skipped`/`changed_skipped` est désormais prise **sous `_state_lock`** et **bloquée s'il existe un job non terminal sur le même `source_path`** (`_find_active_source_path_locked`) → dans ce cas on met en file et le worker rejoue `resolve_ingestion`. |
| 2 | 🔴 | **Remplacement** : le résultat de `delete_document_everywhere` (ancien doc) est **contrôlé** ; en cas d'erreur, le pipeline **abandonne** en `error` (pas de nouvelle version `succeeded` au-dessus de vecteurs orphelins) et marque l'ancien nœud `cleanup_pending` s'il survit. |
| 3 | 🔴 | **Worker** : si la re-résolution d'idempotence **échoue** (Neo4j indisponible…), le job passe en `failed` — **jamais d'ingestion à l'aveugle**. |
| 4 | 🟠 | **`storage_check`** compare le **compte réel** de vecteurs Qdrant (`count_document_chunks`) à `chunk_count` (détecte les vectorisations partielles, pas seulement l'absence totale). |
| 5 | 🟠 | **`list_doc_ids`** ne renvoie `set()` que pour collection absente (404) ; **toute autre erreur est propagée** (plus de faux positifs d'orphelins/chunks manquants). |
| 6 | 🟠 | **`delete_document_everywhere`** : un `s3_deleted == False` (URI existante) est désormais compté comme **erreur** (S3 delete est idempotent → False = vraie erreur). |
| 7 | 🟠 | **`document_delete`** renvoie **`partial_deleted`** (au lieu de `deleted`) quand un backend a échoué. |
| 8 | 🔵 | Commentaire d'ordre de suppression corrigé dans `document_delete` (Qdrant → Neo4j → S3). |
