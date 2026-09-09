"""Seeds one organization, one ACTIVE document, and one golden question for
the Playwright golden-path e2e test (tests/e2e/chat.spec.ts).

Runs the REAL upload -> parse -> interpret -> chunk -> index pipeline
(Docling + Voyage embeddings) against a live apps/api + document_worker
stack — this is not a mock. Needs real VOYAGE_API_KEY/HF_TOKEN configured
(same requirement as tests/rag_eval/evaluate.py) and takes on the order of
seconds to a couple of minutes depending on the machine.

Run from apps/api's uv environment (it already has httpx as a dev
dependency; reportlab was added alongside it for this script):

    cd apps/api
    uv run python ../../tests/e2e/seed.py --base-url http://localhost:8000 \\
        --out ../../tests/e2e/.seed.json

Requires: Postgres/Redis/Qdrant/MinIO (docker compose), apps/api's dev
server, and workers/document_worker's celery worker (--pool=solo on
Windows) all running — see workers/document_worker/README.md.
"""

from __future__ import annotations

import argparse
import io
import json
import time
import uuid

import httpx
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate

QUESTION = "Apa isi Pasal 1 tentang kewajiban pegawai?"
PASAL_TEXT = "Setiap pegawai wajib hadir tepat waktu dan mematuhi tata tertib kantor."

_STYLES = getSampleStyleSheet()
_TITLE = ParagraphStyle("Title", parent=_STYLES["Title"], fontSize=16, spaceAfter=18)
_HEADING = ParagraphStyle("Heading", parent=_STYLES["Heading1"], spaceBefore=12, spaceAfter=10)
_BODY = ParagraphStyle("Body", parent=_STYLES["BodyText"], spaceBefore=24, spaceAfter=24)


def _build_pdf() -> bytes:
    # Mirrors workers/document_worker/tests/fixtures.py's bab_pasal_ayat_pdf
    # (platypus flowables, not raw canvas.drawString — see that file's own
    # docstring for why Docling needs real spacing between text blocks).
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    doc.build(
        [
            Paragraph("PERATURAN CONTOH NOMOR 9 TAHUN 2026", _TITLE),
            Paragraph("TENTANG TATA TERTIB KEPEGAWAIAN", _BODY),
            PageBreak(),
            Paragraph("BAB I", _HEADING),
            Paragraph("KETENTUAN UMUM", _HEADING),
            Paragraph("Pasal 1", _BODY),
            Paragraph(PASAL_TEXT, _BODY),
        ]
    )
    return buffer.getvalue()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--out", default="tests/e2e/.seed.json")
    parser.add_argument("--timeout", type=int, default=180, help="Seconds to wait for ACTIVE")
    args = parser.parse_args()

    run_id = uuid.uuid4().hex[:8]
    email = f"e2e-{run_id}@example.com"
    password = "e2e-test-password-123"

    client = httpx.Client(base_url=args.base_url, timeout=30.0)

    print(f"Registering org for {email} ...")
    register_response = client.post(
        "/auth/register",
        json={
            "organization_name": f"E2E Org {run_id}",
            "email": email,
            "password": password,
        },
    )
    register_response.raise_for_status()

    spaces_response = client.get("/knowledge-spaces")
    spaces_response.raise_for_status()
    knowledge_space_id = spaces_response.json()[0]["id"]

    print("Uploading a real BAB/Pasal PDF (Docling will parse this for real) ...")
    upload_response = client.post(
        "/documents/upload",
        files={"file": ("tata-tertib.pdf", _build_pdf(), "application/pdf")},
        data={"knowledge_space_id": knowledge_space_id},
    )
    upload_response.raise_for_status()
    document_id = upload_response.json()["document_id"]

    print(f"Waiting up to {args.timeout}s for document {document_id} to reach ACTIVE ...")
    deadline = time.monotonic() + args.timeout
    status = None
    while time.monotonic() < deadline:
        document_response = client.get(f"/documents/{document_id}")
        document_response.raise_for_status()
        status = document_response.json()["latest_version_status"]
        if status in ("ACTIVE", "PROCESSING_FAILED"):
            break
        time.sleep(3)

    if status != "ACTIVE":
        raise SystemExit(
            f"Document never reached ACTIVE (last status: {status!r}) — check apps/api and "
            "document_worker logs. Common causes: worker not running, missing/invalid "
            "VOYAGE_API_KEY or HF_TOKEN."
        )

    print(f"Document {document_id} is ACTIVE.")
    seed = {
        "base_url": args.base_url,
        "email": email,
        "password": password,
        "document_id": document_id,
        "question": QUESTION,
        "expected_article": "Pasal 1",
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(seed, f, indent=2)
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
