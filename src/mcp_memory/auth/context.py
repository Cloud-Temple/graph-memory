# -*- coding: utf-8 -*-
"""
Auth Context - Propagation du contexte d'authentification.

Utilise contextvars pour propager les infos d'auth du middleware ASGI
vers les outils MCP (qui n'ont pas accès au scope ASGI).

Usage dans le middleware:
    from .context import current_auth
    current_auth.set({"client_name": "quoteflow", "memory_ids": ["JURIDIQUE"]})

Usage dans les outils:
    from .auth.context import current_auth
    auth = current_auth.get()  # None si pas d'auth (localhost, public paths)
"""

import contextvars
from typing import Optional, Dict, Any

# ContextVar initialisé à None (pas d'auth = accès libre, cas localhost)
current_auth: contextvars.ContextVar[Optional[Dict[str, Any]]] = contextvars.ContextVar(
    'current_auth', default=None
)


def check_memory_access(memory_id: str) -> Optional[dict]:
    """
    Vérifie si le contexte d'auth actuel autorise l'accès à une mémoire.
    
    Règles :
    - Pas d'auth (localhost, public) → autorisé
    - Auth avec memory_ids vide → accès à toutes les mémoires
    - Auth avec memory_ids renseigné → accès restreint
    - Permission "admin" → toujours autorisé
    
    Args:
        memory_id: ID de la mémoire à vérifier
        
    Returns:
        None si autorisé, dict d'erreur si refusé
    """
    auth = current_auth.get()
    
    # Pas d'auth = accès libre (localhost, endpoints publics)
    if auth is None:
        return None
    
    # Admin = accès total
    if "admin" in auth.get("permissions", []):
        return None
    
    # Bootstrap key = accès total
    if auth.get("type") == "bootstrap":
        return None
    
    # memory_ids vide = accès à toutes les mémoires
    memory_ids = auth.get("memory_ids", [])
    if not memory_ids:
        return None
    
    # Vérifier que la mémoire est dans la liste autorisée
    if memory_id not in memory_ids:
        client = auth.get("client_name", "inconnu")
        return {
            "status": "error",
            "message": (
                f"Accès refusé: le token du client '{client}' "
                f"n'est pas autorisé pour la mémoire '{memory_id}'. "
                f"Mémoires autorisées: {memory_ids}"
            )
        }
    
    return None  # Autorisé


def check_admin_permission() -> Optional[dict]:
    """
    Vérifie si le contexte d'auth actuel a la permission admin.
    
    Règles :
    - Pas d'auth (localhost, public) → autorisé (accès libre)
    - Permission "admin" → autorisé
    - Bootstrap key → autorisé
    - Sinon → refusé
    
    Returns:
        None si autorisé, dict d'erreur si refusé
    """
    auth = current_auth.get()
    
    # Pas d'auth = accès libre (localhost)
    if auth is None:
        return None
    
    # Bootstrap = admin
    if auth.get("type") == "bootstrap":
        return None
    
    permissions = auth.get("permissions", [])
    if "admin" in permissions:
        return None
    
    client = auth.get("client_name", "inconnu")
    return {
        "status": "error",
        "message": (
            f"Accès refusé: le token du client '{client}' "
            f"n'a pas la permission 'admin'. "
            f"Cette opération est réservée aux administrateurs."
        )
    }


def get_allowed_memory_ids() -> Optional[list]:
    """
    Retourne la liste des memory_ids autorisés pour le contexte d'auth actuel.
    
    Returns:
        None si pas d'auth ou admin/bootstrap (= pas de restriction)
        [] si memory_ids vide dans le token (= toutes les mémoires autorisées)
        ["A", "B"] si restriction à des mémoires spécifiques
    """
    auth = current_auth.get()
    
    # Pas d'auth = accès libre
    if auth is None:
        return None
    
    # Admin ou bootstrap = accès total (pas de filtrage)
    if auth.get("type") == "bootstrap":
        return None
    if "admin" in auth.get("permissions", []):
        return None
    
    # Retourner la liste (peut être [] = toutes)
    return auth.get("memory_ids", [])


def check_write_permission() -> Optional[dict]:
    """
    Vérifie si le contexte d'auth actuel a la permission d'écriture.
    
    Règles :
    - Pas d'auth (localhost, public) → autorisé (accès libre)
    - Permission "admin" ou "write" → autorisé
    - Bootstrap key → autorisé
    - Sinon → refusé
    
    Returns:
        None si autorisé, dict d'erreur si refusé
    """
    auth = current_auth.get()
    
    # Pas d'auth = accès libre (localhost)
    if auth is None:
        return None
    
    # Admin ou bootstrap = accès total
    if auth.get("type") == "bootstrap":
        return None
    
    permissions = auth.get("permissions", [])
    if "admin" in permissions or "write" in permissions:
        return None
    
    client = auth.get("client_name", "inconnu")
    return {
        "status": "error",
        "message": (
            f"Accès refusé: le token du client '{client}' "
            f"n'a pas la permission 'write'. "
            f"Permissions actuelles: {permissions}"
        )
    }
