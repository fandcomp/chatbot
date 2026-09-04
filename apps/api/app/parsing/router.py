import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import log_action
from app.auth.dependencies import get_current_membership, require_role
from app.core.database import get_db
from app.core.tasks import enqueue_chunk_document
from app.documents.models import DocumentLifecycleStatus
from app.documents.router import get_org_scoped_document, latest_version
from app.ingestion.models import ProcessingJob, ProcessingJobStatus
from app.organizations.models import OrganizationMember, OrgRole
from app.parsing.models import DocumentNode, DocumentRegion, DocumentStructureProfile
from app.parsing.schemas import (
    ApprovalResult,
    DocumentStructurePublic,
    NodeCorrectionRequest,
    StructureNodePublic,
    StructureProfilePublic,
    StructureRegionPublic,
)
from app.parsing.structural_path import order_region_nodes, rebuild_region_structural_paths

router = APIRouter(tags=["parsing"])


def _to_structure_node_public(node: DocumentNode) -> StructureNodePublic:
    return StructureNodePublic(
        id=node.id,
        region_id=node.region_id,
        parent_id=node.parent_id,
        node_type=node.node_type,
        semantic_role=node.semantic_role,
        label=node.label,
        title=node.title,
        text=node.text,
        number_raw=node.number_raw,
        number_normalized=node.number_normalized,
        depth=node.depth,
        sequence_number=node.sequence_number,
        page_start=node.page_start,
        page_end=node.page_end,
        confidence=float(node.confidence),
        structural_path_json=node.structural_path_json,
        structural_path_text=node.structural_path_text,
        structural_depth=node.structural_depth,
        chapter_number=node.chapter_number,
        article_number=node.article_number,
        clause_number=node.clause_number,
        letter_number=node.letter_number,
        appendix_number=node.appendix_number,
    )


def _to_structure_region_public(region: DocumentRegion) -> StructureRegionPublic:
    return StructureRegionPublic(
        id=region.id,
        region_type=region.region_type,
        page_start=region.page_start,
        page_end=region.page_end,
        sequence_number=region.sequence_number,
        confidence=float(region.confidence),
    )


