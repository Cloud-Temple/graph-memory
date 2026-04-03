# -*- coding: utf-8 -*-
"""Tests documents : ingest, document_list, document_get, document_delete + isolation."""

from . import (MCPClient, MEMORY_A, MEMORY_B,
               assert_ok, assert_error, assert_field, ok, fail, skip, phase_header,
               make_test_doc, make_test_docx)


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

    # 4.12 — document_get include_content=True sur fichier TEXTE
    if new_doc_id:
        print("\n  📋 4.12 — document_get include_content=True (fichier texte)")
        result = await client_rw.call_tool("document_get", {
            "memory_id": MEMORY_A, "document_id": new_doc_id, "include_content": True
        })
        if assert_ok(result, "document_get include_content (texte)"):
            content = result.get("content", "")
            if content and "Cloud Temple" in content:
                ok("  → contenu texte retourné correctement")
            else:
                fail("  → contenu texte", f"Contenu inattendu: {content[:80]}")
            # Pas de content_note pour les fichiers texte
            if result.get("content_note") is None:
                ok("  → pas de content_note (fichier texte, normal)")
            # Pas de content_encoding pour les fichiers texte
            if result.get("content_encoding") is None:
                ok("  → pas de content_encoding (fichier texte, normal)")
    else:
        skip("4.12 — document_get include_content (texte)", "pas de doc_id")

    # 4.13 — Ingest DOCX + document_get include_content=True (fichier binaire)
    print("\n  📋 4.13 — document_get include_content=True (fichier DOCX binaire)")
    docx_doc_id = None
    try:
        docx_content = make_test_docx()
        result = await admin.call_tool("memory_ingest", {
            "memory_id": MEMORY_A,
            "content_base64": docx_content,
            "filename": "test-recette.docx"
        })
        if assert_ok(result, "memory_ingest DOCX (admin)"):
            docx_doc_id = result.get("document_id")

            # Tester document_get include_content sur le DOCX
            result = await admin.call_tool("document_get", {
                "memory_id": MEMORY_A, "document_id": docx_doc_id, "include_content": True
            })
            if assert_ok(result, "document_get include_content (DOCX)"):
                content = result.get("content", "")
                if content and "Cloud Temple" in content:
                    ok("  → texte extrait du DOCX correctement")
                else:
                    fail("  → extraction texte DOCX", f"Contenu inattendu: {content[:80]}")
                # Vérifier content_note présent pour binaire
                note = result.get("content_note", "")
                if note and "binaire" in note.lower():
                    ok(f"  → content_note présent: {note}")
                else:
                    fail("  → content_note", f"Attendu 'binaire' dans content_note, obtenu: {note}")
                # En mode text (défaut), pas de content_base64
                if result.get("content_base64") is None:
                    ok("  → pas de content_base64 (mode text, normal)")

            # 4.13b — Tester le mode raw (content_format="raw")
            print("\n  📋 4.13b — document_get content_format='raw' (DOCX binaire)")
            result = await admin.call_tool("document_get", {
                "memory_id": MEMORY_A, "document_id": docx_doc_id,
                "include_content": True, "content_format": "raw"
            })
            if assert_ok(result, "document_get content_format=raw (DOCX)"):
                cb64 = result.get("content_base64", "")
                if cb64 and len(cb64) > 100:
                    ok(f"  → content_base64 présent ({len(cb64)} chars)")
                else:
                    fail("  → content_base64", f"Attendu base64 non vide, obtenu: {len(cb64) if cb64 else 0} chars")
                # En mode raw, pas de content texte
                if result.get("content") is None:
                    ok("  → pas de content (mode raw, normal)")
                fmt = result.get("content_format", "")
                if fmt == "raw":
                    ok("  → content_format=raw confirmé")
                else:
                    fail("  → content_format", f"Attendu 'raw', obtenu: {fmt}")
    except Exception as e:
        fail("4.13 — document_get DOCX", f"Exception: {e}")

    # 4.14 — Nettoyage du DOCX de test
    if docx_doc_id:
        print("\n  📋 4.14 — Nettoyage DOCX de test")
        result = await admin.call_tool("document_delete", {
            "memory_id": MEMORY_A, "document_id": docx_doc_id
        })
        assert_ok(result, "document_delete DOCX (nettoyage)")
    else:
        skip("4.14 — Nettoyage DOCX", "pas de docx_doc_id")

    return {"doc_id_a": new_doc_id}
