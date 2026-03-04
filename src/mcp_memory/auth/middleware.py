# -*- coding: utf-8 -*-
"""
AuthMiddleware - Middleware ASGI pour l'authentification Bearer Token.

Vérifie le header Authorization et valide le token via TokenManager.
"""

import os
import sys
from typing import Optional

from ..config import get_settings
from .context import current_auth


# NOTE: HostNormalizerMiddleware supprimé (migration SSE → Streamable HTTP).
# L'ancien transport SSE nécessitait une normalisation du Host header pour les reverse
# proxies (HTTP 421). Streamable HTTP n'a plus ce problème.


class AuthMiddleware:
    """
    Middleware ASGI pour l'authentification.
    
    Vérifie le header `Authorization: Bearer <token>` et valide le token.
    Pour le bootstrap initial, accepte aussi ADMIN_BOOTSTRAP_KEY.
    """
    
    def __init__(self, app, debug: bool = False):
        """
        Initialise le middleware.
        
        Args:
            app: Application ASGI à wrapper
            debug: Mode debug (logs détaillés)
        """
        self.app = app
        self.debug = debug
        self._settings = get_settings()
        self._token_manager = None
    
    @property
    def token_manager(self):
        """Lazy-load du TokenManager."""
        if self._token_manager is None:
            from .token_manager import get_token_manager
            self._token_manager = get_token_manager()
        return self._token_manager
    
    async def __call__(self, scope, receive, send):
        """Point d'entrée ASGI."""
        if scope["type"] != "http":
            # Passer directement pour WebSocket, lifespan, etc.
            await self.app(scope, receive, send)
            return
        
        path = scope.get("path", "")
        
        # Endpoints publics (pas d'auth requise)
        # Note: /api/ N'EST PLUS public — nécessite un token Bearer
        public_paths = ["/health", "/healthz", "/ready", "/graph", "/static/"]
        if any(path.startswith(p) for p in public_paths):
            await self.app(scope, receive, send)
            return
        
        # Requêtes internes (localhost) : pas d'auth pour MCP/SSE
        # MAIS les endpoints /api/ exigent toujours un token (pour le client web)
        client = scope.get("client", ("", 0))
        client_ip = client[0] if client else ""
        if client_ip in ("127.0.0.1", "::1") and not path.startswith("/api/"):
            await self.app(scope, receive, send)
            return
        
        # Récupérer le header Authorization
        headers = dict(scope.get("headers", []))
        auth_header = headers.get(b"authorization", b"").decode("utf-8")
        
        if not auth_header:
            if self.debug:
                print(f"❌ [Auth] Header Authorization manquant pour {path}", file=sys.stderr)
            await self._send_error(send, 401, "Authorization header required")
            return
        
        # Parser le Bearer token
        if not auth_header.startswith("Bearer "):
            if self.debug:
                print(f"❌ [Auth] Format invalide (attendu: Bearer <token>)", file=sys.stderr)
            await self._send_error(send, 401, "Invalid authorization format. Use: Bearer <token>")
            return
        
        token = auth_header[7:]  # Retire "Bearer "
        
        # Vérifier si c'est la clé bootstrap admin
        bootstrap_key = self._settings.admin_bootstrap_key
        if bootstrap_key and token == bootstrap_key:
            if self.debug:
                print(f"✅ [Auth] Authentification avec clé bootstrap admin", file=sys.stderr)
            # Ajouter info d'auth au scope
            scope["auth"] = {
                "type": "bootstrap",
                "client_name": "admin",
                "permissions": ["admin", "read", "write"],
                "memory_ids": []  # Accès à toutes
            }
            # Propager le contexte d'auth pour les outils MCP
            current_auth.set(scope["auth"])
            await self.app(scope, receive, send)
            return
        
        # Valider le token client
        try:
            token_info = await self.token_manager.validate_token(token)
            
            if not token_info:
                if self.debug:
                    print(f"❌ [Auth] Token invalide ou expiré", file=sys.stderr)
                await self._send_error(send, 401, "Invalid or expired token")
                return
            
            if self.debug:
                print(f"✅ [Auth] Client '{token_info.client_name}' authentifié", file=sys.stderr)
            
            # Ajouter info d'auth au scope
            scope["auth"] = {
                "type": "token",
                "client_name": token_info.client_name,
                "permissions": token_info.permissions,
                "memory_ids": token_info.memory_ids,
                "token_hash": token_info.token_hash
            }
            
            # Propager le contexte d'auth pour les outils MCP
            current_auth.set(scope["auth"])
            await self.app(scope, receive, send)
            
        except Exception as e:
            if self.debug:
                print(f"❌ [Auth] Erreur validation: {e}", file=sys.stderr)
            await self._send_error(send, 500, "Authentication error")
    
    async def _send_error(self, send, status: int, message: str):
        """Envoie une réponse d'erreur HTTP."""
        import json
        
        body = json.dumps({"error": message}).encode()
        
        await send({
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ],
        })
        await send({
            "type": "http.response.body",
            "body": body,
        })


