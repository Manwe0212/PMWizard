"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import type {
  CrossProjectSignal,
  PortfolioRollup,
  ProgramPortfolioOverview,
  ProgramRollup,
  ProjectHealthBand,
  ProjectRollupItem,
  RollupSummary,
  TrendDirection,
} from "@/lib/types";

type Props = {
  onOpenProject: (projectId: string) => void | Promise<void>;
};

function titleCase(value: string): string {
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function scoreLabel(score: number | null): string {
  return score === null ? "—" : String(score);
}

function deltaLabel(value: number | null): string {
  if (value === null) return "—";
  return value > 0 ? `+${value}` : String(value);
}

function bandLabel(band: ProjectHealthBand): string {
  return band === "insufficient_data" ? "Insufficient data" : titleCase(band);
}

function trendLabel(direction: TrendDirection): string {
  return direction === "insufficient_history"
    ? "No trend yet"
    : titleCase(direction);
}

async function loadOverview(): Promise<ProgramPortfolioOverview> {
  const response = await fetch("/api/intelligence/overview", {
    cache: "no-store",
  });
  const payload = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(
      typeof payload?.detail === "string"
        ? payload.detail
        : `Unable to load Program & Portfolio Intelligence (${response.status})`,
    );
  }
  return payload as ProgramPortfolioOverview;
}

