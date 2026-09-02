"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";

import { apiClient } from "@/lib/api-client";

type OrgRole = "OWNER" | "ADMIN" | "EDITOR" | "VIEWER";

type User = {
  id: string;
  email: string;
  full_name: string | null;
  is_active: boolean;
};

type MeResponse = {
  user: User;
  organization_id: string;
  role: OrgRole;
};

type AuthState =
  | { status: "loading" }
  | { status: "authenticated"; user: User; organizationId: string; role: OrgRole }
  | { status: "unauthenticated" };

type AuthContextValue = {
  state: AuthState;
  login: (email: string, password: string) => Promise<void>;
  register: (
    organizationName: string,
    email: string,
    password: string,
    fullName?: string
  ) => Promise<void>;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

function toAuthenticated(me: MeResponse): AuthState {
  return {
    status: "authenticated",
    user: me.user,
    organizationId: me.organization_id,
    role: me.role,
  };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;

    apiClient
      .get<MeResponse>("/auth/me")
      .then((me) => {
        if (!cancelled) setState(toAuthenticated(me));
      })
      .catch(() => {
        if (!cancelled) setState({ status: "unauthenticated" });
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const me = await apiClient.post<MeResponse>("/auth/login", { email, password });
    setState(toAuthenticated(me));
  }, []);

  const register = useCallback(
    async (organizationName: string, email: string, password: string, fullName?: string) => {
      const me = await apiClient.post<MeResponse>("/auth/register", {
        organization_name: organizationName,
        email,
        password,
        full_name: fullName || null,
      });
      setState(toAuthenticated(me));
    },
    []
  );

  const logout = useCallback(async () => {
    await apiClient.post<void>("/auth/logout");
    setState({ status: "unauthenticated" });
  }, []);

  return (
    <AuthContext.Provider value={{ state, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
