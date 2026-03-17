# -*- coding: utf-8 -*-
"""
Shell interactif MCP Memory avec prompt_toolkit.

Fonctionnalités :
  - Autocomplétion des commandes (Tab)
  - Historique persistant (flèches haut/bas)
  - Édition avancée (Ctrl+A/E/W, etc.)
  - Commandes de navigation dans une mémoire
  - --json disponible sur toutes les commandes

Commandes :
  --- Serveur ---
  about             Identité et capacités du service
  health            État de santé (5 services)
  whoami            Identité du token courant
  --- Mémoires ---
  list              Lister les mémoires
  use <id>          Sélectionner une mémoire
  create <id> <o>   Créer une mémoire
  update              Modifier nom/description
  info              Résumé de la mémoire courante
  graph             Graphe complet (types, relations, docs)
  delete [id]       Supprimer mémoire
  --- Documents ---
  docs              Lister les documents
  ingest <path>     Ingérer un document (--force)
  ingestdir <path>  Ingérer un répertoire (--exclude, --confirm, --force)
  deldoc <id>       Supprimer un document
  --- Exploration ---
  entities          Entités par type
  entity <nom>      Contexte d'une entité
  relations [TYPE]  Relations par type
  ask <question>    Poser une question (LLM)
  query <question>  Données structurées (sans LLM)
  --- Stockage ---
  check [id]        Vérifier cohérence S3/graphe
  cleanup           Lister orphelins S3 (--confirm pour supprimer)
  ontologies        Lister les ontologies
  --- Tokens ---
  tokens            Lister les tokens actifs
  token-create <c>  Créer un token
  token-revoke <h>  Révoquer un token
  token-update <h>  Modifier un token (--permissions, --add-memories, etc.)
  --- Backup ---
  backup-create     Créer un backup
  backup-list       Lister les backups
  backup-restore    Restaurer depuis un backup
  backup-download   Télécharger en tar.gz
  backup-delete     Supprimer un backup
  backup-restore-file  Restaurer depuis archive locale
  --- Config ---
  limit [N]         Voir/changer le limit
  debug             Activer/désactiver le debug
  clear             Effacer l'écran
  help              Aide
  exit              Quitter
  --- Options globales ---
  <cmd> --json      JSON brut sans formatage
"""

import sys
import json
import asyncio
import os
import base64
from collections import Counter

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.syntax import Syntax
from rich.markdown import Markdown

from .client import MCPClient
from .display import (
    show_memories_table, show_documents_table, show_graph_summary,
    show_ingest_result, show_error, show_success, show_warning,
    show_answer, show_query_result, show_entity_context, show_storage_check,
    show_cleanup_result, show_tokens_table, show_token_created,
    show_token_updated, show_ingest_preflight, show_entities_by_type,
    show_relations_by_type, format_size, show_json,
    show_whoami_result, show_health_result, show_about,
    show_backup_result, show_backups_table, show_restore_result,
    console
)
from .ingest_progress import run_ingest_with_progress


# =============================================================================
# Autocomplétion prompt_toolkit
# =============================================================================

# Liste des commandes du shell (alignée sur Click v2.0)
SHELL_COMMANDS = [
    "help", "about", "health", "whoami", "list", "use", "info", "graph", "docs",
    "entities", "entity", "relations", "ask", "query", "check", "cleanup",
    "create", "update", "ingest", "ingestdir", "deldoc", "ontologies",
    "tokens", "token-create", "token-revoke", "token-update",
    # Aliases legacy (appellent admin_update_token)
    "token-grant", "token-ungrant", "token-set", "token-promote", "token-set-email",
    "limit", "delete", "debug", "clear", "exit", "quit",
    "--json", "--include-documents", "--force", "--exclude", "--confirm",
    "--permissions", "--add-memories", "--remove-memories", "--set-memories", "--email",
    "backup-create", "backup-list", "backup-restore",
    "backup-download", "backup-delete", "backup-restore-file",
]


def _get_completer():
    """Crée un completer pour prompt_toolkit."""
    try:
        from prompt_toolkit.completion import WordCompleter
        return WordCompleter(SHELL_COMMANDS, ignore_case=True)
    except ImportError:
        return None


def _get_history():
    """Crée un historique persistant pour prompt_toolkit."""
    try:
        from prompt_toolkit.history import FileHistory
        history_path = os.path.expanduser("~/.mcp_memory_history")
        return FileHistory(history_path)
    except ImportError:
        return None


def _prompt_input(prompt_text: str, completer=None, history=None) -> str:
    """
    Lit une ligne avec prompt_toolkit si disponible, sinon fallback input().

    Fonctionnalités :
      - Tab : autocomplétion des commandes
      - ↑/↓ : historique
      - Ctrl+A/E : début/fin de ligne
      - Ctrl+W : supprimer mot
      - Ctrl+C : annuler la ligne
    """
    try:
        from prompt_toolkit import prompt as pt_prompt
        from prompt_toolkit.formatted_text import HTML
        return pt_prompt(
            HTML(prompt_text),
            completer=completer,
            history=history,
            complete_while_typing=False,
        )
    except ImportError:
        # Fallback sans prompt_toolkit
        return input(prompt_text.replace("<b>", "").replace("</b>", ""))


# =============================================================================
# Résolution du memory_id
# =============================================================================

def _resolve_memory_id(candidate: str, known_ids: list) -> str:
    """
    Extrait le memory_id valide d'une saisie utilisateur.

    Gère les cas où l'utilisateur copie la ligne entière du tableau
    (ex: "JURIDIQUE – Corpus Juridique Cloud Temple" → "JURIDIQUE").
    """
    candidate = candidate.strip().strip('"').strip("'")

    # Essayer de couper avant un séparateur
    for sep in [" – ", " - ", "  "]:
        if sep in candidate:
            candidate = candidate.split(sep)[0].strip()
            break

    # Vérifier dans les IDs connus
    if candidate in known_ids:
        return candidate

    # Recherche partielle (case insensitive)
    for kid in known_ids:
        if kid.lower() == candidate.lower():
            return kid

    return candidate  # Retourner tel quel si pas trouvé


# =============================================================================
# Helper JSON
# =============================================================================

def _json_or_show(result: dict, json_output: bool, on_success, ok_statuses=("ok",)):
    """Affiche en JSON brut ou appelle on_success selon le flag.
    
    Helper unifié pour tous les handlers.
    """
    if json_output:
        show_json(result)
    elif result.get("status") in ok_statuses:
        on_success(result)
    else:
        show_error(result.get("message", f"Erreur: {result.get('status', '?')}"))


# =============================================================================
# Handlers de commandes — Serveur
# =============================================================================

async def cmd_about(client: MCPClient, state: dict, json_output: bool = False):
    """Affiche l'identité et les capacités du service MCP Memory."""
    result = await client.call_tool("system_about", {})
    _json_or_show(result, json_output, show_about)


async def cmd_health(client: MCPClient, state: dict, json_output: bool = False):
    """Vérifie l'état de santé des 5 services (S3, Neo4j, LLMaaS, Qdrant, Embedding)."""
    result = await client.call_tool("system_health", {})
    _json_or_show(result, json_output, show_health_result, ok_statuses=("ok", "healthy", "error"))


async def cmd_whoami(client: MCPClient, state: dict, json_output: bool = False):
    """Affiche l'identité du token courant (permissions, mémoires, email)."""
    result = await client.call_tool("system_whoami", {})
    _json_or_show(result, json_output, show_whoami_result)


# =============================================================================
# Handlers de commandes — Mémoires
# =============================================================================

