# -*- coding: utf-8 -*-
"""
Tests ingestion asynchrone (v3.1.0) : memory_ingest_async, ingest_job_status,
ingest_job_list, ingest_job_cancel, memory_ingest_batch_async.

Couvre : soumission immédiate, garde d'intégrité sha256, idempotence par
source_path (skipped / changed_skipped / replace), reprise par source_path,
annulation, batch agrégé, et cohérence storage_check (aucun orphelin).
"""

import asyncio
import base64
import hashlib

from . import (MCPClient, MEMORY_A, MEMORY_B,
               assert_ok, assert_error, assert_field, ok, fail, skip, phase_header)


def _doc(content: str) -> tuple[str, str]:
    """Retourne (content_base64, sha256_hex) pour un texte donné."""
    raw = content.encode("utf-8")
    return base64.b64encode(raw).decode("ascii"), hashlib.sha256(raw).hexdigest()


async def _wait_terminal(client: MCPClient, job_id: str, timeout_s: int = 180) -> dict:
    """Poll ingest_job_status jusqu'à un statut terminal (ou timeout)."""
    terminal = {"succeeded", "failed", "cancelled", "skipped", "changed_skipped"}
    waited = 0
    last = {}
    while waited < timeout_s:
        last = await client.call_tool("ingest_job_status", {"job_id": job_id})
        if last.get("status") in terminal or last.get("status") == "not_found":
            return last
        await asyncio.sleep(3)
        waited += 3
    return last


