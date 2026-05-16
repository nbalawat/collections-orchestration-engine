import { useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { Markdown } from '@/components/Markdown'
import type {
  EnrichedEvent, StoryNarrative, StrategyDecisionAudit,
  AgentAction, Escalation, Customer360,
} from '@/lib/api'
import {
  formatCurrency, formatNumber, formatDateTime, formatTime,
  channelIcon, stageBadgeColor, humanEventLabel,
} from '@/lib/utils'
import {
  ArrowLeft, Brain, Shield, AlertTriangle, Activity, CheckCircle,
  ChevronDown, ChevronRight, Sparkles, Zap, Phone, FileText, Cpu, Clock,
} from 'lucide-react'

function Pulse({ label, value, sub, tone = 'default' }: {
  label: string; value: string | number; sub?: string;
  tone?: 'default' | 'good' | 'warn' | 'bad'
}) {
  const t = {
    default: 'border-slate-200',
    good: 'border-emerald-300 bg-emerald-50',
    warn: 'border-amber-300 bg-amber-50',
    bad: 'border-red-300 bg-red-50',
  }[tone]
  return (
    <div className={`border rounded-lg px-3 py-2 ${t}`}>
      <div className="text-[10px] uppercase tracking-wider text-slate-500">{label}</div>
      <div className="text-xl font-bold text-slate-800">{value}</div>
      {sub && <div className="text-[10px] text-slate-500 mt-0.5">{sub}</div>}
    </div>
  )
}

function NarrativeCard({ id }: { id: string }) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['story-narrative', id],
    queryFn: () => api.storyNarrative(id),
    staleTime: 60000,
  })

  return (
    <div className="bg-gradient-to-br from-blue-50 to-purple-50 border border-blue-200 rounded-xl p-5">
      <div className="flex items-center gap-2 mb-3">
        <Sparkles size={18} className="text-blue-600" />
        <h2 className="text-sm font-bold text-slate-800">The Story So Far</h2>
        {data?.model && (
          <span className="badge badge-blue text-[10px] ml-auto">{data.model}</span>
        )}
      </div>
      {isLoading && (
        <div className="space-y-2">
          <div className="h-3 bg-slate-200/60 rounded animate-pulse" />
          <div className="h-3 bg-slate-200/60 rounded animate-pulse w-5/6" />
          <div className="h-3 bg-slate-200/60 rounded animate-pulse w-4/6" />
        </div>
      )}
      {isError && <p className="text-sm text-red-600">Failed to load narrative.</p>}
      {data?.narrative && <Markdown variant="narrative">{data.narrative}</Markdown>}
      {!data?.narrative && data?.fallback && (
        <>
          <Markdown variant="narrative">{data.fallback}</Markdown>
          {data.note && <p className="text-[11px] text-slate-500 mt-2 italic">{data.note}</p>}
          {data.error && <p className="text-[11px] text-red-600 mt-2">Error: {data.error}</p>}
        </>
      )}
      {data?.tokens && (
        <div className="text-[10px] text-slate-400 mt-3 text-right">
          {data.tokens.input}+{data.tokens.output} tokens
        </div>
      )}
    </div>
  )
}

