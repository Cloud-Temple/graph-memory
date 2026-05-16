#!/usr/bin/env python3
"""
refresh_graph_memory.py — Synchronisation intelligente des fichiers locaux
avec une instance Graph Memory en production.

Compare les hash SHA-256 des fichiers locaux avec ceux ingérés dans Graph Memory,
puis effectue les actions nécessaires : ingestion des nouveaux fichiers,
ré-ingestion des fichiers modifiés, suppression des documents obsolètes.

Usage:
    # Dry-run (affiche le plan sans rien exécuter)
    python3 scripts/refresh_graph_memory.py --url URL --token TOKEN

    # Exécuter la synchronisation
    python3 scripts/refresh_graph_memory.py --url URL --token TOKEN --apply

    # Synchroniser une seule mémoire
    python3 scripts/refresh_graph_memory.py --url URL --token TOKEN --memory DOCS --apply

    # Utiliser les variables d'environnement
    export MCP_URL=https://graph-mem.mcp.cloud-temple.app
    export MCP_TOKEN=your_token_here
    python3 scripts/refresh_graph_memory.py --apply

Mémoires gérées:
    DOCS       — Documentation technique (product_sheets/ + docs/docs/)
    PRESALES   — Documents avant-vente (PRESALES/)
    JURIDIQUE  — Documents juridiques (JURIDIQUE/)

Auteur: Cloud Temple — Graph Memory Team
"""

import argparse
import base64
import hashlib
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

# ============================================================================
# CONFIGURATION DES MÉMOIRES
# ============================================================================
# Chaque mémoire définit ses sources locales, les extensions à scanner,
# les dossiers/fichiers à exclure, et le préfixe pour source_path.

MEMORY_SOURCES = {
    "DOCS": {
        "description": "Documentation technique Cloud Temple",
        "sources": [
            {
                "path": "product_sheets",
                "extensions": [".md"],
                "exclude_dirs": ["01_Templates", "memory-bank", ".git"],
                "exclude_files": ["README.md", "requirements.txt"],
                # source_path relatif au dossier source (pas au repo)
                "source_path_prefix": "",
            },
            {
                "path": "docs/docs",
                "extensions": [".md"],
                "exclude_dirs": [".git", "images"],
                "exclude_files": [],
                "source_path_prefix": "",
            },
        ],
    },
    "PRESALES": {
        "description": "Documents avant-vente Cloud Temple",
        "sources": [
            {
                "path": "PRESALES",
                "extensions": [".md"],
                "exclude_dirs": [".git"],
                "exclude_files": [],
                "source_path_prefix": "",
            },
        ],
    },
    "JURIDIQUE": {
        "description": "Documents juridiques Cloud Temple",
        "sources": [
            {
                "path": "JURIDIQUE",
                "extensions": [".md", ".docx"],
                "exclude_dirs": [".git", "OLD"],
                "exclude_files": [],
                "source_path_prefix": "",
            },
        ],
    },
}


# ============================================================================
# CLIENT MCP GRAPH MEMORY
# ============================================================================

