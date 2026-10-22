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
