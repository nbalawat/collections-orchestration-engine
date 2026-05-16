import { useState, useEffect, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api } from '@/lib/api'
import type { Customer360, Event } from '@/lib/api'
import { useWebSocket } from '@/hooks/useWebSocket'
import {
  formatCurrency, formatNumber, formatDateTime, formatTime, channelIcon, stageBadgeColor,
} from '@/lib/utils'
import {
  Play, CheckCircle, Loader, AlertCircle, Radio, X, Brain, Shield,
  ChevronRight, Phone, MessageSquare, Mail, Activity, Zap, Clock,
  ArrowRight, User, RefreshCw, Eye, DollarSign,
} from 'lucide-react'

function eventLabel(event: LiveEvent): string {
  const labels: Record<string, string> = {
    sms_sent: 'SMS Sent',
    sms_received: 'SMS Received',
    sms_delivered: 'SMS Delivered',
    call_connected_rpc: 'Voice Call Connected',
    call_initiated: 'Call Initiated',
    call_completed: 'Call Completed',
    call_outcome_logged: 'Call Outcome Logged',
    email_sent: 'Email Sent',
    email_delivered: 'Email Delivered',
    email_opened: 'Email Opened',
    email_bounced: 'Email Bounced',
    payment_received: 'Payment Received',
    payment_posted: 'Payment Posted',
    strategy_evaluation: 'Strategy Evaluated',
    ai_reasoning_trace: 'AI Reasoning',
    journey_stage_change: 'Journey Stage Change',
    compliance_check: 'Compliance Check',
    dialer_campaign_loaded: 'Dialer Campaign',
    dialer_call_attempted: 'Dialer Attempt',
    hardship_detected: 'Hardship Detected',
    escalation_triggered: 'Escalation',
    ptp_recorded: 'PTP Recorded',
    arrangement_applied: 'Arrangement Applied',
  }

  const et = event.event_type || ''
  if (labels[et]) return labels[et]

  const topic = (event.topic as string) || ''
  if (topic.includes('decisions') || et === 'decisions') {
    const dt = (event.decision_type as string) || ''
    if (dt === 'strategy_evaluation') return 'Strategy Evaluated'
    return 'Decision: ' + (dt || event.policy_name || 'Evaluation')
  }
  if (topic.includes('compliance') || et === 'compliance') {
    const ct = (event.check_type as string) || ''
    const passed = event.passed as boolean | undefined
    const rule = (event.rule_name as string) || ''
    const blocked = (event.action_blocked as string) || ''
    if (blocked) return `Blocked: ${blocked.replace(/_/g, ' ')}`
    if (ct) return `Compliance: ${ct.replace(/_/g, ' ')}${passed === false ? ' ✗' : passed === true ? ' ✓' : ''}`
    return `Compliance${rule ? ': ' + rule : ''}`
  }
  if (topic.includes('lifecycle') || et === 'lifecycle') {
    const from = (event.from_stage as string) || ''
    const to = (event.to_stage as string) || ''
    if (from && to) return `${from} → ${to}`
    if (to) return `Stage: ${to}`
    return 'Lifecycle Change'
  }
  if (topic.includes('ai.reasoning') || et === 'ai_reasoning') {
    const agent = (event.agent_type as string) || ''
    return agent ? `AI: ${agent.replace(/_/g, ' ')}` : 'AI Reasoning'
  }
  if (topic.includes('actions') || et === 'actions') {
    const at = (event.action_type as string) || ''
    return at ? at.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()) : 'Action Dispatched'
  }

  if (et) return et.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()).replace(/Rpc$/, '').trim()
  return 'Event'
}

function eventCategory(event: LiveEvent): string {
  const topic = (event.topic as string) || ''
  if (topic.includes('decisions')) return 'decision'
  if (topic.includes('compliance')) return 'compliance'
  if (topic.includes('lifecycle')) return 'lifecycle'
  if (topic.includes('ai.reasoning')) return 'ai'
  if (topic.includes('ai.quality')) return 'ai'
  if (topic.includes('actions')) return 'action'
  if (event.channel) return 'channel'
  return event.event_category || event.category || 'unknown'
}

