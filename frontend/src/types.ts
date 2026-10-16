export type MatchTime = { period: 1 | 2; elapsed_ms: number }
export type Window = { start: MatchTime; end: MatchTime; boundary: '(start,end]' }
export type Reference = { event_id: string; revision: number }
export type Event = {
  schema_version: string; match_id: string; event_id: string; revision: number;
  source_delivery_sequence: number; occurrence_order: number;
  occurred_at: MatchTime; available_at: MatchTime;
  actor: { team_id: string; player_id: string }; position: { x: number; y: number };
  action: { kind: string; from_team_id?: string; origin?: string; control?: string; [key: string]: unknown }
}
export type WindowEvidence = { window: Window; value: number; source_events: Reference[] }
export type Evidence = {
  packet: { evidence_id: string; evidence_version: number; match_id: string; subject_team_id: string;
    metric: string; rule_version: string; cutoff: MatchTime; baseline: WindowEvidence; current: WindowEvidence };
  records: Event[]; metric_definition: string; coordinate_system: string
}
export type Insight = {
  insight_id: string; revision: number; evidence_id: string; evidence_version: number;
  claim_type: 'fact'; template: 'high_recovery_increase_v1'; title: string; explanation: string;
  facts: { subject_team_id: string; baseline_count: number; current_count: number; baseline_window: Window; current_window: Window };
  eligible_at: MatchTime
}
export type Snapshot = {
  recap?: SegmentRecap | null;
  adapted_recap?: SegmentRecap | null;
  recap_workflow?: RecapWorkflow | null;
  pressure?: PressureView | null;
  pressure_lifecycle?: PressureChange[];
  selected_kind?: 'recovery' | 'pressure' | 'contribution' | null;
  contribution?: ContributionView | null;
  contribution_lifecycle?: ContributionChange[];
  audience?: Audience | null;
  teams?: { team_id: string; name: string; player_ids: string[] }[];
  workflow?: Workflow | null;
  adaptation?: Adaptation | null;
  scenario_id: string;
  scope_id: string; history_version: number; replay_end: MatchTime;
  lifecycle: { insight_id: string; revision: number; operation: 'create' | 'update' | 'withdraw';
    available_at: MatchTime; insight: Insight | null; evidence: Evidence;
    invalidates: { evidence_id: string; evidence_version: number }[] } | null;
  state: { match_id: string; at: MatchTime; score: Record<string, number>; controlled_possession_team_id: string;
    source_delivery_cursor: number; applied_events: Reference[] };
  metrics: { team_id: string; pass_attempts: number; pass_completions: number; attempted_pass_distance_m: number;
    completed_pass_distance_m: number; high_recoveries: Reference[] }[];
  windows: [Window, Window]; comparison_status: 'collecting' | 'no_increase' | 'ready';
  insight: Insight | null; evidence: Evidence | null
}
export type Adaptation = { attempt_id: string; evidence_id: string; evidence_version: number; text: string; expires_at_unix_ms: number }
export type Workflow = { attempt_id: string; status: string; actions: { label: string; elapsed_ms: number }[] }
export type Preferences = { language: 'en' | 'zh-Hans'; depth: 'analyst' | 'casual'; club_id: string | null; player_id: string | null; metric_focus: 'balanced' | 'high_recoveries' | 'passing' | 'pressure_exposure' | 'pressured_escape' | 'possession_without_progression' | 'player_high_recovery_share'; card_budget: number }
export const defaultPreferences: Preferences = { language: 'en', depth: 'analyst', club_id: null, player_id: null, metric_focus: 'balanced', card_budget: 1 }
export type Variant = { insight_id: string; revision: number; language: Preferences['language']; depth: Preferences['depth']; club_id: string | null; player_id: string | null; title: string; explanation: string; qualification: string; subject_name: string }
export type Audience = { preferences: Preferences; state: 'ready' | 'collecting' | 'no_increase' | 'no_contribution' | 'budget_hidden'; message: string; variant: Variant | null; priority: number; highlighted_events: Reference[]; sequence: Event[]; supporting_event_count: number; selected_event_count: number }
export type Scenario = { scenario_id: string; label: string; start: MatchTime; end: MatchTime }

