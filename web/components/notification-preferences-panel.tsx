"use client";

import { useCallback, useEffect, useState } from "react";

import type {
  AttentionCategory,
  AttentionSeverity,
  NotificationWorkspaceSnapshot,
} from "@/lib/types";

const CATEGORIES: Array<{ value: AttentionCategory; label: string }> = [
  { value: "health", label: "Health" },
  { value: "execution", label: "Execution" },
  { value: "raid", label: "RAID" },
  { value: "decision", label: "Decisions" },
  { value: "source", label: "Sources" },
  { value: "automation", label: "Automations" },
  { value: "review", label: "Inbox review" },
];

const CADENCES = [
  { value: 15, label: "Every 15 minutes" },
  { value: 60, label: "Hourly" },
  { value: 240, label: "Every 4 hours" },
  { value: 1440, label: "Daily" },
];

function formatDate(value: string | null): string {
  if (!value) return "Never";
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

async function readJson<T>(response: Response): Promise<T> {
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(
      typeof payload?.detail === "string"
        ? payload.detail
        : `Notification request failed (${response.status})`,
    );
  }
  return payload as T;
}

export function NotificationPreferencesPanel() {
  const [snapshot, setSnapshot] =
    useState<NotificationWorkspaceSnapshot | null>(null);
  const [enabled, setEnabled] = useState(false);
  const [emailEnabled, setEmailEnabled] = useState(false);
  const [teamsEnabled, setTeamsEnabled] = useState(false);
  const [teamsRef, setTeamsRef] = useState("");
  const [minimumSeverity, setMinimumSeverity] =
    useState<AttentionSeverity>("warning");
  const [categories, setCategories] = useState<AttentionCategory[]>(
    CATEGORIES.map((item) => item.value),
  );
  const [intervalMinutes, setIntervalMinutes] = useState(60);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const hydrate = useCallback((next: NotificationWorkspaceSnapshot) => {
    const preference = next.preference;
    setSnapshot(next);
    setEnabled(preference.enabled);
    setEmailEnabled(preference.email_enabled);
    setTeamsEnabled(preference.teams_enabled);
    setTeamsRef("");
    setMinimumSeverity(preference.minimum_severity);
    setCategories(preference.categories);
    setIntervalMinutes(preference.interval_minutes);
  }, []);

  const load = useCallback(async () => {
    setError(null);
    try {
      hydrate(
        await readJson<NotificationWorkspaceSnapshot>(
          await fetch("/api/notifications", { cache: "no-store" }),
        ),
      );
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Unable to load notification preferences.",
      );
    }
  }, [hydrate]);

  useEffect(() => {
    void load();
  }, [load]);

  async function save({ clearTeams = false }: { clearTeams?: boolean } = {}) {
    setBusy(true);
    setError(null);
    try {
      const nextTeamsEnabled = clearTeams ? false : teamsEnabled;
      const payload: Record<string, unknown> = {
        enabled: clearTeams ? enabled && emailEnabled : enabled,
        email_enabled: emailEnabled,
        teams_enabled: nextTeamsEnabled,
        clear_teams_webhook: clearTeams,
        minimum_severity: minimumSeverity,
        categories,
        interval_minutes: intervalMinutes,
      };
      if (!clearTeams && teamsRef.trim()) {
        payload.teams_webhook_ref = teamsRef.trim();
      }

      const result = await readJson<NotificationWorkspaceSnapshot>(
        await fetch("/api/notifications", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        }),
      );
      hydrate(result);
      if (clearTeams) {
        setTeamsEnabled(false);
      }
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Unable to save notification preferences.",
      );
    } finally {
      setBusy(false);
    }
  }

  function toggleCategory(category: AttentionCategory) {
    setCategories((current) => {
      if (current.includes(category)) {
        if (current.length === 1) return current;
        return current.filter((item) => item !== category);
      }
      return [...current, category];
    });
  }

  const preference = snapshot?.preference;

  return (
    <section className="notificationPanel">
      <button
        className="notificationPanelToggle"
        type="button"
        onClick={() => setOpen((current) => !current)}
      >
        <div>
          <span className="memoryTruthBadge">Outbound delivery</span>
          <strong>Notification preferences</strong>
          <small>
            {preference?.enabled
              ? `Active · ${preference.email_enabled ? "Email " : ""}${
                  preference.teams_enabled ? "Teams" : ""
                }`
              : "Off · Attention Center remains available in-app"}
          </small>
        </div>
        <span>{open ? "−" : "+"}</span>
      </button>

      {open && (
        <div className="notificationPanelBody">
          <div className="notificationToggleRow">
            <div>
              <strong>External delivery</strong>
              <span>
                Deliver only new or changed unread Attention signal versions.
              </span>
            </div>
            <label className="automationToggle">
              <input
                type="checkbox"
                checked={enabled}
                onChange={(event) => setEnabled(event.target.checked)}
              />
              <span>{enabled ? "Enabled" : "Disabled"}</span>
            </label>
          </div>

          <div className="notificationChannelGrid">
            <div className={`notificationChannelCard ${emailEnabled ? "active" : ""}`}>
              <div>
                <span className="sourceTag">Email</span>
                <strong>{preference?.email_destination ?? "Account email"}</strong>
                <small>
                  Destination is locked to the authenticated PMWizard account.
                </small>
              </div>
              <label className="automationToggle">
                <input
                  type="checkbox"
                  checked={emailEnabled}
                  onChange={(event) => setEmailEnabled(event.target.checked)}
                />
                <span>{emailEnabled ? "On" : "Off"}</span>
              </label>
            </div>

            <div className={`notificationChannelCard ${teamsEnabled ? "active" : ""}`}>
              <div>
                <span className="sourceTag">Microsoft Teams</span>
                <strong>
                  {preference?.teams_webhook_configured
                    ? "Webhook alias configured"
                    : "No webhook alias"}
                </strong>
                <small>The real webhook stays in the worker secret provider.</small>
              </div>
              <label className="automationToggle">
                <input
                  type="checkbox"
                  checked={teamsEnabled}
                  onChange={(event) => setTeamsEnabled(event.target.checked)}
                />
                <span>{teamsEnabled ? "On" : "Off"}</span>
              </label>
              <input
                className="notificationSecretInput"
                value={teamsRef}
                onChange={(event) => setTeamsRef(event.target.value)}
                placeholder={
                  preference?.teams_webhook_configured
                    ? "Leave blank to keep current binding"
                    : "env:TEAMS_PROJECT_ALERTS"
                }
              />
              {preference?.teams_webhook_configured && (
                <button
                  className="textButton"
                  type="button"
                  disabled={busy}
                  onClick={() => void save({ clearTeams: true })}
                >
                  Clear Teams binding
                </button>
              )}
            </div>
          </div>

          <div className="notificationRuleGrid">
            <label>
              Minimum severity
              <select
                value={minimumSeverity}
                onChange={(event) =>
                  setMinimumSeverity(event.target.value as AttentionSeverity)
                }
              >
                <option value="critical">Critical only</option>
                <option value="warning">Warning + Critical</option>
                <option value="info">All severities</option>
              </select>
            </label>

            <label>
              Delivery cadence
              <select
                value={intervalMinutes}
                onChange={(event) => setIntervalMinutes(Number(event.target.value))}
              >
                {CADENCES.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <div className="notificationCategories">
            <span>Signal categories</span>
            <div>
              {CATEGORIES.map((item) => (
                <label key={item.value}>
                  <input
                    type="checkbox"
                    checked={categories.includes(item.value)}
                    onChange={() => toggleCategory(item.value)}
                  />
                  <span>{item.label}</span>
                </label>
              ))}
            </div>
          </div>

          <div className="sourceAdminFooter">
            <span className="mutedInline">
              Delivery does not mark signals seen, acknowledged, or resolved.
            </span>
            <button
              className="primaryButton"
              type="button"
              disabled={busy}
              onClick={() => void save()}
            >
              {busy ? "Saving…" : "Save preferences"}
            </button>
          </div>

          {error && (
            <div className="runIssues error">
              <strong>Notification settings need attention</strong>
              <p>{error}</p>
            </div>
          )}

          <div className="notificationHistory">
            <div className="sourceSectionTitle">
              <div>
                <h4>Recent delivery history</h4>
                <p>Sanitized channel outcomes for this project and user.</p>
              </div>
              <span className="mutedInline">
                Last delivery {formatDate(preference?.last_delivery_at ?? null)}
              </span>
            </div>

            {snapshot?.recent_deliveries.length ? (
              snapshot.recent_deliveries.slice(0, 8).map((delivery) => (
                <div className="notificationHistoryRow" key={delivery.id}>
                  <span
                    className={`runStatus ${
                      delivery.status === "success" ? "success" : "failed"
                    }`}
                  >
                    {delivery.status}
                  </span>
                  <div>
                    <strong>{delivery.channel === "teams" ? "Teams" : "Email"}</strong>
                    <span>
                      {delivery.signal_count} signal
                      {delivery.signal_count === 1 ? "" : "s"} ·{" "}
                      {formatDate(delivery.attempted_at)}
                    </span>
                    {delivery.error_message && <small>{delivery.error_message}</small>}
                  </div>
                </div>
              ))
            ) : (
              <div className="noRun">
                <strong>No outbound deliveries yet</strong>
                <span>
                  Delivery history appears after the worker processes an enabled preference.
                </span>
              </div>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
