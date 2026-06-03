# -*- coding: utf-8 -*-
"""Tests système : system_health, system_about, ontology_list et admin UI."""

import base64
import re
from pathlib import Path

from . import MCPClient, assert_ok, assert_error, assert_field, ok, fail, phase_header


TEMP_ONTOLOGY = "zz-recette-ontology"


def _ontology_yaml(name: str, version: str, description: str) -> str:
    """Construit une ontologie minimale mais chargeable par OntologyManager."""
    return f"""name: {name}
version: "{version}"
description: "{description}"
context: "Ontologie temporaire utilisée par la recette automatisée."
entity_types:
  - name: TestEntity
    description: "Entité de validation recette"
    examples:
      - "Cloud Temple"
relation_types:
  - name: TEST_RELATION
    description: "Relation de validation recette"
    examples:
      - "Cloud Temple TEST_RELATION Graph Memory"
extraction_rules:
  max_entities: 5
  max_relations: 5
"""


def _admin_app_source() -> str:
    repo_root = Path(__file__).resolve().parents[2]
    return (repo_root / "src/mcp_memory/static/js/admin-app.js").read_text(encoding="utf-8")


def _admin_css_source() -> str:
    repo_root = Path(__file__).resolve().parents[2]
    return (repo_root / "src/mcp_memory/static/css/admin.css").read_text(encoding="utf-8")


def _server_source() -> str:
    repo_root = Path(__file__).resolve().parents[2]
    return (repo_root / "src/mcp_memory/server.py").read_text(encoding="utf-8")


def _admin_html_source() -> str:
    repo_root = Path(__file__).resolve().parents[2]
    return (repo_root / "src/mcp_memory/static/admin.html").read_text(encoding="utf-8")


def _middleware_source() -> str:
    repo_root = Path(__file__).resolve().parents[2]
    return (repo_root / "src/mcp_memory/auth/middleware.py").read_text(encoding="utf-8")


def _cli_commands_source() -> str:
    repo_root = Path(__file__).resolve().parents[2]
    return (repo_root / "scripts/cli/commands.py").read_text(encoding="utf-8")


def _cli_shell_source() -> str:
    repo_root = Path(__file__).resolve().parents[2]
    return (repo_root / "scripts/cli/shell.py").read_text(encoding="utf-8")


def _assert_admin_ui_actions_are_wired() -> None:
    """Vérifie que chaque bouton data-action dispose d'un handler explicite."""
    source = _admin_app_source()
    actions = set(re.findall(r"data-action=[\"']([^\"']+)[\"']", source))
    handlers = set(re.findall(r"action === ['\"]([^'\"]+)['\"]", source))
    missing = sorted(actions - handlers)
    if missing:
        fail("admin UI — toutes les actions cliquables sont câblées", f"Handlers manquants: {missing}")
    else:
        ok("admin UI — toutes les actions cliquables sont câblées", f"{len(actions)} actions")


def _assert_ingest_jobs_admin_page() -> None:
    """Vérifie la page Ingest Jobs (/admin) : module, renderer, polling, outils async."""
    source = _admin_app_source()
    checks = {
        "module jobs (⚡)": "jobs: { icon: '⚡'" in source,
        "renderer câblé": "jobs: renderIngestJobs" in source,
        "fonction renderIngestJobs": "async function renderIngestJobs(" in source,
        "listing via ingest_job_list": "ingest_job_list" in source,
        "annulation ingest_job_cancel": "ingest_job_cancel" in source,
        "détail ingest_job_status": "ingest_job_status" in source,
        "soumission async memory_ingest_async": "memory_ingest_async" in source,
        "sha256 navigateur": "crypto.subtle.digest('SHA-256'" in source,
        "auto-refresh polling": "jobsPollTimer" in source and "stopJobsPolling()" in source,
    }
    missing = [name for name, passed in checks.items() if not passed]
    if missing:
        fail("admin UI — page Ingest Jobs", f"Contrôles KO: {missing}")
    else:
        ok("admin UI — page Ingest Jobs", f"{len(checks)} contrôles")