export function PortfolioWorkspace({ onOpenProject }: Props) {
  const [overview, setOverview] = useState<ProgramPortfolioOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setOverview(await loadOverview());
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Unable to load Program & Portfolio Intelligence.",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const attentionCount = useMemo(() => {
    if (!overview) return 0;
    return overview.attention_projects.filter(
      (project) =>
        project.health_band === "red" ||
        project.health_band === "amber" ||
        project.trend_direction === "deteriorating",
    ).length;
  }, [overview]);

  if (loading) {
    return (
      <section className="portfolioSurface">
        <div className="memoryLoading">
          <div className="skeletonLine wide" />
          <div className="portfolioMetricGrid">
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

  if (error || !overview) {
    return (
      <section className="portfolioSurface">
        <div className="memoryError">
          <div className="detailEmptyMark">!</div>
          <h2>Program & Portfolio Intelligence unavailable</h2>
          <p>{error ?? "No cross-project intelligence is available."}</p>
          <button className="primaryButton" type="button" onClick={() => void load()}>
            Retry
          </button>
        </div>
      </section>
    );
  }

  const { summary } = overview;

  return (
    <section className="portfolioSurface">
      <div className="portfolioHero">
        <div className="portfolioRollupScore">
          <div className={`portfolioScoreRing ${summary.band}`}>
            <div>
              <strong>{scoreLabel(summary.score)}</strong>
              <span>/100</span>
            </div>
          </div>
          <span className={`healthBandBadge ${summary.band}`}>
            {bandLabel(summary.band)}
          </span>
        </div>

        <div className="portfolioHeroCopy">
          <div className="detailBadges">
            <span className="memoryTruthBadge">Authorized rollup</span>
            <span className="sourceOperationalBadge">
              {summary.projects_total} visible projects
            </span>
          </div>
          <h2>Program & Portfolio Intelligence</h2>
          <p>
            Roll up governed health and trends across the projects your account is
            authorized to read. Hidden projects never participate in the score or
            cross-project signals.
          </p>

          <div className="coverageRow">
            <div>
              <span>Average assessment coverage</span>
              <strong>{summary.average_coverage_percent}%</strong>
            </div>
            <div className="coverageTrack">
              <span style={{ width: `${summary.average_coverage_percent}%` }} />
            </div>
            <small>
              {summary.projects_scored}/{summary.projects_total} projects have a
              reliable scored band.
            </small>
          </div>
        </div>

        <button className="secondaryButton" type="button" onClick={() => void load()}>
          ↻ Refresh rollup
        </button>
      </div>

      <div className="portfolioMetricGrid">
        <ExecutiveMetric
          label="Authorized projects"
          value={summary.projects_total}
          detail={`${summary.projects_scored} reliably scored`}
        />
        <ExecutiveMetric
          label="Needs attention"
          value={attentionCount}
          detail={`${summary.red} red · ${summary.deteriorating} deteriorating`}
          tone={attentionCount > 0 ? "risk" : "good"}
        />
        <ExecutiveMetric
          label="Healthy"
          value={summary.green}
          detail={`${summary.improving} improving`}
          tone="good"
        />
        <ExecutiveMetric
          label="Cross-project signals"
          value={overview.cross_project_signals.length}
          detail="Repeated active risks/dependencies"
          tone={overview.cross_project_signals.length > 0 ? "attention" : "default"}
        />
      </div>

      <div className="portfolioMainGrid">
        <section className="portfolioPanel attentionPanel">
          <div className="portfolioPanelHeader">
            <div>
              <h3>Projects requiring attention</h3>
              <p>Prioritized by red health and deteriorating trend.</p>
            </div>
            <span>{overview.attention_projects.length}</span>
          </div>

          {overview.attention_projects.length ? (
            <div className="attentionProjectList">
              {overview.attention_projects.map((project) => (
                <AttentionProject
                  key={project.project_id}
                  project={project}
                  onOpen={() => void onOpenProject(project.project_id)}
                />
              ))}
            </div>
          ) : (
            <ExecutiveEmpty text="No authorized projects are available yet." />
          )}
        </section>

        <section className="portfolioPanel signalPanel">
          <div className="portfolioPanelHeader">
            <div>
              <h3>Cross-project signals</h3>
              <p>Exact normalized active RAID titles repeated across projects.</p>
            </div>
            <span>{overview.cross_project_signals.length}</span>
          </div>

          {overview.cross_project_signals.length ? (
            <div className="crossSignalList">
              {overview.cross_project_signals.slice(0, 8).map((signal) => (
                <CrossSignal key={`${signal.signal_type}-${signal.title}`} signal={signal} />
              ))}
            </div>
          ) : (
            <ExecutiveEmpty text="No repeated active Risk or Dependency titles across visible projects." />
          )}
        </section>
      </div>

      <section className="portfolioHierarchy">
        <div className="portfolioPanelHeader">
          <div>
            <h3>Portfolio hierarchy</h3>
            <p>Authorized Portfolio → Program → Project rollups.</p>
          </div>
        </div>

        <div className="portfolioHierarchyList">
          {overview.portfolios.map((portfolio) => (
            <PortfolioGroup
              key={portfolio.id}
              portfolio={portfolio}
              onOpenProject={onOpenProject}
            />
          ))}

          {overview.standalone_programs.map((program) => (
            <ProgramGroup
              key={program.id}
              program={program}
              standalone
              onOpenProject={onOpenProject}
            />
          ))}

          {overview.standalone_projects.length > 0 && (
            <div className="standaloneProjectGroup">
              <div className="hierarchyGroupHeader">
                <div>
                  <span className="hierarchyType">Standalone</span>
                  <h4>Projects without Program / Portfolio</h4>
                </div>
                <RollupMini summary={rollupFromProjects(overview.standalone_projects)} />
              </div>
              <div className="portfolioProjectTable">
                {overview.standalone_projects.map((project) => (
                  <ProjectRow
                    key={project.project_id}
                    project={project}
                    onOpen={() => void onOpenProject(project.project_id)}
                  />
                ))}
              </div>
            </div>
          )}

          {overview.portfolios.length === 0 &&
            overview.standalone_programs.length === 0 &&
            overview.standalone_projects.length === 0 && (
              <ExecutiveEmpty text="No authorized projects have been added to the hierarchy." />
            )}
        </div>
      </section>

      <div className="sourceSecurityNote">
        <span>⌁</span>
        <div>
          <strong>Authorization-preserving rollup</strong>
          <p>
            Program and Portfolio Intelligence is computed only from project
            memberships carrying project:read. Counts and shared signals never
            reveal projects outside the current authorized scope.
          </p>
        </div>
      </div>
    </section>
  );
}

function ExecutiveMetric({
  label,
  value,
  detail,
  tone = "default",
}: {
  label: string;
  value: number;
  detail: string;
  tone?: "default" | "risk" | "good" | "attention";
}) {
  return (
    <div className={`memoryMetric ${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </div>
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
    <button className="attentionProject" type="button" onClick={onOpen}>
      <div className={`attentionBand ${project.health_band}`} />
      <div className="attentionProjectCopy">
        <div className="attentionTitleRow">
          <strong>{project.name}</strong>
          <span className={`healthBandBadge ${project.health_band}`}>
            {bandLabel(project.health_band)}
          </span>
        </div>
        <span>
          {project.program_name || project.portfolio_name || "Standalone project"}
        </span>
        {project.top_drivers.length > 0 && (
          <small>{project.top_drivers.slice(0, 2).join(" · ")}</small>
        )}
      </div>
      <div className="attentionScore">
        <strong>{scoreLabel(project.health_score)}</strong>
        <span className={`trendMini ${project.trend_direction}`}>
          {trendLabel(project.trend_direction)}
          {project.trend_score_delta !== null &&
            ` ${deltaLabel(project.trend_score_delta)}`}
        </span>
      </div>
    </button>
  );
}

function CrossSignal({ signal }: { signal: CrossProjectSignal }) {
  return (
    <article className="crossSignal">
      <div className={`crossSignalIcon ${signal.signal_type}`}>
        {signal.signal_type === "risk" ? "R" : "D"}
      </div>
      <div>
        <div className="crossSignalTitle">
          <strong>{signal.title}</strong>
          <span>{signal.project_count} projects</span>
        </div>
        <p>{signal.project_names.join(" · ")}</p>
        <small>
          {signal.statuses.map(titleCase).join(", ")}
          {signal.severity_labels.length
            ? ` · ${signal.severity_labels.map(titleCase).join(", ")}`
            : ""}
        </small>
      </div>
    </article>
  );
}

function PortfolioGroup({
  portfolio,
  onOpenProject,
}: {
  portfolio: PortfolioRollup;
  onOpenProject: Props["onOpenProject"];
}) {
  return (
    <article className="portfolioGroup">
      <div className="hierarchyGroupHeader portfolioHeader">
        <div>
          <span className="hierarchyType">Portfolio</span>
          <h4>{portfolio.name}</h4>
          {portfolio.description && <p>{portfolio.description}</p>}
        </div>
        <RollupMini summary={portfolio.summary} />
      </div>

      {portfolio.strategic_objectives.length > 0 && (
        <div className="objectiveChips">
          {portfolio.strategic_objectives.map((objective) => (
            <span key={objective}>{objective}</span>
          ))}
        </div>
      )}

      <div className="programGrid">
        {portfolio.programs.map((program) => (
          <ProgramGroup
            key={program.id}
            program={program}
            onOpenProject={onOpenProject}
          />
        ))}
      </div>

      {portfolio.direct_projects.length > 0 && (
        <div className="directProjects">
          <span className="directProjectsLabel">Direct portfolio projects</span>
          <div className="portfolioProjectTable">
            {portfolio.direct_projects.map((project) => (
              <ProjectRow
                key={project.project_id}
                project={project}
                onOpen={() => void onOpenProject(project.project_id)}
              />
            ))}
          </div>
        </div>
      )}
    </article>
  );
}

function ProgramGroup({
  program,
  onOpenProject,
  standalone = false,
}: {
  program: ProgramRollup;
  onOpenProject: Props["onOpenProject"];
  standalone?: boolean;
}) {
  return (
    <article className={`programGroup ${standalone ? "standaloneProgram" : ""}`}>
      <div className="hierarchyGroupHeader">
        <div>
          <span className="hierarchyType">Program</span>
          <h4>{program.name}</h4>
          {program.description && <p>{program.description}</p>}
        </div>
        <RollupMini summary={program.summary} />
      </div>
      <div className="portfolioProjectTable">
        {program.projects.map((project) => (
          <ProjectRow
            key={project.project_id}
            project={project}
            onOpen={() => void onOpenProject(project.project_id)}
          />
        ))}
      </div>
    </article>
  );
}

function ProjectRow({
  project,
  onOpen,
}: {
  project: ProjectRollupItem;
  onOpen: () => void;
}) {
  return (
    <button className="portfolioProjectRow" type="button" onClick={onOpen}>
      <div>
        <strong>{project.name}</strong>
        <span>
          {project.priority ? `${titleCase(project.priority)} priority` : "Priority not set"}
          {" · "}
          {project.health_coverage_percent}% coverage
        </span>
      </div>
      <span className={`healthBandBadge ${project.health_band}`}>
        {bandLabel(project.health_band)}
      </span>
      <strong className="projectRollupScore">{scoreLabel(project.health_score)}</strong>
      <span className={`trendMini ${project.trend_direction}`}>
        {trendLabel(project.trend_direction)}
      </span>
      <b>Open →</b>
    </button>
  );
}

function RollupMini({ summary }: { summary: RollupSummary }) {
  return (
    <div className="rollupMini">
      <span className={`healthBandBadge ${summary.band}`}>
        {bandLabel(summary.band)}
      </span>
      <strong>{scoreLabel(summary.score)}</strong>
      <small>{summary.projects_total} projects</small>
    </div>
  );
}

function ExecutiveEmpty({ text }: { text: string }) {
  return (
    <div className="executiveEmpty">
      <div className="emptyIcon">◇</div>
      <strong>No signal yet</strong>
      <span>{text}</span>
    </div>
  );
}

function rollupFromProjects(projects: ProjectRollupItem[]): RollupSummary {
  const reliable = projects.filter(
    (project) =>
      project.health_score !== null &&
      project.health_band !== "insufficient_data",
  );
  const score = reliable.length
    ? Math.round(
        reliable.reduce((total, project) => total + (project.health_score ?? 0), 0) /
          reliable.length,
      )
    : null;
  const averageCoverage = projects.length
    ? Math.round(
        projects.reduce(
          (total, project) => total + project.health_coverage_percent,
          0,
        ) / projects.length,
      )
    : 0;
  const band: ProjectHealthBand =
    score === null || averageCoverage < 35
      ? "insufficient_data"
      : score >= 80
        ? "green"
        : score >= 60
          ? "amber"
          : "red";

  return {
    projects_total: projects.length,
    projects_scored: reliable.length,
    score,
    band,
    average_coverage_percent: averageCoverage,
    green: projects.filter((project) => project.health_band === "green").length,
    amber: projects.filter((project) => project.health_band === "amber").length,
    red: projects.filter((project) => project.health_band === "red").length,
    insufficient_data: projects.filter(
      (project) => project.health_band === "insufficient_data",
    ).length,
    improving: projects.filter(
      (project) => project.trend_direction === "improving",
    ).length,
    stable: projects.filter((project) => project.trend_direction === "stable").length,
    deteriorating: projects.filter(
      (project) => project.trend_direction === "deteriorating",
    ).length,
    insufficient_history: projects.filter(
      (project) => project.trend_direction === "insufficient_history",
    ).length,
  };
}