class GraphMemoryClient:
    """Client HTTP pour communiquer avec Graph Memory via le protocole MCP.

    Utilise JSON-RPC 2.0 sur HTTP Streamable (MCP standard).
    Ne dépend que de la bibliothèque standard Python.
    """

    def __init__(self, url: str, token: str, timeout: int = 120):
        self.url = url.rstrip("/")
        self.mcp_endpoint = f"{self.url}/mcp"
        self.token = token
        self.timeout = timeout
        self.session_id = None
        self._request_id = 0

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def _parse_sse_response(self, body: str) -> dict:
        """Parse une réponse SSE et extrait le JSON-RPC result."""
        for line in body.split("\n"):
            line = line.strip()
            if line.startswith("data: "):
                data = line[6:]
                return json.loads(data)
        raise ValueError(f"Pas de données SSE dans la réponse: {body[:200]}")

    def _call_mcp(self, method: str, params: dict = None, timeout: int = None) -> dict:
        """Effectue un appel JSON-RPC au serveur MCP."""
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": method,
        }
        if params:
            payload["params"] = params

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": f"Bearer {self.token}",
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(self.mcp_endpoint, data=data, headers=headers)

        effective_timeout = timeout or self.timeout
        try:
            with urllib.request.urlopen(req, timeout=effective_timeout) as resp:
                # Capturer le session_id
                sid = resp.headers.get("Mcp-Session-Id")
                if sid:
                    self.session_id = sid

                body = resp.read().decode("utf-8")
                content_type = resp.headers.get("Content-Type", "")

                if "text/event-stream" in content_type:
                    result = self._parse_sse_response(body)
                else:
                    result = json.loads(body)

                if "error" in result:
                    raise RuntimeError(
                        f"Erreur MCP: {result['error'].get('message', result['error'])}"
                    )
                return result
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {e.code}: {body[:500]}")

    def _call_tool(self, tool_name: str, arguments: dict = None, timeout: int = None) -> dict:
        """Appelle un outil MCP et retourne le résultat parsé."""
        result = self._call_mcp(
            "tools/call",
            {"name": tool_name, "arguments": arguments or {}},
            timeout=timeout,
        )
        # Extraire le texte du contenu MCP
        content = result.get("result", {}).get("content", [])
        if content and content[0].get("type") == "text":
            return json.loads(content[0]["text"])
        return result.get("result", {})

    # -- Initialisation -------------------------------------------------------

    def initialize(self):
        """Initialise la session MCP (handshake obligatoire)."""
        result = self._call_mcp("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "refresh-graph-memory", "version": "1.0.0"},
        })
        server_info = result.get("result", {}).get("serverInfo", {})
        version = server_info.get("version", "?")
        print(f"  ✅ Session MCP initialisée (serveur {version})")
        return result

    # -- Outils mémoire -------------------------------------------------------

    def health(self) -> dict:
        """Vérifie la santé du serveur."""
        req = urllib.request.Request(
            f"{self.url}/health",
            headers={"Authorization": f"Bearer {self.token}"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def memory_list(self) -> list:
        """Liste les mémoires disponibles."""
        data = self._call_tool("memory_list")
        return data.get("memories", [])

    def memory_stats(self, memory_id: str) -> dict:
        """Statistiques d'une mémoire."""
        return self._call_tool("memory_stats", {"memory_id": memory_id})

    def document_list(self, memory_id: str) -> list:
        """Liste les documents d'une mémoire."""
        data = self._call_tool("document_list", {"memory_id": memory_id})
        return data.get("documents", [])

    def document_delete(self, memory_id: str, document_id: str) -> dict:
        """Supprime un document."""
        return self._call_tool("document_delete", {
            "memory_id": memory_id,
            "document_id": document_id,
        })

    def memory_ingest(
        self, memory_id: str, content_b64: str, filename: str,
        source_path: str = None, force: bool = False,
        source_modified_at: str = None,
    ) -> dict:
        """Ingère un document dans une mémoire.

        Timeout élevé car l'extraction LLM peut prendre 30-120s par fichier.
        """
        args = {
            "memory_id": memory_id,
            "content_base64": content_b64,
            "filename": filename,
            "force": force,
        }
        if source_path:
            args["source_path"] = source_path
        if source_modified_at:
            args["source_modified_at"] = source_modified_at

        # Timeout long pour ingestion (extraction LLM + embedding)
        return self._call_tool("memory_ingest", args, timeout=600)


# ============================================================================
# SCANNER DE FICHIERS LOCAUX
# ============================================================================

def scan_local_files(base_dir: str, source_config: dict) -> list:
    """Scanne les fichiers locaux selon la configuration d'une source.

    Returns:
        Liste de dicts: {path, filename, hash, size, source_path, mtime}
    """
    source_path = os.path.join(base_dir, source_config["path"])
    if not os.path.isdir(source_path):
        print(f"  ⚠️  Dossier introuvable: {source_path}")
        return []

    extensions = set(source_config.get("extensions", [".md"]))
    exclude_dirs = set(source_config.get("exclude_dirs", []))
    exclude_files = set(source_config.get("exclude_files", []))

    files = []
    for root, dirs, filenames in os.walk(source_path):
        # Exclure les dossiers
        dirs[:] = [d for d in dirs if d not in exclude_dirs]

        for fn in filenames:
            # Vérifier extension
            _, ext = os.path.splitext(fn)
            if ext.lower() not in extensions:
                continue
            # Exclure certains fichiers
            if fn in exclude_files:
                continue

            filepath = os.path.join(root, fn)
            rel_path = os.path.relpath(filepath, source_path)

            # Calculer le hash SHA-256
            with open(filepath, "rb") as f:
                content = f.read()
                file_hash = hashlib.sha256(content).hexdigest()

            # Metadata
            stat = os.stat(filepath)
            mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()

            files.append({
                "filepath": filepath,
                "rel_path": rel_path,
                "filename": fn,
                "hash": file_hash,
                "size": stat.st_size,
                "source_path": rel_path,  # Chemin relatif comme source_path
                "mtime": mtime,
            })

    return files


# ============================================================================
# MOTEUR DE COMPARAISON
# ============================================================================

def compute_diff(local_files: list, remote_docs: list) -> dict:
    """Compare les fichiers locaux avec les documents distants.

    La correspondance se fait par source_path (priorité) puis par filename.
    Le hash SHA-256 détermine si le fichier a été modifié.

    Returns:
        {
            "up_to_date": [...],     # Hash identique, rien à faire
            "modified": [...],       # Hash différent, re-ingestion --force
            "new": [...],            # Fichier local absent du distant
            "obsolete": [...],       # Document distant absent du local
            "duplicates": [...],     # Plusieurs docs distants pour même fichier
        }
    """
    # Indexer les docs distants par source_path (nettoyé)
    remote_by_source = {}
    remote_by_filename = {}
    for doc in remote_docs:
        sp = doc.get("source_path", "") or ""
        # Nettoyer le source_path (retirer le préfixe absolu si présent)
        sp_clean = _clean_source_path(sp)
        if sp_clean:
            remote_by_source.setdefault(sp_clean, []).append(doc)
        fn = doc.get("filename", "")
        if fn:
            remote_by_filename.setdefault(fn, []).append(doc)

    up_to_date = []
    modified = []
    new_files = []
    matched_doc_ids = set()

    for local in local_files:
        # Chercher par source_path d'abord
        sp = local["source_path"]
        candidates = remote_by_source.get(sp, [])

        if not candidates:
            # Fallback: chercher par filename
            candidates = remote_by_filename.get(local["filename"], [])

        if not candidates:
            new_files.append(local)
            continue

        # Prendre le plus récent si plusieurs candidats
        best = max(candidates, key=lambda d: d.get("ingested_at", ""))
        matched_doc_ids.add(best["id"])

        if local["hash"] == best.get("hash", ""):
            up_to_date.append({"local": local, "remote": best})
        else:
            modified.append({"local": local, "remote": best})

    # Documents distants non matchés = obsolètes
    obsolete = [doc for doc in remote_docs if doc["id"] not in matched_doc_ids]

    # Détecter les doublons (plusieurs docs pour le même source_path)
    duplicates = []
    for sp, docs in remote_by_source.items():
        if len(docs) > 1:
            # Garder le plus récent, marquer les autres comme doublons
            sorted_docs = sorted(docs, key=lambda d: d.get("ingested_at", ""), reverse=True)
            duplicates.extend(sorted_docs[1:])

    return {
        "up_to_date": up_to_date,
        "modified": modified,
        "new": new_files,
        "obsolete": obsolete,
        "duplicates": duplicates,
    }


def _clean_source_path(source_path: str) -> str:
    """Nettoie un source_path distant pour le rendre comparable au local.

    Retire les préfixes absolus courants et normalise.
    Ex: "/Users/clesur/PROJETS/graph-memory/product_sheets/Compute/X.md"
      → "Compute/X.md"
    """
    if not source_path:
        return ""

    # Retirer les préfixes absolus connus
    prefixes_to_strip = [
        "/Users/clesur/PROJETS/graph-memory/product_sheets/",
        "/Users/clesur/PROJETS/graph-memory/docs/docs/",
        "/Users/clesur/PROJETS/graph-memory/PRESALES/2025/",
        "/Users/clesur/PROJETS/graph-memory/PRESALES/",
        "/Users/clesur/PROJETS/graph-memory/JURIDIQUE/",
        "/Users/clesur/PROJETS/graph-memory/",
        "product_sheets/",
        "docs/docs/",
    ]
    for prefix in prefixes_to_strip:
        if source_path.startswith(prefix):
            return source_path[len(prefix):]

    return source_path


# ============================================================================
# AFFICHAGE
# ============================================================================

def format_size(size_bytes: int) -> str:
    """Formate une taille en bytes de façon lisible."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


def print_header(title: str):
    """Affiche un en-tête formaté."""
    print(f"\n{'=' * 72}")
    print(f"  {title}")
    print(f"{'=' * 72}")


def print_diff_report(memory_id: str, diff: dict):
    """Affiche le rapport de comparaison pour une mémoire."""
    print_header(f"📊 RAPPORT — {memory_id}")

    # Up to date
    n_ok = len(diff["up_to_date"])
    n_mod = len(diff["modified"])
    n_new = len(diff["new"])
    n_obs = len(diff["obsolete"])
    n_dup = len(diff["duplicates"])

    print(f"\n  ✅ Synchronisés  : {n_ok}")
    print(f"  ⚠️  Modifiés      : {n_mod}")
    print(f"  🆕 Nouveaux      : {n_new}")
    print(f"  🗑️  Obsolètes     : {n_obs}")
    print(f"  📋 Doublons      : {n_dup}")

    if diff["modified"]:
        print(f"\n  ⚠️  FICHIERS MODIFIÉS (re-ingestion --force) :")
        for item in diff["modified"]:
            local = item["local"]
            remote = item["remote"]
            dt = remote.get("ingested_at", "")[:10]
            print(f"    → {local['rel_path']} ({format_size(local['size'])}) "
                  f"[ingéré {dt}]")

    if diff["new"]:
        print(f"\n  🆕 NOUVEAUX FICHIERS (ingestion initiale) :")
        for local in diff["new"]:
            print(f"    → {local['rel_path']} ({format_size(local['size'])})")

    if diff["obsolete"]:
        print(f"\n  🗑️  DOCUMENTS OBSOLÈTES (suppression) :")
        for doc in diff["obsolete"]:
            sp = doc.get("source_path", doc.get("filename", "?"))
            dt = doc.get("ingested_at", "")[:10]
            print(f"    → {doc['filename']} [source: {sp}] [ingéré {dt}]")

    if diff["duplicates"]:
        print(f"\n  📋 DOUBLONS (anciennes versions à supprimer) :")
        for doc in diff["duplicates"]:
            dt = doc.get("ingested_at", "")[:10]
            print(f"    → {doc['filename']} ({doc['id'][:8]}) [ingéré {dt}]")


# ============================================================================
# EXÉCUTION DES ACTIONS
# ============================================================================

def execute_sync(client: GraphMemoryClient, memory_id: str, diff: dict):
    """Exécute la synchronisation pour une mémoire.

    Ordre: 1) Supprimer doublons, 2) Supprimer obsolètes,
           3) Ingérer modifiés (--force), 4) Ingérer nouveaux.
    """
    stats = {"deleted": 0, "ingested": 0, "errors": 0, "skipped": 0}

    # 1. Supprimer les doublons
    if diff["duplicates"]:
        print(f"\n  🧹 Suppression de {len(diff['duplicates'])} doublon(s)...")
        for doc in diff["duplicates"]:
            try:
                client.document_delete(memory_id, doc["id"])
                stats["deleted"] += 1
                print(f"    ✅ {doc['filename']} ({doc['id'][:8]})")
            except Exception as e:
                stats["errors"] += 1
                print(f"    ❌ {doc['filename']}: {e}")

    # 2. Supprimer les obsolètes
    if diff["obsolete"]:
        print(f"\n  🗑️  Suppression de {len(diff['obsolete'])} document(s) obsolète(s)...")
        for doc in diff["obsolete"]:
            try:
                client.document_delete(memory_id, doc["id"])
                stats["deleted"] += 1
                print(f"    ✅ {doc['filename']}")
            except Exception as e:
                stats["errors"] += 1
                print(f"    ❌ {doc['filename']}: {e}")

    # 3. Ré-ingérer les fichiers modifiés
    if diff["modified"]:
        print(f"\n  🔄 Ré-ingestion de {len(diff['modified'])} fichier(s) modifié(s)...")
        for i, item in enumerate(diff["modified"], 1):
            local = item["local"]
            print(f"    [{i}/{len(diff['modified'])}] {local['filename']}...", end=" ", flush=True)
            try:
                t0 = time.time()
                _ingest_file(client, memory_id, local, force=True)
                elapsed = time.time() - t0
                stats["ingested"] += 1
                print(f"✅ ({elapsed:.1f}s)")
            except Exception as e:
                stats["errors"] += 1
                print(f"❌ {e}")

    # 4. Ingérer les nouveaux fichiers
    if diff["new"]:
        print(f"\n  📥 Ingestion de {len(diff['new'])} nouveau(x) fichier(s)...")
        for i, local in enumerate(diff["new"], 1):
            print(f"    [{i}/{len(diff['new'])}] {local['filename']}...", end=" ", flush=True)
            try:
                t0 = time.time()
                _ingest_file(client, memory_id, local, force=False)
                elapsed = time.time() - t0
                stats["ingested"] += 1
                print(f"✅ ({elapsed:.1f}s)")
            except Exception as e:
                stats["errors"] += 1
                print(f"❌ {e}")

    return stats


def _ingest_file(
    client: GraphMemoryClient, memory_id: str, local: dict, force: bool
):
    """Lit un fichier local et l'ingère dans Graph Memory."""
    with open(local["filepath"], "rb") as f:
        content = f.read()

    content_b64 = base64.b64encode(content).decode("ascii")

    client.memory_ingest(
        memory_id=memory_id,
        content_b64=content_b64,
        filename=local["filename"],
        source_path=local["source_path"],
        source_modified_at=local["mtime"],
        force=force,
    )


