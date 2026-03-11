# -*- coding: utf-8 -*-
"""Tests documents : ingest, document_list, document_get, document_delete + isolation."""

from . import (MCPClient, MEMORY_A, MEMORY_B,
               assert_ok, assert_error, assert_field, ok, fail, skip, phase_header,
               make_test_doc)


async def run(admin: MCPClient, client_rw: MCPClient, client_ro: MCPClient, **ctx):
    """Phase Documents — Ingestion, CRUD, isolation. Retourne doc_id_a."""
    phase_header(4, "Documents — Ingestion & CRUD + isolation", "📄")

    test_content = make_test_doc()
    doc_id_a = None

    # 4.1 — client_rw ingère dans MEMORY_A (OK)
    print("\n  📋 4.1 — memory_ingest MEMORY_A (client_rw, OK)")
    result = await client_rw.call_tool("memory_ingest", {
        "memory_id": MEMORY_A,
        "content_base64": test_content,
        "filename": "test-recette.txt"
    })
    if assert_ok(result, "memory_ingest MEMORY_A (client_rw)"):
        doc_id_a = result.get("document_id")
        ok(f"  → doc_id: {doc_id_a}")
        # Vérifier les champs de retour
        assert_field(result, "entities_extracted", "  → entities_extracted")
        assert_field(result, "relations_extracted", "  → relations_extracted")
        assert_field(result, "s3_uri", "  → s3_uri")
        assert_field(result, "chunks_stored", "  → chunks_stored (RAG)")

    # 4.2 — client_rw ne peut PAS ingérer dans MEMORY_B
    print("\n  📋 4.2 — memory_ingest MEMORY_B (client_rw, refusé)")
    result = await client_rw.call_tool("memory_ingest", {
        "memory_id": MEMORY_B,
        "content_base64": test_content,
        "filename": "hack.txt"
    })
    assert_error(result, "memory_ingest MEMORY_B refusé (client_rw)", "refusé")

    # 4.3 — client_ro ne peut PAS ingérer (read-only)
    print("\n  📋 4.3 — memory_ingest MEMORY_B (client_ro, refusé write)")
    result = await client_ro.call_tool("memory_ingest", {
        "memory_id": MEMORY_B,
        "content_base64": test_content,
        "filename": "test.txt"
    })
    assert_error(result, "memory_ingest refusé (read-only)")

    # 4.4 — document_list : client_rw OK sur sa mémoire
    print("\n  📋 4.4 — document_list MEMORY_A (client_rw, OK)")
    result = await client_rw.call_tool("document_list", {"memory_id": MEMORY_A})
    if assert_ok(result, "document_list MEMORY_A (client_rw)"):
        count = result.get("count", 0)
        ok(f"  → {count} document(s)")

    # 4.5 — document_list : client_rw refusé sur MEMORY_B
    print("\n  📋 4.5 — document_list MEMORY_B (client_rw, refusé)")
    result = await client_rw.call_tool("document_list", {"memory_id": MEMORY_B})
    assert_error(result, "document_list MEMORY_B refusé (client_rw)", "refusé")

    # 4.6 — document_get : client_rw OK
    if doc_id_a:
        print("\n  📋 4.6 — document_get MEMORY_A (client_rw, OK)")
        result = await client_rw.call_tool("document_get", {
            "memory_id": MEMORY_A, "document_id": doc_id_a
        })
        if assert_ok(result, "document_get (client_rw)"):
            doc = result.get("document", {})
            assert_field(doc, "filename", "  → filename")
            assert_field(doc, "uri", "  → uri S3")
    else:
        skip("4.6 — document_get", "pas de doc_id")

    # 4.7 — document_get : client_ro refusé sur MEMORY_A
    if doc_id_a:
        print("\n  📋 4.7 — document_get MEMORY_A (client_ro, refusé)")
        result = await client_ro.call_tool("document_get", {
            "memory_id": MEMORY_A, "document_id": doc_id_a
        })
        assert_error(result, "document_get refusé (client_ro)", "refusé")
    else:
        skip("4.7 — document_get isolation", "pas de doc_id")

    # 4.8 — Déduplication : ré-ingérer le même doc sans force → already_exists
    print("\n  📋 4.8 — Déduplication (même doc, sans force)")
    result = await client_rw.call_tool("memory_ingest", {
        "memory_id": MEMORY_A,
        "content_base64": test_content,
        "filename": "test-recette.txt"
    })
    status = result.get("status", "")
    if status == "already_exists":
        ok("Déduplication SHA-256 OK (already_exists)")
    else:
        fail("Déduplication SHA-256", f"Attendu already_exists, obtenu {status}")

    # 4.9 — document_delete : client_ro refusé sur MEMORY_A
    if doc_id_a:
        print("\n  📋 4.9 — document_delete MEMORY_A (client_ro, refusé)")
        result = await client_ro.call_tool("document_delete", {
            "memory_id": MEMORY_A, "document_id": doc_id_a
        })
        assert_error(result, "document_delete refusé (client_ro)", "refusé")

    # 4.10 — document_delete : client_rw OK sur sa mémoire
    if doc_id_a:
        print("\n  📋 4.10 — document_delete MEMORY_A (client_rw, OK)")
        result = await client_rw.call_tool("document_delete", {
            "memory_id": MEMORY_A, "document_id": doc_id_a
        })
        assert_ok(result, "document_delete (client_rw)")
    else:
        skip("4.10 — document_delete", "pas de doc_id")

    # Ré-ingérer pour les phases suivantes (search, backup)
    print("\n  📋 4.11 — Ré-ingestion pour les phases suivantes")
    result = await client_rw.call_tool("memory_ingest", {
        "memory_id": MEMORY_A,
        "content_base64": test_content,
        "filename": "test-recette-v2.txt"
    })
    new_doc_id = None
    if assert_ok(result, "Ré-ingestion MEMORY_A"):
        new_doc_id = result.get("document_id")

    return {"doc_id_a": new_doc_id}