class LoggingMiddleware:
    """
    Middleware ASGI pour le logging des requêtes (mode debug).
    """
    
    def __init__(self, app, debug: bool = False):
        self.app = app
        self.debug = debug
    
    async def __call__(self, scope, receive, send):
        if not self.debug or scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        
        path = scope.get("path", "")
        method = scope.get("method", "?")
        query = scope.get("query_string", b"").decode()
        
        full_path = f"{path}?{query}" if query else path
        print(f"📥 [HTTP] {method} {full_path}", file=sys.stderr)
        
        # Wrapper pour logger la réponse
        status_code = [None]
        
        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status_code[0] = message.get("status")
            await send(message)
        
        await self.app(scope, receive, send_wrapper)
        
        if status_code[0]:
            emoji = "✅" if status_code[0] < 400 else "❌"
            print(f"{emoji} [HTTP] {method} {path} -> {status_code[0]}", file=sys.stderr)


class StaticFilesMiddleware:
    """
    Middleware ASGI pour servir les fichiers statiques et l'API REST simple.
    
    Routes:
    - GET /graph -> Page de visualisation
    - GET /api/memories -> Liste des mémoires (JSON)
    - GET /api/graph/<memory_id> -> Graphe complet (JSON)
    """
    
    def __init__(self, app):
        self.app = app
        self._static_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "static"
        )
        self._graph_service = None
        self._extractor_service = None
    
    @property
    def graph_service(self):
        """Lazy-load GraphService."""
        if self._graph_service is None:
            from ..core.graph import get_graph_service
            self._graph_service = get_graph_service()
        return self._graph_service
    
    @property
    def extractor_service(self):
        """Lazy-load ExtractorService."""
        if self._extractor_service is None:
            from ..core.extractor import get_extractor_service
            self._extractor_service = get_extractor_service()
        return self._extractor_service
    
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        
        path = scope.get("path", "")
        method = scope.get("method", "GET")
        
        # Page de visualisation
        if path == "/graph" or path == "/graph/":
            await self._serve_file(send, "graph.html", "text/html")
            return
        
        # Fichiers statiques (CSS, JS)
        if path.startswith("/static/"):
            rel_path = path[len("/static/"):]
            # Sécurité : pas de traversée de répertoire
            if ".." not in rel_path and rel_path:
                ct = self._guess_content_type(rel_path)
                await self._serve_file(send, rel_path, ct)
                return
        
        # Health check
        if path in ("/health", "/healthz", "/ready"):
            await self._api_health(send)
            return
        
        # API REST - Liste des mémoires
        if path == "/api/memories" and method == "GET":
            await self._api_memories(send)
            return
        
        # API REST - Graphe d'une mémoire
        if path.startswith("/api/graph/") and method == "GET":
            memory_id = path[len("/api/graph/"):]
            if memory_id:
                await self._api_graph(send, memory_id)
                return
        
        # API REST - Question/Réponse (POST)
        if path == "/api/ask" and method == "POST":
            body = await self._read_body(receive)
            await self._api_ask(send, body)
            return
        
        # API REST - Query structuré (POST) — données brutes sans LLM
        if path == "/api/query" and method == "POST":
            body = await self._read_body(receive)
            await self._api_query(send, body)
            return
        
        # Passer au handler suivant
        await self.app(scope, receive, send)
    
    async def _read_body(self, receive) -> bytes:
        """Lit le corps complet d'une requête ASGI."""
        body = b""
        while True:
            message = await receive()
            body += message.get("body", b"")
            if not message.get("more_body", False):
                break
        return body
    
    def _read_version(self) -> str:
        """Lit la version depuis le fichier VERSION."""
        try:
            # auth/middleware.py → auth → mcp_memory → src → project root
            version_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
                "VERSION"
            )
            if os.path.exists(version_path):
                with open(version_path) as f:
                    return f.read().strip()
        except Exception:
            pass
        return "unknown"

    async def _api_health(self, send):
        """Retourne l'état de santé du serveur."""
        import json
        from datetime import datetime
        version = self._read_version()
        try:
            # Test rapide Neo4j via une requête simple
            neo4j_ok = False
            neo4j_msg = "Non testé"
            try:
                test = await self.graph_service.test_connection()
                neo4j_ok = test.get("status") == "ok"
                neo4j_msg = test.get("message", "OK")
            except Exception as e:
                neo4j_msg = str(e)
            
            data = {
                "status": "healthy" if neo4j_ok else "degraded",
                "version": version,
                "timestamp": datetime.utcnow().isoformat(),
                "services": {
                    "neo4j": {"status": "ok" if neo4j_ok else "error", "message": neo4j_msg}
                }
            }
            await self._send_json(send, data)
        except Exception as e:
            await self._send_json(send, {
                "status": "error",
                "version": version,
                "message": str(e)
            }, 500)
    
    async def _api_memories(self, send):
        """Retourne la liste des mémoires en JSON."""
        import json
        try:
            memories = await self.graph_service.list_memories()
            data = {
                "status": "ok",
                "count": len(memories),
                "memories": [
                    {
                        "id": m.id,
                        "name": m.name,
                        "description": m.description,
                        "ontology": m.ontology,
                        "ontology_uri": m.ontology_uri,
                        "created_at": m.created_at.isoformat() if m.created_at else None
                    }
                    for m in memories
                ]
            }
            await self._send_json(send, data)
        except Exception as e:
            await self._send_json(send, {"status": "error", "message": str(e)}, 500)
    
    async def _api_graph(self, send, memory_id: str):
        """Retourne le graphe complet d'une mémoire en JSON."""
        import json
        try:
            graph_data = await self.graph_service.get_full_graph(memory_id)
            data = {
                "status": "ok",
                "memory_id": memory_id,
                "node_count": len(graph_data["nodes"]),
                "edge_count": len(graph_data["edges"]),
                "document_count": len(graph_data["documents"]),
                "nodes": graph_data["nodes"],
                "edges": graph_data["edges"],
                "documents": graph_data["documents"]
            }
            await self._send_json(send, data)
        except Exception as e:
            await self._send_json(send, {"status": "error", "message": str(e)}, 500)
    
    async def _api_ask(self, send, body: bytes):
        """
        Traite une question sur une mémoire et retourne la réponse.
        
        Délègue à question_answer() de server.py (source unique de logique).
        Body JSON: {memory_id, question, limit?}
        Retourne: {status, answer, entities, source_documents}
        """
        import json
        try:
            payload = json.loads(body.decode('utf-8'))
            memory_id = payload.get("memory_id")
            question = payload.get("question")
            limit = payload.get("limit", 10)
            
            if not memory_id or not question:
                await self._send_json(send, {
                    "status": "error",
                    "message": "memory_id et question sont requis"
                }, 400)
                return
            
            print(f"💬 [ASK] {memory_id}: {question}", file=sys.stderr)
            
            # Appel direct à la fonction MCP (source unique de logique)
            from ..server import question_answer
            result = await question_answer(memory_id, question, limit)
            
            # Retirer context_used de la réponse API (pas utile pour le front)
            result.pop("context_used", None)
            
            await self._send_json(send, result)
            
        except json.JSONDecodeError:
            await self._send_json(send, {
                "status": "error",
                "message": "JSON invalide dans le body"
            }, 400)
        except Exception as e:
            print(f"❌ [ASK] Erreur: {e}", file=sys.stderr)
            await self._send_json(send, {
                "status": "error",
                "message": str(e)
            }, 500)
    
    async def _api_query(self, send, body: bytes):
        """
        Interroge une mémoire et retourne les données structurées (sans LLM).
        
        Délègue à memory_query() de server.py (source unique de logique).
        Body JSON: {memory_id, query, limit?}
        Retourne: {status, entities, rag_chunks, source_documents, stats}
        """
        import json
        try:
            payload = json.loads(body.decode('utf-8'))
            memory_id = payload.get("memory_id")
            query = payload.get("query")
            limit = payload.get("limit", 10)
            
            if not memory_id or not query:
                await self._send_json(send, {
                    "status": "error",
                    "message": "memory_id et query sont requis"
                }, 400)
                return
            
            print(f"📊 [Query] {memory_id}: {query}", file=sys.stderr)
            
            from ..server import memory_query
            result = await memory_query(memory_id, query, limit)
            
            await self._send_json(send, result)
            
        except json.JSONDecodeError:
            await self._send_json(send, {
                "status": "error",
                "message": "JSON invalide dans le body"
            }, 400)
        except Exception as e:
            print(f"❌ [Query] Erreur: {e}", file=sys.stderr)
            await self._send_json(send, {
                "status": "error",
                "message": str(e)
            }, 500)
    
    async def _send_json(self, send, data: dict, status: int = 200):
        """Envoie une réponse JSON."""
        import json
        body = json.dumps(data, ensure_ascii=False, default=str).encode('utf-8')
        await send({
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json; charset=utf-8"),
                (b"content-length", str(len(body)).encode()),
                (b"access-control-allow-origin", b"*"),
            ],
        })
        await send({"type": "http.response.body", "body": body})
    
    async def _serve_file(self, send, filename: str, content_type: str):
        """Sert un fichier statique."""
        filepath = os.path.join(self._static_dir, filename)
        
        if not os.path.exists(filepath):
            await self._send_404(send, f"File not found: {filename}")
            return
        
        try:
            with open(filepath, "rb") as f:
                body = f.read()
            
            await send({
                "type": "http.response.start",
                "status": 200,
                "headers": [
                    (b"content-type", content_type.encode()),
                    (b"content-length", str(len(body)).encode()),
                    (b"cache-control", b"no-cache"),
                ],
            })
            await send({
                "type": "http.response.body",
                "body": body,
            })
        except Exception as e:
            await self._send_500(send, str(e))
    
    async def _send_404(self, send, message: str):
        """Envoie une erreur 404."""
        body = f"<h1>404 Not Found</h1><p>{message}</p>".encode()
        await send({
            "type": "http.response.start",
            "status": 404,
            "headers": [
                (b"content-type", b"text/html"),
                (b"content-length", str(len(body)).encode()),
            ],
        })
        await send({"type": "http.response.body", "body": body})
    
    async def _send_500(self, send, message: str):
        """Envoie une erreur 500."""
        body = f"<h1>500 Internal Server Error</h1><p>{message}</p>".encode()
        await send({
            "type": "http.response.start",
            "status": 500,
            "headers": [
                (b"content-type", b"text/html"),
                (b"content-length", str(len(body)).encode()),
            ],
        })
        await send({"type": "http.response.body", "body": body})
    
    @staticmethod
    def _guess_content_type(filename: str) -> str:
        """Devine le content-type à partir de l'extension."""
        ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
        return {
            'html': 'text/html; charset=utf-8',
            'css': 'text/css; charset=utf-8',
            'js': 'application/javascript; charset=utf-8',
            'json': 'application/json',
            'png': 'image/png',
            'svg': 'image/svg+xml',
            'ico': 'image/x-icon',
        }.get(ext, 'application/octet-stream')
