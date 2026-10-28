export type Eligibility =
  | "verified_yes"
  | "verified_no"
  | "unknown"
  | "not_applicable";

export type RecommendationBucket =
  | "act_now"
  | "prepare_early"
  | "keep_on_radar"
  | "needs_verification"
  | "archive"
  | "excluded";

export interface OpportunityCard {
  id: string;
  title: string;
  organization: string | null;
  organization_domain: string | null;
  type: string;
  bucket: RecommendationBucket;
  score: number | null;
  confidence: number | null;
  professional_eligibility: Eligibility;
  india_eligibility: Eligibility;
  student_only: boolean;
  location: string | null;
  workplace_type: string | null;
  life_state: string;
  deadline_on: string | null;
  deadline_at: string | null;
  deadline_precision: string;
  compensation: string | null;
  official_url: string;
  user_decision: string;
  credibility: string;
  first_seen_at: string | null;
  last_seen_at: string | null;
  last_material_change_at: string | null;
  is_fixture: boolean;
  why: string | null;
  hard_gate: string | null;
  next_action: string | null;
}

export interface Assessment {
  score: number;
  bucket: RecommendationBucket;
  confidence: number;
  hard_gate: string;
  factors: Record<string, unknown>;
  reason: string | null;
  rules_version: string;
  profile_version: number;
  evidence: unknown[];
  created_at: string | null;
}

export interface Revision {
  id: string;
  number: number;
  type: string;
  observed_at: string;
  diff: Record<string, unknown>;
  hash: string;
  evidence_ids: unknown[];
}

export interface OpportunitySourceLink {
  source_id: string;
  source_name: string;
  source_kind: string;
  officialness: string;
  item_url: string;
  first_seen_at: string | null;
  last_seen_at: string | null;
  absence_count: number;
  evidence: { url: string; fetched_at: string; excerpt: string | null } | null;
}

export interface OpportunityAlert {
  id: string;
  channel: string;
  kind: string;
  status: string;
  sent_at: string | null;
  scheduled_for: string | null;
}

export interface OpportunityDetail extends OpportunityCard {
  application_url: string;
  description: string | null;
  requirements: string | null;
  qualification: Record<string, unknown> | null;
  assessment: Assessment | null;
  revisions: Revision[];
  sources: OpportunitySourceLink[];
  alerts: OpportunityAlert[];
  notes: string | null;
  followup_due_at: string | null;
}

export interface WatchlistItem extends OpportunityCard {
  followup_due_at: string | null;
  followup_is_due: boolean;
}

export interface WatchlistGroup {
  key: string;
  title: string;
  items: WatchlistItem[];
  total: number;
}

export interface Watchlist {
  groups: WatchlistGroup[];
  followups_due: number;
}

export interface OpportunityList {
  items: OpportunityCard[];
  total: number;
  limit: number;
  offset: number;
}

export interface DeadlineItem extends OpportunityCard {
  deadline_label: string;
  days_until_deadline: number | null;
}

export interface DeadlineList {
  total: number;
  items: DeadlineItem[];
}

export interface DigestSummary {
  id: string;
  kind: "daily" | "weekly";
  period_start: string;
  period_end: string;
  generated_at: string;
  sent_status: string;
  reviewed_at: string | null;
  opportunity_count: number;
}

export interface DigestDetail extends DigestSummary {
  content_md: string;
  content_json: Record<string, unknown>;
  opportunity_ids: string[];
}

export interface DigestList {
  total: number;
  limit: number;
  offset: number;
  items: DigestSummary[];
}

export interface SourceSummary {
  id: string;
  name: string;
  kind: string;
  root_url: string;
  enabled: boolean;
  officialness: string;
  approval_status: string;
  legal_review_status: string;
  health: string;
  consecutive_failures: number;
  interval_hours: number;
  schedule_cron: string | null;
  last_attempt_at: string | null;
  last_success_at: string | null;
  last_error: string | null;
  next_due_at: string | null;
  last_run: SourceRun | null;
}

export interface SourceDetail extends SourceSummary {
  config_json: Record<string, unknown>;
  rate_limit_json: Record<string, unknown>;
}

export interface SourceRun {
  id: string;
  status: string;
  scan_complete: boolean;
  http_status: number | null;
  records_seen: number;
  records_created: number;
  records_updated: number;
  records_skipped: number;
  error_category: string | null;
  error: string | null;
  started_at: string;
  finished_at: string | null;
}

export interface SourceRunList {
  items: SourceRun[];
}

export interface Dashboard {
  active_opportunities: number;
  source_health: Record<string, number>;
  buckets: Record<string, number>;
  failing_sources: {
    id: string;
    name: string;
    last_error: string | null;
    last_error_at: string | null;
    consecutive_failures: number;
  }[];
  recent_failed_runs: {
    id: string;
    source: string;
    started_at: string;
    error_category: string | null;
    error: string | null;
  }[];
  jobs: Record<string, number>;
  pending_alerts: number;
  scan_is_partial: boolean;
}

export interface UserProfile {
  id: string;
  employment_stage: string;
  student_status: boolean;
  home_country: string;
  preferred_countries: string[];
  relocation_allowed: boolean;
  categories: string[];
  skills: string[];
  ignore_terms: string[];
  desired_yoe_min: number | null;
  desired_yoe_max: number | null;
  quiet_hours_start: number;
  quiet_hours_end: number;
  timezone: string;
  alert_channels: string[];
  max_immediate_alerts_per_week: number;
  scoring_version: string;
  profile_version: number;
}

export interface DiscoveryCandidate {
  id: string;
  url: string;
  discovered_at: string;
  candidate_type: string | null;
  suggested_adapter: string | null;
  officialness_guess: string;
  approval_status: string;
  legal_review_status: string;
  promoted_source_id: string | null;
  notes: string | null;
}

export interface DiscoveryList {
  items: DiscoveryCandidate[];
}

export interface IntegrationStatus {
  changedetection: {
    enabled: boolean;
    base_url_configured: boolean;
    webhook_configured: boolean;
  };
  telegram: { enabled: boolean };
  smtp: { enabled: boolean; host_configured: boolean; tls_port: number };
  sheets: {
    enabled: boolean;
    configured: boolean;
    tab: string;
    counts: Record<string, number>;
    last_success_at: string | null;
    last_error: string | null;
  };
  ai: { enabled: boolean; provider: string | null };
}

export interface AlertItem {
  id: string;
  channel: string;
  kind: string;
  status: string;
  scheduled_for: string | null;
  sent_at: string | null;
  created_at: string;
  payload: Record<string, unknown>;
  error: string | null;
}

export interface AlertList {
  items: AlertItem[];
}

export interface JobItem {
  id: string;
  kind: string;
  state: string;
  source_id: string | null;
  attempts: number;
  available_at: string;
  last_error: string | null;
  created_at: string;
}

export interface JobList {
  active: Record<string, number>;
  items: JobItem[];
}

export interface SourceHealth {
  counts: Record<string, number>;
  total: number;
  attention: {
    id: string;
    name: string;
    health: string;
    last_error: string | null;
    last_success_at: string | null;
  }[];
  last_source_success_at: string | null;
}

export interface SystemStatus {
  database: string;
  failing_sources: number;
  stale_sources: number;
  active_jobs: number;
  time: string;
}