function categoryIcon(cat: string): string {
  switch (cat) {
    case 'decision': return '⚡'
    case 'compliance': return '🛡'
    case 'lifecycle': return '🔄'
    case 'ai': return '🧠'
    case 'action': return '🎯'
    default: return '⚙️'
  }
}

function channelColor(channel: string): string {
  const colors: Record<string, string> = {
    sms: 'bg-blue-500',
    email: 'bg-purple-500',
    voice: 'bg-emerald-500',
    dialer: 'bg-amber-500',
    digital: 'bg-cyan-500',
    system: 'bg-slate-400',
  }
  return colors[channel] || 'bg-slate-400'
}

function directionLabel(dir: string): string {
  if (dir === 'inbound') return 'Inbound'
  if (dir === 'outbound') return 'Outbound'
  return 'System'
}

function riskColor(score: number): string {
  if (score < 40) return 'bg-green-500'
  if (score <= 70) return 'bg-amber-500'
  return 'bg-red-500'
}

const SCENARIO_STEPS: Record<string, string[]> = {
  cross_channel: [
    'Start workflow',
    'Outbound SMS dunning notice',
    'Customer replies (hardship)',
    'Outbound email with options',
    'Email bounces',
    'Outbound voice call',
    'Agent applies arrangement',
  ],
  bankruptcy: [
    'Start workflow',
    'Bankruptcy filing notification',
    'Attempt SMS (should be blocked)',
    'Bankruptcy dismissed',
    'Workflow resumes',
  ],
  ptp: [
    'Start workflow',
    'Outbound voice call — PTP',
    'Customer confirms PTP via SMS',
    'Payment arrives',
    'Account cured',
  ],
  strategy_swap: [
    'Start multiple workflows',
    'Change strategy version',
    'Journeys pick up new rules',
  ],
  complex_case: [
    'Start workflow',
    'Inbound call — mixed signals',
    'AI reasoning triggered',
    'Specialist review',
  ],
  portfolio: [
    'Spin up customer workflows',
    'Generate cross-channel events',
    'Portfolio operations complete',
  ],
}

interface LiveEvent {
  event_id?: string
  customer_id?: string
  event_type?: string
  event_category?: string
  category?: string
  channel?: string
  direction?: string
  intent?: string
  payload?: Record<string, unknown>
  source_service?: string
  occurred_at?: string
  [key: string]: unknown
}