async def cmd_list(client: MCPClient, state: dict, json_output: bool = False):
    """Liste les mémoires."""
    result = await client.list_memories()
    if json_output:
        show_json(result)
        return
    if result.get("status") == "ok":
        show_memories_table(result.get("memories", []), state.get("memory"))
    else:
        show_error(result.get("message", "Erreur"))


async def cmd_use(client: MCPClient, state: dict, args: str):
    """Sélectionne une mémoire (avec validation)."""
    if not args:
        show_warning("Usage: use <memory_id>")
        return

    result = await client.list_memories()
    if result.get("status") != "ok":
        state["memory"] = args
        console.print(f"[green]✓[/green] Mémoire: [cyan]{args}[/cyan] (non validée)")
        return

    known_ids = [m["id"] for m in result.get("memories", [])]
    resolved = _resolve_memory_id(args, known_ids)

    if resolved in known_ids:
        state["memory"] = resolved
        mem_info = next((m for m in result["memories"] if m["id"] == resolved), {})
        console.print(
            f"[green]✓[/green] Mémoire: [cyan bold]{resolved}[/cyan bold]"
            f" ({mem_info.get('name', '')})"
        )
    else:
        show_error(f"Mémoire '{resolved}' non trouvée.")
        console.print(f"[dim]Disponibles: {', '.join(known_ids)}[/dim]")


async def cmd_info(client: MCPClient, state: dict, json_output: bool = False):
    """Affiche les infos de la mémoire courante."""
    mem = state.get("memory")
    if not mem:
        show_warning("Sélectionnez une mémoire avec 'use <id>'")
        return

    result = await client.get_graph(mem)
    if json_output:
        show_json(result)
        return
    if result.get("status") == "ok":
        console.print(f"[bold]Mémoire:[/bold] [cyan]{mem}[/cyan]")
        console.print(f"  Entités:   [green]{result.get('node_count', 0)}[/green]")
        console.print(f"  Relations: [green]{result.get('edge_count', 0)}[/green]")
        console.print(f"  Documents: [green]{result.get('document_count', 0)}[/green]")
    else:
        show_error(result.get("message", "Erreur"))


async def cmd_graph(client: MCPClient, state: dict, args: str, json_output: bool = False):
    """Affiche le graphe complet de la mémoire."""
    mem = args or state.get("memory")
    if not mem:
        show_warning("Usage: graph [memory_id] ou 'use' d'abord")
        return

    result = await client.get_graph(mem)
    if json_output:
        show_json(result)
        return
    if result.get("status") == "ok":
        show_graph_summary(result, mem)
    else:
        show_error(result.get("message", "Erreur"))


async def cmd_create(client: MCPClient, state: dict, args: str, json_output: bool = False):
    """
    Crée une nouvelle mémoire.
    
    Usage: create <memory_id> <ontology> [nom] [description]
    Exemple: create JURIDIQUE legal "Corpus Juridique" "Documents contractuels"
    """
    if not args:
        show_warning("Usage: create <memory_id> <ontology> [nom] [description]")
        console.print("[dim]Exemple: create JURIDIQUE legal \"Corpus Juridique\"[/dim]")
        return

    parts = args.split(maxsplit=3)
    if len(parts) < 2:
        show_warning("Usage: create <memory_id> <ontology> [nom] [description]")
        return

    memory_id = parts[0]
    ontology = parts[1]
    name = parts[2].strip('"').strip("'") if len(parts) > 2 else memory_id
    description = parts[3].strip('"').strip("'") if len(parts) > 3 else ""

    result = await client.call_tool("memory_create", {
        "memory_id": memory_id,
        "name": name,
        "description": description,
        "ontology": ontology,
    })
    if json_output:
        show_json(result)
        return
    if result.get("status") in ("ok", "created"):
        show_success(f"Mémoire '{memory_id}' créée (ontologie: {result.get('ontology')})")
        state["memory"] = memory_id
        console.print(f"[green]✓[/green] Mémoire sélectionnée: [cyan bold]{memory_id}[/cyan bold]")
    else:
        show_error(result.get("message", str(result)))


async def cmd_update(client: MCPClient, state: dict, args: str, json_output: bool = False):
    """
    Modifie le nom ou la description d'une mémoire.
    
    Usage: update [memory_id] [--name "Nouveau nom"] [--description "Nouvelle desc"]
    
    Sans memory_id, utilise la mémoire courante (sélectionnée avec 'use').
    
    Exemples:
        update --name "Corpus Juridique v2"
        update --description "Documents contractuels CT"
        update --name "Nouveau nom" --description "Nouvelle desc"
        update JURIDIQUE --name "Nouveau nom"
    """
    import shlex

    if not args:
        show_warning("Usage: update [memory_id] --name \"...\" --description \"...\"")
        console.print("[dim]Exemples:[/dim]")
        console.print("[dim]  update --name \"Nouveau nom\"[/dim]")
        console.print("[dim]  update --description \"Nouvelle description\"[/dim]")
        console.print("[dim]  update JURIDIQUE --name \"Nom\" --description \"Desc\"[/dim]")
        return

    try:
        tokens_list = shlex.split(args)
    except ValueError as e:
        show_error(f"Erreur de syntaxe: {e}")
        return

    # Parser les flags
    name = None
    description = None
    positional = []
    i = 0
    while i < len(tokens_list):
        tok = tokens_list[i]
        if tok in ("--name", "-n"):
            if i + 1 < len(tokens_list):
                i += 1
                name = tokens_list[i]
            else:
                show_warning("--name nécessite une valeur")
                return
        elif tok in ("--description", "-d"):
            if i + 1 < len(tokens_list):
                i += 1
                description = tokens_list[i]
            else:
                show_warning("--description nécessite une valeur")
                return
        elif tok.startswith("--"):
            show_error(f"Option inconnue: {tok}. Options valides: --name, --description")
            return
        else:
            positional.append(tok)
        i += 1

    # Résoudre le memory_id
    mem = positional[0] if positional else state.get("memory")
    if not mem:
        show_warning("Sélectionnez une mémoire avec 'use <id>' ou spécifiez l'ID: update <memory_id> ...")
        return

    if not name and not description:
        show_error("Rien à modifier. Utilisez --name et/ou --description.")
        return

    api_args = {"memory_id": mem}
    if name:
        api_args["name"] = name
    if description:
        api_args["description"] = description

    result = await client.call_tool("memory_update", api_args)
    _json_or_show(result, json_output,
                  lambda r: show_success(
                      f"Mémoire '{mem}' mise à jour: {r.get('name', '')} — {r.get('description', '')}"))


async def cmd_delete(client: MCPClient, state: dict, args: str, json_output: bool = False):
    """Supprime une mémoire."""
    from rich.prompt import Confirm

    mem = args or state.get("memory")
    if not mem:
        show_warning("Usage: delete <memory_id>")
        return

    if not Confirm.ask(f"[yellow]Supprimer la mémoire '{mem}' ?[/yellow]"):
        console.print("[dim]Annulé.[/dim]")
        return

    result = await client.call_tool("memory_delete", {"memory_id": mem})
    if json_output:
        show_json(result)
        return
    if result.get("status") in ("ok", "deleted"):
        show_success(f"Mémoire '{mem}' supprimée")
        if mem == state.get("memory"):
            state["memory"] = None
    else:
        show_error(result.get("message", str(result)))


# =============================================================================
# Handlers de commandes — Documents
# =============================================================================

