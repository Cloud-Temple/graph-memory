.PHONY: help install test run dev

PYTHON ?= python
PIP ?= pip
HOST ?= 0.0.0.0
PORT ?= 8002

help:
	@printf "Targets:\n"
	@printf "  install  Install Python dependencies from requirements.txt\n"
	@printf "  test     Run the Python test suite\n"
	@printf "  run      Start the Graph Memory MCP server\n"
	@printf "  dev      Start the server with debug enabled\n"

install:
	$(PIP) install -r requirements.txt

test:
	$(PYTHON) -m pytest scripts/tests -q

run:
	$(PYTHON) -m src.mcp_memory.server --host $(HOST) --port $(PORT)

dev:
	MCP_SERVER_DEBUG=true $(PYTHON) -m src.mcp_memory.server --host $(HOST) --port $(PORT)
