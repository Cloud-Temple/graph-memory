# Active Context

## Focus actuel (mis à jour 2026-04-03)

### Migration SSE → Streamable HTTP (issue #1) — EN COURS SUR BRANCHE DEV

**Branche** : `dev/streamable-http` (4 commits, en attente de commit final + merge)

**Contexte** : L'issue GitHub #1 demande la migration du transport SSE (déprécié dans la spec MCP 2025-03-26) vers Streamable HTTP. Migration propre sans rétrocompatibilité.

**Changements effectués** :

| Composant | Avant | Après |
|-----------|-------|-------|
| **server.py** | `mcp.sse_app()` → endpoints `/sse` + `/messages` | `mcp.streamable_http_app()` → endpoint unique `/mcp` |
| **client.py** | `from mcp.client.sse import sse_client` | `from mcp.client.streamable_http import streamablehttp_client` |
| **middleware.py** | `HostNormalizerMiddleware` (workaround Host header) | Supprimé (plus nécessaire) |
| **requirements.txt** | `mcp>=1.0.0` | `mcp>=1.8.0` |
| **waf/Caddyfile** | Routes `/sse*` + `/messages/*` séparées | Route unique `/mcp*` |
| **Rate limiting** | SSE 10/min + messages 60/min + global 200/min | MCP 200/min + global 500/min |
| **Dockerfile** | Healthcheck `/sse`, VERSION non copié | Healthcheck `/health`, `COPY VERSION .` |
| **middleware health** | Version hardcodée `"1.1.0"` | Lecture dynamique fichier `VERSION` |

**Tests de qualification** : `scripts/test_streamable_http.py` — **27/27 PASS en 10.4s**

**Fichiers modifiés** (branche dev vs main) :
- `src/mcp_memory/server.py` — streamable_http_app()
- `scripts/cli/client.py` — streamablehttp_client
- `src/mcp_memory/auth/middleware.py` — suppression HostNormalizerMiddleware + fix version
- `requirements.txt` — mcp>=1.8.0
- `waf/Caddyfile` — route /mcp + rate limits ajustés
- `Dockerfile` — COPY VERSION + healthcheck /health
- `README.md` — SSE → Streamable HTTP partout
- `README.en.md` — nouvelle version anglaise
- `scripts/README.md` — SSE → Streamable HTTP
- `scripts/test_streamable_http.py` — script de test complet
- `starter-kit/boilerplate/` — tous les fichiers alignés

**Documentation mise à jour (2026-04-03)** :
- CHANGELOG.md : entrée v1.4.0 complète (migration SSE → Streamable HTTP)
- README.md : section Changelog mise à jour (v1.4.0 + v1.3.7), footer v1.4.0
- docker-compose.yml : healthcheck corrigé `/sse` → `/health` (causait des 404 en boucle)
- README.en.md : restauré (traduction fidèle à faire manuellement par Christophe)

**Prochaines étapes** :
- [ ] Traduire README.en.md + créer CHANGELOG.en.md (Christophe s'en occupe)
- [ ] Commit final de la documentation + healthcheck fix
- [ ] Merge sur main + bump VERSION → 1.4.0
- [ ] Redéployer en production
- [ ] Coordonner la migration Live Memory (même pattern)

---

### Découvertes pendant la migration

1. **Rate limiting Streamable HTTP** : Chaque appel d'outil MCP = 3 requêtes HTTP (POST init + POST call + DELETE close). L'ancien rate limiting SSE (60/min) était trop bas → augmenté à 200/min pour /mcp.

2. **`HostNormalizerMiddleware` obsolète** : Ce middleware normalisait le Host header pour contourner la validation DNS rebinding du SDK MCP v1.26+. Streamable HTTP n'a plus cette validation → middleware supprimé.

3. **Notifications de progression** : Le mécanisme `ctx.info()` → `_received_notification` fonctionne toujours en Streamable HTTP (19 notifications reçues pendant l'ingestion test).

4. **Version /health** : La version était hardcodée "1.1.0" dans le middleware. Corrigé pour lire le fichier VERSION. Le fichier n'était pas dans l'image Docker → ajouté `COPY VERSION .` dans le Dockerfile.

5. **Healthcheck Docker** : Pointait vers `/sse` (qui n'existe plus) → changé en `/health`.

---

## Historique récent

### Intégration Live Memory — Architecture mémoire à deux niveaux (2026-02-21)
(Voir memory bank précédente — toujours valide)

### Ontologie general.yaml v1.1 — Réduction "Other" (2026-02-19)
(Voir memory bank précédente — toujours valide)
