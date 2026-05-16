#!/bin/bash
# Ré-ingestion des 5 fichiers product_sheets modifiés avec --force
# Usage: MCP_URL=... MCP_TOKEN=... bash scripts/reingest_modified.sh

set -e

CLI="python3 scripts/mcp_cli.py document ingest DOCS"

echo "=== Ré-ingestion des fichiers modifiés (--force) ==="
echo ""

# Les 4 fichiers restants (le 1er est déjà en cours)
FILES=(
  "product_sheets/Containers & Orchestration/Managed-Kubernetes-product-sheet.md"
  "product_sheets/Compute/Bare-Metal-product-sheet.md"
  "product_sheets/Compute/IaaS-OpenSource-product-sheet.md"
  "product_sheets/Compute/IaaS-VMware-product-sheet.md"
)

for f in "${FILES[@]}"; do
  echo ""
  echo ">>> $f"
  $CLI "$f" --force
  echo "<<< Done: $f"
done

echo ""
echo "=== Terminé : 4 fichiers ré-ingérés ==="
