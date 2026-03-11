# -*- coding: utf-8 -*-
"""Tests tokens : CRUD admin, isolation non-admin, promotion admin."""

from . import (MCPClient, assert_ok, assert_error, assert_field,
               ok, fail, skip, phase_header)


async def run(admin: MCPClient, client_rw: MCPClient, client_ro: MCPClient, **ctx):
    """Phase Tokens — CRUD, isolation, promotion admin."""
    tokens = ctx.get("tokens", {})
    phase_header(2, "Tokens — CRUD admin + isolation + promotion", "🔑")

    # === 2.1 : Création de tokens (admin) ===
    print("\n  📋 2.1 — admin_create_token : créer un token admin délégué")
    result = await admin.call_tool("admin_create_token", {
        "client_name": "test-admin-delegue",
        "permissions": ["admin", "read", "write"],
        "memory_ids": [],
        "email": "admin-delegue@example.com"
    })
    delegated_admin_token = None
    delegated_admin_hash = None
    if assert_ok(result, "admin_create_token (admin délégué)"):
        delegated_admin_token = result.get("token")
        perms = result.get("permissions", [])
        if "admin" in perms:
            ok("  → Permission admin présente")
        else:
            fail("  → Permission admin manquante", f"perms={perms}")

    # === 2.2 : Lister les tokens (admin) ===
    print("\n  📋 2.2 — admin_list_tokens")
    result = await admin.call_tool("admin_list_tokens", {})
    if assert_ok(result, "admin_list_tokens"):
        count = result.get("count", 0)
        ok(f"  → {count} tokens actifs")
        # Récupérer le hash du token délégué
        for t in result.get("tokens", []):
            if t.get("client_name") == "test-admin-delegue":
                delegated_admin_hash = t["token_hash"][:12]

    # === 2.3 : Token admin délégué peut créer un token ===
    if delegated_admin_token:
        print("\n  📋 2.3 — Token admin délégué crée un sous-token")
        delegated = MCPClient(admin.base_url, delegated_admin_token)
        result = await delegated.call_tool("admin_create_token", {
            "client_name": "test-sous-token",
            "permissions": ["read"],
            "memory_ids": [],
        })
        if assert_ok(result, "admin_create_token via token admin délégué"):
            ok("  → Chaîne de confiance : bootstrap → admin → sous-token ✓")
            # Révoquer le sous-token
            sub_hash = None
            r2 = await delegated.call_tool("admin_list_tokens", {})
            for t in r2.get("tokens", []):
                if t.get("client_name") == "test-sous-token":
                    sub_hash = t["token_hash"][:12]
            if sub_hash:
                await delegated.call_tool("admin_revoke_token", {"token_hash_prefix": sub_hash})
    else:
        skip("2.3 — Token admin délégué", "pas de token")

    # === 2.4 : Promotion d'un token existant en admin ===
    rw_hash = tokens.get("client_rw", {}).get("hash_prefix", "")
    if rw_hash:
        print("\n  📋 2.4 — admin_update_token : promouvoir client_rw en admin")
        result = await admin.call_tool("admin_update_token", {
            "token_hash_prefix": rw_hash,
            "set_permissions": ["admin", "read", "write"]
        })
        if assert_ok(result, "admin_update_token (promotion admin)"):
            perms = result.get("current_permissions", [])
            if "admin" in perms:
                ok("  → Promotion admin confirmée")
            else:
                fail("  → Promotion admin échouée", f"perms={perms}")
        
        # Rétrograder
        print("\n  📋 2.4b — admin_update_token : rétrograder client_rw en read+write")
        result = await admin.call_tool("admin_update_token", {
            "token_hash_prefix": rw_hash,
            "set_permissions": ["read", "write"]
        })
        if assert_ok(result, "admin_update_token (rétrogradation)"):
            perms = result.get("current_permissions", [])
            if "admin" not in perms:
                ok("  → Rétrogradation confirmée")
            else:
                fail("  → Rétrogradation échouée")
    else:
        skip("2.4 — Promotion/rétrogradation", "pas de hash_prefix")

    # === 2.5 : Isolation — client non-admin ne peut PAS gérer les tokens ===
    print("\n  📋 2.5 — Isolation : client_rw ne peut PAS utiliser admin_create_token")
    result = await client_rw.call_tool("admin_create_token", {
        "client_name": "hacker", "permissions": ["admin"]
    })
    assert_error(result, "admin_create_token refusé (non-admin)", "admin")

    print("\n  📋 2.6 — Isolation : client_rw ne peut PAS lister les tokens")
    result = await client_rw.call_tool("admin_list_tokens", {})
    assert_error(result, "admin_list_tokens refusé (non-admin)", "admin")

    print("\n  📋 2.7 — Isolation : client_rw ne peut PAS révoquer")
    result = await client_rw.call_tool("admin_revoke_token", {"token_hash_prefix": "00000000"})
    assert_error(result, "admin_revoke_token refusé (non-admin)", "admin")

    print("\n  📋 2.8 — Isolation : client_rw ne peut PAS update")
    result = await client_rw.call_tool("admin_update_token", {
        "token_hash_prefix": "00000000", "set_permissions": ["admin"]
    })
    assert_error(result, "admin_update_token refusé (non-admin)", "admin")

    print("\n  📋 2.9 — Isolation : client_ro ne peut PAS créer de token")
    result = await client_ro.call_tool("admin_create_token", {
        "client_name": "hack", "permissions": ["read"]
    })
    assert_error(result, "admin_create_token refusé (read-only)", "admin")

    # === Nettoyage : révoquer le token admin délégué ===
    if delegated_admin_hash:
        await admin.call_tool("admin_revoke_token", {"token_hash_prefix": delegated_admin_hash})
        print(f"  🧹 Token admin délégué révoqué")