function EventCard({ event }: { event: EnrichedEvent }) {
  const [expanded, setExpanded] = useState(false)
  const linkedActions = event.linked_actions || []

  const cat = event.event_category
  const Icon = cat === 'compliance' ? Shield :
               cat === 'lifecycle' ? Activity :
               cat === 'decision' ? Zap :
               cat === 'ai_reasoning' ? Brain :
               cat === 'action' ? Cpu :
               null
  const iconColor = cat === 'compliance' ? 'text-red-500' :
                    cat === 'lifecycle' ? 'text-blue-500' :
                    cat === 'decision' ? 'text-amber-500' :
                    cat === 'ai_reasoning' ? 'text-purple-500' :
                    cat === 'action' ? 'text-emerald-500' :
                    'text-slate-400'

  return (
    <div className="relative pl-8 pb-4">
      <div className="absolute left-0 top-1 w-3.5 h-3.5 rounded-full border-2 border-white bg-slate-300 shadow-sm" />

      <div
        className="cursor-pointer hover:bg-slate-50 -ml-2 pl-2 py-1 rounded"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center gap-2 flex-wrap">
          {Icon ? (
            <Icon size={14} className={iconColor} />
          ) : event.channel ? (
            <span className="text-sm">{channelIcon(event.channel)}</span>
          ) : null}
          <span className="text-sm font-semibold text-slate-800">
            {humanEventLabel(event.event_type, event.payload)}
          </span>
          {event.intent && <span className="badge badge-purple text-[10px]">{event.intent}</span>}
          {linkedActions.length > 0 && (
            <span className="badge badge-blue text-[10px] flex items-center gap-1">
              <Brain size={10} /> {linkedActions.length} action{linkedActions.length > 1 ? 's' : ''}
            </span>
          )}
          <span className="text-[10px] text-slate-400 ml-auto whitespace-nowrap">{formatDateTime(event.occurred_at)}</span>
          {(linkedActions.length > 0 || Object.keys(event.payload || {}).length > 0) && (
            expanded ? <ChevronDown size={12} className="text-slate-400" /> : <ChevronRight size={12} className="text-slate-400" />
          )}
        </div>
        <div className="flex items-center gap-2 mt-1">
          <span className="text-[10px] text-slate-500 font-mono">{event.source_service}</span>
          {event.correlation_id && (
            <code className="text-[10px] text-slate-400">trace: {event.correlation_id.slice(0, 8)}…</code>
          )}
        </div>
      </div>

      {expanded && (
        <div className="mt-2 ml-4 space-y-2">
          {linkedActions.length > 0 && (
            <div className="bg-purple-50 border border-purple-200 rounded p-2.5">
              <div className="text-[10px] uppercase tracking-wider text-purple-700 mb-1.5">AI actions in this trace</div>
              {linkedActions.map((a) => (
                <div key={a.action_id} className="text-xs py-1 border-b last:border-b-0 border-purple-100">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-purple-900">{a.agent_type.replace(/_/g, ' ')}</span>
                    <span className="text-purple-700">→ {a.action_type.replace(/_/g, ' ')}</span>
                    <span className={`badge text-[10px] ml-auto ${
                      (a.confidence ?? 0) > 0.8 ? 'badge-green' :
                      (a.confidence ?? 0) > 0.5 ? 'badge-yellow' : 'badge-red'
                    }`}>{((a.confidence ?? 0) * 100).toFixed(0)}%</span>
                  </div>
                  {a.rationale && (
                    <div className="mt-1">
                      <Markdown variant="rationale">{a.rationale}</Markdown>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
          {event.payload && Object.keys(event.payload).length > 0 && (
            <details className="bg-slate-50 border border-slate-200 rounded p-2.5">
              <summary className="text-[10px] uppercase tracking-wider text-slate-600 cursor-pointer">Event payload</summary>
              <pre className="text-[10px] mt-1.5 overflow-auto max-h-64 text-slate-700">
                {JSON.stringify(event.payload, null, 2)}
              </pre>
            </details>
          )}
        </div>
      )}
    </div>
  )
}

function DecisionCard({ d }: { d: StrategyDecisionAudit }) {
  const [expanded, setExpanded] = useState(false)
  const opaInput = (d.input_context?.opa_input as Record<string, unknown>) || d.input_context || {}
  const decision = d.decision || {}
  const treatment = (decision.treatment as Record<string, unknown>) || {}
  const compliance = (decision.compliance as Record<string, unknown>) || {}
  const routing = (decision.routing as Record<string, unknown>) || {}

  return (
    <div className="border border-slate-200 rounded-lg p-3 bg-white">
      <div className="flex items-center gap-2 cursor-pointer" onClick={() => setExpanded(!expanded)}>
        <Zap size={14} className="text-amber-500" />
        <span className="text-sm font-semibold text-slate-800">Strategy evaluated</span>
        <span className="badge badge-gray text-[10px]">{d.strategy_version}</span>
        {treatment.action != null && (
          <span className="badge badge-blue text-[10px]">{String(treatment.action)}</span>
        )}
        {compliance.can_contact === false && (
          <span className="badge badge-red text-[10px]">suppressed</span>
        )}
        <span className="text-[10px] text-slate-400 ml-auto">{formatTime(d.evaluated_at)}</span>
        {expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
      </div>
      {expanded && (
        <div className="mt-3 grid grid-cols-2 gap-3 text-xs">
          <div>
            <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-1">OPA input</div>
            <pre className="bg-slate-50 p-2 rounded text-[10px] max-h-48 overflow-auto">
              {JSON.stringify(opaInput, null, 2)}
            </pre>
          </div>
          <div className="space-y-2">
            <div>
              <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-1">Treatment</div>
              <pre className="bg-amber-50 p-2 rounded text-[10px] max-h-24 overflow-auto">
                {JSON.stringify(treatment, null, 2)}
              </pre>
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-1">Routing</div>
              <pre className="bg-blue-50 p-2 rounded text-[10px] max-h-16 overflow-auto">
                {JSON.stringify(routing, null, 2)}
              </pre>
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-1">Compliance</div>
              <pre className="bg-emerald-50 p-2 rounded text-[10px] max-h-20 overflow-auto">
                {JSON.stringify(compliance, null, 2)}
              </pre>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function EscalationCard({ e }: { e: Escalation }) {
  const overdue = e.seconds_until_sla < 0
  return (
    <div className={`border rounded-lg p-3 ${
      overdue ? 'bg-red-50 border-red-300' :
      e.status === 'queued' ? 'bg-amber-50 border-amber-300' :
      'bg-emerald-50 border-emerald-300'
    }`}>
      <div className="flex items-center gap-2">
        <AlertTriangle size={14} className={
          overdue ? 'text-red-600' :
          e.status === 'queued' ? 'text-amber-600' : 'text-emerald-600'
        } />
        <span className="text-sm font-semibold text-slate-800">{e.urgency} escalation</span>
        <span className="badge badge-gray text-[10px]">{e.specialist_type}</span>
        <span className="badge text-[10px] ml-auto" style={{ background: '#e2e8f0' }}>{e.status}</span>
        <span className="text-[10px] text-slate-400">{formatTime(e.created_at)}</span>
      </div>
      <p className="text-xs text-slate-600 mt-1">{e.reason}</p>
      {e.status === 'queued' && (
        <p className="text-[10px] text-slate-500 mt-1">
          {overdue
            ? `SLA missed by ${Math.abs(e.seconds_until_sla)}s`
            : `SLA in ${Math.round(e.seconds_until_sla / 60)} min`}
        </p>
      )}
    </div>
  )
}

export default function CustomerStory() {
  const { id } = useParams<{ id: string }>()
  const customerId = id ?? ''

  const { data: customer } = useQuery({
    queryKey: ['customer360', customerId],
    queryFn: () => api.getCustomer360(customerId),
    enabled: !!customerId,
  })

  const { data: timeline } = useQuery({
    queryKey: ['story-timeline', customerId],
    queryFn: () => api.storyTimeline(customerId, 200),
    enabled: !!customerId,
    refetchInterval: 8000,
  })

  const { data: decisions } = useQuery({
    queryKey: ['story-decisions', customerId],
    queryFn: () => api.storyDecisions(customerId, 30),
    enabled: !!customerId,
    refetchInterval: 12000,
  })

  const { data: actions } = useQuery({
    queryKey: ['story-actions', customerId],
    queryFn: () => api.storyAgentActions(customerId, 30),
    enabled: !!customerId,
    refetchInterval: 10000,
  })

  const { data: escalations } = useQuery({
    queryKey: ['story-escalations', customerId],
    queryFn: () => api.storyEscalations(customerId),
    enabled: !!customerId,
    refetchInterval: 15000,
  })

  if (!customer) {
    return (
      <div className="p-8 text-sm text-slate-500">Loading customer story…</div>
    )
  }

  const profile = customer.profile as Record<string, unknown>
  const accounts = customer.accounts || []
  const acct = (accounts[0] as Record<string, unknown>) || {}
  const flags = customer.compliance_flags || []
  const fullName = `${profile.first_name ?? ''} ${profile.last_name ?? ''}`.trim() || customerId

  const eventCount = timeline?.count ?? 0
  const decisionCount = decisions?.decisions?.length ?? 0
  const actionCount = actions?.actions?.length ?? 0
  const escalationCount = escalations?.escalations?.length ?? 0

  return (
    <div className="flex-1 overflow-y-auto p-6 space-y-6">
      <Link to="/" className="inline-flex items-center gap-2 text-sm text-slate-500 hover:text-slate-700">
        <ArrowLeft size={16} /> Operations Floor
      </Link>

      <div className="flex items-start gap-6">
        <div className="w-16 h-16 rounded-full bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center text-white text-xl font-bold shrink-0">
          {(profile.first_name as string || '?')[0]}{(profile.last_name as string || '?')[0]}
        </div>
        <div className="flex-1 min-w-0">
          <h1 className="text-2xl font-bold text-slate-900">{fullName}</h1>
          <div className="flex items-center gap-3 mt-1 text-sm text-slate-500">
            <code>{customerId}</code>
            {acct.delinquency_stage && (
              <span className={`badge ${stageBadgeColor(String(acct.delinquency_stage))}`}>
                {String(acct.delinquency_stage).replace(/_/g, ' ')}
              </span>
            )}
            {flags.map((f, i) => (
              <span key={i} className="badge badge-red text-xs">
                <Shield size={10} className="mr-1" />
                {(f as Record<string, unknown>).flag_type as string}
              </span>
            ))}
          </div>
        </div>
        <div className="grid grid-cols-3 gap-3 shrink-0">
          <Pulse
            label="DPD"
            value={String(acct.days_past_due ?? 0)}
            tone={Number(acct.days_past_due ?? 0) > 60 ? 'bad' : Number(acct.days_past_due ?? 0) > 30 ? 'warn' : 'default'}
          />
          <Pulse label="Balance" value={formatCurrency(Number(acct.current_balance ?? 0))} />
          <Pulse
            label="Past Due"
            value={formatCurrency(Number(acct.total_past_due ?? 0))}
            tone={Number(acct.total_past_due ?? 0) > 0 ? 'warn' : 'good'}
          />
        </div>
      </div>

      <NarrativeCard id={customerId} />

      <div className="grid grid-cols-4 gap-3">
        <Pulse label="Events" value={eventCount} sub="full history" />
        <Pulse label="Strategy evaluations" value={decisionCount} sub="OPA decisions" />
        <Pulse
          label="AI actions"
          value={actionCount}
          sub="agent receipts"
          tone={actionCount > 0 ? 'good' : 'default'}
        />
        <Pulse
          label="Escalations"
          value={escalationCount}
          tone={escalationCount > 0 ? 'warn' : 'default'}
        />
      </div>

      <div className="grid grid-cols-3 gap-6">
        <div className="col-span-2">
          <h2 className="text-sm font-bold text-slate-700 mb-3 flex items-center gap-2">
            <Activity size={16} /> Timeline · click any event for trace details
          </h2>
          <div className="relative pl-2">
            <div className="absolute left-[7px] top-0 bottom-0 w-px bg-slate-200" />
            {(timeline?.timeline ?? []).map((e) => (
              <EventCard key={e.event_id} event={e} />
            ))}
            {!timeline?.timeline?.length && (
              <p className="text-sm text-slate-400 ml-4 mt-4">No events yet.</p>
            )}
          </div>
        </div>

        <div className="space-y-6">
          <div>
            <h2 className="text-sm font-bold text-slate-700 mb-3 flex items-center gap-2">
              <Zap size={16} /> Strategy decisions
            </h2>
            <div className="space-y-2">
              {(decisions?.decisions ?? []).slice(0, 10).map((d) => (
                <DecisionCard key={d.audit_id} d={d} />
              ))}
              {!decisions?.decisions?.length && (
                <p className="text-sm text-slate-400">No strategy evaluations yet.</p>
              )}
            </div>
          </div>

          {(escalations?.escalations?.length ?? 0) > 0 && (
            <div>
              <h2 className="text-sm font-bold text-slate-700 mb-3 flex items-center gap-2">
                <AlertTriangle size={16} /> Escalations
              </h2>
              <div className="space-y-2">
                {(escalations?.escalations ?? []).map((e) => (
                  <EscalationCard key={e.escalation_id} e={e} />
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
