"""Contrats HTTP réels du SDK 2, sans S3, LLM ou base externe."""

import asyncio
import base64
import hashlib
import json
import socket
from types import SimpleNamespace
from typing import Optional

import httpx2
import pytest
import pytest_asyncio
import uvicorn
from mcp import Client, ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.server.mcpserver import Context

from scripts.cli.client import MCPClient


@pytest_asyncio.fixture
async def service(monkeypatch):
    for name in ("S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY", "LLMAAS_API_KEY", "NEO4J_PASSWORD"):
        monkeypatch.setenv(name, "sdk2-test-unused")
    monkeypatch.setenv("LOCALHOST_AUTH_BYPASS", "false")
    from src.mcp_memory import server
    from src.mcp_memory.auth.context import current_auth

    monkeypatch.setattr(server.settings, "admin_bootstrap_key", "sdk2-test-admin")
    # Garde les tests de limite rapides : 4 Mio par document, 12 Mio par requête.
    monkeypatch.setattr(server.settings, "max_document_size_mb", 4)

    class Tokens:
        async def validate_token(self, token):
            if token not in ("reader", "writer"):
                return None
            return SimpleNamespace(
                client_name=token, token_hash=token,
                permissions=["read"] if token == "reader" else ["read", "write"],
                memory_ids=["allowed"],
            )

        async def list_tokens(self, **kwargs):
            return []

    tokens = Tokens()
    monkeypatch.setattr(server, "_token_manager", tokens)

    @server.mcp.tool()
    async def sdk2_probe(payload: str, ctx: Optional[Context] = None) -> dict:
        if ctx:
            try:
                await ctx.info("probe-progress")
            except Exception:
                # /api/tool n'a pas de session MCP pour recevoir les logs ;
                # les outils d'ingestion appliquent le même garde-fou.
                pass
        return {
            "status": "ok",
            "size": len(payload),
            "client": current_auth.get()["client_name"],
            "ctx_received": ctx is not None,
        }

    @server.mcp.tool()
    async def sdk2_failure() -> dict:
        raise ValueError("probe-failure")

    app = server.create_app(host="0.0.0.0")
    app._token_manager = tokens
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen()
    port = sock.getsockname()[1]
    runner = uvicorn.Server(uvicorn.Config(app, log_level="error", lifespan="on"))
    task = asyncio.create_task(runner.serve(sockets=[sock]))
    try:
        async with asyncio.timeout(10):
            while not runner.started:
                if task.done():
                    await task
                await asyncio.sleep(0.01)
        yield f"http://127.0.0.1:{port}", server
    finally:
        runner.should_exit = True
        await asyncio.wait_for(task, 10)
        sock.close()
        server.mcp.remove_tool("sdk2_probe")
        server.mcp.remove_tool("sdk2_failure")


@pytest.mark.asyncio
async def test_sdk2_cli_large_request_progress_and_errors(service, monkeypatch):
    url, server = service
    # Un proxy du poste ne doit pas détourner les requêtes locales.
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
    monkeypatch.setenv("NO_PROXY", "")
    messages = []

    async def progress(message):
        messages.append(message)

    client = MCPClient(url, "writer")
    result = await client.call_tool("sdk2_probe", {"payload": "x" * (5 * 1024 * 1024)}, on_progress=progress)
    assert result == {
        "status": "ok",
        "size": 5 * 1024 * 1024,
        "client": "writer",
        "ctx_received": True,
    }
    assert "probe-progress" in messages
    without_progress = await client.call_tool("sdk2_probe", {"payload": "plain"})
    assert without_progress["ctx_received"] is True
    failure = await client.call_tool("sdk2_failure", {})
    assert failure["status"] == "error"
    assert "sdk2_failure" in failure["message"]
    assert "probe-failure" not in failure["message"]  # Le SDK masque les erreurs internes.
    invalid = await client.call_tool("sdk2_probe", {})
    assert invalid["status"] == "error"
    assert "payload" in invalid["message"]

    # Deux documents de 3 Mio produisent une requête JSON/Base64 d'environ
    # 8 Mio : elle dépassait l'ancienne limite de 6 Mio (1,5 × document).
    from src.mcp_memory.core import ingest_queue

    class Storage:
        @staticmethod
        def compute_hash(content):
            return hashlib.sha256(content).hexdigest()

    class Queue:
        def __init__(self):
            self.calls = 0

        async def submit(self, **kwargs):
            self.calls += 1
            return {"status": "queued", "job_id": f"job-{self.calls}"}

    queue = Queue()
    monkeypatch.setattr(server, "get_storage", lambda: Storage())
    monkeypatch.setattr(ingest_queue, "get_ingest_queue", lambda: queue)
    raw = b"b" * (3 * 1024 * 1024)
    encoded = base64.b64encode(raw).decode()
    digest = hashlib.sha256(raw).hexdigest()
    batch = await client.call_tool("memory_ingest_batch_async", {
        "memory_id": "allowed",
        "documents": [
            {"content_base64": encoded, "filename": "a.md", "source_path": "a.md", "sha256": digest},
            {"content_base64": encoded, "filename": "b.md", "source_path": "b.md", "sha256": digest},
        ],
    })
    assert batch["status"] == "ok"
    assert batch["total"] == 2
    assert batch["counts"]["queued"] == 2
    assert queue.calls == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["legacy", "2026-07-28"])
