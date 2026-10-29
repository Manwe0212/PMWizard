"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import type {
  SourceConnectionView,
  SourceRunView,
  SourcesWorkspaceSnapshot,
} from "@/lib/types";

type SourceSystem =
  | "microsoft_graph_mail"
  | "microsoft_graph_sharepoint";

const DEFAULT_EXTENSIONS = ".docx, .txt, .md, .csv, .json, .xml, .yaml, .yml, .log";

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

async function readJson(response: Response) {
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(
      typeof payload?.detail === "string"
        ? payload.detail
        : `Source request failed (${response.status})`,
    );
  }
  return payload;
}

async function loadSources(): Promise<SourcesWorkspaceSnapshot> {
  return readJson(
    await fetch("/api/sources", {
      cache: "no-store",
    }),
  );
}

export function SourcesWorkspace({ canManage }: { canManage: boolean }) {
  const [snapshot, setSnapshot] = useState<SourcesWorkspaceSnapshot | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
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

  if (loading && !snapshot) {
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
            <span className="memoryTruthBadge">Governed integrations</span>
            <span className="sourceOperationalBadge">
              {summary.total} configured
            </span>
          </div>
          <h2>Source connections</h2>
          <p>
            Configure authorized Outlook and SharePoint Sources, keep runtime secrets
            outside PostgreSQL, test connectivity through the worker, and observe
            durable sync telemetry.
          </p>
        </div>
        <div className="sourceHeroActions">
          {canManage && (
            <button
              className="primaryButton"
              type="button"
              onClick={() => setCreateOpen((current) => !current)}
            >
              {createOpen ? "Close" : "+ Add source"}
            </button>
          )}
          <button className="secondaryButton" type="button" onClick={() => void load()}>
            ↻ Refresh
          </button>
        </div>
      </div>

      {createOpen && canManage && (
        <CreateSourcePanel
          onCreated={async (sourceId) => {
            setCreateOpen(false);
            await load();
            setSelectedId(sourceId);
          }}
        />
      )}

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
          <strong>No sources configured</strong>
          <span>
            Add an Outlook or SharePoint Source to begin building governed Evidence.
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
                    {source.connection_test.status === "running"
                      ? "Testing connection…"
                      : `Last sync ${formatDate(source.latest_run?.finished_at ?? null)}`}
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
                key={selected.id}
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
          <strong>Security boundary</strong>
          <p>
            Source configuration is non-secret. Credential values remain in the
            worker&apos;s secret provider. Connection tests and scheduled syncs execute
            outside the request path.
          </p>
        </div>
      </div>
    </section>
  );
}