def _assert_admin_ui_no_raw_tool() -> None:
    """Vérifie que le module Raw Tool a réellement disparu de l'interface."""
    source = _admin_app_source()
    forbidden = ["Raw Tool", "raw-tool", "renderRawTool", "rawToolCall"]
    found = [term for term in forbidden if term in source]
    if found:
        fail("admin UI — module Raw Tool supprimé", f"Termes encore présents: {found}")
    else:
        ok("admin UI — module Raw Tool supprimé")


def _assert_admin_ui_modules_have_emoji() -> None:
    """Vérifie les modules principaux et leur emoji, façon live-memory."""
    source = _admin_app_source()
    expected = {
        "dashboard": "📊",
        "ontologies": "🧬",
        "memories": "🧠",
        "documents": "📄",
        "search": "🔎",
        "tokens": "🔑",
        "backups": "💾",
        "storage": "🧹",
    }
    missing = [
        f"{module}:{emoji}"
        for module, emoji in expected.items()
        if f"{module}: {{ icon: '{emoji}'" not in source
    ]
    if missing:
        fail("admin UI — modules avec emoji", f"Manquants: {missing}")
    elif "tools:" in source:
        fail("admin UI — modules avec emoji", "Le module tools/raw est encore déclaré")
    else:
        ok("admin UI — modules avec emoji", f"{len(expected)} modules")


def _assert_backup_all_memories_supported() -> None:
    """Vérifie que Create Backup accepte vraiment le choix all memories."""
    admin_source = _admin_app_source()
    server_source = _server_source()
    match = re.search(r"async def backup_create\(.+?\n@mcp\.tool\(\)\nasync def backup_list", server_source, re.S)
    backup_create_source = match.group(0) if match else ""
    ui_checks = {
        "modal avec option all memories": "memorySelect('bk_memory', true)" in admin_source,
        "pas de blocage choose a memory": "Choose a memory first." not in admin_source,
        "appel backup_create avec args dynamiques": "callTool('backup_create', args)" in admin_source,
    }
    server_checks = {
        "fonction backup_create trouvée": bool(backup_create_source),
        "memory_id optionnel": "memory_id: Annotated[Optional[str]" in backup_create_source,
        "mode all_memories": '"mode": "all_memories"' in backup_create_source,
        "global admin-only": "admin_err = check_admin_permission()" in backup_create_source,
    }
    missing = [name for name, passed in {**ui_checks, **server_checks}.items() if not passed]
    if missing:
        fail("backup all memories — UI et backend cohérents", f"Contrôles KO: {missing}")
    else:
        ok("backup all memories — UI et backend cohérents")


def _assert_json_results_use_modal_tabs() -> None:
    """Vérifie que les résultats JSON ne sont plus injectés en gros bloc inline."""
    admin_source = _admin_app_source()
    css_source = _admin_css_source()
    required = {
        "helper showResultModal": "function showResultModal" in admin_source,
        "onglet JSON": "label: 'JSON'" in admin_source,
        "onglets cliquables": "data-action=\"result-tab\"" in admin_source,
        "réouverture résultat": "data-action=\"view-result\"" in admin_source,
        "résumé compact": "function resultSummaryHtml" in admin_source,
        "memory_stats via modale riche": "if (action === 'memory-stats') return runAndShow('memory_stats'" in admin_source and "showResultModal(tool, result)" in admin_source,
        "style tabs": ".modal-tabs" in css_source and ".tab-button" in css_source and ".tab-panel" in css_source,
        "style carte compacte": ".result-card.compact" in css_source,
    }
    forbidden = [
        "function jsonBlock",
        'resultEl.innerHTML = `<div class="result-card"><pre class="json-pretty"',
        'showModal(tool, `<pre class="pretty-code">${esc(JSON.stringify',
        'else showModal(data.tool, `<pre class="pretty-code">${esc(JSON.stringify',
    ]
    missing = [name for name, passed in required.items() if not passed]
    found = [pattern for pattern in forbidden if pattern in admin_source]
    if missing or found:
        detail = []
        if missing:
            detail.append(f"Manquants: {missing}")
        if found:
            detail.append(f"Patterns interdits: {found}")
        fail("admin UI — JSON affiché en modale à onglets", " ; ".join(detail))
    else:
        ok("admin UI — JSON affiché en modale à onglets")


