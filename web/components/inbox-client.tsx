"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import { ActivityWorkspace } from "@/components/activity-workspace";
import { AttentionCenterWorkspace } from "@/components/attention-center-workspace";
import { AutomationWorkspace } from "@/components/automation-workspace";
import { ExecutiveDashboard } from "@/components/executive-dashboard";
import { HealthWorkspace } from "@/components/health-workspace";
import { MemoryWorkspace } from "@/components/memory-workspace";
import { PortfolioWorkspace } from "@/components/portfolio-workspace";
import { SourcesWorkspace } from "@/components/sources-workspace";
import { StatusReportWorkspace } from "@/components/status-report-workspace";
import type {
  AttentionCenterSnapshot,
  InboxListResponse,
  InboxSuggestionDetail,
  InboxSuggestionSummary,
  ProjectAccess,
  ReviewResponse,
  ReviewStatus,
} from "@/lib/types";

type Props = {
  projectId: string;
  projectName: string;
  projects: ProjectAccess[];
  userName: string;
  userEmail: string;
  onProjectChange: (projectId: string) => Promise<void>;
  onLogout: () => Promise<void>;
  projectSwitching: boolean;
};

const ACTION_STATUSES = [
  "not_started",
  "in_progress",
  "blocked",
  "pending_external",
  "ready_for_review",
  "completed",
  "cancelled",
];

