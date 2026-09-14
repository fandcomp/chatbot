import { apiClient } from "@/lib/api-client";
import type { OrgRole } from "@/lib/auth-context";

export type Member = {
  id: string;
  user_id: string;
  email: string;
  full_name: string | null;
  role: OrgRole;
  created_at: string;
};

// Ordered least to most privileged, for the role-select control.
export const ORG_ROLE_OPTIONS: OrgRole[] = ["VIEWER", "EDITOR", "ADMIN", "OWNER"];

export const organizationsApi = {
  listMembers: () => apiClient.get<Member[]>("/organizations/members"),
  createMember: (email: string, password: string, role: OrgRole, fullName?: string) =>
    apiClient.post<Member>("/organizations/members", {
      email,
      password,
      role,
      full_name: fullName || null,
    }),
  updateMemberRole: (memberId: string, role: OrgRole) =>
    apiClient.patch<Member>(`/organizations/members/${memberId}`, { role }),
  removeMember: (memberId: string) => apiClient.delete<void>(`/organizations/members/${memberId}`),
};
