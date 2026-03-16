# -*- coding: utf-8 -*-
"""
CLI Click — Commandes scriptables pour MCP Memory.

v2.0 — Syntaxe alignée avec Live Memory :
  - Helper _run_tool() commun (supprime ~600 lignes de boilerplate)
  - --json/-j sur toutes les commandes
  - whoami (identité du token)
  - health → appelle system_health (teste les 5 services)
  - token update (remplace grant/ungrant/set-memories/promote/set-email)

Usage :
    python scripts/mcp_cli.py health
    python scripts/mcp_cli.py whoami
    python scripts/mcp_cli.py memory list
    python scripts/mcp_cli.py token create quoteflow -p read,write
    python scripts/mcp_cli.py shell
"""

import os
import sys
import json
import asyncio
import base64

import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Confirm
from rich.syntax import Syntax

from .client import MCPClient
from . import BASE_URL, TOKEN
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
# Helper commun — élimine le boilerplate async (pattern live-mem)
# =============================================================================

def _run_tool(ctx, tool_name, args, on_success, json_flag=False):
    """Helper commun : appelle un outil MCP et affiche le résultat.
    
    Si json_flag est True, affiche le JSON brut sans formatage.
    Sinon, appelle on_success(result) pour l'affichage formaté.
    Gère automatiquement les erreurs et la connexion.
    """
    async def _run():
        try:
            client = MCPClient(ctx.obj["url"], ctx.obj["token"])
            result = await client.call_tool(tool_name, args)
            if json_flag:
                show_json(result)
            elif result.get("status") in ("ok", "healthy", "created", "deleted"):
                on_success(result)
            else:
                show_error(result.get("message", f"Erreur: {result.get('status', '?')}"))
        except Exception as e:
            show_error(f"Connexion impossible: {e}")
    asyncio.run(_run())


def _run_rest(ctx, method, args, on_success, json_flag=False):
    """Helper pour les appels REST (list_memories, get_graph) qui ne sont pas des outils MCP."""
    async def _run():
        try:
            client = MCPClient(ctx.obj["url"], ctx.obj["token"])
            result = await method(client, **args)
            if json_flag:
                show_json(result)
            elif result.get("status") == "ok":
                on_success(result)
            else:
                show_error(result.get("message", "Erreur"))
        except Exception as e:
            show_error(f"Connexion impossible: {e}")
    asyncio.run(_run())


# =============================================================================
# Groupe principal
# =============================================================================

@click.group(invoke_without_command=True)
@click.option("--url", "-u", envvar=["MCP_URL", "MCP_SERVER_URL"], default=BASE_URL, help="URL du serveur MCP")
@click.option("--token", "-t", envvar=["MCP_TOKEN", "ADMIN_BOOTSTRAP_KEY"], default=TOKEN, help="Token d'authentification")
@click.pass_context
def cli(ctx, url, token):
    """🧠 MCP Memory CLI — Pilotez votre serveur MCP Memory.

    \b
    Exemples:
      mcp-cli health              # État des services
      mcp-cli whoami              # Identité du token
      mcp-cli memory list         # Lister les mémoires
      mcp-cli memory graph ID     # Graphe d'une mémoire
      mcp-cli shell               # Mode interactif
    """
    ctx.ensure_object(dict)
    ctx.obj["url"] = url
    ctx.obj["token"] = token
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


# =============================================================================
# System : health, whoami, about, ontologies
# =============================================================================

@cli.command("health")
@click.option("--json", "-j", "jflag", is_flag=True, help="JSON brut")
@click.pass_context
def health_cmd(ctx, jflag):
    """❤️  État de santé du service (teste S3, Neo4j, LLMaaS, Qdrant, Embedding)."""
    _run_tool(ctx, "system_health", {}, show_health_result, jflag)


@cli.command("whoami")
@click.option("--json", "-j", "jflag", is_flag=True, help="JSON brut")
@click.pass_context
def whoami_cmd(ctx, jflag):
    """👤 Identité du token courant (permissions, mémoires, email)."""
    _run_tool(ctx, "system_whoami", {}, show_whoami_result, jflag)


@cli.command("about")
@click.option("--json", "-j", "jflag", is_flag=True, help="JSON brut")
@click.pass_context
def about_cmd(ctx, jflag):
    """ℹ️  Identité et capacités du service MCP Memory."""
    _run_tool(ctx, "system_about", {}, show_about, jflag)


