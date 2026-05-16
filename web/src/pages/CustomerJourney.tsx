import { useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { Customer360, Event, Payment } from '@/lib/api'
import {
  formatCurrency,
  formatNumber,
  formatDate,
  formatDateTime,
  formatTime,
  channelIcon,
  stageBadgeColor,
  humanEventLabel,
} from '@/lib/utils'
import { useWebSocket } from '@/hooks/useWebSocket'
import {
  ArrowLeft,
  Phone,
  MessageSquare,
  Mail,
  Monitor,
  Bot,
  Brain,
  Shield,
  AlertTriangle,
  CheckCircle,
  Clock,
  DollarSign,
  CreditCard,
  User,
  Building,
  Calendar,
  MapPin,
  ChevronDown,
  ChevronRight,
  Zap,
  FileText,
  TrendingUp,
  ExternalLink,
  AlertCircle,
  ArrowRight,
  Activity,
} from 'lucide-react'

function eventCategoryIcon(event_type: string, category: string): string {
  if (event_type.startsWith('blocked:') || event_type.startsWith('compliance:') || category === 'compliance') return '🛡'
  if (event_type.startsWith('stage_change:') || category === 'lifecycle') return '🔄'
  if (event_type === 'strategy_evaluation' || category === 'decision') return '⚡'
  if (event_type.startsWith('ai_reasoning:') || category === 'ai_reasoning') return '🧠'
  if (category === 'action') return '🎯'
  return ''
}

function channelDotColor(channel: string): string {
  const colors: Record<string, string> = {
    sms: 'bg-blue-500',
    email: 'bg-purple-500',
    voice: 'bg-green-500',
    dialer: 'bg-amber-500',
    digital: 'bg-cyan-500',
    system: 'bg-slate-400',
  }
  return colors[channel] ?? 'bg-slate-400'
}

function directionLabel(direction: string): string {
  if (direction === 'inbound') return 'Inbound'
  if (direction === 'outbound') return 'Outbound'
  return 'System'
}

function riskColor(score: number): string {
  if (score < 40) return 'bg-green-500'
  if (score <= 70) return 'bg-amber-500'
  return 'bg-red-500'
}

function groupEventsByDate(events: Event[]): Map<string, Event[]> {
  const groups = new Map<string, Event[]>()
  for (const event of events) {
    const dateKey = formatDate(event.occurred_at)
    const existing = groups.get(dateKey)
    if (existing) {
      existing.push(event)
    } else {
      groups.set(dateKey, [event])
    }
  }
  return groups
}

const STAGE_ORDER = [
  'CURRENT',
  'PRE_DELINQUENT',
  'EARLY',
  'MID',
  'LATE',
  'SEVERE',
  'CHARGED_OFF',
]

interface ProfileHeroProps {
  profile: Record<string, unknown>
  accounts: Record<string, unknown>[]
  flags: Record<string, unknown>[]
  ptps: Record<string, unknown>[]
}

function ProfileHero({ profile, accounts, flags }: ProfileHeroProps) {
  const firstName = String(profile.first_name ?? '')
  const lastName = String(profile.last_name ?? '')
  const initials = (firstName.charAt(0) + lastName.charAt(0)).toUpperCase()
  const riskScore = Number(profile.risk_score ?? 0)
  const behavioralScore = Number(profile.behavioral_score ?? 0)
  const acct = accounts[0] as Record<string, unknown> | undefined

  return (
    <div className="card animate-fade-in">
      <div className="flex flex-col lg:flex-row gap-6">
        <div className="flex items-center gap-4 min-w-0">
          <div className="w-16 h-16 rounded-full bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center text-white text-xl font-bold shrink-0">
            {initials}
          </div>
          <div className="min-w-0">
            <h1 className="text-2xl font-bold text-slate-900 truncate">
              {firstName} {lastName}
            </h1>
            <p className="text-sm font-mono text-slate-500">{String(profile.customer_id ?? '')}</p>
            {profile.segment && (
              <span className={`badge ${stageBadgeColor(String(profile.segment))} mt-1`}>
                {String(profile.segment)}
              </span>
            )}
          </div>
        </div>

        <div className="flex-1 grid grid-cols-2 sm:grid-cols-3 gap-4 text-sm">
          <div>
            <p className="text-slate-500 mb-1">Risk Score</p>
            <p className="font-semibold text-slate-800 text-lg">{riskScore}</p>
            <div className="risk-gauge mt-1">
              <div
                className={`risk-gauge-fill ${riskColor(riskScore)}`}
                style={{ width: `${Math.min(riskScore, 100)}%` }}
              />
            </div>
          </div>
          <div>
            <p className="text-slate-500 mb-1">Behavioral Score</p>
            <p className="font-semibold text-slate-800 text-lg">{behavioralScore}</p>
            <div className="risk-gauge mt-1">
              <div
                className={`risk-gauge-fill ${riskColor(100 - behavioralScore)}`}
                style={{ width: `${Math.min(behavioralScore, 100)}%` }}
              />
            </div>
          </div>
          {acct && (
            <>
              <div>
                <p className="text-slate-500 mb-1">Days Past Due</p>
                <p className="font-semibold text-slate-800 text-lg">
                  {formatNumber(Number(acct.days_past_due ?? 0))}
                </p>
              </div>
              <div>
                <p className="text-slate-500 mb-1">Current Balance</p>
                <p className="font-semibold text-slate-800 text-lg">
                  {formatCurrency(Number(acct.current_balance ?? 0))}
                </p>
              </div>
              <div>
                <p className="text-slate-500 mb-1">Total Past Due</p>
                <p className="font-semibold text-slate-800 text-lg">
                  {formatCurrency(Number(acct.total_past_due ?? 0))}
                </p>
              </div>
              <div>
                <p className="text-slate-500 mb-1">Delinquency Stage</p>
                <span className={`badge ${stageBadgeColor(String(acct.delinquency_stage ?? 'CURRENT'))}`}>
                  {String(acct.delinquency_stage ?? 'CURRENT')}
                </span>
              </div>
            </>
          )}
        </div>

        <div className="text-sm space-y-2 text-slate-600 shrink-0 lg:w-60">
          <div className="flex items-center gap-2">
            <Mail size={14} className="text-slate-400" />
            <span className="truncate">{String(profile.email ?? '-')}</span>
          </div>
          <div className="flex items-center gap-2">
            <Phone size={14} className="text-slate-400" />
            <span>{String(profile.phone_primary ?? '-')}</span>
          </div>
          <div className="flex items-center gap-2">
            <MessageSquare size={14} className="text-slate-400" />
            <span>Preferred: {String(profile.preferred_channel ?? '-')}</span>
          </div>
          <div className="flex items-center gap-2">
            <Building size={14} className="text-slate-400" />
            <span>{String(profile.employer ?? '-')}</span>
          </div>
          <div className="flex items-center gap-2">
            <DollarSign size={14} className="text-slate-400" />
            <span>Income: {profile.annual_income ? formatCurrency(Number(profile.annual_income)) : '-'}</span>
          </div>
          <div className="flex items-center gap-2">
            <Calendar size={14} className="text-slate-400" />
            <span>Since: {profile.relationship_start ? formatDate(String(profile.relationship_start)) : '-'}</span>
          </div>
          <div className="flex items-center gap-2">
            <TrendingUp size={14} className="text-slate-400" />
            <span>Value: {profile.relationship_value ? formatCurrency(Number(profile.relationship_value)) : '-'}</span>
          </div>
          <div className="flex items-center gap-2">
            <MapPin size={14} className="text-slate-400" />
            <span>
              {profile.address_city ? `${String(profile.address_city)}, ${String(profile.address_state ?? '')}` : '-'}
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}

interface TimelineEventProps {
  event: Event
  isLive: boolean
}

function TimelineEvent({ event, isLive }: TimelineEventProps) {
  const [expanded, setExpanded] = useState(false)
  const payloadEntries = Object.entries(event.payload ?? {})

  return (
    <div className={`relative pl-8 pb-6 animate-fade-in ${isLive ? 'ring-1 ring-blue-300 rounded-lg bg-blue-50/30 p-3 pl-8' : ''}`}>
      <div className={`absolute left-0 top-1 w-3.5 h-3.5 rounded-full border-2 border-white ${channelDotColor(event.channel)} shadow-sm`} />

      <div className="flex items-center gap-2 flex-wrap">
        {isLive && <span className="badge badge-blue text-xs">Live</span>}
        {event.channel ? (
          <span className="text-sm font-medium text-slate-700">
            {channelIcon(event.channel)} {directionLabel(event.direction)}
          </span>
        ) : (
          <span className="text-sm">{eventCategoryIcon(event.event_type, event.event_category)}</span>
        )}
        <span className="text-sm font-semibold text-slate-900">{humanEventLabel(event.event_type, event.payload)}</span>
        <span className="text-xs text-slate-400 ml-auto whitespace-nowrap">{formatDateTime(event.occurred_at)}</span>
      </div>

      <div className="flex items-center gap-2 mt-1 flex-wrap">
        {event.intent && <span className="badge badge-purple text-xs">{event.intent}</span>}
        <span className="badge badge-gray text-xs">{event.source_service}</span>
      </div>

      {payloadEntries.length > 0 && (
        <div className="mt-2">
          <button
            onClick={() => setExpanded(!expanded)}
            className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-700 transition-colors"
          >
            {expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
            Details
          </button>
          {expanded && (
            <div className="mt-1.5 p-2.5 bg-slate-50 rounded-md border border-slate-100 text-xs space-y-1 animate-slide-in">
              {payloadEntries.map(([key, val]) => (
                <div key={key} className="flex gap-2">
                  <span className="text-slate-500 font-medium shrink-0">{key}:</span>
                  <span className="text-slate-700 break-all">
                    {typeof val === 'object' ? JSON.stringify(val, null, 2) : String(val)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

interface JourneyStatePanelProps {
  state: {
    stage: string
    dpd: number
    balance: number
    suspended: boolean
    compliance_flags: string[]
    actions_count: number
    events_count: number
    [key: string]: unknown
  } | null
}

function JourneyStatePanel({ state }: JourneyStatePanelProps) {
  if (!state) {
    return (
      <div className="card animate-slide-in">
        <h3 className="font-semibold text-slate-800 mb-3 flex items-center gap-2">
          <Activity size={16} className="text-blue-500" />
          Journey State
        </h3>
        <p className="text-sm text-slate-400">No active workflow</p>
      </div>
    )
  }

  return (
    <div className="card animate-slide-in">
      <h3 className="font-semibold text-slate-800 mb-3 flex items-center gap-2">
        <Activity size={16} className="text-blue-500" />
        Journey State
      </h3>
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <span className="text-sm text-slate-500">Current Stage</span>
          <span className={`badge ${stageBadgeColor(state.stage)}`}>{state.stage}</span>
        </div>

        <div className="space-y-1">
          {STAGE_ORDER.map((s) => (
            <div key={s} className="flex items-center gap-2">
              <div
                className={`w-2 h-2 rounded-full ${
                  s === state.stage ? 'bg-blue-500 ring-2 ring-blue-200' : 'bg-slate-200'
                }`}
              />
              <span
                className={`text-xs ${
                  s === state.stage ? 'font-semibold text-blue-700' : 'text-slate-400'
                }`}
              >
                {s}
              </span>
            </div>
          ))}
        </div>

        {state.suspended && (
          <div className="flex items-center gap-2 text-red-600 text-sm">
            <AlertTriangle size={14} />
            Workflow Suspended
          </div>
        )}

        <div className="grid grid-cols-2 gap-2 text-sm">
          <div>
            <p className="text-slate-500">Actions</p>
            <p className="font-semibold text-slate-800">{formatNumber(state.actions_count)}</p>
          </div>
          <div>
            <p className="text-slate-500">Events</p>
            <p className="font-semibold text-slate-800">{formatNumber(state.events_count)}</p>
          </div>
        </div>
      </div>
    </div>
  )
}

interface CompliancePanelProps {
  flags: Record<string, unknown>[]
}

function CompliancePanel({ flags }: CompliancePanelProps) {
  return (
    <div className="card animate-slide-in">
      <h3 className="font-semibold text-slate-800 mb-3 flex items-center gap-2">
        <Shield size={16} className="text-blue-500" />
        Compliance Flags
      </h3>
      {flags.length === 0 ? (
        <div className="flex items-center gap-2 text-green-600 text-sm">
          <CheckCircle size={14} />
          No compliance flags
        </div>
      ) : (
        <div className="space-y-3">
          {flags.map((flag, i) => (
            <div key={String(flag.flag_id ?? i)} className="p-2.5 bg-slate-50 rounded-md border border-slate-100">
              <div className="flex items-center gap-2 mb-1">
                <Shield size={12} className="text-slate-400" />
                <span
                  className={`badge text-xs ${
                    String(flag.status) === 'active' ? 'badge-red' : 'badge-gray'
                  }`}
                >
                  {String(flag.flag_type ?? '')}
                </span>
              </div>
              <p className="text-xs text-slate-600">{String(flag.reason ?? '')}</p>
              <p className="text-xs text-slate-400 mt-1">
                Effective: {flag.effective_date ? formatDate(String(flag.effective_date)) : '-'}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

interface PtpPanelProps {
  ptps: Record<string, unknown>[]
}

function PtpPanel({ ptps }: PtpPanelProps) {
  return (
    <div className="card animate-slide-in">
      <h3 className="font-semibold text-slate-800 mb-3 flex items-center gap-2">
        <CreditCard size={16} className="text-blue-500" />
        Active Promises to Pay
      </h3>
      {ptps.length === 0 ? (
        <p className="text-sm text-slate-400">No active promises</p>
      ) : (
        <div className="space-y-3">
          {ptps.map((ptp, i) => (
            <div key={String(ptp.ptp_id ?? i)} className="p-2.5 bg-slate-50 rounded-md border border-slate-100">
              <div className="flex items-center justify-between mb-1">
                <span className="font-semibold text-sm text-slate-800">
                  {formatCurrency(Number(ptp.promised_amount ?? 0))}
                </span>
                <span
                  className={`badge text-xs ${
                    String(ptp.status) === 'active'
                      ? 'badge-green'
                      : String(ptp.status) === 'broken'
                        ? 'badge-red'
                        : 'badge-gray'
                  }`}
                >
                  {String(ptp.status ?? '')}
                </span>
              </div>
              <p className="text-xs text-slate-500">
                Due: {ptp.promised_date ? formatDate(String(ptp.promised_date)) : '-'}
              </p>
              <p className="text-xs text-slate-500">Channel: {String(ptp.channel ?? '-')}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

interface PaymentPanelProps {
  payments: Payment[]
}

function PaymentPanel({ payments }: PaymentPanelProps) {
  const recent = payments.slice(0, 5)

  return (
    <div className="card animate-slide-in">
      <h3 className="font-semibold text-slate-800 mb-3 flex items-center gap-2">
        <DollarSign size={16} className="text-blue-500" />
        Payment History
      </h3>
      {recent.length === 0 ? (
        <p className="text-sm text-slate-400">No payment history</p>
      ) : (
        <div className="space-y-2">
          {recent.map((p) => (
            <div
              key={p.payment_id}
              className="flex items-center justify-between p-2 bg-slate-50 rounded-md border border-slate-100 text-sm"
            >
              <div>
                <p className="font-semibold text-slate-800">{formatCurrency(p.amount)}</p>
                <p className="text-xs text-slate-400">{formatDate(p.payment_date)}</p>
              </div>
              <div className="text-right">
                <p className="text-xs text-slate-500">{p.payment_method}</p>
                <span
                  className={`badge text-xs ${
                    p.status === 'completed' ? 'badge-green' : p.status === 'failed' ? 'badge-red' : 'badge-gray'
                  }`}
                >
                  {p.status}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

interface AITracePanelProps {
  traces: Event[]
}

function AITracePanel({ traces }: AITracePanelProps) {
  const [expandedTrace, setExpandedTrace] = useState<string | null>(null)

  return (
    <div className="card animate-slide-in">
      <h3 className="font-semibold text-slate-800 mb-3 flex items-center gap-2">
        <Brain size={16} className="text-purple-500" />
        AI Agent Activity
      </h3>
      {traces.length === 0 ? (
        <p className="text-sm text-slate-400">No AI activity recorded</p>
      ) : (
        <div className="space-y-3">
          {traces.map((trace) => {
            const payload = trace.payload ?? {}
            const confidence = Number(payload.confidence ?? 0)
            const isExpanded = expandedTrace === trace.event_id
            const steps = (payload.reasoning_steps as Array<Record<string, unknown>>) ?? []

            return (
              <div key={trace.event_id} className="p-2.5 bg-slate-50 rounded-md border border-slate-100">
                <div className="flex items-center gap-2 mb-1 flex-wrap">
                  <Bot size={12} className="text-purple-500" />
                  <span className="text-xs font-semibold text-slate-700">
                    {String(payload.agent_type ?? trace.source_service)}
                  </span>
                  <span
                    className={`badge text-xs ${
                      confidence > 0.7 ? 'badge-green' : confidence >= 0.4 ? 'badge-yellow' : 'badge-red'
                    }`}
                  >
                    {(confidence * 100).toFixed(0)}% confidence
                  </span>
                </div>
                <p className="text-xs text-slate-600 mb-1">{String(payload.action_taken ?? '')}</p>
                <div className="flex items-center gap-3 text-xs text-slate-400">
                  {payload.tokens_used != null && <span>{formatNumber(Number(payload.tokens_used))} tokens</span>}
                  {payload.latency_ms != null && <span>{Number(payload.latency_ms)}ms</span>}
                  <span>{formatTime(trace.occurred_at)}</span>
                </div>
                {steps.length > 0 && (
                  <div className="mt-1.5">
                    <button
                      onClick={() => setExpandedTrace(isExpanded ? null : trace.event_id)}
                      className="flex items-center gap-1 text-xs text-purple-500 hover:text-purple-700 transition-colors"
                    >
                      {isExpanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                      Reasoning Steps ({steps.length})
                    </button>
                    {isExpanded && (
                      <div className="mt-1.5 space-y-1 animate-slide-in">
                        {steps.map((step, idx) => (
                          <div key={idx} className="flex gap-2 text-xs p-1.5 bg-white rounded border border-slate-100">
                            <span className="text-purple-500 font-medium shrink-0">{String(step.step ?? idx + 1)}.</span>
                            <span className="text-slate-600">{String(step.result ?? '')}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

export default function CustomerJourney() {
  const { id } = useParams<{ id: string }>()
  const customerId = id ?? ''

  const { data: customer, isLoading, isError } = useQuery({
    queryKey: ['customer360', customerId],
    queryFn: () => api.getCustomer360(customerId),
    enabled: !!customerId,
  })

  const { data: timelineData } = useQuery({
    queryKey: ['eventTimeline', customerId],
    queryFn: () => api.eventTimeline(customerId),
    enabled: !!customerId,
  })

  const { data: paymentsData } = useQuery({
    queryKey: ['customerPayments', customerId],
    queryFn: () => api.getCustomerPayments(customerId),
    enabled: !!customerId,
  })

  const { data: journeyState } = useQuery({
    queryKey: ['journeyState', customerId],
    queryFn: () => api.getJourneyState(customerId),
    enabled: !!customerId,
    retry: false,
  })

  const { data: tracesData } = useQuery({
    queryKey: ['reasoningTraces'],
    queryFn: () => api.getReasoningTraces(100),
    enabled: !!customerId,
  })

  const { events: liveEvents } = useWebSocket(`/ws/events/${customerId}`, 100)

  const profile = customer?.profile as Record<string, unknown> | undefined
  const accounts = customer?.accounts ?? []
  const flags = customer?.compliance_flags ?? []
  const ptps = customer?.active_ptps ?? []
  const payments = paymentsData?.payments ?? []

  const customerTraces = (tracesData?.traces ?? []).filter(
    (t) => t.customer_id === customerId
  )

  const apiEvents = timelineData?.timeline ?? []
  const liveEventIds = new Set(liveEvents.map((e) => (e as unknown as Event).event_id).filter(Boolean))
  const dedupedApiEvents = apiEvents.filter((e) => !liveEventIds.has(e.event_id))
  const allEvents = [
    ...(liveEvents as unknown as Event[]),
    ...dedupedApiEvents,
  ].sort((a, b) => new Date(b.occurred_at).getTime() - new Date(a.occurred_at).getTime())
  const liveEventIdSet = new Set(liveEvents.map((e) => (e as unknown as Event).event_id).filter(Boolean))
  const groupedEvents = groupEventsByDate(allEvents)

  if (isLoading) {
    return (
      <div className="flex-1 overflow-y-auto overflow-x-hidden min-w-0 p-6 space-y-6">
        <Link to="/" className="inline-flex items-center gap-2 text-sm text-slate-500 hover:text-slate-700 transition-colors">
          <ArrowLeft size={16} />
          Back to Command Center
        </Link>
        <div className="card p-12 text-center">
          <div className="animate-pulse space-y-4">
            <div className="h-16 w-16 rounded-full bg-slate-200 mx-auto" />
            <div className="h-6 w-48 bg-slate-200 rounded mx-auto" />
            <div className="h-4 w-32 bg-slate-200 rounded mx-auto" />
          </div>
        </div>
      </div>
    )
  }

  if (isError || !profile) {
    return (
      <div className="flex-1 overflow-y-auto overflow-x-hidden min-w-0 p-6 space-y-6">
        <Link to="/" className="inline-flex items-center gap-2 text-sm text-slate-500 hover:text-slate-700 transition-colors">
          <ArrowLeft size={16} />
          Back to Command Center
        </Link>
        <div className="card p-12 text-center">
          <AlertCircle size={48} className="text-red-400 mx-auto mb-4" />
          <h2 className="text-xl font-semibold text-slate-800 mb-2">Customer Not Found</h2>
          <p className="text-sm text-slate-500">
            Unable to load data for customer {customerId}. The customer may not exist or the service is unavailable.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto overflow-x-hidden min-w-0 p-6 space-y-6">
      <Link to="/" className="inline-flex items-center gap-2 text-sm text-slate-500 hover:text-slate-700 transition-colors">
        <ArrowLeft size={16} />
        Back to Command Center
      </Link>

      <ProfileHero profile={profile} accounts={accounts} flags={flags} ptps={ptps} />

      <div className="flex gap-6 items-start">
        <div className="w-[65%] min-w-0">
          <div className="card">
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-semibold text-slate-800 flex items-center gap-2">
                <Clock size={16} className="text-blue-500" />
                Cross-Channel Timeline
              </h2>
              <span className="badge badge-gray text-xs">{allEvents.length} events</span>
            </div>

            <div className="relative scrollbar-thin" style={{ maxHeight: '70vh', overflowY: 'auto' }}>
              <div className="timeline-line absolute left-[6px] top-0 bottom-0 w-0.5 bg-slate-200" />

              {Array.from(groupedEvents.entries()).map(([dateLabel, events]) => (
                <div key={dateLabel}>
                  <div className="relative pl-8 py-2 mb-1">
                    <div className="absolute left-0 top-3 w-3.5 h-0.5 bg-slate-300" />
                    <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">{dateLabel}</p>
                  </div>
                  {events.map((event) => (
                    <TimelineEvent
                      key={event.event_id}
                      event={event}
                      isLive={liveEventIdSet.has(event.event_id)}
                    />
                  ))}
                </div>
              ))}

              {allEvents.length === 0 && (
                <p className="text-sm text-slate-400 py-8 text-center">No events recorded yet</p>
              )}
            </div>
          </div>
        </div>

        <div className="w-[35%] space-y-4 min-w-0">
          <JourneyStatePanel state={journeyState ?? null} />
          <CompliancePanel flags={flags} />
          <PtpPanel ptps={ptps} />
          <PaymentPanel payments={payments} />
          <AITracePanel traces={customerTraces} />
        </div>
      </div>
    </div>
  )
}
