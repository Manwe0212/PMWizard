"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import type {
  SourceConnectionView,
  SourceRunView,
  SourcesWorkspaceSnapshot,
} from "@/lib/types";

function systemLabel(system: string): string {
  if (system === "microsoft_graph_mail") return "Outlook Mail";
  if (system === "microsoft_graph_sharepoint") return "SharePoint";
  if (system === "synthetic") return "Synthetic";
  return system.replaceAll("_", " ");
}

function healthLabel(health: string): string {
  return health.replaceAll("_", " ");
}

function formatDate(value: string | null): string {
  if (!value) return "Never";
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

function formatDuration(seconds: number): string {
  if (seconds < 1) return "<1s";
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
}

async function loadSources(): Promise<SourcesWorkspaceSnapshot> {
  const response = await fetch("/api/sources", { cache: "no-store" });
  const payload = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(
      typeof payload?.detail === "string"
        ? payload.detail
        : `Unable to load Sources Workspace (${response.status})`,
    );
  }
  return payload as SourcesWorkspaceSnapshot;
}

export function SourcesWorkspace({ canManage }: { canManage: boolean }) {
  const [snapshot, setSnapshot] = useState<SourcesWorkspaceSnapshot | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await loadSources();
      setSnapshot(result);
      setSelectedId((current) => {
        if (current && result.sources.some((source) => source.id === current)) {
          return current;
        }
        return result.sources[0]?.id ?? null;
      });
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Unable to load Sources Workspace.",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const selected = useMemo(
    () => snapshot?.sources.find((source) => source.id === selectedId) ?? null,
    [snapshot, selectedId],
  );

  if (loading) {
    return (
      <section className="sourcesSurface">
        <div className="memoryLoading">
          <div className="skeletonLine wide" />
          <div className="sourceMetricGrid">
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
      <section className="sourcesSurface">
        <div className="memoryError">
          <div className="detailEmptyMark">!</div>
          <h2>Sources unavailable</h2>
          <p>{error ?? "No source telemetry is available."}</p>
          <button className="primaryButton" type="button" onClick={() => void load()}>
            Retry
          </button>
        </div>
      </section>
    );
  }

  const summary = snapshot.summary;

  return (
    <section className="sourcesSurface">
      <div className="sourcesHero">
        <div>
          <div className="detailBadges">
            <span className="memoryTruthBadge">Read-only integrations</span>
            <span className="sourceOperationalBadge">
              {summary.total} configured
            </span>
          </div>
          <h2>Source health and sync observability</h2>
          <p>
            Verify that PMWizard is receiving current evidence from authorized
            systems without exposing provider tokens or raw delta checkpoints.
          </p>
        </div>
        <button className="secondaryButton" type="button" onClick={() => void load()}>
          ↻ Refresh sources
        </button>
      </div>

      <div className="sourceMetricGrid">
        <SourceMetric label="Healthy" value={summary.healthy} tone="good" />
        <SourceMetric
          label="Needs attention"
          value={summary.attention + summary.failed}
          tone={summary.attention + summary.failed > 0 ? "risk" : "default"}
        />
        <SourceMetric label="Ingested last runs" value={summary.total_ingested} />
        <SourceMetric
          label="Skipped / errors"
          value={summary.total_skipped + summary.total_errors}
          tone={summary.total_skipped + summary.total_errors > 0 ? "attention" : "default"}
        />
      </div>

      {snapshot.sources.length === 0 ? (
        <div className="memoryEmpty sourcesEmpty">
          <div className="emptyIcon">↗</div>
          <strong>No sources registered</strong>
          <span>
            A connector will appear here once it is registered or executed with
            the durable connector runner.
          </span>
        </div>
      ) : (
        <div className="sourcesWorkspace">
          <div className="sourceList">
            <div className="sourceListHeader">
              <div>
                <strong>Connections</strong>
                <span>{snapshot.sources.length} project sources</span>
              </div>
            </div>
            {snapshot.sources.map((source) => (
              <button
                className={`sourceListItem ${selectedId === source.id ? "selected" : ""}`}
                key={source.id}
                type="button"
                onClick={() => setSelectedId(source.id)}
              >
                <div className={`sourceSystemIcon ${source.health}`}>
                  {source.source_type === "email" ? "✉" : "▣"}
                </div>
                <div className="sourceListCopy">
                  <strong>{source.display_name}</strong>
                  <span>{systemLabel(source.source_system)}</span>
                  <small>
                    Last sync {formatDate(source.latest_run?.finished_at ?? null)}
                  </small>
                </div>
                <span className={`sourceHealth ${source.health}`}>
                  {healthLabel(source.health)}
                </span>
              </button>
            ))}
          </div>

          <div className="sourceDetail">
            {selected && (
              <SourceDetail
                source={selected}
                canManage={canManage}
                onChanged={load}
              />
            )}
          </div>
        </div>
      )}

      <div className="sourceSecurityNote">
        <span>⌁</span>
        <div>
          <strong>Runtime secret boundary</strong>
          <p>
            Raw provider cursors remain redacted, and credentials are resolved only by
            the worker from PMWIZARD_SECRET_* variables. The API exposes only whether
            a binding is configured.
          </p>
        </div>
      </div>
    </section>
  );
}