@cli.command("ontologies")
@click.option("--json", "-j", "jflag", is_flag=True, help="JSON brut")
@click.pass_context
def ontologies_cmd(ctx, jflag):
    """📖 Lister les ontologies disponibles."""
    def _show(result):
        from rich.table import Table
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
    _run_tool(ctx, "ontology_list", {}, _show, jflag)


# =============================================================================
# Memory
# =============================================================================

@cli.group()
def memory():
    """📚 Gérer les mémoires."""
    pass


@memory.command("list")
@click.option("--json", "-j", "jflag", is_flag=True, help="JSON brut")
@click.pass_context
def memory_list(ctx, jflag):
    """📋 Lister toutes les mémoires."""
    _run_rest(ctx, lambda c, **kw: c.list_memories(), {},
              lambda r: show_memories_table(r.get("memories", [])), jflag)


@memory.command("create")
@click.argument("memory_id")
@click.option("--name", "-n", default=None, help="Nom de la mémoire")
@click.option("--description", "-d", default=None, help="Description")
@click.option("--ontology", "-o", required=True, help="Ontologie (OBLIGATOIRE)")
@click.option("--json", "-j", "jflag", is_flag=True, help="JSON brut")
@click.pass_context
def memory_create(ctx, memory_id, name, description, ontology, jflag):
    """➕ Créer une nouvelle mémoire."""
    _run_tool(ctx, "memory_create", {
        "memory_id": memory_id,
        "name": name or memory_id,
        "description": description or "",
        "ontology": ontology,
    }, lambda r: show_success(f"Mémoire '{memory_id}' créée (ontologie: {r.get('ontology')})"), jflag)


@memory.command("delete")
@click.argument("memory_id")
@click.option("--confirm", is_flag=True, help="Confirmer la suppression")
@click.option("--json", "-j", "jflag", is_flag=True, help="JSON brut")
@click.pass_context
def memory_delete(ctx, memory_id, confirm, jflag):
    """🗑️  Supprimer une mémoire."""
    if not confirm and not Confirm.ask(f"[yellow]Supprimer '{memory_id}' ?[/yellow]"):
        console.print("[dim]Annulé.[/dim]")
        return
    _run_tool(ctx, "memory_delete", {"memory_id": memory_id},
              lambda r: show_success(f"Mémoire '{memory_id}' supprimée!"), jflag)


@memory.command("graph")
@click.argument("memory_id")
@click.option("--json", "-j", "jflag", is_flag=True, help="JSON brut")
@click.pass_context
def memory_graph(ctx, memory_id, jflag):
    """📊 Afficher le graphe d'une mémoire."""
    _run_rest(ctx, lambda c, **kw: c.get_graph(kw["mid"]), {"mid": memory_id},
              lambda r: show_graph_summary(r, memory_id), jflag)


@memory.command("info")
@click.argument("memory_id")
@click.option("--json", "-j", "jflag", is_flag=True, help="JSON brut")
@click.pass_context
def memory_info(ctx, memory_id, jflag):
    """ℹ️  Résumé d'une mémoire (entités, relations, documents)."""
    def _show(result):
        from rich.panel import Panel
        nodes = result.get("nodes", [])
        edges = result.get("edges", [])
        docs = result.get("documents", [])
        entity_nodes = [n for n in nodes if n.get("node_type") == "entity"]
        non_mention = [e for e in edges if e.get("type") != "MENTIONS"]
        console.print(Panel.fit(
            f"[bold]Mémoire:[/bold]   [cyan]{memory_id}[/cyan]\n"
            f"[bold]Entités:[/bold]   [green]{len(entity_nodes)}[/green]\n"
            f"[bold]Relations:[/bold] [green]{len(non_mention)}[/green]\n"
            f"[bold]MENTIONS:[/bold]  [dim]{len(edges) - len(non_mention)}[/dim]\n"
            f"[bold]Documents:[/bold] [green]{len(docs)}[/green]",
            title=f"ℹ️  Info: {memory_id}",
            border_style="cyan",
        ))
    _run_rest(ctx, lambda c, **kw: c.get_graph(kw["mid"]), {"mid": memory_id}, _show, jflag)


@memory.command("entities")
@click.argument("memory_id")
@click.option("--json", "-j", "jflag", is_flag=True, help="JSON brut")
@click.pass_context
def memory_entities(ctx, memory_id, jflag):
    """📦 Lister les entités par type (avec documents sources)."""
    def _show(result):
        show_entities_by_type(result)
    _run_rest(ctx, lambda c, **kw: c.get_graph(kw["mid"]), {"mid": memory_id}, _show, jflag)


