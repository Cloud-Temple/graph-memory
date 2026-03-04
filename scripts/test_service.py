#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de test end-to-end — Graph Memory Service

Teste toutes les fonctionnalités du service Graph Memory via le protocole
MCP Streamable HTTP (endpoint /mcp). Crée une mémoire de test, ingère un
document, vérifie la recherche, le Q&A, les backups, les tokens et l'API
REST, puis nettoie automatiquement.

Usage:
    # Serveur local (défaut : http://localhost:8080)
    python3 scripts/test_service.py

    # Serveur distant
    MCP_URL=https://graph-mem.example.com MCP_TOKEN=xxx python3 scripts/test_service.py

    # Verbose (affiche les réponses complètes)
    python3 scripts/test_service.py --verbose

Prérequis:
    - Le serveur doit tourner (docker compose up -d)
    - pip install mcp>=1.8.0 httpx

Catégories de tests (9) :
    1. Connectivité     — REST /health + MCP system_health + system_about
    2. CRUD Mémoire     — ontology_list + memory_create/list/stats
    3. Ingestion        — memory_ingest + notifications de progression
    4. Recherche & Q&A  — memory_search + question_answer + memory_query + memory_get_context
    5. Documents        — document_list + document_get + memory_graph
    6. Stockage S3      — storage_check
    7. Backup           — backup_create + backup_list + backup_delete
    8. Tokens           — admin_list_tokens + admin_create_token + admin_revoke_token
    9. API REST         — GET /api/memories + GET /api/graph/{id}

Exit code: 0 si tous les tests passent, 1 sinon.
"""

import os
import sys
import json
import time
import base64
import asyncio
import argparse
import traceback
from datetime import datetime

# =============================================================================
# Configuration
# =============================================================================

BASE_URL = os.getenv("MCP_URL", os.getenv("MCP_SERVER_URL", "http://localhost:8080"))
TOKEN = os.getenv("MCP_TOKEN", os.getenv("ADMIN_BOOTSTRAP_KEY", "admin_bootstrap_key_change_me"))

TEST_MEMORY_ID = f"_test_e2e_{int(time.time())}"
TEST_MEMORY_NAME = "Test E2E"
TEST_ONTOLOGY = "general"

# Petit document Markdown pour les tests d'ingestion
TEST_DOCUMENT = """# Test Document — Graph Memory E2E

## Cloud Temple

Cloud Temple est un fournisseur français de cloud souverain, certifié SecNumCloud.
Il propose des services IaaS, PaaS et SaaS conformes aux exigences de sécurité.

## Services

- **IaaS VMware** : Machines virtuelles sur infrastructure qualifiée
- **Stockage S3** : Compatible Dell ECS, région FR1
- **Kubernetes managé** : Clusters K8s certifiés CNCF

## Certifications

Cloud Temple possède les certifications suivantes :
- SecNumCloud (ANSSI)
- ISO 27001
- HDS (Hébergement de Données de Santé)

## Contacts