export default function Scenarios() {
  const queryClient = useQueryClient()
  const [activeScenario, setActiveScenario] = useState<string | null>(null)
  const [activeCustomer, setActiveCustomer] = useState<string | null>(null)
  const [scenarioStatus, setScenarioStatus] = useState<'idle' | 'running' | 'completed' | 'error'>('idle')
  const [scenarioResult, setScenarioResult] = useState<unknown>(null)
  const [scenarioError, setScenarioError] = useState<string | null>(null)
  const [capturedEvents, setCapturedEvents] = useState<LiveEvent[]>([])
  const [expandedEvent, setExpandedEvent] = useState<string | null>(null)
  const [draining, setDraining] = useState(false)
  const eventListRef = useRef<HTMLDivElement>(null)
  const lastWsCountRef = useRef(0)
  const seenIdsRef = useRef(new Set<string>())

  const { data: scenariosData } = useQuery({ queryKey: ['scenarios'], queryFn: api.listScenarios })

  const { events: wsEvents, connected, clear: clearWs } = useWebSocket('/ws/events/all', 500)

  const { data: customer360 } = useQuery({
    queryKey: ['scenario-customer360', activeCustomer],
    queryFn: () => api.getCustomer360(activeCustomer!),
    enabled: !!activeCustomer,
    refetchInterval: (scenarioStatus === 'running' || draining) ? 3000 : false,
  })

  const { data: workflowState, refetch: refetchWorkflow } = useQuery({
    queryKey: ['scenario-workflow', activeCustomer],
    queryFn: () => api.getJourneyState(activeCustomer!).catch(() => null),
    enabled: !!activeCustomer,
    refetchInterval: (scenarioStatus === 'running' || draining) ? 2000 : false,
  })

  const capturing = scenarioStatus === 'running' || draining

  useEffect(() => {
    if (!capturing || !activeCustomer) return
    const newCount = wsEvents.length
    const lastCount = lastWsCountRef.current
    if (newCount <= lastCount) return
    const fresh = wsEvents.slice(0, newCount - lastCount)
    lastWsCountRef.current = newCount
    const matching = fresh.filter(e => {
      if (e.customer_id && e.customer_id !== activeCustomer) return false
      const eid = (e.event_id as string) || ''
      if (eid && seenIdsRef.current.has(eid)) return false
      if (eid) seenIdsRef.current.add(eid)
      return true
    })
    if (matching.length > 0) {
      setCapturedEvents(prev => [...matching, ...prev])
    }
  }, [wsEvents, activeCustomer, capturing])

  const runMutation = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Record<string, unknown> }) => api.runScenario(id, body),
    onSuccess: (data) => {
      setScenarioStatus('completed')
      setScenarioResult(data.result)
      setDraining(true)
      setTimeout(() => setDraining(false), 8000)
      refetchWorkflow()
      queryClient.invalidateQueries({ queryKey: ['scenario-customer360', activeCustomer] })
    },
    onError: (error) => {
      setScenarioStatus('error')
      setScenarioError(String(error))
    },
  })

  const startScenario = (scenarioId: string, customerId: string) => {
    setActiveScenario(scenarioId)
    setActiveCustomer(customerId)
    setScenarioStatus('running')
    setScenarioResult(null)
    setScenarioError(null)
    setCapturedEvents([])
    clearWs()
    lastWsCountRef.current = 0
    seenIdsRef.current.clear()
    runMutation.mutate({ id: scenarioId, body: { customer_id: customerId } })
  }

  const resetScenario = () => {
    setActiveScenario(null)
    setActiveCustomer(null)
    setScenarioStatus('idle')
    setScenarioResult(null)
    setScenarioError(null)
    setCapturedEvents([])
  }

  const scenarios = scenariosData?.scenarios ?? []
  const activeScenarioData = scenarios.find(s => s.id === activeScenario)

  if (activeScenario && activeScenarioData) {
    return (
      <ScenarioTheater
        scenario={activeScenarioData}
        customerId={activeCustomer!}
        status={scenarioStatus}
        result={scenarioResult}
        error={scenarioError}
        events={capturedEvents}
        customer360={customer360 ?? null}
        workflowState={workflowState}
        connected={connected}
        expandedEvent={expandedEvent}
        setExpandedEvent={setExpandedEvent}
        eventListRef={eventListRef}
        onReset={resetScenario}
      />
    )
  }

  return (
    <div className="p-6 space-y-6 flex-1 overflow-y-auto overflow-x-hidden min-w-0">
      <div className="flex items-center gap-3">
        <Play size={24} className="text-green-600" />
        <h2 className="text-xl font-bold text-slate-800">Demo Scenarios</h2>
      </div>
      <p className="text-sm text-slate-500 max-w-3xl">
        Pre-scripted scenarios that drive realistic collections journeys through the orchestration engine.
        Select a scenario to watch events flow in real-time across channels, see AI agents reason, and observe workflow state transitions.
      </p>

      <div className="grid grid-cols-2 gap-4 min-w-0">
        {scenarios.map((s) => (
          <div key={s.id} className="card min-w-0 overflow-hidden hover:border-blue-300 transition-colors">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0 flex-1">
                <h3 className="font-semibold text-slate-800">{s.name}</h3>
                <p className="text-sm text-slate-500 mt-1">{s.description}</p>
                {s.default_customer && (
                  <p className="text-xs text-slate-400 mt-2 font-mono">Customer: {s.default_customer}</p>
                )}
              </div>
              <button
                className="btn btn-primary btn-sm shrink-0"
                onClick={() => startScenario(s.id, s.default_customer || 'CUST-0001')}
              >
                <Play size={14} /> Run
              </button>
            </div>

            {SCENARIO_STEPS[s.id] && (
              <div className="mt-3 pt-3 border-t border-slate-100">
                <p className="text-xs font-medium text-slate-500 mb-2">Steps:</p>
                <div className="flex flex-wrap gap-1.5">
                  {SCENARIO_STEPS[s.id].map((step, i) => (
                    <span key={i} className="inline-flex items-center gap-1 text-[11px] text-slate-500 bg-slate-50 rounded px-2 py-0.5">
                      <span className="text-slate-400 font-mono">{i + 1}</span>
                      {step}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

interface ScenarioTheaterProps {
  scenario: { id: string; name: string; description: string; default_customer: string }
  customerId: string
  status: 'idle' | 'running' | 'completed' | 'error'
  result: unknown
  error: string | null
  events: LiveEvent[]
  customer360: Customer360 | null
  workflowState: unknown
  connected: boolean
  expandedEvent: string | null
  setExpandedEvent: (id: string | null) => void
  eventListRef: React.RefObject<HTMLDivElement | null>
  onReset: () => void
}

function ScenarioTheater({
  scenario, customerId, status, result, error, events, customer360,
  workflowState, connected, expandedEvent, setExpandedEvent, eventListRef, onReset,
}: ScenarioTheaterProps) {
  const profile = customer360?.profile as Record<string, unknown> | undefined
  const accounts = customer360?.accounts || []
  const firstAccount = accounts[0] as Record<string, unknown> | undefined
  const flags = customer360?.compliance_flags || []
  const wfState = workflowState as Record<string, unknown> | null
  const steps = SCENARIO_STEPS[scenario.id] || []

  const estimatedStep = Math.min(
    steps.length,
    status === 'completed' ? steps.length :
    status === 'error' ? steps.length :
    Math.max(1, Math.ceil((events.length / Math.max(steps.length, 1)) * steps.length))
  )

  return (
    <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
      <div className="shrink-0 px-4 py-3 bg-white border-b border-slate-200 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button onClick={onReset} className="btn btn-outline btn-sm">
            <ArrowRight size={14} className="rotate-180" /> Back
          </button>
          <div>
            <h2 className="text-base font-bold text-slate-800">{scenario.name}</h2>
            <p className="text-xs text-slate-500">{scenario.description}</p>
          </div>
        </div>
        <div className="flex items-center gap-4">
          {status === 'running' && (
            <span className="flex items-center gap-2 text-sm text-blue-600 font-medium">
              <Loader size={14} className="animate-spin" /> Running...
            </span>
          )}
          {status === 'completed' && (
            <span className="flex items-center gap-2 text-sm text-green-600 font-medium">
              <CheckCircle size={14} /> Completed
            </span>
          )}
          {status === 'error' && (
            <span className="flex items-center gap-2 text-sm text-red-600 font-medium">
              <AlertCircle size={14} /> Failed
            </span>
          )}
          <div className="flex items-center gap-1.5">
            <span className={`w-2 h-2 rounded-full ${connected ? 'bg-green-500 pulse-dot' : 'bg-red-500'}`} />
            <span className={`text-xs ${connected ? 'text-green-600' : 'text-red-500'}`}>
              {connected ? 'Live' : 'Offline'}
            </span>
          </div>
        </div>
      </div>

      <div className="shrink-0 px-4 py-3 bg-slate-50 border-b border-slate-200">
        <div className="flex items-center gap-2">
          {steps.map((step, i) => (
            <div key={i} className="flex items-center gap-2">
              {i > 0 && <div className={`w-6 h-px ${i < estimatedStep ? 'bg-green-400' : 'bg-slate-300'}`} />}
              <div className="flex items-center gap-1.5">
                <div className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold ${
                  i < estimatedStep ? 'bg-green-500 text-white' :
                  i === estimatedStep && status === 'running' ? 'bg-blue-500 text-white animate-pulse' :
                  'bg-slate-200 text-slate-500'
                }`}>
                  {i < estimatedStep ? <CheckCircle size={12} /> : i + 1}
                </div>
                <span className={`text-xs whitespace-nowrap ${
                  i < estimatedStep ? 'text-green-700 font-medium' :
                  i === estimatedStep && status === 'running' ? 'text-blue-700 font-medium' :
                  'text-slate-400'
                }`}>
                  {step}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="flex flex-1 min-h-0">
        <div className="flex-1 flex flex-col min-w-0 border-r border-slate-200">
          <div className="shrink-0 px-4 py-2 border-b border-slate-100 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Radio size={14} className={status === 'running' ? 'text-red-500 animate-pulse' : 'text-slate-400'} />
              <h3 className="text-sm font-semibold text-slate-700">Live Event Stream</h3>
              <span className="badge badge-gray text-[10px]">{events.length}</span>
            </div>
            <span className="text-xs text-slate-400 font-mono">{customerId}</span>
          </div>
          <div ref={eventListRef} className="flex-1 overflow-y-auto scrollbar-thin">
            {events.length === 0 ? (
              <div className="flex-1 flex flex-col items-center justify-center text-slate-400 gap-3 p-12 h-full">
                {status === 'running' ? (
                  <>
                    <Loader size={32} className="animate-spin text-blue-400" />
                    <p className="text-sm">Waiting for events...</p>
                    <p className="text-xs text-slate-300">Events will appear here as the scenario runs</p>
                  </>
                ) : (
                  <>
                    <Activity size={32} />
                    <p className="text-sm">No events captured</p>
                  </>
                )}
              </div>
            ) : (
              <div>
                {events.map((event, i) => {
                  const eid = event.event_id || `evt-${i}`
                  const channel = event.channel || 'system'
                  const source = event.source_service || ''
                  const isAi = source.includes('ai-agent') || source.includes('ai_agent')
                  const intent = event.intent || (event.payload as Record<string, unknown>)?.intent as string | undefined
                  const isExpanded = expandedEvent === eid

                  return (
                    <div
                      key={eid}
                      className="animate-fade-in border-b border-slate-100 hover:bg-slate-50 transition-colors"
                    >
                      <div
                        className="px-4 py-2.5 flex items-center gap-2 cursor-pointer"
                        onClick={() => setExpandedEvent(isExpanded ? null : eid)}
                      >
                        {event.channel ? (
                          <>
                            <div className={`w-2 h-2 rounded-full shrink-0 ${channelColor(channel)}`} />
                            <span className="text-sm shrink-0">{channelIcon(channel)}</span>
                          </>
                        ) : (
                          <span className="text-sm shrink-0">{categoryIcon(eventCategory(event))}</span>
                        )}
                        {event.direction && (
                          <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${
                            event.direction === 'inbound' ? 'bg-blue-50 text-blue-600' :
                            event.direction === 'outbound' ? 'bg-green-50 text-green-600' :
                            'bg-slate-50 text-slate-500'
                          }`}>
                            {directionLabel(event.direction)}
                          </span>
                        )}
                        <span className="text-sm text-slate-700 font-medium truncate">
                          {eventLabel(event)}
                        </span>
                        {intent && (
                          <span className={`badge text-[10px] shrink-0 ${
                            intent.toUpperCase().includes('HARDSHIP') ? 'badge-purple' :
                            intent.toUpperCase().includes('PTP') ? 'badge-green' :
                            intent.toUpperCase().includes('DISPUTE') ? 'badge-red' :
                            intent.toUpperCase().includes('SETTLEMENT') ? 'badge-yellow' :
                            'badge-blue'
                          }`}>
                            {intent.toUpperCase()}
                          </span>
                        )}
                        {isAi && <Brain size={14} className="text-purple-500 shrink-0" />}
                        <span className="ml-auto text-[10px] text-slate-400 shrink-0">
                          {event.occurred_at ? formatTime(event.occurred_at) : ''}
                        </span>
                        <ChevronRight size={12} className={`text-slate-300 shrink-0 transition-transform ${isExpanded ? 'rotate-90' : ''}`} />
                      </div>

                      {isExpanded && (
                        <div className="px-4 pb-3 animate-fade-in">
                          <div className="ml-6 p-3 bg-slate-50 rounded-lg text-xs space-y-2">
                            <div className="grid grid-cols-2 gap-x-4 gap-y-1">
                              {event.event_category && (
                                <div><span className="text-slate-400">Category:</span> <span className="text-slate-700">{event.event_category || event.category}</span></div>
                              )}
                              {event.channel && (
                                <div><span className="text-slate-400">Channel:</span> <span className="text-slate-700">{event.channel}</span></div>
                              )}
                              {source && (
                                <div><span className="text-slate-400">Source:</span> <span className="text-slate-700 font-mono">{source}</span></div>
                              )}
                              {event.customer_id && (
                                <div><span className="text-slate-400">Customer:</span> <span className="text-slate-700 font-mono">{event.customer_id}</span></div>
                              )}
                            </div>
                            {event.payload && Object.keys(event.payload).length > 0 && (
                              <div>
                                <span className="text-slate-400 block mb-1">Payload:</span>
                                <pre className="text-[11px] bg-white p-2 rounded border border-slate-200 overflow-auto max-h-32 text-slate-600">
                                  {JSON.stringify(event.payload, null, 2)}
                                </pre>
                              </div>
                            )}
                          </div>
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        </div>

        <div className="w-[400px] shrink-0 flex flex-col min-h-0 overflow-y-auto scrollbar-thin bg-white">
          <div className="p-4 space-y-4">
            {profile && (
              <div className="card bg-gradient-to-br from-slate-50 to-white">
                <div className="flex items-center gap-3 mb-3">
                  <div className="w-10 h-10 rounded-full bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center text-white font-bold text-sm">
                    {(profile.first_name as string || '?')[0]}{(profile.last_name as string || '?')[0]}
                  </div>
                  <div className="min-w-0">
                    <h3 className="font-bold text-slate-800 truncate">
                      {profile.first_name as string} {profile.last_name as string}
                    </h3>
                    <p className="text-xs text-slate-500 font-mono">{customerId}</p>
                  </div>
                  <Link to={`/customer/${customerId}`} className="ml-auto text-blue-500 hover:text-blue-700">
                    <Eye size={16} />
                  </Link>
                </div>
                <div className="grid grid-cols-3 gap-2 text-center">
                  <div className="bg-white rounded-lg p-2 border border-slate-100">
                    <div className="text-xs text-slate-400">Risk</div>
                    <div className={`text-sm font-bold ${(profile.risk_score as number) > 70 ? 'text-red-600' : (profile.risk_score as number) > 40 ? 'text-amber-600' : 'text-green-600'}`}>
                      {profile.risk_score as number}
                    </div>
                  </div>
                  <div className="bg-white rounded-lg p-2 border border-slate-100">
                    <div className="text-xs text-slate-400">DPD</div>
                    <div className="text-sm font-bold text-slate-800">{firstAccount?.days_past_due as number ?? '-'}</div>
                  </div>
                  <div className="bg-white rounded-lg p-2 border border-slate-100">
                    <div className="text-xs text-slate-400">Balance</div>
                    <div className="text-sm font-bold text-slate-800">{formatCurrency(firstAccount?.current_balance as number ?? 0)}</div>
                  </div>
                </div>
                {(firstAccount?.total_past_due as number) > 0 && (
                  <div className="mt-2 px-3 py-1.5 bg-red-50 rounded text-xs text-red-700 font-medium text-center">
                    Past Due: {formatCurrency(firstAccount?.total_past_due as number)}
                  </div>
                )}
                {flags.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1">
                    {flags.map((f, i) => (
                      <span key={i} className="badge badge-red text-[10px]">
                        <Shield size={10} className="mr-0.5" />
                        {(f as Record<string, unknown>).flag_type as string}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            )}

            {wfState && (
              <div className="card">
                <div className="flex items-center gap-2 mb-3">
                  <Activity size={14} className="text-blue-500" />
                  <h4 className="text-xs font-semibold text-slate-600 uppercase tracking-wider">Workflow State</h4>
                  {status === 'running' && (
                    <span className="ml-auto flex items-center gap-1 text-[10px] text-blue-600">
                      <RefreshCw size={10} className="animate-spin" /> Auto-refreshing
                    </span>
                  )}
                </div>
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-slate-500">Stage</span>
                    <span className={`badge text-[10px] ${stageBadgeColor(wfState.stage as string || '')}`}>
                      {((wfState.stage as string) || 'UNKNOWN').replace(/_/g, ' ')}
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-slate-500">Suspended</span>
                    <span className={`text-xs font-medium ${wfState.suspended ? 'text-red-600' : 'text-green-600'}`}>
                      {wfState.suspended ? 'Yes' : 'No'}
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-slate-500">Events</span>
                    <span className="text-xs font-medium text-slate-700">{wfState.events_count as number ?? 0}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-slate-500">Actions</span>
                    <span className="text-xs font-medium text-slate-700">{wfState.actions_count as number ?? 0}</span>
                  </div>
                  {(wfState.compliance_flags as string[])?.length > 0 && (
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-slate-500">Flags</span>
                      <div className="flex gap-1">
                        {(wfState.compliance_flags as string[]).map((f, i) => (
                          <span key={i} className="badge badge-red text-[10px]">{f}</span>
                        ))}
                      </div>
                    </div>
                  )}
                  {wfState.active_ptp && (
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-slate-500">Active PTP</span>
                      <span className="text-xs font-medium text-green-700">
                        {formatCurrency((wfState.active_ptp as Record<string, unknown>)?.amount as number ?? 0)}
                      </span>
                    </div>
                  )}
                  {(wfState.segment as Record<string, unknown>) && (
                    <div className="pt-2 border-t border-slate-100">
                      <span className="text-xs text-slate-500 block mb-1">Strategy Segment</span>
                      <pre className="text-[10px] bg-slate-50 rounded p-2 overflow-auto max-h-20 text-slate-600">
                        {JSON.stringify(wfState.segment, null, 2)}
                      </pre>
                    </div>
                  )}
                </div>
              </div>
            )}

            {!wfState && customerId && status === 'running' && (
              <div className="card">
                <div className="flex items-center gap-2 mb-3">
                  <Activity size={14} className="text-blue-500" />
                  <h4 className="text-xs font-semibold text-slate-600 uppercase tracking-wider">Workflow State</h4>
                </div>
                <div className="flex items-center justify-center py-4 text-slate-400">
                  <Loader size={16} className="animate-spin mr-2" />
                  <span className="text-xs">Starting workflow...</span>
                </div>
              </div>
            )}

            {error && (
              <div className="card border-red-200 bg-red-50">
                <div className="flex items-center gap-2 mb-2">
                  <AlertCircle size={14} className="text-red-500" />
                  <h4 className="text-xs font-semibold text-red-700 uppercase">Error</h4>
                </div>
                <p className="text-xs text-red-600">{error}</p>
              </div>
            )}

            {status === 'completed' && result && (
              <div className="card border-green-200 bg-green-50">
                <div className="flex items-center gap-2 mb-2">
                  <CheckCircle size={14} className="text-green-500" />
                  <h4 className="text-xs font-semibold text-green-700 uppercase">Final State</h4>
                </div>
                <pre className="text-[11px] bg-white p-2 rounded border border-green-200 overflow-auto max-h-40 text-slate-600">
                  {JSON.stringify(result, null, 2)}
                </pre>
              </div>
            )}

            <div className="card">
              <h4 className="text-xs font-semibold text-slate-600 uppercase tracking-wider mb-2">Event Summary</h4>
              <div className="space-y-1.5">
                {(['sms', 'email', 'voice', 'dialer', 'system'] as const).map(ch => {
                  const count = events.filter(e => e.channel === ch).length
                  if (count === 0) return null
                  return (
                    <div key={ch} className="flex items-center gap-2">
                      <div className={`w-2 h-2 rounded-full ${channelColor(ch)}`} />
                      <span className="text-xs text-slate-600 capitalize">{ch}</span>
                      <span className="text-xs font-bold text-slate-800 ml-auto">{count}</span>
                    </div>
                  )
                })}
                {events.filter(e => e.source_service?.includes('ai-agent')).length > 0 && (
                  <div className="flex items-center gap-2">
                    <Brain size={10} className="text-purple-500" />
                    <span className="text-xs text-purple-600">AI Reasoning</span>
                    <span className="text-xs font-bold text-purple-800 ml-auto">
                      {events.filter(e => e.source_service?.includes('ai-agent')).length}
                    </span>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
