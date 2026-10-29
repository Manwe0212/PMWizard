"use client";

import { useMemo, useState } from "react";

import type {
  GroundFact,
  ReportStatement,
  StatusReportAudience,
  StatusReportDraft,
} from "@/lib/types";

type Props = {
  canGenerate: boolean;
};

function titleCase(value: string): string {
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function dateLabel(value: string): string {
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(new Date(`${value}T12:00:00Z`));
}

function timestampLabel(value: string): string {
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

function scoreLabel(value: number | null): string {
  return value === null ? "—" : String(value);
}

function deltaLabel(value: number | null): string {
  if (value === null) return "—";
  return value > 0 ? `+${value}` : String(value);
}

async function generateDraft(
  lookbackDays: number,
  audience: StatusReportAudience,
): Promise<StatusReportDraft> {
  const response = await fetch("/api/status-report", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      lookback_days: lookbackDays,
      audience,
    }),
  });
  const payload = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(
      typeof payload?.detail === "string"
        ? payload.detail
        : `Unable to generate status report (${response.status})`,
    );
  }

  return payload as StatusReportDraft;
}

function plainText(draft: StatusReportDraft): string {
  const section = (title: string, statements: ReportStatement[]) => {
    if (!statements.length) return "";
    return [
      title,
      ...statements.map((item) => `- ${item.text}`),
      "",
    ].join("\n");
  };

  return [
    draft.title,
    `Period: ${draft.period_start} to ${draft.period_end}`,
    `Health: ${draft.health_band.toUpperCase()} ${scoreLabel(draft.health_score)}/100`,
    `Trend: ${titleCase(draft.trend_direction)} ${deltaLabel(draft.trend_score_delta)}`,
    "",
    section("Executive Summary", draft.content.executive_summary),
    section("Accomplishments", draft.content.accomplishments),
    section("Risks & Issues", draft.content.risks_and_issues),
    section("Decisions Needed", draft.content.decisions_needed),
    section("Next Steps", draft.content.next_steps),
    section("Data Quality Notes", draft.content.data_quality_notes),
    draft.disclaimer,
  ]
    .filter(Boolean)
    .join("\n");
}

