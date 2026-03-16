# -*- coding: utf-8 -*-
"""
Helpers d'affichage Rich pour la CLI MCP Memory.

Fournit des fonctions réutilisables pour formater et afficher :
  - Tables (mémoires, documents, entités, relations)
  - Panels (info, erreur, résumé)
  - Statistiques de graphe
"""

from collections import Counter, defaultdict
from typing import List, Dict, Any

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.markdown import Markdown

console = Console()


# =============================================================================
# Affichage des mémoires
# =============================================================================

def show_memories_table(memories: List[dict], current_memory: str = None):
    """Affiche la liste des mémoires dans un tableau."""
    if not memories:
        console.print("[yellow]Aucune mémoire trouvée.[/yellow]")
        return

    table = Table(title=f"📚 Mémoires ({len(memories)})", show_header=True)
    table.add_column("ID", style="cyan bold", no_wrap=True)
    table.add_column("Nom", style="white")
    table.add_column("Ontologie", style="magenta")
    table.add_column("Description", style="dim", max_width=30)
    table.add_column("", width=3)

    for m in memories:
        marker = "→" if m.get("id") == current_memory else ""
        table.add_row(
            m.get("id", ""),
            m.get("name", ""),
            m.get("ontology", "?"),
            (m.get("description", "") or "")[:30],
            marker,
        )

    console.print(table)
    console.print("[dim]Utilisez: use <ID>[/dim]")


# =============================================================================
# Affichage des documents
# =============================================================================

def show_documents_table(docs: List[dict], memory_id: str):
    """Affiche la liste des documents dans un tableau."""
    import os
    if not docs:
        console.print(f"[yellow]Aucun document dans '{memory_id}'.[/yellow]")
        return

    table = Table(title=f"📄 Documents de {memory_id} ({len(docs)})")
    table.add_column("#", style="dim", width=3)
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Fichier", style="white")
    table.add_column("Répertoire", style="blue")
    table.add_column("Ingéré le", style="green", width=12)

    for i, d in enumerate(docs, 1):
        doc_id = d.get("id", "")
        ingested = d.get("ingested_at", "")[:10] if d.get("ingested_at") else "-"
        # Extraire le répertoire depuis source_path
        source_path = d.get("source_path", "")
        directory = os.path.dirname(source_path) if source_path else "-"
        if not directory:
            directory = "."
        table.add_row(
            str(i),
            doc_id,
            d.get("filename", ""),
            directory,
            ingested,
        )

    console.print(table)


# =============================================================================
# Affichage du graphe (résumé complet)
# =============================================================================

def show_graph_summary(graph_data: dict, memory_id: str):
    """
    Affiche un résumé complet et lisible du graphe d'une mémoire.

    Inclut :
      - Compteurs globaux (entités, relations, documents)
      - Entités par type (tableau)
      - Relations par type (tableau)
      - Liste des documents
      - Top 5 nœuds les plus connectés
    """
    nodes = graph_data.get("nodes", [])
    edges = graph_data.get("edges", [])
    docs = graph_data.get("documents", [])

    # --- Panneau de résumé ---
    entity_nodes = [n for n in nodes if n.get("node_type") == "entity"]
    non_mention_edges = [e for e in edges if e.get("type") != "MENTIONS"]

    console.print(Panel.fit(
        f"[bold]Entités:[/bold] [cyan]{len(entity_nodes)}[/cyan]  "
        f"[bold]Relations:[/bold] [cyan]{len(non_mention_edges)}[/cyan]  "
        f"[bold]Documents:[/bold] [cyan]{len(docs)}[/cyan]  "
        f"[bold]MENTIONS:[/bold] [dim]{len(edges) - len(non_mention_edges)}[/dim]",
        title=f"📊 Graphe: {memory_id}",
        border_style="blue",
    ))

    # --- Entités par type ---
    by_type = defaultdict(list)
    for n in entity_nodes:
        by_type[n.get("type", "Unknown")].append(n)

    table_ent = Table(title="📦 Entités par type", show_header=True)
    table_ent.add_column("Type", style="magenta bold")
    table_ent.add_column("Nb", style="cyan", justify="right", width=4)
    table_ent.add_column("Exemples", style="white")

    for etype in sorted(by_type, key=lambda t: -len(by_type[t])):
        entities = by_type[etype]
        examples = ", ".join(e.get("label", "?")[:30] for e in entities[:4])
        if len(entities) > 4:
            examples += f" … (+{len(entities) - 4})"
        table_ent.add_row(etype, str(len(entities)), examples)

    console.print(table_ent)

    # --- Relations par type ---
    rel_types = Counter(e.get("type", "?") for e in non_mention_edges)
    if rel_types:
        table_rel = Table(title="🔗 Relations par type", show_header=True)
        table_rel.add_column("Type", style="blue bold")
        table_rel.add_column("Nb", style="cyan", justify="right", width=4)

        for rtype, count in rel_types.most_common():
            table_rel.add_row(rtype, str(count))

        console.print(table_rel)

    # --- Documents ---
    if docs:
        console.print("\n[bold]📄 Documents:[/bold]")
        for d in docs:
            console.print(f"  • [cyan]{d.get('filename', '?')}[/cyan]  [dim]({d.get('id', '?')[:8]}…)[/dim]")

    # --- Top nœuds connectés ---
    hub_count: Counter = Counter()
    for e in non_mention_edges:
        hub_count[e.get("from", "")] += 1
        hub_count[e.get("to", "")] += 1

    if hub_count:
        console.print("\n[bold]🏢 Top 5 nœuds (nb relations):[/bold]")
        for name, c in hub_count.most_common(5):
            console.print(f"  {name}: [cyan]{c}[/cyan]")


