import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type {} from '@/lib/api'
import { formatCurrency, stageBadgeColor } from '@/lib/utils'
import { Search, Send, Bot, User, AlertCircle, Clock, Zap } from 'lucide-react'

export default function AgentDesktop() {
  const [customerId, setCustomerId] = useState('CUST-0032')
  const [searchInput, setSearchInput] = useState('CUST-0032')
  const [message, setMessage] = useState('')
  const [conversation, setConversation] = useState<ChatMessage[]>([])

  const { data: customer, isLoading } = useQuery({
    queryKey: ['customer360', customerId],
    queryFn: () => api.getCustomer360(customerId),
    enabled: !!customerId,
  })

  const digitalAgent = useMutation({
    mutationFn: (msg: string) => api.invokeDigitalChannel({ customer_id: customerId, message: msg }),
    onSuccess: (result) => {
      setConversation((prev) => [
        ...prev,
        {
          role: 'assistant',
          text: result.response_text || 'No response',
          action: result.action_taken,
          confidence: result.confidence,
          tokens: result.tokens_used,
          latency: result.latency_ms,
          escalated: result.escalated,
          trace: result.reasoning_trace as unknown as Record<string, unknown> | undefined,
        },
      ])
    },
  })

  const copilot = useMutation({
    mutationFn: () => api.invokeCopilot({ customer_id: customerId, request_type: 'nba', channel: 'digital' }),
  })

  const handleSend = () => {
    if (!message.trim()) return
    setConversation((prev) => [...prev, { role: 'user', text: message }])
    digitalAgent.mutate(message)
    setMessage('')
  }

  const profile = customer?.profile as Record<string, unknown> | undefined
  const accounts = customer?.accounts ?? []
  const flags = customer?.compliance_flags ?? []

  return (
    <div className="flex flex-1 min-h-0">
      {/* Left: Customer Panel */}
      <div className="w-80 border-r border-slate-200 bg-white flex flex-col shrink-0">
        <div className="p-4 border-b border-slate-200">
          <div className="flex gap-2">
            <input
              className="flex-1 px-3 py-1.5 border border-slate-300 rounded-lg text-sm"
              placeholder="Customer ID..."
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && setCustomerId(searchInput)}
            />
            <button className="btn btn-primary btn-sm" onClick={() => setCustomerId(searchInput)}>
              <Search size={14} />
            </button>
          </div>
        </div>

        {isLoading && <p className="p-4 text-sm text-slate-400">Loading...</p>}

        {profile && (
          <div className="flex-1 overflow-auto p-4 space-y-4">
            <div>
              <h3 className="font-bold text-slate-800">
                {String(profile.first_name)} {String(profile.last_name)}
              </h3>
              <p className="text-xs text-slate-500">{customerId}</p>
            </div>

            <div className="space-y-1 text-sm">
              <Row label="Email" value={String(profile.email || '-')} />
              <Row label="Phone" value={String(profile.phone_primary || '-')} />
              <Row label="Channel" value={String(profile.preferred_channel || '-')} />
              <Row label="Risk Score" value={String(profile.risk_score || '-')} />
              <Row label="Relationship" value={String(profile.relationship_value || '-')} />
            </div>

            {flags.length > 0 && (
              <div>
                <h4 className="text-xs font-semibold text-red-600 uppercase mb-1">Compliance Flags</h4>
                {flags.map((f, i) => (
                  <div key={i} className="badge badge-red text-xs mb-1">{String((f as Record<string, unknown>).flag_type)}</div>
                ))}
              </div>
            )}

            <div>
              <h4 className="text-xs font-semibold text-slate-500 uppercase mb-2">Accounts</h4>
              {accounts.map((a, i) => {
                const acct = a as Record<string, unknown>
                return (
                  <div key={i} className="p-2 bg-slate-50 rounded-lg mb-2 text-xs space-y-1">
                    <div className="flex justify-between">
                      <span className="font-mono">{String(acct.account_id).slice(-8)}</span>
                      <span className={`badge ${stageBadgeColor(String(acct.delinquency_stage))}`}>
                        {String(acct.delinquency_stage)}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span>Balance: {formatCurrency(Number(acct.current_balance))}</span>
                      <span>{Number(acct.days_past_due)} DPD</span>
                    </div>
                    <div className="text-slate-400">Past Due: {formatCurrency(Number(acct.total_past_due))}</div>
                  </div>
                )
              })}
            </div>

            <button className="btn btn-outline w-full text-xs" onClick={() => copilot.mutate()} disabled={copilot.isPending}>
              <Zap size={14} /> {copilot.isPending ? 'Getting suggestions...' : 'Get AI Suggestions'}
            </button>

            {copilot.data && (
              <div className="p-3 bg-purple-50 rounded-lg text-xs whitespace-pre-wrap">
                {copilot.data.response_text}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Right: Chat */}
      <div className="flex-1 flex flex-col">
        <div className="p-4 border-b border-slate-200 bg-white flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Bot size={18} className="text-blue-600" />
            <span className="font-semibold text-sm">Digital Channel Agent</span>
            <span className="badge badge-blue">claude-sonnet-4-6</span>
          </div>
          {digitalAgent.isPending && (
            <span className="text-xs text-slate-400 flex items-center gap-1">
              <Clock size={12} className="animate-spin" /> Thinking...
            </span>
          )}
        </div>

        <div className="flex-1 overflow-auto p-4 space-y-4">
          {conversation.length === 0 && (
            <p className="text-center text-sm text-slate-400 mt-20">
              Send a message as a customer to start the interaction
            </p>
          )}
          {conversation.map((msg, i) => (
            <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div className={`max-w-lg ${msg.role === 'user' ? 'bg-blue-600 text-white' : 'bg-white border border-slate-200'} rounded-xl px-4 py-3`}>
                <div className="flex items-center gap-2 mb-1">
                  {msg.role === 'user' ? <User size={14} /> : <Bot size={14} className="text-blue-600" />}
                  <span className="text-xs font-medium">{msg.role === 'user' ? 'Customer' : 'AI Agent'}</span>
                </div>
                <p className="text-sm whitespace-pre-wrap">{msg.text}</p>
                {msg.role === 'assistant' && (
                  <div className="mt-2 pt-2 border-t border-slate-100 flex flex-wrap gap-2 text-xs text-slate-500">
                    {msg.action && <span className="badge badge-blue">{msg.action}</span>}
                    {msg.confidence != null && <span>Conf: {(msg.confidence * 100).toFixed(0)}%</span>}
                    {msg.escalated && <span className="badge badge-red flex items-center gap-1"><AlertCircle size={10} /> Escalated</span>}
                    {msg.tokens != null && <span>{msg.tokens} tokens</span>}
                    {msg.latency != null && <span>{msg.latency}ms</span>}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>

        <div className="p-4 border-t border-slate-200 bg-white">
          <div className="flex gap-2">
            <input
              className="flex-1 px-4 py-2 border border-slate-300 rounded-lg text-sm"
              placeholder="Type a customer message..."
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSend()}
              disabled={digitalAgent.isPending}
            />
            <button className="btn btn-primary" onClick={handleSend} disabled={digitalAgent.isPending}>
              <Send size={16} /> Send
            </button>
          </div>
          <div className="flex gap-2 mt-2">
            {['I lost my job, can we work something out?', "What's my balance?", 'I can pay $500 by Friday', 'I want to settle for less'].map(
              (q) => (
                <button key={q} className="btn btn-outline btn-sm text-xs" onClick={() => setMessage(q)}>
                  {q.slice(0, 30)}...
                </button>
              ),
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between">
      <span className="text-slate-500">{label}</span>
      <span className="font-medium text-slate-700">{value}</span>
    </div>
  )
}

interface ChatMessage {
  role: 'user' | 'assistant'
  text: string
  action?: string | null
  confidence?: number | null
  tokens?: number | null
  latency?: number | null
  escalated?: boolean
  trace?: Record<string, unknown> | undefined
}

