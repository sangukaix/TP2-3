"""Merge evidence without collapsing different passages from the same document."""

from copy import deepcopy


def merge_evidence_sources(*groups: list[dict]) -> list[dict]:
    """Latest identical passage wins; parent citation IDs remain unchanged."""
    merged = {}
    for group in groups:
        for row in group:
            if row.get('source_id'):
                identity = (str(row['source_id']), str(row.get('chunk_id') or ''))
                merged[identity] = deepcopy(row)
    return list(merged.values())
