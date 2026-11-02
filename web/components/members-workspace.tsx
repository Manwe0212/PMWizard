"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";

import type {
  ProjectMember,
  ProjectMemberRole,
  ProjectMembersPage,
} from "@/lib/types";

const ROLES: { value: ProjectMemberRole; label: string; detail: string }[] = [
  { value: "viewer", label: "Viewer", detail: "Read-only access" },
  { value: "reviewer", label: "Reviewer", detail: "Read and human-review access" },
  {
    value: "project_manager",
    label: "Project manager",
    detail: "Read, review, and manage members",
  },
];

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, { ...init, cache: "no-store" });
  const payload = response.status === 204
    ? null
    : await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(
      typeof payload?.detail === "string"
        ? payload.detail
        : `Membership request failed (${response.status})`,
    );
  }
  return payload as T;
}

export function MembersWorkspace({ currentUserId }: { currentUserId: string }) {
  const [members, setMembers] = useState<ProjectMember[]>([]);
  const [nextOffset, setNextOffset] = useState<number | null>(null);
  const [email, setEmail] = useState("");
  const [newRole, setNewRole] = useState<ProjectMemberRole>("viewer");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [confirmRemove, setConfirmRemove] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const loadMembers = useCallback(async (offset: number | null = null) => {
    setLoading(true);
    try {
      const data = await requestJson<ProjectMembersPage>(
        `/api/members?limit=50&offset=${offset ?? 0}`,
      );
      setMembers((current) =>
        offset === null
          ? data.items
          : [
              ...current,
              ...data.items.filter(
                (member) => !current.some((existing) => existing.user_id === member.user_id),
              ),
            ],
      );
      setNextOffset(data.next_offset);
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to load members.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadMembers();
  }, [loadMembers]);

  async function addMember(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setBusy("add");
    setNotice(null);
    setError(null);
    try {
      await requestJson<ProjectMember>("/api/members", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email.trim(), role: newRole }),
      });
      setEmail("");
      setNewRole("viewer");
      setNotice("Existing workspace account added to this project.");
      await loadMembers();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to add member.");
    } finally {
      setBusy(null);
    }
  }

  async function updateRole(userId: string, role: ProjectMemberRole) {
    if (busy) return;
    setBusy(userId);
    setError(null);
    setNotice(null);
    try {
      await requestJson<ProjectMember>(`/api/members/${encodeURIComponent(userId)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ role }),
      });
      setNotice("Project role updated. Permissions take effect on the next API request.");
      await loadMembers();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to update member.");
    } finally {
      setBusy(null);
    }
  }

  async function removeMember(userId: string) {
    if (busy) return;
    setBusy(userId);
    setError(null);
    setNotice(null);
    try {
      await requestJson<null>(`/api/members/${encodeURIComponent(userId)}`, {
        method: "DELETE",
      });
      setConfirmRemove(null);
      setNotice("Member removed. Their project access is revoked.");
      await loadMembers();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to remove member.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <section className="memberWorkspace" aria-label="Project member management">
      <div className="memberIntro">
        <div>
          <span className="eyebrow">Project governance</span>
          <h2>Members &amp; roles</h2>
          <p>
            Invite an existing PMWizard account by email to this project. Access stays
            within the selected workspace and project.
          </p>
        </div>
        <button
          className="secondaryButton"
          type="button"
          disabled={loading}
          onClick={() => void loadMembers()}
        >
          Refresh
        </button>
      </div>

      <div className="memberRoleLegend" aria-label="Available role permissions">
        {ROLES.map((role) => (
          <div key={role.value}>
            <strong>{role.label}</strong>
            <span>{role.detail}</span>
          </div>
        ))}
      </div>

      <form className="memberAddForm" onSubmit={addMember}>
        <div>
          <h3>Add existing member</h3>
          <p>Accounts must already exist within this tenant; this does not send an email invitation.</p>
        </div>
        <label>
          Account email
          <input
            type="email"
            autoComplete="off"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="teammate@example.com"
            maxLength={320}
            required
          />
        </label>
        <label>
          Project role
          <select
            value={newRole}
            onChange={(event) => setNewRole(event.target.value as ProjectMemberRole)}
          >
            {ROLES.map((role) => (
              <option key={role.value} value={role.value}>{role.label}</option>
            ))}
          </select>
        </label>
        <button className="primaryButton" type="submit" disabled={!email.trim() || busy !== null}>
          {busy === "add" ? "Adding…" : "Add member"}
        </button>
      </form>

      {error && <div className="activityError" role="alert">{error}</div>}
      {notice && <p className="memberNotice" role="status">{notice}</p>}

      <div className="memberListHeader">
        <h3>Project members</h3>
        <span>{members.length} loaded</span>
      </div>
      {loading && members.length === 0 && <p>Loading members…</p>}
      {!loading && members.length === 0 && !error && <p>No members found.</p>}
      <div className="memberRows">
        {members.map((member) => {
          const protectedMember =
            member.is_owner || member.user_id === currentUserId;
          return (
            <div className="memberRow" key={member.user_id}>
              <div className="memberIdentity">
                <strong>{member.display_name}</strong>
                <span>{member.email}</span>
                <small>
                  {member.is_owner ? "Original owner · " : ""}
                  {!member.is_active ? "Inactive · " : ""}
                  Joined {new Date(member.joined_at).toLocaleDateString()}
                </small>
              </div>
              <div className="memberActions">
                <label>
                  Role
                  <select
                    value={member.role}
                    disabled={protectedMember || busy !== null}
                    aria-label={`Role for ${member.display_name}`}
                    onChange={(event) =>
                      void updateRole(member.user_id, event.target.value as ProjectMemberRole)
                    }
                  >
                    {ROLES.map((role) => (
                      <option key={role.value} value={role.value}>{role.label}</option>
                    ))}
                  </select>
                </label>
                {!protectedMember && (
                  confirmRemove === member.user_id ? (
                    <div className="memberConfirm">
                      <span>Revoke access?</span>
                      <button
                        className="dangerButton"
                        type="button"
                        disabled={busy !== null}
                        onClick={() => void removeMember(member.user_id)}
                      >
                        Confirm
                      </button>
                      <button className="secondaryButton" type="button" onClick={() => setConfirmRemove(null)}>
                        Cancel
                      </button>
                    </div>
                  ) : (
                    <button
                      className="secondaryButton"
                      type="button"
                      disabled={busy !== null}
                      onClick={() => setConfirmRemove(member.user_id)}
                    >
                      Remove
                    </button>
                  )
                )}
                {protectedMember && <small>Protected membership</small>}
              </div>
            </div>
          );
        })}
      </div>
      {nextOffset !== null && (
        <div className="activityLoadMore">
          <button
            className="secondaryButton"
            type="button"
            disabled={loading || busy !== null}
            onClick={() => void loadMembers(nextOffset)}
          >
            {loading ? "Loading…" : "Load more members"}
          </button>
        </div>
      )}
    </section>
  );
}
