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
