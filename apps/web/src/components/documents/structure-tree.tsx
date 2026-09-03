"use client";

import { useMemo, useState } from "react";

import type { DocumentNodeType, StructuralRegionType, StructureNode } from "@/lib/documents-api";

const NODE_TYPES: DocumentNodeType[] = [
  "CHAPTER",
  "PART",
  "SECTION",
  "SUBSECTION",
  "NUMBERED_SECTION",
  "NUMBERED_ITEM",
  "LETTER_ITEM",
  "ROMAN_ITEM",
  "NESTED_ITEM",
  "ARTICLE",
  "CLAUSE",
  "DECISION_ITEM",
  "PARAGRAPH",
  "LIST",
  "LIST_ITEM",
  "TABLE",
  "APPENDIX",
  "FIGURE",
  "UNKNOWN_BLOCK",
];

const REGION_TYPES: StructuralRegionType[] = [
  "COVER",
  "TABLE_OF_CONTENTS",
  "LEGAL_PREAMBLE",
  "LEGAL_BODY",
  "LEGAL_DECISION",
  "TECHNICAL_GUIDELINE",
  "PROCEDURAL_GUIDELINE",
  "NUMBERED_MANUAL",
  "SOP",
  "APPENDIX",
  "FREEFORM_SECTION",
];

const LOW_CONFIDENCE_THRESHOLD = 0.7;

type Props = {
  nodes: StructureNode[];
  canCorrect: boolean;
  onCorrectNodeType: (nodeId: string, nodeType: DocumentNodeType) => void;
  onCorrectRegionType: (nodeId: string, regionType: StructuralRegionType) => void;
};

export function StructureTree({ nodes, canCorrect, onCorrectNodeType, onCorrectRegionType }: Props) {
  const childrenByParent = useMemo(() => {
    const map = new Map<string | null, StructureNode[]>();
    for (const node of nodes) {
      const key = node.parent_id;
      const siblings = map.get(key) ?? [];
      siblings.push(node);
      map.set(key, siblings);
    }
    for (const siblings of map.values()) {
      siblings.sort((a, b) => a.sequence_number - b.sequence_number);
    }
    return map;
  }, [nodes]);

  const roots = childrenByParent.get(null) ?? [];

  if (roots.length === 0) {
    return <p className="text-sm text-muted-foreground">No structure to review yet.</p>;
  }

  return (
    <ul className="flex flex-col gap-1">
      {roots.map((node) => (
        <TreeNode
          key={node.id}
          node={node}
          childrenByParent={childrenByParent}
          canCorrect={canCorrect}
          onCorrectNodeType={onCorrectNodeType}
          onCorrectRegionType={onCorrectRegionType}
        />
      ))}
    </ul>
  );
}

type TreeNodeProps = {
  node: StructureNode;
  childrenByParent: Map<string | null, StructureNode[]>;
  canCorrect: boolean;
  onCorrectNodeType: (nodeId: string, nodeType: DocumentNodeType) => void;
  onCorrectRegionType: (nodeId: string, regionType: StructuralRegionType) => void;
};

function TreeNode({ node, childrenByParent, canCorrect, onCorrectNodeType, onCorrectRegionType }: TreeNodeProps) {
  const [isExpanded, setIsExpanded] = useState(true);
  const children = childrenByParent.get(node.id) ?? [];
  const isLowConfidence = node.confidence < LOW_CONFIDENCE_THRESHOLD;
  const displayLabel = node.structural_path_text ?? node.label ?? node.title ?? node.node_type;

  return (
    <li>
      <div className="flex flex-wrap items-center gap-2 rounded-md px-2 py-1.5 hover:bg-muted/50">
        {children.length > 0 ? (
          <button
            type="button"
            onClick={() => setIsExpanded((current) => !current)}
            className="w-4 text-xs text-muted-foreground"
            aria-label={isExpanded ? "Collapse" : "Expand"}
          >
            {isExpanded ? "▾" : "▸"}
          </button>
        ) : (
          <span className="w-4" />
        )}

        <span className="rounded bg-secondary px-1.5 py-0.5 text-xs font-medium">
          {node.node_type}
        </span>

        {isLowConfidence && (
          <span
            className="rounded bg-destructive/10 px-1.5 py-0.5 text-xs font-medium text-destructive"
            title={`Confidence ${node.confidence.toFixed(2)}`}
          >
            low confidence
          </span>
        )}

        <span className="text-sm">{displayLabel}</span>

        {canCorrect && (
          <div className="ml-auto flex items-center gap-2">
            <select
              className="rounded border border-input bg-background px-1 py-0.5 text-xs"
              value={node.node_type}
              onChange={(event) =>
                onCorrectNodeType(node.id, event.target.value as DocumentNodeType)
              }
            >
              {NODE_TYPES.map((type) => (
                <option key={type} value={type}>
                  {type}
                </option>
              ))}
            </select>
            <select
              className="rounded border border-input bg-background px-1 py-0.5 text-xs"
              defaultValue=""
              onChange={(event) => {
                if (event.target.value) {
                  onCorrectRegionType(node.id, event.target.value as StructuralRegionType);
                  event.target.value = "";
                }
              }}
            >
              <option value="" disabled>
                Fix region…
              </option>
              {REGION_TYPES.map((type) => (
                <option key={type} value={type}>
                  {type}
                </option>
              ))}
            </select>
          </div>
        )}
      </div>

      {isExpanded && children.length > 0 && (
        <ul className="ml-6 flex flex-col gap-1 border-l border-input pl-2">
          {children.map((child) => (
            <TreeNode
              key={child.id}
              node={child}
              childrenByParent={childrenByParent}
              canCorrect={canCorrect}
              onCorrectNodeType={onCorrectNodeType}
              onCorrectRegionType={onCorrectRegionType}
            />
          ))}
        </ul>
      )}
    </li>
  );
}