@router.get("/documents/{document_id}/structure", response_model=DocumentStructurePublic)
async def get_document_structure(
    document_id: uuid.UUID,
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> DocumentStructurePublic:
    document = await get_org_scoped_document(db, document_id, membership.organization_id)
    version = await latest_version(db, document.id)

    regions = (
        (
            await db.execute(
                select(DocumentRegion).where(DocumentRegion.document_version_id == version.id)
            )
        )
        .scalars()
        .all()
    )
    nodes = (
        (
            await db.execute(
                select(DocumentNode).where(DocumentNode.document_version_id == version.id)
            )
        )
        .scalars()
        .all()
    )
    profile = (
        await db.execute(
            select(DocumentStructureProfile).where(
                DocumentStructureProfile.document_version_id == version.id
            )
        )
    ).scalar_one_or_none()

    # default=0.0 (not 1.0): a version with zero nodes must never display as
    # fully confident.
    aggregate_confidence = min((float(node.confidence) for node in nodes), default=0.0)

    return DocumentStructurePublic(
        document_version_id=version.id,
        version_status=version.status,
        aggregate_confidence=aggregate_confidence,
        regions=[_to_structure_region_public(region) for region in regions],
        nodes=[_to_structure_node_public(node) for node in nodes],
        profile=(
            StructureProfilePublic(
                contains_articles=profile.contains_articles,
                contains_numbered_sections=profile.contains_numbered_sections,
                contains_chapters=profile.contains_chapters,
                contains_decision_preamble=profile.contains_decision_preamble,
                contains_appendices=profile.contains_appendices,
                contains_tables=profile.contains_tables,
                contains_diagrams=profile.contains_diagrams,
                contains_embedded_document=profile.contains_embedded_document,
            )
            if profile is not None
            else None
        ),
    )


@router.patch("/documents/{document_id}/nodes/{node_id}", response_model=StructureNodePublic)
async def correct_document_node(
    document_id: uuid.UUID,
    node_id: uuid.UUID,
    body: NodeCorrectionRequest,
    membership: OrganizationMember = Depends(
        require_role(OrgRole.OWNER, OrgRole.ADMIN, OrgRole.EDITOR)
    ),
    db: AsyncSession = Depends(get_db),
) -> StructureNodePublic:
    document = await get_org_scoped_document(db, document_id, membership.organization_id)
    version = await latest_version(db, document.id)

    node = (
        await db.execute(
            select(DocumentNode).where(
                DocumentNode.id == node_id, DocumentNode.document_version_id == version.id
            )
        )
    ).scalar_one_or_none()
    if node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found")

    old_value = {
        "node_type": node.node_type.value,
        "parent_id": str(node.parent_id) if node.parent_id else None,
        "label": node.label,
        "title": node.title,
    }

    if body.parent_id is not None:
        if body.parent_id == node.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="A node cannot be its own parent"
            )
        parent = (
            await db.execute(
                select(DocumentNode).where(
                    DocumentNode.id == body.parent_id,
                    DocumentNode.document_version_id == version.id,
                )
            )
        ).scalar_one_or_none()
        if parent is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Parent node not found"
            )

        # Reject a parent that is actually a descendant of this node — that
        # would create a parent_id cycle, silently excluding the whole
        # subtree from order_region_nodes's traversal (its structural paths
        # would then never be recomputed again).
        all_version_nodes = (
            (
                await db.execute(
                    select(DocumentNode.id, DocumentNode.parent_id).where(
                        DocumentNode.document_version_id == version.id
                    )
                )
            )
            .all()
        )
        parent_by_id = {row.id: row.parent_id for row in all_version_nodes}
        ancestor_id = body.parent_id
        while ancestor_id is not None:
            if ancestor_id == node.id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot move a node under its own descendant",
                )
            ancestor_id = parent_by_id.get(ancestor_id)

        node.parent_id = body.parent_id
    if body.node_type is not None:
        node.node_type = body.node_type
    if body.label is not None:
        node.label = body.label
    if body.title is not None:
        node.title = body.title
    if body.region_type is not None:
        # A node-level correction can also fix the classification of the
        # StructuralRegion it belongs to (addendum §27's "region type" is a
        # region-level property — there is no per-node region_type column).
        region = (
            await db.execute(select(DocumentRegion).where(DocumentRegion.id == node.region_id))
        ).scalar_one()
        region.region_type = body.region_type

    # Recompute the whole region's structural paths rather than just the
    # corrected node's subtree — modest per-document node counts make a full
    # per-region recompute simpler and safer than a partial one (KISS).
    region_nodes = (
        (await db.execute(select(DocumentNode).where(DocumentNode.region_id == node.region_id)))
        .scalars()
        .all()
    )
    rebuild_region_structural_paths(order_region_nodes(region_nodes))
    await db.flush()

    await log_action(
        db,
        actor_id=membership.user_id,
        organization_id=membership.organization_id,
        action="document_node_correct",
        entity_type="document_node",
        entity_id=node.id,
        old_value=old_value,
        new_value={
            "node_type": node.node_type.value,
            "parent_id": str(node.parent_id) if node.parent_id else None,
            "label": node.label,
            "title": node.title,
        },
    )
    await db.commit()
    await db.refresh(node)

    return _to_structure_node_public(node)


@router.post("/documents/{document_id}/approve", response_model=ApprovalResult)
async def approve_document_structure(
    document_id: uuid.UUID,
    membership: OrganizationMember = Depends(
        require_role(OrgRole.OWNER, OrgRole.ADMIN, OrgRole.EDITOR)
    ),
    db: AsyncSession = Depends(get_db),
) -> ApprovalResult:
    document = await get_org_scoped_document(db, document_id, membership.organization_id)
    version = await latest_version(db, document.id)

    if version.status != DocumentLifecycleStatus.REVIEW_REQUIRED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document is not awaiting structure review",
        )

    version.status = DocumentLifecycleStatus.APPROVED

    # M2-M4's job for this version is already terminal (SUCCEEDED) by the
    # time it reaches REVIEW_REQUIRED — chunking (M5) needs its own new job
    # row rather than regressing a terminal job back to PROCESSING (mirrors
    # the auto-approved path's same reasoning in the worker's
    # interpret_structure task).
    job = ProcessingJob(
        organization_id=membership.organization_id,
        document_version_id=version.id,
        status=ProcessingJobStatus.QUEUED,
    )
    db.add(job)
    await db.flush()
    job.celery_task_id = enqueue_chunk_document(str(job.id))

    await log_action(
        db,
        actor_id=membership.user_id,
        organization_id=membership.organization_id,
        action="document_structure_approve",
        entity_type="document_version",
        entity_id=version.id,
    )
    await db.commit()

    return ApprovalResult(
        document_id=document.id, document_version_id=version.id, status=version.status
    )
