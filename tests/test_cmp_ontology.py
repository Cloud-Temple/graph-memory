"""Contrat de l'ontologie Cloud Management Platform (#28)."""

from pathlib import Path

import yaml


def test_cmp_ontology_contract(monkeypatch):
    for name in ("S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY", "LLMAAS_API_KEY", "NEO4J_PASSWORD"):
        monkeypatch.setenv(name, "cmp-ontology-test-unused")

    from src.mcp_memory.core.ontology import OntologyManager

    root = Path(__file__).parents[1]
    path = root / "ONTOLOGIES" / "cloud-management-platform.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    ontology = OntologyManager(str(path.parent)).get_ontology_or_error("cloud-management-platform")

    entity_types = {item.name for item in ontology.entity_types}
    relation_types = {item.name for item in ontology.relation_types}
    assert ontology.version == "1.0.0"
    assert len(entity_types) == 11
    assert len(relation_types) == 16
    assert {
        "Microservice", "ManagedResource", "Product", "PlatformTool",
        "ToolCapability", "TechnicalConstraint",
    } <= entity_types
    assert {"REALIZES", "BACKED_BY", "IMPOSES", "CONSTRAINS"} <= relation_types
    assert not ({"Datacenter", "Region", "Zone", "Environment", "Host"} & entity_types)

    prompt = ontology.build_prompt("Document de validation")
    assert "Ne cree jamais de type \"Other\"" in prompt
    assert "N'extrais AUCUN element de deploiement" in prompt
    assert "PlatformTool -> IMPOSES -> TechnicalConstraint" in prompt
    assert "TechnicalConstraint est un TYPE D'ENTITE" in prompt
    assert "Vendor -> PROVIDES -> PlatformTool" in prompt
    assert "Une source ou une cible vide" in prompt

    for example in raw["examples"]:
        entities = example["output"]["entities"]
        relations = example["output"]["relations"]
        names = {entity["name"] for entity in entities}
        assert len(names) == len(entities)
        assert all(entity["type"] in entity_types for entity in entities)
        assert all(entity["type"] != "Other" for entity in entities)
        assert all(relation["type"] in relation_types for relation in relations)
        assert all(relation["from"] in names and relation["to"] in names for relation in relations)

        constraints = {entity["name"] for entity in entities if entity["type"] == "TechnicalConstraint"}
        for constraint in constraints:
            assert any(rel["type"] == "IMPOSES" and rel["to"] == constraint for rel in relations)
            assert any(rel["type"] == "CONSTRAINS" and rel["from"] == constraint for rel in relations)

    compute_backends = {
        relation["to"]
        for relation in raw["examples"][0]["output"]["relations"]
        if relation["type"] == "BACKED_BY"
    }
    assert compute_backends == {"VMware vSphere", "OpenIaaS"}
