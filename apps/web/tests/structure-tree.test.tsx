import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { StructureTree } from "@/components/documents/structure-tree";
import type { StructureNode } from "@/lib/documents-api";

function makeNode(overrides: Partial<StructureNode>): StructureNode {
  return {
    id: "node-1",
    region_id: "region-1",
    parent_id: null,
    node_type: "PARAGRAPH",
    semantic_role: null,
    label: null,
    title: null,
    text: "some text",
    number_raw: null,
    number_normalized: null,
    depth: 0,
    sequence_number: 0,
    page_start: 1,
    page_end: 1,
    confidence: 0.95,
    structural_path_json: [],
    structural_path_text: null,
    structural_depth: 0,
    chapter_number: null,
    article_number: null,
    clause_number: null,
    letter_number: null,
    appendix_number: null,
    ...overrides,
  };
}

describe("StructureTree", () => {
  it("shows a message when there is nothing to review", () => {
    render(
      <StructureTree
        nodes={[]}
        canCorrect={false}
        onCorrectNodeType={vi.fn()}
        onCorrectRegionType={vi.fn()}
      />
    );

    expect(screen.getByText(/no structure to review/i)).toBeInTheDocument();
  });

  it("renders a chapter and its nested article using their structural path labels", () => {
    const chapter = makeNode({
      id: "chapter-1",
      node_type: "CHAPTER",
      structural_path_text: "BAB III",
    });
    const article = makeNode({
      id: "article-1",
      parent_id: "chapter-1",
      node_type: "ARTICLE",
      structural_path_text: "BAB III > Pasal 20",
    });

    render(
      <StructureTree
        nodes={[chapter, article]}
        canCorrect={false}
        onCorrectNodeType={vi.fn()}
        onCorrectRegionType={vi.fn()}
      />
    );

    expect(screen.getByText("BAB III")).toBeInTheDocument();
    expect(screen.getByText("BAB III > Pasal 20")).toBeInTheDocument();
  });

  it("flags a low-confidence node", () => {
    const node = makeNode({ confidence: 0.4, title: "Suspicious paragraph" });

    render(
      <StructureTree
        nodes={[node]}
        canCorrect={false}
        onCorrectNodeType={vi.fn()}
        onCorrectRegionType={vi.fn()}
      />
    );

    expect(screen.getByText(/low confidence/i)).toBeInTheDocument();
  });

  it("does not show correction controls when canCorrect is false", () => {
    const node = makeNode({ title: "A node" });

    render(
      <StructureTree
        nodes={[node]}
        canCorrect={false}
        onCorrectNodeType={vi.fn()}
        onCorrectRegionType={vi.fn()}
      />
    );

    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  });

  it("calls onCorrectNodeType when an admin reassigns a node's type", async () => {
    const user = userEvent.setup();
    const onCorrectNodeType = vi.fn();
    const node = makeNode({ id: "node-42", title: "Should be an Article", node_type: "PARAGRAPH" });

    render(
      <StructureTree
        nodes={[node]}
        canCorrect
        onCorrectNodeType={onCorrectNodeType}
        onCorrectRegionType={vi.fn()}
      />
    );

    const [typeSelect] = screen.getAllByRole("combobox");
    await user.selectOptions(typeSelect, "ARTICLE");

    expect(onCorrectNodeType).toHaveBeenCalledWith("node-42", "ARTICLE");
  });
});