# =============================================================================
# Affichage d'une entité et son contexte
# =============================================================================

def show_entity_context(context: dict):
    """Affiche le contexte d'une entité (relations, documents, voisins)."""
    name = context.get("entity_name", "?")
    etype = context.get("entity_type", "?")

    console.print(Panel.fit(
        f"[bold]Nom:[/bold] [cyan]{name}[/cyan]\n"
        f"[bold]Type:[/bold] [magenta]{etype}[/magenta]",
        title="🔍 Entité",
        border_style="cyan",
    ))

    # Relations
    relations = context.get("relations", [])
    if relations:
        table = Table(title=f"🔗 Relations ({len(relations)})", show_header=True)
        table.add_column("Type", style="blue bold")
        table.add_column("Vers", style="white")
        table.add_column("Description", style="dim", max_width=40)

        for r in relations:
            table.add_row(
                r.get("type", "?"),
                r.get("target", r.get("to", "?")),
                (r.get("description", "") or "")[:40],
            )
        console.print(table)

    # Documents
    documents = context.get("documents", [])
    if documents:
        console.print(f"\n[bold]📄 Mentionné dans {len(documents)} document(s):[/bold]")
        for d in documents:
            if isinstance(d, dict):
                console.print(f"  • [cyan]{d.get('filename', d.get('id', '?'))}[/cyan]")
            else:
                console.print(f"  • [cyan]{d}[/cyan]")

    # Entités liées
    related = context.get("related_entities", [])
    if related:
        console.print(f"\n[bold]🔗 Entités liées ({len(related)}):[/bold]")
        for r in related:
            if isinstance(r, dict):
                console.print(f"  • [{r.get('type', '?')}] [white]{r.get('name', '?')}[/white]")
            else:
                console.print(f"  • [white]{r}[/white]")


# =============================================================================
# Affichage d'ingestion
# =============================================================================

def _colorize_step(msg: str) -> str:
    """Colorie une étape d'ingestion selon son type."""
    # Mapping emoji → couleur Rich
    color_map = {
        "📦": "cyan",      # Décodage
        "📤": "blue",      # Upload S3
        "📄": "white",     # Extraction texte
        "🔍": "yellow",    # LLM extraction
        "📊": "magenta",   # Neo4j
        "🧩": "cyan",      # RAG/Chunking
        "🔢": "blue",      # Embedding
        "📦": "cyan",      # Stockage Qdrant
        "✅": "green",     # Succès
        "🔄": "yellow",    # Force/suppression
        "🏁": "green bold", # Terminé
    }
    for emoji, color in color_map.items():
        if msg.startswith(emoji):
            return f"[{color}]{msg}[/{color}]"
    return msg


def show_ingest_result(result: dict):
    """Affiche le résultat d'une ingestion avec timeline colorée + panneau enrichi."""
    doc_id = result.get("document_id", "?")
    filename = result.get("filename", "?")
    e_new = result.get("entities_created", 0)
    e_merged = result.get("entities_merged", 0)
    r_new = result.get("relations_created", 0)
    r_merged = result.get("relations_merged", 0)
    chunks = result.get("chunks_stored", 0)
    elapsed = result.get("elapsed_seconds", result.get("_elapsed_seconds", None))
    size_bytes = result.get("size_bytes", 0)

    # === Timeline des étapes (si disponible) ===
    steps = result.get("steps", [])
    if steps:
        step_lines = []
        for step in steps:
            t = step.get("t", 0)
            msg = step.get("msg", "")
            m, s = divmod(int(t), 60)
            colored = _colorize_step(msg)
            step_lines.append(f"  [dim]{m:02d}:{s:02d}[/dim]  {colored}")
        console.print(Panel.fit(
            "\n".join(step_lines),
            title="📋 Pipeline d'ingestion",
            border_style="blue",
        ))

    # === Panneau résultat ===
    timing_str = ""
    if elapsed is not None:
        m, s = divmod(int(elapsed), 60)
        timing_str = f"  [dim]⏱ {m:02d}:{s:02d}[/dim]"

    size_str = _format_size(size_bytes) if size_bytes else ""

    lines = []
    lines.append(f"[bold]Fichier:[/bold]   [cyan]{filename}[/cyan]" + (f"  ({size_str})" if size_str else ""))
    lines.append(f"[bold]ID:[/bold]        [dim]{doc_id}[/dim]")
    lines.append(f"[bold]Entités:[/bold]   [cyan]{e_new}[/cyan] nouvelles + [yellow]{e_merged}[/yellow] fusionnées = [bold]{e_new + e_merged}[/bold]")
    lines.append(f"[bold]Relations:[/bold] [cyan]{r_new}[/cyan] nouvelles + [yellow]{r_merged}[/yellow] fusionnées = [bold]{r_new + r_merged}[/bold]")
    if chunks > 0:
        lines.append(f"[bold]RAG:[/bold]       [green]{chunks}[/green] chunks vectorisés")

    # Types d'entités (compact)
    entity_types = result.get("entity_types", {})
    if entity_types:
        types_str = " ".join(
            f"[magenta]{t}[/magenta]:{c}"
            for t, c in sorted(entity_types.items(), key=lambda x: -x[1])
        )
        lines.append(f"[bold]Types E:[/bold]   {types_str}")

    # Types de relations (compact)
    relation_types = result.get("relation_types", {})
    if relation_types:
        rels_str = " ".join(
            f"[blue]{t}[/blue]:{c}"
            for t, c in sorted(relation_types.items(), key=lambda x: -x[1])
        )
        lines.append(f"[bold]Types R:[/bold]   {rels_str}")

    # Sujets
    topics = result.get("key_topics", [])
    if topics:
        lines.append(f"[bold]Sujets:[/bold]    [dim]{', '.join(topics[:6])}[/dim]")

    # Résumé
    summary = result.get("summary", "")
    if summary:
        lines.append(f"[bold]Résumé:[/bold]    [dim]{summary[:150]}{'…' if len(summary) > 150 else ''}[/dim]")

    console.print(Panel.fit(
        "\n".join(lines),
        title=f"✅ Document ingéré{timing_str}",
        border_style="green",
    ))


