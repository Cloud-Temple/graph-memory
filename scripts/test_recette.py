#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Recette complète graph-memory — Teste TOUTES les fonctionnalités.

7 phases de tests couvrant les 28 outils MCP :
  1. Système    : system_health, system_about, ontology_list
  2. Tokens     : CRUD admin, isolation non-admin, promotion admin, chaîne de confiance
  3. Mémoires   : CRUD, auto-ajout au token, isolation multi-tenant
  4. Documents   : ingest, list, get, delete, déduplication SHA-256, isolation
  5. Recherche   : search, question_answer, memory_query, get_context, graph
  6. Backup      : backup CRUD, storage_check, storage_cleanup, isolation
  7. Nettoyage   : memory_delete isolation + cleanup tokens

3 profils de tokens testés :
  - Admin (bootstrap key) — accès total
  - Client read+write (restreint à MEMORY_A) — CRUD sur ses mémoires uniquement
  - Client read-only (restreint à MEMORY_B) — lecture seule

Usage :
    export MCP_URL=http://localhost:8002
    export MCP_TOKEN=<admin_bootstrap_key>
    python scripts/test_recette.py

Prérequis : docker compose up -d
"""

import asyncio
import os
import sys
import time

# S'assurer que scripts/ est dans le path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tests import (  # noqa: E402
    MCPClient, ServerNotRunningError, MCP_URL, ADMIN_TOKEN,
    MEMORY_A, MEMORY_B, MEMORY_C,
    get_counters, reset_counters, assert_ok, ok, phase_header
)
from tests import test_system, test_tokens, test_memories  # noqa: E402
from tests import test_documents, test_search, test_backup, test_cleanup  # noqa: E402


async def setup_tokens(admin: MCPClient) -> dict:
    """Crée les tokens de test et retourne leurs infos."""
    phase_header(0, "Préparation — Nettoyage + création tokens", "🔧")

    # Nettoyage des mémoires de test
    for mid in [MEMORY_A, MEMORY_B, MEMORY_C]:
        result = await admin.call_tool("memory_delete", {"memory_id": mid})
        s = result.get("status", "?")
        print(f"  {'🗑️' if s == 'deleted' else 'ℹ️'}  {mid}: {s}")

    tokens = {}

    # Token read+write restreint à MEMORY_A
    result = await admin.call_tool("admin_create_token", {
        "client_name": "test-rw", "permissions": ["read", "write"],
        "memory_ids": [MEMORY_A], "email": "test-rw@recette.local"
    })
    if assert_ok(result, "Créer token client_rw"):
        tokens["client_rw"] = {"token": result["token"]}

    # Token read-only restreint à MEMORY_B
    result = await admin.call_tool("admin_create_token", {
        "client_name": "test-ro", "permissions": ["read"],
        "memory_ids": [MEMORY_B], "email": "test-ro@recette.local"
    })
    if assert_ok(result, "Créer token client_ro"):
        tokens["client_ro"] = {"token": result["token"]}

    # Récupérer les hash prefixes
    result = await admin.call_tool("admin_list_tokens", {})
    for t in result.get("tokens", []):
        name = t.get("client_name", "")
        if name == "test-rw" and "client_rw" in tokens:
            tokens["client_rw"]["hash_prefix"] = t["token_hash"][:12]
        elif name == "test-ro" and "client_ro" in tokens:
            tokens["client_ro"]["hash_prefix"] = t["token_hash"][:12]

    return tokens


async def main():
    """Point d'entrée principal."""
    print("=" * 70)
    print("🧪 RECETTE COMPLÈTE — Graph Memory v1.6.0")
    print(f"   URL     : {MCP_URL}")
    print(f"   Phases  : 7 (système, tokens, mémoires, documents, recherche, backup, cleanup)")
    print(f"   Profils : admin + read/write + read-only")
    print("=" * 70)

    if not ADMIN_TOKEN:
        print("\n❌ Variable MCP_TOKEN manquante")
        print("   export MCP_TOKEN=<votre_admin_bootstrap_key>")
        sys.exit(1)

    admin = MCPClient(MCP_URL, ADMIN_TOKEN)

    # Vérifier la connexion
    try:
        result = await admin.call_tool("system_health", {})
        print(f"\n✅ Serveur connecté ({result.get('status', '?')})")
    except ServerNotRunningError:
        print(f"\n❌ Serveur non accessible ({MCP_URL})")
        print("   docker compose up -d")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Erreur connexion: {e}")
        sys.exit(1)

    t0 = time.monotonic()
    reset_counters()

    try:
        # Phase 0 : Setup
        tokens = await setup_tokens(admin)
        if "client_rw" not in tokens or "client_ro" not in tokens:
            print("\n❌ Tokens de test non créés. Abandon.")
            sys.exit(1)

        client_rw = MCPClient(MCP_URL, tokens["client_rw"]["token"])
        client_ro = MCPClient(MCP_URL, tokens["client_ro"]["token"])
        ctx = {"tokens": tokens}

        # Phases 1-7
        await test_system.run(admin, client_rw, client_ro, **ctx)
        await test_tokens.run(admin, client_rw, client_ro, **ctx)
        await test_memories.run(admin, client_rw, client_ro, **ctx)
        doc_ctx = await test_documents.run(admin, client_rw, client_ro, **ctx)
        if doc_ctx:
            ctx.update(doc_ctx)
        await test_search.run(admin, client_rw, client_ro, **ctx)
        await test_backup.run(admin, client_rw, client_ro, **ctx)
        await test_cleanup.run(admin, client_rw, client_ro, **ctx)

    except Exception as e:
        print(f"\n💥 ERREUR FATALE: {e}")
        import traceback
        traceback.print_exc()

    elapsed = round(time.monotonic() - t0, 1)
    c = get_counters()

    # Rapport final
    print(f"\n{'=' * 70}")
    print("📊 RAPPORT FINAL")
    print("=" * 70)
    print(f"  ✅ Réussis  : {c['passed']}")
    print(f"  ❌ Échoués  : {c['failed']}")
    print(f"  ⏭️  Ignorés  : {c['skipped']}")
    print(f"  ⏱️  Durée    : {elapsed}s")

    if c["errors"]:
        print(f"\n  🔴 Détail des échecs :")
        for err in c["errors"]:
            print(f"    {err}")

    print()
    if c["failed"] == 0:
        print("  🎉 RECETTE RÉUSSIE — Toutes les fonctionnalités OK !")
    else:
        print(f"  🚨 RECETTE ÉCHOUÉE — {c['failed']} test(s) en échec")

    print("=" * 70)
    sys.exit(1 if c["failed"] > 0 else 0)


if __name__ == "__main__":
    asyncio.run(main())
