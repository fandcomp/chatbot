"""GenericHierarchyBuilder's chunking counterpart (addendum §37/§19, ADR-006).

Priority: legal structure > semantic structure > token limit (spec §22).
Never hard-codes Article->Clause->Letter (addendum §20's principle, carried
over from node hierarchy into chunk hierarchy too) — the recursion below
only ever asks "does this node have structural children to recurse into?",
never branches on a specific node_type chain.
"""

import re
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from app.chunking.models import ChunkSpec
from app.chunking.text_estimator import estimate_tokens
from app.core.config import settings

# addendum §19's chunk roots, minus types with no concrete DocumentNodeType
# (PROCEDURE_SECTION/APPENDIX_SECTION map onto NUMBERED_SECTION/APPENDIX —
# M4's procedural interpreter tags semantic_role, it doesn't introduce a
# distinct node_type).
_SPECIFIC_ROOT_TYPES = {"ARTICLE", "DECISION_ITEM", "NUMBERED_SECTION", "APPENDIX"}
_FALLBACK_ROOT_TYPES = {"SECTION", "SUBSECTION"}
_TABLE_TYPE = "TABLE"

_SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?])\s+")


@dataclass
class ChunkableNode:
    id: uuid.UUID
    parent_id: uuid.UUID | None
    node_type: str
    text: str | None
    title: str | None
    sequence_number: int
    page_start: int
    page_end: int
    structural_path_json: list[dict[str, Any]]
    structural_path_text: str | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "ChunkableNode":
        return cls(
            id=row["id"],
            parent_id=row["parent_id"],
            node_type=row["node_type"],
            text=row["text"],
            title=row["title"],
            sequence_number=row["sequence_number"],
            page_start=row["page_start"],
            page_end=row["page_end"],
            structural_path_json=list(row["structural_path_json"] or []),
            structural_path_text=row.get("structural_path_text"),
        )


@dataclass
class ChunkDraft:
    anchor_node: ChunkableNode
    text: str
    children: list["ChunkDraft"] = field(default_factory=list)


def _children_by_parent(
    nodes: list[ChunkableNode],
) -> dict[uuid.UUID | None, list[ChunkableNode]]:
    node_ids = {node.id for node in nodes}
    by_parent: dict[uuid.UUID | None, list[ChunkableNode]] = defaultdict(list)
    for node in nodes:
        parent_key = node.parent_id if node.parent_id in node_ids else None
        by_parent[parent_key].append(node)
    for children in by_parent.values():
        children.sort(key=lambda n: n.sequence_number)
    return by_parent


def _subtree_has_text(
    node: ChunkableNode, by_parent: dict[uuid.UUID | None, list[ChunkableNode]]
) -> bool:
    if node.text or node.title:
        return True
    return any(_subtree_has_text(child, by_parent) for child in by_parent.get(node.id, []))


def find_chunk_roots(nodes: list[ChunkableNode]) -> list[ChunkableNode]:
    """Document-order list of chunk roots. TABLE is always its own root,
    even nested inside another root (spec §25: tables are first-class,
    never flattened into surrounding prose). Otherwise the outermost
    specific/fallback root type wins; a node with no root-type descendant
    and no active root above it falls back to claiming itself, as long as
    it actually carries content — this is what guarantees every node ends
    up covered by exactly one chunk lineage.
    """
    by_parent = _children_by_parent(nodes)
    roots: list[ChunkableNode] = []

    def walk(node: ChunkableNode, inside_root: bool) -> bool:
        if node.node_type == _TABLE_TYPE:
            roots.append(node)
            return True

        is_specific = node.node_type in _SPECIFIC_ROOT_TYPES
        is_fallback = node.node_type in _FALLBACK_ROOT_TYPES
        becomes_root = not inside_root and (
            is_specific or (is_fallback and _subtree_has_text(node, by_parent))
        )
        if becomes_root:
            roots.append(node)

        next_inside_root = inside_root or becomes_root
        child_claimed = False
        for child in by_parent.get(node.id, []):
            if walk(child, next_inside_root):
                child_claimed = True

        if becomes_root or child_claimed:
            return True
        if inside_root:
            # An ancestor already owns this subtree's chunking — this
            # node's text is absorbed into that ancestor's concatenation.
            return False
        if node.text or node.title:
            roots.append(node)
            return True
        return False

    for top_level in by_parent.get(None, []):
        walk(top_level, inside_root=False)

    return roots


def _collect_descendant_text_nodes(
    node: ChunkableNode, by_parent: dict[uuid.UUID | None, list[ChunkableNode]]
) -> list[ChunkableNode]:
    """This node + descendants in document order, excluding nested TABLE
    subtrees — those are always chunked separately (see find_chunk_roots).
    """
    collected = [node] if node.text else []
    for child in by_parent.get(node.id, []):
        if child.node_type == _TABLE_TYPE:
            continue
        collected.extend(_collect_descendant_text_nodes(child, by_parent))
    return collected


def _structural_children(
    node: ChunkableNode, by_parent: dict[uuid.UUID | None, list[ChunkableNode]]
) -> list[ChunkableNode]:
    return [child for child in by_parent.get(node.id, []) if child.node_type != _TABLE_TYPE]


