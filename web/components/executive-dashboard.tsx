"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import type {
  ExecutiveDashboardSnapshot,
  ExecutiveDecisionItem,
  ExecutiveInboxItem,
  ExecutiveRAIDItem,
  ExecutiveSourceAlert,
  ProjectHealthBand,
  ProjectRollupItem,
} from "@/lib/types";

type ProjectViewTarget = "health" | "inbox" | "memory" | "sources";

type Props = {
  onOpenProject: (
    projectId: string,
    target: ProjectViewTarget,
  ) => void | Promise<void>;
};

function titleCase(value: string): string {
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function scoreLabel(score: number | null): string {
  return score === null ? "—" : String(score);
}

function bandLabel(band: ProjectHealthBand): string {
  return band === "insufficient_data" ? "Insufficient data" : titleCase(band);
}

function formatDate(value: string | null): string {
  if (!value) return "No date";
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
  }).format(new Date(value));
}

function formatTimestamp(value: string): string {
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

async function loadDashboard(): Promise<ExecutiveDashboardSnapshot> {
  const response = await fetch("/api/executive/dashboard", {
    cache: "no-store",
  });
  const payload = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(
      typeof payload?.detail === "string"
        ? payload.detail
        : `Unable to load Executive Dashboard (${response.status})`,
    );
  }

  return payload as ExecutiveDashboardSnapshot;
}

