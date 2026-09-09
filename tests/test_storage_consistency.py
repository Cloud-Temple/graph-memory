from types import SimpleNamespace

from src.mcp_memory.storage_consistency import (
    collect_referenced_ontology_keys,
    filter_objects_for_memory,
    is_referenced_ontology_key,
)


def _parse_key(value: str) -> str:
    if value.startswith("s3://"):
        parts = value[5:].split("/", 1)
        if len(parts) != 2:
            raise ValueError(value)
        return parts[1]
    return value


def test_referenced_ontology_is_protected_but_duplicate_is_orphan():
    memory = SimpleNamespace(
        id="active-memory",
        ontology="software-development",
        ontology_uri=(
            "s3://bucket/active-memory/documents/aaaa1111_"
            "_ontology_software-development.yaml"
        ),
    )
    referenced, legacy = collect_referenced_ontology_keys([memory], _parse_key)

    assert is_referenced_ontology_key(
        "active-memory/documents/aaaa1111__ontology_software-development.yaml",
        referenced,
        legacy,
    )
    assert not is_referenced_ontology_key(
        "active-memory/documents/bbbb2222__ontology_software-development.yaml",
        referenced,
        legacy,
    )


def test_deleted_memory_ontology_is_orphan():
    referenced, legacy = collect_referenced_ontology_keys([], _parse_key)

    assert not is_referenced_ontology_key(
        "deleted-memory/documents/aaaa1111__ontology_general.yaml",
        referenced,
        legacy,
    )


def test_legacy_memory_without_uri_protects_only_its_expected_ontology():
    memory = SimpleNamespace(
        id="legacy-memory",
        ontology="legal",
        ontology_uri=None,
    )
    referenced, legacy = collect_referenced_ontology_keys([memory], _parse_key)

    assert is_referenced_ontology_key(
        "legacy-memory/documents/aaaa1111__ontology_legal.yaml",
        referenced,
        legacy,
    )
    assert not is_referenced_ontology_key(
        "deleted-memory/documents/aaaa1111__ontology_legal.yaml",
        referenced,
        legacy,
    )


def test_scoped_storage_check_hides_other_memory_keys():
    objects = [
        {"key": "allowed/documents/a.txt"},
        {"key": "other/documents/_ontology_secret.yaml"},
        {"key": "_backups/allowed/archive.tar.gz"},
    ]

    assert filter_objects_for_memory(objects, "allowed") == [objects[0]]
    assert filter_objects_for_memory(objects) == objects