async def cmd_docs(client: MCPClient, state: dict, json_output: bool = False):
    """Liste les documents de la mémoire courante."""
    mem = state.get("memory")
    if not mem:
        show_warning("Sélectionnez une mémoire avec 'use <id>'")
        return

    result = await client.get_graph(mem)
    if json_output:
        show_json({"status": "ok", "documents": result.get("documents", [])})
        return
    if result.get("status") == "ok":
        show_documents_table(result.get("documents", []), mem)
    else:
        show_error(result.get("message", "Erreur"))


async def cmd_ingest(client: MCPClient, state: dict, args: str, json_output: bool = False):
    """
    Ingère un document dans la mémoire courante.
    
    Usage: ingest <chemin_fichier> [--force]
    
    Affiche une progression en temps réel :
    - Phase courante (S3, texte, extraction LLM, Neo4j, chunking, embedding, Qdrant)
    - Barres de progression pour extraction LLM et embedding
    - Compteurs entités/relations en temps réel
    """
    mem = state.get("memory")
    if not mem:
        show_warning("Sélectionnez une mémoire avec 'use <id>' avant d'ingérer")
        return
    if not args:
        show_warning("Usage: ingest <chemin_fichier> [--force]")
        return

    force = "--force" in args
    file_path = args.replace("--force", "").strip()

    if not os.path.isfile(file_path):
        show_error(f"Fichier non trouvé: {file_path}")
        return

    filename = os.path.basename(file_path)
    file_size = os.path.getsize(file_path)
    file_ext = filename.lower().rsplit('.', 1)[-1] if '.' in filename else '?'

    # Affichage pré-vol (partagé)
    if not json_output:
        show_ingest_preflight(filename, file_size, file_ext, mem, force)

    try:
        from datetime import datetime, timezone

        with open(file_path, "rb") as f:
            content_bytes = f.read()
        content_b64 = base64.b64encode(content_bytes).decode("utf-8")

        # Métadonnées enrichies
        source_path = os.path.abspath(file_path)
        mtime = os.path.getmtime(file_path)
        source_modified_at = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()

        # Progression temps réel (partagée via ingest_progress.py)
        result = await run_ingest_with_progress(client, {
            "memory_id": mem,
            "content_base64": content_b64,
            "filename": filename,
            "force": force,
            "source_path": source_path,
            "source_modified_at": source_modified_at,
        })

        if json_output:
            show_json(result)
        elif result.get("status") == "ok":
            show_ingest_result(result)
        elif result.get("status") == "already_exists":
            console.print(f"[yellow]⚠️ Déjà ingéré: {result.get('document_id')} (--force pour réingérer)[/yellow]")
        else:
            show_error(result.get("message", str(result)))
    except Exception as e:
        show_error(str(e))


async def cmd_ingestdir(client: MCPClient, state: dict, args: str, json_output: bool = False):
    """
    Ingère un répertoire entier dans la mémoire courante (récursif).
    
    Usage: ingestdir <chemin> [--exclude PATTERN]... [--confirm] [--force]
    
    Exemples:
        ingestdir ./DOCS
        ingestdir DOCS --exclude "llmaas/licences/*" --exclude "*changelog*"
        ingestdir DOCS --exclude "*.tmp" --force
    """
    import fnmatch
    import shlex
    from pathlib import Path
    from rich.prompt import Confirm

    SUPPORTED_EXTENSIONS = {".txt", ".md", ".html", ".docx", ".pdf", ".csv"}

    mem = state.get("memory")
    if not mem:
        show_warning("Sélectionnez une mémoire avec 'use <id>' avant d'ingérer")
        return
    if not args:
        show_warning("Usage: ingestdir <chemin> [--exclude PATTERN]... [--confirm] [--force]")
        return

    # Parser robuste avec shlex (gère les guillemets et espaces)
    try:
        tokens = shlex.split(args)
    except ValueError as e:
        show_error(f"Erreur de syntaxe dans la commande: {e}")
        return

    confirm_mode = False
    force_mode = False
    exclude_patterns = []
    positional = []
    
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok == "--confirm":
            confirm_mode = True
        elif tok == "--force":
            force_mode = True
        elif tok == "--exclude":
            if i + 1 < len(tokens):
                i += 1
                exclude_patterns.append(tokens[i])
            else:
                show_warning("--exclude nécessite un PATTERN (ex: --exclude '*.tmp')")
                return
        elif tok.startswith("--"):
            show_error(f"Option inconnue: {tok}. Options valides: --exclude, --confirm, --force")
            return
        else:
            positional.append(tok)
        i += 1
    
    dir_path = positional[0] if positional else ""
    
    if not dir_path:
        show_warning("Usage: ingestdir <chemin> [--exclude PATTERN]... [--confirm] [--force]")
        return
    
    if not os.path.isdir(dir_path):
        show_error(f"Répertoire non trouvé: {dir_path}")
        return

    # --- 1. Scanner ---
    if not json_output:
        console.print(f"[dim]📁 Scan de {dir_path}...[/dim]")
    all_files = []
    excluded_files = []
    unsupported_files = []

    for root, dirs, files in os.walk(dir_path):
        for fname in sorted(files):
            fpath = os.path.join(root, fname)
            rel_path = os.path.relpath(fpath, dir_path)

            is_excluded = False
            for pattern in exclude_patterns:
                if fnmatch.fnmatch(rel_path, pattern) or fnmatch.fnmatch(fname, pattern):
                    is_excluded = True
                    break
            if is_excluded:
                excluded_files.append(rel_path)
                continue

            ext = Path(fname).suffix.lower()
            if ext not in SUPPORTED_EXTENSIONS:
                unsupported_files.append(rel_path)
                continue

            all_files.append({
                "path": fpath,
                "rel_path": rel_path,
                "filename": fname,
                "size": os.path.getsize(fpath),
            })

    if not all_files:
        if json_output:
            show_json({"status": "ok", "message": "Aucun fichier supporté", "files": 0})
        else:
            show_warning(f"Aucun fichier supporté dans {dir_path}")
            if unsupported_files:
                console.print(f"[dim]{len(unsupported_files)} fichiers non supportés ignorés[/dim]")
        return

    # --- 2. Vérifier les doublons ---
    graph_result = await client.get_graph(mem)
    existing = set()
    if graph_result.get("status") == "ok":
        for d in graph_result.get("documents", []):
            existing.add(d.get("filename", ""))

    to_ingest = []
    already = []
    for f in all_files:
        if f["filename"] in existing and not force_mode:
            already.append(f)
        else:
            to_ingest.append(f)

    # --- 3. Résumé ---
    total_size = sum(f["size"] for f in to_ingest)

    if not json_output:
        console.print(Panel.fit(
            f"[bold]Répertoire:[/bold]  [cyan]{os.path.abspath(dir_path)}[/cyan]\n"
            f"[bold]Mémoire:[/bold]     [cyan]{mem}[/cyan]\n\n"
            f"[bold]Fichiers trouvés:[/bold]  [green]{len(all_files)}[/green]"
            + (f"  [yellow]Exclus: {len(excluded_files)}[/yellow]" if excluded_files else "")
            + (f"  [dim]Non supportés: {len(unsupported_files)}[/dim]" if unsupported_files else "")
            + (f"  [yellow]Déjà ingérés: {len(already)}[/yellow]" if already else "")
            + f"\n[bold]À ingérer:[/bold]      [green bold]{len(to_ingest)}[/green bold]",
            title="📁 Import en masse",
            border_style="blue",
        ))

    if not to_ingest:
        if json_output:
            show_json({"status": "ok", "message": "Tous les fichiers sont déjà ingérés", "ingested": 0})
        else:
            show_success("Tous les fichiers sont déjà ingérés !")
        return

    # Liste
    if not json_output:
        for i, f in enumerate(to_ingest, 1):
            console.print(f"  [dim]{i}.[/dim] {f['rel_path']}")

    # --- 4. Ingestion ---
    ingested = 0
    skipped = 0
    errors = 0
    results_list = []

    for i, f in enumerate(to_ingest, 1):
        if confirm_mode and not json_output:
            from rich.prompt import Confirm as ConfirmPrompt
            if not ConfirmPrompt.ask(f"[{i}/{len(to_ingest)}] Ingérer [cyan]{f['rel_path']}[/cyan] ?"):
                skipped += 1
                continue

        file_size = f["size"]
        if not json_output:
            console.print(f"\n[bold cyan][{i}/{len(to_ingest)}][/bold cyan] 📥 [bold]{f['rel_path']}[/bold] ({format_size(file_size)})")
        try:
            from datetime import datetime, timezone

            with open(f["path"], "rb") as fh:
                content_bytes = fh.read()
            content_b64 = base64.b64encode(content_bytes).decode("utf-8")
            
            mtime = os.path.getmtime(f["path"])
            source_modified_at = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()

            result = await run_ingest_with_progress(client, {
                "memory_id": mem,
                "content_base64": content_b64,
                "filename": f["filename"],
                "force": force_mode,
                "source_path": f["rel_path"],
                "source_modified_at": source_modified_at,
            })

            if result.get("status") == "ok":
                elapsed = result.get("_elapsed_seconds", 0)
                e_new = result.get("entities_created", 0)
                e_merged = result.get("entities_merged", 0)
                r_new = result.get("relations_created", 0)
                r_merged = result.get("relations_merged", 0)
                if not json_output:
                    console.print(
                        f"  [green]✅[/green] {f['filename']}: "
                        f"[cyan]{e_new}+{e_merged}[/cyan] entités, "
                        f"[cyan]{r_new}+{r_merged}[/cyan] relations "
                        f"[dim]({elapsed}s)[/dim]"
                    )
                ingested += 1
                results_list.append({"file": f["filename"], "status": "ok"})
            elif result.get("status") == "already_exists":
                if not json_output:
                    console.print(f"  [yellow]⏭️[/yellow] {f['filename']}: déjà ingéré")
                skipped += 1
                results_list.append({"file": f["filename"], "status": "already_exists"})
            else:
                if not json_output:
                    console.print(f"  [red]❌[/red] {f['filename']}: {result.get('message', '?')}")
                errors += 1
                results_list.append({"file": f["filename"], "status": "error", "message": result.get("message", "?")})
        except Exception as e:
            if not json_output:
                console.print(f"  [red]❌[/red] {f['filename']}: {e}")
            errors += 1
            results_list.append({"file": f["filename"], "status": "error", "message": str(e)})

    # --- 5. Résumé final ---
    if json_output:
        show_json({"status": "ok", "ingested": ingested, "skipped": skipped, "errors": errors, "files": results_list})
    else:
        console.print(Panel.fit(
            f"[green]✅ Ingérés: {ingested}[/green]  "
            f"[yellow]⏭️ Skippés: {skipped}[/yellow]  "
            f"[red]❌ Erreurs: {errors}[/red]",
            title="📊 Résultat",
            border_style="green" if errors == 0 else "yellow",
        ))