async def test_protocol_versions_auth_and_tool_schemas(service, mode):
    url, _ = service
    async with httpx2.AsyncClient(headers={"Authorization": "Bearer reader"}, trust_env=False) as http:
        transport = streamable_http_client(f"{url}/mcp", http_client=http)
        async with Client(transport, mode=mode) as client:
            tools = await client.list_tools()
            assert len(tools.tools) == 42  # 40 outils métier + 2 sondes de transport.
            assert all("ctx" not in tool.input_schema.get("properties", {}) for tool in tools.tools)
            result = await client.call_tool("system_whoami", {})
            identity = json.loads(result.content[0].text)
            assert identity["client_name"] == "reader"
            assert identity["permissions"] == ["read"]
            denied = await client.call_tool("memory_stats", {"memory_id": "forbidden"})
            denial = json.loads(denied.content[0].text)
            assert denial["status"] == "error"
            assert "Accès refusé" in denial["message"]


@pytest.mark.asyncio
async def test_admin_cookie_and_public_sdk_dispatch(service):
    url, _ = service
    async with httpx2.AsyncClient(base_url=url, trust_env=False) as http:
        assert (await http.get("/admin")).status_code == 200
        assert (await http.post("/api/tool", json={"tool": "system_whoami"})).status_code == 401
        login = await http.post("/api/login", json={"token": "sdk2-test-admin"})
        assert login.status_code == 200
        assert "httponly" in login.headers["set-cookie"].lower()
        result = await http.post("/api/tool", json={"tool": "system_whoami"})
        assert result.status_code == 200
        assert result.json()["auth_type"] == "bootstrap"
        contextual = await http.post(
            "/api/tool", json={"tool": "sdk2_probe", "arguments": {"payload": "admin"}}
        )
        assert contextual.status_code == 200
        assert contextual.json()["ctx_received"] is True
        invalid = await http.post("/api/tool", json={"tool": "memory_stats", "arguments": {}})
        assert invalid.status_code == 200
        assert invalid.json()["status"] == "error"
        unknown = await http.post("/api/tool", json={"tool": "does_not_exist"})
        assert unknown.status_code == 200
        assert unknown.json()["status"] == "error"
        await http.post("/api/logout")
        assert (await http.post("/api/tool", json={"tool": "system_whoami"})).status_code == 401


@pytest.mark.asyncio
async def test_anonymous_mcp_denied_and_http_body_limit(service):
    url, server = service
    async with httpx2.AsyncClient(base_url=url, trust_env=False, timeout=20) as http:
        assert (await http.post("/mcp", json={})).status_code == 401
        public_host = await http.post(
            "/mcp",
            headers={"Authorization": "Bearer sdk2-test-admin", "Host": "graph-memory.example.com"},
            json={},
        )
        assert public_host.status_code != 421
        oversized = await http.post(
            "/mcp", headers={"Authorization": "Bearer sdk2-test-admin"},
            content=b"x" * (server.settings.max_document_size_bytes * 3 + 1),
        )
        assert oversized.status_code == 413


@pytest.mark.asyncio
async def test_internal_decorated_tool_calls(service, monkeypatch):
    """Les routes et outils internes peuvent appeler les fonctions décorées."""
    url, server = service

    class Graph:
        async def list_memories(self):
            return []

        async def search_entities(self, *args, **kwargs):
            return []

    class Storage:
        @staticmethod
        def _parse_key(uri):
            return uri

        async def check_documents(self, uris):
            return {
                "total": 0, "accessible": 0, "missing": 0, "errors": 0,
                "total_size_bytes": 0, "details": [],
            }

        async def list_all_objects(self):
            return []

    class Embedder:
        async def embed_query(self, query):
            return [0.0]

    class VectorStore:
        async def search(self, **kwargs):
            return []

    monkeypatch.setattr(server, "get_graph", lambda: Graph())
    monkeypatch.setattr(server, "get_storage", lambda: Storage())
    monkeypatch.setattr(server, "get_embedder", lambda: Embedder())
    monkeypatch.setattr(server, "get_vector_store", lambda: VectorStore())

    cleanup = await server.storage_cleanup(dry_run=True)
    assert cleanup["status"] == "ok"
    assert cleanup["orphans_found"] == 0

    async with httpx2.AsyncClient(base_url=url, trust_env=False) as http:
        assert (await http.post("/api/login", json={"token": "sdk2-test-admin"})).status_code == 200
        response = await http.post(
            "/api/query", json={"memory_id": "allowed", "query": "test", "limit": 3}
        )
        assert response.status_code == 200
        result = response.json()
        assert result["status"] == "ok"
        assert result["entities"] == []
        assert result["rag_chunks"] == []


@pytest.mark.asyncio
async def test_initialize_reports_application_version(service):
    url, _ = service
    async with httpx2.AsyncClient(headers={"Authorization": "Bearer sdk2-test-admin"}, trust_env=False) as http:
        async with streamable_http_client(f"{url}/mcp", http_client=http) as (read, write):
            async with ClientSession(read, write) as session:
                result = await session.initialize()
                assert result.server_info.version == "3.2.1"
