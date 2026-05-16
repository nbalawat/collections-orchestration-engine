import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api } from '@/lib/api'
import type { AgentResult, ReasoningStep, AgentAction, AgentSummary } from '@/lib/api'
import { Markdown } from '@/components/Markdown'
import { formatTime } from '@/lib/utils'
import {
  Brain, Play, ChevronDown, ChevronRight, Clock, Zap,
  AlertCircle, CheckCircle, Workflow, User, Activity,
} from 'lucide-react'

const AGENT_CONFIGS = [
  {
    id: 'digital_channel',
    name: 'Digital Channel Agent',
    role: 'autonomous',
    description: 'Autonomous customer-facing agent for SMS/chat/web. Auto-fires inside the orchestrator on inbound HARDSHIP/DISPUTE/PTP/DISTRESS messages.',
    invoke: (body: Record<string, unknown>) => api.invokeDigitalChannel(body as { customer_id: string; message: string }),
    defaultBody: { customer_id: 'CUST-0032', message: "I lost my job and can't make payments. Can you help?" },
    fields: ['customer_id', 'message'],
  },
  {
    id: 'copilot',
    name: 'Agent Copilot',
    role: 'advisory',
    description: "Sits alongside human collectors during live calls. Never acts directly — surfaces context, suggestions, and pre-fills forms.",
    invoke: (body: Record<string, unknown>) => api.invokeCopilot(body),
    defaultBody: { customer_id: 'CUST-0055', request_type: 'nba', channel: 'voice' },
    fields: ['customer_id', 'request_type', 'channel'],
  },
  {
    id: 'case_reasoning',
    name: 'Case Reasoning Agent',
    role: 'on_demand',
    description: 'Deep multi-step analysis for complex or escalated cases. Compares treatment paths, models outcomes, writes a recommendation with rationale.',
    invoke: (body: Record<string, unknown>) => api.invokeCaseReasoning(body),
    defaultBody: { customer_id: 'CUST-0120', reason: 'Conflicting signals - new job but cannot pay full amount' },
    fields: ['customer_id', 'reason'],
  },
  {
    id: 'portfolio',
    name: 'Portfolio Intelligence',
    role: 'on_demand',
    description: 'Aggregate analytics across the book. Cohort comparisons, strategy effectiveness, audit-log review.',
    invoke: (body: Record<string, unknown>) => api.invokePortfolio(body),
    defaultBody: { analysis_type: 'portfolio_health' },
    fields: ['analysis_type', 'question'],
  },
  {
    id: 'quality',
    name: 'Quality & Compliance',
    role: 'autonomous',
    description: 'Reviews interactions for FDCPA / Reg F compliance and quality. Auto-fires inside the orchestrator on completed voice calls.',
    invoke: (body: Record<string, unknown>) => api.invokeQuality(body),
    defaultBody: { customer_id: 'CUST-0032', interaction_id: 'latest', channel: 'voice', review_type: 'full' },
    fields: ['customer_id', 'interaction_id', 'channel', 'review_type'],
  },
]

function RoleBadge({ role }: { role: string }) {
  if (role === 'autonomous') return (
    <span className="badge badge-green text-[10px] flex items-center gap-1">
      <Workflow size={10} /> in orchestrator
    </span>
  )
  if (role === 'advisory') return (
    <span className="badge badge-blue text-[10px] flex items-center gap-1">
      <User size={10} /> advises human
    </span>
  )
  return (
    <span className="badge badge-gray text-[10px] flex items-center gap-1">
      <Play size={10} /> on-demand
    </span>
  )
}

