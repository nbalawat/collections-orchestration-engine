import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api } from '@/lib/api'
import { useWebSocket } from '@/hooks/useWebSocket'
import {
  formatCurrency, formatNumber, formatTime, stageBadgeColor,
  channelIcon, humanEventLabel,
} from '@/lib/utils'
import {
  Activity, Radio, Brain, Shield, AlertTriangle, Users,
  ArrowRight, Zap, Phone, MessageSquare, Mail, Server,
  TrendingUp, ChevronRight, Clock,
} from 'lucide-react'

function PulseTile({ label, value, sub, icon, tone = 'default', live }: {
  label: string; value: string | number; sub?: string;
  icon: React.ReactNode; tone?: 'default' | 'good' | 'warn' | 'bad'; live?: boolean
}) {
  const toneClass = {
    default: 'bg-white border-slate-200',
    good: 'bg-emerald-50 border-emerald-300',
    warn: 'bg-amber-50 border-amber-300',
    bad: 'bg-red-50 border-red-300',
  }[tone]
  return (
    <div className={`border rounded-xl p-4 ${toneClass} relative`}>
      {live && (
        <span className="absolute top-3 right-3 w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
      )}
      <div className="flex items-center gap-2 text-[11px] uppercase tracking-wider text-slate-500">
        {icon}{label}
      </div>
      <div className="text-3xl font-bold text-slate-800 mt-1">{value}</div>
      {sub && <div className="text-xs text-slate-500 mt-1">{sub}</div>}
    </div>
  )
}

function ChannelTile({ row }: { row: { channel: string; direction: string; count_5m: number; count_1m: number; unique_customers: number } }) {
  const colors: Record<string, string> = {
    sms: 'from-blue-50 to-blue-100 border-blue-300',
    voice: 'from-emerald-50 to-emerald-100 border-emerald-300',
    email: 'from-purple-50 to-purple-100 border-purple-300',
    dialer: 'from-amber-50 to-amber-100 border-amber-300',
    digital: 'from-cyan-50 to-cyan-100 border-cyan-300',
    system: 'from-slate-50 to-slate-100 border-slate-300',
  }
  const color = colors[row.channel] || colors.system
  return (
    <div className={`bg-gradient-to-br ${color} border rounded-lg p-3`}>
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold text-slate-700 uppercase">{row.channel}</span>
        <span className="text-xs text-slate-500">{row.direction}</span>
      </div>
      <div className="text-2xl font-bold text-slate-800 mt-1">{row.count_5m}</div>
      <div className="text-[10px] text-slate-500 mt-0.5">
        last 5 min · {row.unique_customers} customers
      </div>
      <div className="mt-1.5 text-[10px] text-slate-600">
        <span className="font-medium">{row.count_1m}</span>/min current
      </div>
    </div>
  )
}

function JourneyRow({ j }: { j: import('@/lib/api').LiveJourney }) {
  const name = j.first_name && j.last_name ? `${j.first_name} ${j.last_name}` : j.customer_id
  const stage = j.journey_stage_hint || j.delinquency_stage || 'CURRENT'
  return (
    <Link to={`/customer/${j.customer_id}`} className="block hover:bg-slate-50 border-b border-slate-100 px-3 py-2">
      <div className="flex items-center gap-3">
        <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse shrink-0" />
        <div className="min-w-0 flex-1">
          <div className="text-sm font-medium text-slate-800 truncate">{name}</div>
          <div className="text-[10px] text-slate-400 font-mono truncate">{j.customer_id}</div>
        </div>
        <span className={`badge text-[10px] ${stageBadgeColor(stage)}`}>{stage.replace(/_/g, ' ')}</span>
        <div className="text-right shrink-0">
          <div className="text-xs text-slate-600">{j.days_past_due ?? 0} DPD</div>
          <div className="text-[10px] text-slate-400">{j.current_balance ? formatCurrency(j.current_balance) : '—'}</div>
        </div>
        <span className="text-[10px] text-slate-400 shrink-0 ml-2 w-16 text-right truncate">
          {humanEventLabel(j.last_event_type ?? '')}
        </span>
        <ChevronRight size={14} className="text-slate-300 shrink-0" />
      </div>
    </Link>
  )
}