# =============================================================================
# Utilitaires
# =============================================================================

def show_error(msg: str):
    """Affiche un message d'erreur."""
    console.print(f"[red]❌ {msg}[/red]")


def show_success(msg: str):
    """Affiche un message de succès."""
    console.print(f"[green]✅ {msg}[/green]")


def show_warning(msg: str):
    """Affiche un avertissement."""
    console.print(f"[yellow]⚠️ {msg}[/yellow]")


def show_storage_check(result: dict):
    """
    Affiche le rapport de vérification S3 dans un format lisible.
    
    Affiche :
    - Panneau résumé (docs accessibles, manquants, orphelins)
    - Tableau des documents vérifiés (avec statut)
    - Tableau des fichiers orphelins sur S3
    """
    if result.get("status") != "ok":
        show_error(result.get("message", "Erreur lors du check S3"))
        return
    
    scope = result.get("scope", "all")
    graph_docs = result.get("graph_documents", {})
    orphans = result.get("s3_orphans", {})
    
    # --- Panneau résumé ---
    summary = result.get("summary", "")
    console.print(Panel.fit(
        f"[bold]Scope:[/bold] [cyan]{scope}[/cyan]  "
        f"[bold]Mémoires:[/bold] [cyan]{result.get('memories_checked', 0)}[/cyan]  "
        f"[bold]Objets S3:[/bold] [cyan]{result.get('s3_total_objects', 0)}[/cyan]\n\n"
        f"{summary}",
        title="🔍 Vérification S3",
        border_style="blue",
    ))
    
    # --- Tableau des documents du graphe ---
    details = graph_docs.get("details", [])
    if details:
        table = Table(
            title=f"📄 Documents dans le graphe ({graph_docs.get('total', 0)})",
            show_header=True
        )
        table.add_column("Statut", width=3)
        table.add_column("Mémoire", style="cyan", max_width=20)
        table.add_column("Fichier", style="white", max_width=30)
        table.add_column("Taille", style="dim", justify="right", width=10)
        table.add_column("Type", style="dim", max_width=15)
        
        for d in details:
            status_icon = {
                "ok": "[green]✅[/green]",
                "missing": "[red]❌[/red]",
                "error": "[yellow]⚠️[/yellow]",
            }.get(d.get("status", ""), "❓")
            
            size = d.get("size_bytes", 0)
            size_str = _format_size(size) if size > 0 else "-"
            
            table.add_row(
                status_icon,
                d.get("memory_id", "?"),
                d.get("filename", d.get("key", "?"))[:30],
                size_str,
                d.get("content_type", "")[:15] if d.get("content_type") else "-",
            )
        
        console.print(table)
    
    # --- Tableau des orphelins ---
    orphan_files = orphans.get("files", [])
    if orphan_files:
        table = Table(
            title=f"⚠️ Fichiers orphelins S3 ({orphans.get('count', 0)}, {orphans.get('total_size', '?')})",
            show_header=True,
            border_style="yellow"
        )
        table.add_column("#", style="dim", width=3)
        table.add_column("Clé S3", style="yellow", max_width=50)
        table.add_column("Taille", style="dim", justify="right", width=10)
        table.add_column("Modifié le", style="dim", width=12)
        
        for i, o in enumerate(orphan_files, 1):
            table.add_row(
                str(i),
                o.get("key", "?")[:50],
                _format_size(o.get("size", 0)),
                str(o.get("last_modified", ""))[:10],
            )
        
        console.print(table)
        console.print("[dim]Pour nettoyer: cleanup (dry run) ou cleanup --force (suppression)[/dim]")
    elif graph_docs.get("total", 0) > 0:
        console.print("[green]✅ Aucun fichier orphelin sur S3. Stockage propre ![/green]")


