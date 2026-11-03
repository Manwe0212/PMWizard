"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import type { ProjectMemberRole } from "@/lib/types";

type Invitation = {
  id: string;
  email: string;
  role: ProjectMemberRole;
  status: "pending" | "accepted" | "revoked" | "expired";
  invited_by: string;
  created_at: string;
  expires_at: string;
  delivery_method: "manual" | "email";
  delivery_status: "not_applicable" | "sent";
  delivered_at: string | null;
};

type InvitationPage = {
  items: Invitation[];
  count: number;
  next_offset: number | null;
  email_available: boolean;
  strict_email_only: boolean;
};

type Created = { invitation: Invitation; token: string | null };

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { ...init, cache: "no-store" });
  const body = response.status === 204 ? null : await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(
      typeof body?.detail === "string" ? body.detail : "Invitation request failed.",
    );
  }
  return body as T;
}

export function InvitationWorkspace() {
  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [offset, setOffset] = useState<number | null>(null);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<ProjectMemberRole>("viewer");
  const [deliveryMethod, setDeliveryMethod] = useState<"manual" | "email">("email");
  const [emailAvailable, setEmailAvailable] = useState(false);
  const [strictEmailOnly, setStrictEmailOnly] = useState(false);
  const [newLink, setNewLink] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async (next: number | null = null) => {
    setLoading(true);
    try {
      const page = await requestJson<InvitationPage>(
        `/api/invitations?limit=50&offset=${next ?? 0}`,
      );
      setInvitations((prev) =>
        next === null ? page.items : [
          ...prev,
          ...page.items.filter((item) => !prev.some((old) => old.id === item.id)),
        ],
      );
      setOffset(page.next_offset);
      setEmailAvailable(page.email_available);
      setStrictEmailOnly(page.strict_email_only);
      setDeliveryMethod((current) => page.strict_email_only
        ? "email"
        : !page.email_available ? "manual" : current);
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Cannot load invitations.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setNewLink(null);
    setNotice(null);
    setError(null);
    setBusy(true);
    try {
      const data = await requestJson<Created>("/api/invitations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email.trim(), role, delivery_method: deliveryMethod }),
      });
      // The token stays in component memory; the API never persists its value.
      setNewLink(data.token
        ? `${window.location.origin}/invite#token=${encodeURIComponent(data.token)}`
        : null);
      setEmail("");
      setRole("viewer");
      setNotice(data.invitation.delivery_method === "email"
        ? "Invitation email submitted securely. The link was not exposed to your browser."
        : "Invitation created. Copy the link now; it cannot be retrieved later.");
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to create invitation.");
    } finally {
      setBusy(false);
    }
  }

  async function revoke(id: string) {
    if (busy) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await requestJson<null>(`/api/invitations/${encodeURIComponent(id)}`, {
        method: "DELETE",
      });
      setNotice("Invitation revoked.");
      setNewLink(null);
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to revoke invitation.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="memberInvites" aria-label="Invite new PMWizard users">
      <div className="memberListHeader">
        <div>
          <h3>New-user invitations</h3>
          <p>Issue a seven-day, one-time signup link for someone without a PMWizard account.</p>
        </div>
        <button className="secondaryButton" type="button" onClick={() => void load()} disabled={loading}>
          Refresh
        </button>
      </div>
      <p className="memberPermissionNotice">
        Email delivery requires the server to have verified-TLS SMTP and a public
        HTTPS address configured. Manual links remain available for development
        and are not email-verified. Anyone holding a valid link can activate its
        account. Reviewer has some operational privileges in V0.
      </p>
      <form className="memberAddForm" onSubmit={create}>
        <div><h3>Create an invitation</h3><p>For accounts not yet registered in this workspace.</p></div>
        <label>
          Recipient email
          <input
            type="email"
            value={email}
            placeholder="new-teammate@example.com"
            maxLength={320}
            onChange={(event) => setEmail(event.target.value)}
            required
          />
        </label>
        <label>
          Project role
          <select value={role} onChange={(event) => setRole(event.target.value as ProjectMemberRole)}>
            <option value="viewer">Viewer</option>
            <option value="reviewer">Reviewer</option>
            <option value="project_manager">Project manager</option>
          </select>
        </label>
        <label>
          Delivery
          <select value={deliveryMethod} disabled={loading} onChange={(event) => setDeliveryMethod(event.target.value as "manual" | "email")}>
            <option value="email" disabled={!emailAvailable}>Send by email (verified inbox){!emailAvailable ? " — not configured" : ""}</option>
            <option value="manual" disabled={strictEmailOnly}>Copy link manually (unverified){strictEmailOnly ? " — disabled by policy" : ""}</option>
          </select>
        </label>
        <button className="primaryButton" type="submit" disabled={busy || loading || !email.trim()}>
          {busy ? "Creating…" : deliveryMethod === "email" ? "Send invitation" : "Create invite"}
        </button>
      </form>

      {newLink && (
        <div className="memberInviteLink" role="status">
          <strong>One-time link — copy and share securely</strong>
          <input aria-label="One-time invitation URL" readOnly value={newLink} onFocus={(event) => event.target.select()} />
          <div className="memberInviteLinkActions">
            <button
              className="primaryButton"
              type="button"
              onClick={async () => {
                try {
                  await navigator.clipboard.writeText(newLink);
                  setNotice("Invitation link copied.");
                } catch {
                  setError("Clipboard access unavailable. Select and copy the link above.");
                }
              }}
            >
              Copy link
            </button>
            <button className="secondaryButton" type="button" onClick={() => setNewLink(null)}>
              Clear from screen
            </button>
          </div>
        </div>
      )}
      {notice && <p className="memberNotice" role="status">{notice}</p>}
      {error && <div className="activityError" role="alert">{error}</div>}

      <div className="memberListHeader">
        <h3>Invitation history</h3>
        <span>{invitations.length} loaded</span>
      </div>
      {invitations.length === 0 && !loading && <p>No invitations issued for this project.</p>}
      <div className="memberRows">
        {invitations.map((item) => (
          <div className="memberRow" key={item.id}>
            <div className="memberIdentity">
              <strong>{item.email}</strong>
              <span>{item.role.replaceAll("_", " ")} · {item.status} · {item.delivery_method === "email" ? "email verified on acceptance" : "manual/unverified"}</span>
              <small>Expires {new Date(item.expires_at).toLocaleString()}</small>
            </div>
            {item.status === "pending" && (
              <button className="secondaryButton" type="button" disabled={busy} onClick={() => void revoke(item.id)}>
                Revoke
              </button>
            )}
          </div>
        ))}
      </div>
      {offset !== null && (
        <div className="activityLoadMore">
          <button className="secondaryButton" type="button" disabled={loading} onClick={() => void load(offset)}>
            Load more invitations
          </button>
        </div>
      )}
    </section>
  );
}
