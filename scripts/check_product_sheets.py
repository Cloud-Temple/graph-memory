#!/usr/bin/env python3
"""Vérifie l'état des product_sheets dans la mémoire DOCS."""
import json
import subprocess
import sys
import os
import hashlib

def get_docs_list():
    """Récupère la liste des documents DOCS via CLI."""
    env = os.environ.copy()
    result = subprocess.run(
        ["python3", "scripts/mcp_cli.py", "document", "list", "DOCS", "--json"],
        capture_output=True, text=True, env=env
    )
    # Le JSON peut contenir des descriptions avec des caractères problématiques
    # On nettoie les caractères de contrôle avant parsing
    stdout = result.stdout
    # Remplacer les vrais retours à la ligne dans les valeurs de chaîne
    import re
    # Trouver le début du JSON
    json_start = stdout.find('{')
    if json_start == -1:
        json_start = stdout.find('[')
    if json_start == -1:
        print(f"ERREUR: Pas de JSON trouvé dans la sortie CLI")
        print(f"stdout[:500]: {stdout[:500]}")
        sys.exit(1)
    stdout = stdout[json_start:]
    
    try:
        data = json.loads(stdout, strict=False)
    except json.JSONDecodeError:
        # Fallback: nettoyer les sauts de ligne dans les strings JSON
        cleaned = re.sub(r'(?<=": ")([^"]*)\n([^"]*")', r'\1 \2', stdout)
        data = json.loads(cleaned, strict=False)
    
    return data.get("documents", data)

def get_local_files():
    """Liste les fichiers .md dans product_sheets (hors exclusions)."""
    excludes = ["01_Templates", "memory-bank", "README.md"]
    files = []
    for root, dirs, filenames in os.walk("product_sheets"):
        # Skip excluded dirs
        dirs[:] = [d for d in dirs if not any(ex in d for ex in excludes) and d != ".git"]
        for fn in filenames:
            if not fn.endswith(".md"):
                continue
            if fn == "README.md":
                continue
            path = os.path.join(root, fn)
            rel_path = os.path.relpath(path, "product_sheets")
            # Compute SHA-256
            with open(path, "rb") as f:
                h = hashlib.sha256(f.read()).hexdigest()
            size = os.path.getsize(path)
            files.append({"path": rel_path, "filename": fn, "hash": h, "size": size})
    return files

def main():
    print("=" * 70)
    print("VÉRIFICATION PRODUCT SHEETS DANS DOCS (PRODUCTION)")
    print("=" * 70)
    
    # Get remote docs
    docs = get_docs_list()
    print(f"\n📊 Total documents dans DOCS : {len(docs)}")
    
    # Filter product_sheets by source_path categories
    ps_categories = [
        "Coming_Soon", "AI &", "Compute/", "Containers", "Datacenter/",
        "Management", "Marketplace/", "Networking/", "Security", "Storage/"
    ]
    
    ps_docs = {}
    other_docs = []
    for d in docs:
        sp = d.get("source_path", "") or ""
        if any(cat in sp for cat in ps_categories):
            ps_docs[sp] = d
        else:
            other_docs.append(d)
    
    print(f"📄 Product Sheets ingérées : {len(ps_docs)}")
    print(f"📚 Autres documents : {len(other_docs)}")
    
    # Get local files
    local_files = get_local_files()
    local_by_path = {f["path"]: f for f in local_files}
    
    print(f"💾 Fichiers locaux product_sheets : {len(local_files)}")
    
    # Check what's ingested
    print("\n" + "=" * 70)
    print("📋 PRODUCT SHEETS INGÉRÉES")
    print("=" * 70)
    for sp in sorted(ps_docs.keys()):
        d = ps_docs[sp]
        dt = d.get("ingested_at", "")[:10]
        h = d.get("hash", "")[:8]
        local = local_by_path.get(sp)
        status = ""
        if local:
            if local["hash"] == d.get("hash", ""):
                status = "✅ OK"
            else:
                status = "⚠️  HASH DIFFÉRENT (fichier modifié localement)"
        else:
            status = "❌ ABSENT du repo local"
        print(f"  {dt} | {h} | {status} | {sp}")
    
    # Check what's missing from ingestion
    print("\n" + "=" * 70)
    print("🔍 FICHIERS LOCAUX NON INGÉRÉS")
    print("=" * 70)
    missing = []
    for path, f in sorted(local_by_path.items()):
        if path not in ps_docs:
            missing.append(f)
            print(f"  ❌ {path} ({f['size']} bytes)")
    
    if not missing:
        print("  ✅ Tous les fichiers locaux sont ingérés !")
    
    # Check for obsolete docs (ingested but not in local)
    print("\n" + "=" * 70)
    print("🗑️  DOCUMENTS OBSOLÈTES (ingérés mais absents du repo)")
    print("=" * 70)
    obsolete = []
    for sp, d in sorted(ps_docs.items()):
        if sp not in local_by_path:
            obsolete.append(d)
            print(f"  ⚠️  {sp} (ingéré {d.get('ingested_at', '')[:10]})")
    
    if not obsolete:
        print("  ✅ Aucun document obsolète !")
    
    # Summary
    print("\n" + "=" * 70)
    print("📊 RÉSUMÉ")
    print("=" * 70)
    
    ok_count = sum(1 for sp in ps_docs if sp in local_by_path and local_by_path[sp]["hash"] == ps_docs[sp].get("hash", ""))
    modified_count = sum(1 for sp in ps_docs if sp in local_by_path and local_by_path[sp]["hash"] != ps_docs[sp].get("hash", ""))
    
    print(f"  ✅ Synchronisés (hash OK)  : {ok_count}")
    print(f"  ⚠️  Hash différent          : {modified_count}")
    print(f"  ❌ Non ingérés             : {len(missing)}")
    print(f"  🗑️  Obsolètes              : {len(obsolete)}")
    
    if len(missing) == 0 and len(obsolete) == 0 and modified_count == 0:
        print("\n🎉 TOUT EST PARFAITEMENT SYNCHRONISÉ !")
    elif len(missing) == 0 and len(obsolete) == 0:
        print(f"\n⚠️  {modified_count} fichier(s) modifié(s) localement non ré-ingéré(s)")
    else:
        print(f"\n⚠️  Des actions sont nécessaires.")

if __name__ == "__main__":
    main()