def _assert_admin_assets_are_cache_busted() -> None:
    """Vérifie que le navigateur ne garde pas un ancien admin-app.js."""
    html = _admin_html_source()
    middleware = _middleware_source()
    checks = {
        "CSS versionné": "/static/css/admin.css?v=" in html,
        "API JS versionné": "/static/js/admin-api.js?v=" in html,
        "APP JS versionné": "/static/js/admin-app.js?v=" in html,
        "no-store": "no-store, no-cache, must-revalidate" in middleware,
        "pragma no-cache": "(b\"pragma\", b\"no-cache\")" in middleware,
        "expires 0": "(b\"expires\", b\"0\")" in middleware,
    }
    missing = [name for name, passed in checks.items() if not passed]
    if missing:
        fail("admin UI — assets cache-busted", f"Contrôles KO: {missing}")
    else:
        ok("admin UI — assets cache-busted")


def _assert_result_modals_are_rich() -> None:
    """Vérifie que les résultats JSON/YAML passent par une grande modale à onglets."""
    js = _admin_app_source()
    css = _admin_css_source()
    checks = {
        "helper showResultModal": "function showResultModal" in js,
        "tabs summary/json": "resultTabsHtml" in js and "label: 'JSON'" in js and "label: 'Summary'" in js,
        "inline ouvre une modale": "showResultModal(title, result, options)" in js,
        "pas de JSON inline legacy": "resultEl.innerHTML = `<div class=\"result-card\"><pre" not in js,
        "vue ontologie YAML": "yaml: result.content || ''" in js and "initialTab: 'yaml'" in js,
        "édition ontologie preview": "ontologyEditPreview" in js and "highlightYaml(editor.value)" in js,
        "modale très large": ".modal-card.wide" in css and "1540px" in css and "98vw" in css,
        "YAML coloré": ".yaml-key" in css and ".yaml-comment" in css and ".yaml-value" in css,
        "JSON coloré": "function highlightJson" in js and ".json-key" in css and ".json-string" in css,
        "éditeur haut": ".ontology-editor" in css and "68vh" in css,
    }
    missing = [name for name, passed in checks.items() if not passed]
    if missing:
        fail("admin UI — JSON/YAML en modales riches", f"Contrôles KO: {missing}")
    else:
        ok("admin UI — JSON/YAML en modales riches")


def _assert_dashboard_stats_are_present() -> None:
    """Vérifie que le dashboard affiche des statistiques Graph Memory utiles."""
    js = _admin_app_source()
    css = _admin_css_source()
    checks = {
        "cartes stats": "function dashboardStat" in js and "dash-cards" in js,
        "system_about utilisé": "callTool('system_about'" in js and "cache.about" in js,
        "totaux graph": "function graphTotals" in js and "totals.documents" in js and "totals.entities" in js and "totals.relations" in js,
        "panneau knowledge graph": "Knowledge Graph" in js and "function graphStatsHtml" in js,
        "stats backups": "backup_list" in js and "latestBackup" in js,
        "stats tokens": "admin_list_tokens" in js and "tokenCount" in js,
        "capacités": "function capabilityHtml" in js and "MCP tools" in js,
        "services": "serviceStatusValue" in js and "serviceOk" in js,
        "usage ontologies": "function ontologyUsageHtml" in js and "usage-bar" in js,
        "profil courant": "Current Access" in js and "memoryScope" in js,
        "styles dashboard": ".dashboard-grid" in css and ".dashboard-panel" in css and ".usage-bar" in css,
        "styles métriques": ".metric-grid" in css and ".metric-tile" in css and ".dashboard-panel.wide" in css,
    }
    missing = [name for name, passed in checks.items() if not passed]
    if missing:
        fail("admin UI — dashboard statistiques Graph Memory", f"Contrôles KO: {missing}")
    else:
        ok("admin UI — dashboard statistiques Graph Memory")


