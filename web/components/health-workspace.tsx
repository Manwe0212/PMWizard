"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import type {
  HealthFactor,
  HealthHistoryPoint,
  HealthSignal,
  HealthSnapshotCaptureResponse,
  ProjectHealthBand,
  ProjectHealthHistory,
  ProjectHealthSnapshot,
  TrendDirection,
} from "@/lib/types";

type Props = {
  canCapture: boolean;
};

function titleCase(value: string): string {
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function bandLabel(band: ProjectHealthBand): string {
  if (band === "insufficient_data") return "Insufficient data";
  return titleCase(band);
}

function scoreLabel(score: number | null): string {
  return score === null ? "—" : String(score);
}

function deltaLabel(value: number | null): string {
  if (value === null) return "—";
  return value > 0 ? `+${value}` : String(value);
}

function dateLabel(value: string): string {
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

function trendLabel(direction: TrendDirection): string {
  if (direction === "insufficient_history") return "Insufficient history";
  return titleCase(direction);
}

async function jsonRequest<T>(
  input: RequestInfo | URL,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(input, init);
  const payload = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(
      typeof payload?.detail === "string"
        ? payload.detail
        : `Request failed with status ${response.status}`,
    );
  }
  return payload as T;
}

async function fetchHealth(): Promise<ProjectHealthSnapshot> {
  return jsonRequest<ProjectHealthSnapshot>("/api/health", {
    cache: "no-store",
  });
}

async function fetchHistory(): Promise<ProjectHealthHistory> {
  return jsonRequest<ProjectHealthHistory>("/api/health/history", {
    cache: "no-store",
  });
}

export function HealthWorkspace({ canCapture }: Props) {
  const [snapshot, setSnapshot] = useState<ProjectHealthSnapshot | null>(null);
  const [history, setHistory] = useState<ProjectHealthHistory | null>(null);
  const [loading, setLoading] = useState(true);
  const [capturing, setCapturing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [captureMessage, setCaptureMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [current, historical] = await Promise.all([
        fetchHealth(),
        fetchHistory(),
      ]);
      setSnapshot(current);
      setHistory(historical);
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Unable to load Project Health.",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const rankedFactors = useMemo(() => {
    if (!snapshot) return [];
    return [...snapshot.factors].sort((a, b) => {
      if (a.available !== b.available) return a.available ? -1 : 1;
      return (a.score ?? 101) - (b.score ?? 101);
    });
  }, [snapshot]);

  async function captureSnapshot() {
    if (!canCapture) return;
    setCapturing(true);
    setError(null);
    setCaptureMessage(null);
    try {
      const result = await jsonRequest<HealthSnapshotCaptureResponse>(
        "/api/health/history",
        { method: "POST" },
      );
      setCaptureMessage(
        result.created
          ? `Snapshot captured at ${dateLabel(result.snapshot.captured_at)}.`
          : "An identical snapshot was already captured in the last five minutes.",
      );
      const [current, historical] = await Promise.all([
        fetchHealth(),
        fetchHistory(),
      ]);
      setSnapshot(current);
      setHistory(historical);
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Unable to capture health snapshot.",
      );
    } finally {
      setCapturing(false);
    }
  }

  if (loading) {
    return (
      <section className="healthSurface">
        <div className="memoryLoading">
          <div className="skeletonLine wide" />
          <div className="healthFactorGrid">
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

  if (error && (!snapshot || !history)) {
    return (
      <section className="healthSurface">
        <div className="memoryError">
          <div className="detailEmptyMark">!</div>
          <h2>Project Health unavailable</h2>
          <p>{error}</p>
          <button className="primaryButton" type="button" onClick={() => void load()}>
            Retry
          </button>
        </div>
      </section>
    );
  }

  if (!snapshot || !history) return null;

  return (
    <section className="healthSurface">
      <div className="healthHero">
        <div className="healthScoreColumn">
          <div className={`healthScoreRing ${snapshot.band}`}>
            <div>
              <strong>{scoreLabel(snapshot.score)}</strong>
              <span>/100</span>
            </div>
          </div>
          <span className={`healthBandBadge ${snapshot.band}`}>
            {bandLabel(snapshot.band)}
          </span>
        </div>

        <div className="healthHeroCopy">
          <div className="detailBadges">
            <span className="memoryTruthBadge">Explainable V0</span>
            <span className={`coverageBadge ${snapshot.coverage_band}`}>
              {titleCase(snapshot.coverage_band)} coverage
            </span>
            {history.count >= 2 && (
              <span className={`trendBadge ${history.trend.direction}`}>
                {trendLabel(history.trend.direction)}
                {history.trend.score_delta !== null &&
                  ` ${deltaLabel(history.trend.score_delta)}`}
              </span>
            )}
          </div>
          <h2>{snapshot.project_name}</h2>
          <p>{snapshot.explanation}</p>

          <div className="coverageRow">
            <div>
              <span>Assessment coverage</span>
              <strong>{snapshot.coverage_percent}%</strong>
            </div>
            <div className="coverageTrack" aria-label="Assessment coverage">
              <span style={{ width: `${snapshot.coverage_percent}%` }} />
            </div>
            <small>
              {snapshot.available_weight}/100 model weight has governed data.
            </small>
          </div>
        </div>

        <button className="secondaryButton" type="button" onClick={() => void load()}>
          ↻ Refresh health
        </button>
      </div>

      {error && (
        <div className="errorBanner" role="alert">
          <span>!</span>
          <div>
            <strong>Health history needs attention</strong>
            <p>{error}</p>
          </div>
          <button type="button" onClick={() => void load()}>
            Retry
          </button>
        </div>
      )}

      {captureMessage && (
        <div className="healthCaptureMessage" role="status">
          <span>✓</span>
          {captureMessage}
        </div>
      )}

      <div className="healthFactorGrid">
        {rankedFactors.map((factor) => (
          <FactorCard key={factor.key} factor={factor} />
        ))}
      </div>

      <HealthTrendPanel
        history={history}
        canCapture={canCapture}
        capturing={capturing}
        onCapture={() => void captureSnapshot()}
      />

      <div className="healthLowerGrid">
        <section className="healthPanel">
          <div className="healthPanelHeader">
            <div>
              <h3>Key drivers</h3>
              <p>Largest current penalties across the health model.</p>
            </div>
            <span>{snapshot.key_drivers.length}</span>
          </div>

          {snapshot.key_drivers.length ? (
            <div className="healthDriverList">
              {snapshot.key_drivers.map((driver, index) => (
                <DriverRow key={`${driver.title}-${index}`} signal={driver} />
              ))}
            </div>
          ) : (
            <div className="healthEmpty">
              <div className="emptyIcon">✓</div>
              <strong>No active negative drivers</strong>
              <span>
                Available factors currently contain no penalty-producing signals.
              </span>
            </div>
          )}
        </section>

        <section className="healthPanel methodologyPanel">
          <div className="healthPanelHeader">
            <div>
              <h3>Scoring model</h3>
              <p>Deterministic weights used by Project Health V0.</p>
            </div>
          </div>

          <div className="weightList">
            {snapshot.factors.map((factor) => (
              <div className="weightRow" key={factor.key}>
                <div>
                  <strong>{factor.name}</strong>
                  <span>
                    {factor.available
                      ? `Score ${factor.score}/100`
                      : "No governed data"}
                  </span>
                </div>
                <div className="weightTrack">
                  <span style={{ width: `${factor.weight}%` }} />
                </div>
                <b>{factor.weight}%</b>
              </div>
            ))}
          </div>

          <div className="healthThresholds">
            <div>
              <span className="thresholdDot green" />
              <strong>Green</strong>
              <small>80–100</small>
            </div>
            <div>
              <span className="thresholdDot amber" />
              <strong>Amber</strong>
              <small>60–79</small>
            </div>
            <div>
              <span className="thresholdDot red" />
              <strong>Red</strong>
              <small>0–59</small>
            </div>
          </div>

          <div className="healthGovernanceNote">
            Current Health is live and read-only. Historical points are created only
            by explicit snapshot capture, never by refreshing this page.
          </div>
        </section>
      </div>
    </section>
  );
}

function HealthTrendPanel({
  history,
  canCapture,
  capturing,
  onCapture,
}: {
  history: ProjectHealthHistory;
  canCapture: boolean;
  capturing: boolean;
  onCapture: () => void;
}) {
  const trend = history.trend;

  return (
    <section className="healthTrendPanel">
      <div className="healthTrendHeader">
        <div>
          <div className="detailBadges">
            <span className={`trendBadge ${trend.direction}`}>
              {trendLabel(trend.direction)}
            </span>
            <span className="sourceOperationalBadge">
              {history.count} snapshot{history.count === 1 ? "" : "s"}
            </span>
          </div>
          <h3>Health history & trend</h3>
          <p>{trend.explanation}</p>
        </div>
        <button
          className="primaryButton"
          type="button"
          onClick={onCapture}
          disabled={!canCapture || capturing}
          title={
            canCapture
              ? "Capture the current deterministic health state"
              : "Project review permission is required to capture history"
          }
        >
          {capturing ? "Capturing…" : "Capture snapshot"}
        </button>
      </div>

      <div className="healthTrendGrid">
        <div className="healthChartCard">
          <HealthTrendChart points={history.points} />
        </div>

        <div className="trendChangeCard">
          <div className="trendDeltaHero">
            <span>Latest score change</span>
            <strong className={trend.direction}>
              {deltaLabel(trend.score_delta)}
            </strong>
            <small>
              Coverage {deltaLabel(trend.coverage_delta)} pp
            </small>
          </div>

          <div className="factorDeltaList">
            {Object.keys(trend.factor_deltas).length ? (
              Object.entries(trend.factor_deltas).map(([key, value]) => (
                <div key={key}>
                  <span>{titleCase(key)}</span>
                  <strong className={value > 0 ? "up" : value < 0 ? "down" : ""}>
                    {deltaLabel(value)}
                  </strong>
                </div>
              ))
            ) : (
              <div className="trendNoDelta">
                Capture at least two comparable snapshots to see factor deltas.
              </div>
            )}
          </div>
        </div>
      </div>

      {(trend.new_drivers.length > 0 || trend.resolved_drivers.length > 0) && (
        <div className="trendDriverChanges">
          <div>
            <span>New drivers</span>
            <div className="trendChips">
              {trend.new_drivers.length ? (
                trend.new_drivers.map((driver) => (
                  <b className="new" key={driver}>
                    + {driver}
                  </b>
                ))
              ) : (
                <small>None</small>
              )}
            </div>
          </div>
          <div>
            <span>Resolved drivers</span>
            <div className="trendChips">
              {trend.resolved_drivers.length ? (
                trend.resolved_drivers.map((driver) => (
                  <b className="resolved" key={driver}>
                    ✓ {driver}
                  </b>
                ))
              ) : (
                <small>None</small>
              )}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

function HealthTrendChart({ points }: { points: HealthHistoryPoint[] }) {
  const scored = points.filter(
    (point): point is HealthHistoryPoint & { score: number } =>
      point.score !== null,
  );

  if (scored.length < 2) {
    return (
      <div className="healthChartEmpty">
        <div className="emptyIcon">↗</div>
        <strong>History needs another point</strong>
        <span>
          Capture at least two scored snapshots to visualize direction over time.
        </span>
      </div>
    );
  }

  const width = 720;
  const height = 220;
  const left = 40;
  const right = 20;
  const top = 18;
  const bottom = 34;
  const plotWidth = width - left - right;
  const plotHeight = height - top - bottom;

  const coordinates = scored.map((point, index) => {
    const x =
      left +
      (scored.length === 1
        ? plotWidth / 2
        : (plotWidth * index) / (scored.length - 1));
    const y = top + ((100 - point.score) / 100) * plotHeight;
    return { point, x, y };
  });

  const path = coordinates
    .map(({ x, y }, index) => `${index === 0 ? "M" : "L"} ${x} ${y}`)
    .join(" ");

  const labels = [
    coordinates[0],
    coordinates[Math.floor((coordinates.length - 1) / 2)],
    coordinates[coordinates.length - 1],
  ].filter(
    (item, index, array) =>
      array.findIndex((candidate) => candidate.point.id === item.point.id) === index,
  );

  return (
    <div className="healthChart">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label="Project Health score history"
      >
        {[100, 80, 60, 0].map((score) => {
          const y = top + ((100 - score) / 100) * plotHeight;
          return (
            <g key={score}>
              <line
                className="healthChartGrid"
                x1={left}
                x2={width - right}
                y1={y}
                y2={y}
              />
              <text className="healthChartAxis" x={4} y={y + 3}>
                {score}
              </text>
            </g>
          );
        })}

        <line
          className="healthChartThreshold amber"
          x1={left}
          x2={width - right}
          y1={top + ((100 - 80) / 100) * plotHeight}
          y2={top + ((100 - 80) / 100) * plotHeight}
        />
        <line
          className="healthChartThreshold red"
          x1={left}
          x2={width - right}
          y1={top + ((100 - 60) / 100) * plotHeight}
          y2={top + ((100 - 60) / 100) * plotHeight}
        />

        <path className="healthChartPath" d={path} />

        {coordinates.map(({ point, x, y }) => (
          <g key={point.id}>
            <circle
              className={`healthChartPoint ${point.band}`}
              cx={x}
              cy={y}
              r={5}
            />
            <title>
              {`${dateLabel(point.captured_at)} — ${point.score}/100`}
            </title>
          </g>
        ))}

        {labels.map(({ point, x }) => (
          <text
            className="healthChartDate"
            key={`label-${point.id}`}
            x={x}
            y={height - 8}
            textAnchor="middle"
          >
            {new Intl.DateTimeFormat("en", {
              month: "short",
              day: "numeric",
            }).format(new Date(point.captured_at))}
          </text>
        ))}
      </svg>
    </div>
  );
}

function FactorCard({ factor }: { factor: HealthFactor }) {
  return (
    <article className={`healthFactorCard ${factor.band}`}>
      <div className="healthFactorTop">
        <div>
          <span>{factor.weight}% weight</span>
          <h3>{factor.name}</h3>
        </div>
        <strong>{scoreLabel(factor.score)}</strong>
      </div>

      <div className="factorScoreTrack">
        <span
          className={factor.band}
          style={{ width: `${factor.score ?? 0}%` }}
        />
      </div>

      <div className="factorSignals">
        {factor.signals.slice(0, 3).map((signal, index) => (
          <div className="factorSignal" key={`${signal.title}-${index}`}>
            <span className={`signalDot ${signal.severity}`} />
            <div>
              <strong>{signal.title}</strong>
              <p>{signal.detail}</p>
            </div>
            {signal.penalty > 0 && <b>−{signal.penalty}</b>}
          </div>
        ))}
      </div>

      {!factor.available && (
        <span className="factorUnavailable">Excluded from weighted score</span>
      )}
    </article>
  );
}

function DriverRow({ signal }: { signal: HealthSignal }) {
  return (
    <article className="healthDriver">
      <span className={`driverIcon ${signal.severity}`}>
        {signal.severity === "critical" ? "!" : "↘"}
      </span>
      <div>
        <div className="driverTitleRow">
          <strong>{signal.title}</strong>
          {signal.entity_type && <span>{signal.entity_type}</span>}
        </div>
        <p>{signal.detail}</p>
      </div>
      <b>−{signal.penalty}</b>
    </article>
  );
}
