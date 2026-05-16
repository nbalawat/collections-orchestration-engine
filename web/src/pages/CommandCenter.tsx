import { useState, useEffect, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api } from '@/lib/api'
import type { Event, Customer360 } from '@/lib/api'
import { useWebSocket } from '@/hooks/useWebSocket'
import { formatCurrency, formatNumber, formatDateTime, formatTime, channelIcon, stageBadgeColor, humanEventLabel } from '@/lib/utils'
import {
  Activity, DollarSign, Users, AlertTriangle, TrendingUp, Brain, Shield,
  ChevronRight, X, Phone, MessageSquare, Mail, Monitor, Zap, Clock,
  ArrowRight, ExternalLink, Bot, FileText, CreditCard, AlertCircle,
  CheckCircle, Eye
} from 'lucide-react'

type FilterTab = 'all' | 'interaction' | 'ai_reasoning' | 'decision' | 'compliance' | 'lifecycle'

interface WSEvent {
  topic?: string
  customer_id?: string
  event_type?: string
  category?: string
  channel?: string
  direction?: string
  intent?: string
  payload?: Record<string, unknown>
  source_service?: string
  occurred_at?: string
  event_id?: string
  event_category?: string
  [key: string]: unknown
}

function categoryForFilter(event: WSEvent): string {
  const cat = event.event_category || event.category || ''
  if (cat) return cat
  const src = event.source_service || ''
  if (src.includes('ai-agent') || src.includes('ai_agent')) return 'ai_reasoning'
  const et = event.event_type || ''
  if (et.includes('strategy')) return 'decision'
  if (et.includes('compliance')) return 'compliance'
  if (et.includes('journey') || et.includes('stage')) return 'lifecycle'
  return 'interaction'
}

function isAiSource(source: string): boolean {
  return source.includes('ai-agent') || source.includes('ai_agent') || source.includes('claude') || source.includes('reasoning')
}

function riskColor(score: number): string {
  if (score < 40) return 'bg-green-500'
  if (score <= 70) return 'bg-amber-500'
  return 'bg-red-500'
}

function riskTextColor(score: number): string {
  if (score < 40) return 'text-green-700'
  if (score <= 70) return 'text-amber-700'
  return 'text-red-700'
}

interface MetricPillProps {
  label: string
  value: string
  icon?: React.ReactNode
}

function MetricPill({ label, value, icon }: MetricPillProps) {
  return (
    <div className="flex items-center gap-1.5 px-3 py-1">
      {icon && <span className="text-slate-400">{icon}</span>}
      <span className="text-xs text-slate-500 whitespace-nowrap">{label}</span>
      <span className="text-sm font-semibold text-slate-800 whitespace-nowrap">{value}</span>
    </div>
  )
}

interface EventRowProps {
  event: WSEvent
  onClick: () => void
  selected: boolean
}

function EventRow({ event, onClick, selected }: EventRowProps) {
  const channel = event.channel || 'system'
  const source = event.source_service || ''
  const eventType = event.event_type || ''
  const intent = event.intent || (event.payload as Record<string, unknown>)?.intent as string | undefined
  const customerId = event.customer_id || ''
  const displayId = customerId.length > 9 ? customerId.slice(0, 9) : customerId

  return (
    <div
      className={`event-row animate-fade-in ${selected ? 'selected' : ''}`}
      onClick={onClick}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => { if (e.key === 'Enter') onClick() }}
    >
      <div className="flex items-center gap-2 min-w-0 flex-1">
        <span className={`channel-${channel} shrink-0`} />
        <span className="text-sm shrink-0">{channelIcon(channel)}</span>
        <span className="text-xs font-mono text-slate-500 shrink-0 w-20 truncate">{displayId}</span>
        <span className="text-sm text-slate-700 truncate">{humanEventLabel(eventType)}</span>
        {intent && (
          <span className={`badge text-[10px] shrink-0 ${
            intent.toUpperCase().includes('HARDSHIP') ? 'badge-purple' :
            intent.toUpperCase().includes('PTP') ? 'badge-green' :
            intent.toUpperCase().includes('DISPUTE') ? 'badge-red' :
            intent.toUpperCase().includes('PAYMENT') ? 'badge-green' :
            'badge-blue'
          }`}>
            {intent.toUpperCase()}
          </span>
        )}
        {isAiSource(source) && (
          <Brain size={14} className="text-purple-500 shrink-0" />
        )}
      </div>
      <span className="text-xs text-slate-400 shrink-0 ml-2">
        {event.occurred_at ? formatTime(event.occurred_at) : ''}
      </span>
    </div>
  )
}

