# 🔒 Audit de Sécurité — Graph Memory Service v2.0.1

**Date** : 24 mars 2026  
**Scope** : Code source complet (`src/mcp_memory/`), infrastructure Docker, WAF Caddy/Coraza  
**Méthode** : Revue de code statique (SAST manuelle), analyse d'architecture, revue de configuration  

---

## Résumé Exécutif

| Sévérité          | Nombre | Statut                              |
| ----------------- | ------ | ----------------------------------- |
| 🔴 CRITIQUE      | 4      | À corriger immédiatement            |
| 🟠 HAUTE         | 6      | À corriger avant mise en production |
| 🟡 MOYENNE       | 8      | À planifier                         |
| 🔵 FAIBLE / INFO | 5      | Améliorations recommandées          |
| **TOTAL**         | **23** |                                     |

**Score global** : 🟠 **Non prêt pour la production** — 4 vulnérabilités critiques à corriger avant tout déploiement exposé.

---

## 🔴 CRITIQUES (4)

### C1 — Timing Attack sur la clé Bootstrap Admin

**Fichier** : `src/mcp_memory/auth/middleware.py`, ligne 95  
**Code vulnérable** :
```python
if bootstrap_key and token == bootstrap_key:
```

**Risque** : L'opérateur `==` de Python effectue une comparaison caractère par caractère et court-circuite au premier octet différent. Un attaquant peut mesurer les temps de réponse pour deviner la clé bootstrap progressivement (attaque par timing side-channel).

**Impact** : Compromission de la clé admin bootstrap → accès total au service.

**Correction** :
```python
import hmac

if bootstrap_key and hmac.compare_digest(token, bootstrap_key):
```

**Effort** : 2 lignes, 5 minutes.

---

### C2 — Bypass d'authentification localhost dans un contexte Docker

**Fichier** : `src/mcp_memory/auth/middleware.py`, lignes 66–72  
**Code vulnérable** :
```python
client = scope.get("client", ("", 0))
client_ip = client[0] if client else ""
if client_ip in ("127.0.0.1", "::1") and not path.startswith("/api/"):
    await self.app(scope, receive, send)
    return
```

**Risque** : En Docker, le WAF (Caddy) se connecte au service MCP via le réseau Docker interne. Si le conteneur WAF et le conteneur MCP partagent un réseau, les requêtes arrivant depuis Caddy auront l'IP du conteneur Caddy (ex: `172.18.0.2`), **pas** `127.0.0.1`. Cependant :