function SourceMetric({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: number;
  tone?: "default" | "good" | "risk" | "attention";
}) {
  return (
    <div className={`memoryMetric ${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function SourceDetail({
  source,
  canManage,
  onChanged,
}: {
  source: SourceConnectionView;
  canManage: boolean;
  onChanged: () => Promise<void>;
}) {
  const latest = source.latest_run;
  const [credentialRef, setCredentialRef] = useState("");
  const [credentialBusy, setCredentialBusy] = useState(false);
  const [credentialError, setCredentialError] = useState<string | null>(null);

  async function bindCredential() {
    if (!canManage || !credentialRef.trim()) return;
    setCredentialBusy(true);
    setCredentialError(null);
    try {
      const response = await fetch(
        `/api/sources/${encodeURIComponent(source.id)}/credential`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ credential_ref: credentialRef.trim() }),
        },
      );
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(
          typeof payload?.detail === "string"
            ? payload.detail
            : `Credential binding failed (${response.status})`,
        );
      }
      setCredentialRef("");
      await onChanged();
    } catch (requestError) {
      setCredentialError(
        requestError instanceof Error
          ? requestError.message
          : "Unable to bind runtime credential.",
      );
    } finally {
      setCredentialBusy(false);
    }
  }

  async function clearCredential() {
    if (!canManage) return;
    setCredentialBusy(true);
    setCredentialError(null);
    try {
      const response = await fetch(
        `/api/sources/${encodeURIComponent(source.id)}/credential`,
        { method: "DELETE" },
      );
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(
          typeof payload?.detail === "string"
            ? payload.detail
            : `Credential clear failed (${response.status})`,
        );
      }
      setCredentialRef("");
      await onChanged();
    } catch (requestError) {
      setCredentialError(
        requestError instanceof Error
          ? requestError.message
          : "Unable to clear runtime credential.",
      );
    } finally {
      setCredentialBusy(false);
    }
  }

  return (
    <>
      <div className="sourceDetailHeader">
        <div>
          <div className="detailBadges">
            <span className={`sourceHealth ${source.health}`}>
              {healthLabel(source.health)}
            </span>
            <span className="sourceTag">{systemLabel(source.source_system)}</span>
          </div>
          <h3>{source.display_name}</h3>
          <p>{source.connector_key}</p>
        </div>
        <div className="checkpointBox">
          <span>Checkpoint</span>
          <strong>{source.checkpoint_present ? "Active" : "None"}</strong>
          <small>
            {source.checkpoint_fingerprint
              ? `#${source.checkpoint_fingerprint}`
              : "No fingerprint"}
          </small>
        </div>
      </div>

      <div className="sourceFacts">
        <div>
          <span>Source type</span>
          <strong>{source.source_type}</strong>
        </div>
        <div>
          <span>Checkpoint updated</span>
          <strong>{formatDate(source.checkpoint_updated_at)}</strong>
        </div>
        <div>
          <span>Permission scopes</span>
          <strong>{source.permission_scope.length}</strong>
        </div>
        <div>
          <span>Enabled</span>
          <strong>{source.is_enabled ? "Yes" : "No"}</strong>
        </div>
        <div>
          <span>Runtime credential</span>
          <strong>{source.credential_configured ? "Configured" : "Not configured"}</strong>
        </div>
      </div>

      <section className="sourceSection sourceCredentialSection">
        <div className="sourceSectionTitle">
          <div>
            <h4>Secure runtime credential</h4>
            <p>
              Store only an alias in PMWizard. The actual JSON credential stays in a
              PMWIZARD_SECRET_* environment variable available to the worker.
            </p>
          </div>
          <span
            className={`sourceHealth ${
              source.credential_configured ? "healthy" : "never_synced"
            }`}
          >
            {source.credential_configured ? "configured" : "required for scheduled sync"}
          </span>
        </div>

        {canManage ? (
          <div className="sourceCredentialControls">
            <label>
              Credential alias
              <input
                value={credentialRef}
                onChange={(event) => setCredentialRef(event.target.value)}
                placeholder="env:GRAPH_PROJECT_A"
                disabled={credentialBusy}
              />
            </label>
            <button
              className="primaryButton"
              type="button"
              disabled={credentialBusy || !credentialRef.trim()}
              onClick={() => void bindCredential()}
            >
              {credentialBusy ? "Saving…" : source.credential_configured ? "Replace binding" : "Bind credential"}
            </button>
            {source.credential_configured && (
              <button
                className="dangerButton"
                type="button"
                disabled={credentialBusy}
                onClick={() => void clearCredential()}
              >
                Clear binding
              </button>
            )}
          </div>
        ) : (
          <p className="mutedInline">
            Project review permission is required to manage the runtime credential binding.
          </p>
        )}

        {credentialError && (
          <div className="runIssues error">
            <strong>Credential binding error</strong>
            <p>{credentialError}</p>
          </div>
        )}

        <div className="sourceCredentialHint">
          Example runtime variable: <code>PMWIZARD_SECRET_GRAPH_PROJECT_A</code>.
          PMWizard never returns the stored alias or secret value in this workspace.
        </div>
      </section>

      <section className="sourceSection">
        <div className="sourceSectionTitle">
          <div>
            <h4>Latest sync</h4>
            <p>Durable run telemetry for this connection.</p>
          </div>
        </div>
        {latest ? <RunSummary run={latest} /> : <NoRun />}
      </section>

      <section className="sourceSection">
        <div className="sourceSectionTitle">
          <div>
            <h4>Safe configuration</h4>
            <p>Non-secret connector metadata.</p>
          </div>
        </div>
        <div className="safeConfigGrid">
          {Object.keys(source.safe_config).length ? (
            Object.entries(source.safe_config).map(([key, value]) => (
              <div key={key}>
                <span>{key.replaceAll("_", " ")}</span>
                <strong>{renderConfigValue(value)}</strong>
              </div>
            ))
          ) : (
            <span className="mutedInline">No public configuration metadata.</span>
          )}
        </div>
      </section>

      <section className="sourceSection">
        <div className="sourceSectionTitle">
          <div>
            <h4>Recent runs</h4>
            <p>Up to five most recent sync attempts.</p>
          </div>
        </div>
        <div className="runHistory">
          {source.recent_runs.length ? (
            source.recent_runs.map((run) => <RunHistoryRow key={run.id} run={run} />)
          ) : (
            <NoRun />
          )}
        </div>
      </section>
    </>
  );
}

