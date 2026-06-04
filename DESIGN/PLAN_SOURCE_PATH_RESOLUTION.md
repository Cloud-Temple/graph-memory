# Plan d'action — Exposer `source_path` dans la recherche Graph-first

> **Statut** : CORRIGÉ APRÈS 3 PASSES CODEX. Architecture validée 2× (jointure graphe rétroactive, pas de mutation Qdrant). 3ᵉ passe : 6/6 résiduels levés + 1 vrai bug code corrigé (`retained` non défini si RAG échoue → `retained = []` avant le `try`) + nettoyages (`uri` au contrat, `_iso` dans graph.py, mentions `document_resolve` purgées). 4ᵉ passe : 4/4 RÉSOLU, reste arbitrage périmètre → tranché par Christophe. Périmètre figé **P1 + P2 + alignement `document_get`/`document_list`** (aucun nouvel outil MCP).
> **Cible** : v3.2.0
> **Contexte demandeur** : Graph Memory est utilisé comme index sémantique opérationnel pour LLMaaS. Les documents sont ingérés avec un `source_path` stable (ex. `repo/MCO/1.Incidents/inc-20251222-cc-api-500-pgsql-down/report.md`). En incident chaud, un agent qui fait une recherche Graph-first doit pouvoir **ouvrir immédiatement le fichier Git canonique** sans détour par `document_list` complet ni `rg` local ambigu.

## 1. Besoin

Quand un agent appelle `memory_search` ou `memory_query`, la réponse doit contenir directement le `source_path` de chaque document/chunk retourné, afin d'ouvrir le fichier source sans appel supplémentaire.

Critère de succès : sur une requête type
`Incident base de données PostgreSQL ne répond plus pgsql down Control Center API 500 saturation WAL`
l'agent reçoit directement les chemins :
```
repo/MCO/1.Incidents/inc-20251222-cc-api-500-pgsql-down/report.md
repo/MCO/1.Incidents/inc-20260126-saturation-pgsql01-prod/incident_report.md
repo/MCO/1.Incidents/inc-20251114-saturation-disque-wal-pgsql01-preprod/report.md
```
**sans** `document_list` complet ni recherche locale.

## 2. État du code (vérifié)

| Élément | État actuel | Référence |
|---|---|---|
| `memory_search` → `documents` | `{id, filename, uri}` | `graph.py:1112-1115` (`get_entity_context`) |
| `memory_query` → `source_documents` | `{id, filename}` | `server.py:1199-1203` + `1264-1268` |
| `memory_query` → `rag_chunks` | pas de `source_path` | `server.py:1254-1262` |
| `document_get(memory_id, document_id)` | **existe déjà**, renvoie déjà `source_path`, `source_modified_at` | `server.py:1731-1821` |
| `document_list` | contient déjà `source_path`, `sha256`(=hash), `ingestion_status`, `chunk_count` | `graph.py:1206-1234` |
| Nœud Document Neo4j | possède **toutes** les propriétés : `id, memory_id, uri, filename, hash, source_path, source_modified_at, size_bytes, text_length, content_type, ingested_at, metadata_json, ingestion_status, last_ingest_job_id, chunk_count` | `graph.py:376-478` (`add_document`) |
| Helper de normalisation | `normalize_source_path()` = `strip().lstrip('/')`, `""`/None → None | `graph.py:330-340` |
| Payload Qdrant par chunk | `memory_id, doc_id, filename, text, chunk_index, total_chunks, section_title, article_number, heading_hierarchy, char_count, token_estimate` — **PAS de `source_path`** | `vector_store.py:173-185` |

**Deux conséquences :**

1. `document_get` couvre déjà le besoin « priorité 3 » en mono-document. Une variante batch (`document_resolve`) a été envisagée puis **écartée de cette release** (cf. §4.5, reco Codex) : faible gain une fois P2 enrichie.
2. Le `source_path` n'est PAS dans le payload Qdrant → pour `rag_chunks`, il faut soit (A) joindre sur le graphe, soit (B) ré-ingérer tout le corpus.

