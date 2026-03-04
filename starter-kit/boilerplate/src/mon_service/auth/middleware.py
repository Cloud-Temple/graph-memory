# -*- coding: utf-8 -*-
"""
Middlewares ASGI : authentification, logging.

Pile d'exécution (ordre) :
    AuthMiddleware → LoggingMiddleware → mcp.streamable_http_app()
"""

import sys
import time
import hashlib
from typing import Optional
from .context import current_token_info
from ..config import get_settings


class AuthMiddleware:
    """
    Middleware ASGI d'authentification par Bearer token.

    - Extrait le token du header Authorization
    - Compare le hash SHA-256 avec le bootstrap key (ou un store externe)
    - Injecte les infos du token dans les contextvars
    - Les routes publiques (/health, etc.) passent sans token
    """

    # Routes qui ne nécessitent pas d'authentification
    PUBLIC_PATHS = {"/health", "/favicon.ico"}

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)

        path = scope.get("path", "")

        # Routes publiques → pas d'auth
        if path in self.PUBLIC_PATHS:
            return await self.app(scope, receive, send)

        # Extraire le Bearer token
        token = self._extract_token(scope)
        token_info = None

        if token:
            token_info = self._validate_token(token)

        # Injecter dans le contextvar (même si None → les outils vérifieront)
        tok = current_token_info.set(token_info)
        try:
            await self.app(scope, receive, send)
        finally:
            current_token_info.reset(tok)

    def _extract_token(self, scope) -> Optional[str]:
        """Extrait le token depuis le header Authorization ou query string."""
        headers = dict(scope.get("headers", []))
        auth = headers.get(b"authorization", b"").decode()
        if auth.startswith("Bearer "):
            return auth[7:]

        # Fallback: query string ?token=xxx (pour SSE dans les navigateurs)
        qs = scope.get("query_string", b"").decode()
        for param in qs.split("&"):
            if param.startswith("token="):
                return param[6:]
        return None

    def _validate_token(self, token: str) -> Optional[dict]:
        """
        Valide un token et retourne ses infos.

        Version simple : compare avec le bootstrap key.
        Pour un vrai système, connecter à un store de tokens (DB, Redis, etc.).
        """
        settings = get_settings()

        # Bootstrap key → admin total
        if token == settings.admin_bootstrap_key:
            return {
                "client_name": "admin",
                "permissions": ["admin", "read", "write"],
                "allowed_resources": [],  # vide = accès total
            }

        # TODO: Ajouter ici la validation depuis un store de tokens
        # token_hash = hashlib.sha256(token.encode()).hexdigest()
        # token_info = token_store.get_by_hash(token_hash)
        # if token_info and not token_info.revoked:
        #     return token_info.to_dict()

        return None  # Token invalide


class LoggingMiddleware:
    """
    Middleware ASGI de logging des requêtes HTTP.

    Log sur stderr : méthode, path, status, durée.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        path = scope.get("path", "")
        method = scope.get("method", "?")
        t0 = time.monotonic()
        status_code = 0

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message.get("status", 0)
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            elapsed = round((time.monotonic() - t0) * 1000, 1)
            # Ne pas logger les health checks pour éviter le bruit
            if path not in ("/health",):
                print(
                    f"📡 {method} {path} → {status_code} ({elapsed}ms)",
                    file=sys.stderr,
                )


# NOTE: HostNormalizerMiddleware supprimé — inutile avec Streamable HTTP.