def _assert_storage_check_layout_is_aligned() -> None:
    """Vérifie que le bouton Check du storage reste aligné avec son sélecteur."""
    js = _admin_app_source()
    css = _admin_css_source()
    checks = {
        "classe storage dédiée": "storage-check-actions" in js,
        "layout horizontal sans wrap": ".maint-actions.storage-check-actions" in css and "flex-wrap: nowrap" in css,
        "select borné": ".storage-check-actions .form-input" in css and "max-width: 620px" in css,
        "bouton hauteur fixe": ".storage-check-actions .btn-action" in css and "height: 38px" in css,
        "fallback mobile": ".maint-actions.storage-check-actions { flex-wrap: wrap; justify-content: flex-start; width: 100%; }" in css,
    }
    missing = [name for name, passed in checks.items() if not passed]
    if missing:
        fail("admin UI — bouton Storage Check aligné", f"Contrôles KO: {missing}")
    else:
        ok("admin UI — bouton Storage Check aligné")


def _assert_token_modals_are_usable() -> None:
    """Vérifie que les modales token utilisent des contrôles explicites, pas des CSV bruts."""
    js = _admin_app_source()
    css = _admin_css_source()
    checks = {
        "permissions en checkboxes": "function permissionPicker" in js and "ut_permissions" in js,
        "mémoires en grille": "function memoryCheckboxGrid" in js and "ut_memories" in js,
        "mode mémoire explicite": "ut_memory_mode" in js and "Keep current access" in js and "Selected memories" in js,
        "résumé token": "token-summary" in js and ".token-summary" in css,
        "modale dédiée": "token-modal" in js and ".modal-card.token-modal" in css,
        "résultat update modale": "showInlineResult('tokensResult', result, 'Update Token')" in js,
        "pas de CSV legacy": "ut_add" not in js and "ut_remove" not in js and "ut_set" not in js and "replace memory list" not in js,
        "styles choix": ".choice-pill" in css and ".choice-row" in css and ".memory-choice-grid" in css,
    }
    missing = [name for name, passed in checks.items() if not passed]
    if missing:
        fail("admin UI — modales token utilisables", f"Contrôles KO: {missing}")
    else:
        ok("admin UI — modales token utilisables")


