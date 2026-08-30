"""Règles pures de classification des objets S3 liés aux mémoires."""


def collect_referenced_ontology_keys(memories, parse_key):
    """Retourne les clés d'ontologie légitimes et les fallbacks legacy.

    Les mémoires récentes référencent exactement leur objet via ``ontology_uri``.
    Pour une mémoire legacy sans URI, on protège uniquement son propre préfixe
    et le nom de son ontologie ; les autres objets ``_ontology_`` restent
    éligibles au nettoyage.
    """
    referenced_keys = set()
    legacy_patterns = []

    for memory in memories:
        ontology_uri = getattr(memory, "ontology_uri", None)
        if ontology_uri:
            try:
                referenced_keys.add(parse_key(ontology_uri))
                continue
            except ValueError:
                pass

        memory_id = getattr(memory, "id", "")
        ontology = getattr(memory, "ontology", "")
        if memory_id and ontology:
            legacy_patterns.append((f"{memory_id}/", f"__ontology_{ontology}.yaml"))

    return referenced_keys, legacy_patterns


def is_referenced_ontology_key(key, referenced_keys, legacy_patterns):
    """Indique si une clé d'ontologie est encore rattachée à une mémoire."""
    if "_ontology_" not in key:
        return False
    if key in referenced_keys:
        return True
    return any(
        key.startswith(prefix) and key.endswith(suffix)
        for prefix, suffix in legacy_patterns
    )