async def run(admin: MCPClient, client_rw: MCPClient, client_ro: MCPClient, **ctx):
    """Phase Ingestion asynchrone."""
    phase_header(8, "Ingestion asynchrone — jobs idempotents & observables", "⚡")

    SOURCE_PATH = "recette/async/doc-async.md"
    cb_v1, sha_v1 = _doc("Cloud Temple est un cloud souverain. SecNumCloud, HDS, ISO 27001.")
    cb_v2, sha_v2 = _doc("Cloud Temple propose IaaS, PaaS, SaaS et du SOC managé. Version 2 modifiée.")

    # 8.1 — Soumission asynchrone (client_rw, MEMORY_A) → réponse immédiate
    print("\n  📋 8.1 — memory_ingest_async (réponse immédiate)")
    result = await client_rw.call_tool("memory_ingest_async", {
        "memory_id": MEMORY_A, "content_base64": cb_v1, "filename": "doc-async.md",
        "source_path": SOURCE_PATH, "sha256": sha_v1,
    })
    job_id = result.get("job_id")
    if result.get("status") in ("queued", "running") and job_id:
        ok("Soumission async acceptée", f"status={result['status']}, job={job_id}")
    else:
        fail("Soumission async", f"status={result.get('status')}, msg={result.get('message')}")

    # 8.2 — Garde d'intégrité : sha256 invalide → error
    print("\n  📋 8.2 — Garde d'intégrité sha256 (checksum faux)")
    bad = await client_rw.call_tool("memory_ingest_async", {
        "memory_id": MEMORY_A, "content_base64": cb_v1, "filename": "doc-async.md",
        "source_path": "recette/async/bad.md", "sha256": "deadbeef",
    })
    assert_error(bad, "sha256 invalide rejeté", "checksum")

    # 8.3 — source_path obligatoire
    print("\n  📋 8.3 — source_path obligatoire")
    nosp = await client_rw.call_tool("memory_ingest_async", {
        "memory_id": MEMORY_A, "content_base64": cb_v1, "filename": "x.md",
        "source_path": "", "sha256": sha_v1,
    })
    assert_error(nosp, "source_path obligatoire", "source_path")

    # 8.4 — Isolation : client_ro refusé (write)
    print("\n  📋 8.4 — memory_ingest_async refusé (client_ro)")
    ro = await client_ro.call_tool("memory_ingest_async", {
        "memory_id": MEMORY_B, "content_base64": cb_v1, "filename": "x.md",
        "source_path": "recette/async/ro.md", "sha256": sha_v1,
    })
    assert_error(ro, "async refusé (read-only)")

    # 8.5 — Attendre la fin du job 8.1 → succeeded
    if job_id:
        print("\n  📋 8.5 — ingest_job_status jusqu'à succeeded")
        final = await _wait_terminal(client_rw, job_id)
        if final.get("status") == "succeeded":
            ok("Job terminé", f"E:{final.get('created_entities')} R:{final.get('created_relations')}")
            assert_field(final, "document_id", "  → document_id")
            if final.get("progress_percent") == 100:
                ok("  → progress_percent=100")
        else:
            fail("Job async", f"status final={final.get('status')}, err={final.get('error')}")
    else:
        skip("8.5 — suivi job", "pas de job_id")

    # 8.6 — Idempotence : même source_path + même sha → skipped immédiat
    print("\n  📋 8.6 — Réingestion identique → skipped")
    again = await client_rw.call_tool("memory_ingest_async", {
        "memory_id": MEMORY_A, "content_base64": cb_v1, "filename": "doc-async.md",
        "source_path": SOURCE_PATH, "sha256": sha_v1,
    })
    if again.get("status") == "skipped":
        ok("Idempotence skipped (source_path + checksum identiques)")
    else:
        fail("Idempotence skipped", f"Attendu skipped, obtenu {again.get('status')}")

    # 8.7 — Checksum différent + replace_existing=false → changed_skipped
    print("\n  📋 8.7 — Checksum différent sans replace → changed_skipped")
    changed = await client_rw.call_tool("memory_ingest_async", {
        "memory_id": MEMORY_A, "content_base64": cb_v2, "filename": "doc-async.md",
        "source_path": SOURCE_PATH, "sha256": sha_v2, "replace_existing": False,
    })
    if changed.get("status") == "changed_skipped":
        ok("Remplacement explicite requis (changed_skipped)")
    else:
        fail("changed_skipped", f"Attendu changed_skipped, obtenu {changed.get('status')}")

    # 8.8 — Checksum différent + replace_existing=true → remplacement (pas de doublon)
    print("\n  📋 8.8 — Remplacement explicite (replace_existing=true)")
    repl = await client_rw.call_tool("memory_ingest_async", {
        "memory_id": MEMORY_A, "content_base64": cb_v2, "filename": "doc-async.md",
        "source_path": SOURCE_PATH, "sha256": sha_v2, "replace_existing": True,
    })
    repl_job = repl.get("job_id")
    if repl_job:
        final = await _wait_terminal(client_rw, repl_job)
        assert_ok({"status": "ok"} if final.get("status") == "succeeded" else final,
                  "Remplacement terminé")
    else:
        fail("Remplacement", f"status={repl.get('status')}")

    # 8.9 — Reprise par source_path (ingest_job_list)
    print("\n  📋 8.9 — ingest_job_list filtré par source_path (reprise)")
    listed = await client_rw.call_tool("ingest_job_list", {
        "memory_id": MEMORY_A, "source_path": SOURCE_PATH,
    })
    if listed.get("status") == "ok" and listed.get("count", 0) >= 1:
        ok("Reprise par source_path", f"{listed['count']} job(s)")
    else:
        fail("ingest_job_list source_path", f"count={listed.get('count')}")

    # 8.10 — Pas de doublon : un seul document pour ce source_path
    print("\n  📋 8.10 — document_list : source_path unique + ingestion_status")
    docs = await client_rw.call_tool("document_list", {"memory_id": MEMORY_A})
    matching = [d for d in docs.get("documents", []) if d.get("source_path") == SOURCE_PATH]
    if len(matching) == 1:
        ok("Pas de doublon (1 document pour ce source_path)")
        d = matching[0]
        if d.get("ingestion_status") == "succeeded":
            ok("  → ingestion_status=succeeded")
        else:
            fail("  → ingestion_status", f"obtenu {d.get('ingestion_status')}")
        if d.get("sha256") == sha_v2:
            ok("  → sha256 = version remplacée")
        else:
            fail("  → sha256", "checksum non mis à jour après remplacement")
        if d.get("last_ingest_job_id"):
            ok(f"  → last_ingest_job_id présent")
    else:
        fail("Doublon source_path", f"{len(matching)} documents pour ce source_path")

    # 8.11 — Annulation best-effort
    print("\n  📋 8.11 — ingest_job_cancel (best-effort)")
    cb_c, sha_c = _doc("Document à annuler. " * 50)
    sub = await client_rw.call_tool("memory_ingest_async", {
        "memory_id": MEMORY_A, "content_base64": cb_c, "filename": "to-cancel.md",
        "source_path": "recette/async/to-cancel.md", "sha256": sha_c,
    })
    cjob = sub.get("job_id")
    if cjob:
        cancel = await client_rw.call_tool("ingest_job_cancel", {"job_id": cjob})
        if cancel.get("status") in ("cancelled", "cancelling", "noop"):
            ok("Annulation acceptée", cancel.get("status"))
            # Laisser le pipeline finir l'annulation puis vérifier l'absence d'orphelin
            await _wait_terminal(client_rw, cjob, timeout_s=120)
        else:
            fail("Annulation", f"status={cancel.get('status')}")
    else:
        skip("8.11 — annulation", f"soumission non mise en file ({sub.get('status')})")

    # 8.12 — Batch asynchrone
    print("\n  📋 8.12 — memory_ingest_batch_async (lot)")
    cb_b1, sha_b1 = _doc("Batch doc 1 — réversibilité contractuelle.")
    cb_b2, sha_b2 = _doc("Batch doc 2 — plan de continuité d'activité.")
    batch = await client_rw.call_tool("memory_ingest_batch_async", {
        "memory_id": MEMORY_A,
        "documents": [
            {"content_base64": cb_b1, "filename": "b1.md", "source_path": "recette/async/b1.md", "sha256": sha_b1},
            {"content_base64": cb_b2, "filename": "b2.md", "source_path": "recette/async/b2.md", "sha256": sha_b2},
        ],
    })
    if batch.get("status") == "ok" and batch.get("total") == 2 and batch.get("batch_id"):
        ok("Lot soumis", f"batch_id={batch['batch_id']}, counts={batch.get('counts')}")
        # Attendre la fin des jobs du batch
        for item in batch.get("items", []):
            if item.get("job_id"):
                await _wait_terminal(client_rw, item["job_id"])
        bl = await client_rw.call_tool("ingest_job_list", {"memory_id": MEMORY_A, "batch_id": batch["batch_id"]})
        if bl.get("count", 0) == 2:
            ok("  → ingest_job_list par batch_id (2 jobs)")
    else:
        fail("Batch async", f"status={batch.get('status')}, total={batch.get('total')}")

    # 8.13 — storage_check étendu : 0 orphelin S3 ET 0 incohérence (Qdrant/source_path/partiels)
    print("\n  📋 8.13 — storage_check (S3 + cohérence Qdrant/source_path)")
    check = await admin.call_tool("storage_check", {"memory_id": MEMORY_A})
    if check.get("status") == "ok":
        n_orphans = check.get("s3_orphans", {}).get("count", 0)
        if not n_orphans:
            ok("storage_check : 0 orphelin S3")
        else:
            fail("storage_check orphelins S3", f"{n_orphans} orphelin(s)")
        cons = check.get("consistency", {})
        if cons.get("issues") == 0:
            ok("storage_check : 0 incohérence (Qdrant/doublons/partiels)")
        else:
            fail("storage_check cohérence", f"{cons.get('issues')} incohérence(s): {cons}")
    else:
        skip("8.13 — storage_check", f"status={check.get('status')}")

    # 8.14 — Panne : document sans texte exploitable → échec sans orphelin
    print("\n  📋 8.14 — Ingestion en échec (doc vide) → pas d'orphelin")
    cb_empty, sha_empty = _doc("")  # contenu vide → extraction texte impossible
    subf = await client_rw.call_tool("memory_ingest_async", {
        "memory_id": MEMORY_A, "content_base64": cb_empty, "filename": "empty.md",
        "source_path": "recette/async/empty.md", "sha256": sha_empty,
    })
    fjob = subf.get("job_id")
    if fjob:
        final = await _wait_terminal(client_rw, fjob)
        if final.get("status") == "failed":
            ok("Job en échec correctement signalé", final.get("error", "")[:60])
        else:
            fail("Job échec attendu", f"status={final.get('status')}")
        # Le storage_check doit rester propre (rollback de l'objet S3 partiel)
        check2 = await admin.call_tool("storage_check", {"memory_id": MEMORY_A})
        cons2 = check2.get("consistency", {})
        if check2.get("s3_orphans", {}).get("count", 0) == 0 and cons2.get("issues", 0) == 0:
            ok("  → aucun orphelin/incohérence après l'échec")
        else:
            fail("  → orphelin après échec", f"orphans={check2.get('s3_orphans', {}).get('count')}, cons={cons2.get('issues')}")
    else:
        skip("8.14 — panne", f"soumission inattendue ({subf.get('status')})")