@memory.command("entity")
@click.argument("memory_id")
@click.argument("entity_name")
@click.option("--depth", default=1, help="Profondeur de traversée (défaut: 1)")
@click.option("--json", "-j", "jflag", is_flag=True, help="JSON brut")
@click.pass_context
def memory_entity(ctx, memory_id, entity_name, depth, jflag):
    """🔍 Contexte d'une entité (relations, documents, voisins)."""
    _run_tool(ctx, "memory_get_context", {
        "memory_id": memory_id, "entity_name": entity_name, "depth": depth,
    }, show_entity_context, jflag)


@memory.command("relations")
@click.argument("memory_id")
@click.option("--type", "-t", "rel_type", default=None, help="Filtrer par type de relation")
@click.option("--json", "-j", "jflag", is_flag=True, help="JSON brut")
@click.pass_context
def memory_relations(ctx, memory_id, rel_type, jflag):
    """🔗 Relations par type (résumé ou détail avec --type)."""
    def _show(result):
        show_relations_by_type(result, type_filter=rel_type)
    _run_rest(ctx, lambda c, **kw: c.get_graph(kw["mid"]), {"mid": memory_id}, _show, jflag)


# =============================================================================
# Document
# =============================================================================

@cli.group()
def document():
    """📄 Gérer les documents."""
    pass


@document.command("ingest")
@click.argument("memory_id")
@click.argument("file_path", type=click.Path(exists=True))
@click.option("--force", "-f", is_flag=True, help="Forcer la ré-ingestion")
@click.option("--source-path", default=None, help="Chemin source d'origine (défaut: chemin du fichier)")
@click.option("--json", "-j", "jflag", is_flag=True, help="JSON brut")
@click.pass_context
def document_ingest(ctx, memory_id, file_path, force, source_path, jflag):
    """📥 Ingérer un document dans une mémoire."""
    async def _run():
        try:
            from datetime import datetime, timezone

            with open(file_path, "rb") as f:
                content_bytes = f.read()
            content_b64 = base64.b64encode(content_bytes).decode("utf-8")
            filename = os.path.basename(file_path)
            file_size = len(content_bytes)
            file_ext = filename.lower().rsplit('.', 1)[-1] if '.' in filename else '?'

            # Affichage pré-vol
            if not jflag:
                show_ingest_preflight(filename, file_size, file_ext, memory_id, force)

            # Métadonnées enrichies
            effective_source_path = source_path or os.path.abspath(file_path)
            mtime = os.path.getmtime(file_path)
            source_modified_at = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()

            client = MCPClient(ctx.obj["url"], ctx.obj["token"])

            # Progression temps réel
            result = await run_ingest_with_progress(client, {
                "memory_id": memory_id,
                "content_base64": content_b64,
                "filename": filename,
                "force": force,
                "source_path": effective_source_path,
                "source_modified_at": source_modified_at,
            })

            if jflag:
                show_json(result)
            elif result.get("status") == "ok":
                show_ingest_result(result)
            elif result.get("status") == "already_exists":
                console.print(f"[yellow]⚠️ Déjà ingéré: {result.get('document_id')} (--force pour réingérer)[/yellow]")
            else:
                show_error(result.get("message", str(result)))
        except Exception as e:
            show_error(str(e))
    asyncio.run(_run())


