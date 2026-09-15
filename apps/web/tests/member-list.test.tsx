import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { MemberList } from "@/components/organizations/member-list";
import { AuthProvider } from "@/lib/auth-context";
import type { Member } from "@/lib/organizations-api";

const listMembersMock = vi.fn();
const removeMemberMock = vi.fn();

vi.mock("@/lib/organizations-api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/organizations-api")>(
    "@/lib/organizations-api"
  );
  return {
    ...actual,
    organizationsApi: {
      ...actual.organizationsApi,
      listMembers: () => listMembersMock(),
      removeMember: (memberId: string) => removeMemberMock(memberId),
    },
  };
});

const SAMPLE_MEMBER: Member = {
  id: "member-1",
  user_id: "user-1",
  email: "teammate@example.com",
  full_name: "Teammate Name",
  role: "EDITOR",
  created_at: "2026-01-01T00:00:00Z",
};

function renderList() {
  return render(
    <AuthProvider>
      <MemberList />
    </AuthProvider>
  );
}

// Regression coverage for the gap audit 2026-09-15 frontend pass: removing a
// member immediately revokes their org access with no undo (short of
// re-inviting them), but the "Remove" button previously called the API on a
// single click with zero confirmation.
describe("MemberList remove confirmation", () => {
  beforeEach(() => {
    listMembersMock.mockReset();
    removeMemberMock.mockReset();
    listMembersMock.mockResolvedValue([SAMPLE_MEMBER]);
  });

  it("does not call the remove API until the user confirms", async () => {
    // Arrange
    const user = userEvent.setup();
    renderList();
    await screen.findByText("Teammate Name");

    // Act
    await user.click(screen.getByRole("button", { name: /^remove$/i }));

    // Assert
    expect(removeMemberMock).not.toHaveBeenCalled();
    expect(await screen.findByText(/remove member\?/i)).toBeInTheDocument();
  });

  it("cancelling leaves the member untouched", async () => {
    // Arrange
    const user = userEvent.setup();
    renderList();
    await screen.findByText("Teammate Name");
    await user.click(screen.getByRole("button", { name: /^remove$/i }));
    await screen.findByText(/remove member\?/i);

    // Act
    await user.click(screen.getByRole("button", { name: /cancel/i }));

    // Assert
    expect(removeMemberMock).not.toHaveBeenCalled();
    expect(screen.queryByText(/remove member\?/i)).not.toBeInTheDocument();
    expect(screen.getByText("Teammate Name")).toBeInTheDocument();
  });

  it("confirming removes the member and drops them from the list", async () => {
    // Arrange
    removeMemberMock.mockResolvedValueOnce(undefined);
    const user = userEvent.setup();
    renderList();
    await screen.findByText("Teammate Name");
    await user.click(screen.getByRole("button", { name: /^remove$/i }));
    const dialog = await screen.findByRole("dialog");

    // Act
    await user.click(within(dialog).getByRole("button", { name: /^remove$/i }));

    // Assert
    expect(removeMemberMock).toHaveBeenCalledWith("member-1");
    await waitFor(() => expect(screen.queryByText("Teammate Name")).not.toBeInTheDocument());
  });

  it("surfaces an error and keeps the member if removal fails", async () => {
    // Arrange
    removeMemberMock.mockRejectedValueOnce(new Error("boom"));
    const user = userEvent.setup();
    renderList();
    await screen.findByText("Teammate Name");
    await user.click(screen.getByRole("button", { name: /^remove$/i }));
    const dialog = await screen.findByRole("dialog");

    // Act
    await user.click(within(dialog).getByRole("button", { name: /^remove$/i }));

    // Assert
    await waitFor(() => expect(removeMemberMock).toHaveBeenCalled());
    expect(screen.getByText("Teammate Name")).toBeInTheDocument();
  });
});