def _split_by_token_budget(text: str, max_tokens: int) -> list[str]:
    """Paragraph-boundary greedy packing, falling back to sentence
    boundaries for a single oversized paragraph. A pathological single
    "sentence" with no punctuation at all (and thus no further boundary to
    split on) is left as one oversized piece rather than crashing — a
    documented, non-blocking limitation.
    """
    paragraphs = [p for p in text.split("\n") if p.strip()]
    pieces: list[str] = []
    current: list[str] = []
    current_tokens = 0

    def flush() -> None:
        if current:
            pieces.append("\n".join(current))
            current.clear()

    for paragraph in paragraphs:
        paragraph_tokens = estimate_tokens(paragraph)
        if paragraph_tokens > max_tokens:
            flush()
            current_tokens = 0
            for sentence in _SENTENCE_BOUNDARY_RE.split(paragraph):
                if not sentence.strip():
                    continue
                sentence_tokens = estimate_tokens(sentence)
                if current_tokens + sentence_tokens > max_tokens and current:
                    flush()
                    current_tokens = 0
                current.append(sentence)
                current_tokens += sentence_tokens
            flush()
            current_tokens = 0
            continue

        if current_tokens + paragraph_tokens > max_tokens and current:
            flush()
            current_tokens = 0
        current.append(paragraph)
        current_tokens += paragraph_tokens

    flush()
    return pieces or [text]


def _render_table_text(
    table_node: ChunkableNode, by_parent: dict[uuid.UUID | None, list[ChunkableNode]]
) -> str:
    lines: list[str] = []
    if table_node.text:
        lines.append(table_node.text)
    rows = by_parent.get(table_node.id, [])
    for row in rows:
        cells = by_parent.get(row.id, [])
        lines.append(" | ".join(cell.text or "" for cell in cells))
    return "\n".join(lines)


def _build_draft(
    node: ChunkableNode, by_parent: dict[uuid.UUID | None, list[ChunkableNode]]
) -> ChunkDraft:
    if node.node_type == _TABLE_TYPE:
        return ChunkDraft(anchor_node=node, text=_render_table_text(node, by_parent))

    text_nodes = _collect_descendant_text_nodes(node, by_parent)
    full_text = "\n".join(n.text for n in text_nodes if n.text)

    if estimate_tokens(full_text) <= settings.CHUNK_MAX_TOKENS:
        return ChunkDraft(anchor_node=node, text=full_text)

    structural_children = _structural_children(node, by_parent)
    if not structural_children:
        # No natural sub-boundary — token/paragraph-boundary subdivision.
        pieces = _split_by_token_budget(full_text, settings.CHUNK_MAX_TOKENS)
        return ChunkDraft(
            anchor_node=node,
            text="",
            children=[ChunkDraft(anchor_node=node, text=piece) for piece in pieces],
        )

    child_drafts = [_build_draft(child, by_parent) for child in structural_children]
    return ChunkDraft(anchor_node=node, text=node.text or "", children=child_drafts)


def _page_range(draft: ChunkDraft) -> tuple[int, int]:
    starts = [draft.anchor_node.page_start]
    ends = [draft.anchor_node.page_end]
    for child in draft.children:
        child_start, child_end = _page_range(child)
        starts.append(child_start)
        ends.append(child_end)
    return min(starts), max(ends)


def _flatten(
    draft: ChunkDraft,
    parent_chunk_id: uuid.UUID | None,
    depth: int,
    sequence_number: int,
    chunks: list[ChunkSpec],
    last_sibling: dict[uuid.UUID | None, ChunkSpec],
) -> None:
    page_start, page_end = _page_range(draft)
    chunk = ChunkSpec(
        id=uuid.uuid4(),
        source_node_id=draft.anchor_node.id,
        parent_chunk_id=parent_chunk_id,
        depth=depth,
        sequence_number=sequence_number,
        page_start=page_start,
        page_end=page_end,
        original_text=draft.text,
        structural_path_json=draft.anchor_node.structural_path_json,
        structural_path_text=draft.anchor_node.structural_path_text,
        token_count=estimate_tokens(draft.text),
    )

    previous = last_sibling.get(parent_chunk_id)
    if previous is not None:
        previous.next_chunk_id = chunk.id
        chunk.previous_chunk_id = previous.id
    last_sibling[parent_chunk_id] = chunk
    chunks.append(chunk)

    for index, child_draft in enumerate(draft.children):
        _flatten(child_draft, chunk.id, depth + 1, index, chunks, last_sibling)


def build_chunks(nodes: list[ChunkableNode]) -> list[ChunkSpec]:
    by_parent = _children_by_parent(nodes)
    roots = find_chunk_roots(nodes)

    chunks: list[ChunkSpec] = []
    last_sibling: dict[uuid.UUID | None, ChunkSpec] = {}
    for index, root in enumerate(roots):
        draft = _build_draft(root, by_parent)
        _flatten(draft, None, 0, index, chunks, last_sibling)
    return chunks