async def cmd_deldoc(client: MCPClient, state: dict, args: str, json_output: bool = False):
    """
    Supprime un document de la mémoire courante.
    
    Usage: deldoc <document_id>
    """
    from rich.prompt import Confirm

    mem = state.get("memory")
    if not mem:
        show_warning("Sélectionnez une mémoire avec 'use <id>'")
        return
    if not args:
        show_warning("Usage: deldoc <document_id>")
        console.print("[dim]Utilisez 'docs' pour voir les IDs des documents.[/dim]")
        return

    doc_id = args.strip()
    if not json_output:
        if not Confirm.ask(f"[yellow]Supprimer le document '{doc_id}' de '{mem}' ?[/yellow]"):
            console.print("[dim]Annulé.[/dim]")
            return

    result = await client.call_tool("document_delete", {
        "memory_id": mem, "document_id": doc_id
    })
    if json_output:
        show_json(result)
    elif result.get("status") in ("ok", "deleted"):
        show_success(f"Document supprimé ({result.get('entities_deleted', 0)} entités orphelines nettoyées)")
    else:
        show_error(result.get("message", str(result)))


# =============================================================================
# Handlers de commandes — Exploration
# =============================================================================

async def cmd_entities(client: MCPClient, state: dict, json_output: bool = False):
    """Affiche les entités par type avec leurs documents sources."""
    mem = state.get("memory")
    if not mem:
        show_warning("Sélectionnez une mémoire avec 'use <id>'")
        return

    result = await client.get_graph(mem)
    if json_output:
        show_json(result)
        return
    if result.get("status") != "ok":
        show_error(result.get("message", "Erreur"))
        return

    show_entities_by_type(result)


async def cmd_entity(client: MCPClient, state: dict, args: str, json_output: bool = False):
    """Affiche le contexte d'une entité."""
    mem = state.get("memory")
    if not mem:
        show_warning("Sélectionnez une mémoire avec 'use <id>'")
        return
    if not args:
        show_warning("Usage: entity <nom de l'entité>")
        return

    result = await client.call_tool("memory_get_context", {
        "memory_id": mem, "entity_name": args, "depth": 1
    })
    _json_or_show(result, json_output, show_entity_context)


async def cmd_relations(client: MCPClient, state: dict, args: str = "", json_output: bool = False):
    """
    Affiche les relations. Sans argument : résumé par type.
    Avec un type en argument : détail de toutes les relations de ce type.
    
    Exemples :
        relations              → résumé par type
        relations MENTIONS     → toutes les relations MENTIONS
        relations HAS_AMOUNT   → toutes les relations HAS_AMOUNT
    """
    mem = state.get("memory")
    if not mem:
        show_warning("Sélectionnez une mémoire avec 'use <id>'")
        return

    result = await client.get_graph(mem)
    if json_output:
        show_json(result)
        return
    if result.get("status") != "ok":
        show_error(result.get("message", "Erreur"))
        return

    type_filter = args.strip().upper() if args.strip() else None
    show_relations_by_type(result, type_filter=type_filter)


async def cmd_ask(client: MCPClient, state: dict, args: str, debug: bool, json_output: bool = False):
    """Pose une question sur la mémoire courante."""
    mem = state.get("memory")
    if not mem:
        show_warning("Sélectionnez une mémoire avec 'use <id>'")
        return
    if not args:
        show_warning("Usage: ask <votre question>")
        return

    limit = state.get("limit", 10)
    result = await client.call_tool("question_answer", {
        "memory_id": mem, "question": args, "limit": limit
    })

    if json_output:
        show_json(result)
        return

    if debug:
        console.print(Syntax(json.dumps(result, indent=2, ensure_ascii=False), "json"))

    if result.get("status") == "ok":
        show_answer(
            result.get("answer", ""),
            result.get("entities", []),
            result.get("source_documents", []),
        )
    else:
        show_error(result.get("message", "Erreur"))


async def cmd_query(client: MCPClient, state: dict, args: str, debug: bool, json_output: bool = False):
    """Interroge la mémoire courante et retourne les données structurées (sans LLM)."""
    mem = state.get("memory")
    if not mem:
        show_warning("Sélectionnez une mémoire avec 'use <id>'")
        return
    if not args:
        show_warning("Usage: query <votre requête>")
        return

    limit = state.get("limit", 10)
    result = await client.call_tool("memory_query", {
        "memory_id": mem, "query": args, "limit": limit
    })

    if json_output:
        show_json(result)
        return

    if debug:
        console.print(Syntax(json.dumps(result, indent=2, ensure_ascii=False), "json"))

    if result.get("status") == "ok":
        show_query_result(result)
    else:
        show_error(result.get("message", "Erreur"))


