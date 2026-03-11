# -*- coding: utf-8 -*-
"""Tests mémoires : CRUD, isolation multi-tenant, auto-ajout au token."""

from . import (MCPClient, MEMORY_A, MEMORY_B, MEMORY_C,
               assert_ok, assert_error, ok, fail, skip, phase_header)


async def run(admin: MCPClient, client_rw: MCPClient, client_ro: MCPClient, **ctx):
    """Phase Mémoires — CRUD et isolation."""
    phase_header(3, "Mémoires — CRUD + isolation", "🧠")

    # 3.1 — Admin crée MEMORY_B (pour client_ro)
    print("\n  📋 3.1 — Admin crée MEMORY_B")
    result = await admin.call_tool("memory_create", {
        "memory_id": MEMORY_B, "name": "Test B", "ontology": "general"
    })
    assert_ok(result, "memory_create MEMORY_B (admin)")

    # 3.2 — client_rw crée MEMORY_A (dans sa liste → OK)
    print("\n  📋 3.2 — client_rw crée MEMORY_A (auto-ajout au token)")
    result = await client_rw.call_tool("memory_create", {
        "memory_id": MEMORY_A, "name": "Test A", "ontology": "general"
    })
    assert_ok(result, "memory_create MEMORY_A (client_rw)")

    # 3.3 — client_rw crée MEMORY_C (hors liste → auto-ajout)
    print("\n  📋 3.3 — client_rw crée MEMORY_C (hors liste initiale → auto-ajout)")
    result = await client_rw.call_tool("memory_create", {
        "memory_id": MEMORY_C, "name": "Test C", "ontology": "general"
    })
    assert_ok(result, "memory_create MEMORY_C (auto-ajout)")

    # 3.4 — client_ro ne peut PAS créer de mémoire (read-only)
    print("\n  📋 3.4 — client_ro ne peut PAS créer (read-only)")
    result = await client_ro.call_tool("memory_create", {
        "memory_id": "HACK", "name": "Hack", "ontology": "general"
    })
    assert_error(result, "memory_create refusé (read-only)")

    # 3.5 — memory_list : client_rw voit A et C, PAS B
    print("\n  📋 3.5 — memory_list isolation (client_rw)")
    result = await client_rw.call_tool("memory_list", {})
    if assert_ok(result, "memory_list (client_rw)"):
        ids = [m["id"] for m in result.get("memories", [])]
        if MEMORY_A in ids and MEMORY_C in ids:
            ok("  → Voit MEMORY_A et MEMORY_C")
        else:
            fail("  → Devrait voir A et C", f"Vu: {ids}")
        if MEMORY_B not in ids:
            ok("  → Ne voit PAS MEMORY_B ✓")
        else:
            fail("  → Ne devrait PAS voir B")

    # 3.6 — memory_list : client_ro voit uniquement B
    print("\n  📋 3.6 — memory_list isolation (client_ro)")
    result = await client_ro.call_tool("memory_list", {})
    if assert_ok(result, "memory_list (client_ro)"):
        ids = [m["id"] for m in result.get("memories", [])]
        if MEMORY_B in ids:
            ok("  → Voit MEMORY_B")
        else:
            fail("  → Devrait voir B")
        if MEMORY_A not in ids and MEMORY_C not in ids:
            ok("  → Ne voit PAS A ni C ✓")
        else:
            fail("  → Ne devrait pas voir A ou C")

    # 3.7 — memory_list : admin voit tout
    print("\n  📋 3.7 — memory_list (admin, voit tout)")
    result = await admin.call_tool("memory_list", {})
    if assert_ok(result, "memory_list (admin)"):
        ids = [m["id"] for m in result.get("memories", [])]
        for mid in [MEMORY_A, MEMORY_B, MEMORY_C]:
            if mid in ids:
                ok(f"  → Admin voit {mid}")
            else:
                fail(f"  → Admin devrait voir {mid}")

    # 3.8 — memory_stats : client_rw OK sur sa mémoire
    print("\n  📋 3.8 — memory_stats MEMORY_A (client_rw, OK)")
    result = await client_rw.call_tool("memory_stats", {"memory_id": MEMORY_A})
    assert_ok(result, "memory_stats MEMORY_A (client_rw)")

    # 3.9 — memory_stats : client_rw refusé sur B
    print("\n  📋 3.9 — memory_stats MEMORY_B (client_rw, refusé)")
    result = await client_rw.call_tool("memory_stats", {"memory_id": MEMORY_B})
    assert_error(result, "memory_stats MEMORY_B refusé (client_rw)", "refusé")

    # 3.10 — memory_stats : client_ro refusé sur A
    print("\n  📋 3.10 — memory_stats MEMORY_A (client_ro, refusé)")
    result = await client_ro.call_tool("memory_stats", {"memory_id": MEMORY_A})
    assert_error(result, "memory_stats MEMORY_A refusé (client_ro)", "refusé")
