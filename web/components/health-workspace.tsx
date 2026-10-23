"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import type {
  HealthFactor,
  HealthSignal,
  ProjectHealthBand,
  ProjectHealthSnapshot,
} from "@/lib/types";

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

async function fetchHealth(): Promise<ProjectHealthSnapshot> {
  const response = await fetch("/api/health", { cache: "no-store" });
  const payload = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(
      typeof payload?.detail === "string"
        ? payload.detail
        : `Unable to load Project Health (${response.status})`,
    );
  }

  return payload as ProjectHealthSnapshot;
}

export function HealthWorkspace() {
  const [snapshot, setSnapshot] = useState<ProjectHealthSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setSnapshot(await fetchHealth());
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

  if (error || !snapshot) {
    return (
      <section className="healthSurface">
        <div className="memoryError">
          <div className="detailEmptyMark">!</div>
          <h2>Project Health unavailable</h2>
          <p>{error ?? "No health snapshot is available."}</p>
          <button className="primaryButton" type="button" onClick={() => void load()}>
            Retry
          </button>
        </div>
      </section>
    );
  }

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

      <div className="healthFactorGrid">
        {rankedFactors.map((factor) => (
          <FactorCard key={factor.key} factor={factor} />
        ))}
      </div>

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
            Health V0 reads governed Project Memory and durable Source telemetry.
            It does not write project state or use an opaque LLM judgment.
          </div>
        </section>
      </div>
    </section>
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
