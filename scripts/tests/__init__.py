# -*- coding: utf-8 -*-
"""
Framework de test pour la recette graph-memory.

Fournit les helpers, compteurs et configuration partagés par tous les modules de test.
"""

import base64
import os
import sys

# Ajouter le dossier parent pour les imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from scripts.cli.client import MCPClient, ServerNotRunningError

# =============================================================================
# Configuration
# =============================================================================

MCP_URL = os.environ.get("MCP_URL", "http://localhost:8002")
ADMIN_TOKEN = os.environ.get("MCP_TOKEN", "")

# Mémoires de test
MEMORY_A = "TEST-RECETTE-A"
MEMORY_B = "TEST-RECETTE-B"
MEMORY_C = "TEST-RECETTE-C"

# =============================================================================
# Compteurs globaux
# =============================================================================

_passed = 0
_failed = 0
_skipped = 0
_errors = []


def reset_counters():
    """Remet les compteurs à zéro."""
    global _passed, _failed, _skipped, _errors
    _passed = 0
    _failed = 0
    _skipped = 0
    _errors = []


def get_counters() -> dict:
    """Retourne les compteurs."""
    return {"passed": _passed, "failed": _failed, "skipped": _skipped, "errors": _errors}


# =============================================================================
# Helpers d'assertion
# =============================================================================

def ok(test_name: str, detail: str = ""):
    """Marque un test comme réussi."""
    global _passed
    _passed += 1
    suffix = f" — {detail}" if detail else ""
    print(f"  ✅ {test_name}{suffix}")


def fail(test_name: str, detail: str = ""):
    """Marque un test comme échoué."""
    global _failed
    _failed += 1
    suffix = f" — {detail}" if detail else ""
    msg = f"  ❌ {test_name}{suffix}"
    print(msg)
    _errors.append(msg)


def skip(test_name: str, detail: str = ""):
    """Marque un test comme ignoré."""
    global _skipped
    _skipped += 1
    suffix = f" — {detail}" if detail else ""
    print(f"  ⏭️  {test_name}{suffix}")


def assert_ok(result: dict, test_name: str) -> bool:
    """Vérifie que le résultat est un succès."""
    status = result.get("status", "")
    if status in ("ok", "created", "deleted"):
        ok(test_name)
        return True
    fail(test_name, f"status={status}, msg={result.get('message', '?')}")
    return False


def assert_error(result: dict, test_name: str, expected_msg_part: str = "") -> bool:
    """Vérifie que le résultat est une erreur (accès refusé attendu)."""
    status = result.get("status", "")
    msg = result.get("message", "")
    if status == "error":
        if expected_msg_part and expected_msg_part.lower() not in msg.lower():
            fail(test_name, f"Erreur inattendue: {msg}")
            return False
        ok(test_name, f"Refusé: {msg[:80]}")
        return True
    fail(test_name, f"Attendu: erreur, obtenu: status={status}")
    return False


def assert_field(result: dict, field: str, test_name: str) -> bool:
    """Vérifie qu'un champ existe et n'est pas vide dans le résultat."""
    val = result.get(field)
    if val is not None and val != "" and val != []:
        ok(test_name, f"{field}={str(val)[:60]}")
        return True
    fail(test_name, f"Champ '{field}' manquant ou vide")
    return False


def make_test_doc(content: str = "Cloud Temple est un fournisseur cloud souverain français. "
                  "Il propose des services IaaS, PaaS et SaaS certifiés SecNumCloud.") -> str:
    """Crée un document de test encodé en base64."""
    return base64.b64encode(content.encode("utf-8")).decode("ascii")


def phase_header(num: int, title: str, emoji: str = "📋"):
    """Affiche un header de phase."""
    print(f"\n{'=' * 70}")
    print(f"{emoji} PHASE {num} : {title}")
    print("=" * 70)
