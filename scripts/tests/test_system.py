# -*- coding: utf-8 -*-
"""Tests système : system_health, system_about, ontology_list."""

from . import MCPClient, assert_ok, assert_field, ok, fail, phase_header


async def run(admin: MCPClient, client_rw: MCPClient, client_ro: MCPClient, **ctx):
    """Phase Système — Vérifie les outils publics accessibles à tous."""
    phase_header(1, "Système (health, about, ontology)", "🌐")

    # 1.1 — system_health (admin)
    print("\n  📋 1.1 — system_health (admin)")
    result = await admin.call_tool("system_health", {})
    status = result.get("status", "")
    if status in ("ok", "error"):  # error OK si services pas tous up
        ok("system_health (admin)")
        services = result.get("services", {})
        for svc, info in services.items():
            s = info.get("status", "?") if isinstance(info, dict) else info
            ok(f"  → {svc}: {s}")
    else:
        fail("system_health", f"status={status}")

    # 1.2 — system_health depuis un client non-admin (public)
    print("\n  📋 1.2 — system_health (client_rw, public)")
    result = await client_rw.call_tool("system_health", {})
    if result.get("status") in ("ok", "error"):
        ok("system_health accessible par client_rw")
    else:
        fail("system_health accessible par client_rw")

    # 1.3 — system_about (admin)
    print("\n  📋 1.3 — system_about (admin)")
    result = await admin.call_tool("system_about", {})
    if assert_ok(result, "system_about (admin)"):
        assert_field(result, "identity", "  → identity présent")
        assert_field(result, "capabilities", "  → capabilities présent")
        assert_field(result, "services", "  → services présent")
        # Vérifier la version
        identity = result.get("identity", {})
        version = identity.get("version", "?")
        ok(f"  → version: {version}")

    # 1.4 — system_about depuis un client read-only (public)
    print("\n  📋 1.4 — system_about (client_ro, public)")
    result = await client_ro.call_tool("system_about", {})
    assert_ok(result, "system_about accessible par client_ro")

    # 1.5 — ontology_list
    print("\n  📋 1.5 — ontology_list (admin)")
    result = await admin.call_tool("ontology_list", {})
    if assert_ok(result, "ontology_list"):
        count = result.get("count", 0)
        ok(f"  → {count} ontologies disponibles")
        names = [o.get("name", "?") for o in result.get("ontologies", [])]
        if "general" in names:
            ok("  → ontologie 'general' présente")
        else:
            fail("  → ontologie 'general' manquante", f"Trouvées: {names}")

    # 1.6 — ontology_list depuis un client non-admin (public)
    print("\n  📋 1.6 — ontology_list (client_rw, public)")
    result = await client_rw.call_tool("ontology_list", {})
    assert_ok(result, "ontology_list accessible par client_rw")
