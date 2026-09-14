"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api-client";
import type { DocumentRelationType } from "@/lib/chat-schemas";
import {
  CREATABLE_RELATION_TYPES,
  documentsApi,
  type DocumentItem,
  type DocumentRelation,
} from "@/lib/documents-api";

type Props = {
  documentId: string;
  otherDocuments: DocumentItem[];
};

// spec §21 — admin view of a document's curated relations (create/list/
// delete), the frontend half of apps/api/app/documents/router.py's
// create_relation/list_relations/delete_relation. Without this, the
// AdaptiveCitationService-built citation warning has nothing to ever show,
// since no admin has a way to create a relation in the first place.
export function DocumentRelationsPanel({ documentId, otherDocuments }: Props) {
  const [relations, setRelations] = useState<DocumentRelation[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [targetDocumentId, setTargetDocumentId] = useState(otherDocuments[0]?.id ?? "");
  const [relationType, setRelationType] = useState<DocumentRelationType>(
    CREATABLE_RELATION_TYPES[0]
  );
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    documentsApi
      .listRelations(documentId)
      .then(setRelations)
      .catch((caught) => setError(caught instanceof ApiError ? caught.message : "Failed to load relations"))
      .finally(() => setIsLoading(false));
  }, [documentId]);

  async function handleCreate() {
    if (!targetDocumentId) return;
    setError(null);
    setIsSubmitting(true);
    try {
      const relation = await documentsApi.createRelation(documentId, targetDocumentId, relationType);
      setRelations((current) => [...current, relation]);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Failed to create relation");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleDelete(relationId: string) {
    setError(null);
    try {
      await documentsApi.deleteRelation(relationId);
      setRelations((current) => current.filter((relation) => relation.id !== relationId));
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Failed to delete relation");
    }
  }

  return (
    <div className="flex flex-col gap-2 border-t border-input pt-3">
      {error && <p className="text-xs text-destructive">{error}</p>}
      {isLoading ? (
        <p className="text-xs text-muted-foreground">Loading relations…</p>
      ) : relations.length === 0 ? (
        <p className="text-xs text-muted-foreground">No relations to other documents yet.</p>
      ) : (
        relations.map((relation) => {
          const isFromThisDocument = relation.from_document_id === documentId;
          const otherTitle = isFromThisDocument
            ? relation.to_document_title
            : relation.from_document_title;
          return (
            <div key={relation.id} className="flex items-center justify-between text-xs">
              <span className="text-muted-foreground">
                {isFromThisDocument ? "This document" : otherTitle}{" "}
                <span className="font-medium">{relation.relation_type}</span>{" "}
                {isFromThisDocument ? otherTitle : "this document"}
              </span>
              {relation.relation_type !== "SUPERSEDED_BY" && (
                <Button variant="ghost" size="sm" onClick={() => void handleDelete(relation.id)}>
                  Remove
                </Button>
              )}
            </div>
          );
        })
      )}
      {otherDocuments.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 pt-1">
          <select
            value={relationType}
            onChange={(event) => setRelationType(event.target.value as DocumentRelationType)}
            className="h-7 rounded-md border border-input bg-background px-2 text-xs"
          >
            {CREATABLE_RELATION_TYPES.map((type) => (
              <option key={type} value={type}>
                {type}
              </option>
            ))}
          </select>
          <select
            value={targetDocumentId}
            onChange={(event) => setTargetDocumentId(event.target.value)}
            className="h-7 max-w-40 rounded-md border border-input bg-background px-2 text-xs"
          >
            {otherDocuments.map((document) => (
              <option key={document.id} value={document.id}>
                {document.title}
              </option>
            ))}
          </select>
          <Button
            variant="outline"
            size="sm"
            disabled={isSubmitting || !targetDocumentId}
            onClick={() => void handleCreate()}
          >
            Add relation
          </Button>
        </div>
      )}
    </div>
  );
}
