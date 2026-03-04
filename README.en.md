# 🧠 Graph Memory — MCP Knowledge Graph Service

> 🇫🇷 [Version française](README.md)

A persistent memory service based on a **knowledge graph** for AI agents, implementing the [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) over **Streamable HTTP**.

Built by **[Cloud Temple](https://www.cloud-temple.com)**.

<p align="center">
  <img src="screenshoot/screen1.png" alt="Graph Memory — Knowledge Graph Visualization" width="800">
</p>

---

## 🎯 Concept

**Graph-First approach**: instead of classic vector RAG (embedding → cosine similarity), this service extracts **entities** and **relations** via an LLM to build a queryable knowledge graph.

```
Document (PDF, DOCX, MD, TXT, HTML, CSV)
    │
    ├──▶ S3 upload (persistent storage)
    ├──▶ LLM extraction guided by ontology → Entities + Relations → Neo4j
    └──▶ Semantic chunking + BGE-M3 embedding → Qdrant (vector DB)

Question (natural language)
    │
    ├── Graph search → entities found → Graph-Guided RAG (precise)
    └── No entities → RAG-only fallback (broad)
    │
    └──▶ LLM generates answer with source document citations
```

| Criteria           | Vector RAG                      | Graph Memory                      |
| ------------------ | ------------------------------- | --------------------------------- |
| **Precision**      | Approximate semantic similarity | Explicit typed relations          |
| **Traceability**   | Anonymous chunks                | Named entities + source documents |
| **Exploration**    | Unidirectional search           | Multi-hop graph navigation        |
| **Visualization**  | Difficult                       | Native interactive graph          |
| **Cross-document** | Mixed chunks                    | Explicit cross-document relations |

---

## ✨ Features

- **28 MCP tools** exposed via Streamable HTTP (`/mcp` endpoint)
- **Ontology-guided extraction** — 5 built-in ontologies (legal, cloud, managed-services, presales, general)
- **Graph-Guided RAG** — graph identifies relevant docs, then Qdrant searches chunks *within* those docs
- **Interactive web UI** — vis-network graph visualization, filtering, ASK panel with Markdown rendering
- **Complete CLI** — Click (scriptable) + interactive shell with autocompletion
- **Backup/Restore** — full 3-layer backup (Neo4j + Qdrant + S3) with tar.gz archive support
- **Multi-tenant** — namespace isolation per memory in Neo4j
- **Security** — Coraza WAF, Bearer Token auth, rate limiting, non-root container, isolated Docker network
- **Formats** — PDF, DOCX, Markdown, TXT, HTML, CSV

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────┐
│                    MCP Clients                       │
│  (Claude Desktop, Cline, agents, CLI, Web UI)        │
└────────────────────────┬────────────────────────────┘
                         │ Streamable HTTP + Bearer Token
                         ▼
┌─────────────────────────────────────────────────────┐
│         Coraza WAF (Port 8080 — only exposed port)   │
└────────────────────────┬────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────┐
│           Graph Memory Service (internal :8002)      │
│  Auth → Logging → Static Files → MCP Streamable HTTP │
│  28 MCP tools • 5 ontologies • Graph-Guided RAG      │
└────────────┬───────────┬──────────┬─────────────────┘
             ▼           ▼          ▼
         Neo4j 5    S3 Storage   Qdrant
         (graph)    (documents)  (vectors)
```

---

## 🚀 Quick Start

```bash
# Clone
git clone https://github.com/chrlesur/graph-memory.git
cd graph-memory

# Configure
cp .env.example .env
# Edit .env with your S3, LLM, and Neo4j credentials

# Start
docker compose up -d

# Health check
curl http://localhost:8080/health

# Web UI
open http://localhost:8080/graph
```

### Required Environment Variables

| Variable               | Description                     |
| ---------------------- | ------------------------------- |
| `S3_ENDPOINT_URL`      | S3 endpoint URL                 |
| `S3_ACCESS_KEY_ID`     | S3 access key                   |
| `S3_SECRET_ACCESS_KEY` | S3 secret                       |
| `S3_BUCKET_NAME`       | S3 bucket name                  |
| `LLMAAS_API_URL`       | LLM API URL (OpenAI-compatible) |
| `LLMAAS_API_KEY`       | LLM API key                     |
| `NEO4J_PASSWORD`       | Neo4j password                  |
| `ADMIN_BOOTSTRAP_KEY`  | Bootstrap key for first token   |

---

## 🔌 MCP Integration

### With Claude Desktop / Cline

```json
{
  "mcpServers": {
    "graph-memory": {
      "url": "http://localhost:8080/mcp",
      "headers": {
        "Authorization": "Bearer YOUR_TOKEN"
      }
    }
  }
}
```

### With Python (MCP SDK)

```python
from mcp.client.streamable_http import streamablehttp_client
from mcp import ClientSession
import base64

async def example():
    headers = {"Authorization": "Bearer your_token"}
    
    async with streamablehttp_client(
        "http://localhost:8080/mcp", headers=headers
    ) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            # Create a memory
            await session.call_tool("memory_create", {
                "memory_id": "demo",
                "name": "Demo",
                "description": "Demo memory",
                "ontology": "general"
            })
            
            # Ingest a document
            with open("document.pdf", "rb") as f:
                content = base64.b64encode(f.read()).decode()
            
            await session.call_tool("memory_ingest", {
                "memory_id": "demo",
                "content_base64": content,
                "filename": "document.pdf"
            })
            
            # Ask a question
            result = await session.call_tool("question_answer", {
                "memory_id": "demo",
                "question": "What are the main topics?",
                "limit": 10
            })
            print(result)
```

---

## 🔧 MCP Tools (28)

| Category           | Tools                                                                                                          |
| ------------------ | -------------------------------------------------------------------------------------------------------------- |
| **Memory CRUD**    | `memory_create`, `memory_delete`, `memory_list`, `memory_stats`                                                |
| **Ingestion**      | `memory_ingest`                                                                                                |
| **Search & Q&A**   | `memory_search`, `memory_query`, `memory_get_context`, `question_answer`                                       |
| **Documents**      | `document_list`, `document_get`, `document_delete`                                                             |
| **Backup/Restore** | `backup_create`, `backup_list`, `backup_restore`, `backup_download`, `backup_delete`, `backup_restore_archive` |
| **Admin**          | `admin_create_token`, `admin_list_tokens`, `admin_revoke_token`, `admin_update_token`                          |
| **Diagnostics**    | `system_health`, `system_about`, `storage_check`, `storage_cleanup`                                            |
| **Visualization**  | `memory_graph`, `ontology_list`                                                                                |

---

## 📖 Ontologies

Ontologies define the entity types and relation types the LLM should extract. Required when creating a memory.

| Ontology           | Entities | Relations | Use case                                 |
| ------------------ | -------- | --------- | ---------------------------------------- |
| `legal`            | 22       | 22        | Legal documents, contracts               |
| `cloud`            | 27       | 19        | Cloud infrastructure, product sheets     |
| `managed-services` | 20       | 16        | Managed services, outsourcing            |
| `presales`         | 28       | 30        | Pre-sales, RFP/RFI, proposals            |
| `general`          | 24       | 22        | Generic: FAQ, certifications, CSR, specs |

Custom ontologies can be added as YAML files in `ONTOLOGIES/`.

---

## 💻 CLI

```bash
# Install CLI dependencies
pip install httpx click rich prompt_toolkit mcp

# Scriptable mode
python scripts/mcp_cli.py health
python scripts/mcp_cli.py memory list
python scripts/mcp_cli.py document ingest DEMO /path/to/doc.pdf
python scripts/mcp_cli.py ask DEMO "What are the key points?"

# Interactive shell (Tab completion, history, Rich display)
python scripts/mcp_cli.py shell
```

### Production CLI (remote server)

```bash
export MCP_URL=https://graph-mem.example.com
export MCP_TOKEN=your_production_key
python scripts/mcp_cli.py health
```

---

## 🔒 Security

- **Coraza WAF** — OWASP CRS, only port 8080 exposed
- **Bearer Token auth** — required for all MCP and API requests
- **Rate limiting** — per-IP limits (MCP 60/min, API 30/min, global 200/min)
- **Non-root container** — MCP service runs as user `mcp`
- **Isolated Docker network** — Neo4j and Qdrant not exposed externally
- **TLS** — automatic Let's Encrypt in production (`SITE_ADDRESS=your-domain.com`)

---

## 🌉 Integration with Live Memory

Graph Memory integrates natively with [Live Memory](https://github.com/chrlesur/live-memory) to form a **two-tier memory architecture** for multi-agent systems:

| Tier                 | Service      | Duration        | Content                                  |
| -------------------- | ------------ | --------------- | ---------------------------------------- |
| **Working memory**   | Live Memory  | Session/project | Raw notes → Markdown bank                |
| **Long-term memory** | Graph Memory | Permanent       | Entities + relations + vector embeddings |

Agents take notes in Live Memory → LLM consolidates → `graph_push` ingests into Graph Memory → queryable knowledge graph.

---

## 📄 License

**Apache 2.0** — See [LICENSE](LICENSE).

Built by **[Cloud Temple](https://www.cloud-temple.com)**.
