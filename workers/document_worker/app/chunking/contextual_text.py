"""Generic contextual-text renderer (addendum §24.2). Spec's own example is
Pasal-specific ("Dokumen:/BAB:/Pasal:/Ayat:/Isi:") — generalized here to
walk the chunk's own `structural_path_json` (already grammar-faithful from
M4's StructuralPathService: each entry's `label` is a fully-rendered,
terminology-correct string like "Pasal 20" or "11. Urut-urutan Kegiatan")
so a NUMBERED_SECTION-grammar document never gets a fabricated "Pasal:"
line. Deliberately simpler than the spec's illustrative tag/value split
(e.g. "Pasal:" then "17" on its own line) — M4's labels are already
self-descriptive, so a synthetic per-node-type tag would just duplicate
what the label already says.
"""

from typing import Any


def render_contextual_text(
    document_title: str, structural_path_json: list[dict[str, Any]], original_text: str
) -> str:
    ancestor_labels = [entry["label"] for entry in structural_path_json if entry.get("label")]
    lines = ["Dokumen:", document_title, ""]
    lines.extend(ancestor_labels)
    if ancestor_labels:
        lines.append("")
    lines.append("Isi:")
    lines.append(original_text)
    return "\n".join(lines)
