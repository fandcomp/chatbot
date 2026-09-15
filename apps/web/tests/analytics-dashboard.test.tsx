import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AnalyticsDashboard } from "@/components/analytics/analytics-dashboard";

const getOverviewMock = vi.fn();
const getKnowledgeBaseOverviewMock = vi.fn();
const listKnowledgeGapsMock = vi.fn();
const listTopQuestionsMock = vi.fn();
const listTopSourcesMock = vi.fn();

vi.mock("@/lib/analytics-api", () => ({
  analyticsApi: {
    getOverview: () => getOverviewMock(),
    getKnowledgeBaseOverview: () => getKnowledgeBaseOverviewMock(),
    listKnowledgeGaps: () => listKnowledgeGapsMock(),
    listTopQuestions: () => listTopQuestionsMock(),
    listTopSources: () => listTopSourcesMock(),
  },
}));

// A single row: RankedList renders each row's 1-based rank position as its
// own text node ("1", "2", ...), and a second row here would render a "2"
// that collides with the "Insufficient Evidence" stat's bare "2" text node
// below. total_documents/count values themselves are also picked to avoid
// colliding with OVERVIEW's numbers (2, 5, 1, 10, 8...).
const KNOWLEDGE_BASE = {
  total_documents: 7,
  total_indexed_chunks: 123,
  status_breakdown: [{ status: "ACTIVE", count: 4 }],
};

const OVERVIEW = {
  total_questions: 10,
  answered: 8,
  insufficient_evidence: 2,
  avg_latency_ms: 1500,
  p95_latency_ms: 2500,
  avg_cost_usd: 0.0032,
  citation_coverage: 0.9,
  retrieval_success: 0.95,
  cache_hit_rate: 0.4,
  thumbs_up: 5,
  thumbs_down: 1,
};

describe("AnalyticsDashboard", () => {
  it("renders overview stats, rates, and ranked lists on success", async () => {
    // Arrange
    getOverviewMock.mockResolvedValueOnce(OVERVIEW);
    getKnowledgeBaseOverviewMock.mockResolvedValueOnce(KNOWLEDGE_BASE);
    listKnowledgeGapsMock.mockResolvedValueOnce([
      { query: "Bagaimana prosedur X?", frequency: 37, last_asked_at: new Date().toISOString() },
    ]);
    listTopQuestionsMock.mockResolvedValueOnce([
      { query: "Apa isi Pasal 5?", frequency: 12, last_asked_at: new Date().toISOString() },
    ]);
    listTopSourcesMock.mockResolvedValueOnce([
      { document_id: "doc-1", document_title: "Peraturan X", citation_count: 9 },
    ]);

    // Act
    render(<AnalyticsDashboard />);

    // Assert
    expect(await screen.findByText("80%")).toBeInTheDocument();
    expect(screen.getByText("of 10 questions")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText("1.5s")).toBeInTheDocument();
    expect(screen.getByText("2.5s")).toBeInTheDocument();
    expect(screen.getByText("$0.0032")).toBeInTheDocument();
    expect(screen.getByText("5 / 1")).toBeInTheDocument();
    expect(screen.getByText("90%")).toBeInTheDocument();
    expect(screen.getByText("Bagaimana prosedur X?")).toBeInTheDocument();
    expect(screen.getByText("Apa isi Pasal 5?")).toBeInTheDocument();
    expect(screen.getByText("Peraturan X")).toBeInTheDocument();
    expect(screen.getByText("7")).toBeInTheDocument();
    expect(screen.getByText("123 indexed sections")).toBeInTheDocument();
    expect(screen.getByText("ACTIVE")).toBeInTheDocument();
  });

  it("shows an error message when a request fails", async () => {
    // Arrange
    getOverviewMock.mockRejectedValueOnce(new Error("boom"));
    getKnowledgeBaseOverviewMock.mockResolvedValueOnce(KNOWLEDGE_BASE);
    listKnowledgeGapsMock.mockResolvedValueOnce([]);
    listTopQuestionsMock.mockResolvedValueOnce([]);
    listTopSourcesMock.mockResolvedValueOnce([]);

    // Act
    render(<AnalyticsDashboard />);

    // Assert
    expect(await screen.findByText(/failed to load analytics/i)).toBeInTheDocument();
  });

  it("shows empty-state messages when there is no data yet", async () => {
    // Arrange
    getOverviewMock.mockResolvedValueOnce({ ...OVERVIEW, total_questions: 0, answered: 0 });
    getKnowledgeBaseOverviewMock.mockResolvedValueOnce({
      total_documents: 0,
      total_indexed_chunks: 0,
      status_breakdown: [],
    });
    listKnowledgeGapsMock.mockResolvedValueOnce([]);
    listTopQuestionsMock.mockResolvedValueOnce([]);
    listTopSourcesMock.mockResolvedValueOnce([]);

    // Act
    render(<AnalyticsDashboard />);

    // Assert
    expect(await screen.findByText("No unanswered questions yet.")).toBeInTheDocument();
    expect(screen.getByText("No questions logged yet.")).toBeInTheDocument();
    expect(screen.getByText("No citations logged yet.")).toBeInTheDocument();
    expect(screen.getByText("No documents uploaded yet.")).toBeInTheDocument();
  });
});