@document.command("ingest-dir")
@click.argument("memory_id")
@click.argument("directory", type=click.Path(exists=True, file_okay=False))
@click.option("--exclude", "-e", multiple=True, help="Patterns à exclure (glob, ex: '*.tmp'). Répétable.")
@click.option("--confirm", "-c", is_flag=True, help="Demander confirmation pour chaque fichier")
@click.option("--force", "-f", is_flag=True, help="Forcer la ré-ingestion des fichiers déjà présents")
@click.option("--json", "-j", "jflag", is_flag=True, help="JSON brut")
@click.pass_context
def document_ingest_dir(ctx, memory_id, directory, exclude, confirm, force, jflag):
    """📁 Ingérer un répertoire entier (récursif).

    \b
    Parcourt le répertoire et ses sous-répertoires pour trouver les fichiers
    supportés (.txt, .md, .html, .docx, .pdf, .csv).

    \b
    Exemples:
      document ingest-dir JURIDIQUE ./MATIERE/JURIDIQUE
      document ingest-dir JURIDIQUE ./docs -e '*.tmp' -e '__pycache__/*'
      document ingest-dir JURIDIQUE ./docs --confirm
      document ingest-dir JURIDIQUE ./docs --force
    """
    import fnmatch
    from pathlib import Path
    from rich.table import Table
    from rich.panel import Panel

    SUPPORTED_EXTENSIONS = {".txt", ".md", ".html", ".docx", ".pdf", ".csv"}

    async def _run():
        try:
            client = MCPClient(ctx.obj["url"], ctx.obj["token"])

            # --- 1. Scanner le répertoire ---
            console.print(f"[dim]📁 Scan de {directory}...[/dim]")
            all_files = []
            excluded_files = []
            unsupported_files = []

            for root, dirs, files in os.walk(directory):
                for fname in sorted(files):
                    fpath = os.path.join(root, fname)
                    rel_path = os.path.relpath(fpath, directory)

                    is_excluded = False
                    for pattern in exclude:
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

                    file_size = os.path.getsize(fpath)
                    all_files.append({
                        "path": fpath, "rel_path": rel_path,
                        "filename": fname, "size": file_size,
                    })

            if not all_files:
                show_warning(f"Aucun fichier supporté trouvé dans {directory}")
                if unsupported_files:
                    console.print(f"[dim]Formats non supportés: {len(unsupported_files)} fichiers ignorés[/dim]")
                    console.print(f"[dim]Extensions supportées: {', '.join(sorted(SUPPORTED_EXTENSIONS))}[/dim]")
                return

            # --- 2. Vérifier les doublons ---
            graph_result = await client.get_graph(memory_id)
            existing_filenames = set()
            if graph_result.get("status") == "ok":
                for d in graph_result.get("documents", []):
                    existing_filenames.add(d.get("filename", ""))

            to_ingest = []
            already_present = []
            for f in all_files:
                if f["filename"] in existing_filenames and not force:
                    already_present.append(f)
                else:
                    to_ingest.append(f)

            # --- 3. Afficher le résumé ---
            total_size = sum(f["size"] for f in to_ingest)
            size_str = format_size(total_size)

            summary_lines = [
                f"[bold]Répertoire:[/bold]  [cyan]{os.path.abspath(directory)}[/cyan]",
                f"[bold]Mémoire:[/bold]     [cyan]{memory_id}[/cyan]",
                f"",
                f"[bold]Fichiers trouvés:[/bold]     [green]{len(all_files)}[/green]",
            ]
            if excluded_files:
                summary_lines.append(f"[bold]Exclus (patterns):[/bold]  [yellow]{len(excluded_files)}[/yellow]")
            if unsupported_files:
                summary_lines.append(f"[bold]Non supportés:[/bold]      [dim]{len(unsupported_files)}[/dim]")
            if already_present:
                summary_lines.append(f"[bold]Déjà ingérés:[/bold]      [yellow]{len(already_present)}[/yellow] (skip)")
            summary_lines.append(f"[bold]À ingérer:[/bold]          [green bold]{len(to_ingest)}[/green bold] ({size_str})")

            console.print(Panel.fit("\n".join(summary_lines), title="📁 Import en masse", border_style="blue"))

            if not to_ingest:
                show_success("Tous les fichiers sont déjà ingérés !")
                return

            # Liste des fichiers
            table = Table(title=f"📄 Fichiers à ingérer ({len(to_ingest)})", show_header=True)
            table.add_column("#", style="dim", width=3)
            table.add_column("Fichier", style="white")
            table.add_column("Taille", style="dim", justify="right", width=10)
            for i, f in enumerate(to_ingest, 1):
                table.add_row(str(i), f["rel_path"], format_size(f["size"]))
            console.print(table)

            # --- 4. Ingestion ---
            ingested = 0
            skipped = 0
            errors = 0

            for i, f in enumerate(to_ingest, 1):
                if confirm:
                    if not Confirm.ask(f"[{i}/{len(to_ingest)}] Ingérer [cyan]{f['rel_path']}[/cyan] ?"):
                        skipped += 1
                        continue

                file_size_str = format_size(f["size"])
                console.print(f"\n[bold cyan][{i}/{len(to_ingest)}][/bold cyan] 📥 [bold]{f['rel_path']}[/bold] ({file_size_str})")

                try:
                    from datetime import datetime, timezone

                    with open(f["path"], "rb") as fh:
                        content_bytes = fh.read()
                    content_b64 = base64.b64encode(content_bytes).decode("utf-8")
                    mtime = os.path.getmtime(f["path"])
                    source_modified_at = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()

                    result = await run_ingest_with_progress(client, {
                        "memory_id": memory_id,
                        "content_base64": content_b64,
                        "filename": f["filename"],
                        "force": force,
                        "source_path": f["rel_path"],
                        "source_modified_at": source_modified_at,
                    })

                    if result.get("status") == "ok":
                        elapsed = result.get("_elapsed_seconds", 0)
                        e_new = result.get("entities_created", 0)
                        e_merged = result.get("entities_merged", 0)
                        r_new = result.get("relations_created", 0)
                        r_merged = result.get("relations_merged", 0)
                        console.print(
                            f"  [green]✅[/green] {f['filename']}: "
                            f"[cyan]{e_new}+{e_merged}[/cyan] entités, "
                            f"[cyan]{r_new}+{r_merged}[/cyan] relations "
                            f"[dim]({elapsed}s)[/dim]"
                        )
                        ingested += 1
                    elif result.get("status") == "already_exists":
                        console.print(f"  [yellow]⏭️[/yellow] {f['filename']}: déjà ingéré")
                        skipped += 1
                    else:
                        console.print(f"  [red]❌[/red] {f['filename']}: {result.get('message', '?')}")
                        errors += 1
                except Exception as e:
                    console.print(f"  [red]❌[/red] {f['filename']}: {e}")
                    errors += 1

            # --- 5. Résumé final ---
            console.print(Panel.fit(
                f"[green]✅ Ingérés: {ingested}[/green]  "
                f"[yellow]⏭️ Skippés: {skipped}[/yellow]  "
                f"[red]❌ Erreurs: {errors}[/red]",
                title="📊 Résultat",
                border_style="green" if errors == 0 else "yellow",
            ))

        except Exception as e:
            show_error(str(e))

    asyncio.run(_run())