# =============================================================================
# Handlers de commandes — Stockage
# =============================================================================

async def cmd_check(client: MCPClient, state: dict, args: str, json_output: bool = False):
    """
    Vérifie la cohérence S3 / graphe.
    
    Sans argument : vérifie toutes les mémoires.
    Avec un memory_id : vérifie uniquement cette mémoire.
    """
    params = {}
    if args.strip():
        params["memory_id"] = args.strip()
    elif state.get("memory"):
        params["memory_id"] = state["memory"]
    
    if not json_output:
        console.print("[dim]🔍 Vérification S3 en cours...[/dim]")
    result = await client.call_tool("storage_check", params)
    _json_or_show(result, json_output, show_storage_check)


async def cmd_cleanup(client: MCPClient, state: dict, confirm: bool = False, json_output: bool = False):
    """
    Nettoie les fichiers orphelins sur S3.
    
    confirm=False : dry run (liste seulement).
    confirm=True : supprime réellement.
    """
    if not json_output:
        console.print("[dim]🧹 Analyse des orphelins S3...[/dim]")
    result = await client.call_tool("storage_cleanup", {"dry_run": not confirm})
    _json_or_show(result, json_output, show_cleanup_result)


async def cmd_ontologies(client: MCPClient, state: dict, json_output: bool = False):
    """Liste les ontologies disponibles."""
    result = await client.call_tool("ontology_list", {})
    if json_output:
        show_json(result)
        return
    if result.get("status") == "ok":
        ontologies = result.get("ontologies", [])
        table = Table(title=f"📖 Ontologies ({len(ontologies)})")
        table.add_column("Nom", style="cyan")
        table.add_column("Description", style="white")
        table.add_column("Types", style="dim")
        for o in ontologies:
            table.add_row(
                o.get("name", ""),
                o.get("description", "")[:50],
                f"{o.get('entity_types_count', 0)} entités, {o.get('relation_types_count', 0)} relations"
            )
        console.print(table)
    else:
        show_error(result.get("message", "Erreur"))


# =============================================================================
# Handlers token — v2.0 : token-update unifié + aliases legacy
# =============================================================================

async def cmd_tokens(client: MCPClient, state: dict, json_output: bool = False):
    """Liste tous les tokens actifs."""
    result = await client.call_tool("admin_list_tokens", {})
    _json_or_show(result, json_output, lambda r: show_tokens_table(r.get("tokens", [])))


async def cmd_token_create(client: MCPClient, state: dict, args: str, json_output: bool = False):
    """
    Crée un token pour un client.

    Usage: token-create <client_name> [perms] [memories] [--email addr] [--expires N]
    Exemples:
        token-create quoteflow
        token-create quoteflow --email user@example.com
        token-create quoteflow read,write JURIDIQUE,CLOUD --email user@example.com
        token-create admin-bot admin --expires 30
    """
    if not args:
        show_warning("Usage: token-create <client_name> [permissions] [memories] [--email addr] [--expires N]")
        console.print("[dim]Exemples:[/dim]")
        console.print("[dim]  token-create quoteflow[/dim]")
        console.print("[dim]  token-create quoteflow --email user@example.com[/dim]")
        console.print("[dim]  token-create quoteflow read,write JURIDIQUE,CLOUD[/dim]")
        console.print("[dim]  token-create admin-bot admin --expires 30[/dim]")
        return

    import shlex
    try:
        tokens_list = shlex.split(args)
    except ValueError as e:
        show_error(f"Erreur de syntaxe: {e}")
        return

    # Extraire les flags
    email = None
    expires = None
    positional = []
    i = 0
    while i < len(tokens_list):
        tok = tokens_list[i]
        if tok == "--email":
            if i + 1 < len(tokens_list):
                i += 1
                email = tokens_list[i]
            else:
                show_warning("--email nécessite une adresse")
                return
        elif tok == "--expires":
            if i + 1 < len(tokens_list):
                i += 1
                try:
                    expires = int(tokens_list[i])
                except ValueError:
                    show_error("--expires attend un nombre de jours")
                    return
            else:
                show_warning("--expires nécessite un nombre de jours")
                return
        elif tok.startswith("--"):
            show_error(f"Option inconnue: {tok}. Options valides: --email, --expires")
            return
        else:
            positional.append(tok)
        i += 1

    if not positional:
        show_warning("Usage: token-create <client_name> [permissions] [memories]")
        return

    client_name = positional[0]
    perms = positional[1].split(",") if len(positional) > 1 else ["read", "write"]
    memories = positional[2].split(",") if len(positional) > 2 else []

    # Validation des permissions
    valid_perms = {"read", "write", "admin"}
    invalid = [p for p in perms if p not in valid_perms]
    if invalid:
        show_error(f"Permissions invalides: {invalid}. Valides: read, write, admin")
        return

    params = {
        "client_name": client_name,
        "permissions": perms,
        "memory_ids": memories,
    }
    if email:
        params["email"] = email
    if expires:
        params["expires_in_days"] = expires

    result = await client.call_tool("admin_create_token", params)
    _json_or_show(result, json_output, show_token_created)


async def cmd_token_revoke(client: MCPClient, state: dict, args: str, json_output: bool = False):
    """Révoque un token par préfixe de hash."""
    from rich.prompt import Confirm

    if not args:
        show_warning("Usage: token-revoke <hash_prefix>")
        console.print("[dim]Utilisez 'tokens' pour voir les préfixes de hash.[/dim]")
        return

    hash_prefix = args.strip()
    if not json_output:
        if not Confirm.ask(f"[yellow]Révoquer le token '{hash_prefix[:12]}...' ?[/yellow]"):
            console.print("[dim]Annulé.[/dim]")
            return

    result = await client.call_tool("admin_revoke_token", {"token_hash_prefix": hash_prefix})
    _json_or_show(result, json_output, lambda r: show_success(r.get("message", "Token révoqué")))