def show_cleanup_result(result: dict):
    """Affiche le résultat du nettoyage S3."""
    if result.get("status") != "ok":
        show_error(result.get("message", "Erreur"))
        return
    
    message = result.get("message", "")
    console.print(f"\n{message}")
    
    if result.get("dry_run") and result.get("files"):
        files = result["files"]
        table = Table(title="📋 Fichiers à supprimer", show_header=True)
        table.add_column("#", style="dim", width=3)
        table.add_column("Clé S3", style="yellow", max_width=50)
        table.add_column("Taille", style="dim", justify="right", width=10)
        
        for i, f in enumerate(files, 1):
            table.add_row(
                str(i),
                f.get("key", "?")[:50],
                _format_size(f.get("size", 0)),
            )
        console.print(table)


def format_size(size_bytes: int) -> str:
    """Convertit des bytes en taille lisible (ex: 1024 → '1.0 KB')."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


# Alias rétrocompatible (ancien nom privé)
_format_size = format_size


# =============================================================================
# Affichage partagé : panel pré-vol d'ingestion
# =============================================================================

def show_ingest_preflight(filename: str, file_size: int, file_ext: str,
                          memory_id: str, force: bool = False):
    """Affiche le panel pré-vol avant une ingestion (partagé CLI Click / Shell)."""
    console.print(Panel.fit(
        f"[bold]Fichier:[/bold]  [cyan]{filename}[/cyan]\n"
        f"[bold]Taille:[/bold]  [cyan]{format_size(file_size)}[/cyan]  "
        f"[bold]Type:[/bold] [cyan]{file_ext}[/cyan]  "
        f"[bold]Mémoire:[/bold] [cyan]{memory_id}[/cyan]"
        + (f"\n[bold]Mode:[/bold]   [yellow]Force (ré-ingestion)[/yellow]" if force else ""),
        title="📥 Ingestion", border_style="blue",
    ))


# =============================================================================
# Affichage partagé : entités par type (avec documents sources)
# =============================================================================

def show_entities_by_type(graph_data: dict):
    """
    Affiche les entités par type avec leurs documents sources.

    Extrait les entités du graphe, mappe les relations MENTIONS vers les
    noms de fichiers, et affiche un tableau par type d'entité.
    Retourne True si des entités existent, False sinon.

    Utilisé par : commands.py (memory_entities) et shell.py (cmd_entities).
    """
    nodes = [n for n in graph_data.get("nodes", []) if n.get("node_type") == "entity"]
    if not nodes:
        show_warning("Aucune entité dans cette mémoire.")
        return False

    # Mapping entité → documents via MENTIONS
    edges = graph_data.get("edges", [])
    docs_by_id = {}
    for d in graph_data.get("documents", []):
        did = d.get("id", "")
        fname = d.get("filename", "?")
        docs_by_id[did] = fname
        docs_by_id[f"doc:{did}"] = fname

    entity_docs = {}
    for e in edges:
        if e.get("type") == "MENTIONS":
            from_id = e.get("from", "")
            to_label = e.get("to", "")
            fname = docs_by_id.get(from_id, "")
            if fname:
                entity_docs.setdefault(to_label, set()).add(fname)

    by_type = defaultdict(list)
    for n in nodes:
        by_type[n.get("type", "?")].append(n)

    for etype in sorted(by_type, key=lambda t: -len(by_type[t])):
        entities = by_type[etype]
        table = Table(
            title=f"[magenta]{etype}[/magenta] ({len(entities)})",
            show_header=True, show_lines=False
        )
        table.add_column("Nom", style="white")
        table.add_column("Description", style="dim", max_width=40)
        table.add_column("Document(s)", style="cyan")

        for ent in entities:
            label = ent.get("label", "?")
            doc_list = entity_docs.get(label, set())
            doc_str = ", ".join(sorted(doc_list)) if doc_list else "-"
            table.add_row(
                label[:40],
                (ent.get("description", "") or "")[:40],
                doc_str,
            )
        console.print(table)

    return True


# =============================================================================
# Affichage partagé : relations par type
# =============================================================================

def show_relations_by_type(graph_data: dict, type_filter: str = None):
    """
    Affiche les relations du graphe.

    - Sans type_filter : résumé avec compteurs par type et exemples.
    - Avec type_filter : liste détaillée de toutes les relations de ce type.
    Retourne True si des relations existent, False sinon.

    Utilisé par : commands.py (memory_relations) et shell.py (cmd_relations).
    """
    edges = graph_data.get("edges", [])
    if not edges:
        show_warning("Aucune relation dans cette mémoire.")
        return False

    if type_filter:
        # --- Mode détaillé : toutes les relations d'un type ---
        filtered = [e for e in edges if e.get("type", "").upper() == type_filter.upper()]
        if not filtered:
            available = sorted(set(e.get("type", "?") for e in edges))
            show_error(f"Type '{type_filter}' non trouvé.")
            console.print(f"[dim]Types disponibles: {', '.join(available)}[/dim]")
            return True  # Des relations existent, juste pas ce type

        table = Table(
            title=f"🔗 {type_filter.upper()} ({len(filtered)} relations)",
            show_header=True
        )
        table.add_column("De", style="white")
        table.add_column("→", style="dim", width=2)
        table.add_column("Vers", style="cyan")
        table.add_column("Description", style="dim", max_width=40)

        for e in filtered:
            table.add_row(
                e.get("from", "?")[:35],
                "→",
                e.get("to", "?")[:35],
                (e.get("description", "") or "")[:40],
            )
        console.print(table)
    else:
        # --- Mode résumé : compteurs par type ---
        rel_types = Counter(e.get("type", "?") for e in edges)
        table = Table(title=f"🔗 Relations ({len(edges)} total)", show_header=True)
        table.add_column("Type", style="blue bold")
        table.add_column("Nombre", style="cyan", justify="right")
        table.add_column("Exemples", style="dim")

        for rtype, count in rel_types.most_common():
            examples = [e for e in edges if e.get("type") == rtype][:3]
            ex_str = ", ".join(
                f"{e.get('from', '?')} → {e.get('to', '?')}" for e in examples
            )
            table.add_row(rtype, str(count), ex_str[:60])

        console.print(table)
        if not type_filter:
            console.print("[dim]Deepdive: relations <TYPE> (ex: relations HAS_DURATION)[/dim]")

    return True


# =============================================================================
# Affichage des tokens
# =============================================================================

def show_tokens_table(tokens: List[dict]):
    """Affiche la liste des tokens dans un tableau."""
    if not tokens:
        console.print("[yellow]Aucun token trouvé.[/yellow]")
        return

    table = Table(title=f"🔑 Tokens ({len(tokens)})", show_header=True)
    table.add_column("Client", style="cyan bold", no_wrap=True)
    table.add_column("Email", style="white", max_width=25)
    table.add_column("Hash (ID)", style="yellow", no_wrap=True)
    table.add_column("Permissions", style="magenta")
    table.add_column("Mémoires", style="green")
    table.add_column("Créé le", style="dim", width=12)
    table.add_column("Expire", style="dim", width=12)

    for t in tokens:
        perms = ", ".join(t.get("permissions", []))
        memories = t.get("memory_ids", [])
        mem_str = ", ".join(memories) if memories else "[dim]toutes[/dim]"
        created = (t.get("created_at") or "")[:10]
        expires = (t.get("expires_at") or "jamais")[:10]
        email = t.get("email") or "[dim]-[/dim]"
        token_hash = t.get("token_hash", t.get("token_hash_prefix", "?"))

        table.add_row(
            t.get("client_name", "?"),
            email,
            token_hash,
            perms,
            mem_str,
            created,
            expires,
        )

    console.print(table)
    console.print("[dim]💡 Copiez le Hash pour: token revoke <hash>, token grant <hash> ...[/dim]")


def show_token_created(result: dict):
    """Affiche le résultat de création d'un token."""
    email_line = f"\n[bold]Email:[/bold]       [white]{result['email']}[/white]" if result.get('email') else ""
    console.print(Panel.fit(
        f"[bold]Client:[/bold]      [cyan]{result.get('client_name', '?')}[/cyan]{email_line}\n"
        f"[bold]Token:[/bold]       [green bold]{result.get('token', '?')}[/green bold]\n"
        f"[bold]Permissions:[/bold] [magenta]{', '.join(result.get('permissions', []))}[/magenta]\n"
        f"[bold]Mémoires:[/bold]    {', '.join(result.get('memory_ids', [])) or '[dim]toutes[/dim]'}",
        title="🔑 Token créé",
        border_style="green",
    ))
    console.print("[yellow]⚠️  Conservez ce token précieusement, il ne sera plus affiché ![/yellow]")