@document.command("list")
@click.argument("memory_id")
@click.option("--json", "-j", "jflag", is_flag=True, help="JSON brut")
@click.pass_context
def document_list(ctx, memory_id, jflag):
    """📋 Lister les documents d'une mémoire."""
    _run_rest(ctx, lambda c, **kw: c.get_graph(kw["mid"]), {"mid": memory_id},
              lambda r: show_documents_table(r.get("documents", []), memory_id), jflag)


@document.command("delete")
@click.argument("memory_id")
@click.argument("document_id")
@click.option("--confirm", is_flag=True, help="Confirmer la suppression")
@click.option("--json", "-j", "jflag", is_flag=True, help="JSON brut")
@click.pass_context
def document_delete(ctx, memory_id, document_id, confirm, jflag):
    """🗑️  Supprimer un document."""
    if not confirm and not Confirm.ask(f"Supprimer '{document_id}' ?"):
        console.print("[dim]Annulé.[/dim]")
        return
    _run_tool(ctx, "document_delete", {
        "memory_id": memory_id, "document_id": document_id,
    }, lambda r: show_success(f"Document supprimé ({r.get('entities_deleted', 0)} entités orphelines nettoyées)"), jflag)


# =============================================================================
# Question / Réponse
# =============================================================================

@cli.command("ask")
@click.argument("memory_id")
@click.argument("question")
@click.option("--limit", "-l", default=10, help="Max entités à rechercher (défaut: 10)")
@click.option("--json", "-j", "jflag", is_flag=True, help="JSON brut")
@click.pass_context
def ask_cmd(ctx, memory_id, question, limit, jflag):
    """❓ Poser une question sur une mémoire."""
    def _show(result):
        show_answer(result.get("answer", ""), result.get("entities", []), result.get("source_documents", []))
    
    async def _run():
        try:
            client = MCPClient(ctx.obj["url"], ctx.obj["token"])
            with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as p:
                p.add_task("Recherche…", total=None)
                result = await client.call_tool("question_answer", {
                    "memory_id": memory_id, "question": question, "limit": limit,
                })
            if jflag:
                show_json(result)
            elif result.get("status") == "ok":
                _show(result)
            else:
                show_error(result.get("message", "Erreur"))
        except Exception as e:
            show_error(str(e))
    asyncio.run(_run())