def _assert_cli_and_admin_stay_in_sync() -> None:
    """Vérifie que les fonctionnalités CLI critiques existent aussi dans /admin, et inversement."""
    admin_js = _admin_app_source()
    cli_py = _cli_commands_source()
    shell_py = _cli_shell_source()
    server_py = _server_source()

    checks = {
        "serveur ontologies CRUD": all(
            f"async def {tool}(" in server_py
            for tool in ["ontology_get", "ontology_export", "ontology_import", "ontology_update", "ontology_delete"]
        ),
        "admin ontologies CRUD": all(
            f"callTool('{tool}'" in admin_js
            for tool in ["ontology_get", "ontology_export", "ontology_import", "ontology_update", "ontology_delete"]
        ),
        "click ontologies CRUD": all(
            f'"{tool}"' in cli_py
            for tool in ["ontology_get", "ontology_export", "ontology_import", "ontology_update", "ontology_delete"]
        ) and "@cli.group()\ndef ontology" in cli_py,
        "shell ontologies CRUD": all(
            cmd in shell_py
            for cmd in ["ontology-get", "ontology-export", "ontology-import", "ontology-update", "ontology-delete"]
        ) and all(
            f'"{tool}"' in shell_py
            for tool in ["ontology_get", "ontology_export", "ontology_import", "ontology_update", "ontology_delete"]
        ),
        "document_get admin et CLI": (
            "callTool('document_get'" in admin_js
            and '"document_get"' in cli_py
            and '"document_get"' in shell_py
            and "docget" in shell_py
        ),
        "backup all memories Click": (
            "@click.argument(\"memory_id\", required=False, default=None)" in cli_py
            and "params = {}" in cli_py
            and "if memory_id:" in cli_py
            and '"memory_id"' in cli_py
        ),
        "backup all memories shell": (
            "target = mem or \"toutes les mémoires\"" in shell_py
            and "params = {}" in shell_py
            and 'params["memory_id"] = mem' in shell_py
        ),
        "backup restore archive admin": (
            "restore-backup-archive" in admin_js
            and "function showRestoreBackupArchive" in admin_js
            and "callTool('backup_restore_archive'" in admin_js
            and "fileToBase64" in admin_js
        ),
        "backup restore archive CLI": (
            '"backup_restore_archive"' in cli_py
            and '"backup_restore_archive"' in shell_py
            and "backup-restore-file" in shell_py
        ),
    }
    missing = [name for name, passed in checks.items() if not passed]
    if missing:
        fail("CLI / MCP / admin — fonctionnalités synchronisées", f"Contrôles KO: {missing}")
    else:
        ok("CLI / MCP / admin — fonctionnalités synchronisées", f"{len(checks)} contrôles")