function AgentTile({ s }: { s: import('@/lib/api').AgentSummary }) {
  const conf = (s.avg_confidence ?? 0) * 100
  return (
    <div className="border border-slate-200 rounded-lg p-3 bg-white">
      <div className="flex items-center justify-between">
        <span className="text-xs font-bold text-slate-700">{s.agent_type.replace(/_/g, ' ')}</span>
        <Brain size={14} className="text-purple-500" />
      </div>
      <div className="mt-2 text-2xl font-bold text-slate-800">{s.actions_24h}</div>
      <div className="text-[10px] text-slate-500">actions in 24h</div>
      <div className="flex justify-between mt-1.5 text-[10px]">
        <span className="text-slate-500">5m: {s.actions_5m}</span>
        <span className={s.escalations_24h > 0 ? 'text-amber-600' : 'text-slate-500'}>
          escalations: {s.escalations_24h}
        </span>
      </div>
      <div className="text-[10px] text-slate-500 mt-0.5">
        avg confidence: {conf.toFixed(0)}%
      </div>
    </div>
  )
}

function ActionRow({ a }: { a: import('@/lib/api').AgentAction }) {
  const isEscalated = a.status === 'escalated'
  const conf = (a.confidence ?? 0) * 100
  return (
    <Link to={`/customer/${a.customer_id}`} className="block hover:bg-slate-50 border-b border-slate-100 px-3 py-2">
      <div className="flex items-center gap-2 text-xs">
        <Brain size={12} className={isEscalated ? 'text-amber-500' : 'text-purple-500'} />
        <span className="font-semibold text-slate-700 truncate max-w-[120px]">
          {a.agent_type.replace(/_/g, ' ')}
        </span>
        <span className="font-medium text-slate-800 truncate flex-1">
          {a.action_type.replace(/_/g, ' ')}
        </span>
        <span className={`badge text-[10px] ${
          conf > 80 ? 'badge-green' : conf > 50 ? 'badge-yellow' : 'badge-red'
        }`}>
          {conf.toFixed(0)}%
        </span>
        {isEscalated && <span className="badge badge-red text-[10px]">ESC</span>}
        <span className="text-[10px] text-slate-400 ml-1">{formatTime(a.created_at)}</span>
      </div>
      {a.rationale && (
        <div className="text-[11px] text-slate-500 mt-0.5 pl-4 line-clamp-1">{a.rationale}</div>
      )}
    </Link>
  )
}

function EscalationRow({ e }: { e: import('@/lib/api').Escalation }) {
  const name = e.first_name && e.last_name ? `${e.first_name} ${e.last_name}` : e.customer_id
  const sec = e.seconds_until_sla
  const overdue = sec < 0
  const slaTone = overdue ? 'text-red-600 font-bold' :
                  sec < 600 ? 'text-amber-600' : 'text-slate-500'
  const urgencyTone = e.urgency === 'immediate' ? 'badge-red' :
                      e.urgency === 'high' ? 'badge-yellow' : 'badge-blue'
  return (
    <Link to={`/customer/${e.customer_id}`} className="block hover:bg-slate-50 border-b border-slate-100 px-3 py-2">
      <div className="flex items-center gap-2 text-xs">
        <AlertTriangle size={12} className={e.urgency === 'immediate' ? 'text-red-500' : 'text-amber-500'} />
        <span className={`badge text-[10px] ${urgencyTone}`}>{e.urgency}</span>
        <span className="font-semibold text-slate-700 truncate">{name}</span>
        <span className="text-slate-500 truncate flex-1">{e.specialist_type}</span>
        <span className={`text-[10px] ${slaTone}`}>
          {overdue ? `SLA missed (${Math.abs(sec)}s ago)` : `SLA in ${formatDuration(sec)}`}
        </span>
      </div>
      <div className="text-[11px] text-slate-500 mt-0.5 pl-4 line-clamp-1">{e.reason}</div>
    </Link>
  )
}