# ============================================================================
# POINT D'ENTRÉE
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Synchronise les fichiers locaux avec Graph Memory en production.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples:
  # Dry-run complet (toutes les mémoires)
  python3 scripts/refresh_graph_memory.py --url URL --token TOKEN

  # Synchroniser uniquement DOCS
  python3 scripts/refresh_graph_memory.py --url URL --token TOKEN --memory DOCS --apply

  # Variables d'environnement
  export MCP_URL=https://graph-mem.mcp.cloud-temple.app
  export MCP_TOKEN=your_token
  python3 scripts/refresh_graph_memory.py --apply

Mémoires configurées: DOCS, PRESALES, JURIDIQUE
        """,
    )
    parser.add_argument(
        "--url",
        default=os.environ.get("MCP_URL", ""),
        help="URL du serveur Graph Memory (ou env MCP_URL)",
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("MCP_TOKEN", ""),
        help="Token d'authentification (ou env MCP_TOKEN)",
    )
    parser.add_argument(
        "--memory", "-m",
        choices=list(MEMORY_SOURCES.keys()),
        help="Synchroniser une seule mémoire (défaut: toutes)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Exécuter les actions (sans ce flag = dry-run)",
    )
    parser.add_argument(
        "--skip-obsolete",
        action="store_true",
        help="Ne pas supprimer les documents obsolètes",
    )
    parser.add_argument(
        "--skip-duplicates",
        action="store_true",
        help="Ne pas supprimer les doublons",
    )
    parser.add_argument(
        "--base-dir",
        default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        help="Répertoire racine du projet (défaut: parent de scripts/)",
    )

    args = parser.parse_args()

    # Validation
    if not args.url:
        parser.error("--url requis (ou export MCP_URL=...)")
    if not args.token:
        parser.error("--token requis (ou export MCP_TOKEN=...)")

    # Header
    print_header("🔄 GRAPH MEMORY — REFRESH TOOL")
    print(f"  Serveur   : {args.url}")
    print(f"  Mode      : {'🚀 APPLY' if args.apply else '👀 DRY-RUN'}")
    print(f"  Base dir  : {args.base_dir}")
    print(f"  Mémoires  : {args.memory or 'TOUTES'}")
    print(f"  Date      : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Connexion
    print(f"\n  🔌 Connexion à {args.url}...")
    client = GraphMemoryClient(args.url, args.token)

    try:
        health = client.health()
        version = health.get("version", "?")
        print(f"  ✅ Serveur healthy (v{version})")
    except Exception as e:
        print(f"  ❌ Serveur injoignable: {e}")
        sys.exit(1)

    # Initialiser la session MCP
    client.initialize()

    # Lister les mémoires disponibles
    memories = client.memory_list()
    memory_ids = {m["id"] for m in memories}
    print(f"  📂 {len(memories)} mémoire(s) disponible(s): {', '.join(sorted(memory_ids))}")

    # Déterminer les mémoires à synchroniser
    targets = [args.memory] if args.memory else list(MEMORY_SOURCES.keys())

    global_stats = {"memories": 0, "deleted": 0, "ingested": 0, "errors": 0}

    for memory_id in targets:
        if memory_id not in memory_ids:
            print(f"\n  ⚠️  Mémoire '{memory_id}' non trouvée sur le serveur, ignorée.")
            continue

        config = MEMORY_SOURCES[memory_id]
        print_header(f"📂 {memory_id} — {config['description']}")

        # Scanner les fichiers locaux
        all_local_files = []
        for source in config["sources"]:
            files = scan_local_files(args.base_dir, source)
            print(f"  📁 {source['path']}: {len(files)} fichier(s)")
            all_local_files.extend(files)

        print(f"  📊 Total local: {len(all_local_files)} fichier(s)")

        # Récupérer les documents distants
        print(f"  🌐 Récupération des documents distants...")
        remote_docs = client.document_list(memory_id)
        print(f"  📊 Total distant: {len(remote_docs)} document(s)")

        # Comparer
        diff = compute_diff(all_local_files, remote_docs)

        # Appliquer les filtres
        if args.skip_obsolete:
            diff["obsolete"] = []
        if args.skip_duplicates:
            diff["duplicates"] = []

        # Afficher le rapport
        print_diff_report(memory_id, diff)

        # Exécuter si --apply
        n_actions = (len(diff["modified"]) + len(diff["new"])
                     + len(diff["obsolete"]) + len(diff["duplicates"]))

        if n_actions == 0:
            print(f"\n  🎉 {memory_id} est parfaitement synchronisé !")
        elif args.apply:
            print(f"\n  🚀 Exécution de {n_actions} action(s)...")
            stats = execute_sync(client, memory_id, diff)
            global_stats["deleted"] += stats["deleted"]
            global_stats["ingested"] += stats["ingested"]
            global_stats["errors"] += stats["errors"]
            global_stats["memories"] += 1
        else:
            est_time = n_actions * 45  # ~45s par action en moyenne
            print(f"\n  👀 DRY-RUN: {n_actions} action(s) à effectuer")
            print(f"     Temps estimé: ~{est_time // 60} min {est_time % 60}s")
            print(f"     Relancez avec --apply pour exécuter.")

    # Résumé global
    print_header("📊 RÉSUMÉ GLOBAL")
    if args.apply:
        print(f"  Mémoires synchronisées : {global_stats['memories']}")
        print(f"  Documents supprimés    : {global_stats['deleted']}")
        print(f"  Documents ingérés      : {global_stats['ingested']}")
        print(f"  Erreurs                : {global_stats['errors']}")
        if global_stats["errors"] > 0:
            print(f"\n  ⚠️  {global_stats['errors']} erreur(s) rencontrée(s).")
        else:
            print(f"\n  🎉 Synchronisation terminée sans erreur !")
    else:
        total_actions = sum(
            len(compute_diff(
                [f for s in MEMORY_SOURCES.get(m, {}).get("sources", [])
                 for f in scan_local_files(args.base_dir, s)],
                client.document_list(m) if m in memory_ids else []
            ).get("modified", [])) +
            len(compute_diff(
                [f for s in MEMORY_SOURCES.get(m, {}).get("sources", [])
                 for f in scan_local_files(args.base_dir, s)],
                client.document_list(m) if m in memory_ids else []
            ).get("new", []))
            for m in targets if m in memory_ids
        ) if False else 0  # Pas de re-calcul, juste le message
        print(f"  Mode DRY-RUN — aucune modification effectuée.")
        print(f"  Relancez avec --apply pour exécuter les actions.")


if __name__ == "__main__":
    main()