function LiveAgentPanel() {
  const { data: summary } = useQuery({
    queryKey: ['ai-explorer-agent-summary'],
    queryFn: api.opsAgentSummary,
    refetchInterval: 6000,
  })
  const { data: recent } = useQuery({
    queryKey: ['ai-explorer-agent-activity'],
    queryFn: () => api.opsAgentActivity(15),
    refetchInterval: 5000,
  })

  return (
    <div className="card border-emerald-200 bg-gradient-to-br from-emerald-50/50 to-white">
      <div className="flex items-center gap-2 mb-3">
        <Workflow size={16} className="text-emerald-600" />
        <h3 className="text-sm font-bold text-slate-800">Live AI activity inside the orchestrator</h3>
        <span className="text-[11px] text-slate-500 ml-1">— auto-fired by the workflow, not by humans</span>
      </div>

      {(summary?.agents ?? []).length === 0 ? (
        <p className="text-sm text-slate-400">No agent activity yet.</p>
      ) : (
        <>
          <div className="grid grid-cols-4 gap-2 mb-3">
            {(summary?.agents ?? []).map((s: AgentSummary) => (
              <div key={s.agent_type} className="bg-white border border-slate-200 rounded-lg p-2.5">
                <div className="text-xs font-bold text-slate-700">{s.agent_type.replace(/_/g, ' ')}</div>
                <div className="text-xl font-bold text-slate-800 mt-1">{s.actions_24h}</div>
                <div className="text-[10px] text-slate-500">actions 24h · {s.actions_5m} in 5m</div>
                <div className="flex justify-between text-[10px] mt-1">
                  <span className={s.escalations_24h > 0 ? 'text-amber-600' : 'text-slate-500'}>
                    escalated: {s.escalations_24h}
                  </span>
                  <span className="text-slate-600">
                    avg conf {((s.avg_confidence ?? 0) * 100).toFixed(0)}%
                  </span>
                </div>
              </div>
            ))}
          </div>

          <div className="bg-white border border-slate-200 rounded-lg max-h-72 overflow-y-auto">
            {(recent?.actions ?? []).map((a: AgentAction) => (
              <Link key={a.action_id} to={`/customer/${a.customer_id}`}
                    className="block border-b last:border-b-0 border-slate-100 px-3 py-2 hover:bg-slate-50">
                <div className="flex items-center gap-2 text-xs">
                  <Brain size={11} className={a.status === 'escalated' ? 'text-amber-500' : 'text-purple-500'} />
                  <span className="font-semibold text-slate-700">{a.agent_type.replace(/_/g, ' ')}</span>
                  <span className="text-slate-500">→</span>
                  <span className="font-medium text-slate-800">{a.action_type.replace(/_/g, ' ')}</span>
                  <span className={`badge text-[10px] ml-auto ${
                    (a.confidence ?? 0) > 0.8 ? 'badge-green' :
                    (a.confidence ?? 0) > 0.5 ? 'badge-yellow' : 'badge-red'
                  }`}>{((a.confidence ?? 0) * 100).toFixed(0)}%</span>
                  <span className="text-[10px] text-slate-400">{formatTime(a.created_at)}</span>
                </div>
                {a.rationale && (
                  <div className="text-[11px] text-slate-500 mt-1 pl-4 line-clamp-2">
                    <Markdown variant="note">{a.rationale}</Markdown>
                  </div>
                )}
              </Link>
            ))}
            {(recent?.actions ?? []).length === 0 && (
              <p className="p-4 text-sm text-slate-400">Waiting for agent actions…</p>
            )}
          </div>
        </>
      )}
    </div>
  )
}

