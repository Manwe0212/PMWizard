"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import type {
  AttentionCenterSnapshot,
  AttentionSignalView,
  AttentionStateResponse,
} from "@/lib/types";

type TargetView = "health" | "memory" | "sources" | "automations" | "inbox";
type Filter = "all" | "unread" | "critical" | "snoozed";

type Props = {
  onNavigate: (view: TargetView) => void;
  onUnreadChange: (count: number) => void;
};

function titleCase(value: string): string {
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatDate(value: string | null): string {
  if (!value) return "Not recorded";
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
        : `Attention request failed (${response.status})`,
    );
  }
  return payload as T;
}

export function AttentionCenterWorkspace({
  onNavigate,
  onUnreadChange,
}: Props) {
  const [snapshot, setSnapshot] = useState<AttentionCenterSnapshot | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [busy, setBusy] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await readJson<AttentionCenterSnapshot>(
        await fetch("/api/attention", { cache: "no-store" }),
      );
      setSnapshot(result);
      onUnreadChange(result.summary.unread);
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Unable to load Attention Center.",
      );
    } finally {
      setLoading(false);
    }
  }, [onUnreadChange]);

  useEffect(() => {
    void load();
  }, [load]);

  const visible = useMemo(() => {
    const signals = snapshot?.signals ?? [];
    if (filter === "unread") {
      return signals.filter((item) => item.state === "unread");
    }
    if (filter === "critical") {
      return signals.filter((item) => item.severity === "critical");
    }
    if (filter === "snoozed") {
      return signals.filter((item) => item.state === "snoozed");
    }
    return signals;
  }, [snapshot, filter]);

  async function mutate(
    signal: AttentionSignalView,
    action: "seen" | "acknowledge" | "snooze" | "reset",
  ) {
    setBusy(signal.id);
    setError(null);
    try {
      const body: Record<string, unknown> = { action };
      await readJson<AttentionStateResponse>(
        await fetch(
          `/api/attention/${encodeURIComponent(signal.id)}/state`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
          },
        ),
      );
      await load();
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Unable to update Attention state.",
      );
    } finally {
      setBusy(null);
    }
  }

  async function openSignal(signal: AttentionSignalView) {
    if (signal.state === "unread") {
      await mutate(signal, "seen");
    }
    onNavigate(signal.target_view);
  }

  if (loading && !snapshot) {
    return (
      <section className="attentionSurface">
        <div className="memoryLoading">
          <div className="skeletonLine wide" />
          <div className="attentionMetricGrid">
            <div className="skeletonBlock" />
            <div className="skeletonBlock" />
            <div className="skeletonBlock" />
            <div className="skeletonBlock" />
          </div>
          <div className="skeletonBlock memorySkeletonLarge" />
        </div>
      </section>
    );
  }

  if (error && !snapshot) {
    return (
      <section className="attentionSurface">
        <div className="memoryError">
          <div className="detailEmptyMark">!</div>
          <h2>Attention Center unavailable</h2>
          <p>{error}</p>
          <button className="primaryButton" type="button" onClick={() => void load()}>
            Retry
          </button>
        </div>
      </section>
    );
  }

  const summary = snapshot?.summary;

  return (
    <section className="attentionSurface">
      <div className="attentionHero">
        <div>
          <div className="detailBadges">
            <span className="memoryTruthBadge">Deterministic signals</span>
            <span className="sourceOperationalBadge">Personal receipts</span>
          </div>
          <h2>What requires your attention?</h2>
          <p>
            Active signals are recomputed from governed project truth and operational
            telemetry. Acknowledging or snoozing changes only your personal receipt.
          </p>
        </div>
        <button
          className="secondaryButton"
          type="button"
          onClick={() => void load()}
          disabled={loading}
        >
          ↻ Refresh
        </button>
      </div>

      {error && (
        <div className="errorBanner" role="alert">
          <span>!</span>
          <div>
            <strong>Attention operation failed</strong>
            <p>{error}</p>
          </div>
        </div>
      )}

      {summary && (
        <div className="attentionMetricGrid">
          <AttentionMetric
            label="Unread"
            value={summary.unread}
            detail="New or changed signals"
            tone={summary.unread ? "attention" : "good"}
          />
          <AttentionMetric
            label="Critical"
            value={summary.critical}
            detail="Immediate intervention"
            tone={summary.critical ? "risk" : "good"}
          />
          <AttentionMetric
            label="Warnings"
            value={summary.warning}
            detail="Needs follow-up"
            tone={summary.warning ? "attention" : "default"}
          />
          <AttentionMetric
            label="Snoozed"
            value={summary.snoozed}
            detail="Temporarily deferred"
          />
        </div>
      )}

      <div className="attentionFilters">
        {(["all", "unread", "critical", "snoozed"] as Filter[]).map((item) => (
          <button
            className={filter === item ? "active" : ""}
            key={item}
            type="button"
            onClick={() => setFilter(item)}
          >
            {titleCase(item)}
          </button>
        ))}
      </div>

      {visible.length === 0 ? (
        <div className="attentionEmpty">
          <div className="emptyIcon">✓</div>
          <strong>No signals in this view</strong>
          <span>
            Active problems disappear automatically when governed project state resolves
            them.
          </span>
        </div>
      ) : (
        <div className="attentionList">
          {visible.map((signal) => (
            <article
              className={`attentionCard ${signal.severity} ${signal.state}`}
              key={signal.id}
            >
              <div className="attentionCardIcon">
                {signal.severity === "critical"
                  ? "!"
                  : signal.severity === "warning"
                    ? "△"
                    : "i"}
              </div>

              <div className="attentionCardBody">
                <div className="attentionCardBadges">
                  <span className={`attentionSeverity ${signal.severity}`}>
                    {titleCase(signal.severity)}
                  </span>
                  <span className="sourceTag">{titleCase(signal.category)}</span>
                  <span className={`attentionState ${signal.state}`}>
                    {titleCase(signal.state)}
                  </span>
                </div>
                <h3>{signal.title}</h3>
                <p>{signal.detail}</p>
                <div className="attentionMeta">
                  {signal.due_date && <span>Due {signal.due_date}</span>}
                  {signal.observed_at && (
                    <span>Observed {formatDate(signal.observed_at)}</span>
                  )}
                  {signal.state === "snoozed" && signal.snoozed_until && (
                    <span>Snoozed until {formatDate(signal.snoozed_until)}</span>
                  )}
                </div>
              </div>

              <div className="attentionActions">
                <button
                  className="primaryButton"
                  type="button"
                  disabled={busy === signal.id}
                  onClick={() => void openSignal(signal)}
                >
                  {signal.action_label}
                </button>

                {signal.state !== "acknowledged" &&
                signal.state !== "snoozed" ? (
                  <>
                    <button
                      className="secondaryButton"
                      type="button"
                      disabled={busy === signal.id}
                      onClick={() => void mutate(signal, "acknowledge")}
                    >
                      Acknowledge
                    </button>
                    <button
                      className="textButton"
                      type="button"
                      disabled={busy === signal.id}
                      onClick={() => void mutate(signal, "snooze")}
                    >
                      Snooze 24h
                    </button>
                  </>
                ) : (
                  <button
                    className="secondaryButton"
                    type="button"
                    disabled={busy === signal.id}
                    onClick={() => void mutate(signal, "reset")}
                  >
                    Reopen
                  </button>
                )}
              </div>
            </article>
          ))}
        </div>
      )}

      <div className="healthGovernanceNote">
        Attention receipts do not resolve project conditions. A signal disappears only
        when the underlying governed state or operational condition no longer satisfies
        its rule.
      </div>
    </section>
  );
}

function AttentionMetric({
  label,
  value,
  detail,
  tone = "default",
}: {
  label: string;
  value: number;
  detail: string;
  tone?: "default" | "attention" | "risk" | "good";
}) {
  return (
    <article className={`executiveMetric ${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </article>
  );
}