@cli.command("query")
@click.argument("memory_id")
@click.argument("query_text")
@click.option("--limit", "-l", default=10, help="Max entités à rechercher (défaut: 10)")
@click.option("--json", "-j", "jflag", is_flag=True, help="JSON brut")
@click.pass_context
def query_cmd(ctx, memory_id, query_text, limit, jflag):
    """📊 Interroger une mémoire (données structurées, sans LLM)."""
    async def _run():
        try:
            client = MCPClient(ctx.obj["url"], ctx.obj["token"])
            with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as p:
                p.add_task("Recherche…", total=None)
                result = await client.call_tool("memory_query", {
                    "memory_id": memory_id, "query": query_text, "limit": limit,
                })
            if jflag:
                show_json(result)
            elif result.get("status") == "ok":
                show_query_result(result)
            else:
                show_error(result.get("message", "Erreur"))
        except Exception as e:
            show_error(str(e))
    asyncio.run(_run())


# =============================================================================
# Storage (check / cleanup)
# =============================================================================

@cli.group()
def storage():
    """💾 Vérification et nettoyage du stockage S3."""
    pass


@storage.command("check")
@click.argument("memory_id", required=False, default=None)
@click.option("--json", "-j", "jflag", is_flag=True, help="JSON brut")
@click.pass_context
def storage_check(ctx, memory_id, jflag):
    """🔍 Vérifier la cohérence S3/graphe (docs accessibles, orphelins)."""
    params = {}
    if memory_id:
        params["memory_id"] = memory_id
    if not jflag:
        console.print("[dim]🔍 Vérification S3 en cours...[/dim]")
    _run_tool(ctx, "storage_check", params, show_storage_check, jflag)


@storage.command("cleanup")
@click.option("--confirm", is_flag=True, help="Supprimer réellement (sinon dry run)")
@click.option("--json", "-j", "jflag", is_flag=True, help="JSON brut")
@click.pass_context
def storage_cleanup(ctx, confirm, jflag):
    """🧹 Nettoyer les fichiers orphelins sur S3 (dry run par défaut)."""
    if not jflag:
        console.print("[dim]🧹 Analyse des orphelins S3...[/dim]")
    _run_tool(ctx, "storage_cleanup", {"dry_run": not confirm}, show_cleanup_result, jflag)


# =============================================================================
# Token (gestion des tokens d'accès) — v2.0 simplifié
# =============================================================================

@cli.group()
def token():
    """🔑 Gérer les tokens d'accès clients."""
    pass


# Niveaux de permissions valides
VALID_PERMISSIONS = click.Choice(
    ["read", "read,write", "read,write,admin"],
    case_sensitive=False,
)


@token.command("list")
@click.option("--json", "-j", "jflag", is_flag=True, help="JSON brut")
@click.pass_context
def token_list(ctx, jflag):
    """📋 Lister tous les tokens actifs."""
    _run_tool(ctx, "admin_list_tokens", {},
              lambda r: show_tokens_table(r.get("tokens", [])), jflag)


@token.command("create")
@click.argument("client_name")
@click.option("--permissions", "-p", type=VALID_PERMISSIONS, default="read,write",
              help="Permissions : read | read,write | read,write,admin")
@click.option("--memories", "-m", default="", help="Mémoires autorisées (virgules, vide=toutes)")
@click.option("--email", "-e", default=None, help="Email du propriétaire")
@click.option("--expires", type=int, default=None, help="Expiration en jours")
@click.option("--json", "-j", "jflag", is_flag=True, help="JSON brut")
@click.pass_context
def token_create(ctx, client_name, permissions, memories, email, expires, jflag):
    """➕ Créer un token pour un client.

    \b
    Exemples:
      token create quoteflow
      token create quoteflow -p read,write -m JURIDIQUE,CLOUD
      token create quoteflow -e user@example.com
      token create admin-bot -p read,write,admin --expires 30
    """
    perms_list = [p.strip() for p in permissions.split(",") if p.strip()]
    mem_list = [m.strip() for m in memories.split(",") if m.strip()]
    params = {
        "client_name": client_name,
        "permissions": perms_list,
        "memory_ids": mem_list,
    }
    if email:
        params["email"] = email
    if expires:
        params["expires_in_days"] = expires
    _run_tool(ctx, "admin_create_token", params, show_token_created, jflag)


