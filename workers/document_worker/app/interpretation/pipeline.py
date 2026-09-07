"""Orchestrates M4's per-region grammar detection -> interpretation ->
path/profile computation. Consumes M3's already-persisted region/node rows
(read back from Postgres by the caller — see tasks.py's
`_interpret_structure_async`) rather than in-memory objects from
`parse_document`, keeping the two Celery tasks independently
invokable/testable at the cost of one extra DB round-trip per document.
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from app.interpretation.confidence import apply_confidence_adjustments
from app.interpretation.document_profile import build_structure_profile
from app.interpretation.models import InterpretedNode
from app.interpretation.pattern_detector import detect_grammar, split_into_grammar_segments
from app.interpretation.specialized_interpreter import interpret_region
from app.interpretation.structural_path import rebuild_structural_paths


@dataclass
class InterpretationResult:
    nodes: list[InterpretedNode]
    profile: dict[str, bool]
    aggregate_confidence: float


def _order_region_nodes(nodes: list[InterpretedNode]) -> list[InterpretedNode]:
    """Pre-order DFS by parent_id (children sorted by sequence_number) —
    document reading order within one region, regardless of whether M3's
    Docling-derived tree nested every item correctly (see
    specialized_interpreter.py's module docstring).
    """
    node_ids = {node.id for node in nodes}
    children_by_parent: dict[uuid.UUID | None, list[InterpretedNode]] = defaultdict(list)
    for node in nodes:
        parent_key = node.parent_id if node.parent_id in node_ids else None
        children_by_parent[parent_key].append(node)
    for children in children_by_parent.values():
        children.sort(key=lambda n: n.sequence_number)

    ordered: list[InterpretedNode] = []

    def walk(parent_key: uuid.UUID | None) -> None:
        for child in children_by_parent.get(parent_key, []):
            ordered.append(child)
            walk(child.id)

    walk(None)
    return ordered


def interpret_document(
    node_rows: list[dict[str, Any]], region_rows: list[dict[str, Any]]
) -> InterpretationResult:
    all_nodes = [InterpretedNode.from_row(row) for row in node_rows]

    nodes_by_region: dict[uuid.UUID, list[InterpretedNode]] = defaultdict(list)
    for node in all_nodes:
        nodes_by_region[node.region_id].append(node)

    for region_nodes in nodes_by_region.values():
        ordered = _order_region_nodes(region_nodes)
        # A decision preamble and its Pasal-based body routinely share one
        # region (see split_into_grammar_segments) — each segment gets its
        # own grammar so the body doesn't inherit the preamble's, or vice
        # versa. structural_path/confidence still run over the whole region
        # in original order, since those recover hierarchy/sequence across
        # the full node list regardless of which segment produced a node.
        for segment in split_into_grammar_segments(ordered):
            grammar = detect_grammar(segment)
            interpret_region(segment, grammar)
        rebuild_structural_paths(ordered)
        apply_confidence_adjustments(ordered)

    region_types = [row["region_type"] for row in region_rows]
    profile = build_structure_profile(all_nodes, region_types)
    # Minimum, not average: a single garbled node should force review rather
    # than being swept under a high overall average (spec §102: correctness
    # over feature speed). default=0.0 (not 1.0): a document with zero nodes
    # must never be silently auto-approved for lack of anything to score.
    aggregate_confidence = min((node.confidence for node in all_nodes), default=0.0)

    return InterpretationResult(
        nodes=all_nodes, profile=profile, aggregate_confidence=aggregate_confidence
    )
