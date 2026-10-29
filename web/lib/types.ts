export type ReviewStatus =
  | "pending"
  | "accepted"
  | "edited"
  | "rejected"
  | "deferred";

export interface InboxSuggestionSummary {
  id: string;
  project_id: string;
  suggestion_type: string;
  target_entity_type: string | null;
  target_entity_id: string | null;
  proposed_changes: Record<string, unknown>;
  reason: string;
  confidence: number;
  review_status: ReviewStatus;
  evidence_count: number;
  evidence_sources: string[];
  created_at: string;
}

export interface InboxEvidenceView {
  id: string;
  source_type: string;
  source_system: string | null;
  source_reference: string | null;
  author: string | null;
  captured_at: string;
  content_excerpt: string | null;
  permission_scope: string[];
}

export interface ActionItemView {
  id: string;
  project_id: string;
  title: string;
  description: string | null;
  status: string;
  priority: string | null;
  progress_summary: string | null;
  due_date: string | null;
  owner_id: string | null;
}

export interface InboxListResponse {
  project_id: string;
  count: number;
  items: InboxSuggestionSummary[];
}

export interface InboxSuggestionDetail {
  suggestion: InboxSuggestionSummary;
  target_action_item: ActionItemView | null;
  evidence: InboxEvidenceView[];
}

export interface ReviewResponse {
  suggestion_id: string;
  review_status: ReviewStatus;
  updated_action_item: ActionItemView | null;
}


