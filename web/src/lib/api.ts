const BASE = '/api';

async function fetchJSON<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${url}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status}: ${text}`);
  }
  return res.json();
}

export const api = {
  // Customers
  listCustomers: (page = 1, size = 20, search = '', segment = '') =>
    fetchJSON<{ customers: Customer[]; total: number }>(`/customers?page=${page}&size=${size}&search=${search}&segment=${segment}`),
  getCustomer360: (id: string) => fetchJSON<Customer360>(`/customers/${id}`),
  getCustomerEvents: (id: string, limit = 50) => fetchJSON<{ events: Event[] }>(`/customers/${id}/events?limit=${limit}`),

  // Workflows
  getJourneyState: (id: string) => fetchJSON<JourneyState>(`/workflows/${id}`),
  startJourney: (id: string) => fetchJSON<{ workflow_id: string }>(`/workflows/${id}/start`, { method: 'POST' }),

  // Agents
  listAgents: () => fetchJSON<{ agents: AgentInfo[] }>('/agents'),
  invokeDigitalChannel: (body: { customer_id: string; message: string; channel?: string }) =>
    fetchJSON<AgentResult>('/agents/digital-channel/invoke', { method: 'POST', body: JSON.stringify(body) }),
  invokeCopilot: (body: Record<string, unknown>) =>
    fetchJSON<AgentResult>('/agents/copilot/invoke', { method: 'POST', body: JSON.stringify(body) }),
  invokeCaseReasoning: (body: Record<string, unknown>) =>
    fetchJSON<AgentResult>('/agents/case-reasoning/invoke', { method: 'POST', body: JSON.stringify(body) }),
  invokePortfolio: (body: Record<string, unknown>) =>
    fetchJSON<AgentResult>('/agents/portfolio/invoke', { method: 'POST', body: JSON.stringify(body) }),
  invokeQuality: (body: Record<string, unknown>) =>
    fetchJSON<AgentResult>('/agents/quality/invoke', { method: 'POST', body: JSON.stringify(body) }),
  getReasoningTraces: (limit = 20) => fetchJSON<{ traces: Event[] }>(`/agents/reasoning-traces?limit=${limit}`),

  // Portfolio
  portfolioSummary: () => fetchJSON<PortfolioSummary>('/portfolio/summary'),
  delinquencyBreakdown: () => fetchJSON<{ breakdown: DelinquencyBucket[] }>('/portfolio/delinquency'),
  dashboardMetrics: () => fetchJSON<DashboardMetrics>('/portfolio/dashboard-metrics'),
  channelActivity: (days = 30) => fetchJSON<{ activity: ChannelActivity[] }>(`/portfolio/channel-activity?days=${days}`),

  // Events
  listEvents: (limit = 50, category = '') => fetchJSON<{ events: Event[] }>(`/events?limit=${limit}&category=${category}`),
  eventStats: (hours = 24) => fetchJSON<{ stats: EventStat[] }>(`/events/stats?hours=${hours}`),
  eventTimeline: (customerId: string) => fetchJSON<{ timeline: Event[] }>(`/events/timeline?customer_id=${customerId}`),

  // Strategies
  evaluateSegmentation: (input: Record<string, unknown>) =>
    fetchJSON<Record<string, unknown>>('/strategies/evaluate/segmentation', { method: 'POST', body: JSON.stringify(input) }),
  evaluateFull: (input: Record<string, unknown>) =>
    fetchJSON<Record<string, unknown>>('/strategies/evaluate/full', { method: 'POST', body: JSON.stringify(input) }),
  getAuditLog: () => fetchJSON<{ audit_log: AuditEntry[] }>('/strategies/audit-log'),
  strategySegmentMatrix: () => fetchJSON<{ cells: SegmentMatrixCell[] }>('/strategies/segment-matrix'),
  strategyTreatmentMatrix: () => fetchJSON<{ rows: TreatmentMatrixRow[] }>('/strategies/treatment-matrix'),
  strategyComplianceFiring: () => fetchJSON<{ reasons: ComplianceFiringRow[] }>('/strategies/compliance-firing'),
  strategyRecentDecisions: (limit = 30) => fetchJSON<{ decisions: StrategyDecisionRow[] }>(`/strategies/recent-decisions?limit=${limit}`),
  strategyVersionComparison: () => fetchJSON<{ versions: StrategyVersionRow[] }>('/strategies/version-comparison'),
  strategySideBySide: (customer_input: Record<string, unknown>) =>
    fetchJSON<{ results: SideBySideResult[] }>('/strategies/evaluate-side-by-side', {
      method: 'POST',
      body: JSON.stringify({ customer_input }),
    }),
  strategyVersionTimeline: () => fetchJSON<{ versions: StrategyVersionRow[]; daily_evaluations: { strategy_version: string; day: string; evaluations: number }[] }>('/strategies/version-timeline'),

  // Scenarios
  listScenarios: () => fetchJSON<{ scenarios: Scenario[] }>('/scenarios'),
  runScenario: (id: string, body?: Record<string, unknown>) =>
    fetchJSON<{ scenario: string; status: string; result: unknown }>(`/scenarios/${id}/run`, { method: 'POST', body: JSON.stringify(body ?? {}) }),

  // Customer detail
  getCustomerPayments: (id: string) =>
    fetchJSON<{ payments: Payment[]; customer_id: string }>(`/customers/${id}/payments`),
  getCustomerContacts: (id: string) =>
    fetchJSON<{ contacts: Contact[]; customer_id: string }>(`/customers/${id}/contacts`),

  // Portfolio detail
  portfolioSegments: () => fetchJSON<{ segments: Segment[] }>('/portfolio/segments'),
  ptpSummary: () => fetchJSON<{ ptps: PtpSummaryEntry[] }>('/portfolio/ptp-summary'),
  complianceFlags: () => fetchJSON<{ flags: ComplianceFlagSummary[] }>('/portfolio/compliance-flags'),

  // Workflow detail
  getWorkflowActions: (id: string) => fetchJSON<{ actions: WorkflowAction[] }>(`/workflows/${id}/actions`),
  getWorkflowEvents: (id: string) => fetchJSON<{ events: Event[] }>(`/workflows/${id}/events`),

  // Platform Operations
  platformServices: () => fetchJSON<{ services: ServiceHeartbeat[]; timestamp: number }>('/platform/services'),
  platformKafkaTopics: () => fetchJSON<{ topics: KafkaTopicInfo[]; timestamp: number }>('/platform/kafka/topics'),
  platformConsumerLag: () => fetchJSON<{ consumer_groups: ConsumerGroupLag[]; timestamp: number }>('/platform/kafka/consumer-lag'),
  platformOpaPolicies: () => fetchJSON<{ policies: OpaPolicy[]; count: number }>('/platform/opa/policies'),
  platformOpaDecisions: (limit = 50) => fetchJSON<{ decisions: OpaDecision[] }>(`/platform/opa/decisions?limit=${limit}`),
  platformTrace: (eventId: string) => fetchJSON<TraceResult>(`/platform/trace/${eventId}`),
  platformHealth: () => fetchJSON<PlatformHealth>('/platform/health/summary'),

  // Operations Floor
  opsPulse: () => fetchJSON<OperationsPulse>('/operations/portfolio-pulse'),
  opsLiveJourneys: (limit = 80) => fetchJSON<{ journeys: LiveJourney[]; count: number }>(`/operations/live-journeys?limit=${limit}`),
  opsChannelActivity: () => fetchJSON<{ channels: ChannelActivityRow[] }>('/operations/channel-activity'),
  opsAgentActivity: (limit = 30) => fetchJSON<{ actions: AgentAction[] }>(`/operations/agent-activity?limit=${limit}`),
  opsAgentSummary: () => fetchJSON<{ agents: AgentSummary[] }>('/operations/agent-activity/summary'),
  opsEscalationQueue: () => fetchJSON<{ escalations: Escalation[] }>('/operations/escalation-queue'),
  opsComplianceBlocks: (limit = 20) => fetchJSON<{ blocks: ComplianceBlock[] }>(`/operations/compliance-blocks?limit=${limit}`),
  opsPortfolioKpis: () => fetchJSON<PortfolioKpis>('/operations/portfolio-kpis'),

  // Customer Story
  storyNarrative: (id: string) => fetchJSON<StoryNarrative>(`/story/customers/${id}/narrative`),
  storyTimeline: (id: string, limit = 200) => fetchJSON<{ timeline: EnrichedEvent[]; count: number }>(`/story/customers/${id}/timeline?limit=${limit}`),
  storyDecisions: (id: string, limit = 30) => fetchJSON<{ decisions: StrategyDecisionAudit[] }>(`/story/customers/${id}/decisions?limit=${limit}`),
  storyAgentActions: (id: string, limit = 30) => fetchJSON<{ actions: AgentAction[] }>(`/story/customers/${id}/agent-actions?limit=${limit}`),
  storyEscalations: (id: string) => fetchJSON<{ escalations: Escalation[] }>(`/story/customers/${id}/escalations`),
  storyActivityDigest: (id: string, window: string = '7d') => fetchJSON<ActivityDigest>(`/story/customers/${id}/activity-digest?window=${window}`),

  // Lakehouse
  lakehouseTopology: () => fetchJSON<LakehouseTopology>('/lakehouse/topology'),
  lakehouseBronzeObjects: (topic?: string, limit = 50) =>
    fetchJSON<{ bucket: string; prefix: string; objects: S3Object[] }>(`/lakehouse/bronze/objects?${topic ? `topic=${topic}&` : ''}limit=${limit}`),
  lakehouseSilverPartitions: () => fetchJSON<{ bucket: string; partitions: SilverPartition[] }>('/lakehouse/silver/partitions'),
  lakehouseGoldMarts: () => fetchJSON<{ bucket: string; marts: GoldMart[]; manifest: { last_run_at?: string; marts?: string[]; build_number?: number } | null }>('/lakehouse/gold/marts'),
  lakehouseSavedQueries: () => fetchJSON<{ queries: SavedQuery[] }>('/lakehouse/queries'),
  lakehouseQuery: (sql: string, limit = 100) => fetchJSON<QueryResult>('/lakehouse/query', {
    method: 'POST', body: JSON.stringify({ sql, limit }),
  }),
  lakehouseLineage: (eventId: string) => fetchJSON<EventLineage>(`/lakehouse/lineage/${eventId}`),
  lakehouseLineageSuggestions: (limit = 12) => fetchJSON<{ suggestions: LineageSuggestion[] }>(`/lakehouse/lineage-suggestions?limit=${limit}`),
};

// Types
export interface Customer {
  customer_id: string;
  first_name: string;
  last_name: string;
  email: string;
  phone_primary: string;
  risk_score: number;
  behavioral_score: number;
  preferred_channel: string;
  timezone: string;
  account_id: string;
  product_type: string;
  current_balance: number;
  days_past_due: number;
  delinquency_stage: string;
  total_past_due: number;
  last_payment_date: string | null;
  last_payment_amount: number | null;
}

export interface Customer360 {
  profile: Record<string, unknown>;
  accounts: Record<string, unknown>[];
  compliance_flags: Record<string, unknown>[];
  active_ptps: Record<string, unknown>[];
  recent_events: Event[];
}

export interface JourneyState {
  stage: string;
  dpd: number;
  balance: number;
  suspended: boolean;
  compliance_flags: string[];
  actions_count: number;
  events_count: number;
  [key: string]: unknown;
}

export interface AgentInfo {
  id: string;
  name: string;
  agent_type: string;
  model: string;
  tool_count: number;
}

export interface AgentResult {
  response_text?: string;
  action_taken?: string;
  confidence?: number;
  escalated?: boolean;
  tokens_used?: number;
  latency_ms?: number;
  reasoning_trace?: ReasoningTrace;
  error?: string;
}

export interface ReasoningTrace {
  event_id: string;
  agent_type: string;
  customer_id: string;
  reasoning_steps: ReasoningStep[];
  action_taken: string;
  confidence: number;
  escalated: boolean;
  tokens_used: number;
  latency_ms: number;
  model: string;
}

export interface ReasoningStep {
  step: string;
  result: string;
  confidence?: number;
}

export interface PortfolioSummary {
  total_customers: number;
  total_accounts: number;
  total_outstanding: number;
  avg_dpd: number;
  total_past_due: number;
  current_count: number;
  bucket_1_29: number;
  bucket_30_59: number;
  bucket_60_89: number;
  bucket_90_plus: number;
}

export interface DelinquencyBucket {
  delinquency_stage: string;
  count: number;
  total_balance: number;
  avg_dpd: number;
  total_past_due: number;
}

export interface DashboardMetrics {
  summary: PortfolioSummary;
  delinquency: { breakdown: DelinquencyBucket[] };
  ptps: { ptps: Record<string, unknown>[] };
  compliance_flags: { flags: Record<string, unknown>[] };
}

export interface ChannelActivity {
  channel: string;
  direction: string;
  event_category: string;
  event_count: number;
  unique_customers: number;
}

export interface Event {
  event_id: string;
  customer_id: string;
  event_type: string;
  event_category: string;
  channel: string;
  direction: string;
  intent: string;
  payload: Record<string, unknown>;
  source_service: string;
  occurred_at: string;
}

export interface EventStat {
  event_category: string;
  count: number;
  unique_customers: number;
}

export interface AuditEntry {
  strategy_version: string;
  change_type: string;
  change_details: string;
  changed_by: string;
  change_reason: string;
  created_at: string;
}

export interface SegmentMatrixCell {
  dpd_bucket: string;
  risk_tier: string;
  value_segment: string;
  n: number;
  unique_customers: number;
}

export interface TreatmentMatrixRow {
  dpd_bucket: string;
  risk_tier: string;
  treatment_action: string;
  message_tone: string;
  n: number;
}

export interface ComplianceFiringRow {
  reason: string;
  check_type: string;
  action_blocked: string | null;
  passed: boolean;
  n: number;
}

export interface StrategyDecisionRow {
  audit_id: string;
  customer_id: string;
  strategy_version: string;
  policy_name: string;
  dpd_bucket: string;
  risk_tier: string;
  value_segment: string;
  treatment_action: string;
  recommended_channels: unknown;
  can_contact: string;
  input_context: Record<string, unknown>;
  decision: Record<string, unknown>;
  evaluated_at: string;
}

export interface StrategyVersionRow {
  strategy_version: string;
  role: 'champion' | 'challenger' | 'retired' | string;
  description: string;
  allocation_pct: number | string;
  activated_at: string | null;
  retired_at: string | null;
  assigned_customers: number;
  customers_24h?: number;
  evaluations_24h?: number;
  agent_actions_24h?: number;
  escalations_24h?: number;
  cures_24h?: number;
  avg_confidence?: number | null;
  cure_rate_24h?: number | null;
}

export interface SideBySideResult {
  strategy_version: string;
  role: string;
  description: string;
  policies: {
    segmentation: Record<string, unknown>;
    treatment: Record<string, unknown>;
    channel_routing: Record<string, unknown>;
    compliance: Record<string, unknown>;
  };
}

export interface Scenario {
  id: string;
  name: string;
  description: string;
  default_customer: string;
}

export interface Payment {
  payment_id: string;
  account_id: string;
  customer_id: string;
  amount: number;
  payment_date: string;
  due_date: string;
  payment_method: string;
  status: string;
}

export interface Contact {
  contact_id: string;
  customer_id: string;
  account_id: string;
  channel: string;
  direction: string;
  contact_type: string;
  outcome: string;
  agent_id: string;
  duration_seconds: number;
  notes: string;
  occurred_at: string;
}

export interface Segment {
  delinquency_stage: string;
  risk_bucket: string;
  count: number;
  avg_balance: number;
  avg_dpd: number;
}

export interface PtpSummaryEntry {
  status: string;
  count: number;
  total_amount: number;
  avg_amount: number;
}

export interface ComplianceFlagSummary {
  flag_type: string;
  status: string;
  count: number;
}

export interface WorkflowAction {
  action_type: string;
  channel: string;
  parameters: Record<string, unknown>;
  priority: number;
  reason: string;
  timestamp?: string;
}

export interface ServiceHeartbeat {
  service_name: string;
  instance_id: string;
  status: string;
  throughput_per_sec: number | null;
  error_count_5m: number;
  p99_latency_ms: number | null;
  extra: Record<string, unknown>;
  last_seen_at: string;
  seconds_since_last_seen: number;
}

export interface KafkaTopicInfo {
  topic: string;
  partition_count: number;
  total_messages: number;
  throughput_per_sec: number | null;
  partitions: { id: number; leader: number; begin_offset: number; end_offset: number }[];
}

export interface ConsumerGroupLag {
  group_id: string;
  total_lag: number;
  partitions: { topic: string; partition: number; committed: number; end_offset: number; lag: number }[];
}

export interface OpaPolicy {
  id: string;
  ast_size: number;
  raw_present: boolean;
}

export interface OpaDecision {
  audit_id: string;
  customer_id: string;
  strategy_version: string;
  policy_name: string;
  input_context: Record<string, unknown>;
  decision: Record<string, unknown>;
  evaluated_at: string;
}

export interface TraceHop {
  event_id: string;
  customer_id: string;
  event_type: string;
  event_category: string;
  channel: string;
  direction: string;
  source_service: string;
  payload: Record<string, unknown>;
  correlation_id: string;
  occurred_at: string;
  received_at: string;
}

export interface TraceResult {
  event: TraceHop;
  correlation_id: string;
  trace: TraceHop[];
  hop_count: number;
}

export interface PlatformHealth {
  events_last_5m: number;
  events_per_sec_estimate: number;
  services_healthy: number;
  services_total: number;
  kafka_topics: number;
}

export interface OperationsPulse {
  active_journeys: number;
  events_last_minute: number;
  agent_actions_5m: number;
  pending_escalations: number;
  compliance_blocks_1h: number;
  stage_transitions_1h: number;
}

export interface LiveJourney {
  customer_id: string;
  first_name: string | null;
  last_name: string | null;
  risk_score: number | null;
  account_id: string | null;
  delinquency_stage: string | null;
  days_past_due: number | null;
  current_balance: number | null;
  total_past_due: number | null;
  last_event_type: string | null;
  journey_stage_hint: string | null;
  last_activity: string;
}

export interface ChannelActivityRow {
  channel: string;
  direction: string;
  count_5m: number;
  count_1m: number;
  unique_customers: number;
}

export interface AgentAction {
  action_id: string;
  agent_type: string;
  customer_id: string;
  action_type: string;
  confidence: number | null;
  rationale: string | null;
  status: string;
  created_at: string;
  first_name: string | null;
  last_name: string | null;
}

export interface AgentSummary {
  agent_type: string;
  actions_24h: number;
  actions_5m: number;
  escalations_24h: number;
  avg_confidence: number | null;
}

export interface Escalation {
  escalation_id: string;
  customer_id: string;
  reason: string;
  urgency: string;
  specialist_type: string;
  status: string;
  sla_due_at: string;
  created_at: string;
  source_agent: string | null;
  first_name: string | null;
  last_name: string | null;
  seconds_until_sla: number;
}

export interface PortfolioKpis {
  cure: { at_risk: number; cured: number; cure_rate_pct: number | null };
  roll_matrix: { from_stage: string; to_stage: string; transitions: number }[];
  strategy_performance: {
    strategy_version: string;
    role: string;
    description: string;
    customers: number;
    actions_7d: number;
    escalations_7d: number;
    avg_confidence: number | null;
    cured_7d: number;
    cure_rate_7d_pct: number | null;
  }[];
  recovery_30d: { payments_30d: number; paying_customers: number };
  ptp_30d: { status: string; n: number }[];
  enforcement_24h: { allowed: number; blocked: number; block_rate_pct: number | null };
}

export interface ComplianceBlock {
  event_id: string;
  customer_id: string;
  occurred_at: string;
  action_blocked: string | null;
  rule_name: string | null;
  check_type: string | null;
  reason: string | null;
  payload: Record<string, unknown>;
}

export interface StoryNarrative {
  narrative: string | null;
  fallback?: string;
  model?: string | null;
  tokens?: { input: number; output: number };
  note?: string;
  error?: string;
}

export interface EnrichedEvent {
  event_id: string;
  customer_id: string;
  event_type: string;
  event_category: string;
  channel: string | null;
  direction: string | null;
  intent: string | null;
  payload: Record<string, unknown>;
  source_service: string;
  correlation_id: string | null;
  workflow_id: string | null;
  occurred_at: string;
  received_at: string;
  linked_actions: AgentAction[];
}

export interface DigestHighlight {
  dimension: 'compliance' | 'risk' | 'operations' | 'ai' | 'profile' | string;
  severity: 'low' | 'medium' | 'high' | 'critical';
  text: string;
}

export interface ActivityDigest {
  window: string;
  as_of: string;
  summary: string | null;
  fallback?: string;
  highlights: DigestHighlight[];
  context_size: {
    channel_buckets: number;
    stage_transitions: number;
    agent_actions: number;
    strategy_decisions: number;
    compliance_evaluations: number;
    escalations: number;
    ptps: number;
  };
  model?: string | null;
  tokens?: { input: number; output: number };
  note?: string;
  error?: string;
}

export interface S3Object {
  key: string;
  size: number;
  last_modified: string;
}

export interface LakehouseTier {
  bucket: string | null;
  region?: string;
  object_count: number;
  total_bytes: number;
  per_topic?: Record<string, { objects: number; bytes: number }>;
  error?: string;
}

export interface LakehouseTopology {
  tiers: {
    bronze: LakehouseTier;
    silver: LakehouseTier;
    gold: LakehouseTier;
  };
  timestamp: number;
}

export interface SilverPartition {
  topic: string;
  date: string;
  key: string;
  size: number;
  last_modified: string;
  rows_hint: number;
}

export interface GoldMart {
  mart: string;
  row_count: number;
  size_bytes: number;
  objects: number;
  sample: Record<string, unknown>[];
}

export interface SavedQuery {
  id: string;
  label: string;
  sql: string;
}

export interface QueryResult {
  rows: Record<string, unknown>[];
  columns: string[];
  elapsed_ms: number;
}

export interface LineageSuggestion {
  event_id: string;
  customer_id: string;
  event_type: string;
  event_category: string;
  occurred_at: string;
  correlation_id: string | null;
  linked_agent_actions: number;
}

export interface LineageTierKafka {
  topic: string;
  key: string;
  key_purpose: string;
  topic_partitions: number;
  retention_hours: number;
}

export interface LineageTierPostgres {
  database: string;
  table: string;
  primary_key: string;
  row: Record<string, unknown>;
  audit_status: string;
  audit_note: string;
}

export interface LineageTierRedis {
  channels: string[];
  purpose: string;
  ttl: string;
}

export interface LineageTierBronze {
  bucket: string;
  partition: string;
  found: boolean;
  key?: string;
  object_size_bytes?: number;
  events_in_file?: number;
  line_number?: number;
  raw_record?: Record<string, unknown>;
  ingested_at?: string;
  compression?: string;
  format?: string;
}

export interface LineageTierSilver {
  bucket: string;
  partition_pattern: string;
  found: boolean;
  row?: Record<string, unknown>;
  row_format?: string;
  schema_note?: string;
  error?: string;
}

export interface LineageGoldContribution {
  mart: string;
  columns: string[];
  note: string;
}

export interface LineageTierGold {
  bucket: string;
  contributions: LineageGoldContribution[];
  note: string;
}

export interface EventLineage {
  event_id: string;
  correlation_id: string | null;
  customer_id: string;
  topic: string;
  occurred_at: string;
  tiers: {
    kafka: LineageTierKafka;
    postgres: LineageTierPostgres;
    redis: LineageTierRedis;
    bronze: LineageTierBronze;
    silver: LineageTierSilver;
    gold: LineageTierGold;
  };
  downstream: {
    correlation_id: string | null;
    agent_actions: Record<string, unknown>[];
    related_events: Record<string, unknown>[];
    escalations: Record<string, unknown>[];
  };
}

export interface StrategyDecisionAudit {
  audit_id: string;
  strategy_version: string;
  policy_name: string;
  input_context: Record<string, unknown>;
  decision: Record<string, unknown>;
  evaluated_at: string;
}