async def cmd_token_update(client: MCPClient, state: dict, args: str, json_output: bool = False):
    """
    Modifie un token (permissions, mémoires, email).
    
    C'est la commande unifiée v2.0 qui remplace grant/ungrant/set/promote/set-email.

    Usage: token-update <hash_prefix> [options]
    Options:
        --permissions <p>       Nouvelles permissions (read,write,admin)
        --add-memories <m>      Ajouter des mémoires (séparées par virgules)
        --remove-memories <m>   Retirer des mémoires
        --set-memories <m>      Remplacer les mémoires (vide=toutes)
        --email <e>             Modifier l'email

    Exemples:
        token-update abc12 --permissions admin,read,write
        token-update abc12 --add-memories JURIDIQUE,CLOUD
        token-update abc12 --remove-memories CLOUD
        token-update abc12 --set-memories JURIDIQUE,CLOUD
        token-update abc12 --set-memories ""
        token-update abc12 --email user@example.com
    """
    if not args:
        show_warning("Usage: token-update <hash_prefix> [options]")
        console.print("[dim]Options:[/dim]")
        console.print("[dim]  --permissions <perms>       Permissions (read,write,admin)[/dim]")
        console.print("[dim]  --add-memories <mems>       Ajouter des mémoires[/dim]")
        console.print("[dim]  --remove-memories <mems>    Retirer des mémoires[/dim]")
        console.print("[dim]  --set-memories <mems>       Remplacer les mémoires (\"\"=toutes)[/dim]")
        console.print("[dim]  --email <addr>              Modifier l'email[/dim]")
        return

    import shlex
    try:
        tokens_list = shlex.split(args)
    except ValueError as e:
        show_error(f"Erreur de syntaxe: {e}")
        return

    if not tokens_list:
        show_warning("Usage: token-update <hash_prefix> [options]")
        return

    hash_prefix = tokens_list[0]
    api_args = {"token_hash_prefix": hash_prefix}
    has_update = False

    i = 1
    while i < len(tokens_list):
        tok = tokens_list[i]
        if tok == "--permissions":
            if i + 1 < len(tokens_list):
                i += 1
                api_args["set_permissions"] = [p.strip() for p in tokens_list[i].split(",") if p.strip()]
                has_update = True
            else:
                show_warning("--permissions nécessite une valeur (ex: read,write,admin)")
                return
        elif tok == "--add-memories":
            if i + 1 < len(tokens_list):
                i += 1
                api_args["add_memories"] = [m.strip() for m in tokens_list[i].split(",") if m.strip()]
                has_update = True
            else:
                show_warning("--add-memories nécessite une valeur")
                return
        elif tok == "--remove-memories":
            if i + 1 < len(tokens_list):
                i += 1
                api_args["remove_memories"] = [m.strip() for m in tokens_list[i].split(",") if m.strip()]
                has_update = True
            else:
                show_warning("--remove-memories nécessite une valeur")
                return
        elif tok == "--set-memories":
            if i + 1 < len(tokens_list):
                i += 1
                val = tokens_list[i]
                api_args["set_memories"] = [m.strip() for m in val.split(",") if m.strip()] if val else []
                has_update = True
            else:
                # --set-memories sans valeur = accès à toutes
                api_args["set_memories"] = []
                has_update = True
        elif tok == "--email":
            if i + 1 < len(tokens_list):
                i += 1
                api_args["set_email"] = tokens_list[i]
                has_update = True
            else:
                show_warning("--email nécessite une adresse")
                return
        elif tok.startswith("--"):
            show_error(f"Option inconnue: {tok}")
            console.print("[dim]Options valides: --permissions, --add-memories, --remove-memories, --set-memories, --email[/dim]")
            return
        else:
            show_error(f"Argument inattendu: {tok}")
            return
        i += 1

    if not has_update:
        show_error("Rien à modifier. Utilisez --permissions, --add-memories, --remove-memories, --set-memories ou --email.")
        return

    result = await client.call_tool("admin_update_token", api_args)
    _json_or_show(result, json_output, show_token_updated)


# --- Aliases legacy (appellent admin_update_token en interne) ---

async def cmd_token_grant(client: MCPClient, state: dict, args: str, json_output: bool = False):
    """[ALIAS] → token-update <hash> --add-memories <mems>"""
    if not args or len(args.split()) < 2:
        show_warning("Usage: token-grant <hash_prefix> <memory1> [memory2] ...")
        console.print("[dim]💡 Préférez: token-update <hash> --add-memories mem1,mem2[/dim]")
        return
    parts = args.split()
    await cmd_token_update(client, state, f"{parts[0]} --add-memories {','.join(parts[1:])}", json_output)


async def cmd_token_ungrant(client: MCPClient, state: dict, args: str, json_output: bool = False):
    """[ALIAS] → token-update <hash> --remove-memories <mems>"""
    if not args or len(args.split()) < 2:
        show_warning("Usage: token-ungrant <hash_prefix> <memory1> [memory2] ...")
        console.print("[dim]💡 Préférez: token-update <hash> --remove-memories mem1,mem2[/dim]")
        return
    parts = args.split()
    await cmd_token_update(client, state, f"{parts[0]} --remove-memories {','.join(parts[1:])}", json_output)


async def cmd_token_set(client: MCPClient, state: dict, args: str, json_output: bool = False):
    """[ALIAS] → token-update <hash> --set-memories <mems>"""
    if not args:
        show_warning("Usage: token-set <hash_prefix> [memory1] [memory2] ...")
        console.print("[dim]💡 Préférez: token-update <hash> --set-memories mem1,mem2[/dim]")
        return
    parts = args.split()
    memories = ",".join(parts[1:]) if len(parts) > 1 else '""'
    await cmd_token_update(client, state, f'{parts[0]} --set-memories {memories}', json_output)


async def cmd_token_promote(client: MCPClient, state: dict, args: str, json_output: bool = False):
    """[ALIAS] → token-update <hash> --permissions <perms>"""
    if not args or len(args.split()) < 2:
        show_warning("Usage: token-promote <hash_prefix> <permissions>")
        console.print("[dim]💡 Préférez: token-update <hash> --permissions read,write,admin[/dim]")
        return
    parts = args.split()
    await cmd_token_update(client, state, f"{parts[0]} --permissions {parts[1]}", json_output)


async def cmd_token_set_email(client: MCPClient, state: dict, args: str, json_output: bool = False):
    """[ALIAS] → token-update <hash> --email <addr>"""
    if not args or len(args.split()) < 2:
        show_warning("Usage: token-set-email <hash_prefix> <email>")
        console.print("[dim]💡 Préférez: token-update <hash> --email user@example.com[/dim]")
        return
    parts = args.split()
    await cmd_token_update(client, state, f"{parts[0]} --email {parts[1]}", json_output)


# =============================================================================
# Handlers backup
# =============================================================================

async def cmd_backup_create(client: MCPClient, state: dict, args: str, json_output: bool = False):
    """Crée un backup de la mémoire courante ou spécifiée."""
    parts = args.split(maxsplit=1) if args else []
    mem = parts[0] if parts else state.get("memory")
    description = parts[1].strip('"').strip("'") if len(parts) > 1 else None
    
    if not mem:
        show_warning("Usage: backup-create [memory_id] [description]")
        return
    
    if not json_output:
        console.print(f"[dim]💾 Backup de '{mem}' en cours...[/dim]")
    params = {"memory_id": mem}
    if description:
        params["description"] = description
    
    result = await client.call_tool("backup_create", params)
    _json_or_show(result, json_output, show_backup_result)


async def cmd_backup_list(client: MCPClient, state: dict, args: str, json_output: bool = False):
    """Liste les backups disponibles."""
    params = {}
    mem = args.strip() if args.strip() else state.get("memory")
    if mem:
        params["memory_id"] = mem
    
    result = await client.call_tool("backup_list", params)
    _json_or_show(result, json_output, lambda r: show_backups_table(r.get("backups", [])))


async def cmd_backup_restore(client: MCPClient, state: dict, args: str, json_output: bool = False):
    """Restaure une mémoire depuis un backup."""
    from rich.prompt import Confirm
    
    if not args:
        show_warning("Usage: backup-restore <backup_id>")
        console.print("[dim]Utilisez 'backup-list' pour voir les backup_id[/dim]")
        return
    
    backup_id = args.strip()
    if not json_output:
        if not Confirm.ask(f"[yellow]Restaurer depuis '{backup_id}' ?[/yellow]"):
            console.print("[dim]Annulé.[/dim]")
            return
        console.print(f"[dim]📥 Restauration de '{backup_id}'...[/dim]")

    result = await client.call_tool("backup_restore", {"backup_id": backup_id})
    _json_or_show(result, json_output, show_restore_result)


