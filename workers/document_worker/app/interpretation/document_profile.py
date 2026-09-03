"""DocumentStructureProfile builder (addendum §15) — an 8-flag coarse summary
of a document version's structure, used by the review UI and later
milestones' retrieval routing (§24) without re-walking the whole node tree.
"""

from app.interpretation.models import InterpretedNode

_DIAGRAM_NODE_TYPES = {"DIAGRAM", "FIGURE", "FLOWCHART", "ORGANIZATION_CHART"}
_DIAGRAM_REGION_TYPES = {"DIAGRAM_REGION", "ORGANIZATION_CHART", "FLOWCHART"}


def build_structure_profile(
    nodes: list[InterpretedNode], region_types: list[str]
) -> dict[str, bool]:
    node_types = {node.node_type for node in nodes}
    region_type_set = set(region_types)
    return {
        "contains_articles": "ARTICLE" in node_types,
        "contains_numbered_sections": "NUMBERED_SECTION" in node_types,
        "contains_chapters": "CHAPTER" in node_types,
        "contains_decision_preamble": "DECISION_ITEM" in node_types,
        "contains_appendices": "APPENDIX" in node_types or "APPENDIX" in region_type_set,
        "contains_tables": "TABLE" in node_types,
        "contains_diagrams": bool(node_types & _DIAGRAM_NODE_TYPES)
        or bool(region_type_set & _DIAGRAM_REGION_TYPES),
        "contains_embedded_document": "EMBEDDED_TEMPLATE" in region_type_set,
    }