@token.command("revoke")
@click.argument("token_hash")
@click.option("--confirm", is_flag=True, help="Confirmer la révocation")
@click.option("--json", "-j", "jflag", is_flag=True, help="JSON brut")
@click.pass_context
def token_revoke(ctx, token_hash, confirm, jflag):
    """🚫 Révoquer un token (par hash ou préfixe de hash)."""
    if not confirm and not Confirm.ask(f"[yellow]Révoquer le token '{token_hash[:12]}...' ?[/yellow]"):
        console.print("[dim]Annulé.[/dim]")
        return
    _run_tool(ctx, "admin_revoke_token", {"token_hash_prefix": token_hash},
              lambda r: show_success(r.get("message", "Token révoqué")), jflag)


@token.command("update")
@click.argument("token_hash")
@click.option("--permissions", "-p", default="",
              help="Nouvelles permissions (read | read,write | read,write,admin)")
@click.option("--add-memories", default="", help="Mémoires à ajouter (virgules)")
@click.option("--remove-memories", default="", help="Mémoires à retirer (virgules)")
@click.option("--set-memories", default=None, help="Remplacer les mémoires (virgules, vide=toutes)")
@click.option("--email", "-e", default="", help="Email du propriétaire")
@click.option("--json", "-j", "jflag", is_flag=True, help="JSON brut")
@click.pass_context
def token_update(ctx, token_hash, permissions, add_memories, remove_memories, set_memories, email, jflag):
    """✏️  Mettre à jour un token (permissions, mémoires, email).

    \b
    Exemples:
      token update sha256:a8c5 -p read,write,admin          # Promouvoir admin
      token update sha256:a8c5 --add-memories JURIDIQUE      # Ajouter mémoire
      token update sha256:a8c5 --remove-memories CLOUD       # Retirer mémoire
      token update sha256:a8c5 --set-memories "JURIDIQUE,CLOUD"  # Remplacer
      token update sha256:a8c5 --set-memories ""             # Accès à toutes
      token update sha256:a8c5 -e user@example.com           # Modifier email
    """
    args = {"token_hash_prefix": token_hash}
    has_update = False

    if permissions:
        args["set_permissions"] = [p.strip() for p in permissions.split(",") if p.strip()]
        has_update = True
    if add_memories:
        args["add_memories"] = [m.strip() for m in add_memories.split(",") if m.strip()]
        has_update = True
    if remove_memories:
        args["remove_memories"] = [m.strip() for m in remove_memories.split(",") if m.strip()]
        has_update = True
    if set_memories is not None:
        args["set_memories"] = [m.strip() for m in set_memories.split(",") if m.strip()] if set_memories else []
        has_update = True
    if email:
        args["set_email"] = email
        has_update = True

    if not has_update:
        show_error("Rien à modifier. Utilisez --permissions, --add-memories, --remove-memories, --set-memories ou --email.")
        return

    _run_tool(ctx, "admin_update_token", args, show_token_updated, jflag)


# =============================================================================
# Backup / Restore
# =============================================================================

@cli.group()
def backup():
    """💾 Backup et restauration des mémoires."""
    pass


@backup.command("create")
@click.argument("memory_id")
@click.option("--description", "-d", default=None, help="Description du backup")
@click.option("--json", "-j", "jflag", is_flag=True, help="JSON brut")
@click.pass_context
def backup_create(ctx, memory_id, description, jflag):
    """💾 Créer un backup complet d'une mémoire."""
    if not jflag:
        console.print(f"[dim]💾 Backup de '{memory_id}' en cours...[/dim]")
    params = {"memory_id": memory_id}
    if description:
        params["description"] = description
    _run_tool(ctx, "backup_create", params, show_backup_result, jflag)


@backup.command("list")
@click.argument("memory_id", required=False, default=None)
@click.option("--json", "-j", "jflag", is_flag=True, help="JSON brut")
@click.pass_context
def backup_list(ctx, memory_id, jflag):
    """📋 Lister les backups disponibles."""
    params = {}
    if memory_id:
        params["memory_id"] = memory_id
    _run_tool(ctx, "backup_list", params,
              lambda r: show_backups_table(r.get("backups", [])), jflag)