async def cmd_backup_download(client: MCPClient, state: dict, args: str, json_output: bool = False):
    """
    Télécharge un backup en archive tar.gz.
    
    Usage: backup-download <backup_id> [output_file] [--include-documents]
    
    --include-documents : inclut les documents originaux (PDF, DOCX...) dans l'archive.
    """
    if not args:
        show_warning("Usage: backup-download <backup_id> [output_file] [--include-documents]")
        console.print("[dim]  --include-documents : inclut les docs originaux pour restore offline[/dim]")
        return
    
    # Détecter --include-documents
    include_documents = "--include-documents" in args
    clean_args = args.replace("--include-documents", "").strip()
    
    parts = clean_args.split(maxsplit=1)
    backup_id = parts[0]
    output = parts[1].strip() if len(parts) > 1 else None
    
    if not json_output:
        if include_documents:
            console.print(f"[dim]📦 Téléchargement de '{backup_id}' [yellow](avec documents)[/yellow]...[/dim]")
        else:
            console.print(f"[dim]📦 Téléchargement de '{backup_id}'...[/dim]")
    
    params = {"backup_id": backup_id}
    if include_documents:
        params["include_documents"] = True
    
    result = await client.call_tool("backup_download", params)
    if json_output:
        show_json(result)
    elif result.get("status") == "ok":
        content_b64 = result.get("content_base64", "")
        archive_bytes = base64.b64decode(content_b64)
        out_file = output or result.get("filename", f"backup-{backup_id.replace('/', '-')}.tar.gz")
        with open(out_file, "wb") as f:
            f.write(archive_bytes)
        show_success(f"Archive: {out_file} ({format_size(len(archive_bytes))})")
    else:
        show_error(result.get("message", str(result)))


async def cmd_backup_delete(client: MCPClient, state: dict, args: str, json_output: bool = False):
    """Supprime un backup."""
    from rich.prompt import Confirm
    
    if not args:
        show_warning("Usage: backup-delete <backup_id>")
        return
    
    backup_id = args.strip()
    if not json_output:
        if not Confirm.ask(f"[yellow]Supprimer le backup '{backup_id}' ?[/yellow]"):
            console.print("[dim]Annulé.[/dim]")
            return
    
    result = await client.call_tool("backup_delete", {"backup_id": backup_id})
    _json_or_show(result, json_output,
                  lambda r: show_success(f"Backup supprimé: {backup_id} ({r.get('files_deleted', 0)} fichiers)"))


async def cmd_backup_restore_file(client: MCPClient, state: dict, args: str, json_output: bool = False):
    """
    Restaure une mémoire depuis une archive tar.gz locale.
    
    Usage: backup-restore-file <archive_path> [--confirm]
    
    ⚠️ La mémoire NE DOIT PAS exister (supprimez-la d'abord si nécessaire).
    Les documents S3 inclus dans l'archive sont ré-uploadés.
    """
    from rich.prompt import Confirm

    if not args:
        show_warning("Usage: backup-restore-file <archive_path> [--confirm]")
        console.print("[dim]⚠️ La mémoire ne doit pas exister.[/dim]")
        return

    # Détecter --confirm
    confirmed = "--confirm" in args
    archive_path = args.replace("--confirm", "").strip()

    if not archive_path:
        show_warning("Usage: backup-restore-file <archive_path> [--confirm]")
        return

    if not os.path.isfile(archive_path):
        show_error(f"Fichier non trouvé: {archive_path}")
        return

    file_size = os.path.getsize(archive_path)
    size_mb = file_size / (1024 * 1024)

    if not confirmed and not json_output:
        if not Confirm.ask(
            f"[yellow]Restaurer depuis '{archive_path}' ({size_mb:.1f} MB) ?\n"
            f"La mémoire ne doit pas exister.[/yellow]"
        ):
            console.print("[dim]Annulé.[/dim]")
            return

    try:
        if not json_output:
            console.print(f"📦 Lecture de l'archive ({size_mb:.1f} MB)...")
        with open(archive_path, "rb") as f:
            archive_bytes = f.read()
        archive_b64 = base64.b64encode(archive_bytes).decode("ascii")

        if not json_output:
            console.print("📥 Envoi au serveur pour restauration...")
        result = await client.call_tool("backup_restore_archive", {
            "archive_base64": archive_b64,
        })

        _json_or_show(result, json_output, show_restore_result)
    except Exception as e:
        show_error(str(e))


# =============================================================================
# Boucle principale du shell
# =============================================================================

