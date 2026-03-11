# Active Context

## Contexte actuel (11 mars 2026)

### Focus : Isolation multi-tenant v1.6.0

Audit de sécurité complet du système d'authentification et d'isolation des données. **14 failles corrigées**, recette automatisée de 119 tests, promotion admin déléguée.

### Changements majeurs v1.6.0

**Sécurité (14 failles corrigées)** :
- `memory_list`, `backup_list` → filtrés par `memory_ids` du token
- `memory_create` → auto-ajout au token après création (permet aux clients restreints de créer)
- `memory_delete`, `memory_ingest` → `check_write_permission()` ajouté
- `document_list`, `document_get` → `check_memory_access()` ajouté
- 4 outils `admin_*` → `check_admin_permission()` ajouté (empêche escalade de privilèges)
- `storage_check` (global), `storage_cleanup` → admin requis
- `backup_restore_archive` → vérification memory_id dans le manifest

**Nouvelles fonctions auth** (`auth/context.py`) :
- `check_admin_permission()` — garde pour outils admin
- `get_allowed_memory_ids()` — filtre les résultats par token

**Promotion admin déléguée** :
- `update_token_permissions()` dans `token_manager.py`
- `set_permissions` dans `admin_update_token` → promouvoir/rétrograder des tokens
- Chaîne de confiance : bootstrap → admin délégué → sous-tokens

**Recette complète** (`scripts/test_recette.py`) :
- 119 tests, 7 phases, 7 modules (<120 lignes chacun)
- 3 profils : admin, read/write restreint, read-only
- Teste tous les 28 outils MCP + isolation + déduplication SHA-256

**Scripts nettoyés** :
- 7 scripts obsolètes supprimés (analyze_*.py, test_ontology.py, test_service.py, view_graph.py, ingest_quoteflow.*)
- README scripts mis à jour (fr + en)

### Contexte précédent (v1.5.0)

Ontologie `software-development` v1.2 pour l'ingestion de code source :
- 21 types d'entités + 23 types de relations
- Test QuoteFlow : 965 entités, 910 relations, 99% conformité

### Décisions actives

- **memory_ids vide = accès à toutes les mémoires** : c'est le comportement par défaut pour un token. L'admin doit explicitement restreindre les memory_ids pour isoler un client.
- **Auto-ajout au token lors de memory_create** : un client restreint qui crée une mémoire la voit automatiquement ajoutée à son token. Cela évite de devoir faire un round-trip admin.
- **Localhost exempt d'auth pour MCP** : les requêtes depuis 127.0.0.1 n'ont pas besoin de token (sauf /api/*). Décision de design pour faciliter le développement.

### Prochaines étapes possibles

- Tester en production (déploiement Docker)
- Ajouter des tests d'expiration de tokens
- Considérer le rate-limiting par token (pas seulement par IP)
