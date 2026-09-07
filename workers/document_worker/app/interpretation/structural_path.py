"""StructuralPathService (addendum §37) — rebuilds structural_path_json with
specialized, source-terminology-faithful labels (§17-18) and renders
structural_path_text for display.

Uses a rank-based context stack keyed by *semantic* nesting level rather than
each node's raw `parent_id` — this recovers correct hierarchy (e.g. a letter
item nesting under the numbered section that precedes it) even when M3's
Docling-derived tree left true siblings flat (see specialized_interpreter.py's
module docstring for why that happens).
"""

from app.interpretation.models import InterpretedNode

# Lower rank = higher (outer) in the hierarchy. A node type absent from this
# map never pushes a new context level — it's a leaf that inherits whatever
# context is currently on the stack (e.g. PARAGRAPH, TABLE, FIGURE).
# Public: chunk_builder.py reuses this exact table to recover the same
# hierarchy for chunk grouping — see its module docstring for why.
LEVEL_RANK: dict[str, int] = {
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


def _label_for(node: InterpretedNode) -> str:
    """specialized_interpreter.py sets `node.label` to the grammar-appropriate
    display token for every node it re-types (e.g. "huruf a" under an
    ARTICLE_BASED Pasal vs. bare "a" under a NUMBERED_SECTION_BASED item) —
    this renderer just joins those already-computed, terminology-faithful
    labels. Only a node the interpreter left untouched (M3's generic type)
    falls back to its title/text/type name here.
    """
    if node.label:
        return node.label
    return node.title or (node.text[:60] if node.text else node.node_type)


def _path_entry(node: InterpretedNode) -> dict[str, str | None]:
    return {"node_type": node.node_type, "label": _label_for(node), "title": node.title}


def render_structural_path_text(path_json: list[dict[str, str | None]]) -> str:
    return " > ".join(entry["label"] for entry in path_json if entry.get("label"))


def rebuild_structural_paths(nodes_ordered: list[InterpretedNode]) -> None:
    """Mutates each node's structural_path_json/structural_path_text/
    structural_depth in place, in document order for one region.
    """
    stack: list[tuple[int, dict[str, str | None]]] = []
    for node in nodes_ordered:
        entry = _path_entry(node)
        rank = LEVEL_RANK.get(node.node_type)
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
