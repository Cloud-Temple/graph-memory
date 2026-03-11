# 💻 MCP Memory CLI

Command-line client for the **Graph Memory MCP** server.

Two usage modes:
- **Click mode** (scriptable): direct commands with arguments and options
- **Shell mode** (interactive): tab completion, history, contextual commands

> 📖 This is a summary. See [README.md](README.md) (French) for the full reference.

---

## Prerequisites

```bash
pip install httpx click rich prompt_toolkit
docker compose up -d
```

## Configuration

| Priority | URL Variable | Token Variable | Usage |
| :------: | ------------ | -------------- | ----- |
| **1** (recommended) | `MCP_URL` | `MCP_TOKEN` | **Dedicated CLI variables** |
| 2 (fallback) | `MCP_SERVER_URL` | `ADMIN_BOOTSTRAP_KEY` | Compatibility — also read from local `.env` |

**Defaults**: `http://localhost:8080` (URL) and `admin_bootstrap_key_change_me` (token).

```bash
# Local development (uses .env automatically)
python scripts/mcp_cli.py health

# Production
export MCP_URL=https://mcp-memory.example.com
export MCP_TOKEN=your_production_key
python scripts/mcp_cli.py health
```

---

## Click Mode (Scriptable)

Entry point: `python scripts/mcp_cli.py [COMMAND] [OPTIONS]`

### Server
```bash
python scripts/mcp_cli.py about      # Service identity & capabilities
python scripts/mcp_cli.py health     # Health check (all services)
```

### Memories
```bash
python scripts/mcp_cli.py memory list
python scripts/mcp_cli.py memory create LEGAL -n "Legal Corpus" -o legal
python scripts/mcp_cli.py memory delete LEGAL -f
python scripts/mcp_cli.py memory info LEGAL
python scripts/mcp_cli.py memory graph LEGAL
python scripts/mcp_cli.py memory entities LEGAL
python scripts/mcp_cli.py memory entity LEGAL "Cloud Temple"
python scripts/mcp_cli.py memory relations LEGAL -t DEFINES
```

### Documents
```bash
python scripts/mcp_cli.py document list LEGAL
python scripts/mcp_cli.py document ingest LEGAL /path/to/contract.docx
python scripts/mcp_cli.py document ingest LEGAL /path/to/contract.docx -f  # force re-ingest
python scripts/mcp_cli.py document ingest-dir LEGAL ./docs -e '*.tmp'      # recursive
python scripts/mcp_cli.py document delete LEGAL <document_id>
```

### Question/Answer
```bash
python scripts/mcp_cli.py ask LEGAL "What are the termination conditions?"
python scripts/mcp_cli.py query LEGAL "data reversibility"   # structured, no LLM
```

### Storage & Ontologies
```bash
python scripts/mcp_cli.py storage check LEGAL
python scripts/mcp_cli.py storage cleanup -f
python scripts/mcp_cli.py ontologies
```

### Backup / Restore
```bash
python scripts/mcp_cli.py backup create LEGAL -d "Before migration"
python scripts/mcp_cli.py backup list
python scripts/mcp_cli.py backup restore "LEGAL/2026-02-16T15-33-48"
python scripts/mcp_cli.py backup download "LEGAL/2026-02-16T15-33-48" --include-documents
python scripts/mcp_cli.py backup delete "LEGAL/2026-02-16T15-33-48" -f
python scripts/mcp_cli.py backup restore-file ./backup.tar.gz
```

### Access Tokens
```bash
python scripts/mcp_cli.py token list
python scripts/mcp_cli.py token create quoteflow -p read,write -m LEGAL,CLOUD
python scripts/mcp_cli.py token create admin-bot -p admin -e 30
python scripts/mcp_cli.py token revoke <hash> -f
python scripts/mcp_cli.py token grant <hash> LEGAL CLOUD
python scripts/mcp_cli.py token ungrant <hash> LEGAL
python scripts/mcp_cli.py token set-memories <hash>  # empty = all memories

# Promote/demote token permissions
python scripts/mcp_cli.py token promote <hash> admin,read,write  # Promote to admin
python scripts/mcp_cli.py token promote <hash> read,write         # Demote to regular
python scripts/mcp_cli.py token promote <hash> read                # Read-only
```