## 3. Décision d'architecture : jointure graphe rétroactive (option A)

Pour `rag_chunks` et `source_documents`, on **ne touche PAS au payload Qdrant**. À la place, en fin de pipeline `memory_query`, on récupère en **une seule requête Neo4j** les métadonnées de tous les `doc_id` apparaissant dans le résultat, puis on injecte `source_path`/`repo_path`/`sha256`/`ingestion_status` par jointure sur `doc_id`.

**Justification :**
- **Rétroactif** : fonctionne immédiatement sur l'index déjà ingéré, **zéro ré-ingestion** (l'option B exigerait de tout ré-ingérer pour que les anciens chunks portent le champ).
- **Source de vérité unique** : `source_path` vit sur le nœud Document (Neo4j), qui est déjà la clé d'idempotence (`normalize_source_path`). Dupliquer dans Qdrant créerait un risque d'incohérence après un remplacement de document.
- **Coût** : 1 requête supplémentaire par `memory_query` (`WHERE d.id IN $ids`), avec au plus `rag_chunk_limit` (8) + N entités doc_ids → négligeable, indexé sur `(memory_id, id)`.
- **Mutualisation** : la même méthode `get_documents_meta` pourra servir de backend à un futur `document_resolve` (hors scope ici) ; elle est utilisée dès maintenant par `memory_query`.

Option B (payload Qdrant) **rejetée** comme mécanisme principal pour cause de non-rétroactivité et de duplication de la source de vérité. (Pourra être ajoutée plus tard comme optimisation pour éviter la jointure, sans changer le contrat.)

## 3bis. Corrections issues de la revue Codex (intégrées)

