"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import type {
  ActionItemView,
  DecisionView,
  DependencyView,
  IssueView,
  ProjectMemorySnapshot,
  RiskView,
} from "@/lib/types";

type DeliveryFlag = {
  id: string;
  type: "Overdue action" | "Blocked action" | "Blocked dependency" | "Open issue" | "Open risk" | "Decision needed";
  title: string;
  detail: string;
  date: string | null;
  urgency: "critical" | "attention";
};

const TERMINAL = new Set([
  "completed", "closed", "cancelled", "canceled", "resolved",
  "approved", "rejected", "invalidated", "satisfied", "validated",
]);
const normalize = (status: string): string => status.trim().toLowerCase().replaceAll(" ", "_");
const active = (status: string): boolean => !TERMINAL.has(normalize(status));
const label = (status: string): string =>
  status.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());

function dateLabel(date: string | null): string {
  if (!date) return "Date not set";
  const parsed = new Date(date.slice(0, 10) + "T12:00:00Z");
  return Number.isNaN(parsed.getTime())
    ? "Date unavailable"
    : new Intl.DateTimeFormat("en", {
        month: "short", day: "numeric", year: "numeric", timeZone: "UTC",
      }).format(parsed);
}

function daysBetween(start: string, end: string): number | null {
  const from = Date.parse(start.slice(0, 10) + "T00:00:00Z");
  const to = Date.parse(end.slice(0, 10) + "T00:00:00Z");
  if (!Number.isFinite(from) || !Number.isFinite(to)) return null;
  return Math.round((to - from) / 86400000);
}

function daysUntil(due: string | null, today: string): number | null {
  return due ? daysBetween(today, due) : null;
}

function actionFlags(items: ActionItemView[], today: string): DeliveryFlag[] {
  return items.flatMap<DeliveryFlag>((item) => {
    if (!active(item.status)) return [];
    const delta = daysUntil(item.due_date, today);
    if (normalize(item.status) === "blocked") {
      return [{
        id: "action-" + item.id, type: "Blocked action" as const,
        title: item.title,
        detail: "Action is blocked" + (item.due_date ? " · Due " + dateLabel(item.due_date) : ""),
        date: item.due_date, urgency: "critical" as const,
      }];
    }
    if (delta !== null && delta < 0) {
      return [{
        id: "action-" + item.id, type: "Overdue action" as const,
        title: item.title,
        detail: Math.abs(delta) + " day(s) past due · " + label(item.status),
        date: item.due_date, urgency: "critical" as const,
      }];
    }
    return [];
  });
}

function dependencyFlags(items: DependencyView[]): DeliveryFlag[] {
  return items
    .filter((item) => active(item.status) && normalize(item.status) === "blocked")
    .map((item) => ({
      id: "dependency-" + item.id, type: "Blocked dependency" as const,
      title: item.title,
      detail: [item.provider ? "Provider: " + item.provider : null, item.required_by ? "Required by: " + item.required_by : null]
        .filter(Boolean).join(" · ") || "Blocked dependency requires follow-up",
      date: null, urgency: "critical" as const,
    }));
}

function decisionFlags(items: DecisionView[], today: string): DeliveryFlag[] {
  return items
    .filter((item) => ["pending", "proposed"].includes(normalize(item.status)))
    .map((item) => {
      const delta = daysUntil(item.review_date, today);
      return {
        id: "decision-" + item.id, type: "Decision needed" as const,
        title: item.title,
        detail: delta !== null && delta < 0
          ? "Review overdue by " + Math.abs(delta) + " day(s)"
          : item.review_date ? "Review " + dateLabel(item.review_date) : "Review date not set",
        date: item.review_date,
        urgency: delta !== null && delta < 0 ? "critical" as const : "attention" as const,
      };
    });
}

function issueFlags(items: IssueView[]): DeliveryFlag[] {
  return items.filter((item) => active(item.status)).map((item) => ({
    id: "issue-" + item.id, type: "Open issue" as const, title: item.title,
    detail: [item.severity ? "Severity: " + label(item.severity) : null,
      item.due_date ? "Due " + dateLabel(item.due_date) : null].filter(Boolean).join(" · ") || "Open issue",
    date: item.due_date,
    urgency: ["critical", "high", "severe"].includes(normalize(item.severity ?? "")) ? "critical" as const : "attention" as const,
  }));
}