export type Episode = { episode_id: string; start: MatchTime; end: MatchTime | null; observed_start: boolean; outcome: string; pressure_events: Reference[]; source_events: Reference[] }
export type EpisodeWindow = { window: Window; included: string[]; boundary_excluded: string[]; left_censored: string[]; pending: string[]; completed: number; exposed: number; escaped_under_pressure: number; exposure_rate: number | null; pressured_escape_rate: number | null }
export type PossessionEpisode = Omit<Episode, 'pressure_events'> & { start_x: number; maximum_x: number; forward_gain_m: number; completed_actions: number; controlled_span_ms: number }
export type ProgressionWindow = Omit<EpisodeWindow, 'exposed' | 'escaped_under_pressure' | 'exposure_rate' | 'pressured_escape_rate'> & { without_progression: string[]; without_progression_count: number; brief_excluded: string[]; limited_space: string[]; rate: number | null }
export type RateDecision = { metric: 'pressure_exposure' | 'pressured_escape' | 'possession_without_progression'; status: string; direction: string; baseline_numerator: number; baseline_denominator: number; current_numerator: number; current_denominator: number; change: number | null }
export type PressureChange = { insight_id: string; evidence_id: string; revision: number; operation: 'create' | 'update' | 'withdraw'; available_at: MatchTime; metric: RateDecision['metric']; decision: RateDecision; invalidates: number[];
  evidence: { match_id: string; subject_team_id: string; cutoff: MatchTime; rule_version: string; baseline: EpisodeWindow | ProgressionWindow; current: EpisodeWindow | ProgressionWindow; episodes: (Episode | PossessionEpisode)[]; records: Event[]; disclosure: string; policy: { minimum_episodes: number; minimum_rate_change: number; cooldown_ms: number; forward_gain_m?: number; minimum_completed_actions?: number; minimum_controlled_span_ms?: number } } }
export type PressureView = { preferences: Preferences; state: string; message: string; publication: PressureChange | null; variant: Variant | null; highlighted_events: Reference[]; priority: number }

export function clock(ms: number, period = 2) {
  const total = Math.floor(ms / 1000)
  return `${Math.floor(total / 60) + (period === 2 ? 45 : 0)}:${String(total % 60).padStart(2, '0')}`
}
export function windowLabel(window: Window) { return `${clock(window.start.elapsed_ms)}–${clock(window.end.elapsed_ms)}` }

export type ContributionWindow = { window: Window; team_events: Reference[]; player_events: Reference[]; team_count: number; player_count: number; share: number | null }
export type ContributionChange = { insight_id: string; evidence_id: string; revision: number; operation: 'create' | 'update' | 'withdraw'; available_at: MatchTime; invalidates: number[];
  evidence: { rule_version: string; metric: 'player_high_recovery_share'; match_id: string; subject_team_id: string; subject_player_id: string; cutoff: MatchTime; coverage_start: MatchTime;
    baseline: ContributionWindow; current: ContributionWindow; records: Event[]; disclosure: string;
    policy: { minimum_team_recoveries: number; minimum_current_player_recoveries: number; minimum_count_increase: number; minimum_share_increase: number };
    decision: { status: string; count_change: number; share_change: number | null } } }
export type ContributionView = { preferences: Preferences; state: string; message: string; publication: ContributionChange | null; variant: Variant | null; highlighted_events: Reference[]; priority: number }

export type RecapCitation = { kind: 'recovery' | 'pressure' | 'contribution'; insight_id: string; revision: number; evidence_id: string; available_at: MatchTime }
export type SegmentRecap = { match_id: string; cutoff: MatchTime; windows: [Window, Window]; preferences: Preferences;
  state: 'ready' | 'collecting' | 'no_eligible' | 'budget_hidden'; statements: { narrative: Variant; citation: RecapCitation }[]; omitted_count: number }

export type RecapWorkflow = Workflow & { applied: boolean; heading: 'segment_review' | 'key_changes' | null; expires_at_unix_ms: number }
