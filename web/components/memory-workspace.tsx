"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import type {
  ActionItemView,
  AssumptionView,
  DecisionView,
  DependencyView,
  IssueView,
  ProjectMemorySnapshot,
  RiskView,
} from "@/lib/types";

type MemoryTab = "actions" | "raid" | "decisions";

type Props = {
  projectName: string;
};

function titleCase(value: string): string {
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function statusClass(status: string): string {
  if (
    ["completed", "approved", "validated", "resolved", "satisfied", "closed"].includes(
      status,
    )
  ) {
    return "good";
  }
  if (["blocked", "materialized", "invalidated", "rejected"].includes(status)) {
    return "bad";
  }
  if (["pending", "pending_external", "proposed", "open"].includes(status)) {
    return "neutral";
  }
  return "working";
}

function dateLabel(value: string | null): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(new Date(value));
}

async function getMemory(): Promise<ProjectMemorySnapshot> {
  const response = await fetch("/api/memory", { cache: "no-store" });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(
      typeof payload?.detail === "string"
        ? payload.detail
        : `Unable to load Project Memory (${response.status})`,
    );
  }
  return payload as ProjectMemorySnapshot;
}

export function MemoryWorkspace({ projectName }: Props) {
  const [snapshot, setSnapshot] = useState<ProjectMemorySnapshot | null>(null);
  const [tab, setTab] = useState<MemoryTab>("actions");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setSnapshot(await getMemory());
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Unable to load Project Memory.",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const raidCount = useMemo(() => {
    if (!snapshot) return 0;
    return (
      snapshot.risks.length +
      snapshot.assumptions.length +
      snapshot.issues.length +
      snapshot.dependencies.length
    );
  }, [snapshot]);

  if (loading) {
    return (
      <section className="memorySurface">
        <div className="memoryLoading">
          <div className="skeletonLine wide" />
          <div className="memoryMetricGrid">
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

  if (error || !snapshot) {
    return (
      <section className="memorySurface">
        <div className="memoryError">
          <div className="detailEmptyMark">!</div>
          <h2>Project Memory unavailable</h2>
          <p>{error ?? "No governed project snapshot is available."}</p>
          <button className="primaryButton" type="button" onClick={() => void load()}>
            Retry
          </button>
        </div>
      </section>
    );
  }

  const { project, summary } = snapshot;

  return (
    <section className="memorySurface">
      <div className="memoryHero">
        <div>
          <div className="detailBadges">
            <span className="memoryTruthBadge">Governed truth</span>
            {project.status && (
              <span className={`memoryStatus ${statusClass(project.status)}`}>
                {titleCase(project.status)}
              </span>
            )}
          </div>
          <h2>{project.name || projectName}</h2>
          <p>
            {project.objective ||
              project.description ||
              "Governed Action Items, RAID and Decisions for this project."}
          </p>
        </div>
        <button className="secondaryButton" type="button" onClick={() => void load()}>
          ↻ Refresh memory
        </button>
      </div>

      <div className="memoryMetricGrid">
        <MemoryMetric
          label="Open actions"
          value={summary.action_items_open}
          detail={`${summary.action_items_total} total`}
          tone={summary.action_items_blocked > 0 ? "attention" : "default"}
        />
        <MemoryMetric
          label="Blocked actions"
          value={summary.action_items_blocked}
          detail="Require intervention"
          tone={summary.action_items_blocked > 0 ? "risk" : "good"}
        />
        <MemoryMetric
          label="Open RAID"
          value={
            summary.risks_open +
            summary.assumptions_open +
            summary.issues_open +
            summary.dependencies_open
          }
          detail={`${raidCount} governed records`}
          tone="default"
        />
        <MemoryMetric
          label="Approved decisions"
          value={summary.decisions_approved}
          detail={`${summary.decisions_total} total`}
          tone="good"
        />
      </div>

      <div className="memoryOverview">
        <div className="memoryOverviewItem">
          <span>Priority</span>
          <strong>{project.priority ? titleCase(project.priority) : "Not set"}</strong>
        </div>
        <div className="memoryOverviewItem">
          <span>Lifecycle phase</span>
          <strong>
            {project.lifecycle_phase ? titleCase(project.lifecycle_phase) : "Not set"}
          </strong>
        </div>
        <div className="memoryOverviewItem">
          <span>Methodology</span>
          <strong>{project.methodology || "Not set"}</strong>
        </div>
        <div className="memoryOverviewItem">
          <span>Forecast end</span>
          <strong>{dateLabel(project.forecast_end_date || project.planned_end_date)}</strong>
        </div>
      </div>

      <div className="memoryTabs" role="tablist" aria-label="Project Memory sections">
        <button
          type="button"
          className={tab === "actions" ? "active" : ""}
          onClick={() => setTab("actions")}
        >
          Action Items
          <span>{snapshot.action_items.length}</span>
        </button>
        <button
          type="button"
          className={tab === "raid" ? "active" : ""}
          onClick={() => setTab("raid")}
        >
          RAID
          <span>{raidCount}</span>
        </button>
        <button
          type="button"
          className={tab === "decisions" ? "active" : ""}
          onClick={() => setTab("decisions")}
        >
          Decisions
          <span>{snapshot.decisions.length}</span>
        </button>
      </div>

      <div className="memoryContent">
        {tab === "actions" && (
          <ActionItemsSection items={snapshot.action_items} />
        )}
        {tab === "raid" && (
          <RaidSection
            risks={snapshot.risks}
            assumptions={snapshot.assumptions}
            issues={snapshot.issues}
            dependencies={snapshot.dependencies}
          />
        )}
        {tab === "decisions" && (
          <DecisionsSection items={snapshot.decisions} />
        )}
      </div>

      <div className="memoryGovernanceNote">
        <span className="governanceDot" />
        <div>
          <strong>Read-only governed state</strong>
          <p>
            Changes enter Project Memory only after authorized Human Review in the
            Project Inbox.
          </p>
        </div>
      </div>
    </section>
  );
}

function MemoryMetric({
  label,
  value,
  detail,
  tone,
}: {
  label: string;
  value: number;
  detail: string;
  tone: "default" | "attention" | "risk" | "good";
}) {
  return (
    <div className={`memoryMetric ${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </div>
  );
}

function ActionItemsSection({ items }: { items: ActionItemView[] }) {
  if (!items.length) {
    return <MemoryEmpty text="No governed Action Items yet." />;
  }

  return (
    <div className="memoryTableWrap">
      <table className="memoryTable">
        <thead>
          <tr>
            <th>Action Item</th>
            <th>Status</th>
            <th>Priority</th>
            <th>Due</th>
            <th>Progress</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.id}>
              <td>
                <strong>{item.title}</strong>
                {item.description && <span>{item.description}</span>}
              </td>
              <td>
                <span className={`memoryStatus ${statusClass(item.status)}`}>
                  {titleCase(item.status)}
                </span>
              </td>
              <td>{item.priority ? titleCase(item.priority) : "—"}</td>
              <td>{dateLabel(item.due_date)}</td>
              <td className="progressCell">
                {item.progress_summary || "No progress summary"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RaidSection({
  risks,
  assumptions,
  issues,
  dependencies,
}: {
  risks: RiskView[];
  assumptions: AssumptionView[];
  issues: IssueView[];
  dependencies: DependencyView[];
}) {
  const sections = [
    {
      name: "Risks",
      code: "R",
      items: risks.map((item) => ({
        id: item.id,
        title: item.title,
        status: item.status,
        detail:
          item.mitigation ||
          item.description ||
          (item.impact ? `Impact: ${item.impact}` : "No mitigation recorded"),
        meta: item.category || item.impact || "Risk",
      })),
    },
    {
      name: "Assumptions",
      code: "A",
      items: assumptions.map((item) => ({
        id: item.id,
        title: item.title,
        status: item.status,
        detail: item.outcome || item.description || "Awaiting validation",
        meta: item.category || "Assumption",
      })),
    },
    {
      name: "Issues",
      code: "I",
      items: issues.map((item) => ({
        id: item.id,
        title: item.title,
        status: item.status,
        detail: item.resolution || item.description || "No resolution recorded",
        meta: item.severity ? `${titleCase(item.severity)} severity` : "Issue",
      })),
    },
    {
      name: "Dependencies",
      code: "D",
      items: dependencies.map((item) => ({
        id: item.id,
        title: item.title,
        status: item.status,
        detail: item.description || "External/internal dependency",
        meta: item.provider || item.criticality || "Dependency",
      })),
    },
  ];

  const hasItems = sections.some((section) => section.items.length);
  if (!hasItems) {
    return <MemoryEmpty text="No governed RAID records yet." />;
  }

  return (
    <div className="raidGrid">
      {sections.map((section) => (
        <section className="raidColumn" key={section.name}>
          <div className="raidHeader">
            <div className="raidCode">{section.code}</div>
            <div>
              <strong>{section.name}</strong>
              <span>{section.items.length} records</span>
            </div>
          </div>
          <div className="raidList">
            {section.items.length ? (
              section.items.map((item) => (
                <article className="raidCard" key={item.id}>
                  <div className="raidCardTop">
                    <span>{item.meta}</span>
                    <span className={`memoryStatus ${statusClass(item.status)}`}>
                      {titleCase(item.status)}
                    </span>
                  </div>
                  <strong>{item.title}</strong>
                  <p>{item.detail}</p>
                </article>
              ))
            ) : (
              <div className="raidEmpty">No records</div>
            )}
          </div>
        </section>
      ))}
    </div>
  );
}

function DecisionsSection({ items }: { items: DecisionView[] }) {
  if (!items.length) {
    return <MemoryEmpty text="No governed Decisions yet." />;
  }

  return (
    <div className="decisionTimeline">
      {items.map((item) => (
        <article className="decisionCard" key={item.id}>
          <div className="decisionMarker" />
          <div className="decisionBody">
            <div className="decisionHeader">
              <div>
                <span>{dateLabel(item.decision_date)}</span>
                <h3>{item.title}</h3>
              </div>
              <span className={`memoryStatus ${statusClass(item.status)}`}>
                {titleCase(item.status)}
              </span>
            </div>
            {item.description && <p>{item.description}</p>}
            {item.rationale && (
              <div className="decisionRationale">
                <span>Rationale</span>
                <p>{item.rationale}</p>
              </div>
            )}
            {item.expected_impact && (
              <div className="decisionImpact">
                <span>Expected impact</span>
                <p>{item.expected_impact}</p>
              </div>
            )}
          </div>
        </article>
      ))}
    </div>
  );
}

function MemoryEmpty({ text }: { text: string }) {
  return (
    <div className="memoryEmpty">
      <div className="emptyIcon">◇</div>
      <strong>Nothing recorded</strong>
      <span>{text}</span>
    </div>
  );
}