function riskFlags(items: RiskView[]): DeliveryFlag[] {
  return items.filter((item) => active(item.status) && ["high", "critical"].includes(normalize(item.impact ?? "")))
    .map((item) => ({
      id: "risk-" + item.id, type: "Open risk" as const, title: item.title,
      detail: item.mitigation ? "Mitigation: " + item.mitigation : "Mitigation not documented",
      date: item.due_date, urgency: "attention" as const,
    }));
}

async function loadMemory(): Promise<ProjectMemorySnapshot> {
  const response = await fetch("/api/memory", { cache: "no-store" });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(typeof payload.detail === "string" ? payload.detail : "Unable to load delivery data");
  }
  return payload as ProjectMemorySnapshot;
}

type MemorySection = "actions" | "raid" | "decisions";

type Props = {
  onOpenMemory: (section: MemorySection) => void;
  onOpenAttention: () => void;
};

function sectionForFlag(type: DeliveryFlag["type"]): MemorySection {
  if (type === "Overdue action" || type === "Blocked action") return "actions";
  if (type === "Decision needed") return "decisions";
  return "raid";
}

export function DeliveryWorkspace({ onOpenMemory, onOpenAttention }: Props) {
  const [snapshot, setSnapshot] = useState<ProjectMemorySnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);
  const [filter, setFilter] = useState<"all" | "critical" | "attention">("all");

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try { setSnapshot(await loadMemory()); }
    catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to load delivery intelligence");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  // UTC date is a consistent boundary for date-only governed fields.
  const today = new Date().toISOString().slice(0, 10);
  const flags = useMemo(() => {
    if (!snapshot) return [];
    const result = [
      ...dependencyFlags(snapshot.dependencies),
      ...actionFlags(snapshot.action_items, today),
      ...decisionFlags(snapshot.decisions, today),
      ...issueFlags(snapshot.issues),
      ...riskFlags(snapshot.risks),
    ];
    return result.sort((a, b) =>
      Number(b.urgency === "critical") - Number(a.urgency === "critical") ||
      (a.date ?? "9999").localeCompare(b.date ?? "9999") ||
      a.title.localeCompare(b.title)
    );
  }, [snapshot, today]);

  if (loading) return <section className="deliverySurface" aria-busy="true"><div className="memoryLoading">Loading governed delivery intelligence…</div></section>;
  if (!snapshot || error) {
    return <section className="deliverySurface"><div className="memoryError">
      <h2>Delivery Intelligence unavailable</h2><p>{error ?? "No project information available"}</p>
      <button className="primaryButton" type="button" onClick={() => void refresh()}>Retry</button>
    </div></section>;
  }

  const project = snapshot.project;
  const activeActions = snapshot.action_items.filter((item) => active(item.status));
  const blockedActions = activeActions.filter((item) => normalize(item.status) === "blocked");
  const overdueActions = activeActions.filter((item) => {
    const delta = daysUntil(item.due_date, today);
    return delta !== null && delta < 0;
  });
  const blockedDependencies = snapshot.dependencies.filter((item) => active(item.status) && normalize(item.status) === "blocked");
  const pendingDecisions = snapshot.decisions.filter((item) => ["pending", "proposed"].includes(normalize(item.status)));
  const forecastVariance = project.planned_end_date && project.forecast_end_date
    ? daysBetween(project.planned_end_date, project.forecast_end_date) : null;
  const visible = flags.filter((flag) => filter === "all" || flag.urgency === filter);
  const display = showAll ? visible : visible.slice(0, 8);

  return (
    <section className="deliverySurface">
      <div className="deliveryHero">
        <div>
          <span className="executivePriorityEyebrow">DELIVERY INTELLIGENCE · GOVERNED PROJECT MEMORY</span>
          <h2>{project.name} — Delivery pulse</h2>
          <p>Spot blockers, overdue commitments, decisions and execution pressure. All signals come from authorized project records, not an AI prediction.</p>
        </div>
        <button className="secondaryButton" type="button" onClick={() => void refresh()}>↻ Refresh</button>
      </div>

      <div className="deliveryKpiGrid">
        <DeliveryKpi label="Open actions" value={activeActions.length} detail={blockedActions.length + " currently blocked"} tone="neutral" />
        <DeliveryKpi label="Overdue actions" value={overdueActions.length} detail="Due date before today (UTC)" tone={overdueActions.length ? "critical" : "good"} />
        <DeliveryKpi label="Blocked dependencies" value={blockedDependencies.length} detail="Unresolved external or internal blockers" tone={blockedDependencies.length ? "critical" : "good"} />
        <DeliveryKpi label="Pending decisions" value={pendingDecisions.length} detail="Awaiting human resolution" tone={pendingDecisions.length ? "attention" : "good"} />
      </div>

      <div className="deliveryDetailsGrid">
        <article className="deliverySchedule">
          <span className="executivePriorityEyebrow">SCHEDULE CONTEXT</span>
          <h3>Delivery dates</h3>
          <dl>
            <div><dt>Planned finish</dt><dd>{dateLabel(project.planned_end_date)}</dd></div>
            <div><dt>Forecast finish</dt><dd>{project.forecast_end_date ? dateLabel(project.forecast_end_date) : "Not recorded"}</dd></div>
            <div><dt>Forecast variance</dt><dd>{
              forecastVariance === null ? "Not available" :
                forecastVariance === 0 ? "No variance" :
                (forecastVariance > 0 ? "+" : "") + forecastVariance + " calendar day(s)"
            }</dd></div>
          </dl>
          <p>Planned and forecast dates are separate governed fields. Variance is available only when both are recorded; it is not a prediction. Milestone-level tracking is not available in this MVP view.</p>
        </article>
        <article className="deliverySchedule">
          <span className="executivePriorityEyebrow">EXECUTION STATUS</span>
          <h3>Action delivery mix</h3>
          <div className="deliveryTrack" aria-label="Completed action items versus total">
            <div style={{ width: `${snapshot.action_items.length
              ? Math.round(100 * snapshot.action_items.filter((a) => ["completed", "closed"].includes(normalize(a.status))).length / snapshot.action_items.length)
              : 0}%` }} />
          </div>
          <strong>{snapshot.action_items.filter((a) => ["completed", "closed"].includes(normalize(a.status))).length} / {snapshot.action_items.length} completed</strong>
          <p>This ratio is a count of governed Action Items, not percentage of scope delivered or earned value.</p>
        </article>
      </div>

      <div className="deliverySignalHeader">
        <div><h3>Delivery follow-up queue</h3><p>Read-only prioritization: blockers first, then time-sensitive and open governance items.</p></div>
        <div className="deliverySignalFilters" aria-label="Filter delivery signals">
          {(["all", "critical", "attention"] as const).map((value) =>
            <button key={value} type="button" aria-pressed={filter === value}
              className={filter === value ? "active" : ""}
              onClick={() => { setFilter(value); setShowAll(false); }}>
              {label(value)} ({value === "all" ? flags.length : flags.filter((f) => f.urgency === value).length})
            </button>
          )}
        </div>
      </div>
      <div className="deliverySignalList">
        {display.length ? display.map((flag) =>
          <article className={`deliverySignalItem ${flag.urgency}`} key={flag.id}>
            <div className="deliverySignalCopy">
              <span className="deliverySignalPill">{flag.type}</span>
              <div><h4>{flag.title}</h4><p>{flag.detail}</p></div>
            </div>
            <div className="deliverySignalControls">
              <span className="deliveryUrgency">{label(flag.urgency)}</span>
              <button className="secondaryButton deliveryInspectButton" type="button"
                onClick={() => onOpenMemory(sectionForFlag(flag.type))}
                aria-label={`Inspect ${flag.type.toLowerCase()} in Project Memory: ${flag.title}`}>
                Inspect in Project Memory <span aria-hidden="true">→</span>
              </button>
            </div>
          </article>
        ) : <div className="deliveryEmpty">No matching governed follow-up signals. This does not guarantee the project has no delivery risks.</div>}
      </div>
      {!showAll && visible.length > 8 && <button className="secondaryButton deliveryShowAll" type="button" onClick={() => setShowAll(true)}>Show all {visible.length} signals</button>}
      <div className="deliveryReadOnlyNote">
        <strong>Read-only delivery intelligence</strong>
        <p>Inspect the complete records in Project Memory or review personal signals in Attention Center. Section links do not automatically select an individual record. Changes to governed truth still require authorized review.</p>
        <div className="deliveryNavigationActions">
          <button className="secondaryButton" type="button" onClick={() => onOpenMemory("actions")}>Open Project Memory</button>
          <button className="secondaryButton" type="button" onClick={onOpenAttention}>Open Attention Center</button>
        </div>
      </div>
    </section>
  );
}

function DeliveryKpi({ label: name, value, detail, tone }: {
  label: string; value: number; detail: string; tone: "neutral" | "critical" | "attention" | "good";
}) {
  return <article className={`deliveryKpi ${tone}`}>
    <span>{name}</span><strong>{value}</strong><small>{detail}</small>
  </article>;
}
