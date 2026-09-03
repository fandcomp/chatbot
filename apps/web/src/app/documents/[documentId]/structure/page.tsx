"use client";

import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { StructureTree } from "@/components/documents/structure-tree";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api-client";
import {
  type DocumentNodeType,
  type DocumentStructure,
  type StructuralRegionType,
  documentsApi,
} from "@/lib/documents-api";

const CORRECTABLE_STATUSES = new Set(["REVIEW_REQUIRED", "PARSED", "APPROVED"]);

export default function DocumentStructurePage() {
  const params = useParams<{ documentId: string }>();
  const router = useRouter();
  const documentId = params.documentId;

  const [structure, setStructure] = useState<DocumentStructure | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isApproving, setIsApproving] = useState(false);

  const loadStructure = useCallback(() => {
    documentsApi
      .getStructure(documentId)
      .then(setStructure)
      .catch((err: unknown) => setError(err instanceof ApiError ? err.message : "Failed to load"))
      .finally(() => setIsLoading(false));
  }, [documentId]);

  useEffect(() => {
    loadStructure();
  }, [loadStructure]);

  async function handleCorrectNodeType(nodeId: string, nodeType: DocumentNodeType) {
    try {
      await documentsApi.updateNode(documentId, nodeId, { node_type: nodeType });
      loadStructure();
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : "Correction failed");
    }
  }

  async function handleCorrectRegionType(nodeId: string, regionType: StructuralRegionType) {
    try {
      await documentsApi.updateNode(documentId, nodeId, { region_type: regionType });
      loadStructure();
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : "Correction failed");
    }
  }

  async function handleApprove() {
    setIsApproving(true);
    try {
      await documentsApi.approveDocument(documentId);
      router.push("/documents");
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : "Approval failed");
    } finally {
      setIsApproving(false);
    }
  }

  if (isLoading) {
    return <p className="p-12 text-sm text-muted-foreground">Loading structure…</p>;
  }

  if (error || !structure) {
    return <p className="p-12 text-sm text-destructive">{error ?? "Structure not found."}</p>;
  }

  const canCorrect = CORRECTABLE_STATUSES.has(structure.version_status);
  const canApprove = structure.version_status === "REVIEW_REQUIRED";

  return (
    <div className="mx-auto flex min-h-screen w-full max-w-3xl flex-col gap-6 px-6 py-12">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Structure review</h1>
          <p className="text-sm text-muted-foreground">
            Status: {structure.version_status} · Aggregate confidence:{" "}
            {structure.aggregate_confidence.toFixed(2)}
          </p>
        </div>
        <Button onClick={() => void handleApprove()} disabled={!canApprove || isApproving}>
          {isApproving ? "Approving…" : "Approve document"}
        </Button>
      </div>

      <StructureTree
        nodes={structure.nodes}
        canCorrect={canCorrect}
        onCorrectNodeType={(nodeId, nodeType) => void handleCorrectNodeType(nodeId, nodeType)}
        onCorrectRegionType={(nodeId, regionType) =>
          void handleCorrectRegionType(nodeId, regionType)
        }
      />
    </div>
  );
}
