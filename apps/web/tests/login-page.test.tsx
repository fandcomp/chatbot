import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import LoginPage from "@/app/login/page";

const pushMock = vi.fn();
const loginMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
}));

vi.mock("@/lib/auth-context", () => ({
  useAuth: () => ({ login: loginMock }),
}));

describe("LoginPage", () => {
  beforeEach(() => {
    pushMock.mockClear();
    loginMock.mockClear();
  });

  it("renders email and password fields", () => {
    // Arrange & Act
    render(<LoginPage />);

    // Assert
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
  });

  it("shows a validation error and does not call login for an invalid email", async () => {
    // Arrange
    const user = userEvent.setup();
    render(<LoginPage />);

    // Act
    await user.type(screen.getByLabelText(/email/i), "not-an-email");
    await user.type(screen.getByLabelText(/password/i), "supersecret123");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    // Assert
    expect(await screen.findByText(/valid email/i)).toBeInTheDocument();
    expect(loginMock).not.toHaveBeenCalled();
  });

  it("calls login and navigates home on valid submit", async () => {
    // Arrange
    loginMock.mockResolvedValueOnce(undefined);
    const user = userEvent.setup();
    render(<LoginPage />);

    // Act
    await user.type(screen.getByLabelText(/email/i), "owner@acme-corp.io");
    await user.type(screen.getByLabelText(/password/i), "supersecret123");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    // Assert
    expect(loginMock).toHaveBeenCalledWith("owner@acme-corp.io", "supersecret123");
    expect(await screen.findByRole("button", { name: /sign in/i })).toBeInTheDocument();
    expect(pushMock).toHaveBeenCalledWith("/");
  });
});
