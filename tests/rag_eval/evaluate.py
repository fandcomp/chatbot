"""RAG Evaluation harness (docs/MASTER_DEVELOPMENT_SPEC.md §96).

Runs a golden question set against a REAL running instance of the backend
(real Postgres/Qdrant/Redis, real Voyage/HF credentials) and reports the
subset of §96's metrics this script computes:

    Recall@K, MRR, Citation Accuracy, Citation Coverage,
    Insufficient-Evidence Accuracy, Latency (p50/p95)

Deliberately NOT implemented here (documented gap, not a hidden one):

    nDCG                 — needs graded relevance judgments, not just a
                            single expected_article per question.
    Faithfulness         — needs an LLM-as-judge or a library like RAGAS;
                            out of scope for a zero-dependency stdlib script.
    Answer Correctness   — same as Faithfulness; a substring/keyword check
                            against expected_answer would be a false sense
                            of rigor, so it is left out rather than faked.
    Cost per Query       — this codebase computes estimated_cost_usd only
                            as an aggregate in GET /analytics/overview, not
                            per-request; read that endpoint separately if
                            you need a cost figure alongside a given run.

This script has zero third-party dependencies (stdlib only: urllib, json)
so it needs no venv beyond a plain Python 3.11+ interpreter — run it from
anywhere:

    python tests/rag_eval/evaluate.py \\
        --base-url http://localhost:8000 \\
        --email owner@example.com --password '...' \\
        --dataset tests/rag_eval/dataset.example.json

Copy dataset.example.json to your own dataset.json (git-ignored is up to
you) seeded with real questions against documents already ACTIVE in the
target organization — this script does not upload or index anything.
"""

from __future__ import annotations

import argparse
import http.cookiejar
import json
import statistics
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field


@dataclass
class QuestionResult:
    question: str
    latency_ms: float
    reciprocal_rank: float | None  # None when expected_article is not given
    recall_hit: bool | None
    expect_insufficient: bool
    got_insufficient: bool
    citation_hit: bool | None
    claim_support_rate: float | None
    error: str | None = None


@dataclass
class Report:
    results: list[QuestionResult] = field(default_factory=list)

    def summarize(self, k: int) -> dict:
        ranked = [r for r in self.results if r.reciprocal_rank is not None and r.error is None]
        cited = [r for r in self.results if r.citation_hit is not None and r.error is None]
        insufficiency_checked = [r for r in self.results if r.error is None]
        latencies = [r.latency_ms for r in self.results if r.error is None]
        return {
            "questions": len(self.results),
            "errors": sum(1 for r in self.results if r.error),
            f"recall_at_{k}": (
                sum(1 for r in ranked if r.recall_hit) / len(ranked) if ranked else None
            ),
            "mrr": statistics.mean(r.reciprocal_rank for r in ranked) if ranked else None,
            "citation_accuracy": (
                sum(1 for r in cited if r.citation_hit) / len(cited) if cited else None
            ),
            "citation_coverage": (
                statistics.mean(
                    r.claim_support_rate for r in cited if r.claim_support_rate is not None
                )
                if any(r.claim_support_rate is not None for r in cited)
                else None
            ),
            "insufficient_evidence_accuracy": (
                sum(
                    1
                    for r in insufficiency_checked
                    if r.expect_insufficient == r.got_insufficient
                )
                / len(insufficiency_checked)
                if insufficiency_checked
                else None
            ),
            "latency_p50_ms": statistics.median(latencies) if latencies else None,
            "latency_p95_ms": (
                statistics.quantiles(latencies, n=20)[18] if len(latencies) >= 20 else max(latencies)
            )
            if latencies
            else None,
        }


class ApiClient:
    def __init__(self, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")
        jar = http.cookiejar.CookieJar()
        self._opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    def _post(self, path: str, body: dict) -> dict:
        request = urllib.request.Request(
            f"{self._base_url}{path}",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self._opener.open(request, timeout=60) as response:
            return json.loads(response.read())

    def login(self, email: str, password: str) -> None:
        self._post("/auth/login", {"email": email, "password": password})

    def search(self, query: str) -> dict:
        return self._post("/retrieval/search", {"query": query})

    def chat(self, query: str) -> dict:
        return self._post("/chat", {"query": query})


def _evaluate_question(client: ApiClient, item: dict, k: int) -> QuestionResult:
    question = item["question"]
    expected_article = item.get("expected_article")
    expect_insufficient = bool(item.get("expect_insufficient", False))

    try:
        started = time.perf_counter()
        chat_response = client.chat(question)
        latency_ms = (time.perf_counter() - started) * 1000
    except urllib.error.URLError as exc:
        return QuestionResult(
            question=question,
            latency_ms=0.0,
            reciprocal_rank=None,
            recall_hit=None,
            expect_insufficient=expect_insufficient,
            got_insufficient=False,
            citation_hit=None,
            claim_support_rate=None,
            error=str(exc),
        )

    answer = chat_response["answer"]
    got_insufficient = answer["insufficient_evidence"]

    reciprocal_rank = None
    recall_hit = None
    if expected_article and not expect_insufficient:
        search_response = client.search(question)
        chunks = search_response["chunks"][:k]
        rank = next(
            (
                i + 1
                for i, chunk in enumerate(chunks)
                if chunk["structural_path_text"] and expected_article in chunk["structural_path_text"]
            ),
            None,
        )
        recall_hit = rank is not None
        reciprocal_rank = (1.0 / rank) if rank else 0.0

    citation_hit = None
    claim_support_rate = None
    if expected_article and not expect_insufficient:
        citations = answer.get("citations", {})
        citation_hit = any(
            expected_article in (c.get("structural_path_text") or "") for c in citations.values()
        )
        claims = answer.get("claims", [])
        if claims:
            claim_support_rate = sum(1 for c in claims if c["status"] == "SUPPORTED") / len(claims)

    return QuestionResult(
        question=question,
        latency_ms=latency_ms,
        reciprocal_rank=reciprocal_rank,
        recall_hit=recall_hit,
        expect_insufficient=expect_insufficient,
        got_insufficient=got_insufficient,
        citation_hit=citation_hit,
        claim_support_rate=claim_support_rate,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--k", type=int, default=5, help="Recall@K / ranked-list cutoff")
    args = parser.parse_args()

    with open(args.dataset, encoding="utf-8") as f:
        dataset = json.load(f)

    client = ApiClient(args.base_url)
    client.login(args.email, args.password)

    report = Report()
    for item in dataset:
        result = _evaluate_question(client, item, args.k)
        report.results.append(result)
        status = "ERROR" if result.error else ("OK" if not result.error else "")
        print(f"[{status or 'OK'}] {result.question!r} — {result.latency_ms:.0f}ms")
        if result.error:
            print(f"    {result.error}")

    summary = report.summarize(args.k)
    print("\n--- Summary ---")
    for key, value in summary.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
