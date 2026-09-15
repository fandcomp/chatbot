"""Unit tests for the streaming path's inline-citation parser (spec §41)."""

from app.chat.inline_citation_parser import (
    REDACTION_PLACEHOLDER,
    parse_inline_citations,
    redact_unsupported_claims,
)
from app.verification.schemas import ClaimStatus, VerifiedClaim


def _verified(text: str, status: ClaimStatus, source_ids: list[str] | None = None) -> VerifiedClaim:
    return VerifiedClaim(text=text, source_ids=source_ids or [], status=status, invalid_reason=None)


def test_parses_single_sentence_with_one_source() -> None:
    claims = parse_inline_citations("Setiap warga negara berhak atas pendidikan. [S1]")
    assert len(claims) == 1
    assert claims[0].text == "Setiap warga negara berhak atas pendidikan."
    assert claims[0].source_ids == ["S1"]


def test_parses_multiple_sentences_with_different_sources() -> None:
    text = "Pertama, ketentuan A berlaku. [S1] Kedua, ketentuan B juga berlaku. [S2]"
    claims = parse_inline_citations(text)
    assert len(claims) == 2
    assert claims[0].source_ids == ["S1"]
    assert claims[1].source_ids == ["S2"]


def test_parses_multiple_sources_in_one_marker() -> None:
    claims = parse_inline_citations("Ketentuan ini konsisten. [S1, S2]")
    assert claims[0].source_ids == ["S1", "S2"]


def test_trailing_uncited_text_becomes_claim_with_no_sources() -> None:
    text = "Ketentuan A berlaku. [S1] Ini adalah kesimpulan tanpa sumber."
    claims = parse_inline_citations(text)
    assert len(claims) == 2
    assert claims[1].source_ids == []
    assert "kesimpulan" in claims[1].text


def test_text_with_no_markers_at_all_becomes_one_uncited_claim() -> None:
    claims = parse_inline_citations("Ini jawaban tanpa sitasi sama sekali.")
    assert len(claims) == 1
    assert claims[0].source_ids == []


def test_empty_text_produces_no_claims() -> None:
    assert parse_inline_citations("") == []


# -- redact_unsupported_claims (ADR-022) --------------------------------


def test_redacts_an_unsupported_claim_including_its_citation_marker() -> None:
    text = "Ketentuan A berlaku. [S1] Ketentuan palsu ini tidak berlaku. [S2]"
    verified = [
        _verified("Ketentuan A berlaku.", ClaimStatus.SUPPORTED, ["S1"]),
        _verified("Ketentuan palsu ini tidak berlaku.", ClaimStatus.UNSUPPORTED, ["S2"]),
    ]

    result = redact_unsupported_claims(text, verified)

    assert "Ketentuan A berlaku. [S1]" in result
    assert "Ketentuan palsu" not in result
    assert "[S2]" not in result
    assert REDACTION_PLACEHOLDER in result


def test_supported_and_uncertain_claims_are_left_untouched() -> None:
    text = "Pertama. [S1] Kedua. [S2]"
    verified = [
        _verified("Pertama.", ClaimStatus.SUPPORTED, ["S1"]),
        _verified("Kedua.", ClaimStatus.UNCERTAIN, ["S2"]),
    ]

    assert redact_unsupported_claims(text, verified) == text


def test_redacting_an_uncited_trailing_claim_removes_only_that_segment() -> None:
    text = "Ketentuan A berlaku. [S1] Ini kesimpulan tanpa sumber yang mengarang fakta."
    verified = [
        _verified("Ketentuan A berlaku.", ClaimStatus.SUPPORTED, ["S1"]),
        _verified("Ini kesimpulan tanpa sumber yang mengarang fakta.", ClaimStatus.UNSUPPORTED, []),
    ]

    result = redact_unsupported_claims(text, verified)

    assert "Ketentuan A berlaku. [S1]" in result
    assert "mengarang fakta" not in result
    assert REDACTION_PLACEHOLDER in result


def test_mismatched_claim_count_returns_text_unmodified() -> None:
    # Defensive path: verified_claims must come from verifying
    # parse_inline_citations(text) against this exact text — a mismatch
    # means the caller passed stale/unrelated data, and guessing which
    # claim maps to which span would be worse than not redacting at all.
    text = "Satu klaim saja. [S1]"
    verified = [
        _verified("Satu klaim saja.", ClaimStatus.UNSUPPORTED, ["S1"]),
        _verified("Klaim kedua yang tidak ada di text.", ClaimStatus.UNSUPPORTED, ["S2"]),
    ]

    assert redact_unsupported_claims(text, verified) == text
