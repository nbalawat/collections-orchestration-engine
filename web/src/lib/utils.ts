import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatCurrency(value: number): string {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(value);
}

export function formatNumber(value: number): string {
  return new Intl.NumberFormat('en-US').format(Math.round(value));
}

export function formatDate(value: string): string {
  if (!value) return '-';
  return new Date(value).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

export function formatTime(value: string): string {
  if (!value) return '-';
  return new Date(value).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

export function formatDateTime(value: string): string {
  if (!value) return '-';
  return `${formatDate(value)} ${formatTime(value)}`;
}

export function stageBadgeColor(stage: string): string {
  const colors: Record<string, string> = {
    PRE_DELINQUENT: 'badge-blue',
    EARLY: 'badge-yellow',
    MID: 'badge-yellow',
    LATE: 'badge-red',
    SEVERE: 'badge-red',
    CURRENT: 'badge-green',
    CURED: 'badge-green',
    IDLE: 'badge-gray',
    DUNNING: 'badge-blue',
    PTP_ACTIVE: 'badge-green',
    PTP_BROKEN: 'badge-red',
    HARDSHIP_REVIEW: 'badge-purple',
    SUSPENDED: 'badge-red',
    CHARGED_OFF: 'badge-red',
  };
  return colors[stage] || 'badge-gray';
}

export function channelIcon(channel: string): string {
  const icons: Record<string, string> = {
    sms: '💬',
    email: '📧',
    voice: '📞',
    dialer: '📱',
    digital: '🖥️',
    system: '⚙️',
  };
  return icons[channel] || '📋';
}

const STAGE_LABELS: Record<string, string> = {
  IDLE: 'Idle',
  CURRENT: 'Current',
  PRE_DELINQUENT: 'Pre-delinquent',
  DUNNING: 'Dunning',
  EARLY: 'Early collections',
  MID: 'Mid collections',
  LATE: 'Late collections',
  SEVERE: 'Severe delinquency',
  HARDSHIP_REVIEW: 'Hardship review',
  PTP_ACTIVE: 'Promise to pay active',
  PTP_BROKEN: 'Broken promise to pay',
  SUSPENDED: 'Suspended',
  CHARGED_OFF: 'Charged off',
  CURED: 'Cured',
};

function friendlyStage(stage: string): string {
  return STAGE_LABELS[stage] || stage.toLowerCase().replace(/_/g, ' ');
}

function friendlyAction(action: string): string {
  const map: Record<string, string> = {
    ptp_capture: 'recording a promise-to-pay',
    payment_reminder_with_link: 'sending a payment reminder',
    send_dunning_notice: 'sending a dunning notice',
    send_settlement_offer: 'sending a settlement offer',
    escalate_to_supervisor: 'escalating to a supervisor',
    schedule_callback: 'scheduling a callback',
    send_hardship_options: 'sending hardship options',
  };
  return map[action] || action.replace(/_/g, ' ');
}

export function humanEventLabel(eventType: string, payload?: Record<string, unknown>): string {
  // Channel events — interactions
  const channelLabels: Record<string, string> = {
    sms_sent: 'Sent SMS to customer',
    sms_received: 'Received SMS from customer',
    sms_delivered: 'SMS delivered to customer',
    email_sent: 'Sent email to customer',
    email_delivered: 'Email delivered to customer',
    email_opened: 'Customer opened email',
    email_bounced: 'Email bounced back undelivered',
    call_connected_rpc: 'Connected voice call with customer',
    call_initiated: 'Initiated outbound call',
    call_completed: 'Voice call completed',
    call_outcome_logged: 'Logged call outcome',
    payment_received: 'Payment received from customer',
    payment_posted: 'Payment posted to account',
    payment_failed: 'Payment attempt failed',
    dialer_campaign_loaded: 'Loaded dialer campaign',
    dialer_call_attempted: 'Auto-dialer attempted call',
    ptp_created: 'Customer made a promise to pay',
    ptp_broken: 'Customer broke their promise to pay',
    ptp_fulfilled: 'Customer fulfilled their promise to pay',
    hardship_detected: 'Financial hardship detected',
    escalation_triggered: 'Case escalated for review',
    arrangement_applied: 'Payment arrangement applied to account',
  };
  if (channelLabels[eventType]) return channelLabels[eventType];

  // Strategy / decision events
  if (eventType === 'strategy_evaluation') {
    return 'Evaluated next-best-action strategy';
  }

  // Compliance events
  if (eventType.startsWith('blocked:')) {
    const action = eventType.slice(8);
    return `Compliance blocked ${friendlyAction(action)}`;
  }
  if (eventType.startsWith('compliance:')) {
    const ct = eventType.slice(11);
    const passed = payload?.passed;
    if (passed === false) return `Compliance check failed: ${ct.replace(/_/g, ' ')}`;
    if (passed === true) return `Compliance check passed: ${ct.replace(/_/g, ' ')}`;
    return `Ran compliance check: ${ct.replace(/_/g, ' ')}`;
  }
  if (eventType === 'compliance_check') return 'Ran compliance check';

  // Lifecycle / stage transitions
  if (eventType.startsWith('stage_change:')) {
    const parts = eventType.slice(13);
    if (parts.includes('->')) {
      const [from, to] = parts.split('->');
      return `Moved from ${friendlyStage(from)} to ${friendlyStage(to)}`;
    }
    return `Entered ${friendlyStage(parts)} stage`;
  }
  if (eventType === 'journey_stage_change') return 'Journey stage changed';

  // AI events
  if (eventType.startsWith('ai_reasoning:')) {
    const agent = eventType.slice(13);
    const agentLabels: Record<string, string> = {
      risk_assessor: 'AI assessed customer risk profile',
      treatment_optimizer: 'AI optimized treatment strategy',
      conversation_analyzer: 'AI analyzed customer conversation',
      compliance_reviewer: 'AI reviewed compliance requirements',
      outcome_predictor: 'AI predicted likely outcome',
    };
    return agentLabels[agent] || `AI agent (${agent.replace(/_/g, ' ')}) analyzed case`;
  }
  if (eventType === 'ai_reasoning_trace') return 'AI agent analyzed case';

  // Action events
  if (eventType === 'action_dispatched') return 'Dispatched collection action';

  // Fallback — title-case the event type
  return eventType
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
    .replace(/Rpc$/, '')
    .trim();
}
