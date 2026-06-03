# -*- coding: utf-8 -*-
"""
🧠 MCP Memory CLI - Package principal.

Architecture:
    client.py   - Communication avec le serveur MCP (REST + SSE)
    commands.py - Commandes Click (health, memory, document, ask...)
    shell.py    - Shell interactif avec prompt_toolkit
    display.py  - Helpers d'affichage Rich (tables, panels)
"""

import os
from dotenv import load_dotenv

load_dotenv()

# Configuration globale
# MCP_URL et MCP_TOKEN sont prioritaires (variables explicites pour le CLI)
# Fallback : MCP_SERVER_URL et ADMIN_BOOTSTRAP_KEY (compatibilité .env)
BASE_URL = os.getenv("MCP_URL") or os.getenv("MCP_SERVER_URL", "http://localhost:8070")
TOKEN = os.getenv("MCP_TOKEN") or os.getenv("ADMIN_BOOTSTRAP_KEY", "admin_bootstrap_key_change_me")
