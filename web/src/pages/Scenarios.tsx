import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { Play, CheckCircle, Loader, AlertCircle } from 'lucide-react'

export default function Scenarios() {
  const { data: scenariosData } = useQuery({ queryKey: ['scenarios'], queryFn: api.listScenarios })
  const [runResults, setRunResults] = useState<Record<string, { status: string; result?: unknown; error?: string }>>({})

  const runMutation = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Record<string, unknown> }) => api.runScenario(id, body),
    onMutate: ({ id }) => {
      setRunResults((prev) => ({ ...prev, [id]: { status: 'running' } }))
    },
    onSuccess: (data, { id }) => {
      setRunResults((prev) => ({ ...prev, [id]: { status: 'completed', result: data.result } }))
    },
    onError: (error, { id }) => {
      setRunResults((prev) => ({ ...prev, [id]: { status: 'error', error: String(error) } }))
    },
  })

  const scenarios = scenariosData?.scenarios ?? []

  return (
    <div className="p-6 space-y-6 flex-1 overflow-y-auto overflow-x-hidden min-w-0">
      <div className="flex items-center gap-3">
        <Play size={24} className="text-green-600" />
        <h2 className="text-xl font-bold text-slate-800">Demo Scenarios</h2>
      </div>
      <p className="text-sm text-slate-500 max-w-3xl">
        Pre-scripted scenarios that drive realistic collections journeys through the orchestration engine.
        Each scenario generates events across channels, triggers workflow state transitions, and exercises AI agents.
      </p>

      <div className="grid grid-cols-2 gap-4 min-w-0">
        {scenarios.map((s) => {
          const result = runResults[s.id]
          return (
            <div key={s.id} className="card min-w-0 overflow-hidden">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <h3 className="font-semibold text-slate-800">{s.name}</h3>
                  <p className="text-sm text-slate-500 mt-1">{s.description}</p>
                  {s.default_customer && (
                    <p className="text-xs text-slate-400 mt-1 font-mono">Default: {s.default_customer}</p>
                  )}
                </div>
                <button
                  className="btn btn-primary btn-sm shrink-0"
                  onClick={() => runMutation.mutate({ id: s.id, body: { customer_id: s.default_customer } })}
                  disabled={result?.status === 'running'}
                >
                  {result?.status === 'running' ? (
                    <><Loader size={14} className="animate-spin" /> Running...</>
                  ) : (
                    <><Play size={14} /> Run</>
                  )}
                </button>
              </div>

              {result?.status === 'completed' && (
                <div className="mt-3 p-3 bg-green-50 rounded-lg">
                  <div className="flex items-center gap-2 text-sm text-green-700 font-medium">
                    <CheckCircle size={14} /> Completed
                  </div>
                  <pre className="text-xs mt-2 text-green-600 overflow-auto max-h-32">
                    {JSON.stringify(result.result, null, 2)}
                  </pre>
                </div>
              )}

              {result?.status === 'error' && (
                <div className="mt-3 p-3 bg-red-50 rounded-lg">
                  <div className="flex items-center gap-2 text-sm text-red-700 font-medium">
                    <AlertCircle size={14} /> Failed
                  </div>
                  <p className="text-xs mt-1 text-red-600">{result.error}</p>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
