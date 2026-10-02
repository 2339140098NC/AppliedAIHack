"""Group facets that share a key so disagreements sit side by side."""

import uuid

from caseboard.domain.enums import GroupStatus
from caseboard.domain.models import ComparisonGroup, Facet, GroupEntry
from caseboard.extract.compare import compare_value


def build_groups(facets: list[Facet]) -> list[ComparisonGroup]:
    buckets: dict[str, list[Facet]] = {}
    for facet in facets:
        buckets.setdefault(facet.facet_key, []).append(facet)
    groups = []
    for key in sorted(buckets):
        entries = [
            GroupEntry(
                facet_id=facet.id,
                value=facet.value,
                authored_by=facet.authored_by,
                sensitivity=facet.sensitivity,
                evidence=facet.evidence,
            )
            for facet in buckets[key]
        ]
        groups.append(
            ComparisonGroup(
                id=str(uuid.uuid4()),
                facet_key=key,
                status=status_for([entry.value for entry in entries], key=key),
                entries=entries,
            )
        )
    return groups


def status_for(values: list[str | None], *, key: str = "") -> GroupStatus:
    nonempty = {compare_value(key, value) for value in values if value and str(value).strip()}
    blanks = any(value is None or not str(value).strip() for value in values)
    if len(nonempty) > 1:
        return GroupStatus.conflict
    if blanks:
        return GroupStatus.incomplete
    return GroupStatus.consistent
