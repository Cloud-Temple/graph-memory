# -*- coding: utf-8 -*-
"""Tests backup/storage : backup CRUD, storage_check, storage_cleanup + isolation."""

from . import (MCPClient, MEMORY_A, MEMORY_B,
               assert_ok, assert_error, ok, fail, skip, phase_header)


async def run(admin: MCPClient, client_rw: MCPClient, client_ro: MCPClient, **ctx):
    """Phase Backup & Storage — CRUD backup, check/cleanup, isolation."""
    phase_header(6, "Backup & Storage — CRUD + isolation", "💾")

    backup_id_a = None

    # === BACKUP ===

    # 6.1 — backup_create : client_rw sur MEMORY_A (OK)
    print("\n  📋 6.1 — backup_create MEMORY_A (client_rw, OK)")
    result = await client_rw.call_tool("backup_create", {
        "memory_id": MEMORY_A, "description": "Recette backup"
    })
    if assert_ok(result, "backup_create MEMORY_A (client_rw)"):
        backup_id_a = result.get("backup_id")
        ok(f"  → backup_id: {backup_id_a}")

    # 6.2 — backup_create : client_rw refusé sur MEMORY_B
    print("\n  📋 6.2 — backup_create MEMORY_B (client_rw, refusé)")
    result = await client_rw.call_tool("backup_create", {
        "memory_id": MEMORY_B, "description": "Hack"
    })
    assert_error(result, "backup_create MEMORY_B refusé (client_rw)", "refusé")

    # 6.3 — backup_create : client_ro refusé (read-only)
    print("\n  📋 6.3 — backup_create MEMORY_B (client_ro, refusé write)")
    result = await client_ro.call_tool("backup_create", {
        "memory_id": MEMORY_B, "description": "Test"
    })
    assert_error(result, "backup_create refusé (read-only)")

    # 6.4 — backup_list : client_rw voit seulement ses backups
    print("\n  📋 6.4 — backup_list (client_rw, filtré)")
    result = await client_rw.call_tool("backup_list", {})
    if assert_ok(result, "backup_list (client_rw)"):
        mids = [b.get("memory_id") for b in result.get("backups", [])]
        if MEMORY_B not in mids:
            ok("  → Ne voit PAS les backups de MEMORY_B ✓")
        else:
            fail("  → Ne devrait PAS voir MEMORY_B")

    # 6.5 — backup_list par mémoire spécifique
    print("\n  📋 6.5 — backup_list MEMORY_A (client_rw, OK)")
    result = await client_rw.call_tool("backup_list", {"memory_id": MEMORY_A})
    if assert_ok(result, "backup_list MEMORY_A"):
        count = result.get("count", 0)
        ok(f"  → {count} backup(s)")

    # 6.6 — backup_list : client_rw refusé sur MEMORY_B
    print("\n  📋 6.6 — backup_list MEMORY_B (client_rw, refusé)")
    result = await client_rw.call_tool("backup_list", {"memory_id": MEMORY_B})
    assert_error(result, "backup_list MEMORY_B refusé (client_rw)", "refusé")

    # 6.7 — backup_list : admin voit tout
    print("\n  📋 6.7 — backup_list (admin, voit tout)")
    result = await admin.call_tool("backup_list", {})
    assert_ok(result, "backup_list (admin)")

    # 6.8 — backup_delete : client_rw OK sur son backup
    if backup_id_a:
        print("\n  📋 6.8 — backup_delete (client_rw, OK)")
        result = await client_rw.call_tool("backup_delete", {"backup_id": backup_id_a})
        assert_ok(result, "backup_delete (client_rw)")
    else:
        skip("6.8 — backup_delete", "pas de backup_id")

    # === STORAGE ===

    # 6.9 — storage_check global : client_rw refusé (admin only)
    print("\n  📋 6.9 — storage_check global (client_rw, refusé)")
    result = await client_rw.call_tool("storage_check", {})
    assert_error(result, "storage_check global refusé (non-admin)", "admin")

    # 6.10 — storage_check spécifique : client_rw OK sur sa mémoire
    print("\n  📋 6.10 — storage_check MEMORY_A (client_rw, OK)")
    result = await client_rw.call_tool("storage_check", {"memory_id": MEMORY_A})
    if assert_ok(result, "storage_check MEMORY_A (client_rw)"):
        summary = result.get("summary", "")
        ok(f"  → {summary[:60]}")

    # 6.11 — storage_check spécifique : client_rw refusé sur MEMORY_B
    print("\n  📋 6.11 — storage_check MEMORY_B (client_rw, refusé)")
    result = await client_rw.call_tool("storage_check", {"memory_id": MEMORY_B})
    assert_error(result, "storage_check MEMORY_B refusé (client_rw)", "refusé")

    # 6.12 — storage_check global : admin OK
    print("\n  📋 6.12 — storage_check global (admin, OK)")
    result = await admin.call_tool("storage_check", {})
    if assert_ok(result, "storage_check global (admin)"):
        summary = result.get("summary", "")
        ok(f"  → {summary[:60]}")

    # 6.13 — storage_cleanup : client_rw refusé (admin only)
    print("\n  📋 6.13 — storage_cleanup (client_rw, refusé)")
    result = await client_rw.call_tool("storage_cleanup", {"dry_run": True})
    assert_error(result, "storage_cleanup refusé (non-admin)", "admin")

    # 6.14 — storage_cleanup : admin OK (dry_run)
    print("\n  📋 6.14 — storage_cleanup dry_run (admin, OK)")
    result = await admin.call_tool("storage_cleanup", {"dry_run": True})
    assert_ok(result, "storage_cleanup dry_run (admin)")