def show_token_updated(result: dict):
    """Affiche le résultat d'une mise à jour de token."""
    prev = result.get("previous_memories", [])
    curr = result.get("current_memories", [])
    console.print(Panel.fit(
        f"[bold]Client:[/bold]      [cyan]{result.get('client_name', '?')}[/cyan]\n"
        f"[bold]Hash:[/bold]        [dim]{result.get('token_hash_prefix', '?')}[/dim]\n"
        f"[bold]Avant:[/bold]       {', '.join(prev) if prev else '[dim]toutes[/dim]'}\n"
        f"[bold]Après:[/bold]       {', '.join(curr) if curr else '[dim]toutes[/dim]'}",
        title="🔑 Token mis à jour",
        border_style="cyan",
    ))


def show_query_result(result: dict):
    """
    Affiche le résultat d'un memory_query (données structurées, pas de réponse LLM).
    
    Sections :
    - Bannière stats (mode, entités, chunks, docs)
    - Entités enrichies (type, description, relations, documents)
    - Chunks RAG (score, section, extrait)
    - Documents sources
    """
    stats = result.get("stats", {})
    query = result.get("query", "?")
    mode = result.get("retrieval_mode", "?")
    
    # --- Bannière stats ---
    console.print(Panel.fit(
        f"[bold]Query:[/bold]      [cyan]{query}[/cyan]\n"
        f"[bold]Mode:[/bold]       [yellow]{mode}[/yellow]\n"
        f"[bold]Entités:[/bold]    [green]{stats.get('entities_found', 0)}[/green]  "
        f"[bold]RAG chunks:[/bold] [green]{stats.get('rag_chunks_retained', 0)}[/green] "
        f"[dim](filtrés: {stats.get('rag_chunks_filtered', 0)}, seuil: {stats.get('rag_score_threshold', '?')})[/dim]  "
        f"[bold]Documents:[/bold] [green]{len(result.get('source_documents', []))}[/green]",
        title="📊 Résultat Query (données structurées)",
        border_style="blue",
    ))
    
    # --- Entités ---
    entities = result.get("entities", [])
    if entities:
        table = Table(title=f"🔗 Entités ({len(entities)})", show_header=True, show_lines=True)
        table.add_column("Nom", style="cyan bold", max_width=30)
        table.add_column("Type", style="magenta", width=15)
        table.add_column("Description", style="white", max_width=40)
        table.add_column("Documents", style="dim", max_width=20)
        table.add_column("Relations", style="dim", max_width=25)
        
        for e in entities:
            docs_str = ", ".join(e.get("source_documents", []))[:20] or "-"
            rels = e.get("relations", [])
            rels_str = ", ".join(f"{r['type']}→{r['target']}" for r in rels[:3])
            if len(rels) > 3:
                rels_str += f" (+{len(rels)-3})"
            table.add_row(
                e.get("name", "?")[:30],
                e.get("type", "?"),
                (e.get("description", "") or "")[:40],
                docs_str,
                rels_str or "-",
            )
        console.print(table)
    
    # --- Chunks RAG ---
    rag_chunks = result.get("rag_chunks", [])
    if rag_chunks:
        table = Table(title=f"📎 Chunks RAG ({len(rag_chunks)})", show_header=True, show_lines=True)
        table.add_column("#", style="dim", width=3)
        table.add_column("Score", style="green", width=7)
        table.add_column("Section", style="yellow", max_width=25)
        table.add_column("Document", style="cyan", max_width=20)
        table.add_column("Extrait", style="white", max_width=50)
        
        for i, chunk in enumerate(rag_chunks, 1):
            section = chunk.get("section_title") or chunk.get("article_number") or "-"
            preview = (chunk.get("text", "")[:80]).replace("\n", " ").strip()
            table.add_row(
                str(i),
                f"{chunk.get('score', 0):.4f}",
                section[:25],
                chunk.get("filename", "?")[:20],
                preview + ("…" if len(chunk.get("text", "")) > 80 else ""),
            )
        console.print(table)
    
    # --- Documents sources ---
    source_docs = result.get("source_documents", [])
    if source_docs:
        console.print(f"\n[bold]📄 Documents sources ({len(source_docs)}):[/bold]")
        for doc in source_docs:
            console.print(f"  • [cyan]{doc.get('filename', '?')}[/cyan]  [dim]({doc.get('id', '?')[:8]}…)[/dim]")