export function StatusReportWorkspace({ canGenerate }: Props) {
  const [lookbackDays, setLookbackDays] = useState(7);
  const [audience, setAudience] =
    useState<StatusReportAudience>("executive");
  const [draft, setDraft] = useState<StatusReportDraft | null>(null);
  const [generating, setGenerating] = useState(false);
  const [copyLabel, setCopyLabel] = useState("Copy report");
  const [error, setError] = useState<string | null>(null);

  const factsById = useMemo(() => {
    if (!draft) return new Map<string, GroundFact>();
    return new Map(draft.facts.map((fact) => [fact.fact_id, fact]));
  }, [draft]);

  async function onGenerate() {
    if (!canGenerate) return;
    setGenerating(true);
    setError(null);
    try {
      setDraft(await generateDraft(lookbackDays, audience));
    } catch (requestError) {
      setDraft(null);
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Unable to generate status report.",
      );
    } finally {
      setGenerating(false);
    }
  }

  async function onCopy() {
    if (!draft) return;
    await navigator.clipboard.writeText(plainText(draft));
    setCopyLabel("Copied");
    window.setTimeout(() => setCopyLabel("Copy report"), 1500);
  }

  return (
    <section className="reportSurface">
      <div className="reportControlPanel">
        <div>
          <div className="detailBadges">
            <span className="memoryTruthBadge">Grounded generation</span>
            <span className="sourceOperationalBadge">Human review required</span>
          </div>
          <h2>AI Status Report Generator</h2>
          <p>
            Draft a concise status report from governed Project Memory, deterministic
            Health, captured Trends and Source telemetry. Pending AI suggestions are
            excluded from reportable truth.
          </p>
        </div>

        <div className="reportControls">
          <label>
            Audience
            <select
              value={audience}
              onChange={(event) =>
                setAudience(event.target.value as StatusReportAudience)
              }
              disabled={generating}
            >
              <option value="executive">Executive / Sponsor</option>
              <option value="project_team">Project Team</option>
            </select>
          </label>

          <label>
            Reporting window
            <select
              value={lookbackDays}
              onChange={(event) => setLookbackDays(Number(event.target.value))}
              disabled={generating}
            >
              <option value={7}>Last 7 days</option>
              <option value={14}>Last 14 days</option>
              <option value={21}>Last 21 days</option>
              <option value={30}>Last 30 days</option>
            </select>
          </label>

          <button
            className="primaryButton reportGenerateButton"
            type="button"
            disabled={!canGenerate || generating}
            onClick={() => void onGenerate()}
            title={
              canGenerate
                ? "Generate a grounded AI draft"
                : "Project review permission is required to generate reports"
            }
          >
            {generating ? "Generating…" : "✦ Generate draft"}
          </button>
        </div>
      </div>

      {!canGenerate && (
        <div className="reportPermissionNote">
          You can view this workspace, but project:review permission is required to
          generate a new AI draft.
        </div>
      )}

      {error && (
        <div className="errorBanner" role="alert">
          <span>!</span>
          <div>
            <strong>Status report generation failed</strong>
            <p>{error}</p>
          </div>
        </div>
      )}

      {!draft && !error && (
        <div className="reportEmpty">
          <div className="reportEmptyMark">✦</div>
          <h3>Generate a grounded project update</h3>
          <p>
            PMWizard will assemble an authorized fact packet first, then allow the
            configured AI provider to draft wording against that finite fact set.
          </p>
          <div className="reportFlow">
            <span>Project Memory</span>
            <b>+</b>
            <span>Health & Trends</span>
            <b>+</b>
            <span>Sources</span>
            <b>→</b>
            <span>Grounding Packet</span>
            <b>→</b>
            <span>AI Draft</span>
          </div>
        </div>
      )}

      {draft && (
        <>
          <div className="reportMetaHero">
            <div>
              <div className="detailBadges">
                <span className="memoryTruthBadge">
                  {draft.validation.grounded ? "Grounding validated" : "Unvalidated"}
                </span>
                <span className="sourceOperationalBadge">
                  {titleCase(draft.audience)}
                </span>
              </div>
              <h2>{draft.title}</h2>
              <p>
                {dateLabel(draft.period_start)} – {dateLabel(draft.period_end)}
              </p>
            </div>

            <div className="reportHealthStrip">
              <div>
                <span>Health</span>
                <strong>{scoreLabel(draft.health_score)}</strong>
                <small>{titleCase(draft.health_band)}</small>
              </div>
              <div>
                <span>Coverage</span>
                <strong>{draft.health_coverage_percent}%</strong>
                <small>Governed data</small>
              </div>
              <div>
                <span>Trend</span>
                <strong>{deltaLabel(draft.trend_score_delta)}</strong>
                <small>{titleCase(draft.trend_direction)}</small>
              </div>
            </div>

            <div className="reportMetaActions">
              <button
                className="secondaryButton"
                type="button"
                onClick={() => void onCopy()}
              >
                {copyLabel}
              </button>
              <small>
                {draft.provider} · {draft.model}
              </small>
              <small>{timestampLabel(draft.generated_at)}</small>
            </div>
          </div>

          <div className="reportValidationBar">
            <span>✓</span>
            <div>
              <strong>Grounding validation passed</strong>
              <p>
                {draft.validation.statement_count} statements ·{" "}
                {draft.validation.cited_fact_count} cited facts ·{" "}
                {draft.validation.available_fact_count} facts available
              </p>
            </div>
          </div>

          <div className="reportDocument">
            <ReportSection
              title="Executive Summary"
              statements={draft.content.executive_summary}
              factsById={factsById}
            />
            <ReportSection
              title="Accomplishments"
              statements={draft.content.accomplishments}
              factsById={factsById}
            />
            <ReportSection
              title="Risks & Issues"
              statements={draft.content.risks_and_issues}
              factsById={factsById}
            />
            <ReportSection
              title="Decisions Needed"
              statements={draft.content.decisions_needed}
              factsById={factsById}
            />
            <ReportSection
              title="Next Steps"
              statements={draft.content.next_steps}
              factsById={factsById}
            />
            <ReportSection
              title="Data Quality Notes"
              statements={draft.content.data_quality_notes}
              factsById={factsById}
            />
          </div>

          <section className="reportFactLedger">
            <div className="portfolioPanelHeader">
              <div>
                <h3>Grounding fact ledger</h3>
                <p>
                  Deterministic facts supplied to the model for this generation.
                </p>
              </div>
              <span>{draft.facts.length}</span>
            </div>
            <div className="reportFactGrid">
              {draft.facts.map((fact) => (
                <article className="reportFact" key={fact.fact_id}>
                  <div>
                    <b>{fact.fact_id}</b>
                    <span>{titleCase(fact.category)}</span>
                  </div>
                  <p>{fact.text}</p>
                  {fact.evidence_ids.length > 0 && (
                    <small>{fact.evidence_ids.length} supporting evidence ID(s)</small>
                  )}
                </article>
              ))}
            </div>
          </section>

          <div className="healthGovernanceNote reportDisclaimer">
            {draft.disclaimer}
          </div>
        </>
      )}
    </section>
  );
}

function ReportSection({
  title,
  statements,
  factsById,
}: {
  title: string;
  statements: ReportStatement[];
  factsById: Map<string, GroundFact>;
}) {
  return (
    <section className="reportSection">
      <h3>{title}</h3>
      {statements.length ? (
        <div className="reportStatementList">
          {statements.map((statement, index) => (
            <article className="reportStatement" key={`${title}-${index}`}>
              <p>{statement.text}</p>
              <div className="reportFactRefs">
                {statement.fact_ids.map((factId) => {
                  const fact = factsById.get(factId);
                  return (
                    <span key={factId} title={fact?.text ?? factId}>
                      {factId}
                    </span>
                  );
                })}
              </div>
            </article>
          ))}
        </div>
      ) : (
        <p className="reportSectionEmpty">No grounded statements for this section.</p>
      )}
    </section>
  );
}
