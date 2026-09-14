"use client";

import { useEffect, useState } from "react";
import type { FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api-client";
import { useAuth } from "@/lib/auth-context";
import type { OrgRole } from "@/lib/auth-context";
import { ORG_ROLE_OPTIONS, organizationsApi, type Member } from "@/lib/organizations-api";

export function MemberList() {
  const { state } = useAuth();
  const [members, setMembers] = useState<Member[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isInviting, setIsInviting] = useState(false);
  const [inviteEmail, setInviteEmail] = useState("");
  const [invitePassword, setInvitePassword] = useState("");
  const [inviteRole, setInviteRole] = useState<OrgRole>("VIEWER");

  const currentUserId = state.status === "authenticated" ? state.user.id : null;

  useEffect(() => {
    organizationsApi
      .listMembers()
      .then(setMembers)
      .catch((caught) => setError(caught instanceof ApiError ? caught.message : "Failed to load members"))
      .finally(() => setIsLoading(false));
  }, []);

  async function handleInvite(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setIsInviting(true);
    try {
      const member = await organizationsApi.createMember(inviteEmail, invitePassword, inviteRole);
      setMembers((current) => [...current, member]);
      setInviteEmail("");
      setInvitePassword("");
      setInviteRole("VIEWER");
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Failed to invite member");
    } finally {
      setIsInviting(false);
    }
  }

  async function handleRoleChange(memberId: string, role: OrgRole) {
    setError(null);
    const previous = members;
    setMembers((current) => current.map((m) => (m.id === memberId ? { ...m, role } : m)));
    try {
      await organizationsApi.updateMemberRole(memberId, role);
    } catch (caught) {
      setMembers(previous);
      setError(caught instanceof ApiError ? caught.message : "Failed to change role");
    }
  }

  async function handleRemove(memberId: string) {
    setError(null);
    try {
      await organizationsApi.removeMember(memberId);
      setMembers((current) => current.filter((m) => m.id !== memberId));
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Failed to remove member");
    }
  }

  if (isLoading) {
    return <p className="text-sm text-muted-foreground">Loading members…</p>;
  }

  return (
    <div className="flex flex-col gap-4">
      {error && <p className="text-sm text-destructive">{error}</p>}

      <ul className="flex flex-col gap-2">
        {members.map((member) => (
          <li
            key={member.id}
            className="flex items-center justify-between gap-2 rounded-md border border-input px-4 py-3"
          >
            <div>
              <p className="text-sm font-medium">{member.full_name ?? member.email}</p>
              <p className="text-xs text-muted-foreground">{member.email}</p>
            </div>
            <div className="flex items-center gap-2">
              <select
                value={member.role}
                onChange={(event) => void handleRoleChange(member.id, event.target.value as OrgRole)}
                className="h-8 rounded-md border border-input bg-background px-2 text-xs"
              >
                {ORG_ROLE_OPTIONS.map((role) => (
                  <option key={role} value={role}>
                    {role}
                  </option>
                ))}
              </select>
              <Button
                variant="ghost"
                size="sm"
                disabled={member.user_id === currentUserId}
                onClick={() => void handleRemove(member.id)}
              >
                Remove
              </Button>
            </div>
          </li>
        ))}
      </ul>

      <form
        onSubmit={(event) => void handleInvite(event)}
        className="flex flex-wrap items-end gap-2 border-t border-input pt-4"
      >
        <div className="flex flex-col gap-1">
          <label className="text-xs text-muted-foreground" htmlFor="invite-email">
            Email
          </label>
          <input
            id="invite-email"
            type="email"
            required
            value={inviteEmail}
            onChange={(event) => setInviteEmail(event.target.value)}
            className="h-8 w-56 rounded-md border border-input bg-background px-2 text-sm"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-muted-foreground" htmlFor="invite-password">
            Temporary password
          </label>
          <input
            id="invite-password"
            type="password"
            required
            minLength={8}
            value={invitePassword}
            onChange={(event) => setInvitePassword(event.target.value)}
            className="h-8 w-40 rounded-md border border-input bg-background px-2 text-sm"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-muted-foreground" htmlFor="invite-role">
            Role
          </label>
          <select
            id="invite-role"
            value={inviteRole}
            onChange={(event) => setInviteRole(event.target.value as OrgRole)}
            className="h-8 rounded-md border border-input bg-background px-2 text-sm"
          >
            {ORG_ROLE_OPTIONS.map((role) => (
              <option key={role} value={role}>
                {role}
              </option>
            ))}
          </select>
        </div>
        <Button type="submit" disabled={isInviting}>
          Invite member
        </Button>
      </form>
    </div>
  );
}