function CreateSourcePanel({
  onCreated,
}: {
  onCreated: (sourceId: string) => Promise<void>;
}) {
  const [system, setSystem] = useState<SourceSystem>("microsoft_graph_mail");
  const [displayName, setDisplayName] = useState("Project Inbox");
  const [scope, setScope] = useState("project:read");
  const [mailbox, setMailbox] = useState("me");
  const [folderId, setFolderId] = useState("inbox");
  const [receivedAfter, setReceivedAfter] = useState("");
  const [driveId, setDriveId] = useState("");
  const [syncMode, setSyncMode] = useState<"latest" | "full">("latest");
  const [extensions, setExtensions] = useState(DEFAULT_EXTENSIONS);
  const [maxBytes, setMaxBytes] = useState(10 * 1024 * 1024);
  const [enabled, setEnabled] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const safe_config =
        system === "microsoft_graph_mail"
          ? {
              mailbox: mailbox.trim(),
              folder_id: folderId.trim(),
              received_after: toIsoUtc(receivedAfter),
            }
          : {
              drive_id: driveId.trim(),
              initial_sync_mode: syncMode,
              supported_extensions: splitList(extensions),
              max_file_bytes: maxBytes,
            };

      const source = await readJson(
        await fetch("/api/sources", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            source_system: system,
            display_name: displayName.trim(),
            safe_config,
            permission_scope: splitList(scope),
            enabled,
          }),
        }),
      );
      await onCreated(String(source.id));
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Unable to create Source.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="sourceAdminPanel" onSubmit={submit}>
      <div className="sourceAdminHeader">
        <div>
          <span className="memoryTruthBadge">New connection</span>
          <h3>Add project Source</h3>
          <p>
            Only safe connector metadata is stored here. Bind the runtime credential
            after the Source is created.
          </p>
        </div>
      </div>

      <div className="sourceAdminGrid">
        <label>
          Source system
          <select
            value={system}
            onChange={(event) => {
              const next = event.target.value as SourceSystem;
              setSystem(next);
              setDisplayName(
                next === "microsoft_graph_mail"
                  ? "Project Inbox"
                  : "Project Documents",
              );
            }}
          >
            <option value="microsoft_graph_mail">Outlook Mail</option>
            <option value="microsoft_graph_sharepoint">SharePoint</option>
          </select>
        </label>

        <label>
          Display name
          <input
            value={displayName}
            onChange={(event) => setDisplayName(event.target.value)}
            required
          />
        </label>

        <label className="wide">
          Evidence permission scope
          <input
            value={scope}
            onChange={(event) => setScope(event.target.value)}
            placeholder="project:read, source:mail"
            required
          />
          <small>Comma-separated. Defaults to project:read.</small>
        </label>

        {system === "microsoft_graph_mail" ? (
          <>
            <label>
              Mailbox
              <input
                value={mailbox}
                onChange={(event) => setMailbox(event.target.value)}
                placeholder="pm@example.com or me"
                required
              />
            </label>
            <label>
              Folder ID
              <input
                value={folderId}
                onChange={(event) => setFolderId(event.target.value)}
                required
              />
            </label>
            <label className="wide">
              Received after
              <input
                type="datetime-local"
                value={receivedAfter}
                onChange={(event) => setReceivedAfter(event.target.value)}
              />
              <small>Optional. Leave empty to use the connector&apos;s normal delta start.</small>
            </label>
          </>
        ) : (
          <>
            <label className="wide">
              SharePoint drive ID
              <input
                value={driveId}
                onChange={(event) => setDriveId(event.target.value)}
                required
              />
            </label>
            <label>
              Initial sync
              <select
                value={syncMode}
                onChange={(event) =>
                  setSyncMode(event.target.value as "latest" | "full")
                }
              >
                <option value="latest">Latest</option>
                <option value="full">Full</option>
              </select>
            </label>
            <label>
              Max file bytes
              <input
                type="number"
                min={1}
                value={maxBytes}
                onChange={(event) => setMaxBytes(Number(event.target.value))}
              />
            </label>
            <label className="wide">
              Supported extensions
              <input
                value={extensions}
                onChange={(event) => setExtensions(event.target.value)}
              />
            </label>
          </>
        )}
      </div>

      <div className="sourceAdminFooter">
        <label className="automationToggle">
          <input
            type="checkbox"
            checked={enabled}
            onChange={(event) => setEnabled(event.target.checked)}
          />
          <span>Enable immediately</span>
        </label>
        <button className="primaryButton" type="submit" disabled={busy}>
          {busy ? "Creating…" : "Create source"}
        </button>
      </div>

      {error && (
        <div className="runIssues error">
          <strong>Could not create Source</strong>
          <p>{error}</p>
        </div>
      )}
    </form>
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
  const isMail = source.source_system === "microsoft_graph_mail";
  const isSharePoint = source.source_system === "microsoft_graph_sharepoint";
  const administrable = isMail || isSharePoint;

  const [displayName, setDisplayName] = useState(source.display_name);
  const [scope, setScope] = useState(source.permission_scope.join(", "));
  const [enabled, setEnabled] = useState(source.is_enabled);
  const [mailbox, setMailbox] = useState(String(source.safe_config.mailbox ?? "me"));
  const [folderId, setFolderId] = useState(String(source.safe_config.folder_id ?? "inbox"));
  const [receivedAfter, setReceivedAfter] = useState(
    toLocalDateTime(source.safe_config.received_after),
  );
  const [driveId, setDriveId] = useState(String(source.safe_config.drive_id ?? ""));
  const [syncMode, setSyncMode] = useState<"latest" | "full">(
    source.safe_config.initial_sync_mode === "full" ? "full" : "latest",
  );
  const [extensions, setExtensions] = useState(
    Array.isArray(source.safe_config.supported_extensions)
      ? source.safe_config.supported_extensions.join(", ")
      : DEFAULT_EXTENSIONS,
  );
  const [maxBytes, setMaxBytes] = useState(
    Number(source.safe_config.max_file_bytes ?? 10 * 1024 * 1024),
  );

  const [credentialRef, setCredentialRef] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [operationError, setOperationError] = useState<string | null>(null);

  async function saveConfiguration() {
    if (!canManage || !administrable) return;
    setBusy("save");
    setOperationError(null);
    try {
      const safe_config = isMail
        ? {
            mailbox: mailbox.trim(),
            folder_id: folderId.trim(),
            received_after: toIsoUtc(receivedAfter),
          }
        : {
            drive_id: driveId.trim(),
            initial_sync_mode: syncMode,
            supported_extensions: splitList(extensions),
            max_file_bytes: maxBytes,
          };

      await readJson(
        await fetch(`/api/sources/${encodeURIComponent(source.id)}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            display_name: displayName.trim(),
            safe_config,
            permission_scope: splitList(scope),
            enabled,
          }),
        }),
      );
      await onChanged();
    } catch (requestError) {
      setOperationError(
        requestError instanceof Error
          ? requestError.message
          : "Unable to update Source.",
      );
    } finally {
      setBusy(null);
    }
  }

  async function toggleEnabled() {
    if (!canManage || !administrable) return;
    const next = !source.is_enabled;
    setBusy("toggle");
    setOperationError(null);
    try {
      await readJson(
        await fetch(`/api/sources/${encodeURIComponent(source.id)}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ enabled: next }),
        }),
      );
      setEnabled(next);
      await onChanged();
    } catch (requestError) {
      setOperationError(
        requestError instanceof Error ? requestError.message : "Unable to update Source.",
      );
    } finally {
      setBusy(null);
    }
  }

  async function queueTest() {
    if (!canManage) return;
    setBusy("test");
    setOperationError(null);
    try {
      await readJson(
        await fetch(`/api/sources/${encodeURIComponent(source.id)}/test`, {
          method: "POST",
        }),
      );
      await onChanged();
    } catch (requestError) {
      setOperationError(
        requestError instanceof Error
          ? requestError.message
          : "Unable to queue connection test.",
      );
    } finally {
      setBusy(null);
    }
  }

  async function bindCredential() {
    if (!canManage || !credentialRef.trim()) return;
    setBusy("credential");
    setOperationError(null);
    try {
      await readJson(
        await fetch(
          `/api/sources/${encodeURIComponent(source.id)}/credential`,
          {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ credential_ref: credentialRef.trim() }),
          },
        ),
      );
      setCredentialRef("");
      await onChanged();
    } catch (requestError) {
      setOperationError(
        requestError instanceof Error
          ? requestError.message
          : "Unable to bind runtime credential.",
      );
    } finally {
      setBusy(null);
    }
  }

  async function clearCredential() {
    if (!canManage) return;
    setBusy("credential");
    setOperationError(null);
    try {
      await readJson(
        await fetch(
          `/api/sources/${encodeURIComponent(source.id)}/credential`,
          { method: "DELETE" },
        ),
      );
      setCredentialRef("");
      await onChanged();
    } catch (requestError) {
      setOperationError(
        requestError instanceof Error
          ? requestError.message
          : "Unable to clear runtime credential.",
      );
    } finally {
      setBusy(null);
    }
  }

  const test = source.connection_test;

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
          <p className="sourceImmutableKey">{source.connector_key}</p>
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
          <span>Last sync</span>
          <strong>{formatDate(source.latest_run?.finished_at ?? null)}</strong>
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

      {canManage && administrable && (
        <section className="sourceSection sourceAdminEditor">
          <div className="sourceSectionTitle">
            <div>
              <h4>Connection administration</h4>
              <p>
                Connector identity is immutable. Editing stream configuration resets
                the current delta checkpoint so the next sync starts safely.
              </p>
            </div>
            <button
              className={source.is_enabled ? "dangerButton" : "secondaryButton"}
              type="button"
              disabled={busy !== null}
              onClick={() => void toggleEnabled()}
            >
              {source.is_enabled ? "Disable source" : "Enable source"}
            </button>
          </div>

          <div className="sourceAdminGrid compact">
            <label>
              Display name
              <input
                value={displayName}
                onChange={(event) => setDisplayName(event.target.value)}
              />
            </label>
            <label>
              Permission scope
              <input value={scope} onChange={(event) => setScope(event.target.value)} />
            </label>

            {isMail ? (
              <>
                <label>
                  Mailbox
                  <input value={mailbox} onChange={(event) => setMailbox(event.target.value)} />
                </label>
                <label>
                  Folder ID
                  <input value={folderId} onChange={(event) => setFolderId(event.target.value)} />
                </label>
                <label className="wide">
                  Received after
                  <input
                    type="datetime-local"
                    value={receivedAfter}
                    onChange={(event) => setReceivedAfter(event.target.value)}
                  />
                </label>
              </>
            ) : (
              <>
                <label className="wide">
                  SharePoint drive ID
                  <input value={driveId} onChange={(event) => setDriveId(event.target.value)} />
                </label>
                <label>
                  Initial sync
                  <select
                    value={syncMode}
                    onChange={(event) =>
                      setSyncMode(event.target.value as "latest" | "full")
                    }
                  >
                    <option value="latest">Latest</option>
                    <option value="full">Full</option>
                  </select>
                </label>
                <label>
                  Max file bytes
                  <input
                    type="number"
                    min={1}
                    value={maxBytes}
                    onChange={(event) => setMaxBytes(Number(event.target.value))}
                  />
                </label>
                <label className="wide">
                  Supported extensions
                  <input
                    value={extensions}
                    onChange={(event) => setExtensions(event.target.value)}
                  />
                </label>
              </>
            )}
          </div>

          <div className="sourceAdminFooter">
            <span className="mutedInline">
              {source.is_enabled
                ? "Disabling also pauses active Source Sync schedules."
                : "Re-enabling does not automatically resume paused schedules."}
            </span>
            <button
              className="primaryButton"
              type="button"
              disabled={busy !== null}
              onClick={() => void saveConfiguration()}
            >
              {busy === "save" ? "Saving…" : "Save configuration"}
            </button>
          </div>
        </section>
      )}

      <section className="sourceSection sourceCredentialSection">
        <div className="sourceSectionTitle">
          <div>
            <h4>Secure runtime credential</h4>
            <p>
              PMWizard stores only an opaque alias. The actual credential stays in a
              PMWIZARD_SECRET_* variable available to the worker.
            </p>
          </div>
          <span
            className={`sourceHealth ${
              source.credential_configured ? "healthy" : "never_synced"
            }`}
          >
            {source.credential_configured ? "configured" : "not configured"}
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
                disabled={busy !== null}
              />
            </label>
            <button
              className="primaryButton"
              type="button"
              disabled={busy !== null || !credentialRef.trim()}
              onClick={() => void bindCredential()}
            >
              {busy === "credential"
                ? "Saving…"
                : source.credential_configured
                  ? "Replace binding"
                  : "Bind credential"}
            </button>
            {source.credential_configured && (
              <button
                className="dangerButton"
                type="button"
                disabled={busy !== null}
                onClick={() => void clearCredential()}
              >
                Clear binding
              </button>
            )}
          </div>
        ) : (
          <p className="mutedInline">
            Project review permission is required to manage runtime credentials.
          </p>
        )}
      </section>

      <section className="sourceSection sourceTestSection">
        <div className="sourceSectionTitle">
          <div>
            <h4>Connection test</h4>
            <p>
              The API queues this request. The worker resolves credentials and performs
              the provider test outside the request path.
            </p>
          </div>
          <span className={`sourceTestBadge ${test.status}`}>
            {healthLabel(test.status)}
          </span>
        </div>

        <div className="sourceTestBody">
          <div>
            <span>Last test</span>
            <strong>{formatDate(test.last_test_at)}</strong>
            {test.message && <p>{test.message}</p>}
          </div>
          {canManage && administrable && (
            <button
              className="secondaryButton"
              type="button"
              disabled={
                busy !== null ||
                !source.is_enabled ||
                !source.credential_configured ||
                test.status === "queued" ||
                test.status === "running"
              }
              onClick={() => void queueTest()}
            >
              {busy === "test" ? "Queueing…" : "Test connection"}
            </button>
          )}
        </div>
      </section>

      {operationError && (
        <div className="runIssues error">
          <strong>Source operation failed</strong>
          <p>{operationError}</p>
        </div>
      )}

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
            <p>Non-secret connector metadata currently stored in PostgreSQL.</p>
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
      <span>This Source has not produced durable run telemetry yet.</span>
    </div>
  );
}

function renderConfigValue(value: unknown): string {
  if (Array.isArray(value)) return value.join(", ");
  if (value === null || value === undefined || value === "") return "Not set";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return String(value);
}

function splitList(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function toLocalDateTime(value: unknown): string {
  if (typeof value !== "string" || !value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}


function toIsoUtc(value: string): string | null {
  if (!value.trim()) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return date.toISOString();
}
