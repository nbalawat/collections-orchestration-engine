import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { formatDateTime } from '@/lib/utils'
import { Cog, Play, RefreshCw } from 'lucide-react'

const SAMPLE_INPUTS = [
  { label: 'Early Delinquent (45 DPD)', input: { days_past_due: 45, current_balance: 15000, risk_score: 60, prior_delinquencies: 1, prior_cures: 0, journey_stage: 'DUNNING', channel_history: [], prior_treatments: [], compliance_flags: [] } },
  { label: 'Severe (120 DPD)', input: { days_past_due: 120, current_balance: 42000, risk_score: 85, prior_delinquencies: 3, prior_cures: 1, journey_stage: 'DUNNING', channel_history: ['sms', 'voice'], prior_treatments: ['payment_reminder'], compliance_flags: [] } },
  { label: 'Bankruptcy Filed', input: { days_past_due: 60, current_balance: 28000, risk_score: 70, prior_delinquencies: 2, prior_cures: 0, journey_stage: 'SUSPENDED', channel_history: ['sms'], prior_treatments: [], compliance_flags: ['BANKRUPTCY'] } },
  { label: 'High-Value Customer', input: { days_past_due: 30, current_balance: 85000, risk_score: 30, prior_delinquencies: 0, prior_cures: 0, journey_stage: 'DUNNING', channel_history: [], prior_treatments: [], compliance_flags: [] } },
]

export default function StrategyConsole() {
  const [selectedSample, setSelectedSample] = useState(0)
  const [inputJson, setInputJson] = useState(JSON.stringify(SAMPLE_INPUTS[0].input, null, 2))

  const { data: auditLog, refetch: refetchAudit } = useQuery({
    queryKey: ['audit-log'],
    queryFn: api.getAuditLog,
  })

  const evaluateMutation = useMutation({
    mutationFn: () => api.evaluateFull(JSON.parse(inputJson)),
  })

  const selectSample = (idx: number) => {
    setSelectedSample(idx)
    setInputJson(JSON.stringify(SAMPLE_INPUTS[idx].input, null, 2))
  }

  return (
    <div className="p-6 space-y-6 flex-1 overflow-y-auto overflow-x-hidden min-w-0">
      <div className="flex items-center gap-3">
        <Cog size={24} className="text-slate-600" />
        <h2 className="text-xl font-bold text-slate-800">Strategy Console</h2>
      </div>

      <div className="grid grid-cols-2 gap-6">
        {/* Left: Strategy Evaluator */}
        <div className="space-y-4">
          <div className="card">
            <h3 className="text-sm font-semibold text-slate-700 mb-3">Strategy Evaluator</h3>
            <div className="flex gap-2 mb-3 flex-wrap">
              {SAMPLE_INPUTS.map((s, i) => (
                <button
                  key={i}
                  className={`btn btn-sm ${i === selectedSample ? 'btn-primary' : 'btn-outline'}`}
                  onClick={() => selectSample(i)}
                >
                  {s.label}
                </button>
              ))}
            </div>
            <textarea
              className="w-full h-48 px-3 py-2 border border-slate-300 rounded-lg text-xs font-mono"
              value={inputJson}
              onChange={(e) => setInputJson(e.target.value)}
            />
            <button
              className="btn btn-primary mt-2"
              onClick={() => evaluateMutation.mutate()}
              disabled={evaluateMutation.isPending}
            >
              <Play size={14} /> Evaluate All Policies
            </button>
          </div>

          {/* Evaluation Results */}
          {evaluateMutation.data && (
            <div className="space-y-3">
              {Object.entries(evaluateMutation.data).map(([policy, result]) => (
                <div key={policy} className="card">
                  <h4 className="text-sm font-semibold text-slate-700 mb-2 capitalize">{policy.replace('_', ' ')}</h4>
                  <pre className="text-xs bg-slate-50 p-3 rounded-lg overflow-auto max-h-48 font-mono">
                    {JSON.stringify(result, null, 2)}
                  </pre>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Right: Audit Log */}
        <div className="card">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-slate-700">Strategy Audit Log</h3>
            <button className="btn btn-outline btn-sm" onClick={() => refetchAudit()}>
              <RefreshCw size={12} /> Refresh
            </button>
          </div>
          {auditLog?.audit_log?.length === 0 ? (
            <p className="text-sm text-slate-400 text-center py-8">No audit entries yet</p>
          ) : (
            <div className="space-y-2 max-h-[600px] overflow-auto">
              {auditLog?.audit_log?.map((entry, i) => (
                <div key={i} className="p-3 bg-slate-50 rounded-lg text-xs">
                  <div className="flex justify-between mb-1">
                    <span className="font-semibold">{entry.change_type}</span>
                    <span className="text-slate-400">{formatDateTime(entry.created_at)}</span>
                  </div>
                  <div className="text-slate-600">{entry.change_reason}</div>
                  <div className="text-slate-400 mt-1">By: {entry.changed_by} | Version: {entry.strategy_version}</div>
                  {entry.change_details && (
                    <pre className="mt-1 text-xs text-slate-500 bg-white p-2 rounded">
                      {typeof entry.change_details === 'string' ? entry.change_details : JSON.stringify(entry.change_details, null, 2)}
                    </pre>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