function RunSummary({ run }: { run: SourceRunView }) {
  return (
    <div className="runSummary">
      <div className="runSummaryTop">
        <span className={`runStatus ${run.status}`}>{run.status}</span>
        <time>{formatDate(run.finished_at)}</time>
      </div>
      <div className="runStats">
        <RunStat label="Fetched" value={run.fetched} />
        <RunStat label="Ingested" value={run.ingested} />
        <RunStat label="Duplicates" value={run.duplicates} />
        <RunStat label="Skipped" value={run.skipped} />
        <RunStat label="Errors" value={run.errors.length} />
        <RunStat label="Duration" value={formatDuration(run.duration_seconds)} />
      </div>
      {run.errors.length > 0 && (
        <div className="runIssues error">
          <strong>Errors</strong>
          {run.errors.slice(0, 3).map((error, index) => (
            <p key={index}>
              {String(error.stage ?? "runner")}: {String(error.message ?? "Unknown error")}
            </p>
          ))}
        </div>
      )}
      {run.skips.length > 0 && (
        <div className="runIssues">
          <strong>Skipped items</strong>
          {run.skips.slice(0, 3).map((skip, index) => (
            <p key={index}>{String(skip.reason ?? "Skipped by connector")}</p>
          ))}
        </div>
      )}
    </div>
  );
}

function RunHistoryRow({ run }: { run: SourceRunView }) {
  return (
    <div className="runHistoryRow">
      <span className={`runDot ${run.status}`} />
      <div>
        <strong>{formatDate(run.finished_at)}</strong>
        <span>
          {run.ingested} ingested · {run.duplicates} duplicates · {run.skipped} skipped
        </span>
      </div>
      <span className={`runStatus ${run.status}`}>{run.status}</span>
    </div>
  );
}

function RunStat({
  label,
  value,
}: {
  label: string;
  value: string | number;
}) {
  return (
    <div>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function NoRun() {
  return (
    <div className="noRun">
      <strong>No sync has been recorded</strong>
      <span>This source is registered but has not produced durable run telemetry yet.</span>
    </div>
  );
}

function renderConfigValue(value: unknown): string {
  if (Array.isArray(value)) return value.join(", ");
  if (value === null || value === undefined || value === "") return "Not set";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return String(value);
}
