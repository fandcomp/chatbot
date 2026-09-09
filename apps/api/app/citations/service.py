"""AdaptiveCitationService (spec §90/§41, addendum §16-18) — maps S1/S2/...
to real citations using each source's own terminology via its already-
rendered structural_path_text. Never fabricates a Document->BAB->Pasal->
Ayat->Huruf->Page structure (addendum §16) — the generic structural_path
IS the citation, rendered adaptively back in M5.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.citations.schemas import Citation, RelatingDocument
from app.documents.models import (
    Document,
    DocumentRelation,
    DocumentRelationType,
    DocumentVersion,
)
from app.reranking.schemas import Evidence

_EXCERPT_MAX_CHARS = 500

# AMENDS/REPEALS/REPLACES all mean "the cited document is no longer the
# whole story" and are worth a citation warning. IMPLEMENTS/REFERS_TO are
# plain cross-references (this document implements/mentions another) with no
# staleness implication, and SUPERSEDED_BY is a version-lifecycle fact that
# never applies here — evidence only ever comes from an ACTIVE version (M7),
# so it can never be the "to" side of its own supersede relation.
_SUPERSEDING_RELATION_TYPES = (
    DocumentRelationType.AMENDS,
    DocumentRelationType.REPEALS,
    DocumentRelationType.REPLACES,
)


class AdaptiveCitationService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def build_citations(
        self, evidence: list[Evidence], organization_id: uuid.UUID
    ) -> dict[str, Citation]:
        document_ids = {item.document_id for item in evidence}
        titles = await self._fetch_titles(document_ids, organization_id)
        relations = await self._fetch_superseding_relations(document_ids, organization_id)
        return {
            item.evidence_id: Citation(
                source_id=item.evidence_id,
                document_id=item.document_id,
                document_title=titles.get(item.document_id, "(unknown document)"),
                structural_path_text=item.structural_path_text,
                page_start=item.page_start,
                page_end=item.page_end,
                original_text_excerpt=item.original_text[:_EXCERPT_MAX_CHARS],
                superseding_relations=relations.get(item.document_id, []),
            )
            for item in evidence
        }

    async def _fetch_titles(
        self, document_ids: set[uuid.UUID], organization_id: uuid.UUID
    ) -> dict[uuid.UUID, str]:
        if not document_ids:
            return {}
        rows = (
            await self._db.execute(
                select(Document.id, Document.title).where(
                    Document.id.in_(document_ids),
                    Document.organization_id == organization_id,
                )
            )
        ).all()
        return {row.id: row.title for row in rows}

    async def _fetch_superseding_relations(
        self, document_ids: set[uuid.UUID], organization_id: uuid.UUID
    ) -> dict[uuid.UUID, list[RelatingDocument]]:
        if not document_ids:
            return {}
        to_version = aliased(DocumentVersion)
        from_version = aliased(DocumentVersion)
        from_document = aliased(Document)
        rows = (
            await self._db.execute(
                select(
                    to_version.document_id,
                    DocumentRelation.relation_type,
                    from_document.id,
                    from_document.title,
                )
                .join(to_version, DocumentRelation.to_document_version_id == to_version.id)
                .join(from_version, DocumentRelation.from_document_version_id == from_version.id)
                .join(from_document, from_version.document_id == from_document.id)
                .where(
                    to_version.document_id.in_(document_ids),
                    DocumentRelation.relation_type.in_(_SUPERSEDING_RELATION_TYPES),
                    DocumentRelation.organization_id == organization_id,
                )
            )
        ).all()
        result: dict[uuid.UUID, list[RelatingDocument]] = {}
        for cited_document_id, relation_type, related_document_id, related_document_title in rows:
            result.setdefault(cited_document_id, []).append(
                RelatingDocument(
                    relation_type=relation_type,
                    related_document_id=related_document_id,
                    related_document_title=related_document_title,
                )
            )
        return result
