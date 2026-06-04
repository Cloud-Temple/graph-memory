# -*- coding: utf-8 -*-
"""Tests recherche : memory_search, question_answer, memory_query, memory_get_context, memory_graph."""

import base64

from . import (MCPClient, MEMORY_A, MEMORY_B,
               assert_ok, assert_error, assert_field, ok, fail, skip, phase_header)


async def run(admin: MCPClient, client_rw: MCPClient, client_ro: MCPClient, **ctx):
    """Phase Recherche — Search, Q&A, Query, Context, Graph + isolation."""
    phase_header(5, "Recherche & Q&A — Fonctionnel + isolation", "🔍")

    # 5.1 — memory_search : client_rw sur MEMORY_A (OK)
    print("\n  📋 5.1 — memory_search MEMORY_A (client_rw, OK)")
    result = await client_rw.call_tool("memory_search", {
        "memory_id": MEMORY_A, "query": "cloud"
    })
    if assert_ok(result, "memory_search MEMORY_A (client_rw)"):
        count = result.get("result_count", 0)
        ok(f"  → {count} résultat(s)")

    # 5.2 — memory_search : client_rw refusé sur MEMORY_B
    print("\n  📋 5.2 — memory_search MEMORY_B (client_rw, refusé)")
    result = await client_rw.call_tool("memory_search", {
        "memory_id": MEMORY_B, "query": "cloud"
    })
    assert_error(result, "memory_search MEMORY_B refusé (client_rw)", "refusé")

    # 5.3 — question_answer : client_rw sur MEMORY_A (OK)
    print("\n  📋 5.3 — question_answer MEMORY_A (client_rw, OK)")
    result = await client_rw.call_tool("question_answer", {
        "memory_id": MEMORY_A, "question": "Qu'est-ce que Cloud Temple ?"
    })
    if assert_ok(result, "question_answer MEMORY_A (client_rw)"):
        assert_field(result, "answer", "  → answer présente")
        rag = result.get("rag_chunks_used", 0)
        ok(f"  → RAG chunks utilisés: {rag}")
        docs = result.get("source_documents", [])
        ok(f"  → {len(docs)} document(s) source")

    # 5.4 — question_answer : client_ro refusé sur MEMORY_A
    print("\n  📋 5.4 — question_answer MEMORY_A (client_ro, refusé)")
    result = await client_ro.call_tool("question_answer", {
        "memory_id": MEMORY_A, "question": "Test"
    })
    assert_error(result, "question_answer MEMORY_A refusé (client_ro)", "refusé")

    # 5.5 — memory_query : client_rw sur MEMORY_A (OK, sans LLM)
    print("\n  📋 5.5 — memory_query MEMORY_A (client_rw, OK)")
    result = await client_rw.call_tool("memory_query", {
        "memory_id": MEMORY_A, "query": "cloud souverain"
    })
    if assert_ok(result, "memory_query MEMORY_A (client_rw)"):
        assert_field(result, "entities", "  → entities")
        assert_field(result, "stats", "  → stats")
        mode = result.get("retrieval_mode", "?")
        ok(f"  → retrieval_mode: {mode}")

    # 5.6 — memory_query : client_rw refusé sur MEMORY_B
    print("\n  📋 5.6 — memory_query MEMORY_B (client_rw, refusé)")
    result = await client_rw.call_tool("memory_query", {
        "memory_id": MEMORY_B, "query": "test"
    })
    assert_error(result, "memory_query MEMORY_B refusé (client_rw)", "refusé")

    # 5.7 — memory_get_context : client_rw sur MEMORY_A (OK)
    print("\n  📋 5.7 — memory_get_context MEMORY_A (client_rw, OK)")
    result = await client_rw.call_tool("memory_get_context", {
        "memory_id": MEMORY_A, "entity_name": "Cloud Temple"
    })
    # Peut retourner OK même sans entité trouvée
    status = result.get("status", "")
    if status == "ok":
        ok("memory_get_context MEMORY_A (client_rw)")
    elif status == "error" and "refusé" not in result.get("message", "").lower():
        ok("memory_get_context MEMORY_A (entité non trouvée, OK)")
    else:
        fail("memory_get_context MEMORY_A", f"status={status}")

    # 5.8 — memory_get_context : client_rw refusé sur MEMORY_B
    print("\n  📋 5.8 — memory_get_context MEMORY_B (client_rw, refusé)")
    result = await client_rw.call_tool("memory_get_context", {
        "memory_id": MEMORY_B, "entity_name": "Test"
    })
    assert_error(result, "memory_get_context MEMORY_B refusé (client_rw)", "refusé")

    # 5.9 — memory_graph : client_rw sur MEMORY_A (OK)
    print("\n  📋 5.9 — memory_graph MEMORY_A (client_rw, OK)")
    result = await client_rw.call_tool("memory_graph", {"memory_id": MEMORY_A})
    if assert_ok(result, "memory_graph MEMORY_A (client_rw)"):
        nodes = result.get("node_count", 0)
        edges = result.get("edge_count", 0)
        docs = result.get("document_count", 0)
        ok(f"  → {nodes} nodes, {edges} edges, {docs} docs")

    # 5.10 — memory_graph : formats (nodes, edges, documents)
    print("\n  📋 5.10 — memory_graph formats (nodes/edges/documents)")
    for fmt in ["nodes", "edges", "documents"]:
        result = await admin.call_tool("memory_graph", {
            "memory_id": MEMORY_A, "format": fmt
        })
        assert_ok(result, f"memory_graph format={fmt}")

    # 5.11 — memory_graph : client_rw refusé sur MEMORY_B
    print("\n  📋 5.11 — memory_graph MEMORY_B (client_rw, refusé)")
    result = await client_rw.call_tool("memory_graph", {"memory_id": MEMORY_B})
    assert_error(result, "memory_graph MEMORY_B refusé (client_rw)", "refusé")

    # =========================================================================
    # 5.12+ — Enrichissement source_path / repo_path (v3.2.0)
    # =========================================================================
    # Objectif : un agent en incident doit recevoir directement le chemin Git
    # canonique dans memory_search / memory_query, sans document_list complet.
    #
    # Tests DÉTERMINISTES (non complaisants) : la matrice de dérivation est
    # validée via document_get (indépendant du scoring RAG), avec assertions
    # strictes — aucune branche "ok" par défaut quand un cas n'est pas couvert.

    # Marqueur unique → garantit que le RAG retrouve CE document précis (test non complaisant)
    MARKER = "ZZRECETTESOURCEPATH-pgsql01-wal-controlcenter-incident-unique-token"

    def _ingest(content_marker, filename, source_path, marker=""):
        body = (
            f"# {content_marker}\n\n"
            f"{marker} PostgreSQL pgsql01 ne répond plus, saturation WAL, Control Center API renvoie 500. "
            "Index sémantique opérationnel Graph Memory pour Cloud Temple.\n"
        )
        return base64.b64encode(body.encode("utf-8")).decode("ascii")

    # source_path avec préfixe 'repo/' ET un slash de tête → teste aussi la normalisation
    SP_RAW = "/repo/MCO/1.Incidents/inc-recette-source-path/report.md"
    SP_NORM = "repo/MCO/1.Incidents/inc-recette-source-path/report.md"
    REPO_PATH = "MCO/1.Incidents/inc-recette-source-path/report.md"
    # source_path SANS préfixe 'repo/' → repo_path doit être null
    SP_NONREPO = "legal/contracts/cga-recette.md"

    print("\n  📋 5.12 — Ingestion matrice source_path (repo/ + slash, non-repo, legacy)")
    r_repo = await admin.call_tool("memory_ingest", {
        "memory_id": MEMORY_A, "content_base64": _ingest("Incident repo", "report.md",
        SP_RAW, marker=MARKER), "filename": "report.md", "source_path": SP_RAW, "force": True})
    doc_repo = r_repo.get("document_id") if r_repo.get("status") == "ok" else None
    assert_ok(r_repo, "ingest doc repo/ (admin)")

    r_non = await admin.call_tool("memory_ingest", {
        "memory_id": MEMORY_A, "content_base64": _ingest("Contrat CGA", "cga.md", SP_NONREPO),
        "filename": "cga.md", "source_path": SP_NONREPO, "force": True})
    doc_non = r_non.get("document_id") if r_non.get("status") == "ok" else None
    assert_ok(r_non, "ingest doc non-repo (admin)")

    r_leg = await admin.call_tool("memory_ingest", {
        "memory_id": MEMORY_A, "content_base64": _ingest("Doc legacy", "legacy.txt", None),
        "filename": "legacy-recette.txt", "force": True})
    doc_leg = r_leg.get("document_id") if r_leg.get("status") == "ok" else None
    assert_ok(r_leg, "ingest doc legacy sans source_path (admin)")

    # 5.13 — document_get : matrice de dérivation repo_path (déterministe, strict)
    print("\n  📋 5.13 — document_get : matrice source_path/repo_path (déterministe)")
    cases = [
        ("repo/ + slash → normalisé + repo_path", doc_repo, SP_NORM, REPO_PATH),
        ("non-repo → source_path présent, repo_path null", doc_non, SP_NONREPO, None),
        ("legacy → source_path null + repo_path null", doc_leg, None, None),
    ]
    for label, did, exp_sp, exp_repo in cases:
        if not did:
            fail(f"document_get matrice — {label}", "ingestion préalable échouée (doc_id manquant)")
            continue
        res = await client_rw.call_tool("document_get", {"memory_id": MEMORY_A, "document_id": did})
        if not assert_ok(res, f"document_get — {label}"):
            continue
        d = res.get("document", {})
        got_sp, got_repo = d.get("source_path"), d.get("repo_path")
        if got_sp == exp_sp and got_repo == exp_repo:
            ok(f"  → source_path={got_sp!r}, repo_path={got_repo!r}")
        else:
            fail(f"document_get dérivation — {label}",
                 f"attendu source_path={exp_sp!r}/repo_path={exp_repo!r}, reçu {got_sp!r}/{got_repo!r}")
        # Contrat de champs (non complaisant : exiger explicitement les clés)
        missing = [k for k in ("hash", "sha256", "ingestion_status", "chunk_count") if k not in d]
        if missing:
            fail(f"document_get contrat champs — {label}", f"clés manquantes: {missing}")
        else:
            ok("  → contrat champs complet (hash, sha256, ingestion_status, chunk_count)")

    # 5.14 — memory_query : enrichissement effectif dans source_documents ET rag_chunks
    # Requête sur le MARQUEUR UNIQUE → le doc repo/ doit remonter de façon déterministe.
    print("\n  📋 5.14 — memory_query expose source_path/repo_path (source_documents + rag_chunks)")
    result = await client_rw.call_tool("memory_query", {
        "memory_id": MEMORY_A,
        "query": f"{MARKER} incident PostgreSQL pgsql saturation WAL Control Center API 500",
    })
    if assert_ok(result, "memory_query (enrichissement source_path)"):
        src_docs = result.get("source_documents", [])
        # Strict : le doc repo/ DOIT être présent par ID et porter source_path normalisé + repo_path
        doc = next((d for d in src_docs if d.get("id") == doc_repo), None)
        if doc is None:
            fail("source_documents contient le doc repo/ par ID", f"doc {doc_repo} introuvable")
        elif doc.get("source_path") == SP_NORM and doc.get("repo_path") == REPO_PATH:
            ok(f"  → source_documents[{doc_repo[:8]}…]: source_path/repo_path corrects")
        else:
            fail("source_documents.source_path/repo_path",
                 f"reçu source_path={doc.get('source_path')!r}, repo_path={doc.get('repo_path')!r}")

        # Non complaisant : source_documents non vide + TOUS exposent les clés du contrat
        contract = ("source_path", "repo_path", "hash", "sha256", "ingestion_status")
        if not src_docs:
            fail("source_documents non vide", "aucun document source retourné pour le marqueur unique")
        else:
            bad = [d.get("id", "?")[:8] for d in src_docs if any(k not in d for k in contract)]
            if bad:
                fail("source_documents contrat de clés", f"docs incomplets: {bad}")
            else:
                ok(f"  → {len(src_docs)} source_document(s) exposent toutes les clés du contrat")

        # Non complaisant : rag_chunks NON VIDE (marqueur unique) + chunk du doc repo/ présent et correct
        rag = result.get("rag_chunks", [])
        if not rag:
            fail("rag_chunks non vide", "aucun chunk RAG retourné pour le marqueur unique")
        else:
            bad_chunks = [c.get("doc_id", "?") for c in rag
                          if "source_path" not in c or "repo_path" not in c]
            if bad_chunks:
                fail("rag_chunks clés source_path/repo_path", f"chunks sans les clés: {bad_chunks}")
            else:
                ok(f"  → {len(rag)} rag_chunk(s) exposent source_path + repo_path")
            repo_chunks = [c for c in rag if c.get("doc_id") == doc_repo]
            if not repo_chunks:
                fail("rag_chunks du doc repo/", "aucun chunk du doc repo/ retourné malgré le marqueur unique")
            elif all(c.get("source_path") == SP_NORM and c.get("repo_path") == REPO_PATH for c in repo_chunks):
                ok(f"  → {len(repo_chunks)} rag_chunk(s) du doc repo/ avec chemins corrects")
            else:
                fail("rag_chunks du doc repo/", "source_path/repo_path incorrect sur au moins un chunk")

    # 5.15 — memory_search : les documents liés exposent aussi source_path/repo_path (P1)
    print("\n  📋 5.15 — memory_search expose source_path/repo_path dans les documents liés")
    result = await client_rw.call_tool("memory_search", {
        "memory_id": MEMORY_A, "query": "PostgreSQL Control Center Cloud Temple",
    })
    if assert_ok(result, "memory_search (enrichissement source_path)"):
        all_docs = [d for r in result.get("results", []) for d in r.get("documents", [])]
        if not all_docs:
            fail("memory_search documents non vide", "aucun document lié retourné (entités non trouvées ?)")
        else:
            # Structural (non complaisant) : TOUT document lié expose source_path ET repo_path
            bad = [d.get("id", "?")[:8] for d in all_docs
                   if "source_path" not in d or "repo_path" not in d]
            if bad:
                fail("memory_search contrat source_path/repo_path", f"docs sans les clés: {bad}")
            else:
                ok(f"  → {len(all_docs)} document(s) lié(s) exposent source_path + repo_path")
            # Si notre doc repo/ est lié, vérifier la valeur exacte
            d_repo = next((d for d in all_docs if d.get("id") == doc_repo), None)
            if d_repo is not None:
                if d_repo.get("source_path") == SP_NORM and d_repo.get("repo_path") == REPO_PATH:
                    ok("  → doc repo/ trouvé via memory_search avec chemins corrects")
                else:
                    fail("memory_search doc repo/",
                         f"reçu source_path={d_repo.get('source_path')!r}, repo_path={d_repo.get('repo_path')!r}")
