# -*- coding: utf-8 -*-
"""Tests suppression : memory_delete avec isolation + nettoyage final."""

from . import (MCPClient, MEMORY_A, MEMORY_B, MEMORY_C,
               assert_ok, assert_error, ok, fail, phase_header)


async def run(admin: MCPClient, client_rw: MCPClient, client_ro: MCPClient, **ctx):
    """Phase Nettoyage — Suppression mémoires avec isolation + cleanup tokens."""
    tokens = ctx.get("tokens", {})
    phase_header(7, "Suppression mémoires + nettoyage", "🧹")

    # 7.1 — client_rw ne peut PAS supprimer MEMORY_B (pas sa mémoire)
    print("\n  📋 7.1 — memory_delete MEMORY_B (client_rw, refusé)")
    result = await client_rw.call_tool("memory_delete", {"memory_id": MEMORY_B})
    assert_error(result, "memory_delete MEMORY_B refusé (client_rw)", "refusé")

    # 7.2 — client_ro ne peut PAS supprimer MEMORY_B (read-only)
    print("\n  📋 7.2 — memory_delete MEMORY_B (client_ro, refusé write)")
    result = await client_ro.call_tool("memory_delete", {"memory_id": MEMORY_B})
    status = result.get("status", "")
    if status == "deleted":
        fail("memory_delete MEMORY_B (client_ro)", "READ-ONLY A PU SUPPRIMER !")
    else:
        ok("memory_delete MEMORY_B refusé (client_ro, read-only)")

    # 7.3 — client_rw supprime MEMORY_A (sa mémoire, OK)
    print("\n  📋 7.3 — memory_delete MEMORY_A (client_rw, OK)")
    result = await client_rw.call_tool("memory_delete", {"memory_id": MEMORY_A})
    assert_ok(result, "memory_delete MEMORY_A (client_rw)")

    # 7.4 — client_rw supprime MEMORY_C (auto-ajoutée, OK)
    print("\n  📋 7.4 — memory_delete MEMORY_C (client_rw, OK)")
    result = await client_rw.call_tool("memory_delete", {"memory_id": MEMORY_C})
    assert_ok(result, "memory_delete MEMORY_C (client_rw)")

    # 7.5 — admin supprime MEMORY_B
    print("\n  📋 7.5 — memory_delete MEMORY_B (admin)")
    result = await admin.call_tool("memory_delete", {"memory_id": MEMORY_B})
    assert_ok(result, "memory_delete MEMORY_B (admin)")

    # 7.6 — Vérifier que les mémoires sont bien supprimées
    print("\n  📋 7.6 — Vérification post-suppression")
    result = await admin.call_tool("memory_list", {})
    if assert_ok(result, "memory_list post-cleanup"):
        ids = [m["id"] for m in result.get("memories", [])]
        for mid in [MEMORY_A, MEMORY_B, MEMORY_C]:
            if mid not in ids:
                ok(f"  → {mid} supprimé ✓")
            else:
                fail(f"  → {mid} encore présent !")

    # 7.7 — Révoquer les tokens de test
    print("\n  📋 7.7 — Révocation des tokens de test")
    for name, info in tokens.items():
        prefix = info.get("hash_prefix", "")
        if prefix:
            result = await admin.call_tool("admin_revoke_token", {
                "token_hash_prefix": prefix
            })
            s = result.get("status", result.get("message", "?"))
            print(f"  🔑 Token {name}: {s}")