> **v1.6.0**: A token with `admin` permission has the same rights as the bootstrap key:
> create/revoke tokens, manage permissions, access all memories, use global diagnostics.
> **Trust chain**: bootstrap → delegated admin → sub-tokens.

---

## Shell Mode (Interactive)

```bash
python scripts/mcp_cli.py shell
```

Features: Tab completion, persistent history, `--json` on any read command.

Key commands: `about`, `health`, `list`, `use <id>`, `create <id> <onto>`, `info`, `graph`, `docs`, `ingest <path>`, `ingestdir <path>`, `entities`, `entity <name>`, `relations`, `ask <question>`, `query <question>`, `check`, `cleanup`, `tokens`, `token-create`, `backup-create`, `backup-list`, `backup-restore`, `backup-download`, `backup-delete`.

---

## Testing

Full acceptance test suite (119 tests, 7 phases, 3 token profiles):

```bash
# Direct connection (bypasses WAF rate limiting)
export MCP_URL=http://localhost:8002
export MCP_TOKEN=<admin_bootstrap_key>
python scripts/test_recette.py
```

**Phases tested:**
1. **System** — system_health, system_about, ontology_list
2. **Tokens** — CRUD, admin isolation, admin promotion, trust chain
3. **Memories** — CRUD, auto-add to token, multi-tenant isolation
4. **Documents** — ingest, list, get, delete, SHA-256 deduplication, isolation
5. **Search** — search, question_answer, memory_query, get_context, graph
6. **Backup** — backup CRUD, storage_check, storage_cleanup, isolation
7. **Cleanup** — memory_delete isolation + token cleanup

---

## Architecture

```
scripts/
├── mcp_cli.py                   # CLI entry point (Click)
├── README.md                    # Full documentation (French)
├── README.en.md                 # This file (English summary)
├── test_recette.py              # Full test suite (119 tests, 7 phases)
├── audit_ontology.py            # Ontology quality audit on a memory
├── check_param_descriptions.py  # MCP parameter descriptions checker
├── cli/                         # CLI package
│   ├── __init__.py              # Configuration (URL, token)
│   ├── client.py                # Streamable HTTP client for MCP server
│   ├── ingest_progress.py       # Real-time ingestion progress (Rich Live)
│   ├── commands.py              # Click commands (scriptable mode)
│   ├── display.py               # Rich display (tables, panels, graphs, tokens)
│   └── shell.py                 # Interactive shell (prompt_toolkit)
└── tests/                       # Test modules (acceptance tests)
    ├── __init__.py              # Test framework (helpers, counters)
    ├── test_system.py           # System tests (health, about, ontology)
    ├── test_tokens.py           # Token tests (CRUD, isolation, admin promotion)
    ├── test_memories.py         # Memory tests (CRUD, auto-add, isolation)
    ├── test_documents.py        # Document tests (ingest, list, get, delete, dedup)
    ├── test_search.py           # Search tests (search, Q&A, query, context, graph)
    ├── test_backup.py           # Backup/storage tests (CRUD, check, cleanup)
    └── test_cleanup.py          # Deletion tests + cleanup
```

---

## Exit Codes

| Code | Meaning |
| ---- | ------- |
| 0    | Success |
| 1    | Error (server, network, parameter) |

---

## Troubleshooting

```bash
# Server not responding
docker compose ps && docker compose logs mcp-memory --tail 20

# 401 Unauthorized
python scripts/mcp_cli.py --token <your_token> health

# Missing dependencies
pip install httpx click rich prompt_toolkit
```

---

*Graph Memory CLI v1.6.0 — March 2026*
