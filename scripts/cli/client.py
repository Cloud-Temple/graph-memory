# -*- coding: utf-8 -*-
"""
MCPClient - Communication avec le serveur MCP Memory.

Deux modes de communication :
  - REST : pour les endpoints simples (health, list, graph)
  - Streamable HTTP/MCP : pour appeler les outils MCP (ingest, delete, search...)

Gestion des erreurs de connexion :
  - Si le serveur est injoignable, lève ServerNotRunningError
  - Le message indique comment démarrer le serveur (docker compose up -d)
"""

import json
from typing import Dict, Any


class ServerNotRunningError(Exception):
    """Levée quand le serveur MCP n'est pas accessible."""

    def __init__(self, url: str, original_error: Exception = None):
        self.url = url
        self.original_error = original_error
        super().__init__(
            f"🔴 Serveur MCP non accessible ({url})\n"
            f"\n"
            f"  Démarrez-le avec :  docker compose up -d\n"
            f"  Vérifiez les logs : docker compose logs -f mcp-memory\n"
        )


class MCPClient:
    """Client pour communiquer avec le serveur MCP Memory."""

    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self.token = token

    # =========================================================================
    # Transport bas niveau
    # =========================================================================

    async def _fetch(self, endpoint: str) -> dict:
        """
        Requête GET sur l'API REST.

        Lève ServerNotRunningError si le serveur est injoignable.
        """
        import aiohttp

        url = f"{self.base_url}{endpoint}"
        headers = {"Authorization": f"Bearer {self.token}"}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        return await response.json()
                    text = await response.text()
                    raise Exception(f"HTTP {response.status}: {text}")
        except aiohttp.ClientConnectorError:
            raise ServerNotRunningError(self.base_url)
        except aiohttp.ClientConnectionError:
            raise ServerNotRunningError(self.base_url)
        except ConnectionRefusedError:
            raise ServerNotRunningError(self.base_url)
        except OSError as e:
            # Couvre les erreurs réseau bas niveau (ex: "Connection refused")
            if "Connect call failed" in str(e) or "refused" in str(e).lower():
                raise ServerNotRunningError(self.base_url)
            raise

    async def call_tool(self, tool_name: str, args: dict, max_retries: int = 2,
                        on_progress=None) -> dict:
        """
        Appeler un outil MCP via Streamable HTTP.

        Lève ServerNotRunningError si le serveur est injoignable.
        Les erreurs de connexion sont souvent wrappées dans un
        ExceptionGroup/TaskGroup, d'où le parsing récursif.
        
        Retry automatique en cas de déconnexion transport (RemoteProtocolError,
        ClosedResourceError) — fréquent pour les opérations longues (ingestion).
        
        Args:
            tool_name: Nom de l'outil MCP
            args: Arguments de l'outil
            max_retries: Nombre max de tentatives (défaut: 2)
            on_progress: Callback async appelée pour chaque notification de
                         progression (ctx.info() côté serveur). Signature:
                         async def on_progress(message: str) -> None
        """
        import asyncio
        import sys
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client

        headers = {"Authorization": f"Bearer {self.token}"}

        last_error = None
        for attempt in range(1, max_retries + 1):
            try:
                async with streamablehttp_client(
                    f"{self.base_url}/mcp",
                    headers=headers,
                    timeout=30,              # connexion initiale : 30s
                    sse_read_timeout=900     # attente réponse : 15 min (extraction LLM de gros docs)
                ) as (read, write, _):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        
                        # Capturer les notifications de progression (ctx.info())
                        # Le SDK MCP expose _received_notification() comme hook surchargeable
                        if on_progress:
                            _original_received = session._received_notification
                            
                            async def _patched_received_notification(notification):
                                try:
                                    # Le SDK wrappe dans un type union : notification.root
                                    # est le vrai objet (ex: LoggingMessageNotification)
                                    root = getattr(notification, 'root', notification)
                                    params = getattr(root, 'params', None)
                                    if params:
                                        # ctx.info() → LoggingMessageNotification.params.data
                                        msg = getattr(params, 'data', None)
                                        if msg:
                                            await on_progress(str(msg))
                                except Exception:
                                    pass
                                # Appeler le handler original
                                await _original_received(notification)
                            
                            session._received_notification = _patched_received_notification
                        
                        result = await session.call_tool(tool_name, args)
                        # --- Parsing robuste de la réponse MCP ---
                        # Vérifier si le serveur a renvoyé une erreur
                        if getattr(result, 'isError', False):
                            error_msg = "Erreur serveur MCP"
                            if result.content:
                                error_msg = getattr(result.content[0], 'text', '') or error_msg
                            return {"status": "error", "message": error_msg}
                        # Extraire le texte du premier bloc de contenu
                        text = ""
                        if result.content:
                            text = getattr(result.content[0], 'text', '') or ""
                        if not text:
                            return {"status": "error", "message": "Réponse vide du serveur"}
                        # Parser le JSON (avec fallback texte brut)
                        try:
                            return json.loads(text)
                        except json.JSONDecodeError:
                            return {"status": "error", "message": f"Réponse non-JSON: {text[:500]}"}
            except ConnectionRefusedError:
                raise ServerNotRunningError(self.base_url)
            except OSError as e:
                if "refused" in str(e).lower() or "Connect call failed" in str(e):
                    raise ServerNotRunningError(self.base_url)
                raise
            except BaseException as e:
                # Vérifier si c'est une erreur de connexion (serveur down)
                if self._is_connection_error(e):
                    raise ServerNotRunningError(self.base_url)
                # Vérifier si c'est une erreur transport récupérable (déconnexion mid-stream)
                if self._is_transport_disconnect(e) and attempt < max_retries:
                    last_error = e
                    wait_time = attempt * 5  # 5s, 10s, 15s...
                    print(f"⚠️  Connexion perdue (tentative {attempt}/{max_retries}), "
                          f"retry dans {wait_time}s...", file=sys.stderr)
                    await asyncio.sleep(wait_time)
                    continue
                # Extraire le message utile des TaskGroup/ExceptionGroup
                detail = self._extract_root_cause(e)
                if detail and detail != str(e):
                    raise RuntimeError(
                        f"{detail}\n\n"
                        f"💡 Vérifiez que le serveur MCP est accessible.\n"
                        f"   URL: {self.base_url}/mcp"
                    ) from None
                raise

        # Si on arrive ici, tous les retries ont échoué
        raise last_error or Exception("Échec après toutes les tentatives de retry")

    @staticmethod
    def _is_transport_disconnect(exc: BaseException) -> bool:
        """
        Vérifie si une exception est une déconnexion transport récupérable.
        
        Ces erreurs surviennent quand la connexion HTTP est coupée pendant
        une opération longue (ex: ingestion LLM de 5+ minutes).
        Contrairement aux erreurs de connexion (serveur down), ces erreurs
        sont temporaires et méritent un retry.
        """
        # Vérifier le message d'erreur directement
        msg = str(exc).lower()
        recoverable_patterns = [
            "incomplete chunked read",
            "peer closed connection",
            "closedresourceerror",
            "remoteprotocolerror",
            "server disconnected",
        ]
        for pattern in recoverable_patterns:
            if pattern in msg:
                return True
        
        # Vérifier le type d'exception
        type_name = type(exc).__name__
        if type_name in ("RemoteProtocolError", "ClosedResourceError"):
            return True
        
        # Parcourir les sous-exceptions d'un ExceptionGroup
        if hasattr(exc, 'exceptions'):
            for sub in exc.exceptions:
                if MCPClient._is_transport_disconnect(sub):
                    return True
        
        # Vérifier __cause__ (chainage d'exceptions)
        if exc.__cause__ and MCPClient._is_transport_disconnect(exc.__cause__):
            return True
        
        return False

    @staticmethod
    def _extract_root_cause(exc: BaseException) -> str:
        """
        Extrait le message d'erreur utile d'un TaskGroup/ExceptionGroup.
        
        Le MCP SDK wrappe souvent les vraies erreurs dans un ExceptionGroup
        (ex: "unhandled errors in a TaskGroup (1 sub-exception)").
        Cette méthode descend récursivement pour trouver le vrai message.
        """
        messages = []
        
        # Parcourir les sous-exceptions d'un ExceptionGroup
        if hasattr(exc, 'exceptions'):
            for sub in exc.exceptions:
                sub_msg = MCPClient._extract_root_cause(sub)
                if sub_msg:
                    messages.append(sub_msg)
        
        # Vérifier __cause__ (chainage d'exceptions)
        if exc.__cause__:
            cause_msg = MCPClient._extract_root_cause(exc.__cause__)
            if cause_msg:
                messages.append(cause_msg)
        
        if messages:
            return " → ".join(messages)
        
        # Message direct de l'exception
        msg = str(exc)
        if msg and "TaskGroup" not in msg and "sub-exception" not in msg:
            return f"{type(exc).__name__}: {msg}"
        
        return ""

    @staticmethod
    def _is_connection_error(exc: BaseException) -> bool:
        """
        Vérifie récursivement si une exception (ou un ExceptionGroup)
        contient une erreur de connexion.

        Couvre :
        - ConnectionRefusedError (stdlib)
        - OSError avec "refused" ou "connect call failed"
        - httpx.ConnectError ("All connection attempts failed")
        - Toute exception avec "connection" dans le nom de type
        """
        # Types stdlib
        if isinstance(exc, (ConnectionRefusedError,)):
            return True
        if isinstance(exc, OSError):
            msg = str(exc).lower()
            if "refused" in msg or "connect call failed" in msg:
                return True
        # httpx/anyio ConnectError et variantes
        type_name = type(exc).__name__
        if "ConnectError" in type_name or "ConnectionError" in type_name:
            return True
        # Message générique de connexion
        msg = str(exc).lower()
        if "connection attempts failed" in msg or "connection refused" in msg:
            return True
        # Parcourir les sous-exceptions d'un ExceptionGroup
        if hasattr(exc, 'exceptions'):
            for sub in exc.exceptions:
                if MCPClient._is_connection_error(sub):
                    return True
        return False

    # =========================================================================
    # Raccourcis API REST
    # =========================================================================

    async def list_memories(self) -> dict:
        """Liste les mémoires via REST."""
        return await self._fetch("/api/memories")

    async def get_graph(self, memory_id: str) -> dict:
        """Récupère le graphe complet d'une mémoire via REST."""
        return await self._fetch(f"/api/graph/{memory_id}")