function NoSelectionState() {
  return (
    <div className="flex-1 flex flex-col items-center justify-center text-slate-400 gap-3 p-8">
      <Eye size={40} strokeWidth={1.5} />
      <p className="text-sm text-center">Select an event to view customer details</p>
    </div>
  )
}

function EmptyState() {
  return (
    <div className="flex-1 flex flex-col items-center justify-center text-slate-400 gap-3 p-8">
      <Activity size={40} strokeWidth={1.5} />
      <p className="text-sm text-center">No events yet. Run a demo scenario to see live events.</p>
    </div>
  )
}

interface CustomerDetailPanelProps {
  customer360: Customer360
  customerId: string
  traces: Event[]
  onClose: () => void
}

function CustomerDetailPanel({ customer360, customerId, traces, onClose }: CustomerDetailPanelProps) {
  const [expandedTrace, setExpandedTrace] = useState<string | null>(null)
  const profile = customer360.profile as Record<string, unknown>
  const accounts = customer360.accounts || []
  const flags = customer360.compliance_flags || []
  const ptps = customer360.active_ptps || []
  const recentEvents = (customer360.recent_events || []).slice(0, 10)
  const firstAccount = accounts[0] as Record<string, unknown> | undefined

  const riskScore = (profile.risk_score as number) || 0
  const dpd = (firstAccount?.days_past_due as number) || 0
  const balance = (firstAccount?.current_balance as number) || 0
  const pastDue = (firstAccount?.total_past_due as number) || 0
  const stage = (firstAccount?.delinquency_stage as string) || (profile.segment as string) || ''
  const firstName = (profile.first_name as string) || ''
  const lastName = (profile.last_name as string) || ''

  const customerTraces = traces.filter((t) => t.customer_id === customerId)

  return (
    <div className="animate-slide-in flex flex-col h-full">
      <div className="flex items-start justify-between p-4 border-b border-slate-200">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="text-base font-bold text-slate-800 truncate">
              {firstName} {lastName}
            </h3>
            {stage && <span className={`badge text-[10px] ${stageBadgeColor(stage)}`}>{stage.replace(/_/g, ' ')}</span>}
          </div>
          <p className="text-xs text-slate-500 font-mono mt-0.5">{customerId}</p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <Link to={`/customer/${customerId}`} className="btn btn-sm btn-outline flex items-center gap-1 text-xs">
            View Full Journey <ArrowRight size={12} />
          </Link>
          <button onClick={onClose} className="p-1 rounded hover:bg-slate-100 text-slate-400 hover:text-slate-600">
            <X size={16} />
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto scrollbar-thin p-4 space-y-4">
        <div className="grid grid-cols-2 gap-3">
          <div className="bg-slate-50 rounded-lg p-3">
            <p className="text-xs text-slate-500 mb-1">Risk Score</p>
            <div className="flex items-center gap-2">
              <span className={`text-lg font-bold ${riskTextColor(riskScore)}`}>{riskScore}</span>
              <div className="flex-1 h-2 bg-slate-200 rounded-full overflow-hidden risk-gauge">
                <div
                  className={`h-full rounded-full risk-gauge-fill ${riskColor(riskScore)}`}
                  style={{ width: `${riskScore}%` }}
                />
              </div>
            </div>
          </div>
          <div className="bg-slate-50 rounded-lg p-3">
            <p className="text-xs text-slate-500 mb-1">Days Past Due</p>
            <p className={`text-lg font-bold ${dpd > 60 ? 'text-red-600' : dpd > 30 ? 'text-amber-600' : 'text-slate-800'}`}>{dpd}</p>
          </div>
          <div className="bg-slate-50 rounded-lg p-3">
            <p className="text-xs text-slate-500 mb-1">Balance</p>
            <p className="text-lg font-bold text-slate-800">{formatCurrency(balance)}</p>
          </div>
          <div className="bg-slate-50 rounded-lg p-3">
            <p className="text-xs text-slate-500 mb-1">Past Due</p>
            <p className={`text-lg font-bold ${pastDue > 0 ? 'text-red-600' : 'text-green-600'}`}>{formatCurrency(pastDue)}</p>
          </div>
        </div>

        <div>
          <div className="flex items-center gap-1.5 mb-2">
            <Shield size={14} className="text-slate-500" />
            <h4 className="text-xs font-semibold text-slate-600 uppercase tracking-wider">Compliance Flags</h4>
          </div>
          {flags.length > 0 ? (
            <div className="flex flex-wrap gap-1.5">
              {flags.map((f, i) => (
                <span key={i} className="badge badge-red text-[10px] flex items-center gap-1">
                  <AlertCircle size={10} />
                  {(f as Record<string, unknown>).flag_type as string}
                </span>
              ))}
            </div>
          ) : (
            <p className="text-xs text-green-600 flex items-center gap-1">
              <CheckCircle size={12} /> No flags
            </p>
          )}
        </div>

        <div>
          <h4 className="text-xs font-semibold text-slate-600 uppercase tracking-wider mb-2">Active PTPs</h4>
          {ptps.length > 0 ? (
            <div className="space-y-1.5">
              {ptps.map((p, i) => {
                const ptp = p as Record<string, unknown>
                return (
                  <div key={i} className="flex items-center justify-between bg-green-50 rounded px-3 py-1.5 text-xs">
                    <span className="font-semibold text-green-800">{formatCurrency(ptp.promised_amount as number)}</span>
                    <span className="text-green-700">due {ptp.promised_date as string}</span>
                    <span className={`badge text-[10px] ${(ptp.status as string) === 'pending' ? 'badge-yellow' : 'badge-green'}`}>
                      {(ptp.status as string || '').toUpperCase()}
                    </span>
                  </div>
                )
              })}
            </div>
          ) : (
            <p className="text-xs text-slate-400">No active PTPs</p>
          )}
        </div>

        <div>
          <h4 className="text-xs font-semibold text-slate-600 uppercase tracking-wider mb-2">Recent Activity</h4>
          <div className="space-y-0">
            {recentEvents.length > 0 ? recentEvents.map((evt, i) => (
              <div key={evt.event_id || i} className="flex items-start gap-2 py-1.5 border-l-2 border-slate-200 pl-3 ml-1 relative">
                <div className="absolute -left-[5px] top-2.5 w-2 h-2 rounded-full bg-slate-300" />
                <span className="text-sm shrink-0">{channelIcon(evt.channel)}</span>
                <div className="min-w-0 flex-1">
                  <span className="text-xs text-slate-700">{humanEventLabel(evt.event_type)}</span>
                  {evt.intent && (
                    <span className="badge badge-blue text-[9px] ml-1.5">{evt.intent.toUpperCase()}</span>
                  )}
                </div>
                <span className="text-[10px] text-slate-400 shrink-0">{formatTime(evt.occurred_at)}</span>
              </div>
            )) : (
              <p className="text-xs text-slate-400">No recent activity</p>
            )}
          </div>
        </div>

        {customerTraces.length > 0 && (
          <div>
            <div className="flex items-center gap-1.5 mb-2">
              <Brain size={14} className="text-purple-500" />
              <h4 className="text-xs font-semibold text-purple-700 uppercase tracking-wider">AI Activity</h4>
            </div>
            <div className="space-y-2">
              {customerTraces.map((trace) => {
                const tp = trace.payload || {}
                const reasoning = tp.reasoning_trace as Record<string, unknown> | undefined
                const agentType = (reasoning?.agent_type as string) || trace.source_service || 'AI Agent'
                const action = (reasoning?.action_taken as string) || trace.event_type || ''
                const confidence = reasoning?.confidence as number | undefined
                const latency = reasoning?.latency_ms as number | undefined
                const steps = (reasoning?.reasoning_steps as Array<Record<string, unknown>>) || []
                const isExpanded = expandedTrace === trace.event_id

                return (
                  <div key={trace.event_id} className="bg-purple-50 rounded-lg p-3 text-xs">
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-semibold text-purple-800">{agentType.replace(/_/g, ' ')}</span>
                      <div className="flex items-center gap-2 text-purple-600">
                        {confidence !== undefined && <span>{Math.round(confidence * 100)}% conf</span>}
                        {latency !== undefined && <span>{latency}ms</span>}
                      </div>
                    </div>
                    <p className="text-purple-700 mb-1">{action.replace(/_/g, ' ')}</p>
                    {steps.length > 0 && (
                      <button
                        onClick={() => setExpandedTrace(isExpanded ? null : trace.event_id)}
                        className="text-purple-500 hover:text-purple-700 underline text-[10px]"
                      >
                        {isExpanded ? 'Hide reasoning' : `Show reasoning (${steps.length} steps)`}
                      </button>
                    )}
                    {isExpanded && steps.length > 0 && (
                      <div className="mt-2 space-y-1 border-t border-purple-200 pt-2">
                        {steps.map((step, si) => (
                          <div key={si} className="flex gap-2">
                            <span className="text-purple-400 shrink-0">{si + 1}.</span>
                            <div>
                              <span className="font-medium text-purple-800">{step.step as string}</span>
                              <span className="text-purple-600 ml-1">{step.result as string}</span>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

const FILTER_TABS: { key: FilterTab; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'interaction', label: 'Channel' },
  { key: 'ai_reasoning', label: 'AI' },
  { key: 'decision', label: 'Decisions' },
  { key: 'compliance', label: 'Compliance' },
]

export default function CommandCenter() {
  const [selectedCustomerId, setSelectedCustomerId] = useState<string | null>(null)
  const [activeFilter, setActiveFilter] = useState<FilterTab>('all')

  const { events: wsEvents, connected } = useWebSocket('/ws/events/all', 200)
  const { data: initialEvents } = useQuery({
    queryKey: ['events-initial'],
    queryFn: () => api.listEvents(50),
    staleTime: 30000,
  })
  const { data: metrics } = useQuery({
    queryKey: ['dashboard-metrics'],
    queryFn: api.dashboardMetrics,
    refetchInterval: 15000,
  })
  const { data: tracesData } = useQuery({
    queryKey: ['reasoning-traces'],
    queryFn: () => api.getReasoningTraces(50),
    refetchInterval: 10000,
  })
  const { data: customer360, isLoading: customerLoading } = useQuery({
    queryKey: ['customer360', selectedCustomerId],
    queryFn: () => api.getCustomer360(selectedCustomerId!),
    enabled: !!selectedCustomerId,
  })

  const traces = tracesData?.traces || []
  const summary = metrics?.summary

  const allEvents = useMemo(() => {
    const apiEvents: WSEvent[] = (initialEvents?.events || []).map((e) => ({
      ...e,
      category: e.event_category,
    }))
    const seen = new Set<string>()
    const merged: WSEvent[] = []
    for (const e of wsEvents) {
      const id = (e.event_id as string) || `${e.customer_id}-${e.event_type}-${e.occurred_at}`
      if (!seen.has(id)) {
        seen.add(id)
        merged.push(e)
      }
    }
    for (const e of apiEvents) {
      const id = (e.event_id as string) || `${e.customer_id}-${e.event_type}-${e.occurred_at}`
      if (!seen.has(id)) {
        seen.add(id)
        merged.push(e)
      }
    }
    return merged
  }, [wsEvents, initialEvents])

  const filteredEvents = useMemo(() => {
    if (activeFilter === 'all') return allEvents
    return allEvents.filter((e) => categoryForFilter(e) === activeFilter)
  }, [allEvents, activeFilter])

  const ptpCount = metrics?.ptps?.ptps?.length || 0

  return (
    <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
      <div className="flex items-center justify-between px-4 py-2 bg-white border-b border-slate-200 shrink-0">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <Activity size={18} className="text-blue-600" />
            <h1 className="text-base font-bold text-slate-800">Command Center</h1>
          </div>
          {summary && (
            <div className="flex items-center divide-x divide-slate-200 ml-2">
              <MetricPill label="Customers" value={formatNumber(summary.total_customers)} icon={<Users size={13} />} />
              <MetricPill label="Outstanding" value={formatCurrency(summary.total_outstanding)} icon={<DollarSign size={13} />} />
              <MetricPill label="Past Due" value={formatCurrency(summary.total_past_due)} icon={<AlertTriangle size={13} />} />
              <MetricPill label="Avg DPD" value={`${Math.round(summary.avg_dpd)}d`} icon={<TrendingUp size={13} />} />
              <MetricPill label="PTPs" value={String(ptpCount)} icon={<FileText size={13} />} />
            </div>
          )}
        </div>
        <div className="flex items-center gap-2 text-sm">
          <span className={`w-2 h-2 rounded-full ${connected ? 'bg-green-500' : 'bg-red-500'} pulse-dot`} />
          <span className={`text-xs font-medium ${connected ? 'text-green-600' : 'text-red-500'}`}>
            {connected ? 'Live' : 'Offline'}
          </span>
        </div>
      </div>

      <div className="flex flex-1 min-h-0">
        <div className="flex-1 flex flex-col min-w-0 border-r border-slate-200">
          <div className="flex items-center justify-between px-4 py-2 border-b border-slate-100 shrink-0">
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-semibold text-slate-700">Live Event Stream</h2>
              <span className="badge badge-gray text-[10px]">{filteredEvents.length}</span>
            </div>
            <div className="flex items-center gap-1">
              {FILTER_TABS.map((tab) => (
                <button
                  key={tab.key}
                  onClick={() => setActiveFilter(tab.key)}
                  className={`px-2.5 py-1 text-xs rounded-md transition-colors ${
                    activeFilter === tab.key
                      ? 'bg-blue-100 text-blue-700 font-medium'
                      : 'text-slate-500 hover:text-slate-700 hover:bg-slate-100'
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>
          </div>

          <div className="flex-1 overflow-y-auto scrollbar-thin">
            {filteredEvents.length > 0 ? (
              filteredEvents.map((event, i) => {
                const key = (event.event_id as string) || `${event.customer_id}-${event.event_type}-${i}`
                return (
                  <EventRow
                    key={key}
                    event={event}
                    onClick={() => event.customer_id && setSelectedCustomerId(event.customer_id)}
                    selected={!!selectedCustomerId && event.customer_id === selectedCustomerId}
                  />
                )
              })
            ) : (
              <EmptyState />
            )}
          </div>
        </div>

        <div className="w-[440px] shrink-0 bg-white flex flex-col min-h-0">
          {selectedCustomerId ? (
            customerLoading ? (
              <div className="flex-1 flex items-center justify-center text-slate-400">
                <div className="flex flex-col items-center gap-2">
                  <div className="w-6 h-6 border-2 border-slate-300 border-t-blue-500 rounded-full animate-spin" />
                  <span className="text-xs">Loading customer data...</span>
                </div>
              </div>
            ) : customer360 ? (
              <CustomerDetailPanel
                customer360={customer360}
                customerId={selectedCustomerId}
                traces={traces}
                onClose={() => setSelectedCustomerId(null)}
              />
            ) : (
              <div className="flex-1 flex items-center justify-center text-slate-400 p-8">
                <p className="text-sm text-center">Customer data not available</p>
              </div>
            )
          ) : (
            <NoSelectionState />
          )}
        </div>
      </div>
    </div>
  )
}