def show_backup_result(result: dict):
    """Affiche le résultat d'un backup."""
    from rich.panel import Panel
    
    stats = result.get("stats", {})
    lines = [
        f"[bold]Backup ID:[/bold]  [cyan]{result.get('backup_id', '?')}[/cyan]",
        f"[bold]Mémoire:[/bold]    [cyan]{result.get('memory_id', '?')}[/cyan]",
        f"[bold]Date:[/bold]       [dim]{result.get('created_at', '?')}[/dim]",
        f"",
        f"[bold]Entités:[/bold]    [green]{stats.get('entities', 0)}[/green]",
        f"[bold]Relations:[/bold]  [green]{stats.get('relations', 0)}[/green]",
        f"[bold]Documents:[/bold]  [green]{stats.get('documents', 0)}[/green]",
        f"[bold]Vecteurs:[/bold]   [green]{stats.get('qdrant_vectors', 0)}[/green]",
        f"",
        f"[bold]Temps:[/bold]      [dim]{result.get('elapsed_seconds', 0)}s[/dim]",
    ]
    
    retention = result.get("retention_deleted", 0)
    if retention > 0:
        lines.append(f"[bold]Rétention:[/bold] [yellow]{retention} ancien(s) backup(s) supprimé(s)[/yellow]")
    
    console.print(Panel.fit(
        "\n".join(lines),
        title="💾 Backup créé",
        border_style="green"
    ))