@backup.command("restore")
@click.argument("backup_id")
@click.option("--confirm", is_flag=True, help="Confirmer la restauration")
@click.option("--json", "-j", "jflag", is_flag=True, help="JSON brut")
@click.pass_context
def backup_restore(ctx, backup_id, confirm, jflag):
    """📥 Restaurer une mémoire depuis un backup.

    \b
    ⚠️ La mémoire NE DOIT PAS exister (supprimez-la d'abord si nécessaire).
    """
    if not confirm and not Confirm.ask(
        f"[yellow]Restaurer depuis '{backup_id}' ?[/yellow]\n"
        f"[dim]La mémoire ne doit pas exister.[/dim]"
    ):
        console.print("[dim]Annulé.[/dim]")
        return
    if not jflag:
        console.print(f"[dim]📥 Restauration de '{backup_id}' en cours...[/dim]")
    _run_tool(ctx, "backup_restore", {"backup_id": backup_id}, show_restore_result, jflag)


@backup.command("download")
@click.argument("backup_id")
@click.option("--output", "-o", default=None, help="Fichier de sortie (défaut: backup-{id}.tar.gz)")
@click.option("--include-documents", is_flag=True, help="Inclure les documents originaux")
@click.pass_context
def backup_download(ctx, backup_id, output, include_documents):
    """📦 Télécharger un backup en archive tar.gz."""
    async def _run():
        try:
            client = MCPClient(ctx.obj["url"], ctx.obj["token"])
            console.print(f"[dim]📦 Téléchargement de '{backup_id}'...[/dim]")
            result = await client.call_tool("backup_download", {
                "backup_id": backup_id,
                "include_documents": include_documents,
            })
            if result.get("status") == "ok":
                content_b64 = result.get("content_base64", "")
                archive_bytes = base64.b64decode(content_b64)
                out_file = output or result.get("filename", f"backup-{backup_id.replace('/', '-')}.tar.gz")
                with open(out_file, "wb") as f:
                    f.write(archive_bytes)
                show_success(f"Archive sauvée: {out_file} ({format_size(len(archive_bytes))})")
            else:
                show_error(result.get("message", str(result)))
        except Exception as e:
            show_error(str(e))
    asyncio.run(_run())


@backup.command("delete")
@click.argument("backup_id")
@click.option("--confirm", is_flag=True, help="Confirmer la suppression")
@click.option("--json", "-j", "jflag", is_flag=True, help="JSON brut")
@click.pass_context
def backup_delete(ctx, backup_id, confirm, jflag):
    """🗑️  Supprimer un backup."""
    if not confirm and not Confirm.ask(f"[yellow]Supprimer le backup '{backup_id}' ?[/yellow]"):
        console.print("[dim]Annulé.[/dim]")
        return
    _run_tool(ctx, "backup_delete", {"backup_id": backup_id},
              lambda r: show_success(f"Backup supprimé: {backup_id} ({r.get('files_deleted', 0)} fichiers)"), jflag)


@backup.command("restore-file")
@click.argument("archive_path", type=click.Path(exists=True))
@click.option("--confirm", is_flag=True, help="Confirmer la restauration")
@click.option("--json", "-j", "jflag", is_flag=True, help="JSON brut")
@click.pass_context
def backup_restore_file(ctx, archive_path, confirm, jflag):
    """📦 Restaurer depuis une archive tar.gz locale (avec documents S3)."""
    file_size = os.path.getsize(archive_path)
    size_mb = file_size / (1024 * 1024)

    if not confirm and not Confirm.ask(
        f"[yellow]Restaurer depuis '{archive_path}' ({size_mb:.1f} MB) ?\n"
        f"La mémoire ne doit pas exister.[/yellow]"
    ):
        console.print("[dim]Annulé.[/dim]")
        return

    async def _run():
        try:
            console.print(f"📦 Lecture de l'archive ({size_mb:.1f} MB)...")
            with open(archive_path, "rb") as f:
                archive_bytes = f.read()
            archive_b64 = base64.b64encode(archive_bytes).decode("ascii")

            console.print("📥 Envoi au serveur pour restauration...")
            client = MCPClient(ctx.obj["url"], ctx.obj["token"])
            result = await client.call_tool("backup_restore_archive", {
                "archive_base64": archive_b64,
            })

            if jflag:
                show_json(result)
            elif result.get("status") == "ok":
                show_restore_result(result)
            else:
                show_error(result.get("message", str(result)))
        except Exception as e:
            show_error(str(e))
    asyncio.run(_run())


# =============================================================================
# Shell (délègue à shell.py)
# =============================================================================

@cli.command()
@click.pass_context
def shell(ctx):
    """🐚 Mode shell interactif."""
    from .shell import run_shell
    run_shell(ctx.obj["url"], ctx.obj["token"])