def run_shell(url: str, token: str):
    """Point d'entrée du shell interactif."""

    console.print(Panel.fit(
        "[bold cyan]🧠 MCP Memory Shell[/bold cyan]\n\n"
        f"[bold]Serveur:[/bold] [yellow]{url}[/yellow]\n"
        "Tab : autocomplétion  •  ↑↓ : historique  •  Ctrl+C : annuler\n"
        "Tapez [green]help[/green] pour les commandes, [yellow]exit[/yellow] pour quitter.",
        border_style="cyan",
    ))

    client = MCPClient(url, token)
    state = {"memory": None, "debug": False, "limit": 10}

    completer = _get_completer()
    history = _get_history()

    # Table d'aide (organisée par catégorie, alignée sur Click v2.0)
    HELP = {
        # --- Serveur ---
        "about":        "Identité et capacités du service MCP Memory",
        "health":       "État de santé (S3, Neo4j, LLMaaS, Qdrant, Embedding)",
        "whoami":       "Identité du token courant (permissions, mémoires, email)",
        # --- Mémoires ---
        "list":         "Lister les mémoires",
        "use <id>":     "Sélectionner une mémoire",
        "create <id> <onto>": "Créer une mémoire (ex: create LEGAL legal)",
        "update":       "Modifier nom/description (--name, --description)",
        "info":         "Résumé de la mémoire courante",
        "graph":        "Graphe complet (types, relations, documents)",
        "delete":       "Supprimer la mémoire courante (+ S3)",
        # --- Documents ---
        "docs":         "Lister les documents",
        "ingest <path>":"Ingérer un fichier (--force pour réingérer)",
        "ingestdir <p>":"Ingérer un répertoire (--exclude, --confirm, --force)",
        "deldoc <id>":  "Supprimer un document",
        # --- Exploration ---
        "entities":     "Entités par type (avec descriptions)",
        "entity <n>":   "Contexte d'une entité (relations, documents, voisins)",
        "relations":    "Relations par type (avec exemples)",
        "ask <q>":      "Poser une question (réponse LLM)",
        "query <q>":    "Données structurées (sans LLM)",
        # --- Stockage ---
        "check":        "Vérifier cohérence S3/graphe (docs accessibles, orphelins)",
        "cleanup":      "Lister les orphelins S3 (--confirm pour supprimer)",
        # --- Ontologies ---
        "ontologies":   "Lister les ontologies disponibles",
        # --- Tokens (v2.0) ---
        "tokens":               "Lister les tokens actifs",
        "token-create <c>":     "Créer un token (ex: token-create quoteflow read,write JURIDIQUE)",
        "token-revoke <h>":     "Révoquer un token (par préfixe de hash)",
        "token-update <h>":     "Modifier un token (--permissions, --add-memories, --remove-memories, --set-memories, --email)",
        # --- Backup ---
        "backup-create [id]":       "Créer un backup (mémoire courante ou spécifiée)",
        "backup-list [id]":         "Lister les backups disponibles",
        "backup-restore <bid>":     "Restaurer depuis un backup",
        "backup-download <bid>":    "Télécharger en tar.gz (--include-documents)",
        "backup-delete <bid>":      "Supprimer un backup",
        "backup-restore-file <f>":  "Restaurer depuis archive locale (--confirm)",
        # --- Config ---
        "limit [N]":    "Voir/changer le limit de recherche (défaut: 10)",
        "debug":        "Activer/désactiver le debug",
        "clear":        "Effacer l'écran",
        "help":         "Afficher cette aide",
        "exit":         "Quitter",
        # --- Options globales ---
        "<cmd> --json":  "JSON brut sans formatage (ex: list --json)",
    }

    def show_help():
        table = Table(title="📖 Commandes", show_header=True)
        table.add_column("Commande", style="cyan")
        table.add_column("Description", style="white")
        for cmd, desc in HELP.items():
            table.add_row(cmd, desc)
        console.print(table)
        # Aliases legacy
        console.print("[dim]Aliases legacy (→ token-update): token-grant, token-ungrant, token-set, token-promote, token-set-email[/dim]")
        console.print("[dim]Alias cleanup: --force = --confirm (backward compat)[/dim]")

    # Boucle principale
    while True:
        try:
            mem_label = state["memory"] or "no memory"
            prompt_text = f"\n🧠 <b>{mem_label}</b>: "

            cmd = _prompt_input(prompt_text, completer=completer, history=history)
            if not cmd.strip():
                continue

            # Détecter --json n'importe où dans la ligne
            raw_line = cmd.strip()
            json_output = "--json" in raw_line
            if json_output:
                raw_line = raw_line.replace("--json", "").strip()

            parts = raw_line.split(maxsplit=1)
            command = parts[0].lower() if parts else ""
            args = parts[1] if len(parts) > 1 else ""

            if not command:
                continue

            # Dispatch
            if command in ("exit", "quit", "q"):
                console.print("[dim]Au revoir! 👋[/dim]")
                break

            elif command == "help":
                show_help()

            elif command == "debug":
                state["debug"] = not state["debug"]
                status = "[green]ACTIVÉ[/green]" if state["debug"] else "[dim]désactivé[/dim]"
                console.print(f"🔍 Debug: {status}")

            elif command == "clear":
                console.clear()

            # --- Serveur ---
            elif command == "about":
                asyncio.run(cmd_about(client, state, json_output=json_output))

            elif command == "health":
                asyncio.run(cmd_health(client, state, json_output=json_output))

            elif command == "whoami":
                asyncio.run(cmd_whoami(client, state, json_output=json_output))

            # --- Mémoires ---
            elif command == "list":
                asyncio.run(cmd_list(client, state, json_output=json_output))

            elif command == "use":
                asyncio.run(cmd_use(client, state, args))

            elif command == "info":
                asyncio.run(cmd_info(client, state, json_output=json_output))

            elif command == "graph":
                asyncio.run(cmd_graph(client, state, args, json_output=json_output))

            elif command == "create":
                asyncio.run(cmd_create(client, state, args, json_output=json_output))

            elif command == "update":
                asyncio.run(cmd_update(client, state, args, json_output=json_output))

            elif command == "delete":
                asyncio.run(cmd_delete(client, state, args, json_output=json_output))

            # --- Documents ---
            elif command == "docs":
                asyncio.run(cmd_docs(client, state, json_output=json_output))

            elif command == "ingest":
                asyncio.run(cmd_ingest(client, state, args, json_output=json_output))

            elif command == "ingestdir":
                asyncio.run(cmd_ingestdir(client, state, args, json_output=json_output))

            elif command == "deldoc":
                asyncio.run(cmd_deldoc(client, state, args, json_output=json_output))

            # --- Exploration ---
            elif command == "entities":
                asyncio.run(cmd_entities(client, state, json_output=json_output))

            elif command == "entity":
                asyncio.run(cmd_entity(client, state, args, json_output=json_output))

            elif command == "relations":
                asyncio.run(cmd_relations(client, state, args, json_output=json_output))

            elif command == "ask":
                asyncio.run(cmd_ask(client, state, args, state["debug"], json_output=json_output))

            elif command == "query":
                asyncio.run(cmd_query(client, state, args, state["debug"], json_output=json_output))

            # --- Stockage ---
            elif command == "check":
                asyncio.run(cmd_check(client, state, args, json_output=json_output))

            elif command == "cleanup":
                # --confirm (v2.0) ou --force (backward compat)
                confirm = "--confirm" in args.lower() or "--force" in args.lower() if args else False
                if confirm and not json_output:
                    from rich.prompt import Confirm
                    if not Confirm.ask("[yellow]⚠️ Supprimer les fichiers orphelins S3 ?[/yellow]"):
                        console.print("[dim]Annulé.[/dim]")
                        continue
                asyncio.run(cmd_cleanup(client, state, confirm=confirm, json_output=json_output))

            elif command == "ontologies":
                asyncio.run(cmd_ontologies(client, state, json_output=json_output))

            elif command == "limit":
                if args.strip():
                    try:
                        new_limit = int(args.strip())
                        if new_limit < 1:
                            raise ValueError
                        state["limit"] = new_limit
                        console.print(f"[green]✓[/green] Limit: [cyan]{new_limit}[/cyan] entités par recherche")
                    except ValueError:
                        show_error("Usage: limit <nombre> (ex: limit 20)")
                else:
                    console.print(f"Limit actuel: [cyan]{state['limit']}[/cyan] entités par recherche")

            # --- Token commands (v2.0 + aliases) ---
            elif command == "tokens":
                asyncio.run(cmd_tokens(client, state, json_output=json_output))

            elif command == "token-create":
                asyncio.run(cmd_token_create(client, state, args, json_output=json_output))

            elif command == "token-revoke":
                asyncio.run(cmd_token_revoke(client, state, args, json_output=json_output))

            elif command == "token-update":
                asyncio.run(cmd_token_update(client, state, args, json_output=json_output))

            # Aliases legacy
            elif command == "token-grant":
                asyncio.run(cmd_token_grant(client, state, args, json_output=json_output))

            elif command == "token-ungrant":
                asyncio.run(cmd_token_ungrant(client, state, args, json_output=json_output))

            elif command == "token-set":
                asyncio.run(cmd_token_set(client, state, args, json_output=json_output))

            elif command == "token-promote":
                asyncio.run(cmd_token_promote(client, state, args, json_output=json_output))

            elif command == "token-set-email":
                asyncio.run(cmd_token_set_email(client, state, args, json_output=json_output))

            # --- Backup commands ---
            elif command == "backup-create":
                asyncio.run(cmd_backup_create(client, state, args, json_output=json_output))

            elif command == "backup-list":
                asyncio.run(cmd_backup_list(client, state, args, json_output=json_output))

            elif command == "backup-restore":
                asyncio.run(cmd_backup_restore(client, state, args, json_output=json_output))

            elif command == "backup-download":
                asyncio.run(cmd_backup_download(client, state, args, json_output=json_output))

            elif command == "backup-delete":
                asyncio.run(cmd_backup_delete(client, state, args, json_output=json_output))

            elif command == "backup-restore-file":
                asyncio.run(cmd_backup_restore_file(client, state, args, json_output=json_output))

            # Alias legacy pour backup (backward compat)
            elif command == "backup":
                show_warning("Commande 'backup' sans sous-commande. Utilisez: backup-create, backup-list, backup-restore, backup-download, backup-delete, backup-restore-file")

            else:
                show_error(f"Commande inconnue: '{command}'. Tapez 'help'.")

        except KeyboardInterrupt:
            console.print("\n[dim]Ctrl+C — tapez 'exit' pour quitter[/dim]")
        except EOFError:
            console.print("\n[dim]Au revoir! 👋[/dim]")
            break
        except Exception as e:
            show_error(str(e))