def show_backups_table(backups: list):
    """Affiche la liste des backups en table."""
    from rich.table import Table
    
    if not backups:
        console.print("[dim]Aucun backup trouvé.[/dim]")
        return
    
    table = Table(title=f"💾 Backups ({len(backups)})", show_header=True)
    table.add_column("Backup ID", style="cyan", no_wrap=True, min_width=35)
    table.add_column("Mémoire", style="white")
    table.add_column("Date", style="dim", no_wrap=True, min_width=19)
    table.add_column("Entités", style="green", justify="right")
    table.add_column("Relations", style="green", justify="right")
    table.add_column("Vecteurs", style="green", justify="right")
    table.add_column("Docs", style="green", justify="right")
    table.add_column("Description", style="dim", max_width=30)
    
    for b in backups:
        stats = b.get("stats", {})
        table.add_row(
            b.get("backup_id", "?"),
            b.get("memory_name", b.get("memory_id", "?")),
            (b.get("created_at", "") or "")[:19],
            str(stats.get("entities", 0)),
            str(stats.get("relations", 0)),
            str(stats.get("qdrant_vectors", 0)),
            str(stats.get("documents", 0)),
            (b.get("description", "") or "")[:30],
        )
    
    console.print(table)


def show_restore_result(result: dict):
    """Affiche le résultat d'une restauration."""
    from rich.panel import Panel
    
    graph = result.get("graph", {})
    lines = [
        f"[bold]Backup ID:[/bold]  [cyan]{result.get('backup_id', '?')}[/cyan]",
        f"[bold]Mémoire:[/bold]    [cyan]{result.get('memory_id', '?')}[/cyan]",
        f"",
        f"[bold green]Graphe restauré:[/bold green]",
        f"  Memory:    [green]{graph.get('memory', 0)}[/green]",
        f"  Documents: [green]{graph.get('documents', 0)}[/green]",
        f"  Entités:   [green]{graph.get('entities', 0)}[/green]",
        f"  Relations: [green]{graph.get('relations', 0)}[/green]",
        f"  Mentions:  [green]{graph.get('mentions', 0)}[/green]",
        f"",
        f"[bold green]Vecteurs:[/bold green]   [green]{result.get('qdrant_vectors_restored', 0)}[/green] restaurés",
        f"[bold]Docs S3:[/bold]    [green]{result.get('s3_documents_ok', 0)}[/green] OK",
    ]
    
    missing = result.get("s3_documents_missing", 0)
    if missing > 0:
        lines.append(f"            [red]{missing} manquant(s)[/red]")
    
    lines.append(f"")
    lines.append(f"[bold]Temps:[/bold]      [dim]{result.get('elapsed_seconds', 0)}s[/dim]")
    
    console.print(Panel.fit(
        "\n".join(lines),
        title="📥 Restauration terminée",
        border_style="green"
    ))


def show_about(result: dict):
    """Affiche les informations du service MCP Memory (system_about)."""
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.columns import Columns
    
    console = Console()
    
    identity = result.get("identity", {})
    capabilities = result.get("capabilities", {})
    memories = result.get("memories", [])
    services = result.get("services", {})
    config = result.get("configuration", {})
    
    # === Identité ===
    id_text = (
        f"[bold cyan]{identity.get('name', '?')}[/bold cyan] "
        f"v{identity.get('version', '?')} — {identity.get('provider', '?')}\n\n"
        f"[bold]Description[/bold]\n{identity.get('description', '')}\n\n"
        f"[bold]Objectif[/bold]\n{identity.get('purpose', '')}\n\n"
        f"[bold]Approche[/bold]\n{identity.get('approach', '')}\n\n"
        f"[dim]Repo: {identity.get('repo', '')}[/dim]"
    )
    console.print(Panel(id_text, title="🧠 Qui suis-je ?", border_style="cyan"))
    
    # === Services ===
    svc_parts = []
    for name, status in services.items():
        icon = "✅" if status == "ok" else "❌"
        svc_parts.append(f"{icon} {name}")
    console.print(Panel("  ".join(svc_parts), title="🔌 Services", border_style="green" if all(s == "ok" for s in services.values()) else "red"))
    
    # === Capacités ===
    cats = capabilities.get("categories", {})
    tools_total = capabilities.get("total_tools", 0)
    cat_parts = [f"[bold]{k}[/bold]: {v}" for k, v in cats.items()]
    formats = ", ".join(capabilities.get("supported_formats", []))
    
    onto_parts = []
    for o in capabilities.get("ontologies", []):
        onto_parts.append(f"• {o.get('name', '?')}: {o.get('description', '')[:60]}")
    
    cap_text = (
        f"[bold]{tools_total} outils MCP[/bold] répartis en {len(cats)} catégories :\n"
        + "  " + " | ".join(cat_parts) + "\n\n"
        f"[bold]Formats supportés[/bold] : {formats}\n\n"
        f"[bold]Ontologies ({len(onto_parts)})[/bold] :\n" + "\n".join(onto_parts)
    )
    console.print(Panel(cap_text, title="⚡ Capacités", border_style="yellow"))
    
    # === Mémoires actives ===
    if memories:
        table = Table(title=f"📚 Mémoires actives ({len(memories)})", show_lines=False)
        table.add_column("ID", style="bold cyan")
        table.add_column("Nom", style="white")
        table.add_column("Ontologie", style="yellow")
        table.add_column("Docs", style="green", justify="right")
        table.add_column("Entités", style="green", justify="right")
        table.add_column("Relations", style="green", justify="right")
        
        for m in memories:
            table.add_row(
                m.get("id", "?"),
                m.get("name", "?"),
                m.get("ontology", "?"),
                str(m.get("documents", 0)),
                str(m.get("entities", 0)),
                str(m.get("relations", 0)),
            )
        console.print(table)
    else:
        console.print("[dim]Aucune mémoire active.[/dim]")
    
    # === Configuration ===
    cfg_parts = [
        f"LLM: [bold]{config.get('llm_model', '?')}[/bold]",
        f"Embedding: [bold]{config.get('embedding_model', '?')}[/bold] ({config.get('embedding_dimensions', '?')}d)",
        f"RAG seuil: {config.get('rag_score_threshold', '?')}",
        f"Chunk: {config.get('chunk_size', '?')} tokens",
        f"Backup rétention: {config.get('backup_retention', '?')}",
    ]
    console.print(Panel("  |  ".join(cfg_parts), title="⚙️ Configuration", border_style="dim"))


