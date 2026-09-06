"use client";

import { useEffect, useState } from "react";

import { RankedList } from "@/components/analytics/ranked-list";
import { RateBar } from "@/components/analytics/rate-bar";
import { StatCard } from "@/components/analytics/stat-card";
import { Card, CardContent } from "@/components/ui/card";
import { ApiError } from "@/lib/api-client";
import {
  analyticsApi,
  type AnalyticsOverview,
  type DocumentMention,
  type KnowledgeGap,
  type TopQuestion,
} from "@/lib/analytics-api";

type State = {
  overview: AnalyticsOverview;
  knowledgeGaps: KnowledgeGap[];
  topQuestions: TopQuestion[];
  topSources: DocumentMention[];
};

function formatMs(value: number | null): string {
  if (value === null) return "—";
  return value < 1000 ? `${Math.round(value)}ms` : `${(value / 1000).toFixed(1)}s`;
}

function formatCost(value: number | null): string {
  if (value === null) return "—";
  return `$${value.toFixed(4)}`;
}

function relativeTime(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const diffHours = Math.round(diffMs / (1000 * 60 * 60));
  if (diffHours < 1) return "just now";
  if (diffHours < 24) return `${diffHours}h ago`;
  return `${Math.round(diffHours / 24)}d ago`;
}

export function AnalyticsDashboard() {
  const [state, setState] = useState<State | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    Promise.all([
      analyticsApi.getOverview(),
      analyticsApi.listKnowledgeGaps(),
      analyticsApi.listTopQuestions(),
      analyticsApi.listTopSources(),
    ])
      .then(([overview, knowledgeGaps, topQuestions, topSources]) => {
        if (!cancelled) {
          setState({ overview, knowledgeGaps, topQuestions, topSources });
        }
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setError(caught instanceof ApiError ? caught.message : "Failed to load analytics");
        }
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  if (isLoading) {
    return <p className="text-sm text-muted-foreground">Loading analytics…</p>;
  }

  if (error || !state) {
    return <p className="text-sm text-destructive">{error ?? "Failed to load analytics"}</p>;
  }

  const { overview, knowledgeGaps, topQuestions, topSources } = state;
  const answeredRate =
    overview.total_questions > 0 ? overview.answered / overview.total_questions : 0;

  return (
    <div className="flex flex-col gap-8">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <StatCard
          size="hero"
          label="Answered"
          value={`${Math.round(answeredRate * 100)}%`}
          sublabel={`of ${overview.total_questions} question${overview.total_questions === 1 ? "" : "s"}`}
        />
        <StatCard
          size="hero"
          label="Insufficient Evidence"
          value={String(overview.insufficient_evidence)}
          sublabel="questions the knowledge base couldn't answer"
          tone="destructive"
        />
      </div>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatCard label="Avg Latency" value={formatMs(overview.avg_latency_ms)} />
        <StatCard label="P95 Latency" value={formatMs(overview.p95_latency_ms)} />
        <StatCard label="Avg Cost / Query" value={formatCost(overview.avg_cost_usd)} />
        <StatCard
          label="Feedback"
          value={`${overview.thumbs_up} / ${overview.thumbs_down}`}
          sublabel="thumbs up / down"
        />
      </div>

      <Card>
        <CardContent className="grid grid-cols-1 gap-6 sm:grid-cols-3">
          <RateBar label="Citation Coverage" fraction={overview.citation_coverage} />
          <RateBar label="Retrieval Success" fraction={overview.retrieval_success} />
          <RateBar label="Cache Hit Rate" fraction={overview.cache_hit_rate} />
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 gap-8 md:grid-cols-2">
        <RankedList
          title="Top Topics"
          items={topQuestions.map((q) => ({
            key: q.query,
            label: q.query,
            count: q.frequency,
            meta: relativeTime(q.last_asked_at),
          }))}
          emptyMessage="No questions logged yet."
          countLabel="asks"
        />
        <RankedList
          title="Top Documents"
          items={topSources.map((s) => ({
            key: s.document_id,
            label: s.document_title,
            count: s.citation_count,
          }))}
          emptyMessage="No citations logged yet."
          countLabel="citations"
        />
      </div>

      <RankedList
        title="Knowledge Gaps"
        items={knowledgeGaps.map((gap) => ({
          key: gap.query,
          label: gap.query,
          count: gap.frequency,
          meta: relativeTime(gap.last_asked_at),
        }))}
        emptyMessage="No unanswered questions yet."
        countLabel="asks"
      />
    </div>
  );
}