export default function AIExplorer() {
  const [selectedAgent, setSelectedAgent] = useState(AGENT_CONFIGS[0])
  const [inputs, setInputs] = useState<Record<string, string>>(
    Object.fromEntries(Object.entries(AGENT_CONFIGS[0].defaultBody).map(([k, v]) => [k, String(v)])),
  )
  const [results, setResults] = useState<AgentResult[]>([])
  const [expandedTrace, setExpandedTrace] = useState<number | null>(null)

  const mutation = useMutation({
    mutationFn: () => selectedAgent.invoke(inputs),
    onSuccess: (result) => {
      setResults((prev) => [result, ...prev])
      setExpandedTrace(0)
    },
  })

  const selectAgent = (agent: typeof AGENT_CONFIGS[0]) => {
    setSelectedAgent(agent)
    setInputs(Object.fromEntries(Object.entries(agent.defaultBody).map(([k, v]) => [k, String(v)])))
  }

  return (
    <div className="p-6 space-y-6 flex-1 overflow-y-auto overflow-x-hidden min-w-0">
      <div className="flex items-center gap-3">
        <Brain size={24} className="text-purple-600" />
        <h2 className="text-xl font-bold text-slate-800">AI in the Collections Engine</h2>
      </div>

      <p className="text-sm text-slate-600 max-w-3xl">
        The platform uses five Claude-powered agents. Two of them <b>auto-fire inside the
        orchestrator</b> on real customer events (digital channel + quality compliance); two are
        <b> on-demand</b> tools for case investigation and portfolio analysis; one is a
        <b> live copilot</b> that sits next to human collectors. Every invocation is logged,
        every decision is persisted with structured action + confidence + rationale.
      </p>

      <LiveAgentPanel />

      <div>
        <div className="flex items-center gap-2 mb-2">
          <Play size={14} className="text-slate-500" />
          <h3 className="text-sm font-bold text-slate-700">Invoke an agent yourself</h3>
        </div>
        <div className="grid grid-cols-3 gap-3">
          {AGENT_CONFIGS.map((agent) => (
            <button
              key={agent.id}
              onClick={() => selectAgent(agent)}
              className={`card text-left transition-all ${
                selectedAgent.id === agent.id ? 'ring-2 ring-purple-500 bg-purple-50' : 'hover:border-purple-300'
              }`}
            >
              <div className="flex items-center justify-between gap-2 mb-1">
                <div className="text-sm font-semibold text-slate-800">{agent.name}</div>
                <RoleBadge role={agent.role} />
              </div>
              <div className="text-xs text-slate-500">{agent.description}</div>
            </button>
          ))}
        </div>
      </div>

      <div className="card">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-slate-700">{selectedAgent.name} — Input</h3>
          <button
            className="btn btn-primary btn-sm"
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending}
          >
            {mutation.isPending ? (
              <><Clock size={14} className="animate-spin" /> Running real Claude call…</>
            ) : (
              <><Play size={14} /> Invoke agent</>
            )}
          </button>
        </div>
        <div className="grid grid-cols-2 gap-3">
          {selectedAgent.fields.map((field) => (
            <div key={field}>
              <label className="text-xs font-medium text-slate-500 block mb-1">{field}</label>
              <input
                className="w-full px-3 py-1.5 border border-slate-300 rounded-lg text-sm"
                value={inputs[field] || ''}
                onChange={(e) => setInputs({ ...inputs, [field]: e.target.value })}
              />
            </div>
          ))}
        </div>
      </div>

      {results.map((result, i) => (
        <div key={i} className="card">
          <div
            className="flex items-center justify-between cursor-pointer"
            onClick={() => setExpandedTrace(expandedTrace === i ? null : i)}
          >
            <div className="flex items-center gap-3">
              {expandedTrace === i ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
              <span className="text-sm font-semibold text-slate-700">
                {result.reasoning_trace?.agent_type || selectedAgent.id}
              </span>
              {result.action_taken && <span className="badge badge-blue">{result.action_taken}</span>}
              {result.escalated && <span className="badge badge-red flex items-center gap-1"><AlertCircle size={10} /> escalated</span>}
              {!result.escalated && result.confidence && result.confidence > 0.7 && (
                <span className="badge badge-green flex items-center gap-1"><CheckCircle size={10} /> {(result.confidence * 100).toFixed(0)}%</span>
              )}
            </div>
            <div className="flex items-center gap-4 text-xs text-slate-500">
              {result.tokens_used && <span><Zap size={12} className="inline" /> {result.tokens_used} tokens</span>}
              {result.latency_ms && <span><Clock size={12} className="inline" /> {result.latency_ms}ms</span>}
            </div>
          </div>

          {expandedTrace === i && (
            <div className="mt-4 space-y-4">
              {(result as { rationale?: string }).rationale && (
                <div>
                  <h4 className="text-xs font-semibold text-slate-500 uppercase mb-2">Recorded decision rationale</h4>
                  <div className="p-3 bg-purple-50 border border-purple-200 rounded-lg">
                    <Markdown variant="narrative">{(result as { rationale?: string }).rationale ?? ''}</Markdown>
                  </div>
                </div>
              )}

              {result.reasoning_trace?.reasoning_steps && (
                <div>
                  <h4 className="text-xs font-semibold text-slate-500 uppercase mb-2">
                    Reasoning steps <span className="ml-1 text-slate-400">({result.reasoning_trace.reasoning_steps.length})</span>
                  </h4>
                  <div className="space-y-1 max-h-96 overflow-auto">
                    {result.reasoning_trace.reasoning_steps.map((step: ReasoningStep, j: number) => (
                      <div key={j} className="flex gap-3 text-xs p-2 bg-slate-50 rounded">
                        <span className="font-mono text-purple-600 whitespace-nowrap min-w-32">{step.step}</span>
                        <span className="text-slate-600 break-all">{step.result.slice(0, 300)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {result.response_text && (
                <div>
                  <h4 className="text-xs font-semibold text-slate-500 uppercase mb-2">Agent response</h4>
                  <div className="p-3 bg-white border border-slate-200 rounded-lg max-h-96 overflow-auto">
                    <Markdown variant="narrative">{result.response_text}</Markdown>
                  </div>
                </div>
              )}

              {result.error && (
                <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
                  Error: {result.error}
                </div>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}
