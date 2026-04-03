# Guide d'intégration — Graph Memory + Cline (VS Code)

> **Version** : 2.1 | **Date** : 3 avril 2026
> **Audience** : Développeurs et utilisateurs de Cline dans VS Code
> **Prérequis** : Graph Memory déployé (local ou distant), extension Cline installée

---

## Table des matières

1. [Vue d'ensemble](#1-vue-densemble)
2. [Prérequis](#2-prérequis)
3. [Configuration rapide (5 minutes)](#3-configuration-rapide-5-minutes)
4. [Configuration détaillée](#4-configuration-détaillée)
5. [Premiers pas avec Cline](#5-premiers-pas-avec-cline)
6. [Cas d'usage courants](#6-cas-dusage-courants)
7. [Les 30 outils à disposition](#7-les-30-outils-à-disposition)
8. [Bonnes pratiques](#8-bonnes-pratiques)
9. [Dépannage](#9-dépannage)
10. [Architecture technique](#10-architecture-technique)

---

## 1. Vue d'ensemble

### Qu'est-ce que Graph Memory ?

**Graph Memory** est un serveur MCP (Model Context Protocol) qui offre une **mémoire persistante structurée** à vos agents IA. Au lieu de perdre le contexte entre les sessions, Cline peut :

- **Stocker** des connaissances extraites de vos documents (contrats, docs techniques, specs…)
- **Interroger** un graphe de connaissances en langage naturel
- **Retrouver** des informations précises avec citations des documents sources
- **Naviguer** dans les relations entre concepts (entités, certifications, articles…)

### Comment ça s'intègre avec Cline ?

```
┌─────────────────────────────────────┐
│  VS Code + Extension Cline          │
│  ┌───────────────────────────────┐  │
│  │ Agent IA (Claude, GPT, etc.)  │  │
│  │                               │  │
│  │  "Quelles sont les clauses    │  │
│  │   de résiliation du contrat?" │  │
│  └──────────┬────────────────────┘  │
│             │ appel MCP tool        │
└─────────────┼───────────────────────┘
              │ Streamable HTTP
              ▼
┌─────────────────────────────────────┐
│  Graph Memory (serveur MCP)         │
│  30 outils : ingestion, Q&A,       │
│  recherche, backup, admin…          │
│  Neo4j + Qdrant + S3 + LLM         │
└─────────────────────────────────────┘
```

Cline appelle les **outils MCP** de Graph Memory de manière transparente. L'agent IA choisit automatiquement le bon outil selon votre demande.

---

## 2. Prérequis

### Côté VS Code
- **VS Code** installé (version récente)
- **Extension Cline** installée depuis le marketplace VS Code
- Un modèle IA configuré dans Cline (Claude, GPT, etc.)

### Côté Graph Memory
- **Graph Memory déployé** et accessible :
  - **Local** : `http://localhost:8080` (via Docker Compose)
  - **Distant** : `https://graph-mem.votre-domaine.com` (production)
- Un **token d'accès** (Bearer Token) avec les permissions appropriées

### Vérifier que Graph Memory fonctionne

```bash
# Test de santé
curl http://localhost:8080/health

# Réponse attendue :
# {"status":"healthy","services":{"neo4j":"ok","s3":"ok","llmaas":"ok","qdrant":"ok","embedding":"ok"}}
```

---

## 3. Configuration rapide (5 minutes)

### Étape 1 — Obtenir un token

Si vous avez la clé admin (bootstrap), créez un token via la CLI :

```bash
# Installer les dépendances CLI (optionnel, pour la gestion)
pip install httpx httpx-sse click rich prompt_toolkit

# Créer un token avec droits lecture + écriture
python scripts/mcp_cli.py shell
mcp> token create cline-vscode --permissions read,write --email votre@email.com
# ⚠️ Notez le token affiché — il ne sera plus jamais visible !
```

Ou utilisez directement la clé `ADMIN_BOOTSTRAP_KEY` du fichier `.env` (accès total).

### Étape 2 — Configurer Cline dans VS Code

1. Ouvrez VS Code
2. Ouvrez les paramètres Cline : **Cmd+Shift+P** → `Cline: MCP Servers`
3. Cliquez sur **Edit MCP Settings** (ouvre le fichier `cline_mcp_settings.json`)
4. Ajoutez la configuration Graph Memory :

```json
{
  "mcpServers": {
    "graph-memory": {
      "url": "http://localhost:8080/mcp",
      "headers": {
        "Authorization": "Bearer VOTRE_TOKEN_ICI"
      }
    }
  }
}
```

> **⚠️ Remplacez** `VOTRE_TOKEN_ICI` par votre token réel ou votre `ADMIN_BOOTSTRAP_KEY`.

### Étape 3 — Vérifier la connexion

Dans le chat Cline, tapez :

> Utilise l'outil system_health pour vérifier que Graph Memory fonctionne.

Cline devrait appeler `system_health` et afficher l'état des 5 services (Neo4j, S3, LLMaaS, Qdrant, Embedding).

**C'est prêt !** 🎉 Cline a maintenant accès aux 30 outils Graph Memory.

---

## 4. Configuration détaillée

### 4.1 Fichier de configuration Cline

Le fichier `cline_mcp_settings.json` se trouve typiquement à :
- **macOS** : `~/Library/Application Support/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json`
- **Linux** : `~/.config/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json`
- **Windows** : `%APPDATA%\Code\User\globalStorage\saoudrizwan.claude-dev\settings\cline_mcp_settings.json`

### 4.2 Configuration serveur local (développement)

```json
{
  "mcpServers": {
    "graph-memory": {
      "url": "http://localhost:8080/mcp",
      "headers": {
        "Authorization": "Bearer VOTRE_BOOTSTRAP_KEY"
      }
    }
  }
}
```

### 4.3 Configuration serveur distant (production)

```json
{
  "mcpServers": {
    "graph-memory": {
      "url": "https://graph-mem.votre-domaine.com/mcp",
      "headers": {
        "Authorization": "Bearer VOTRE_TOKEN_PRODUCTION"
      }
    }
  }
}
```

### 4.4 Configuration multi-serveurs

Vous pouvez combiner Graph Memory avec d'autres serveurs MCP :

```json
{
  "mcpServers": {
    "graph-memory": {
      "url": "http://localhost:8080/mcp",
      "headers": {
        "Authorization": "Bearer TOKEN_GRAPH_MEMORY"
      }
    },
    "live-memory": {
      "url": "http://localhost:8081/mcp",
      "headers": {
        "Authorization": "Bearer TOKEN_LIVE_MEMORY"
      }
    }
  }
}
```

### 4.5 Tokens et permissions

| Permission | Accès | Usage typique |
|-----------|-------|---------------|
| `read` | Consultation (search, Q&A, list, stats) | Utilisateur en lecture |
| `read,write` | Consultation + ingestion + suppression | Utilisateur standard |
| `admin` | Tout + gestion tokens | Administrateur |

Créer un token restreint à une mémoire spécifique :
```bash
mcp> token create cline-juridique --permissions read --memories JURIDIQUE
```

---

## 5. Premiers pas avec Cline

### 5.1 Découvrir les capacités

Demandez à Cline :

> Utilise system_about pour me décrire les capacités de Graph Memory.

### 5.2 Créer une mémoire

> Crée une mémoire "PROJETS" avec l'ontologie "general" et la description "Base de connaissances projets".

Cline appellera automatiquement `memory_create`.

### 5.3 Ingérer un document

> Ingère le fichier `/chemin/vers/cahier-des-charges.pdf` dans la mémoire PROJETS.

Cline appellera `memory_ingest` avec le fichier encodé en base64.

### 5.4 Poser une question

> Interroge la mémoire PROJETS : quelles sont les exigences de sécurité du projet ?

Cline appellera `question_answer` et recevra une réponse structurée avec citations.

### 5.5 Explorer le graphe

> Montre-moi les statistiques de la mémoire PROJETS.

> Cherche toutes les entités liées à "Cloud Temple" dans la mémoire PROJETS.

---

## 6. Cas d'usage courants

### 6.1 Analyse de contrats juridiques

```
Toi : Crée une mémoire JURIDIQUE avec l'ontologie legal.
Cline : ✅ Mémoire JURIDIQUE créée avec ontologie legal.

Toi : Ingère le fichier CGA.docx dans JURIDIQUE.
Cline : ✅ Document ingéré — 45 entités, 52 relations extraites.

Toi : Quelles sont les conditions de résiliation dans le contrat ?
Cline : Selon l'Article 15 du CGA [Source: CGA.docx], la résiliation
        peut intervenir dans les cas suivants : ...
```

### 6.2 Base de connaissances technique

```
Toi : Crée une mémoire DOCS avec l'ontologie cloud.
Cline : ✅ Mémoire DOCS créée.

Toi : Ingère tous les fichiers du dossier product_sheets/ dans DOCS.
Cline : ✅ 8 documents ingérés (356 entités, 412 relations).

Toi : Quelles certifications Cloud Temple possède-t-il ?
Cline : Cloud Temple possède les certifications suivantes :
        - SecNumCloud (ANSSI) [Source: iaas-vmware.md]
        - HDS (Hébergement de Données de Santé) [Source: paas.md]
        - ISO 27001 [Source: securite.md]
```

### 6.3 Mémoire de projet persistante

```
Toi : Crée une mémoire SPRINT42 avec l'ontologie general.
Cline : ✅ Mémoire SPRINT42 créée.

Toi : Ingère le compte-rendu de réunion sprint42-cr.md
Cline : ✅ Document ingéré.

[... plusieurs jours plus tard, nouvelle session ...]

Toi : Interroge SPRINT42 : quelles décisions ont été prises lors du dernier sprint ?
Cline : Selon le compte-rendu [Source: sprint42-cr.md], les décisions suivantes...
```

### 6.4 Backup et sécurité

```
Toi : Fais un backup de la mémoire JURIDIQUE.
Cline : ✅ Backup créé : JURIDIQUE/20260308_153000 (45 entités, 23 vecteurs)

Toi : Liste les backups de JURIDIQUE.
Cline : 3 backups trouvés : [tableau avec dates, stats, tailles]
```

---

## 7. Les 30 outils à disposition

Cline a accès à tous ces outils. Il choisit automatiquement le bon outil selon votre demande.

| Catégorie | Outils | Ce que vous pouvez demander |
|-----------|--------|---------------------------|
| **Mémoires** (5) | `memory_create`, `memory_update`, `memory_delete`, `memory_list`, `memory_stats` | "Crée une mémoire", "Renomme JURIDIQUE", "Stats de DOCS" |
| **Documents** (4) | `memory_ingest`, `document_list`, `document_get`, `document_delete` | "Ingère ce fichier", "Liste les documents", "Supprime ce doc" |
| **Recherche/Q&A** (4) | `memory_search`, `memory_get_context`, `question_answer`, `memory_query` | "Cherche X", "Contexte de Y", "Question sur Z" |
| **Graphe** (1) | `memory_graph` | "Montre le graphe complet de JURIDIQUE" |
| **Ontologies** (1) | `ontology_list` | "Quelles ontologies sont disponibles ?" |
| **Stockage** (2) | `storage_check`, `storage_cleanup` | "Vérifie la cohérence", "Nettoie les orphelins" |
| **Backup** (6) | `backup_create`, `backup_list`, `backup_restore`, `backup_download`, `backup_delete`, `backup_restore_archive` | "Sauvegarde JURIDIQUE", "Restaure ce backup" |
| **Admin** (4) | `admin_create_token`, `admin_list_tokens`, `admin_revoke_token`, `admin_update_token` | "Crée un token read-only", "Liste les tokens" |
| **Système** (3) | `system_health`, `system_about`, `system_whoami` | "État de santé ?", "Qui suis-je ?", "Capacités ?" |

### Outils les plus utilisés

- **`question_answer`** — Posez une question en langage naturel, obtenez une réponse avec sources
- **`memory_ingest`** — Ingérez des documents (PDF, DOCX, MD, TXT, HTML, CSV)
- **`memory_search`** — Cherchez des entités dans le graphe
- **`memory_query`** — Obtenez des données structurées (pour chaîner avec d'autres outils)

---

## 8. Bonnes pratiques

### 8.1 Choix de l'ontologie

L'ontologie détermine la qualité de l'extraction. Choisissez-la bien :

| Type de documents | Ontologie recommandée |
|-------------------|----------------------|
| Contrats, CGV, CGVU | `legal` |
| Fiches produits cloud, docs techniques | `cloud` |
| Documents d'infogérance, MCO/MCS | `managed-services` |
| Réponses appels d'offres, RFP/RFI | `presales` |
| FAQ, certifications, RSE, specs générales | `general` |

### 8.2 Nommage des mémoires

- Utilisez des noms **courts et en majuscules** : `JURIDIQUE`, `DOCS`, `PRESALES`
- Un nom par domaine de connaissances (pas une mémoire par document)
- Les mémoires sont isolées (namespace Neo4j) — pas de fuite entre mémoires

### 8.3 Ingestion efficace

- **Un domaine = une mémoire** — Ne mélangez pas des contrats et des fiches techniques dans la même mémoire
- **Force re-ingestion** : si vous modifiez un document, demandez une ré-ingestion avec `force=true`
- **Formats supportés** : PDF, DOCX, MD, TXT, HTML, CSV
- Les gros documents (>25K chars) sont automatiquement découpés en chunks

### 8.4 Questions efficaces

- Soyez **spécifique** : "Quelles sont les pénalités de retard dans le contrat CGA ?" > "Parle-moi du contrat"
- Nommez les **entités** : "Quelles certifications possède Cloud Temple ?" > "Quelles certifications ?"
- Demandez des **comparaisons** : "Compare les SLA de stockage objet et stockage bloc"

### 8.5 Utilisation dans les rules Cline

Vous pouvez ajouter des instructions dans `.clinerules` pour que Cline utilise automatiquement Graph Memory :

```markdown
# .clinerules/graph-memory.md
Quand tu as besoin d'informations sur nos produits cloud, utilise l'outil
question_answer avec memory_id="DOCS" pour interroger notre base de connaissances.

Quand tu analyses un document juridique, ingère-le d'abord dans la mémoire JURIDIQUE
avec l'ontologie legal, puis utilise question_answer pour répondre aux questions.
```

---

## 9. Dépannage

### 9.1 Cline ne voit pas les outils Graph Memory

**Symptôme** : Cline ne propose pas les outils `memory_*`, `question_answer`, etc.

**Solutions** :
1. Vérifiez que le fichier `cline_mcp_settings.json` est correct (JSON valide)
2. Redémarrez VS Code après modification de la config
3. Vérifiez que le serveur est accessible : `curl http://localhost:8080/health`
4. Testez l'endpoint MCP : `curl -v http://localhost:8080/mcp`
5. Vérifiez dans Cline : **Cmd+Shift+P** → `Cline: MCP Servers` → le serveur doit apparaître en vert

### 9.2 Erreur 401 (Unauthorized)

**Symptôme** : "Error: 401 Unauthorized"

**Solutions** :
1. Vérifiez que votre token est correct dans `cline_mcp_settings.json`
2. Le token a-t-il expiré ? Créez-en un nouveau
3. Le token a-t-il les permissions nécessaires (`read` pour consulter, `write` pour ingérer) ?

### 9.3 Erreur de connexion

**Symptôme** : "Connection refused" ou timeout

**Solutions** :
1. Vérifiez que Docker est lancé : `docker compose ps`
2. Vérifiez que le WAF est healthy : `docker compose logs waf --tail 10`
3. Testez l'URL : `curl -v http://localhost:8080/mcp`

### 9.4 L'ingestion échoue

**Symptôme** : Erreur lors de `memory_ingest`

**Solutions** :
1. Vérifiez le format du fichier (PDF, DOCX, MD, TXT, HTML, CSV uniquement)
2. Le fichier est-il trop gros ? Limite par défaut : 50 MB
3. Le LLM est-il accessible ? Vérifiez avec `system_health`
4. Consultez les logs : `docker compose logs mcp-memory --tail 50`

### 9.5 Réponses Q&A imprécises

**Symptôme** : `question_answer` donne des réponses vagues

**Solutions** :
1. Vérifiez l'ontologie : une ontologie inadaptée produit des entités de type "Other"
2. Utilisez `memory_stats` pour voir la distribution des types d'entités
3. Ré-ingérez avec une ontologie plus adaptée (et `force=true`)
4. Soyez plus spécifique dans votre question (nommez les entités)

---

## 10. Architecture technique

### 10.1 Flux d'un appel MCP depuis Cline

```
1. L'utilisateur pose une question dans le chat Cline
2. Le LLM de Cline décide d'utiliser un outil MCP (ex: question_answer)
3. Cline envoie une requête Streamable HTTP à http://localhost:8080/mcp
   avec le header Authorization: Bearer TOKEN
4. Le WAF Coraza valide la requête (rate limiting, OWASP CRS)
5. Le service MCP reçoit l'appel tool
6. AuthMiddleware vérifie le token et les permissions
7. L'outil est exécuté (requête Neo4j + Qdrant + LLM)
8. Le résultat est renvoyé via Streamable HTTP à Cline
9. Le LLM de Cline formule la réponse finale à l'utilisateur
```

### 10.2 Latence typique

| Opération | Latence |
|-----------|---------|
| `system_health` | ~200ms |
| `memory_list` | ~100ms |
| `memory_search` | ~300ms |
| `question_answer` | 3-15s (dépend du LLM) |
| `memory_ingest` (petit doc) | 10-30s |
| `memory_ingest` (gros doc 100 pages) | 2-5 min |

### 10.3 Interface web complémentaire

En plus de Cline, vous pouvez visualiser vos graphes via l'interface web :

**http://localhost:8080/graph**

Cette interface permet de :
- Visualiser le graphe de connaissances interactif
- Filtrer par types d'entités et de relations
- Poser des questions via le panneau ASK
- Explorer les relations entre entités

---

*Guide d'intégration Graph Memory + Cline — v2.1 — Avril 2026*
*Développé par Cloud Temple — https://www.cloud-temple.com*
