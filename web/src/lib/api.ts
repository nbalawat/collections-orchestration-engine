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
