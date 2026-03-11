# -*- coding: utf-8 -*-
"""Tests recherche : memory_search, question_answer, memory_query, memory_get_context, memory_graph."""

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
