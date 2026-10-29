"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import type {
  AutomationRunView,
  AutomationScheduleView,
  AutomationsWorkspaceSnapshot,
  SourceConnectionView,
  SourcesWorkspaceSnapshot,
} from "@/lib/types";

type Props = {
  canManage: boolean;
};

const CADENCES = [
  { minutes: 60, label: "Every hour" },
  { minutes: 360, label: "Every 6 hours" },
  { minutes: 720, label: "Every 12 hours" },
  { minutes: 1440, label: "Daily" },
  { minutes: 10080, label: "Weekly" },
];

function titleCase(value: string): string {
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function dateTimeLabel(value: string | null): string {
  if (!value) return "Never";
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

function cadenceLabel(minutes: number): string {
  return (
    CADENCES.find((item) => item.minutes === minutes)?.label ??
    `Every ${minutes} min`
  );
}

async function readJson(response: Response) {
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(
      typeof payload?.detail === "string"
        ? payload.detail
        : `Automation request failed (${response.status})`,
    );
  }
  return payload;
}

async function loadAutomations(): Promise<AutomationsWorkspaceSnapshot> {
  return readJson(
    await fetch("/api/automations", {
      cache: "no-store",
    }),
  );
}

async function loadSources(): Promise<SourcesWorkspaceSnapshot> {
  return readJson(
    await fetch("/api/sources", {
      cache: "no-store",
    }),
  );
}

export function AutomationWorkspace({ canManage }: Props) {
  const [snapshot, setSnapshot] =
    useState<AutomationsWorkspaceSnapshot | null>(null);
  const [sources, setSources] = useState<SourceConnectionView[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [newCadence, setNewCadence] = useState(1440);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [automations, sourceSnapshot] = await Promise.all([
        loadAutomations(),
        loadSources(),
      ]);
      setSnapshot(automations);
      setSources(sourceSnapshot.sources);
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Unable to load Automations.",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const hasHealthSchedule = useMemo(
    () =>
      snapshot?.schedules.some(
        (schedule) => schedule.task_type === "health_snapshot",
      ) ?? false,
    [snapshot],
  );

  const scheduledSourceIds = useMemo(
    () =>
      new Set(
        (snapshot?.schedules ?? [])
          .filter((schedule) => schedule.task_type === "source_sync")
          .map((schedule) => String(schedule.config.source_connection_id ?? "")),
      ),
    [snapshot],
  );

  const schedulableSources = useMemo(
    () =>
      sources.filter(
        (source) =>
          source.is_enabled &&
          source.credential_configured &&
          ["microsoft_graph_mail", "microsoft_graph_sharepoint"].includes(
            source.source_system,
          ) &&
          !scheduledSourceIds.has(source.id),
      ),
    [sources, scheduledSourceIds],
  );

  const blockedSources = useMemo(
    () =>
      sources.filter(
        (source) =>
          source.is_enabled &&
          ["microsoft_graph_mail", "microsoft_graph_sharepoint"].includes(
            source.source_system,
          ) &&
          !source.credential_configured,
      ),
    [sources],
  );

  async function createHealthSchedule() {
    if (!canManage) return;
    setCreating(true);
    setError(null);
    try {
      await readJson(
        await fetch("/api/automations", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name: "Automatic Project Health snapshot",
            task_type: "health_snapshot",
            interval_minutes: newCadence,
            enabled: true,
          }),
        }),
      );
      await load();
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Unable to create automation.",
      );
    } finally {
      setCreating(false);
    }
  }

  async function createSourceSync(source: SourceConnectionView) {
    if (!canManage) return;
    setCreating(true);
    setError(null);
    try {
      await readJson(
        await fetch("/api/automations", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name: `Sync ${source.display_name}`,
            task_type: "source_sync",
            interval_minutes: 60,
            enabled: true,
            config: {
              source_connection_id: source.id,
            },
          }),
        }),
      );
      await load();
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Unable to create Source sync automation.",
      );
    } finally {
      setCreating(false);
    }
  }

  async function patchSchedule(
    scheduleId: string,
    body: Record<string, unknown>,
  ) {
    if (!canManage) return;
    setBusy(scheduleId);
    setError(null);
    try {
      await readJson(
        await fetch(`/api/automations/${encodeURIComponent(scheduleId)}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        }),
      );
      await load();
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Unable to update automation.",
      );
    } finally {
      setBusy(null);
    }
  }

  async function runNow(scheduleId: string) {
    if (!canManage) return;
    setBusy(scheduleId);
    setError(null);
    try {
      await readJson(
        await fetch(
          `/api/automations/${encodeURIComponent(scheduleId)}/run-now`,
          {
            method: "POST",
          },
        ),
      );
      await load();
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Unable to queue automation.",
      );
    } finally {
      setBusy(null);
    }
  }

  if (loading && !snapshot) {
    return (
      <section className="automationSurface">
        <div className="memoryLoading">
          <div className="skeletonLine wide" />
          <div className="automationMetricGrid">
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

  return (
    <section className="automationSurface">
      <div className="automationHero">
        <div>
          <div className="detailBadges">
            <span className="memoryTruthBadge">Durable scheduler</span>
            <span className="sourceOperationalBadge">Worker executed</span>
          </div>
          <h2>Automation & Scheduler</h2>
          <p>
            Persist recurring project intelligence jobs in PostgreSQL. API requests
            only configure or queue work; a dedicated worker claims due jobs through
            expiring leases and records every execution.
          </p>
        </div>
        <button
          className="secondaryButton"
          type="button"
          onClick={() => void load()}
          disabled={loading}
        >
          ↻ Refresh
        </button>
      </div>

      {error && (
        <div className="errorBanner" role="alert">
          <span>!</span>
          <div>
            <strong>Automation operation failed</strong>
            <p>{error}</p>
          </div>
        </div>
      )}

      {snapshot && (
        <>
          <div className="automationMetricGrid">
            <AutomationMetric
              label="Schedules"
              value={snapshot.summary.total}
              detail={`${snapshot.summary.enabled} enabled`}
            />
            <AutomationMetric
              label="Running"
              value={snapshot.summary.running}
              detail="Active unexpired leases"
              tone={snapshot.summary.running ? "attention" : "default"}
            />
            <AutomationMetric
              label="Due now"
              value={snapshot.summary.due_now}
              detail="Waiting for worker claim"
              tone={snapshot.summary.due_now ? "attention" : "good"}
            />
            <AutomationMetric
              label="Failing"
              value={snapshot.summary.failing}
              detail="Last run failed or abandoned"
              tone={snapshot.summary.failing ? "risk" : "good"}
            />
          </div>

          {!canManage && (
            <div className="reportPermissionNote">
              You can inspect schedules and run history, but project:review permission
              is required to configure or queue automations.
            </div>
          )}

          {!hasHealthSchedule && (
            <section className="automationSetupCard">
              <div>
                <span className="automationSetupIcon">◉</span>
                <div>
                  <h3>Automatic Project Health snapshots</h3>
                  <p>
                    Capture deterministic Health on a recurring cadence so Trends
                    build without requiring a PM to press Capture snapshot manually.
                  </p>
                </div>
              </div>
              <div className="automationSetupActions">
                <select
                  value={newCadence}
                  disabled={!canManage || creating}
                  onChange={(event) => setNewCadence(Number(event.target.value))}
                  aria-label="Health snapshot cadence"
                >
                  {CADENCES.map((item) => (
                    <option key={item.minutes} value={item.minutes}>
                      {item.label}
                    </option>
                  ))}
                </select>
                <button
                  className="primaryButton"
                  type="button"
                  disabled={!canManage || creating}
                  onClick={() => void createHealthSchedule()}
                >
                  {creating ? "Creating…" : "Enable automation"}
                </button>
              </div>
            </section>
          )}

          {(schedulableSources.length > 0 || blockedSources.length > 0) && (
            <section className="automationSourceSetup">
              <div className="portfolioPanelHeader">
                <div>
                  <h3>Scheduled Source sync</h3>
                  <p>
                    Resume Outlook / SharePoint delta checkpoints automatically using
                    worker-only runtime credentials.
                  </p>
                </div>
                <span>{schedulableSources.length}</span>
              </div>

              <div className="automationSourceGrid">
                {schedulableSources.map((source) => (
                  <article className="automationSourceCard" key={source.id}>
                    <div>
                      <span className="automationSetupIcon">
                        {source.source_type === "email" ? "✉" : "▣"}
                      </span>
                      <div>
                        <strong>{source.display_name}</strong>
                        <small>{titleCase(source.source_system)}</small>
                      </div>
                    </div>
                    <button
                      className="primaryButton"
                      type="button"
                      disabled={!canManage || creating}
                      onClick={() => void createSourceSync(source)}
                    >
                      {creating ? "Creating…" : "Schedule hourly sync"}
                    </button>
                  </article>
                ))}

                {blockedSources.map((source) => (
                  <article className="automationSourceCard blocked" key={source.id}>
                    <div>
                      <span className="automationSetupIcon">!</span>
                      <div>
                        <strong>{source.display_name}</strong>
                        <small>Runtime credential required in Sources</small>
                      </div>
                    </div>
                    <span className="automationQueuedBadge">Not ready</span>
                  </article>
                ))}
              </div>
            </section>
          )}

          <div className="automationScheduleList">
            {snapshot.schedules.map((schedule) => (
              <ScheduleCard
                key={schedule.id}
                schedule={schedule}
                canManage={canManage}
                busy={busy === schedule.id}
                onToggle={() =>
                  void patchSchedule(schedule.id, {
                    enabled: !schedule.enabled,
                  })
                }
                onCadence={(minutes) =>
                  void patchSchedule(schedule.id, {
                    interval_minutes: minutes,
                  })
                }
                onRunNow={() => void runNow(schedule.id)}
              />
            ))}

            {snapshot.schedules.length === 0 && hasHealthSchedule && (
              <div className="executiveEmpty">
                <div className="emptyIcon">◇</div>
                <strong>No schedules</strong>
                <span>Create an automation to begin building recurring intelligence.</span>
              </div>
            )}
          </div>

          <div className="sourceSecurityNote">
            <span>⚙</span>
            <div>
              <strong>Worker boundary</strong>
              <p>
                Schedules execute only while a PMWizard automation worker is running.
                Start one with <code>python -m pmwizard.automation.worker</code>. A
                schedule lease prevents duplicate execution when multiple workers are
                online.
              </p>
            </div>
          </div>
        </>
      )}
    </section>
  );
}

function AutomationMetric({
  label,
  value,
  detail,
  tone = "default",
}: {
  label: string;
  value: number;
  detail: string;
  tone?: "default" | "attention" | "risk" | "good";
}) {
  return (
    <article className={`executiveMetric ${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </article>
  );
}

function ScheduleCard({
  schedule,
  canManage,
  busy,
  onToggle,
  onCadence,
  onRunNow,
}: {
  schedule: AutomationScheduleView;
  canManage: boolean;
  busy: boolean;
  onToggle: () => void;
  onCadence: (minutes: number) => void;
  onRunNow: () => void;
}) {
  const status =
    schedule.running
      ? "running"
      : schedule.last_status ??
        (schedule.enabled ? "scheduled" : "paused");

  return (
    <article className="automationScheduleCard">
      <div className="automationScheduleHeader">
        <div className={`automationTaskIcon ${status}`}>◉</div>
        <div className="automationScheduleTitle">
          <div>
            <span className={`automationStatusBadge ${status}`}>
              {titleCase(status)}
            </span>
            {schedule.pending_trigger === "manual" && !schedule.running && (
              <span className="automationQueuedBadge">Manual run queued</span>
            )}
          </div>
          <h3>{schedule.name}</h3>
          <p>{titleCase(schedule.task_type)}</p>
        </div>
        <div className="automationScheduleControls">
          <label className="automationToggle">
            <input
              type="checkbox"
              checked={schedule.enabled}
              disabled={!canManage || busy || schedule.running}
              onChange={onToggle}
            />
            <span>{schedule.enabled ? "Enabled" : "Paused"}</span>
          </label>
          <button
            className="secondaryButton"
            type="button"
            disabled={!canManage || busy || !schedule.enabled || schedule.running}
            onClick={onRunNow}
          >
            {busy ? "Updating…" : "Run now"}
          </button>
        </div>
      </div>

      <div className="automationScheduleFacts">
        <div>
          <span>Cadence</span>
          <select
            value={schedule.interval_minutes}
            disabled={!canManage || busy || schedule.running}
            onChange={(event) => onCadence(Number(event.target.value))}
          >
            {CADENCES.map((item) => (
              <option key={item.minutes} value={item.minutes}>
                {item.label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <span>Next run</span>
          <strong>{schedule.enabled ? dateTimeLabel(schedule.next_run_at) : "Paused"}</strong>
        </div>
        <div>
          <span>Last run</span>
          <strong>{dateTimeLabel(schedule.last_run_at)}</strong>
        </div>
        <div>
          <span>Failures</span>
          <strong>{schedule.consecutive_failures}</strong>
        </div>
      </div>

      <div className="automationRunSection">
        <div className="portfolioPanelHeader">
          <div>
            <h3>Recent runs</h3>
            <p>Execution history is persisted independently of the worker process.</p>
          </div>
          <span>{schedule.recent_runs.length}</span>
        </div>

        {schedule.recent_runs.length ? (
          <div className="automationRunList">
            {schedule.recent_runs.map((run) => (
              <RunRow key={run.id} run={run} />
            ))}
          </div>
        ) : (
          <p className="automationNoRuns">
            No executions yet. The first scheduled or manual run will appear here.
          </p>
        )}
      </div>
    </article>
  );
}

function RunRow({ run }: { run: AutomationRunView }) {
  const ingested =
    typeof run.summary.ingested === "number"
      ? String(run.summary.ingested)
      : null;
  const score =
    typeof run.summary.score === "number"
      ? String(run.summary.score)
      : null;
  const band =
    typeof run.summary.band === "string"
      ? titleCase(run.summary.band)
      : null;

  return (
    <div className="automationRunRow">
      <span className={`automationRunDot ${run.status}`} />
      <div>
        <strong>{titleCase(run.status)}</strong>
        <span>
          {titleCase(run.trigger)} · {dateTimeLabel(run.started_at)}
        </span>
        {run.error_message && <small>{run.error_message}</small>}
      </div>
      <div className="automationRunResult">
        {score !== null ? (
          <>
            <strong>{score}</strong>
            <span>{band}</span>
          </>
        ) : ingested !== null ? (
          <>
            <strong>{ingested}</strong>
            <span>Ingested</span>
          </>
        ) : (
          <>
            <strong>—</strong>
            <span>{run.finished_at ? "Completed" : "In progress"}</span>
          </>
        )}
      </div>
    </div>
  );
}