| # | Sévérité | Correction appliquée au plan |
|---|---|---|
| 1 | BLOQUANT | **Index manquant.** Aucun index sur `(memory_id, id)` (seule la contrainte `(memory_id, source_path)` existe, `graph.py:364-365`). → Ajouter `CREATE INDEX document_memory_id_id IF NOT EXISTS FOR (d:Document) ON (d.memory_id, d.id)` dans `ensure_document_constraints`. Bénéficie aussi à `get_document`. |
| 2 | BLOQUANT | **`source_modified_at` est une string**, pas un DateTime (`add_document` ligne 453 `source_modified_at or ""`, restore ligne 1512). → Ne PAS appeler `.isoformat()` dessus : renvoyer `r["source_modified_at"] or None`. Pour `ingested_at` (vrai DateTime Neo4j) : helper robuste `_iso(v)`. |
| 3 | IMPORTANT | **Contrat `source_path` = canonique normalisé.** Appliquer `normalize_source_path` dans toutes les sorties (`memory_search`, `memory_query`) ET aligner `document_get`/`document_list` (qui renvoient aujourd'hui la valeur brute stockée). |
| 4 | IMPORTANT | **Conserver `hash` ET ajouter `sha256`** (alias) partout pour compat. Champs communs : `id, filename, uri, source_path, repo_path, hash, sha256, ingestion_status (défaut "unknown"), chunk_count, last_ingest_job_id`. |
| 5 | IMPORTANT | **Perf : pas de gros `IN`.** `get_entity_context` fait `collect(DISTINCT d)` sans limite → une entité fréquente = potentiellement des milliers de doc_ids. → Stratégie : `get_entity_context` renvoyant désormais les docs **déjà enrichis**, `memory_query` construit la map meta directement depuis `ctx.documents`, et n'appelle `get_documents_meta` QUE pour les doc_ids issus du RAG **non déjà couverts**. + log du nombre de doc_ids enrichis. |
| 6 | MINEUR | Tester un chunk RAG legacy sans `doc_id` (`doc_id == ""`) → `source_path: null`, `repo_path: null`, pas de KeyError. |
| 7 | MINEUR | `entities[].source_documents` reste une **liste de filenames** (résumé humain) — documenté tel quel ; le top-level `source_documents` porte les métadonnées complètes. |
| 8 | MINEUR | `return` : remplacer la ligne `"source_documents": list(source_documents.values())` par `"source_documents": enriched_sources` (le retour est déjà une liste, pas de double clé). |

### Helper date robuste — défini dans `graph.py` (module-level, avant la classe), appelé par `get_documents_meta`

```python
def _iso(v):
    if v is None: return None
    if hasattr(v, "to_native"):  # neo4j.time.DateTime
        return v.to_native().isoformat()
    if hasattr(v, "isoformat"):  # datetime natif
        return v.isoformat()
    return str(v)  # déjà une string (cas source_modified_at)
```

## 4. Modifications détaillées

### 4.1. Helper `derive_repo_path` (graph.py, à côté de `normalize_source_path`)

```python
@staticmethod
def derive_repo_path(source_path: Optional[str]) -> Optional[str]:
    """repo/MCO/x/report.md → MCO/x/report.md ; sinon None.
    S'appuie sur le source_path normalisé."""
    norm = GraphService.normalize_source_path(source_path)
    if norm and norm.startswith("repo/"):
        return norm[len("repo/"):] or None
    return None
```

### 4.1bis. Index `(memory_id, id)` — finding #1 (graph.py `ensure_document_constraints`)

Créer l'index **AVANT** la contrainte d'unicité, dans son **propre `try`** (réserve Codex 2ᵉ passe : si des doublons legacy `source_path` font échouer la contrainte, l'index ne doit pas être bloqué) :
```python
# try séparé, AVANT la contrainte (memory_id, source_path)
try:
    async with self.session() as session:
        await session.run(
            """
            CREATE INDEX document_memory_id_id IF NOT EXISTS
            FOR (d:Document) ON (d.memory_id, d.id)
            """
        )
except Exception as e:
    print(f"⚠️ [Graph] Index (memory_id,id) non créé: {e}", file=sys.stderr)
```
Indispensable avant `get_documents_meta` (sinon scan label). Bénéficie aussi à `get_document`.

### 4.2. Nouvelle méthode `get_documents_meta` (graph.py)

```python
async def get_documents_meta(self, memory_id: str, doc_ids: list[str]) -> dict[str, dict]:
    """Métadonnées de plusieurs documents en une requête. Clé = doc_id.
    Documents absents → simplement omis du dict (pas d'erreur)."""
    if not doc_ids:
        return {}
    async with self.session() as session:
        result = await session.run(
            """
            MATCH (d:Document {memory_id: $memory_id})
            WHERE d.id IN $doc_ids
            RETURN d.id as id, d.filename as filename, d.uri as uri,
                   d.hash as hash, d.source_path as source_path,
                   d.source_modified_at as source_modified_at,
                   d.ingested_at as ingested_at,
                   d.ingestion_status as ingestion_status,
                   d.last_ingest_job_id as last_ingest_job_id,
                   d.chunk_count as chunk_count,
                   d.size_bytes as size_bytes,
                   d.text_length as text_length,
                   d.content_type as content_type
            """,
            memory_id=memory_id, doc_ids=list(doc_ids),
        )
        out = {}
        async for r in result:
            sp = self.normalize_source_path(r["source_path"])
            out[r["id"]] = {
                "id": r["id"],
                "filename": r["filename"],
                "uri": r["uri"],
                "hash": r["hash"],      # conservé pour compat (finding #4)
                "sha256": r["hash"],    # alias métier
                "source_path": sp,
                "repo_path": self.derive_repo_path(sp),
                "source_modified_at": r["source_modified_at"] or None,  # string, PAS de .isoformat() (finding #2)
                "ingested_at": _iso(r["ingested_at"]),  # DateTime Neo4j → helper robuste
                "ingestion_status": r["ingestion_status"] or "unknown",
                "last_ingest_job_id": r["last_ingest_job_id"],
                "chunk_count": r["chunk_count"] or 0,
                "size_bytes": r["size_bytes"] or 0,
                "text_length": r["text_length"] or 0,
                "content_type": r["content_type"],
            }
        return out
```

### 4.3. Priorité 1 — `memory_search` (graph.py `get_entity_context`, ligne 1112)

```python
documents = [
    {
        "id": d["id"],
        "filename": d["filename"],
        "uri": d["uri"],
        "source_path": (sp := self.normalize_source_path(d.get("source_path"))),
        "repo_path": self.derive_repo_path(sp),
        "hash": d.get("hash"),          # conservé pour compat (finding #4)
        "sha256": d.get("hash"),        # alias métier
        "ingestion_status": d.get("ingestion_status") or "unknown",
        "chunk_count": d.get("chunk_count") or 0,
        "last_ingest_job_id": d.get("last_ingest_job_id"),
    }
    for d in record["docs"] if d
]
```
Le nœud `d` complet est déjà retourné par le Cypher existant → **aucun changement de requête**. Comme `memory_search` renvoie `context.documents` tel quel, la priorité 1 est couverte par cette seule modification.

> Note : la sortie réelle de `memory_search` est `results[].documents` (imbriqué par entité), pas un tableau `documents` à plat comme dans l'exemple de la demande. Le contenu par document est conforme.

### 4.4. Priorité 2 — `memory_query` (server.py)

**Stratégie perf (finding #5)** : `get_entity_context` renvoie désormais les docs déjà enrichis (cf. 4.3). `memory_query` accumule donc la map `meta` **dans la boucle existante** sur `ctx.documents` (étape 2, déjà en mémoire, aucune requête), et n'interroge `get_documents_meta` QUE pour les `doc_id` apparus côté RAG et **absents** de cette map.

**Étape 2 (boucle existante, ligne ~1189)** — on initialise `meta = {}` avant la boucle, et dans la boucle sur `ctx.documents` on alimente la map (correction du `graph_docs_seen` fantôme, finding résiduel) :
```python
meta = {}  # doc_id -> métadonnées enrichies, source de vérité unique
...
for doc in ctx.documents:                       # doc est déjà enrichi (4.3)
    if isinstance(doc, dict) and doc.get("id"):
        meta.setdefault(doc["id"], doc)          # alimente meta sans requête
        ...                                       # (logique source_documents inchangée)
```

**⚠️ Pré-requis (BLOQUANT, 3ᵉ passe)** : `retained` n'est défini qu'à l'intérieur du `try` RAG (server.py:1250). Si le RAG échoue, `for cr in retained` lèverait `NameError`. → initialiser **`retained = []`** avant le `try` (à côté de `rag_chunks = []`, ligne ~1231).

**En fin de pipeline, avant le `return`** (après l'étape RAG, ~ligne 1276) :
```python
# Compléter uniquement les doc_ids RAG manquants (pas de gros IN sur entité fréquente)
missing = [cr.chunk.doc_id for cr in retained   # retained = [] garanti défini (cf. pré-requis)
           if cr.chunk.doc_id and cr.chunk.doc_id not in meta]
if missing:
    try:
        meta.update(await get_graph().get_documents_meta(memory_id, list(set(missing))))
    except Exception as e:
        print(f"⚠️ [Query] Enrichissement source_path échoué: {e}", file=sys.stderr)
print(f"🧭 [Query] {len(meta)} documents enrichis (source_path)", file=sys.stderr)

def _doc_fields(m):  # contrat commun (finding #4) — hash ET sha256
    return {
        "uri": m.get("uri"),     # ajouté (3ᵉ passe) — utile pour récupérer le doc S3
        "source_path": m.get("source_path"),
        "repo_path": m.get("repo_path"),
        "hash": m.get("hash"),
        "sha256": m.get("sha256"),
        "ingestion_status": m.get("ingestion_status", "unknown"),
        "chunk_count": m.get("chunk_count", 0),
        "last_ingest_job_id": m.get("last_ingest_job_id"),
    }
# Note : `base` (id, filename) déjà présent dans source_documents ; `uri` peut y être None
# si le doc provient du graphe (où get_entity_context fournit uri) — _doc_fields l'écrase
# avec la valeur de meta qui fait autorité.

# Enrichir source_documents (contrat complet)
enriched_sources = [{**base, **_doc_fields(meta.get(doc_id, {}))}
                    for doc_id, base in source_documents.items()]

# Enrichir rag_chunks (source_path + repo_path suffisent pour ouvrir le fichier)
for ch in rag_chunks:
    m = meta.get(ch.get("doc_id"), {})
    ch["source_path"] = m.get("source_path")
    ch["repo_path"] = m.get("repo_path")
```
Puis `return ... "source_documents": enriched_sources`.

> Détail : `source_documents` est aujourd'hui un dict `doc_id -> {id, filename}` rempli à deux endroits (contexte graphe ligne 1199, et chunks RAG ligne 1264). La jointure finale couvre les deux origines de façon uniforme — pas besoin de modifier ces deux points d'insertion.

### 4.5. Périmètre figé : **P1 + P2 + alignement des outils existants** (aucun nouvel outil MCP)

`document_resolve` est **écarté de cette release** : `document_get` (mono-doc) existe déjà, et le gain réel est faible une fois `source_documents`/`rag_chunks` correctement enrichis. Pas de nouvelle surface MCP.

**Décision Christophe (post 4ᵉ passe Codex)** : on **inclut** l'alignement de `document_get` et `document_list` pour tenir le contrat « `source_path` canonique + `repo_path` **partout** » (finding #3) sur les 4 outils. Ce n'est PAS un nouvel outil, juste 2 petites éditions sur l'existant — éditions concrètes :
- `graph.get_document` (ligne 609) : `"source_path": self.normalize_source_path(record["source_path"])` + ajout `"repo_path": self.derive_repo_path(...)`. Optionnellement exposer `sha256`/`ingestion_status`/`chunk_count` (déjà dans le nœud) pour homogénéité avec `document_list`.
- `get_full_graph`/`document_list` (ligne ~1218) : normaliser `source_path` au moment de poser `doc_entry["source_path"]` + dériver `repo_path`.

→ Pas de changement de `system_about` (toujours 40 outils, aucun nouvel outil).

## 5. Tests (recette `scripts/tests/`)

- `memory_search` : un document avec `source_path` connu → la réponse contient `source_path`, `repo_path` (si `repo/...`), `sha256`, `ingestion_status`.
- `memory_query` : même mémoire → `source_documents[].source_path` ET `rag_chunks[].source_path` présents et cohérents avec le `doc_id`.
- `repo_path` : `repo/MCO/x/report.md` → `MCO/x/report.md` ; un `source_path` sans préfixe `repo/` → `repo_path` = null/absent.
- Document **legacy sans source_path** → `source_path = null`, `repo_path = null`, pas d'erreur.
- **Chunk RAG sans `doc_id`** (`doc_id == ""`, cas legacy distinct du précédent — finding #6) → `source_path = null`, `repo_path = null`, pas de KeyError.
- `get_documents_meta` avec un id inexistant → simplement omis du dict, pas d'erreur.
- `document_get`/`document_list` : `source_path` renvoyé normalisé + `repo_path` présent (cohérence inter-outils).
- Non-régression : recette complète 206/206 doit rester verte.

## 6. Points soumis à la revue Codex

1. La jointure graphe (option A) est-elle préférable au payload Qdrant (option B) compte tenu de la rétroactivité et de la source de vérité unique ? Risque manqué ?
2. `get_documents_meta` : la requête `WHERE d.id IN $doc_ids` est-elle correctement indexée (contrainte/index sur `(memory_id, id)` ?) ? Risque de full scan ?
3. Normalisation : faut-il renvoyer le `source_path` **normalisé** (`normalize_source_path`) ou la valeur brute stockée ? Risque d'incohérence si l'ingestion a stocké une valeur non normalisée.
4. `repo_path` dérivé : préfixe `repo/` en dur — robuste ? Faut-il le rendre configurable (env) ?
5. Cohérence des champs entre `memory_search`, `memory_query`, `document_get`, `document_list` (même noms, même sémantique `sha256` vs `hash`, `ingestion_status` défaut `unknown`).
6. Périmètre : livrer P1+P2 seules d'abord (gain immédiat) ou inclure P3 dans la même release ?
7. Impact perf de la requête supplémentaire dans `memory_query` (chemin chaud incident) — acceptable ?
