import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { AgentResult, ReasoningStep } from '@/lib/api'
import { Brain, Play, ChevronDown, ChevronRight, Clock, Zap, AlertCircle, CheckCircle } from 'lucide-react'

const AGENT_CONFIGS = [
  {
    id: 'digital_channel',
    name: 'Digital Channel Agent',
    description: 'Autonomous customer-facing agent for SMS/chat/web',
    invoke: (body: Record<string, unknown>) => api.invokeDigitalChannel(body as { customer_id: string; message: string }),
    defaultBody: { customer_id: 'CUST-0032', message: "I lost my job and can't make payments. Can you help?" },
    fields: ['customer_id', 'message'],
  },
  {
    id: 'copilot',
    name: 'Agent Copilot',
    description: 'Real-time AI assistant for human agents',
    invoke: (body: Record<string, unknown>) => api.invokeCopilot(body),
    defaultBody: { customer_id: 'CUST-0055', request_type: 'nba', channel: 'voice' },
    fields: ['customer_id', 'request_type', 'channel'],
  },
  {
    id: 'case_reasoning',
    name: 'Case Reasoning Agent',
    description: 'Deep analysis for complex or escalated cases',
    invoke: (body: Record<string, unknown>) => api.invokeCaseReasoning(body),
    defaultBody: { customer_id: 'CUST-0120', reason: 'Conflicting signals - new job but cannot pay full amount' },
    fields: ['customer_id', 'reason'],
  },
  {
    id: 'portfolio',
    name: 'Portfolio Intelligence',
    description: 'Analytics and strategy optimization across the book',
    invoke: (body: Record<string, unknown>) => api.invokePortfolio(body),
    defaultBody: { analysis_type: 'portfolio_health' },
    fields: ['analysis_type', 'question'],
  },
  {
    id: 'quality',
    name: 'Quality & Compliance',
    description: 'Reviews interactions for quality and regulatory compliance',
    invoke: (body: Record<string, unknown>) => api.invokeQuality(body),
    defaultBody: { customer_id: 'CUST-0032', interaction_id: 'latest', channel: 'voice', review_type: 'full' },
    fields: ['customer_id', 'interaction_id', 'channel', 'review_type'],
  },
]

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
        <h2 className="text-xl font-bold text-slate-800">AI Reasoning Explorer</h2>
      </div>

      {/* Agent Selector */}
      <div className="grid grid-cols-3 gap-3">
        {AGENT_CONFIGS.map((agent) => (
          <button
            key={agent.id}
            onClick={() => selectAgent(agent)}
            className={`card text-left transition-all ${
              selectedAgent.id === agent.id ? 'ring-2 ring-purple-500 bg-purple-50' : 'hover:border-purple-300'
            }`}
          >
            <div className="text-sm font-semibold text-slate-800">{agent.name}</div>
            <div className="text-xs text-slate-500 mt-1">{agent.description}</div>
          </button>
        ))}
      </div>

      {/* Input Form */}
      <div className="card">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-slate-700">{selectedAgent.name} — Input</h3>
          <button
            className="btn btn-primary btn-sm"
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending}
          >
            {mutation.isPending ? (
              <><Clock size={14} className="animate-spin" /> Running...</>
            ) : (
              <><Play size={14} /> Invoke Agent</>
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

      {/* Results */}
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
              {result.escalated && <span className="badge badge-red flex items-center gap-1"><AlertCircle size={10} /> Escalated</span>}
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
              {/* Reasoning Steps */}
              {result.reasoning_trace?.reasoning_steps && (
                <div>
                  <h4 className="text-xs font-semibold text-slate-500 uppercase mb-2">Reasoning Steps</h4>
                  <div className="space-y-1">
                    {result.reasoning_trace.reasoning_steps.map((step: ReasoningStep, j: number) => (
                      <div key={j} className="flex gap-3 text-xs p-2 bg-slate-50 rounded">
                        <span className="font-mono text-purple-600 whitespace-nowrap min-w-32">{step.step}</span>
                        <span className="text-slate-600 break-all">{step.result.slice(0, 200)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Response Text */}
              {result.response_text && (
                <div>
                  <h4 className="text-xs font-semibold text-slate-500 uppercase mb-2">Agent Response</h4>
                  <div className="p-3 bg-white border border-slate-200 rounded-lg text-sm whitespace-pre-wrap max-h-96 overflow-auto">
                    {result.response_text}
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