async def run(admin: MCPClient, client_rw: MCPClient, client_ro: MCPClient, **ctx):
    """Phase Système — Vérifie les outils publics accessibles à tous."""
    phase_header(1, "Système (health, about, ontology)", "🌐")

    # 1.1 — system_health (admin)
    print("\n  📋 1.1 — system_health (admin)")
    result = await admin.call_tool("system_health", {})
    status = result.get("status", "")
    if status in ("ok", "error"):  # error OK si services pas tous up
        ok("system_health (admin)")
        services = result.get("services", {})
        for svc, info in services.items():
            s = info.get("status", "?") if isinstance(info, dict) else info
            ok(f"  → {svc}: {s}")
    else:
        fail("system_health", f"status={status}")

    # 1.2 — system_health depuis un client non-admin (public)
    print("\n  📋 1.2 — system_health (client_rw, public)")
    result = await client_rw.call_tool("system_health", {})
    if result.get("status") in ("ok", "error"):
        ok("system_health accessible par client_rw")
    else:
        fail("system_health accessible par client_rw")

    # 1.3 — system_about (admin)
    print("\n  📋 1.3 — system_about (admin)")
    result = await admin.call_tool("system_about", {})
    if assert_ok(result, "system_about (admin)"):
        assert_field(result, "identity", "  → identity présent")
        assert_field(result, "capabilities", "  → capabilities présent")
        assert_field(result, "services", "  → services présent")
        # Vérifier la version
        identity = result.get("identity", {})
        version = identity.get("version", "?")
        ok(f"  → version: {version}")
        capabilities = result.get("capabilities", {})
        if capabilities.get("total_tools") == 40:
            ok("  → total_tools MCP exact")
        else:
            fail("  → total_tools MCP exact", f"total_tools={capabilities.get('total_tools')}")
        categories = capabilities.get("categories", {})
        if categories.get("Ingestion asynchrone") == 5:
            ok("  → catégorie Ingestion asynchrone (5 outils)")
        else:
            fail("  → catégorie Ingestion asynchrone", f"obtenu {categories.get('Ingestion asynchrone')}")
        if categories.get("Ontologies") == 6:
            ok("  → catégorie Ontologies complète")
        else:
            fail("  → catégorie Ontologies complète", f"categories={categories}")

    # 1.4 — system_about depuis un client read-only (public)
    print("\n  📋 1.4 — system_about (client_ro, public)")
    result = await client_ro.call_tool("system_about", {})
    assert_ok(result, "system_about accessible par client_ro")

    # 1.5 — ontology_list
    print("\n  📋 1.5 — ontology_list (admin)")
    result = await admin.call_tool("ontology_list", {})
    if assert_ok(result, "ontology_list"):
        count = result.get("count", 0)
        ok(f"  → {count} ontologies disponibles")
        names = [o.get("name", "?") for o in result.get("ontologies", [])]
        if "general" in names:
            ok("  → ontologie 'general' présente")
        else:
            fail("  → ontologie 'general' manquante", f"Trouvées: {names}")

    # 1.6 — ontology_list depuis un client non-admin (public)
    print("\n  📋 1.6 — ontology_list (client_rw, public)")
    result = await client_rw.call_tool("ontology_list", {})
    assert_ok(result, "ontology_list accessible par client_rw")

    # 1.7 — system_whoami (admin/bootstrap)
    print("\n  📋 1.7 — system_whoami (admin)")
    result = await admin.call_tool("system_whoami", {})
    if assert_ok(result, "system_whoami (admin)"):
        auth_type = result.get("auth_type", "?")
        client_name = result.get("client_name", "?")
        permissions = result.get("permissions", [])
        ok(f"  → auth_type: {auth_type}, client: {client_name}")
        if "admin" in permissions:
            ok("  → permission admin présente")
        else:
            fail("  → permission admin manquante", f"permissions: {permissions}")

    # 1.8 — system_whoami (client_rw)
    print("\n  📋 1.8 — system_whoami (client_rw)")
    result = await client_rw.call_tool("system_whoami", {})
    if assert_ok(result, "system_whoami (client_rw)"):
        auth_type = result.get("auth_type", "?")
        permissions = result.get("permissions", [])
        if auth_type == "token":
            ok(f"  → auth_type: token")
        else:
            fail(f"  → auth_type attendu: token, obtenu: {auth_type}")
        if "write" in permissions:
            ok("  → permission write présente")
        else:
            fail("  → permission write manquante", f"permissions: {permissions}")

    # 1.9 — system_whoami (client_ro)
    print("\n  📋 1.9 — system_whoami (client_ro)")
    result = await client_ro.call_tool("system_whoami", {})
    if assert_ok(result, "system_whoami (client_ro)"):
        permissions = result.get("permissions", [])
        if "read" in permissions and "write" not in permissions:
            ok("  → permissions read-only correctes")
        else:
            fail("  → permissions read-only incorrectes", f"permissions: {permissions}")

    # 1.10 — ontology_get / ontology_export sur une ontologie existante
    print("\n  📋 1.10 — ontology_get/export (general)")
    result = await admin.call_tool("ontology_get", {"name": "general"})
    if assert_ok(result, "ontology_get general"):
        if result.get("name") == "general":
            ok("  → nom general confirmé")
        else:
            fail("  → nom general confirmé", f"name={result.get('name')}")
        if result.get("entity_types_count", 0) > 0 and result.get("relation_types_count", 0) > 0:
            ok("  → types entités/relations présents")
        else:
            fail("  → types entités/relations présents", str(result))
        content = result.get("content", "")
        if "name: general" in content:
            ok("  → contenu YAML brut présent")
        else:
            fail("  → contenu YAML brut présent")

    export_result = await admin.call_tool("ontology_export", {"name": "general"})
    if assert_ok(export_result, "ontology_export general"):
        try:
            decoded = base64.b64decode(export_result.get("content_base64", "")).decode("utf-8")
            if decoded == export_result.get("content"):
                ok("  → export base64 fidèle au YAML")
            else:
                fail("  → export base64 fidèle au YAML")
        except Exception as e:
            fail("  → export base64 décodable", str(e))

    # 1.11 — CRUD admin des ontologies avec refus et conflits
    print("\n  📋 1.11 — ontology import/update/delete (admin + refus)")
    create_yaml = _ontology_yaml(TEMP_ONTOLOGY, "1.0", "Création recette")
    update_yaml = _ontology_yaml(TEMP_ONTOLOGY, "1.1", "Mise à jour recette")
    renamed_yaml = _ontology_yaml(f"{TEMP_ONTOLOGY}-renamed", "1.1", "Renommage interdit")
    invalid_yaml = f"""name: {TEMP_ONTOLOGY}-invalid
version: "1.0"
description: "Invalide car sans relations"
entity_types:
  - name: TestEntity
    description: "Entité seulement"
"""

    await admin.call_tool("ontology_delete", {"name": TEMP_ONTOLOGY, "force": True})
    try:
        result = await client_rw.call_tool("ontology_import", {
            "content_yaml": create_yaml,
            "overwrite": True,
        })
        assert_error(result, "ontology_import refusé sans admin", "admin")

        result = await admin.call_tool("ontology_import", {
            "content_yaml": invalid_yaml,
            "overwrite": True,
        })
        assert_error(result, "ontology_import refuse un YAML incomplet", "relation_types")

        result = await admin.call_tool("ontology_import", {
            "content_yaml": create_yaml,
            "overwrite": False,
        })
        if assert_ok(result, "ontology_import crée une ontologie temporaire"):
            if result.get("name") == TEMP_ONTOLOGY:
                ok("  → nom importé correct")
            else:
                fail("  → nom importé correct", f"name={result.get('name')}")

        result = await admin.call_tool("ontology_import", {
            "content_yaml": create_yaml,
            "overwrite": False,
        })
        assert_error(result, "ontology_import refuse un doublon sans overwrite", "existe déjà")

        result = await admin.call_tool("ontology_get", {"name": TEMP_ONTOLOGY})
        if assert_ok(result, "ontology_get retrouve l'ontologie importée"):
            if result.get("version") == "1.0":
                ok("  → version initiale correcte")
            else:
                fail("  → version initiale correcte", f"version={result.get('version')}")

        result = await admin.call_tool("ontology_update", {
            "name": TEMP_ONTOLOGY,
            "content_yaml": renamed_yaml,
        })
        assert_error(result, "ontology_update refuse le changement de name", "doit rester identique")

        result = await admin.call_tool("ontology_update", {
            "name": TEMP_ONTOLOGY,
            "content_yaml": update_yaml,
        })
        assert_ok(result, "ontology_update met à jour le YAML")

        result = await admin.call_tool("ontology_export", {"name": TEMP_ONTOLOGY})
        if assert_ok(result, "ontology_export retourne la version mise à jour"):
            if "version: \"1.1\"" in result.get("content", ""):
                ok("  → version exportée correcte")
            else:
                fail("  → version exportée correcte", result.get("content", "")[:120])

        result = await admin.call_tool("ontology_delete", {"name": TEMP_ONTOLOGY, "force": False})
        assert_ok(result, "ontology_delete supprime l'ontologie temporaire")

        result = await admin.call_tool("ontology_get", {"name": TEMP_ONTOLOGY})
        assert_error(result, "ontology_get échoue après suppression", "non trouvée")
    finally:
        await admin.call_tool("ontology_delete", {"name": TEMP_ONTOLOGY, "force": True})

    # 1.12 — contrôles statiques admin UI
    print("\n  📋 1.12 — admin UI statique")
    _assert_admin_ui_actions_are_wired()
    _assert_admin_ui_no_raw_tool()
    _assert_admin_ui_modules_have_emoji()
    _assert_ingest_jobs_admin_page()
    _assert_backup_all_memories_supported()
    _assert_json_results_use_modal_tabs()
    _assert_admin_assets_are_cache_busted()
    _assert_result_modals_are_rich()
    _assert_dashboard_stats_are_present()
    _assert_storage_check_layout_is_aligned()
    _assert_token_modals_are_usable()
    _assert_cli_and_admin_stay_in_sync()