Le support technique est joignable 24/7 via le portail Shiva.
"""

# =============================================================================
# Helpers
# =============================================================================

VERBOSE = False
PASS = 0
FAIL = 0
SKIP = 0
RESULTS = []


def log(msg: str, level: str = "info"):
    """Affiche un message avec timestamp."""
    ts = datetime.now().strftime("%H:%M:%S")
    prefix = {"info": "ℹ️", "ok": "✅", "fail": "❌", "warn": "⚠️", "skip": "⏭️"}.get(level, "")
    print(f"  [{ts}] {prefix} {msg}")


def record(test_name: str, passed: bool, detail: str = "", skipped: bool = False):
    """Enregistre un résultat de test."""
    global PASS, FAIL, SKIP
    if skipped:
        SKIP += 1
        status = "SKIP"
    elif passed:
        PASS += 1
        status = "PASS"
    else:
        FAIL += 1
        status = "FAIL"
    RESULTS.append({"test": test_name, "status": status, "detail": detail})
    emoji = {"PASS": "✅", "FAIL": "❌", "SKIP": "⏭️"}[status]
    print(f"  {emoji} {test_name}" + (f" — {detail}" if detail else ""))


async def call_tool(tool_name: str, args: dict = {}, expect_status: str = "ok") -> dict:
    """
    Appelle un outil MCP via Streamable HTTP et vérifie le statut.
    Retourne le résultat ou lève une exception.
    """
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    headers = {"Authorization": f"Bearer {TOKEN}"}
    notifications = []

    async with streamablehttp_client(
        f"{BASE_URL}/mcp",
        headers=headers,
        timeout=30,
        sse_read_timeout=600,
    ) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # Capturer les notifications
            _original = session._received_notification

            async def _patched(notification):
                try:
                    root = getattr(notification, 'root', notification)
                    params = getattr(root, 'params', None)
                    if params:
                        msg = getattr(params, 'data', None)
                        if msg:
                            notifications.append(str(msg))
                except Exception:
                    pass
                await _original(notification)

            session._received_notification = _patched

            result = await session.call_tool(tool_name, args)

            # Parser la réponse
            text = ""
            if result.content:
                text = getattr(result.content[0], 'text', '') or ""

            if not text:
                raise RuntimeError(f"Réponse vide pour {tool_name}")

            data = json.loads(text)

            if VERBOSE:
                print(f"    📦 {tool_name} → {json.dumps(data, indent=2, ensure_ascii=False)[:500]}")

            if notifications and VERBOSE:
                print(f"    📣 {len(notifications)} notifications reçues")

            data["_notifications"] = notifications
            return data


async def call_rest(endpoint: str) -> dict:
    """Appelle un endpoint REST GET."""
    import httpx
    headers = {"Authorization": f"Bearer {TOKEN}"}
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"{BASE_URL}{endpoint}", headers=headers)
        return resp.json()


# =============================================================================
# Tests
# =============================================================================

async def test_01_connectivity():
    """Test 1: Connectivité de base (REST health + Streamable HTTP handshake)"""
    print("\n🔌 TEST 1 — Connectivité")
    print("=" * 50)

    # 1a. REST health
    try:
        data = await call_rest("/health")
        ok = data.get("status") in ("healthy", "degraded")
        record("REST /health", ok, data.get("status", "?"))
    except Exception as e:
        record("REST /health", False, str(e))
        return False

    # 1b. Streamable HTTP — system_health
    try:
        data = await call_tool("system_health")
        ok = data.get("status") in ("ok", "error")
        services = data.get("services", {})
        summary = ", ".join(f"{k}={v.get('status','?')}" for k, v in services.items())
        record("MCP system_health (Streamable HTTP)", ok, summary)
    except Exception as e:
        record("MCP system_health (Streamable HTTP)", False, str(e))
        return False

    # 1c. system_about
    try:
        data = await call_tool("system_about")
        ok = data.get("status") == "ok"
        tools = data.get("capabilities", {}).get("total_tools", "?")
        record("MCP system_about", ok, f"{tools} outils")
    except Exception as e:
        record("MCP system_about", False, str(e))

    return True


async def test_02_memory_crud():
    """Test 2: CRUD Mémoire"""
    print(f"\n📦 TEST 2 — CRUD Mémoire ({TEST_MEMORY_ID})")
    print("=" * 50)

    # 2a. Lister les ontologies
    try:
        data = await call_tool("ontology_list")
        ok = data.get("status") == "ok" and data.get("count", 0) > 0
        names = [o.get("name") for o in data.get("ontologies", [])]
        record("ontology_list", ok, f"{data.get('count')} ontologies: {names}")
    except Exception as e:
        record("ontology_list", False, str(e))

    # 2b. Créer une mémoire de test
    try:
        data = await call_tool("memory_create", {
            "memory_id": TEST_MEMORY_ID,
            "name": TEST_MEMORY_NAME,
            "ontology": TEST_ONTOLOGY,
            "description": "Mémoire de test end-to-end (auto-supprimée)"
        })
        ok = data.get("status") == "created"
        record("memory_create", ok, data.get("memory_id", data.get("message", "?")))
    except Exception as e:
        record("memory_create", False, str(e))
        return False

    # 2c. Lister les mémoires
    try:
        data = await call_tool("memory_list")
        ok = data.get("status") == "ok"
        ids = [m.get("id") for m in data.get("memories", [])]
        found = TEST_MEMORY_ID in ids
        record("memory_list (contient test)", ok and found, f"{data.get('count')} mémoires")
    except Exception as e:
        record("memory_list", False, str(e))

    # 2d. Stats de la mémoire
    try:
        data = await call_tool("memory_stats", {"memory_id": TEST_MEMORY_ID})
        ok = data.get("status") == "ok"
        record("memory_stats", ok, f"docs={data.get('document_count',0)}, entities={data.get('entity_count',0)}")
    except Exception as e:
        record("memory_stats", False, str(e))

    return True


async def test_03_ingestion():
    """Test 3: Ingestion de document avec notifications de progression"""
    print(f"\n📥 TEST 3 — Ingestion document")
    print("=" * 50)

    content_b64 = base64.b64encode(TEST_DOCUMENT.encode("utf-8")).decode("ascii")

    try:
        data = await call_tool("memory_ingest", {
            "memory_id": TEST_MEMORY_ID,
            "content_base64": content_b64,
            "filename": "test-e2e.md",
            "metadata": {"test": True},
            "source_path": "test/test-e2e.md",
        })
        ok = data.get("status") == "ok"
        entities = data.get("entities_extracted", 0)
        relations = data.get("relations_extracted", 0)
        chunks = data.get("chunks_stored", 0)
        elapsed = data.get("elapsed_seconds", "?")
        notifs = len(data.get("_notifications", []))

        record("memory_ingest", ok, f"{entities}E {relations}R {chunks}chunks en {elapsed}s")
        record("notifications progression", notifs > 0, f"{notifs} notifications reçues")

        if ok and entities > 0:
            # Vérifier les types d'entités
            types = data.get("entity_types", {})
            record("extraction entités", True, f"types: {dict(list(types.items())[:5])}")
        elif ok:
            record("extraction entités", False, "0 entités extraites")

        return ok
    except Exception as e:
        record("memory_ingest", False, str(e))
        if VERBOSE:
            traceback.print_exc()
        return False


async def test_04_search():
    """Test 4: Recherche et Q&A"""
    print(f"\n🔍 TEST 4 — Recherche et Q&A")
    print("=" * 50)

    # 4a. Recherche d'entités
    try:
        data = await call_tool("memory_search", {
            "memory_id": TEST_MEMORY_ID,
            "query": "Cloud Temple",
            "limit": 5
        })
        ok = data.get("status") == "ok"
        count = data.get("result_count", 0)
        record("memory_search", ok, f"{count} résultats pour 'Cloud Temple'")
    except Exception as e:
        record("memory_search", False, str(e))

    # 4b. Question/Réponse (LLM)
    try:
        data = await call_tool("question_answer", {
            "memory_id": TEST_MEMORY_ID,
            "question": "Quelles certifications possède Cloud Temple ?",
            "limit": 5
        })
        ok = data.get("status") == "ok"
        has_answer = bool(data.get("answer", ""))
        rag_chunks = data.get("rag_chunks_used", 0)
        docs = len(data.get("source_documents", []))
        record("question_answer", ok and has_answer, f"answer={len(data.get('answer',''))}chars, RAG={rag_chunks}chunks, docs={docs}")
        if VERBOSE and has_answer:
            print(f"    📝 Réponse: {data['answer'][:200]}...")
    except Exception as e:
        record("question_answer", False, str(e))

    # 4c. Query structuré (sans LLM)
    try:
        data = await call_tool("memory_query", {
            "memory_id": TEST_MEMORY_ID,
            "query": "SecNumCloud",
            "limit": 5
        })
        ok = data.get("status") == "ok"
        entities = data.get("stats", {}).get("entities_found", 0)
        rag = data.get("stats", {}).get("rag_chunks_retained", 0)
        record("memory_query", ok, f"{entities} entités, {rag} chunks RAG")
    except Exception as e:
        record("memory_query", False, str(e))

    # 4d. Contexte d'entité
    try:
        # Chercher une entité existante
        search = await call_tool("memory_search", {
            "memory_id": TEST_MEMORY_ID,
            "query": "Cloud Temple",
            "limit": 1
        })
        results = search.get("results", [])
        if results:
            entity_name = results[0].get("entity", {}).get("name", "Cloud Temple")
            data = await call_tool("memory_get_context", {
                "memory_id": TEST_MEMORY_ID,
                "entity_name": entity_name,
                "depth": 1
            })
            ok = data.get("status") == "ok"
            rels = len(data.get("relations", []))
            docs = len(data.get("documents", []))
            record("memory_get_context", ok, f"entity='{entity_name}', {rels} relations, {docs} docs")
        else:
            record("memory_get_context", False, "Pas d'entité trouvée pour le test", skipped=True)
    except Exception as e:
        record("memory_get_context", False, str(e))


async def test_05_documents():
    """Test 5: Gestion documents"""
    print(f"\n📄 TEST 5 — Gestion documents")
    print("=" * 50)

    # 5a. Lister les documents
    doc_id = None
    try:
        data = await call_tool("document_list", {"memory_id": TEST_MEMORY_ID})
        ok = data.get("status") == "ok" and data.get("count", 0) > 0
        record("document_list", ok, f"{data.get('count',0)} documents")
        if data.get("documents"):
            doc_id = data["documents"][0].get("id")
    except Exception as e:
        record("document_list", False, str(e))

    # 5b. Détails d'un document
    if doc_id:
        try:
            data = await call_tool("document_get", {
                "memory_id": TEST_MEMORY_ID,
                "document_id": doc_id,
                "include_content": False
            })
            ok = data.get("status") == "ok"
            doc = data.get("document", {})
            record("document_get", ok, f"filename={doc.get('filename')}, size={doc.get('size_bytes')}B")
        except Exception as e:
            record("document_get", False, str(e))
    else:
        record("document_get", False, "Pas de doc_id", skipped=True)

    # 5c. Graphe complet
    try:
        data = await call_tool("memory_graph", {"memory_id": TEST_MEMORY_ID, "format": "full"})
        ok = data.get("status") == "ok"
        record("memory_graph", ok,
               f"nodes={data.get('node_count',0)}, edges={data.get('edge_count',0)}, docs={data.get('document_count',0)}")
    except Exception as e:
        record("memory_graph", False, str(e))

    return doc_id


async def test_06_storage():
    """Test 6: Vérification stockage S3"""
    print(f"\n🗄️ TEST 6 — Vérification S3")
    print("=" * 50)

    try:
        data = await call_tool("storage_check", {"memory_id": TEST_MEMORY_ID})
        ok = data.get("status") == "ok"
        summary = data.get("summary", "?")
        record("storage_check", ok, summary)
    except Exception as e:
        record("storage_check", False, str(e))


async def test_07_backup():
    """Test 7: Backup / Restore"""
    print(f"\n💾 TEST 7 — Backup")
    print("=" * 50)

    backup_id = None

    # 7a. Créer un backup
    try:
        data = await call_tool("backup_create", {
            "memory_id": TEST_MEMORY_ID,
            "description": "Test backup E2E"
        })
        ok = data.get("status") == "ok"
        backup_id = data.get("backup_id")
        record("backup_create", ok, f"backup_id={backup_id}")
    except Exception as e:
        record("backup_create", False, str(e))

    # 7b. Lister les backups
    try:
        data = await call_tool("backup_list", {"memory_id": TEST_MEMORY_ID})
        ok = data.get("status") == "ok" and data.get("count", 0) > 0
        record("backup_list", ok, f"{data.get('count',0)} backups")
    except Exception as e:
        record("backup_list", False, str(e))

    # 7c. Supprimer le backup (nettoyage)
    if backup_id:
        try:
            data = await call_tool("backup_delete", {"backup_id": backup_id})
            ok = data.get("status") == "ok"
            record("backup_delete", ok, f"backup_id={backup_id}")
        except Exception as e:
            record("backup_delete", False, str(e))


async def test_08_tokens():
    """Test 8: Gestion des tokens"""
    print(f"\n🔑 TEST 8 — Tokens")
    print("=" * 50)

    token_hash = None

    # 8a. Lister les tokens
    try:
        data = await call_tool("admin_list_tokens")
        ok = data.get("status") == "ok"
        record("admin_list_tokens", ok, f"{data.get('count',0)} tokens")
    except Exception as e:
        record("admin_list_tokens", False, str(e))

    # 8b. Créer un token de test
    try:
        data = await call_tool("admin_create_token", {
            "client_name": f"test-e2e-{int(time.time())}",
            "permissions": ["read"],
            "memory_ids": [TEST_MEMORY_ID],
        })
        ok = data.get("status") == "ok"
        token_val = data.get("token", "")
        record("admin_create_token", ok, f"token={'***' + token_val[-8:] if token_val else '?'}")

        # Récupérer le hash pour le révoquer
        if ok:
            tokens = await call_tool("admin_list_tokens")
            for t in tokens.get("tokens", []):
                if t.get("client_name", "").startswith("test-e2e-"):
                    token_hash = t.get("token_hash", "")[:12]
                    break
    except Exception as e:
        record("admin_create_token", False, str(e))

    # 8c. Révoquer le token
    if token_hash:
        try:
            data = await call_tool("admin_revoke_token", {"token_hash_prefix": token_hash})
            ok = data.get("status") == "ok"
            record("admin_revoke_token", ok, data.get("message", "?"))
        except Exception as e:
            record("admin_revoke_token", False, str(e))


async def test_09_rest_api():
    """Test 9: API REST (servie par StaticFilesMiddleware)"""
    print(f"\n🌐 TEST 9 — API REST")
    print("=" * 50)

    # 9a. GET /api/memories
    try:
        data = await call_rest("/api/memories")
        ok = data.get("status") == "ok"
        record("GET /api/memories", ok, f"{data.get('count',0)} mémoires")
    except Exception as e:
        record("GET /api/memories", False, str(e))

    # 9b. GET /api/graph/{memory_id}
    try:
        data = await call_rest(f"/api/graph/{TEST_MEMORY_ID}")
        ok = data.get("status") == "ok"
        record(f"GET /api/graph/{TEST_MEMORY_ID}", ok,
               f"nodes={data.get('node_count',0)}, edges={data.get('edge_count',0)}")
    except Exception as e:
        record(f"GET /api/graph/...", False, str(e))


async def test_99_cleanup():
    """Nettoyage: suppression de la mémoire de test"""
    print(f"\n🧹 CLEANUP — Suppression mémoire {TEST_MEMORY_ID}")
    print("=" * 50)

    try:
        data = await call_tool("memory_delete", {"memory_id": TEST_MEMORY_ID})
        ok = data.get("status") == "deleted"
        record("memory_delete (cleanup)", ok, f"S3={data.get('s3_files_deleted',0)}, Qdrant={data.get('qdrant_collection_deleted')}")
    except Exception as e:
        record("memory_delete (cleanup)", False, str(e))


# =============================================================================
# Main
# =============================================================================

async def run_all_tests():
    """Exécute tous les tests dans l'ordre."""
    print("=" * 60)
    print("🧪 TEST END-TO-END — Graph Memory Service")
    print(f"   Serveur : {BASE_URL}")
    print(f"   Token   : {'***' + TOKEN[-8:] if len(TOKEN) > 8 else '***'}")
    print(f"   Mémoire : {TEST_MEMORY_ID}")
    print(f"   Date    : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    t0 = time.monotonic()

    # Phase 1: Connectivité (si ça échoue, on arrête)
    connected = await test_01_connectivity()
    if not connected:
        print("\n❌ ARRÊT — Impossible de se connecter au serveur")
        print(f"   Vérifiez : docker compose up -d && docker compose logs -f mcp-memory")
        return False

    # Phase 2: CRUD Mémoire
    created = await test_02_memory_crud()
    if not created:
        print("\n❌ ARRÊT — Impossible de créer la mémoire de test")
        return False

    # Phase 3: Ingestion
    ingested = await test_03_ingestion()

    # Phase 4: Recherche (si ingestion OK)
    if ingested:
        await test_04_search()
    else:
        print("\n⏭️ TEST 4 — Recherche (SKIPPED — ingestion échouée)")
        record("search tests", False, "skipped", skipped=True)

    # Phase 5: Documents
    await test_05_documents()

    # Phase 6: Storage
    await test_06_storage()

    # Phase 7: Backup
    await test_07_backup()

    # Phase 8: Tokens
    await test_08_tokens()

    # Phase 9: REST API
    await test_09_rest_api()

    # Phase 99: Cleanup
    await test_99_cleanup()

    # Résumé
    elapsed = round(time.monotonic() - t0, 1)
    total = PASS + FAIL + SKIP

    print("\n" + "=" * 60)
    print("📊 RÉSUMÉ")
    print("=" * 60)
    print(f"  Tests   : {total} total")
    print(f"  ✅ PASS  : {PASS}")
    print(f"  ❌ FAIL  : {FAIL}")
    print(f"  ⏭️ SKIP  : {SKIP}")
    print(f"  ⏱️ Durée  : {elapsed}s")
    print(f"  🔗 Transport : Streamable HTTP (/mcp)")
    print("=" * 60)

    if FAIL == 0:
        print("\n🎉 TOUS LES TESTS PASSENT !")
    else:
        print(f"\n⚠️ {FAIL} TESTS EN ÉCHEC")
        print("\nDétails des échecs :")
        for r in RESULTS:
            if r["status"] == "FAIL":
                print(f"  ❌ {r['test']}: {r['detail']}")

    return FAIL == 0


def main():
    global VERBOSE
    parser = argparse.ArgumentParser(description="Test end-to-end du service Graph Memory")
    parser.add_argument("--verbose", "-v", action="store_true", help="Affiche les réponses complètes")
    args = parser.parse_args()
    VERBOSE = args.verbose

    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