export function ExecutiveDashboard({ onOpenProject }: Props) {
  const [dashboard, setDashboard] =
    useState<ExecutiveDashboardSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setDashboard(await loadDashboard());
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Unable to load Executive Dashboard.",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const headline = useMemo(() => {
    if (!dashboard) return "";
    const summary = dashboard.summary;
    const alerts =
      summary.projects_needing_attention +
      summary.critical_raid +
      summary.source_failures;

    if (alerts === 0 && summary.pending_inbox === 0) {
      return "No material executive alerts are visible across your authorized projects.";
    }

    const parts: string[] = [];
    if (summary.projects_needing_attention > 0) {
      parts.push(
        `${summary.projects_needing_attention} project${
          summary.projects_needing_attention === 1 ? "" : "s"
        } need attention`,
      );
    }
    if (summary.critical_raid > 0) {
      parts.push(`${summary.critical_raid} critical RAID signal${
        summary.critical_raid === 1 ? "" : "s"
      }`);
    }
    if (summary.source_failures > 0) {
      parts.push(`${summary.source_failures} failed source${
        summary.source_failures === 1 ? "" : "s"
      }`);
    }
    if (summary.pending_inbox > 0) {
      parts.push(`${summary.pending_inbox} pending review${
        summary.pending_inbox === 1 ? "" : "s"
      }`);
    }
    return parts.join(" · ");
  }, [dashboard]);

  if (loading && !dashboard) {
    return (
      <section className="executiveSurface">
        <div className="memoryLoading">
          <div className="skeletonLine wide" />
          <div className="executiveMetricGrid">
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

  if (!dashboard) {
    return (
      <section className="executiveSurface">
        <div className="memoryError">
          <div className="detailEmptyMark">!</div>
          <h2>Executive Dashboard unavailable</h2>
          <p>{error ?? "No executive intelligence is available."}</p>
          <button className="primaryButton" type="button" onClick={() => void load()}>
            Retry
          </button>
        </div>
      </section>
    );
  }

  const { summary } = dashboard;
  const priorityActions: Array<{
    key: string;
    label: string;
    subject: string;
    rationale: string;
    action: string;
    projectId: string;
    target: ProjectViewTarget;
    tone: "critical" | "attention";
  }> = [
    ...dashboard.critical_raid.slice(0, 2).map((item) => ({
      key: `raid-${item.entity_type}-${item.entity_id}`,
      label: "Critical RAID",
      subject: item.title,
      rationale: `${item.project_name} · ${item.reason}`,
      action: "Inspect governed RAID",
      projectId: item.project_id,
      target: "memory" as const,
      tone: "critical" as const,
    })),
    ...dashboard.pending_decisions.slice(0, 1).map((item) => ({
      key: `decision-${item.decision_id}`,
      label: "Decision awaiting resolution",
      subject: item.title,
      rationale: `${item.project_name} · ${item.expected_impact || "Impact not documented"}`,
      action: "Review decision",
      projectId: item.project_id,
      target: "memory" as const,
      tone: "attention" as const,
    })),
    ...dashboard.inbox_items.slice(0, 1).map((item) => ({
      key: `review-${item.suggestion_id}`,
      label: "Human review required",
      subject: titleCase(item.suggestion_type),
      rationale: `${item.project_name} · ${item.reason}`,
      action: "Open Project Inbox",
      projectId: item.project_id,
      target: "inbox" as const,
      tone: "attention" as const,
    })),
    ...dashboard.source_alerts.slice(0, 1).map((item) => ({
      key: `source-${item.source_id}`,
      label: "Source health requires attention",
      subject: item.display_name,
      rationale: `${item.project_name} · ${titleCase(item.health)}`,
      action: "Inspect source",
      projectId: item.project_id,
      target: "sources" as const,
      tone: "attention" as const,
    })),
  ].slice(0, 3);

  return (
    <section className="executiveSurface" aria-busy={loading}>
      {error && (
        <div className="demoStaleNotice" role="alert">
          <div><strong>Executive Dashboard refresh failed</strong><p>Showing the last successfully loaded snapshot. Figures may be outdated. {error}</p></div>
          <button type="button" className="secondaryButton" disabled={loading} onClick={() => void load()}>Retry refresh</button>
        </div>
      )}
      <div className="executiveHero">
        <div className="executiveHealthBlock">
          <div className={`executiveScoreRing ${summary.health.band}`}>
            <div>
              <strong>{scoreLabel(summary.health.score)}</strong>
              <span>/100</span>
            </div>
          </div>
          <span className={`healthBandBadge ${summary.health.band}`}>
            {bandLabel(summary.health.band)}
          </span>
        </div>

        <div className="executiveHeroCopy">
          <div className="detailBadges">
            <span className="memoryTruthBadge">Executive read model</span>
            <span className="sourceOperationalBadge">
              {summary.health.projects_total} authorized projects
            </span>
          </div>
          <h2>Executive command center</h2>
          <p className="executiveHeadline">{headline}</p>
          <p>
            Current governed Health, review workload, RAID, Decisions and Source
            operations in one authorization-preserving view.
          </p>

          <div className="coverageRow">
            <div>
              <span>Average health coverage</span>
              <strong>{summary.health.average_coverage_percent}%</strong>
            </div>
            <div className="coverageTrack">
              <span
                style={{ width: `${summary.health.average_coverage_percent}%` }}
              />
            </div>
            <small>
              {summary.health.projects_scored}/{summary.health.projects_total} projects
              have reliable health scoring.
            </small>
          </div>
        </div>

        <div className="executiveHeroActions">
          <button className="secondaryButton" type="button" disabled={loading} onClick={() => void load()}>
            ↻ Refresh
          </button>
          <small>Generated {formatTimestamp(dashboard.generated_at)}</small>
        </div>
      </div>

      <div className="executiveMetricGrid">
        <MetricCard
          label="Projects needing attention"
          value={summary.projects_needing_attention}
          detail={`${summary.health.red} red · ${summary.health.deteriorating} deteriorating`}
          tone={summary.projects_needing_attention ? "risk" : "good"}
        />
        <MetricCard
          label="Inbox pending"
          value={summary.pending_inbox}
          detail={`${summary.deferred_inbox} deferred`}
          tone={summary.pending_inbox ? "attention" : "good"}
        />
        <MetricCard
          label="Critical RAID"
          value={summary.critical_raid}
          detail="Materialized, blocked or high-severity"
          tone={summary.critical_raid ? "risk" : "good"}
        />
        <MetricCard
          label="Decisions pending"
          value={summary.pending_decisions}
          detail="Proposed or pending"
          tone={summary.pending_decisions ? "attention" : "default"}
        />
        <MetricCard
          label="Source failures"
          value={summary.source_failures}
          detail={`${summary.source_attention} additional source alerts`}
          tone={summary.source_failures ? "risk" : "good"}
        />
        <MetricCard
          label="Cross-project signals"
          value={summary.cross_project_signals}
          detail="Repeated active Risks / Dependencies"
          tone={summary.cross_project_signals ? "attention" : "default"}
        />
      </div>

      <section className="executivePrioritySection" aria-label="Executive action priorities">
        <div className="executivePriorityHeading">
          <div>
            <span className="executivePriorityEyebrow">DECISION SUPPORT · GOVERNED SIGNALS</span>
            <h3>What needs attention next?</h3>
            <p>
              A focused view of visible RAID, decision, review and source signals.
              Open the underlying record before taking action.
            </p>
          </div>
          <span className="executivePriorityCount">
            {priorityActions.length} highlighted
          </span>
        </div>
        {priorityActions.length ? (
          <div className="executivePriorityGrid">
            {priorityActions.map((priority) => (
              <article className={`executivePriorityCard ${priority.tone}`} key={priority.key}>
                <span className="executivePriorityLabel">{priority.label}</span>
                <h4>{priority.subject}</h4>
                <p>{priority.rationale}</p>
                <button
                  type="button"
                  onClick={() => void onOpenProject(priority.projectId, priority.target)}
                >
                  {priority.action} <span aria-hidden="true">→</span>
                </button>
              </article>
            ))}
          </div>
        ) : (
          <div className="executivePriorityEmpty">
            No critical RAID, pending decisions, review suggestions or source
            alerts are visible across your authorized projects.
          </div>
        )}
        <p className="executivePriorityNote">
          These are presentation priorities from current governed records,
          not AI-generated recommendations or automatic changes.
        </p>
      </section>

      <div className="executivePrimaryGrid">
        <DashboardPanel
          title="Projects requiring attention"
          subtitle="Current Health and trend determine executive priority."
          count={dashboard.attention_projects.length}
        >
          {dashboard.attention_projects.length ? (
            <div className="executiveProjectList">
              {dashboard.attention_projects.map((project) => (
                <AttentionProject
                  key={project.project_id}
                  project={project}
                  onOpen={() => void onOpenProject(project.project_id, "health")}
                />
              ))}
            </div>
          ) : (
            <EmptySignal text="No red, amber or deteriorating authorized projects." />
          )}
        </DashboardPanel>

        <DashboardPanel
          title="Critical RAID"
          subtitle="Materialized, blocked or high-severity governed items."
          count={dashboard.critical_raid.length}
        >
          {dashboard.critical_raid.length ? (
            <div className="executiveList">
              {dashboard.critical_raid.map((item) => (
                <RAIDRow
                  key={`${item.entity_type}-${item.entity_id}`}
                  item={item}
                  onOpen={() => void onOpenProject(item.project_id, "memory")}
                />
              ))}
            </div>
          ) : (
            <EmptySignal text="No critical governed RAID items are visible." />
          )}
        </DashboardPanel>
      </div>

      <div className="executiveSecondaryGrid">
        <DashboardPanel
          title="Review workload"
          subtitle="Evidence-visible Inbox suggestions awaiting human governance."
          count={dashboard.inbox_items.length}
        >
          {dashboard.inbox_items.length ? (
            <div className="executiveList">
              {dashboard.inbox_items.map((item) => (
                <InboxRow
                  key={item.suggestion_id}
                  item={item}
                  onOpen={() => void onOpenProject(item.project_id, "inbox")}
                />
              ))}
            </div>
          ) : (
            <EmptySignal text="No authorized Inbox suggestions require review." />
          )}
        </DashboardPanel>

        <DashboardPanel
          title="Pending decisions"
          subtitle="Governed Decisions still proposed or pending."
          count={dashboard.pending_decisions.length}
        >
          {dashboard.pending_decisions.length ? (
            <div className="executiveList">
              {dashboard.pending_decisions.map((item) => (
                <DecisionRow
                  key={item.decision_id}
                  item={item}
                  onOpen={() => void onOpenProject(item.project_id, "memory")}
                />
              ))}
            </div>
          ) : (
            <EmptySignal text="No pending governed Decisions are visible." />
          )}
        </DashboardPanel>

        <DashboardPanel
          title="Source operations"
          subtitle="Failed, partial or never-synced authorized connections."
          count={dashboard.source_alerts.length}
        >
          {dashboard.source_alerts.length ? (
            <div className="executiveList">
              {dashboard.source_alerts.map((item) => (
                <SourceRow
                  key={item.source_id}
                  item={item}
                  onOpen={() => void onOpenProject(item.project_id, "sources")}
                />
              ))}
            </div>
          ) : (
            <EmptySignal text="No Source operational alerts are visible." />
          )}
        </DashboardPanel>
      </div>

      <DashboardPanel
        title="Cross-project signals"
        subtitle="Conservative repeated active Risk and Dependency titles."
        count={dashboard.cross_project_signals.length}
      >
        {dashboard.cross_project_signals.length ? (
          <div className="executiveSignalGrid">
            {dashboard.cross_project_signals.map((signal) => (
              <article
                className="executiveCrossSignal"
                key={`${signal.signal_type}-${signal.title}`}
              >
                <div className={`crossSignalIcon ${signal.signal_type}`}>
                  {signal.signal_type === "risk" ? "R" : "D"}
                </div>
                <div>
                  <div className="crossSignalTitle">
                    <strong>{signal.title}</strong>
                    <span>{signal.project_count} projects</span>
                  </div>
                  <p>{signal.project_names.join(" · ")}</p>
                  <small>{signal.explanation}</small>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <EmptySignal text="No repeated active Risks or Dependencies across visible projects." />
        )}
      </DashboardPanel>

      <div className="sourceSecurityNote">
        <span>⌁</span>
        <div>
          <strong>Executive visibility follows Project authorization</strong>
          <p>
            Dashboard metrics are composed only from project:read memberships. Inbox
            counts additionally honor Evidence permission scopes before a suggestion
            can appear.
          </p>
        </div>
      </div>
    </section>
  );
}

function MetricCard({
  label,
  value,
  detail,
  tone,
}: {
  label: string;
  value: number;
  detail: string;
  tone: "risk" | "attention" | "good" | "default";
}) {
  return (
    <article className={`executiveMetric ${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </article>
  );
}

function DashboardPanel({
  title,
  subtitle,
  count,
  children,
}: {
  title: string;
  subtitle: string;
  count: number;
  children: React.ReactNode;
}) {
  return (
    <section className="executivePanel">
      <div className="portfolioPanelHeader">
        <div>
          <h3>{title}</h3>
          <p>{subtitle}</p>
        </div>
        <span>{count}</span>
      </div>
      {children}
    </section>
  );
}

function AttentionProject({
  project,
  onOpen,
}: {
  project: ProjectRollupItem;
  onOpen: () => void;
}) {
  return (
    <button className="executiveProjectRow" type="button" onClick={onOpen}>
      <span className={`executiveBandBar ${project.health_band}`} />
      <div>
        <strong>{project.name}</strong>
        <span>
          {project.program_name || project.portfolio_name || "Standalone project"}
        </span>
        <small>
          {project.top_drivers.length
            ? project.top_drivers.slice(0, 2).join(" · ")
            : "No negative drivers"}
        </small>
      </div>
      <div className="executiveProjectScore">
        <strong>{scoreLabel(project.health_score)}</strong>
        <span className={`trendMini ${project.trend_direction}`}>
          {titleCase(project.trend_direction)}
          {project.trend_score_delta !== null
            ? ` ${project.trend_score_delta > 0 ? "+" : ""}${project.trend_score_delta}`
            : ""}
        </span>
      </div>
    </button>
  );
}

function RAIDRow({
  item,
  onOpen,
}: {
  item: ExecutiveRAIDItem;
  onOpen: () => void;
}) {
  return (
    <button className="executiveRow" type="button" onClick={onOpen}>
      <span className={`executiveEntityIcon raid ${item.severity}`}>
        {item.entity_type.slice(0, 1)}
      </span>
      <div>
        <strong>{item.title}</strong>
        <span>{item.project_name} · {item.entity_type}</span>
        <small>{item.reason}</small>
      </div>
      <div className="executiveRowMeta">
        <b>{titleCase(item.status)}</b>
        <span>{formatDate(item.due_date)}</span>
      </div>
    </button>
  );
}

function InboxRow({
  item,
  onOpen,
}: {
  item: ExecutiveInboxItem;
  onOpen: () => void;
}) {
  return (
    <button className="executiveRow" type="button" onClick={onOpen}>
      <span className="executiveEntityIcon inbox">⌁</span>
      <div>
        <strong>{titleCase(item.suggestion_type)}</strong>
        <span>{item.project_name}</span>
        <small>{item.reason}</small>
      </div>
      <div className="executiveRowMeta">
        <b>{Math.round(item.confidence * 100)}%</b>
        <span>{titleCase(item.review_status)}</span>
      </div>
    </button>
  );
}

function DecisionRow({
  item,
  onOpen,
}: {
  item: ExecutiveDecisionItem;
  onOpen: () => void;
}) {
  return (
    <button className="executiveRow" type="button" onClick={onOpen}>
      <span className="executiveEntityIcon decision">D</span>
      <div>
        <strong>{item.title}</strong>
        <span>{item.project_name}</span>
        <small>{item.expected_impact || "Expected impact not documented."}</small>
      </div>
      <div className="executiveRowMeta">
        <b>{titleCase(item.status)}</b>
        <span>{formatDate(item.review_date)}</span>
      </div>
    </button>
  );
}

function SourceRow({
  item,
  onOpen,
}: {
  item: ExecutiveSourceAlert;
  onOpen: () => void;
}) {
  return (
    <button className="executiveRow" type="button" onClick={onOpen}>
      <span className={`executiveEntityIcon source ${item.health}`}>↗</span>
      <div>
        <strong>{item.display_name}</strong>
        <span>{item.project_name} · {titleCase(item.source_system)}</span>
        <small>
          {item.error_count} errors · {item.skipped} skipped
        </small>
      </div>
      <div className="executiveRowMeta">
        <b>{titleCase(item.health)}</b>
        <span>
          {item.latest_finished_at
            ? formatTimestamp(item.latest_finished_at)
            : "Never synced"}
        </span>
      </div>
    </button>
  );
}

function EmptySignal({ text }: { text: string }) {
  return (
    <div className="executiveEmpty compact">
      <div className="emptyIcon">✓</div>
      <strong>No immediate signal</strong>
      <span>{text}</span>
    </div>
  );
}