1. Si un attaquant accède au réseau Docker interne (escape de conteneur, compromission d'un autre service), il peut contourner l'auth en se connectant directement au port 8002 du service MCP.
2. En développement local (sans Docker), tout processus sur la machine a un accès admin complet sans token.
3. L'IP source est extraite de `scope["client"]` qui est fiable côté ASGI, MAIS un reverse proxy qui fait du `X-Forwarded-For` pourrait fausser cette valeur.

**Impact** : Accès admin sans authentification depuis le réseau Docker interne.

**Correction recommandée** :
```python
# Option A : Désactiver le bypass localhost en production
LOCALHOST_BYPASS_ENABLED = os.getenv("LOCALHOST_AUTH_BYPASS", "true").lower() == "true"

if LOCALHOST_BYPASS_ENABLED and client_ip in ("127.0.0.1", "::1") and not path.startswith("/api/"):
    # ...bypass...
```

```env
# En production (.env)
LOCALHOST_AUTH_BYPASS=false
```

**Effort** : 5 lignes, 10 minutes.

---

### C3 — Route `/mcp*` exclue du WAF Coraza

**Fichier** : `waf/Caddyfile`, lignes 53–78  
**Configuration** :
```caddy
@mcp_endpoints {
    path /mcp /mcp/*
}
handle @mcp_endpoints {
    reverse_proxy mcp-memory:8002 {
        # PAS de WAF Coraza ici
    }
}
```

**Risque** : La route `/mcp` (point d'entrée principal du protocole MCP Streamable HTTP) contourne **entièrement** le WAF Coraza. Toutes les protections OWASP CRS (injection SQL, XSS, path traversal, etc.) sont désactivées pour 100% du trafic MCP.

**Justification documentée** : Coraza bufférise les réponses pour inspection, ce qui est incompatible avec le streaming HTTP. C'est un compromis technique conscient.

**Impact** : Les payloads malveillants dans les appels MCP (noms de mémoire, noms de fichiers, contenus de documents) ne sont pas inspectés par le WAF.

**Correction recommandée** :
1. **Compenser côté applicatif** : Ajouter une validation stricte des inputs dans chaque outil MCP (voir H2, M1, M2)
2. **Envisager un WAF en mode non-buffering** si Coraza le supporte dans une future version
3. **Ajouter un rate-limiting spécifique** sur `/mcp` (actuellement 600/min — c'est beaucoup)

**Effort** : Moyen — nécessite des validations dans chaque outil MCP.

---

### C4 — Injection de clés S3 via `memory_id` et `filename` non validés

**Fichier** : `src/mcp_memory/core/storage.py`, méthode `_get_key()`  
**Code vulnérable** :
```python
def _get_key(self, memory_id: str, filename: str) -> str:
    return f"{memory_id}/{filename}"
```

**Risque** : Ni `memory_id` ni `filename` ne sont validés. Un attaquant peut injecter des path traversal :
- `memory_id = "../../admin"` → accès à des préfixes S3 arbitraires
- `filename = "../../_backups/other-memory/data.json"` → lecture/écriture de backups d'autres mémoires
- `filename = "\x00malicious"` → null byte injection

**Impact** : Lecture/écriture/suppression de fichiers S3 arbitraires dans le bucket, y compris les backups et tokens d'autres mémoires.

**Correction** :
```python
import re

SAFE_ID_PATTERN = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$')

def _validate_s3_component(value: str, name: str) -> str:
    """Valide qu'un composant de clé S3 est sûr."""
    if not value or '..' in value or '/' in value or '\x00' in value:
        raise ValueError(f"{name} contient des caractères interdits: {value!r}")
    if not SAFE_ID_PATTERN.match(value):
        raise ValueError(f"{name} invalide: {value!r}")
    return value

def _get_key(self, memory_id: str, filename: str) -> str:
    _validate_s3_component(memory_id, "memory_id")
    # filename peut contenir des extensions mais pas de traversal
    if '..' in filename or filename.startswith('/'):
        raise ValueError(f"Filename invalide: {filename!r}")
    return f"{memory_id}/{filename}"
```

**Effort** : 15 lignes, 30 minutes (+ tests).

---

## 🟠 HAUTES (6)

### H1 — `system_about` expose la configuration interne sans authentification

**Fichier** : `src/mcp_memory/server.py`, outil `system_about`  
**Risque** : Cet outil, accessible sans authentification, expose :
- Modèle LLM utilisé (`gpt-oss:120b`)
- Modèle d'embedding (`bge-m3:567m`, 1024 dimensions)
- Seuils RAG (score_threshold=0.58, chunk_limit=8)
- Tailles de chunks (chunk_size=500, overlap=50)
- Politique de backup (retention_count=5)
- État des services connectés (S3, Neo4j, LLMaaS, Qdrant)
- Liste des mémoires actives avec leurs noms

**Impact** : Reconnaissance facilitée pour un attaquant. La liste des mémoires donne des cibles. Les paramètres RAG/LLM permettent de crafiter des attaques d'injection de prompt optimisées.

**Correction** : Exiger au minimum une permission `read` pour `system_about`, ou ne retourner que l'identité/version sans les détails de configuration.

**Effort** : 10 minutes.

---

### H2 — Absence de validation de `memory_id` dans les outils MCP

**Fichier** : `src/mcp_memory/server.py`, tous les outils MCP  
**Risque** : Le `memory_id` est utilisé directement dans :
- Des labels Neo4j Cypher (injection Cypher potentielle)
- Des clés S3 (path traversal, cf. C4)
- Des noms de collections Qdrant

Aucune validation regex n'est appliquée à l'entrée du `memory_id` dans les outils MCP. La validation existe dans `_validate_backup_id()` pour les backups mais **pas** pour les opérations courantes.

**Impact** : Injection Cypher, path traversal S3, corruption de données Qdrant.

**Correction** : Ajouter une fonction de validation centralisée appelée au début de chaque outil :
```python
VALID_MEMORY_ID = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$')

def validate_memory_id(memory_id: str) -> str:
    if not VALID_MEMORY_ID.match(memory_id):
        raise ValueError(f"memory_id invalide: {memory_id!r}")
    return memory_id
```

**Effort** : 1 fonction + 30 appels (1h).

---

### H3 — Injection Cypher via `memory_id` dans les labels dynamiques

**Fichier** : `src/mcp_memory/core/graph.py`  
**Risque** : Le `memory_id` est utilisé pour construire des labels Neo4j dynamiques via f-strings :
```python
label = f"{namespace}_Entity"
query = f"MATCH (e:{label}) WHERE ..."
```

Si `memory_id` contient des caractères spéciaux Cypher (ex: `}) DETACH DELETE n //`), cela pourrait permettre une injection Cypher.

**Note atténuante** : Le `namespace` est construit via `memory_id.replace("-", "_")`, ce qui limite certains caractères, mais ne bloque pas les backticks, parenthèses, accolades, etc.

**Impact** : Exécution de requêtes Cypher arbitraires → lecture/modification/suppression de données dans Neo4j.

**Correction** : Valider `memory_id` à l'entrée (H2) ET backtick-escaper les labels :
```python
label = f"`{namespace}_Entity`"  # Les backticks protègent les labels Neo4j
```

**Effort** : 30 minutes (systématiser les backticks dans graph.py).

---

### H4 — Pas de HSTS (HTTP Strict Transport Security)

**Fichier** : `waf/Caddyfile`  
**Risque** : Le header `Strict-Transport-Security` n'est PAS défini dans la configuration Caddy. C'est d'ailleurs mentionné comme recommandation dans leur propre document `DESIGN/ANALYSE_RISQUES_SECURITE.md` mais jamais implémenté.

Sans HSTS, un attaquant peut effectuer un downgrade HTTPS→HTTP (attaque SSL stripping) lors de la première connexion d'un client.

**Impact** : Interception des tokens d'authentification en clair.

**Correction** :
```caddy
header {
    Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"
}
```

**Effort** : 1 ligne, 2 minutes.

---

### H5 — Timing Attack sur la comparaison de tokens S3

**Fichier** : `src/mcp_memory/auth/token_manager.py`  
**Risque** : La validation de tokens utilise une comparaison de hash SHA-256 :
```python
token_hash = hashlib.sha256(token.encode()).hexdigest()
# Puis recherche dans le dictionnaire par token_hash
```

La recherche dans un dictionnaire Python par clé est en O(1) et ne permet pas de timing attack sur le hash lui-même. **Cependant**, si le hash est comparé avec `==` quelque part, c'est vulnérable.

**Vérification** : Le `TokenManager` charge tous les tokens en mémoire et utilise `dict.get(token_hash)` — ce qui est sûr car c'est un lookup de hash table, pas une comparaison séquentielle. **Cette vulnérabilité est atténuée** mais la comparaison de la bootstrap key (C1) reste critique.

**Reclassification** : Descendre en MOYENNE si confirmé que seul `dict.get()` est utilisé.

---

### H6 — Pas de limite de taille sur le contenu base64 d'ingestion

**Fichier** : `src/mcp_memory/server.py`, outil `memory_ingest`  
**Risque** : Le paramètre `content_base64` est un string de taille arbitraire. Un attaquant peut envoyer un fichier de plusieurs Go encodé en base64, causant :
1. Consommation mémoire (le décodage base64 alloue ~75% de la taille)
2. Saturation du stockage S3
3. Timeout LLM sur l'extraction

**Note atténuante** : `EXTRACTION_MAX_TEXT_LENGTH = 950000` limite le texte extrait, mais PAS la taille du fichier lui-même (un PDF de 500MB avec peu de texte passerait).

**Impact** : Déni de service (DoS) par épuisement mémoire.

**Correction** :
```python
MAX_INGEST_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB

content = base64.b64decode(content_base64)
if len(content) > MAX_INGEST_SIZE_BYTES:
    raise ValueError(f"Document trop volumineux: {len(content)} bytes (max {MAX_INGEST_SIZE_BYTES})")
```

**Effort** : 5 lignes, 10 minutes.

---

## 🟡 MOYENNES (8)

### M1 — Pas de validation de `filename` à l'ingestion

**Fichier** : `src/mcp_memory/server.py`, outil `memory_ingest`  
**Risque** : Le paramètre `filename` est utilisé directement comme clé S3 et dans les métadonnées Neo4j sans aucune sanitisation. Un `filename` contenant `../../`, `\x00`, ou des caractères Unicode malveillants peut causer des problèmes.

**Correction** : Sanitiser le filename à l'entrée :
```python
filename = os.path.basename(filename)  # Retire tout chemin
if not filename or len(filename) > 255:
    raise ValueError("Nom de fichier invalide")
```

---

### M2 — Pas de validation de `entity_name` dans `memory_get_context`

**Fichier** : `src/mcp_memory/server.py`  
**Risque** : Le `entity_name` est passé directement dans des requêtes Cypher. Si des caractères Cypher spéciaux sont inclus, cela pourrait causer des erreurs ou des injections.

**Note atténuante** : Neo4j utilise des paramètres préparés pour les valeurs (`$name`), mais les labels dynamiques (construits à partir de `memory_id`) restent vulnérables.

**Correction** : Vérifier que les requêtes Cypher utilisent bien des paramètres `$param` pour toutes les valeurs utilisateur.

---

### M3 — Headers de sécurité manquants dans la réponse MCP

**Fichier** : `waf/Caddyfile`  
**Risque** : Les headers de sécurité (CSP, X-Frame-Options, etc.) sont définis dans Caddy, mais la route `/mcp*` ne passe PAS par le handler qui les ajoute. Les réponses MCP n'ont donc aucun header de sécurité.

**Correction** : Déplacer les headers de sécurité dans un bloc global qui s'applique à toutes les routes, y compris `/mcp*`.

---

### M4 — Neo4j sans chiffrement (bolt:// au lieu de bolt+s://)

**Fichier** : `docker-compose.yml`  
**Risque** : La connexion Neo4j utilise `bolt://neo4j:7687` (non chiffré). Les requêtes Cypher contenant des données sensibles (entités, relations) transitent en clair sur le réseau Docker.

**Note atténuante** : Le réseau Docker est interne, mais dans un environnement partagé, un autre conteneur pourrait sniffer le trafic.

**Correction** : Configurer Neo4j avec TLS (`bolt+s://`) en production.

---

### M5 — Qdrant sans authentification

**Fichier** : `docker-compose.yml`  
**Risque** : Qdrant est déployé sans aucune authentification (`QDRANT__SERVICE__API_KEY` non configuré). Tout conteneur sur le réseau Docker interne peut lire/écrire/supprimer des vecteurs.

**Correction** :
```yaml
qdrant:
  environment:
    - QDRANT__SERVICE__API_KEY=${QDRANT_API_KEY}
```

---

### M6 — ~~Pas de `Content-Security-Policy` pour le client web~~ ✅ CORRIGÉ

**Fichier** : `waf/Caddyfile`, `src/mcp_memory/static/`  
**Risque initial** : Le CSP contenait `'unsafe-inline'` pour `script-src` et `style-src`, annulant la protection XSS du CSP.

**Correction appliquée (v2.1.0)** :
- Suppression de `'unsafe-inline'` dans `script-src` (le vrai risque XSS)
- `style-src` conserve `'unsafe-inline'` car vis-network (lib tierce) utilise `setAttribute('style',...)` pour le rendu du graphe — non modifiable
- CSP finale : `script-src 'self' https://unpkg.com https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline'`
- **Refactoring du client web** (8 fichiers) :
  - `graph.html` : 12 handlers `onclick`/`onchange` → `data-action` attributes
  - `graph.html` : 5 attributs `style=""` → classes CSS
  - `sidebar.js` : event delegation sur conteneurs parents + `applyDynamicColors()` pour couleurs via API DOM
  - `ask.js` : event delegation sur `#askBody` pour boutons/tags dynamiques
  - `graph.js` : event delegation sur `#detailContent` + post-render couleurs
  - `app.js` : `setupSidebarEvents()` au démarrage + `classList.toggle('hidden')`
  - `graph.css` : 16 nouvelles classes utilitaires CSP-safe
- **Technique** : les couleurs dynamiques (type d'entité) utilisent `element.style.xxx = value` (API DOM, autorisé par CSP) au lieu de `style=""` (attribut HTML, bloqué par CSP)

---

### M7 — Logs de debug exposent des tokens en développement

**Fichier** : `src/mcp_memory/auth/middleware.py`  
**Risque** : En mode debug (`MCP_SERVER_DEBUG=true`), le `LoggingMiddleware` logge les headers complets des requêtes, y compris le header `Authorization` contenant le token Bearer.

**Correction** : Masquer le header Authorization dans les logs :
```python
if key == "authorization":
    value = f"Bearer {'*' * 8}...{value[-4:]}" if len(value) > 12 else "***"
```

---

### M8 — Pas de rotation automatique de la clé bootstrap

**Configuration** : `.env.example`  
**Risque** : La clé bootstrap admin (`ADMIN_BOOTSTRAP_KEY`) est une valeur statique dans le fichier `.env`. Il n'y a pas de mécanisme de rotation, et la valeur par défaut dans l'exemple est `admin_bootstrap_key_change_me`.

**Correction** : 
1. Documenter l'obligation de changer la clé bootstrap au déploiement
2. Ajouter un check au démarrage qui refuse de démarrer si la clé contient "change_me"
3. Envisager un mécanisme de rotation (re-hash au premier usage)

---

## 🔵 FAIBLES / INFORMATIVES (5)

### I1 — ReDoS potentiel dans le chunker

**Fichier** : `src/mcp_memory/core/chunker.py`  
**Risque** : Les regex compilées (`ARTICLE_PATTERN`, `UPPERCASE_TITLE_PATTERN`) sont appliquées sur des textes potentiellement très longs. Certains patterns avec `{15,}` pourraient être lents sur des inputs crafités.

**Impact** : Lent mais pas exploitable en pratique (pas de backtracking catastrophique identifié).

---

### I2 — Version de Python non épinglée dans le Dockerfile

**Fichier** : `Dockerfile`  
```dockerfile
FROM python:3.11-slim
```
**Risque** : Utiliser `3.11-slim` sans épingler le patch (ex: `3.11.8-slim`) peut introduire des régressions lors de rebuilds.

---

### I3 — Pas de scan de vulnérabilités des dépendances

**Fichier** : `requirements.txt`  
**Risque** : Les dépendances Python ne sont pas scannées par un outil comme `pip-audit`, `safety` ou Dependabot. Des CVE connues dans les dépendances pourraient être présentes.

**Correction** : Ajouter `pip-audit` en CI/CD ou activer Dependabot sur le repo GitHub.

---

### I4 — Le WAF Coraza body limit est très élevé (75 MB)

**Fichier** : `waf/Caddyfile`  
```
SecRequestBodyLimit 78643200
```
**Risque** : 75 MB est élevé pour un WAF. Des requêtes volumineuses peuvent ralentir l'inspection.

**Note** : Justifié par l'ingestion de gros documents (PDF).

---

### I5 — Commentaire "SSE" résiduel dans le code

**Fichier** : `src/mcp_memory/auth/middleware.py`, ligne 66  
```python
# Requêtes internes (localhost) : pas d'auth pour MCP/SSE
```
**Risque** : Le commentaire mentionne "SSE" alors que le projet utilise Streamable HTTP. C'est cosmétique mais source de confusion.

**Correction** : Mettre à jour le commentaire → "MCP Streamable HTTP".

---

## 📋 Matrice de Priorisation

| ID  | Sévérité     | Effort | Priorité | Description                                           |
| --- | ------------ | ------ | -------- | ----------------------------------------------------- |
| C1  | 🔴 CRITIQUE | 5 min  | P0       | Timing attack bootstrap key → `hmac.compare_digest`   |
| C2  | 🔴 CRITIQUE | 10 min | P0       | Localhost bypass configurable en production           |
| C4  | 🔴 CRITIQUE | 30 min | P0       | Validation S3 key components                          |
| H2  | 🟠 HAUTE    | 1h     | P0       | Validation centralisée memory_id                      |
| H3  | 🟠 HAUTE    | 30 min | P0       | Backtick-escape labels Cypher                         |
| C3  | 🔴 CRITIQUE | 2h     | P1       | Validation input compensant l'absence de WAF sur /mcp |
| H1  | 🟠 HAUTE    | 10 min | P1       | Restreindre system_about                              |
| H4  | 🟠 HAUTE    | 2 min  | P1       | Ajouter HSTS                                          |
| H6  | 🟠 HAUTE    | 10 min | P1       | Limite taille ingestion                               |
| M1  | 🟡 MOYENNE  | 15 min | P2       | Sanitisation filename                                 |
| M5  | 🟡 MOYENNE  | 10 min | P2       | Auth Qdrant                                           |
| M7  | 🟡 MOYENNE  | 10 min | P2       | Masquer tokens dans logs debug                        |
| M8  | 🟡 MOYENNE  | 20 min | P2       | Check bootstrap key au démarrage                      |
| M2  | 🟡 MOYENNE  | 20 min | P3       | Validation entity_name                                |
| M3  | 🟡 MOYENNE  | 15 min | P3       | Headers sécurité sur /mcp                             |
| M4  | 🟡 MOYENNE  | 30 min | P3       | TLS Neo4j                                             |
| M6  | ✅ CORRIGÉ   | 1h     | —        | CSP strict (unsafe-inline supprimé)                   |

**Temps estimé total** : ~7h pour P0+P1, ~2h supplémentaires pour P2.

---

## 🛡️ Recommandations Architecturales

### 1. Validation d'entrée centralisée (Defense in Depth)

Créer un module `src/mcp_memory/core/validators.py` avec des fonctions de validation réutilisables :
- `validate_memory_id(value)` — regex `^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$`
- `validate_filename(value)` — `os.path.basename()` + longueur + caractères autorisés
- `validate_entity_name(value)` — longueur max + pas de caractères Cypher spéciaux
- `validate_backup_id(value)` — déjà existant, à factoriser

### 2. Durcissement de la configuration de production

Créer un `.env.production.example` avec les paramètres de sécurité recommandés :
```env
LOCALHOST_AUTH_BYPASS=false
MCP_SERVER_DEBUG=false
ADMIN_BOOTSTRAP_KEY=<générer avec openssl rand -hex 32>
QDRANT_API_KEY=<générer avec openssl rand -hex 32>
```

### 3. Pipeline de sécurité CI/CD

- `pip-audit` pour les CVE dans les dépendances
- `bandit` pour l'analyse statique Python
- `trivy` pour le scan d'images Docker
- Tests de recette incluant des cas de path traversal, injection, et fuzzing des inputs

---

## ✅ Points Forts Identifiés

Le projet présente déjà de bonnes pratiques de sécurité :

1. **Isolation multi-tenant** : Labels Neo4j par namespace, contrôles d'accès sur 28+ outils
2. **Recette de tests de sécurité** : 136 tests couvrant 3 profils (admin, rw, ro)
3. **WAF Coraza avec OWASP CRS** sur les endpoints `/api/*`
4. **Rate limiting** par IP sur 3 zones
5. **Validation backup_id** avec regex stricte (anti path-traversal)
6. **Conteneur non-root** : `USER mcp` dans le Dockerfile
7. **Réseau Docker isolé** : Neo4j et Qdrant non exposés
8. **Déduplication SHA-256** des documents
9. **Headers de sécurité** : CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy
10. **Limite d'archive** : 100 MB max pour les restore d'archives backup