def show_answer(answer: str, entities: list = None, source_documents: list = None):
    """Affiche une réponse Q&A avec les documents sources."""
    console.print(Panel.fit(
        Markdown(answer),
        title="💡 Réponse",
        border_style="green",
    ))

    # Documents sources
    if source_documents:
        console.print(f"\n[bold]📄 Documents sources ({len(source_documents)}):[/bold]")
        for doc in source_documents:
            if isinstance(doc, dict):
                console.print(f"  • [cyan]{doc.get('filename', '?')}[/cyan]  [dim]({doc.get('id', '?')[:8]}…)[/dim]")
            else:
                console.print(f"  • [cyan]{doc}[/cyan]")

    # Entités liées
    if entities:
        console.print(f"[dim]Entités liées: {', '.join(str(e) for e in entities)}[/dim]")


# =============================================================================
# JSON brut (--json)
# =============================================================================

def show_json(data: dict):
    """Affiche un dict en JSON coloré (pour le flag --json)."""
    import json
    from rich.syntax import Syntax
    console.print(Syntax(
        json.dumps(data, indent=2, ensure_ascii=False, default=str), "json"
    ))


# =============================================================================
# Whoami (identité du token)
# =============================================================================

def show_whoami_result(result: dict):
    """Affiche le résultat de system_whoami."""
    auth_type = result.get("auth_type", "?")
    type_icon = "🔑" if auth_type == "bootstrap" else "🏷️" if auth_type == "token" else "🏠"
    perms = result.get("permissions", [])

    # Icônes de permissions
    perm_icons = []
    if "read" in perms:
        perm_icons.append("🔑 read")
    if "write" in perms:
        perm_icons.append("✏️ write")
    if "admin" in perms:
        perm_icons.append("👑 admin")
    perm_display = "  ".join(perm_icons) if perm_icons else "aucune"

    memory_ids = result.get("memory_ids", [])
    memories_str = ", ".join(memory_ids) if memory_ids else "[dim]toutes[/dim]"

    lines = [
        f"[bold]Identité :[/bold] [cyan bold]{result.get('client_name', '?')}[/cyan bold]",
        f"[bold]Type     :[/bold] {type_icon} {auth_type}",
        f"[bold]Droits   :[/bold] {perm_display}",
        f"[bold]Mémoires :[/bold] {memories_str}",
    ]

    # Métadonnées supplémentaires pour les tokens
    if result.get("email"):
        lines.append(f"[bold]Email    :[/bold] {result['email']}")
    if result.get("token_hash"):
        lines.append(f"[bold]Hash     :[/bold] [dim]{result['token_hash']}[/dim]")
    if result.get("created_at"):
        lines.append(f"[bold]Créé le  :[/bold] {result['created_at'][:19]}")
    expires = result.get("expires_at")
    if expires:
        lines.append(f"[bold]Expire   :[/bold] {expires[:19]}")
    elif result.get("auth_type") == "token":
        lines.append(f"[bold]Expire   :[/bold] jamais")
    if result.get("note"):
        lines.append(f"\n[dim italic]{result['note']}[/dim italic]")

    console.print(Panel.fit(
        "\n".join(lines),
        title="👤 Qui suis-je ?", border_style="cyan",
    ))


# =============================================================================
# Health (état de santé des services)
# =============================================================================

def show_health_result(result: dict):
    """Affiche le résultat de system_health."""
    status = result.get("status", "?")
    services = result.get("services", {})
    icon = "✅" if status == "ok" else "⚠️"

    table = Table(title=f"{icon} Health — Services", show_header=True)
    table.add_column("Service", style="cyan bold")
    table.add_column("Statut")
    table.add_column("Détails", style="dim")

    for name, info in services.items():
        if isinstance(info, dict):
            s = info.get("status", "?")
            s_icon = "✅" if s == "ok" else "❌"
            details = info.get("message", info.get("latency_ms", ""))
            table.add_row(name, f"{s_icon} {s}", str(details))
        else:
            table.add_row(name, str(info), "")

    console.print(table)
