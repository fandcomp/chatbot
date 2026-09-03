"""Duplicated by design (matching ADR-016's worker/api hand-sync pattern) —
mirrors workers/document_worker/app/interpretation/structural_path.py and
pipeline.py's `_order_region_nodes`, kept in sync by hand if that algorithm
changes. Used only by the admin node-correction endpoint below to recompute
a region's structural_path_json/structural_path_text after an admin edits a
node's type/parent/label/title (addendum §27).
"""

import uuid
from collections import defaultdict
from typing import Any

from app.parsing.models import DocumentNode

_LEVEL_RANK: dict[str, int] = {
    "CHAPTER": 0,
    "PART": 0,
    "ARTICLE": 1,
    "NUMBERED_SECTION": 1,
    "DECISION_ITEM": 1,
    "SECTION": 1,
    "SUBSECTION": 2,
    "CLAUSE": 2,
    "NUMBERED_ITEM": 2,
    "LETTER_ITEM": 3,
    "ROMAN_ITEM": 4,
    "NESTED_ITEM": 5,
}


def _node_type_value(node: DocumentNode) -> str:
    return node.node_type.value if hasattr(node.node_type, "value") else node.node_type


def _label_for(node: DocumentNode) -> str:
    if node.label:
        return node.label
    return node.title or (node.text[:60] if node.text else _node_type_value(node))


def render_structural_path_text(path_json: list[dict[str, Any]]) -> str:
    return " > ".join(entry["label"] for entry in path_json if entry.get("label"))


def order_region_nodes(nodes: list[DocumentNode]) -> list[DocumentNode]:
    node_ids = {node.id for node in nodes}
    children_by_parent: dict[uuid.UUID | None, list[DocumentNode]] = defaultdict(list)
    for node in nodes:
        parent_key = node.parent_id if node.parent_id in node_ids else None
        children_by_parent[parent_key].append(node)
    for children in children_by_parent.values():
        children.sort(key=lambda n: n.sequence_number)

    ordered: list[DocumentNode] = []

    def walk(parent_key: uuid.UUID | None) -> None:
        for child in children_by_parent.get(parent_key, []):
            ordered.append(child)
            walk(child.id)

    walk(None)
    return ordered


def rebuild_region_structural_paths(nodes_ordered: list[DocumentNode]) -> None:
    stack: list[tuple[int, dict[str, Any]]] = []
    for node in nodes_ordered:
        node_type_value = _node_type_value(node)
        entry = {"node_type": node_type_value, "label": _label_for(node), "title": node.title}
        rank = _LEVEL_RANK.get(node_type_value)
        if rank is not None:
            while stack and stack[-1][0] >= rank:
                stack.pop()
            path = [e for _, e in stack] + [entry]
            stack.append((rank, entry))
        else:
            path = [e for _, e in stack] + [entry]
        node.structural_path_json = path
        node.structural_depth = len(path)
        node.structural_path_text = render_structural_path_text(path)
