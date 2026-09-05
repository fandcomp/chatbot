"""Unit tests for ClaimVerificationService (spec §40, addendum §34)."""

import uuid

from app.llm.answer_schemas import Claim
from app.reranking.schemas import Evidence
from app.verification.schemas import ClaimStatus
from app.verification.service import ClaimVerificationService


def _evidence(evidence_id: str, structural_path_text: str, original_text: str) -> Evidence:
    return Evidence(
        evidence_id=evidence_id,
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_version_id=uuid.uuid4(),
        structural_path_text=structural_path_text,
        original_text=original_text,
        page_start=1,
        page_end=1,
        parent_context=None,
        relevance_score=None,
    )


def test_claim_citing_unknown_source_id_is_unsupported() -> None:
    service = ClaimVerificationService()
    claim = Claim(text="Setiap warga negara berhak atas pendidikan.", source_ids=["S9"])
    evidence = [_evidence("S1", "Pasal 5", "Setiap warga negara berhak atas pendidikan.")]

    result = service.verify([claim], evidence)

    assert result[0].status == ClaimStatus.UNSUPPORTED
    assert "unknown source" in result[0].invalid_reason


def test_claim_citing_no_source_at_all_is_unsupported() -> None:
    service = ClaimVerificationService()
    claim = Claim(text="Ketentuan berlaku.", source_ids=[])
    result = service.verify([claim], [])
    assert result[0].status == ClaimStatus.UNSUPPORTED


def test_claim_mentioning_pasal_for_numbered_section_source_is_flagged_invalid() -> None:
    # addendum §34's exact scenario: answer says Pasal 11, but the cited
    # source is a numbered section, never labeled "Pasal" anywhere.
    service = ClaimVerificationService()
    claim = Claim(
        text="Berdasarkan Pasal 11, kegiatan tersebut wajib dilaksanakan.",
        source_ids=["S1"],
    )
    evidence = [
        _evidence("S1", "BAB III > 11 Urut-urutan Kegiatan", "11. Kegiatan wajib dilaksanakan.")
    ]

    result = service.verify([claim], evidence)

    assert result[0].status == ClaimStatus.UNSUPPORTED
    assert "addendum" in result[0].invalid_reason.lower()


def test_claim_mentioning_pasal_for_real_article_source_is_not_flagged_for_terminology() -> None:
    service = ClaimVerificationService()
    claim = Claim(
        text="Berdasarkan Pasal 5, setiap warga negara berhak atas pendidikan.",
        source_ids=["S1"],
    )
    evidence = [_evidence("S1", "Pasal 5", "Setiap warga negara berhak atas pendidikan.")]

    result = service.verify([claim], evidence)

    assert result[0].status != ClaimStatus.UNSUPPORTED


def test_claim_with_strong_lexical_overlap_is_supported() -> None:
    service = ClaimVerificationService()
    claim = Claim(
        text="Setiap warga negara berhak atas pendidikan dasar.",
        source_ids=["S1"],
    )
    evidence = [
        _evidence(
            "S1",
            "Pasal 5",
            "Setiap warga negara berhak atas pendidikan dasar yang layak.",
        )
    ]

    result = service.verify([claim], evidence)

    assert result[0].status == ClaimStatus.SUPPORTED


def test_claim_with_weak_lexical_overlap_is_uncertain_not_supported() -> None:
    service = ClaimVerificationService()
    claim = Claim(
        text="Prosedur pengajuan izin memerlukan waktu tiga puluh hari kerja.",
        source_ids=["S1"],
    )
    evidence = [_evidence("S1", "Pasal 5", "Setiap warga negara berhak atas pendidikan.")]

    result = service.verify([claim], evidence)

    assert result[0].status == ClaimStatus.UNCERTAIN