export interface AppUser {
  id: string;
  tenant_id: string;
  email: string;
  display_name: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ProjectAccess {
  project_id: string;
  name: string;
  status: string | null;
  role: string;
  permissions: string[];
}

export interface WebSession {
  user: AppUser;
  projects: ProjectAccess[];
  selected_project_id: string | null;
}


export interface ProjectView {
  id: string;
  name: string;
  description: string | null;
  objective: string | null;
  status: string | null;
  priority: string | null;
  lifecycle_phase: string | null;
  methodology: string | null;
  industry: string | null;
  start_date: string | null;
  planned_end_date: string | null;
  forecast_end_date: string | null;
}

export interface RiskView {
  id: string;
  project_id: string;
  title: string;
  description: string | null;
  category: string | null;
  probability: number | null;
  impact: string | null;
  exposure: number | null;
  impact_type: string | null;
  trigger: string | null;
  mitigation: string | null;
  contingency: string | null;
  owner_id: string | null;
  status: string;
  due_date: string | null;
}

export interface AssumptionView {
  id: string;
  project_id: string;
  title: string;
  description: string | null;
  category: string | null;
  owner_id: string | null;
  status: string;
  validation_date: string | null;
  outcome: string | null;
}

export interface IssueView {
  id: string;
  project_id: string;
  title: string;
  description: string | null;
  category: string | null;
  severity: string | null;
  impact_type: string | null;
  owner_id: string | null;
  status: string;
  due_date: string | null;
  resolution: string | null;
}

export interface DependencyView {
  id: string;
  project_id: string;
  title: string;
  description: string | null;
  dependency_type: string | null;
  owner_id: string | null;
  provider: string | null;
  required_by: string | null;
  status: string;
  criticality: string | null;
}

export interface DecisionView {
  id: string;
  project_id: string;
  title: string;
  description: string | null;
  status: string;
  decision_date: string | null;
  decision_maker_id: string | null;
  context: string | null;
  alternatives_considered: string[];
  rationale: string | null;
  expected_impact: string | null;
  review_date: string | null;
}

export interface ProjectMemorySummary {
  action_items_total: number;
  action_items_open: number;
  action_items_blocked: number;
  risks_open: number;
  assumptions_open: number;
  issues_open: number;
  dependencies_open: number;
  decisions_total: number;
  decisions_approved: number;
}

export interface ProjectMemorySnapshot {
  project: ProjectView;
  summary: ProjectMemorySummary;
  action_items: ActionItemView[];
  risks: RiskView[];
  assumptions: AssumptionView[];
  issues: IssueView[];
  dependencies: DependencyView[];
  decisions: DecisionView[];
}


export type SourceHealthStatus =
  | "healthy"
  | "attention"
  | "failed"
  | "never_synced"
  | "disabled";

export interface SourceRunView {
  id: string;
  status: "success" | "partial" | "failed";
  started_at: string;
  finished_at: string;
  duration_seconds: number;
  pages_processed: number;
  fetched: number;
  ingested: number;
  duplicates: number;
  source_changed: number;
  empty_content: number;
  skipped: number;
  errors: Array<Record<string, unknown>>;
  skips: Array<Record<string, unknown>>;
  start_checkpoint_present: boolean;
  end_checkpoint_present: boolean;
  checkpoint_fingerprint: string | null;
}

export interface SourceConnectionView {
  id: string;
  connector_key: string;
  source_type: string;
  source_system: string;
  display_name: string;
  permission_scope: string[];
  safe_config: Record<string, unknown>;
  is_enabled: boolean;
  health: SourceHealthStatus;
  checkpoint_present: boolean;
  checkpoint_fingerprint: string | null;
  checkpoint_updated_at: string | null;
  latest_run: SourceRunView | null;
  recent_runs: SourceRunView[];
}

export interface SourcesSummary {
  total: number;
  healthy: number;
  attention: number;
  failed: number;
  never_synced: number;
  disabled: number;
  total_ingested: number;
  total_skipped: number;
  total_errors: number;
}

export interface SourcesWorkspaceSnapshot {
  project_id: string;
  summary: SourcesSummary;
  sources: SourceConnectionView[];
}


export type ProjectHealthBand =
  | "green"
  | "amber"
  | "red"
  | "insufficient_data";

export type CoverageBand = "low" | "medium" | "high";

export type HealthSignalSeverity =
  | "positive"
  | "info"
  | "warning"
  | "critical";

export interface HealthSignal {
  severity: HealthSignalSeverity;
  title: string;
  detail: string;
  penalty: number;
  entity_type: string | null;
  entity_ids: string[];
}

export interface HealthFactor {
  key: string;
  name: string;
  weight: number;
  available: boolean;
  score: number | null;
  band: ProjectHealthBand;
  signals: HealthSignal[];
}

export interface ProjectHealthSnapshot {
  project_id: string;
  project_name: string;
  assessed_on: string;
  score: number | null;
  band: ProjectHealthBand;
  coverage_percent: number;
  coverage_band: CoverageBand;
  available_weight: number;
  explanation: string;
  factors: HealthFactor[];
  key_drivers: HealthSignal[];
}


export type TrendDirection =
  | "improving"
  | "stable"
  | "deteriorating"
  | "insufficient_history";

export interface HealthHistoryPoint {
  id: string;
  captured_at: string;
  captured_by: string | null;
  capture_source: string;
  model_version: string;
  score: number | null;
  band: ProjectHealthBand;
  coverage_percent: number;
  coverage_band: CoverageBand;
  factor_scores: Record<string, number | null>;
  key_drivers: HealthSignal[];
}

export interface HealthTrendSummary {
  direction: TrendDirection;
  from_snapshot_id: string | null;
  to_snapshot_id: string | null;
  score_delta: number | null;
  coverage_delta: number | null;
  factor_deltas: Record<string, number>;
  new_drivers: string[];
  resolved_drivers: string[];
  elapsed_hours: number | null;
  explanation: string;
}

export interface ProjectHealthHistory {
  project_id: string;
  count: number;
  points: HealthHistoryPoint[];
  trend: HealthTrendSummary;
}

export interface HealthSnapshotCaptureResponse {
  created: boolean;
  snapshot: HealthHistoryPoint;
}


export interface RollupSummary {
  projects_total: number;
  projects_scored: number;
  score: number | null;
  band: ProjectHealthBand;
  average_coverage_percent: number;
  green: number;
  amber: number;
  red: number;
  insufficient_data: number;
  improving: number;
  stable: number;
  deteriorating: number;
  insufficient_history: number;
}

export interface ProjectRollupItem {
  project_id: string;
  name: string;
  status: string | null;
  priority: string | null;
  program_id: string | null;
  program_name: string | null;
  portfolio_id: string | null;
  portfolio_name: string | null;
  health_score: number | null;
  health_band: ProjectHealthBand;
  health_coverage_percent: number;
  trend_direction: TrendDirection;
  trend_score_delta: number | null;
  top_drivers: string[];
}

export interface ProgramRollup {
  id: string;
  name: string;
  description: string | null;
  status: string | null;
  portfolio_id: string | null;
  portfolio_name: string | null;
  summary: RollupSummary;
  projects: ProjectRollupItem[];
}

export interface PortfolioRollup {
  id: string;
  name: string;
  description: string | null;
  status: string | null;
  strategic_objectives: string[];
  summary: RollupSummary;
  programs: ProgramRollup[];
  direct_projects: ProjectRollupItem[];
}

export interface CrossProjectSignal {
  signal_type: "risk" | "dependency";
  title: string;
  project_count: number;
  project_ids: string[];
  project_names: string[];
  statuses: string[];
  severity_labels: string[];
  explanation: string;
}

export interface ProgramPortfolioOverview {
  summary: RollupSummary;
  portfolios: PortfolioRollup[];
  standalone_programs: ProgramRollup[];
  standalone_projects: ProjectRollupItem[];
  attention_projects: ProjectRollupItem[];
  cross_project_signals: CrossProjectSignal[];
}


export interface ExecutiveSummary {
  health: RollupSummary;
  projects_needing_attention: number;
  pending_inbox: number;
  deferred_inbox: number;
  critical_raid: number;
  pending_decisions: number;
  source_failures: number;
  source_attention: number;
  cross_project_signals: number;
}

export interface ExecutiveInboxItem {
  suggestion_id: string;
  project_id: string;
  project_name: string;
  suggestion_type: string;
  review_status: ReviewStatus;
  reason: string;
  confidence: number;
  created_at: string;
}

export interface ExecutiveRAIDItem {
  entity_type: "Risk" | "Assumption" | "Issue" | "Dependency";
  entity_id: string;
  project_id: string;
  project_name: string;
  title: string;
  status: string;
  severity: string;
  due_date: string | null;
  reason: string;
}

export interface ExecutiveDecisionItem {
  decision_id: string;
  project_id: string;
  project_name: string;
  title: string;
  status: string;
  review_date: string | null;
  expected_impact: string | null;
}

export interface ExecutiveSourceAlert {
  source_id: string;
  project_id: string;
  project_name: string;
  display_name: string;
  source_system: string;
  health: SourceHealthStatus;
  latest_status: string | null;
  latest_finished_at: string | null;
  error_count: number;
  skipped: number;
}

export interface ExecutiveDashboardSnapshot {
  generated_at: string;
  summary: ExecutiveSummary;
  attention_projects: ProjectRollupItem[];
  inbox_items: ExecutiveInboxItem[];
  critical_raid: ExecutiveRAIDItem[];
  pending_decisions: ExecutiveDecisionItem[];
  source_alerts: ExecutiveSourceAlert[];
  cross_project_signals: CrossProjectSignal[];
}


export type StatusReportAudience = "executive" | "project_team";

export interface GroundFact {
  fact_id: string;
  category: string;
  text: string;
  entity_type: string | null;
  entity_id: string | null;
  evidence_ids: string[];
  observed_at: string | null;
}

export interface ReportStatement {
  text: string;
  fact_ids: string[];
}

export interface StatusReportContent {
  executive_summary: ReportStatement[];
  accomplishments: ReportStatement[];
  risks_and_issues: ReportStatement[];
  decisions_needed: ReportStatement[];
  next_steps: ReportStatement[];
  data_quality_notes: ReportStatement[];
}

export interface StatusReportValidation {
  grounded: boolean;
  statement_count: number;
  cited_fact_count: number;
  available_fact_count: number;
}

export interface StatusReportDraft {
  project_id: string;
  project_name: string;
  title: string;
  audience: StatusReportAudience;
  period_start: string;
  period_end: string;
  generated_at: string;
  provider: string;
  model: string;
  health_score: number | null;
  health_band: ProjectHealthBand;
  health_coverage_percent: number;
  trend_direction: TrendDirection;
  trend_score_delta: number | null;
  content: StatusReportContent;
  facts: GroundFact[];
  validation: StatusReportValidation;
  disclaimer: string;
}


export type AutomationTaskType = "health_snapshot";
export type AutomationRunStatus =
  | "running"
  | "success"
  | "failed"
  | "abandoned";
export type AutomationTrigger = "scheduled" | "manual";

export interface AutomationRunView {
  id: string;
  schedule_id: string;
  project_id: string;
  task_type: AutomationTaskType;
  trigger: AutomationTrigger;
  status: AutomationRunStatus;
  worker_id: string;
  scheduled_for: string;
  started_at: string;
  finished_at: string | null;
  summary: Record<string, unknown>;
  error_message: string | null;
}

export interface AutomationScheduleView {
  id: string;
  project_id: string;
  name: string;
  task_type: AutomationTaskType;
  interval_minutes: number;
  enabled: boolean;
  config: Record<string, unknown>;
  next_run_at: string;
  pending_trigger: AutomationTrigger;
  last_run_at: string | null;
  last_status: AutomationRunStatus | null;
  consecutive_failures: number;
  created_by: string | null;
  running: boolean;
  created_at: string;
  updated_at: string;
  recent_runs: AutomationRunView[];
}

export interface AutomationsSummary {
  total: number;
  enabled: number;
  running: number;
  failing: number;
  due_now: number;
}

export interface AutomationsWorkspaceSnapshot {
  project_id: string;
  generated_at: string;
  summary: AutomationsSummary;
  schedules: AutomationScheduleView[];
}