function ComplianceBlockRow({ b }: { b: import('@/lib/api').ComplianceBlock }) {
  return (
    <Link to={`/customer/${b.customer_id}`} className="block hover:bg-slate-50 border-b border-slate-100 px-3 py-2">
      <div className="flex items-center gap-2 text-xs">
        <Shield size={12} className="text-red-500" />
        <span className="font-semibold text-slate-800">
          {b.action_blocked ? b.action_blocked.replace(/_/g, ' ') : 'action'} blocked
        </span>
        <code className="text-[10px] text-slate-400">{b.customer_id}</code>
        <span className="text-[10px] text-slate-400 ml-auto">{formatTime(b.occurred_at)}</span>
      </div>
      <div className="text-[11px] text-slate-500 mt-0.5 pl-4">
        {b.rule_name && <span className="font-medium">{b.rule_name}</span>}
        {b.reason && <span> · {b.reason}</span>}
      </div>
    </Link>
  )
}

function formatDuration(sec: number): string {
  if (sec < 60) return `${sec}s`
  if (sec < 3600) return `${Math.round(sec / 60)}m`
  return `${Math.round(sec / 3600)}h`
}

export default function OperationsFloor() {
  const { connected } = useWebSocket('/ws/events/all', 50)

  const { data: pulse } = useQuery({
    queryKey: ['ops-pulse'],
    queryFn: api.opsPulse,
    refetchInterval: 3000,
  })

  const { data: journeys } = useQuery({
    queryKey: ['ops-live-journeys'],
    queryFn: () => api.opsLiveJourneys(80),
    refetchInterval: 4000,
  })

  const { data: channels } = useQuery({
    queryKey: ['ops-channels'],
    queryFn: api.opsChannelActivity,
    refetchInterval: 3000,
  })

  const { data: agentSummary } = useQuery({
    queryKey: ['ops-agent-summary'],
    queryFn: api.opsAgentSummary,
    refetchInterval: 5000,
  })

  const { data: agentActivity } = useQuery({
    queryKey: ['ops-agent-activity'],
    queryFn: () => api.opsAgentActivity(20),
    refetchInterval: 4000,
  })

  const { data: escalations } = useQuery({
    queryKey: ['ops-escalations'],
    queryFn: api.opsEscalationQueue,
    refetchInterval: 4000,
  })

  const { data: blocks } = useQuery({
    queryKey: ['ops-compliance-blocks'],
    queryFn: () => api.opsComplianceBlocks(15),
    refetchInterval: 4000,
  })

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      <div className="px-6 py-3 border-b border-slate-200 bg-white flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Radio size={22} className="text-blue-600" />
          <div>
            <h1 className="text-lg font-bold text-slate-800">Operations Floor</h1>
            <p className="text-xs text-slate-500">Live view of collections activity across the portfolio</p>
          </div>
        </div>
        <div className="flex items-center gap-2 text-sm">
          <span className={`w-2 h-2 rounded-full ${connected ? 'bg-emerald-500 animate-pulse' : 'bg-red-500'}`} />
          <span className={connected ? 'text-emerald-700 text-xs' : 'text-red-600 text-xs'}>
            {connected ? 'Streaming live' : 'Disconnected'}
          </span>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        <div className="grid grid-cols-6 gap-3">
          <PulseTile
            label="Active journeys"
            value={pulse?.active_journeys ?? '—'}
            sub="last 5 min"
            icon={<Users size={12} />}
            live
          />
          <PulseTile
            label="Events / min"
            value={pulse?.events_last_minute ?? '—'}
            sub="last 60 sec"
            icon={<Activity size={12} />}
            live
          />
          <PulseTile
            label="Agent actions"
            value={pulse?.agent_actions_5m ?? '—'}
            sub="last 5 min"
            icon={<Brain size={12} />}
          />
          <PulseTile
            label="Pending escalations"
            value={pulse?.pending_escalations ?? '—'}
            tone={pulse && pulse.pending_escalations > 5 ? 'warn' : 'default'}
            icon={<AlertTriangle size={12} />}
          />
          <PulseTile
            label="Compliance blocks"
            value={pulse?.compliance_blocks_1h ?? '—'}
            sub="last hour"
            tone={pulse && pulse.compliance_blocks_1h > 0 ? 'warn' : 'default'}
            icon={<Shield size={12} />}
          />
          <PulseTile
            label="Stage transitions"
            value={pulse?.stage_transitions_1h ?? '—'}
            sub="last hour"
            icon={<TrendingUp size={12} />}
          />
        </div>

        <section>
          <h2 className="text-sm font-bold text-slate-700 mb-3 flex items-center gap-2">
            <Activity size={16} /> Channel activity (last 5 min)
          </h2>
          <div className="grid grid-cols-6 gap-3">
            {(channels?.channels ?? []).map((c, i) => (
              <ChannelTile key={`${c.channel}-${c.direction}-${i}`} row={c} />
            ))}
            {(channels?.channels ?? []).length === 0 && (
              <div className="col-span-6 text-sm text-slate-400 text-center py-6">
                No channel activity yet — traffic generator is warming up.
              </div>
            )}
          </div>
        </section>

        <section className="grid grid-cols-3 gap-6">
          <div>
            <h2 className="text-sm font-bold text-slate-700 mb-3 flex items-center gap-2">
              <Users size={16} /> Live journeys
              <span className="badge badge-gray text-[10px] ml-1">{journeys?.count ?? 0}</span>
            </h2>
            <div className="bg-white border border-slate-200 rounded-lg max-h-[500px] overflow-y-auto">
              {(journeys?.journeys ?? []).map((j) => (
                <JourneyRow key={j.customer_id} j={j} />
              ))}
              {(journeys?.journeys ?? []).length === 0 && (
                <p className="p-4 text-sm text-slate-400">Waiting for first events…</p>
              )}
            </div>
          </div>

          <div>
            <h2 className="text-sm font-bold text-slate-700 mb-3 flex items-center gap-2">
              <Brain size={16} /> AI agent activity
            </h2>
            <div className="grid grid-cols-2 gap-2 mb-3">
              {(agentSummary?.agents ?? []).map((s) => (
                <AgentTile key={s.agent_type} s={s} />
              ))}
            </div>
            <div className="bg-white border border-slate-200 rounded-lg max-h-[330px] overflow-y-auto">
              {(agentActivity?.actions ?? []).map((a) => (
                <ActionRow key={a.action_id} a={a} />
              ))}
              {(agentActivity?.actions ?? []).length === 0 && (
                <p className="p-4 text-sm text-slate-400">No AI agent actions yet.</p>
              )}
            </div>
          </div>

          <div>
            <h2 className="text-sm font-bold text-slate-700 mb-3 flex items-center gap-2">
              <Shield size={16} /> Enforcement &amp; escalation
            </h2>
            <div className="space-y-3">
              <div>
                <div className="text-[11px] uppercase tracking-wider text-amber-700 mb-1.5">Escalation queue</div>
                <div className="bg-white border border-slate-200 rounded-lg max-h-[230px] overflow-y-auto">
                  {(escalations?.escalations ?? []).map((e) => (
                    <EscalationRow key={e.escalation_id} e={e} />
                  ))}
                  {(escalations?.escalations ?? []).length === 0 && (
                    <p className="p-4 text-sm text-slate-400">No pending escalations.</p>
                  )}
                </div>
              </div>
              <div>
                <div className="text-[11px] uppercase tracking-wider text-red-700 mb-1.5">Recent compliance blocks</div>
                <div className="bg-white border border-slate-200 rounded-lg max-h-[230px] overflow-y-auto">
                  {(blocks?.blocks ?? []).map((b) => (
                    <ComplianceBlockRow key={b.event_id} b={b} />
                  ))}
                  {(blocks?.blocks ?? []).length === 0 && (
                    <p className="p-4 text-sm text-slate-400">No recent compliance blocks.</p>
                  )}
                </div>
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  )
}
