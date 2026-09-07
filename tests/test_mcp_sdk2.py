"""Contrats HTTP réels du SDK 2, sans S3, LLM ou base externe."""

import asyncio
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
    url, _ = service
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
        oversized = await http.post(
            "/mcp", headers={"Authorization": "Bearer sdk2-test-admin"},
            content=b"x" * (int(server.settings.max_document_size_bytes * 1.5) + 1),
        )
        assert oversized.status_code == 413


@pytest.mark.asyncio
async def test_initialize_reports_application_version(service):
    url, _ = service
    async with httpx2.AsyncClient(headers={"Authorization": "Bearer sdk2-test-admin"}, trust_env=False) as http:
        async with streamable_http_client(f"{url}/mcp", http_client=http) as (read, write):
            async with ClientSession(read, write) as session:
                result = await session.initialize()
                assert result.server_info.version == "3.2.1"