function titleCase(value: string): string {
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function confidenceLabel(confidence: number): string {
  if (confidence >= 0.9) return "High confidence";
  if (confidence >= 0.75) return "Medium confidence";
  return "Review carefully";
}

function sourceLabel(source: string): string {
  if (source === "microsoft_graph_mail") return "Outlook";
  if (source === "microsoft_graph_sharepoint") return "SharePoint";
  return titleCase(source);
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

async function jsonRequest<T>(
  input: RequestInfo | URL,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(input, init);
  const payload = await response.json().catch(() => ({}));

  if (!response.ok) {
    const detail =
      typeof payload?.detail === "string"
        ? payload.detail
        : `Request failed with status ${response.status}`;
    throw new Error(detail);
  }

  return payload as T;
}

export function InboxClient({
  projectId,
  projectName,
  projects,
  userName,
  userEmail,
  onProjectChange,
  onLogout,
  projectSwitching,
}: Props) {
  const [items, setItems] = useState<InboxSuggestionSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<InboxSuggestionDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editMode, setEditMode] = useState(false);
  const [editStatus, setEditStatus] = useState("in_progress");
  const [editSummary, setEditSummary] = useState("");
  const [reviewerNote, setReviewerNote] = useState("");
  const [attentionUnread, setAttentionUnread] = useState(0);
  const [activeView, setActiveView] = useState<
    "executive" | "portfolio" | "attention" | "health" | "reports" | "automations" | "inbox" | "memory" | "sources" | "activity"
  >("executive");

  const loadInbox = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await jsonRequest<InboxListResponse>("/api/inbox");
      setItems(response.items);
      setSelectedId((current) => {
        if (current && response.items.some((item) => item.id === current)) {
          return current;
        }
        return response.items[0]?.id ?? null;
      });
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Unable to load Project Inbox.",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  const loadAttentionSummary = useCallback(async () => {
    try {
      const response = await jsonRequest<AttentionCenterSnapshot>("/api/attention");
      setAttentionUnread(response.summary.unread);
    } catch {
      setAttentionUnread(0);
    }
  }, []);

  const loadDetail = useCallback(async (suggestionId: string) => {
    setDetailLoading(true);
    setError(null);
    try {
      const response = await jsonRequest<InboxSuggestionDetail>(
        `/api/inbox/${suggestionId}`,
      );
      setDetail(response);
      const proposedStatus = response.suggestion.proposed_changes.status;
      const proposedSummary =
        response.suggestion.proposed_changes.progress_summary;
      setEditStatus(
        typeof proposedStatus === "string"
          ? proposedStatus
          : response.target_action_item?.status ?? "in_progress",
      );
      setEditSummary(
        typeof proposedSummary === "string"
          ? proposedSummary
          : response.target_action_item?.progress_summary ?? "",
      );
      setReviewerNote("");
      setEditMode(false);
    } catch (requestError) {
      setDetail(null);
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Unable to load suggestion detail.",
      );
    } finally {
      setDetailLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadInbox();
  }, [loadInbox]);

  useEffect(() => {
    void loadAttentionSummary();
  }, [activeView, projectId, loadAttentionSummary]);

  useEffect(() => {
    if (selectedId) {
      void loadDetail(selectedId);
    } else {
      setDetail(null);
    }
  }, [selectedId, loadDetail]);

  const averageConfidence = useMemo(() => {
    if (!items.length) return 0;
    return (
      items.reduce((total, item) => total + item.confidence, 0) / items.length
    );
  }, [items]);

  const deferredCount = useMemo(
    () => items.filter((item) => item.review_status === "deferred").length,
    [items],
  );

  const canReviewProject =
    projects
      .find((project) => project.project_id === projectId)
      ?.permissions.includes("project:review") ?? false;

  async function submitReview(
    status: ReviewStatus,
    finalChanges: Record<string, unknown> = {},
  ) {
    if (!selectedId) return;
    setActionLoading(true);
    setError(null);

    try {
      await jsonRequest<ReviewResponse>(
        `/api/inbox/${selectedId}/review`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            status,
            reviewer_note: reviewerNote || null,
            final_changes: finalChanges,
          }),
        },
      );

      await loadInbox();
      await loadAttentionSummary();

      if (status === "deferred") {
        await loadDetail(selectedId);
      } else {
        setDetail(null);
        setEditMode(false);
      }
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Unable to submit review.",
      );
    } finally {
      setActionLoading(false);
    }
  }

  async function submitEdit(event: FormEvent) {
    event.preventDefault();
    await submitReview("edited", {
      status: editStatus,
      progress_summary: editSummary,
    });
  }

  return (
    <div className="appShell">
      <aside className="sidebar">
        <div>
          <div className="brand">
            <div className="brandMark">P</div>
            <div>
              <strong>PMWizard</strong>
              <span>Project Intelligence</span>
            </div>
          </div>

          <nav className="nav">
            <button
              className={`navItem ${activeView === "executive" ? "active" : ""}`}
              type="button"
              onClick={() => setActiveView("executive")}
            >
              <span className="navIcon">⌂</span>
              Executive Dashboard
            </button>
            <button
              className={`navItem ${activeView === "portfolio" ? "active" : ""}`}
              type="button"
              onClick={() => setActiveView("portfolio")}
            >
              <span className="navIcon">▦</span>
              Program & Portfolio
            </button>
            <button
              className={`navItem ${activeView === "attention" ? "active" : ""}`}
              type="button"
              onClick={() => setActiveView("attention")}
            >
              <span className="navIcon">!</span>
              Attention Center
              {attentionUnread > 0 && (
                <span className="navCount">{attentionUnread}</span>
              )}
            </button>
            <button
              className={`navItem ${activeView === "health" ? "active" : ""}`}
              type="button"
              onClick={() => setActiveView("health")}
            >
              <span className="navIcon">◉</span>
              Project Health
            </button>
            <button
              className={`navItem ${activeView === "reports" ? "active" : ""}`}
              type="button"
              onClick={() => setActiveView("reports")}
            >
              <span className="navIcon">✦</span>
              Status Reports
            </button>
            <button
              className={`navItem ${activeView === "automations" ? "active" : ""}`}
              type="button"
              onClick={() => setActiveView("automations")}
            >
              <span className="navIcon">⚙</span>
              Automations
            </button>
            <button
              className={`navItem ${activeView === "inbox" ? "active" : ""}`}
              type="button"
              onClick={() => setActiveView("inbox")}
            >
              <span className="navIcon">⌁</span>
              Project Inbox
              {items.length > 0 && <span className="navCount">{items.length}</span>}
            </button>
            <button
              className={`navItem ${activeView === "activity" ? "active" : ""}`}
              type="button"
              onClick={() => setActiveView("activity")}
            >
              <span className="navIcon">≡</span>
              Activity Timeline
            </button>
            <button
              className={`navItem ${activeView === "memory" ? "active" : ""}`}
              type="button"
              onClick={() => setActiveView("memory")}
            >
              <span className="navIcon">◇</span>
              Project Memory
            </button>
            <button
              className={`navItem ${activeView === "sources" ? "active" : ""}`}
              type="button"
              onClick={() => setActiveView("sources")}
            >
              <span className="navIcon">↗</span>
              Sources
            </button>
          </nav>
        </div>

        <div className="sidebarFooter">
          <div className="governanceDot" />
          <div>
            <strong>Human governed</strong>
            <span>AI proposes. You decide.</span>
          </div>
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <div>
            <div className="eyebrow">
              {activeView === "executive"
                ? "Executive workspace"
                : activeView === "portfolio"
                  ? "Cross-project workspace"
                  : activeView === "attention"
                    ? "Personal attention workspace"
                    : "Project workspace"}
            </div>
            <h1>
              {activeView === "executive"
                ? "Executive Dashboard"
                : activeView === "portfolio"
                  ? "Program & Portfolio"
                  : activeView === "attention"
                    ? "Attention Center"
                    : activeView === "health"
                  ? "Project Health"
                  : activeView === "reports"
                    ? "Status Reports"
                    : activeView === "automations"
                      ? "Automations"
                      : activeView === "inbox"
                      ? "Project Inbox"
                    : activeView === "activity"
                      ? "Activity Timeline"
                    : activeView === "memory"
                      ? "Project Memory"
                      : "Sources"}
            </h1>
            <p>
              {activeView === "executive"
                ? "See what requires attention across your authorized project landscape."
                : activeView === "portfolio"
                  ? "Roll up authorized project health, trends, hierarchy, and shared signals."
                  : activeView === "attention"
                    ? "Prioritize active project conditions without changing governed truth."
                    : activeView === "health"
                  ? "Understand project health through deterministic, explainable signals."
                  : activeView === "reports"
                    ? "Generate grounded AI status-report drafts from governed project truth."
                    : activeView === "automations"
                      ? "Schedule recurring intelligence work without moving governance into the request path."
                      : activeView === "inbox"
                      ? "Review evidence-backed updates before they become project truth."
                    : activeView === "activity"
                      ? "Explore the ordered, evidence-aware record of project activity."
                    : activeView === "memory"
                      ? "Inspect the governed project truth produced by authorized review."
                      : "Monitor authorized source health, sync history, and ingestion telemetry."}
            </p>
          </div>
          <div className="topbarControls">
            {activeView === "executive" || activeView === "portfolio" ? (
              <div className="projectPill portfolioScopePill">
                <span className="projectDot" />
                <div>
                  <small>Scope</small>
                  <strong>{projects.length} authorized projects</strong>
                </div>
              </div>
            ) : (
              <div className="projectPill projectSelectorPill">
                <span className="projectDot" />
                <div>
                  <small>Project</small>
                  <select
                    className="projectSelect"
                    value={projectId}
                    disabled={projectSwitching}
                    aria-label="Select project"
                    onChange={(event) =>
                      void onProjectChange(event.target.value)
                    }
                  >
                    {projects.map((project) => (
                      <option key={project.project_id} value={project.project_id}>
                        {project.name}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
            )}
            <div className="accountPill" title={userEmail}>
              <div className="accountAvatar">
                {userName.trim().slice(0, 1).toUpperCase()}
              </div>
              <div>
                <small>Signed in</small>
                <strong>{userName}</strong>
              </div>
              <button
                type="button"
                className="logoutButton"
                onClick={() => void onLogout()}
                aria-label="Sign out"
                title="Sign out"
              >
                ↪
              </button>
            </div>
          </div>
        </header>

        {activeView === "executive" ? (
          <ExecutiveDashboard
            onOpenProject={async (nextProjectId, target) => {
              await onProjectChange(nextProjectId);
              setActiveView(target);
            }}
          />
        ) : activeView === "portfolio" ? (
          <PortfolioWorkspace
            onOpenProject={async (nextProjectId) => {
              await onProjectChange(nextProjectId);
              setActiveView("health");
            }}
          />
        ) : activeView === "attention" ? (
          <AttentionCenterWorkspace
            onNavigate={(target) => setActiveView(target)}
            onUnreadChange={setAttentionUnread}
          />
        ) : activeView === "health" ? (
          <HealthWorkspace canCapture={canReviewProject} />
        ) : activeView === "reports" ? (
          <StatusReportWorkspace canGenerate={canReviewProject} />
        ) : activeView === "automations" ? (
          <AutomationWorkspace canManage={canReviewProject} />
        ) : activeView === "inbox" ? (
          <>
          <section className="metrics" aria-label="Inbox summary">
            <div className="metric">
              <span>Needs attention</span>
              <strong>{items.length}</strong>
              <small>Pending and deferred suggestions</small>
            </div>
            <div className="metric">
              <span>Average confidence</span>
              <strong>
                {items.length ? `${Math.round(averageConfidence * 100)}%` : "—"}
              </strong>
              <small>Across visible suggestions</small>
            </div>
            <div className="metric">
              <span>Deferred</span>
              <strong>{deferredCount}</strong>
              <small>Waiting for a later decision</small>
            </div>
            <div className="metric governanceMetric">
              <span>Governance mode</span>
              <strong>Human</strong>
              <small>No autonomous state changes</small>
            </div>
          </section>
  
          {error && (
            <div className="errorBanner" role="alert">
              <span>!</span>
              <div>
                <strong>PMWizard needs attention</strong>
                <p>{error}</p>
              </div>
              <button type="button" onClick={() => void loadInbox()}>
                Retry
              </button>
            </div>
          )}
  
          <section className="workspace">
            <div className="queuePanel">
              <div className="panelHeader">
                <div>
                  <h2>Review queue</h2>
                  <p>{items.length} suggestions visible to you</p>
                </div>
                <button
                  className="iconButton"
                  type="button"
                  onClick={() => void loadInbox()}
                  disabled={loading}
                  aria-label="Refresh inbox"
                  title="Refresh inbox"
                >
                  ↻
                </button>
              </div>
  
              <div className="queue">
                {loading ? (
                  <>
                    <div className="skeletonCard" />
                    <div className="skeletonCard" />
                    <div className="skeletonCard" />
                  </>
                ) : items.length === 0 ? (
                  <div className="emptyState">
                    <div className="emptyIcon">✓</div>
                    <h3>Inbox clear</h3>
                    <p>No authorized suggestions require your attention right now.</p>
                  </div>
                ) : (
                  items.map((item) => (
                    <button
                      key={item.id}
                      className={`queueCard ${selectedId === item.id ? "selected" : ""}`}
                      type="button"
                      onClick={() => setSelectedId(item.id)}
                    >
                      <div className="queueCardTop">
                        <span className={`statusTag ${item.review_status}`}>
                          {item.review_status === "deferred" ? "Deferred" : "Review"}
                        </span>
                        <span className="confidence">
                          {Math.round(item.confidence * 100)}%
                        </span>
                      </div>
                      <strong>{titleCase(item.suggestion_type)}</strong>
                      <p>{item.reason}</p>
                      <div className="proposedRow">
                        <span>Suggested</span>
                        <b>
                          {typeof item.proposed_changes.status === "string"
                            ? titleCase(item.proposed_changes.status)
                            : "Project update"}
                        </b>
                      </div>
                      <div className="queueMeta">
                        <span>
                          {item.evidence_count} evidence
                          {item.evidence_count === 1 ? "" : "s"}
                        </span>
                        <span>•</span>
                        <span>{formatDate(item.created_at)}</span>
                      </div>
                    </button>
                  ))
                )}
              </div>
            </div>
  
            <div className="detailPanel">
              {!selectedId ? (
                <div className="detailEmpty">
                  <div className="detailEmptyMark">⌁</div>
                  <h2>Select a suggestion</h2>
                  <p>Evidence, current state and proposed changes will appear here.</p>
                </div>
              ) : detailLoading || !detail ? (
                <div className="detailLoading">
                  <div className="skeletonLine wide" />
                  <div className="skeletonLine" />
                  <div className="skeletonBlock" />
                  <div className="skeletonBlock" />
                </div>
              ) : (
                <>
                  <div className="detailHeader">
                    <div>
                      <div className="detailBadges">
                        <span className={`statusTag ${detail.suggestion.review_status}`}>
                          {titleCase(detail.suggestion.review_status)}
                        </span>
                        <span className="sourceTag">
                          {detail.suggestion.evidence_sources
                            .map(sourceLabel)
                            .join(" + ") || "Evidence"}
                        </span>
                      </div>
                      <h2>
                        {detail.target_action_item?.title ??
                          titleCase(detail.suggestion.suggestion_type)}
                      </h2>
                      <p>{detail.suggestion.reason}</p>
                    </div>
                    <div className="confidenceRing">
                      <strong>
                        {Math.round(detail.suggestion.confidence * 100)}%
                      </strong>
                      <span>{confidenceLabel(detail.suggestion.confidence)}</span>
                    </div>
                  </div>
  
                  <div className="comparison">
                    <div className="stateCard current">
                      <span>Current state</span>
                      <strong>
                        {titleCase(
                          detail.target_action_item?.status ?? "Not available",
                        )}
                      </strong>
                      <p>
                        {detail.target_action_item?.progress_summary ||
                          "No current progress summary."}
                      </p>
                    </div>
                    <div className="stateArrow">→</div>
                    <div className="stateCard proposed">
                      <span>PMWizard suggests</span>
                      <strong>
                        {typeof detail.suggestion.proposed_changes.status === "string"
                          ? titleCase(detail.suggestion.proposed_changes.status)
                          : "Update project memory"}
                      </strong>
                      <p>
                        {typeof detail.suggestion.proposed_changes.progress_summary ===
                        "string"
                          ? detail.suggestion.proposed_changes.progress_summary
                          : "Review proposed changes below."}
                      </p>
                    </div>
                  </div>
  
                  <section className="evidenceSection">
                    <div className="sectionTitle">
                      <div>
                        <h3>Supporting evidence</h3>
                        <p>
                          {detail.evidence.length} authorized source
                          {detail.evidence.length === 1 ? "" : "s"}
                        </p>
                      </div>
                    </div>
  
                    <div className="evidenceList">
                      {detail.evidence.map((evidence) => (
                        <article className="evidenceCard" key={evidence.id}>
                          <div className="evidenceHeader">
                            <div>
                              <span className="sourceTag">
                                {sourceLabel(
                                  evidence.source_system ?? evidence.source_type,
                                )}
                              </span>
                              <strong>{evidence.author || "Unknown author"}</strong>
                            </div>
                            <time>{formatDate(evidence.captured_at)}</time>
                          </div>
                          <blockquote>
                            {evidence.content_excerpt || "No excerpt available."}
                          </blockquote>
                          {evidence.source_reference && (
                            <a
                              href={evidence.source_reference}
                              target="_blank"
                              rel="noreferrer"
                            >
                              Open source ↗
                            </a>
                          )}
                        </article>
                      ))}
                    </div>
                  </section>
  
                  {editMode ? (
                    <form className="editForm" onSubmit={submitEdit}>
                      <div className="editHeader">
                        <div>
                          <h3>Edit before applying</h3>
                          <p>Your values become the governed project state.</p>
                        </div>
                        <button
                          type="button"
                          className="textButton"
                          onClick={() => setEditMode(false)}
                        >
                          Cancel
                        </button>
                      </div>
  
                      <label>
                        Status
                        <select
                          value={editStatus}
                          onChange={(event) => setEditStatus(event.target.value)}
                        >
                          {ACTION_STATUSES.map((status) => (
                            <option key={status} value={status}>
                              {titleCase(status)}
                            </option>
                          ))}
                        </select>
                      </label>
  
                      <label>
                        Progress summary
                        <textarea
                          value={editSummary}
                          onChange={(event) => setEditSummary(event.target.value)}
                          rows={4}
                          required
                        />
                      </label>
  
                      <label>
                        Reviewer note <span>optional</span>
                        <textarea
                          value={reviewerNote}
                          onChange={(event) => setReviewerNote(event.target.value)}
                          rows={2}
                          placeholder="Why did you change the AI proposal?"
                        />
                      </label>
  
                      <button
                        className="primaryButton full"
                        type="submit"
                        disabled={actionLoading}
                      >
                        {actionLoading ? "Applying…" : "Apply edited decision"}
                      </button>
                    </form>
                  ) : (
                    <div className="reviewBar">
                      <div className="reviewCopy">
                        <strong>Your decision governs Project Memory</strong>
                        <span>
                          Accept the proposal, correct it, reject it, or decide later.
                        </span>
                      </div>
                      <div className="reviewActions">
                        <button
                          className="secondaryButton"
                          type="button"
                          onClick={() => void submitReview("deferred")}
                          disabled={actionLoading}
                        >
                          Defer
                        </button>
                        <button
                          className="dangerButton"
                          type="button"
                          onClick={() => void submitReview("rejected")}
                          disabled={actionLoading}
                        >
                          Reject
                        </button>
                        <button
                          className="secondaryButton"
                          type="button"
                          onClick={() => setEditMode(true)}
                          disabled={actionLoading}
                        >
                          Edit
                        </button>
                        <button
                          className="primaryButton"
                          type="button"
                          onClick={() => void submitReview("accepted")}
                          disabled={actionLoading}
                        >
                          {actionLoading ? "Applying…" : "Accept"}
                        </button>
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>
          </section>
  
          </>
        ) : activeView === "activity" ? (
          <ActivityWorkspace />
        ) : activeView === "memory" ? (
          <MemoryWorkspace projectName={projectName} />
        ) : (
          <SourcesWorkspace canManage={canReviewProject} />
        )}
      </main>
    </div>
  );
}
