"""AdaptiveCitationService (spec §90/§41, addendum §16-18) — maps S1/S2/...
to real citations using each source's own terminology via its already-
rendered structural_path_text. Never fabricates a Document->BAB->Pasal->
Ayat->Huruf->Page structure (addendum §16) — the generic structural_path
IS the citation, rendered adaptively back in M5.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.citations.schemas import Citation
from app.documents.models import Document
from app.reranking.schemas import Evidence


class AdaptiveCitationService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def build_citations(self, evidence: list[Evidence]) -> dict[str, Citation]:
        titles = await self._fetch_titles({item.document_id for item in evidence})
        return {
            item.evidence_id: Citation(
                source_id=item.evidence_id,
                document_id=item.document_id,
                document_title=titles.get(item.document_id, "(unknown document)"),
                structural_path_text=item.structural_path_text,
                page_start=item.page_start,
                page_end=item.page_end,
            )
            for item in evidence
        }

    async def _fetch_titles(self, document_ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
        if not document_ids:
            return {}
        rows = (
            await self._db.execute(
                select(Document.id, Document.title).where(Document.id.in_(document_ids))
            )
        ).all()
        return {row.id: row.title for row in rows}
