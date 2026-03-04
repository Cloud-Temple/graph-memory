# -*- coding: utf-8 -*-
"""
Client Streamable HTTP pour communiquer avec le serveur MCP.

Ce client gère :
- La connexion Streamable HTTP (endpoint /mcp)
- L'appel d'outils MCP via le SDK officiel
- La réception des notifications de progression
- La gestion des erreurs et reconnexion
"""

import json
import asyncio
from typing import Optional, Callable, Any


class MCPClient:
    """Client MCP générique via Streamable HTTP."""

    def __init__(self, base_url: str, token: str = "", timeout: float = 300.0):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict,
        on_progress: Optional[Callable] = None,
    ) -> dict:
        """
        Appelle un outil MCP via Streamable HTTP.

        Args:
            tool_name: Nom de l'outil (ex: "system_health")
            arguments: Paramètres de l'outil
            on_progress: Callback optionnel pour les notifications (async callable)

        Returns:
            Le résultat de l'outil (dict)
        """
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client

        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        try:
            async with streamablehttp_client(
                f"{self.base_url}/mcp",
                headers=headers,
                timeout=30,
                sse_read_timeout=self.timeout,
            ) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()

                    # Capturer les notifications de progression
                    if on_progress:
                        _original = session._received_notification

                        async def _patched(notification):
                            try:
                                root = getattr(notification, 'root', notification)
                                params = getattr(root, 'params', None)
                                if params:
                                    msg = getattr(params, 'data', None)
                                    if msg:
                                        await on_progress(str(msg))
                            except Exception:
                                pass
                            await _original(notification)

                        session._received_notification = _patched

                    result = await session.call_tool(tool_name, arguments)

                    # Parser la réponse MCP
                    if getattr(result, 'isError', False):
                        error_msg = "Erreur serveur MCP"
                        if result.content:
                            error_msg = getattr(result.content[0], 'text', '') or error_msg
                        return {"status": "error", "message": error_msg}

                    text = ""
                    if result.content:
                        text = getattr(result.content[0], 'text', '') or ""
                    if not text:
                        return {"status": "error", "message": "Réponse vide"}

                    try:
                        return json.loads(text)
                    except json.JSONDecodeError:
                        return {"status": "ok", "raw": text}

        except ConnectionRefusedError:
            return {"status": "error", "message": f"Serveur non accessible: {self.base_url}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def list_tools(self) -> list:
        """Liste les outils MCP disponibles."""
        result = await self.call_tool("system_about", {})
        return result.get("tools", [])
