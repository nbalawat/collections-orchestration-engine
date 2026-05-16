import { useState, useMemo } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api } from '@/lib/api'
import type {
  RiskModelCard, RiskScoreResponse, RollRateResponse,
  RecoveryCurvesResponse, CohortVintageCell, AbSignificanceResponse,
  AiCostResponse,
} from '@/lib/api'
import {
  Brain, Activity, TrendingUp, GitBranch, Target, Zap, DollarSign,
  Layers, RefreshCw, Play, ChevronDown, ChevronRight, Search,
  AlertTriangle, CheckCircle, Trophy,
} from 'lucide-react'
import { formatCurrency, formatNumber, formatTime } from '@/lib/utils'

function SectionHeader({ icon, title, subtitle, action }: {
  icon: React.ReactNode; title: string; subtitle?: string; action?: React.ReactNode
}) {
  return (
    <div className="flex items-start justify-between mb-3">
      <div className="flex items-start gap-3">
        <div className="mt-0.5">{icon}</div>
        <div>
          <h2 className="text-base font-bold text-slate-800">{title}</h2>
          {subtitle && <p className="text-xs text-slate-500 mt-0.5 max-w-2xl">{subtitle}</p>}
        </div>
      </div>
      {action}
    </div>
  )
}

// ── Story 1: Risk model card + feature importance ──

function ModelCardSection() {
  const { data, refetch } = useQuery({
    queryKey: ['risk-model-card'],
    queryFn: api.riskModelCard,
    refetchInterval: 30000,
  })
  const retrainMut = useMutation({
    mutationFn: api.riskRetrain,
    onSuccess: () => refetch(),
  })

  const m = data?.training_meta
  const isReal = data?.is_real
  const tone = isReal ? 'from-emerald-50 to-white border-emerald-200' : 'from-amber-50 to-white border-amber-200'

  const maxImp = useMemo(() => Math.max(0.001, ...(data?.feature_importance ?? []).map(f => f.importance)), [data])

  return (
    <section className={`bg-gradient-to-br border ${tone} rounded-xl p-5`}>
      <SectionHeader
        icon={<Brain size={20} className={isReal ? "text-emerald-600" : "text-amber-600"} />}
        title="Risk model · trained on real customer history"
        subtitle="GradientBoostingClassifier — predicts probability a customer's delinquency stage will worsen in the next forward window. Trained on stage_change events; label = stage worsened within lookahead window."
        action={
          <button
            className="btn btn-primary text-sm flex items-center gap-1.5"
            disabled={retrainMut.isPending}
            onClick={() => retrainMut.mutate()}
          >
            {retrainMut.isPending ? <><RefreshCw size={14} className="animate-spin" /> Retraining…</> : <><RefreshCw size={14} /> Retrain now</>}
          </button>
        }
      />

      <div className="grid grid-cols-6 gap-3 mb-4">
        <Stat label="Status" value={m?.status ?? '—'} highlight={isReal ? 'good' : 'warn'} />
        <Stat label="AUC" value={typeof m?.auc === 'number' ? m.auc.toFixed(3) : '—'} />
        <Stat label="Brier score" value={typeof m?.brier === 'number' ? m.brier.toFixed(3) : '—'} />
        <Stat label="Training rows" value={m?.snapshots ? formatNumber(m.snapshots) : '—'} />
        <Stat label="Positive rate" value={m?.positive_rate != null ? `${(m.positive_rate * 100).toFixed(1)}%` : '—'} />
        <Stat label="Features" value={data?.n_features ?? '—'} />
      </div>

      <div>
        <div className="text-xs font-bold text-slate-700 mb-2 flex items-center gap-1">
          <TrendingUp size={12} /> Feature importance (top 15)
        </div>
        <div className="space-y-1">
          {(data?.feature_importance ?? []).slice(0, 15).map((f, i) => (
            <div key={f.feature} className="grid grid-cols-[180px_1fr_60px] items-center gap-2 text-xs">
              <code className="text-slate-700 truncate">{f.feature}</code>
              <div className="bg-slate-100 rounded h-3 overflow-hidden">
                <div
                  className="h-3 bg-gradient-to-r from-indigo-400 to-indigo-600 rounded"
                  style={{ width: `${(f.importance / maxImp) * 100}%` }}
                />
              </div>
              <span className="text-slate-600 font-mono text-right">{f.importance.toFixed(4)}</span>
            </div>
          ))}
        </div>
      </div>

      {!isReal && (
        <div className="mt-3 bg-amber-100/60 border border-amber-300 rounded p-2 text-xs text-amber-900">
          Heuristic fallback in use: {String(m?.reason ?? 'no_training_data')}.
          Generate more activity, then click Retrain.
        </div>
      )}
    </section>
  )
}

function Stat({ label, value, highlight }: { label: string; value: React.ReactNode; highlight?: 'good' | 'warn' | 'bad' }) {
  const ring = highlight === 'good' ? 'border-emerald-300 bg-emerald-50' :
               highlight === 'warn' ? 'border-amber-300 bg-amber-50' :
               highlight === 'bad'  ? 'border-red-300 bg-red-50' :
               'border-slate-200 bg-white'
  return (
    <div className={`border rounded-lg p-2 ${ring}`}>
      <div className="text-[10px] uppercase tracking-wider text-slate-500">{label}</div>
      <div className="text-lg font-bold text-slate-800 truncate">{value}</div>
    </div>
  )
}

// ── Story 2: Score a customer + explainability ──

function ScoreSection() {
  const [cid, setCid] = useState('')
  const [submitted, setSubmitted] = useState<string | null>(null)
  const { data, isFetching, error } = useQuery({
    queryKey: ['risk-score', submitted],
    queryFn: () => api.riskScore(submitted!),
    enabled: !!submitted,
  })

  return (
    <section className="bg-white border border-slate-200 rounded-xl p-5">
      <SectionHeader
        icon={<Target size={20} className="text-indigo-600" />}
        title="Score a customer · feature-store demo"
        subtitle="Real-time scoring: pulls features from the feature store, runs the trained model, returns probability + top contributing features."
      />
      <div className="flex gap-2 mb-3 flex-wrap">
        <input
          className="flex-1 min-w-[200px] px-3 py-1.5 border border-slate-200 rounded font-mono text-xs"
          placeholder="CUST-0032 …"
          value={cid}
          onChange={(e) => setCid(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && cid.trim()) setSubmitted(cid.trim()) }}
        />
        <button
          className="btn btn-primary text-xs px-3 py-1.5 flex items-center gap-1"
          onClick={() => setSubmitted(cid.trim() || 'CUST-0032')}
          disabled={isFetching}
        >
          {isFetching ? <><RefreshCw size={11} className="animate-spin" /> scoring</> : <><Search size={11} /> score</>}
        </button>
        <button
          className="btn btn-outline text-xs px-3 py-1.5"
          onClick={() => { setCid('CUST-0032'); setSubmitted('CUST-0032') }}
        >try CUST-0032</button>
      </div>

      {error && <div className="bg-red-50 border border-red-200 rounded p-2 text-xs text-red-700">{String(error)}</div>}

      {data && (
        <div className="grid grid-cols-3 gap-3">
          <div className={`col-span-1 rounded-xl p-4 border-2 ${
            data.risk_band === 'HIGH' ? 'bg-red-50 border-red-300' :
            data.risk_band === 'MEDIUM' ? 'bg-amber-50 border-amber-300' :
            'bg-emerald-50 border-emerald-300'
          }`}>
            <div className="text-[10px] uppercase tracking-wider text-slate-500">Probability of stage worsening</div>
            <div className="text-5xl font-bold text-slate-800 mt-1">{(data.probability_worsen_7d * 100).toFixed(0)}<span className="text-2xl">%</span></div>
            <div className={`mt-2 text-sm font-bold ${
              data.risk_band === 'HIGH' ? 'text-red-700' :
              data.risk_band === 'MEDIUM' ? 'text-amber-700' : 'text-emerald-700'
            }`}>{data.risk_band} risk</div>
            <Link to={`/customer/${data.customer_id}`} className="text-xs text-indigo-600 hover:underline mt-3 inline-block">
              see customer story →
            </Link>
            <div className="text-[10px] text-slate-400 mt-2">model: {data.model_status}</div>
          </div>

          <div className="col-span-2 bg-white border border-slate-200 rounded-xl p-4">
            <div className="text-xs font-bold text-slate-700 mb-2">Top contributors to this score</div>
            <div className="space-y-1.5">
              {data.top_contributors.map((c, i) => (
                <div key={c.feature} className="grid grid-cols-[180px_60px_60px_1fr_50px] items-center gap-2 text-xs">
                  <code className="text-slate-700 truncate">{c.feature}</code>
                  <span className="text-slate-600 font-mono text-right">{c.value.toFixed(2)}</span>
                  <span className={`font-mono text-right ${c.z_score > 0 ? 'text-red-600' : 'text-emerald-600'}`}>
                    z={c.z_score > 0 ? '+' : ''}{c.z_score.toFixed(2)}
                  </span>
                  <div className="bg-slate-100 rounded h-3 overflow-hidden">
                    <div
                      className="h-3 bg-gradient-to-r from-indigo-400 to-indigo-600 rounded"
                      style={{ width: `${Math.min(100, c.local_contribution / 0.5 * 100)}%` }}
                    />
                  </div>
                  <span className="text-slate-500 font-mono text-right">{c.local_contribution.toFixed(3)}</span>
                </div>
              ))}
            </div>
            <div className="text-[10px] text-slate-400 mt-3">
              Local contribution ≈ |z-score of feature value| × global feature importance.
              Positive z-scores (red) push risk up; negative (green) pull it down.
            </div>
          </div>
        </div>
      )}
    </section>
  )
}

// ── Story 3: Roll-rate Markov forecast ──

function RollRateSection() {
  const { data } = useQuery({
    queryKey: ['risk-roll-rate'],
    queryFn: api.riskRollRate,
    refetchInterval: 30000,
  })

  const labels = data?.labels ?? []
  const matrix = data?.matrix ?? []
  const cs = data?.current_state ?? {}
  const p30 = data?.projections?.['30_day'] ?? {}
  const p60 = data?.projections?.['60_day'] ?? {}
  const p90 = data?.projections?.['90_day'] ?? {}

  const populatedStages = useMemo(() => {
    return labels.filter(l => (cs[l] ?? 0) > 0 || (p90[l] ?? 0) > 0)
  }, [labels, cs, p90])

  return (
    <section className="bg-white border border-slate-200 rounded-xl p-5">
      <SectionHeader
        icon={<GitBranch size={20} className="text-slate-700" />}
        title="Roll-rate forecast · Markov chain"
        subtitle="Empirical stage transition matrix built from every stage_change event, current portfolio state from journey history, projected forward 30/60/90 days. CURED and CHARGED_OFF are absorbing."
      />

      <div className="grid grid-cols-2 gap-6">
        <div>
          <h3 className="text-xs font-bold text-slate-700 mb-2">Portfolio projection</h3>
          <div className="bg-slate-50 border border-slate-200 rounded overflow-hidden">
            <table className="w-full text-xs">
              <thead className="bg-slate-100">
                <tr>
                  <th className="text-left px-2 py-1.5 text-[10px] uppercase tracking-wider text-slate-500">Stage</th>
                  <th className="text-right px-2 py-1.5 text-[10px] uppercase tracking-wider text-slate-500">Now</th>
                  <th className="text-right px-2 py-1.5 text-[10px] uppercase tracking-wider text-slate-500">30d</th>
                  <th className="text-right px-2 py-1.5 text-[10px] uppercase tracking-wider text-slate-500">60d</th>
                  <th className="text-right px-2 py-1.5 text-[10px] uppercase tracking-wider text-slate-500">90d</th>
                  <th className="text-right px-2 py-1.5 text-[10px] uppercase tracking-wider text-slate-500">Δ</th>
                </tr>
              </thead>
              <tbody>
                {populatedStages.map(s => {
                  const now = cs[s] ?? 0
                  const future = p90[s] ?? 0
                  const delta = future - now
                  return (
                    <tr key={s} className="border-t border-slate-100">
                      <td className="px-2 py-1.5 font-mono text-slate-700 text-[11px]">{s}</td>
                      <td className="text-right px-2 py-1.5 font-mono">{now}</td>
                      <td className="text-right px-2 py-1.5 font-mono text-slate-600">{(p30[s] ?? 0).toFixed(1)}</td>
                      <td className="text-right px-2 py-1.5 font-mono text-slate-600">{(p60[s] ?? 0).toFixed(1)}</td>
                      <td className="text-right px-2 py-1.5 font-mono text-slate-800">{(p90[s] ?? 0).toFixed(1)}</td>
                      <td className={`text-right px-2 py-1.5 font-mono ${delta > 0 ? 'text-red-600' : delta < 0 ? 'text-emerald-600' : 'text-slate-400'}`}>
                        {delta === 0 ? '·' : `${delta > 0 ? '+' : ''}${delta.toFixed(1)}`}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          <div className="text-[10px] text-slate-500 mt-2">
            current_total: {data?.current_total} · estimated transitions/day/customer: {data?.steps_per_period.daily_transition_rate}
          </div>
        </div>

        <div>
          <h3 className="text-xs font-bold text-slate-700 mb-2">Transition matrix heatmap</h3>
          <div className="overflow-auto max-h-80">
            <table className="text-[9px] border border-slate-200">
              <thead className="bg-slate-50">
                <tr>
                  <th className="px-1 py-1 sticky left-0 bg-slate-50">from \ to</th>
                  {populatedStages.map(s => (
                    <th key={s} className="px-1 py-1 text-slate-500 font-normal" style={{ writingMode: 'vertical-rl' }}>{s}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {populatedStages.map(from => {
                  const fromIdx = labels.indexOf(from)
                  return (
                    <tr key={from} className="border-t border-slate-100">
                      <td className="px-1 py-1 font-mono text-slate-600 sticky left-0 bg-white">{from}</td>
                      {populatedStages.map(to => {
                        const toIdx = labels.indexOf(to)
                        const p = matrix[fromIdx]?.[toIdx] ?? 0
                        return (
                          <td key={to} className="px-1 py-1 text-center font-mono"
                              style={{
                                backgroundColor: p > 0 ? `rgba(99, 102, 241, ${0.1 + p * 0.7})` : 'transparent',
                                color: p > 0.5 ? 'white' : 'rgb(30, 41, 59)',
                              }}>
                            {p === 0 ? '·' : (p * 100).toFixed(0)}
                          </td>
                        )
                      })}
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          <div className="text-[10px] text-slate-500 mt-2">Cell = P(from → to) as %.</div>
        </div>
      </div>
    </section>
  )
}

// ── Story 4: Champion vs Challenger statistical significance ──

function AbTestSection() {
  const [metric, setMetric] = useState<'cure' | 'escalation' | 'engagement'>('engagement')
  const { data } = useQuery({
    queryKey: ['risk-ab', metric],
    queryFn: () => api.riskAbSignificance(metric),
    refetchInterval: 20000,
  })

  const verdictTone =
    data?.verdict === 'challenger_wins' ? 'bg-emerald-50 border-emerald-300 text-emerald-900' :
    data?.verdict === 'champion_wins' ? 'bg-amber-50 border-amber-300 text-amber-900' :
    data?.verdict === 'insufficient_data' ? 'bg-slate-50 border-slate-300 text-slate-700' :
    'bg-blue-50 border-blue-300 text-blue-900'

  return (
    <section className="bg-white border border-slate-200 rounded-xl p-5">
      <SectionHeader
        icon={<Trophy size={20} className="text-amber-600" />}
        title="A/B significance · champion vs challenger"
        subtitle="Two-proportion z-test on real assignment + outcome data over the last 24 hours. Verdict = significant at α=0.05."
        action={
          <select
            value={metric}
            onChange={(e) => setMetric(e.target.value as 'cure' | 'escalation' | 'engagement')}
            className="text-xs border border-slate-200 rounded px-2 py-1 bg-white"
          >
            <option value="cure">cure rate</option>
            <option value="escalation">escalation rate</option>
            <option value="engagement">inbound engagement</option>
          </select>
        }
      />

      <div className={`border-2 rounded-lg p-4 mb-3 ${verdictTone}`}>
        <div className="text-xs uppercase tracking-wider opacity-70">Verdict</div>
        <div className="text-2xl font-bold mt-1 uppercase">{(data?.verdict ?? '—').replace(/_/g, ' ')}</div>
        {data?.lift_pct != null && (
          <div className="text-sm mt-1">
            Lift: <span className="font-bold">{data.lift_pct > 0 ? '+' : ''}{data.lift_pct.toFixed(1)}%</span>
            {data.p_value != null && <span className="ml-3">p-value: <span className="font-mono">{data.p_value.toFixed(3)}</span></span>}
            {data.z_score != null && <span className="ml-3">z: <span className="font-mono">{data.z_score.toFixed(2)}</span></span>}
          </div>
        )}
      </div>

      <div className="grid grid-cols-2 gap-3">
        {data && [data.champion, data.challenger].map((arm, i) => (
          <div key={i} className={`border rounded-lg p-3 ${i === 0 ? 'bg-amber-50 border-amber-200' : 'bg-indigo-50 border-indigo-200'}`}>
            <div className="flex items-center justify-between">
              <code className="text-sm font-bold text-slate-800">{arm?.version}</code>
              <span className={`badge text-[10px] ${i === 0 ? 'badge-yellow' : 'badge-blue'}`}>
                {i === 0 ? 'champion' : 'challenger'}
              </span>
            </div>
            <div className="grid grid-cols-3 gap-2 mt-3 text-center">
              <div className="bg-white/70 rounded p-2"><div className="text-[10px] text-slate-500">n</div><div className="text-lg font-bold">{arm?.n}</div></div>
              <div className="bg-white/70 rounded p-2"><div className="text-[10px] text-slate-500">conv</div><div className="text-lg font-bold">{arm?.conversions}</div></div>
              <div className="bg-white/70 rounded p-2"><div className="text-[10px] text-slate-500">rate</div><div className="text-lg font-bold">{arm?.rate != null ? `${(arm.rate * 100).toFixed(2)}%` : '—'}</div></div>
            </div>
          </div>
        ))}
      </div>

      {data?.difference_95_ci && (
        <div className="mt-3 grid grid-cols-2 gap-3 text-xs">
          <div className="bg-slate-50 border border-slate-200 rounded p-2">
            <div className="text-[10px] uppercase tracking-wider text-slate-500">95% CI on difference</div>
            <div className="font-mono text-slate-800">[{data.difference_95_ci[0].toFixed(4)}, {data.difference_95_ci[1].toFixed(4)}]</div>
          </div>
          <div className="bg-slate-50 border border-slate-200 rounded p-2">
            <div className="text-[10px] uppercase tracking-wider text-slate-500">Required n/arm for 5% lift @ 80% power</div>
            <div className="font-mono text-slate-800">
              {data.required_n_per_arm_for_5pct_lift_80pct_power
                ? formatNumber(data.required_n_per_arm_for_5pct_lift_80pct_power)
                : '—'}
            </div>
          </div>
        </div>
      )}
    </section>
  )
}

// ── Story 5: Recovery curves + cohort vintage ──

function RecoverySection() {
  const { data: rc } = useQuery({ queryKey: ['risk-recovery'], queryFn: api.riskRecoveryCurves, refetchInterval: 30000 })
  const { data: cv } = useQuery({ queryKey: ['risk-cohort'], queryFn: api.riskCohortVintage, refetchInterval: 60000 })

  return (
    <section className="bg-white border border-slate-200 rounded-xl p-5">
      <SectionHeader
        icon={<Activity size={20} className="text-emerald-600" />}
        title="Recovery curves & cohort vintage"
        subtitle="Cohorts: customers grouped by first-entry-stage and by entry week. Cure = subsequent transition to CURED."
      />

      <div className="grid grid-cols-2 gap-6">
        <div>
          <h3 className="text-xs font-bold text-slate-700 mb-2">Cure rate by entry stage (30-day window)</h3>
          <div className="bg-slate-50 border border-slate-200 rounded overflow-hidden">
            <table className="w-full text-xs">
              <thead className="bg-slate-100">
                <tr>
                  <th className="text-left px-2 py-1.5 text-[10px] uppercase tracking-wider text-slate-500">Entry stage</th>
                  <th className="text-right px-2 py-1.5 text-[10px] uppercase tracking-wider text-slate-500">Cohort</th>
                  <th className="text-right px-2 py-1.5 text-[10px] uppercase tracking-wider text-slate-500">Cures</th>
                  <th className="text-right px-2 py-1.5 text-[10px] uppercase tracking-wider text-slate-500">Rate</th>
                  <th className="text-right px-2 py-1.5 text-[10px] uppercase tracking-wider text-slate-500">Avg hrs to cure</th>
                </tr>
              </thead>
              <tbody>
                {(rc?.summary ?? []).map((r) => (
                  <tr key={r.entry_stage} className="border-t border-slate-100">
                    <td className="px-2 py-1.5 font-mono text-slate-700">{r.entry_stage}</td>
                    <td className="px-2 py-1.5 text-right font-mono">{r.cohort_size}</td>
                    <td className="px-2 py-1.5 text-right font-mono text-emerald-700">{r.cures}</td>
                    <td className="px-2 py-1.5 text-right font-mono">{Number(r.cure_rate_pct).toFixed(1)}%</td>
                    <td className="px-2 py-1.5 text-right font-mono text-slate-600">{r.avg_hours_to_cure ? Number(r.avg_hours_to_cure).toFixed(1) : '—'}</td>
                  </tr>
                ))}
                {(rc?.summary ?? []).length === 0 && (
                  <tr><td colSpan={5} className="text-center py-4 text-sm text-slate-400">Waiting for cohort data…</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        <div>
          <h3 className="text-xs font-bold text-slate-700 mb-2">Cohort vintage (week entered × current stage)</h3>
          <div className="bg-slate-50 border border-slate-200 rounded overflow-auto max-h-72">
            <table className="w-full text-xs">
              <thead className="bg-slate-100 sticky top-0">
                <tr>
                  <th className="text-left px-2 py-1.5 text-[10px] uppercase tracking-wider text-slate-500">Vintage week</th>
                  <th className="text-left px-2 py-1.5 text-[10px] uppercase tracking-wider text-slate-500">Current stage</th>
                  <th className="text-right px-2 py-1.5 text-[10px] uppercase tracking-wider text-slate-500">n</th>
                </tr>
              </thead>
              <tbody>
                {(cv?.cells ?? []).map((row: CohortVintageCell, i: number) => (
                  <tr key={i} className="border-t border-slate-100">
                    <td className="px-2 py-1.5 text-slate-700 font-mono text-[10px]">{String(row.vintage_week).slice(0, 10)}</td>
                    <td className="px-2 py-1.5 text-slate-700"><span className="badge badge-gray text-[9px]">{row.current_stage ?? '—'}</span></td>
                    <td className="px-2 py-1.5 text-right font-mono">{row.n}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </section>
  )
}

// ── Story 6: AI cost dashboard ──

function AiCostSection() {
  const { data } = useQuery({ queryKey: ['risk-ai-cost'], queryFn: api.riskAiCost, refetchInterval: 30000 })

  return (
    <section className="bg-white border border-slate-200 rounded-xl p-5">
      <SectionHeader
        icon={<DollarSign size={20} className="text-yellow-600" />}
        title="AI cost & token spend"
        subtitle="Per-agent, per-day token spend with cost computed from the published Anthropic rate card. Drives FinOps."
      />

      <div className="grid grid-cols-3 gap-3 mb-4">
        <div className="bg-gradient-to-br from-yellow-50 to-amber-50 border border-amber-200 rounded-lg p-3">
          <div className="text-[10px] uppercase tracking-wider text-slate-500">Estimated cost · last 7 days</div>
          <div className="text-3xl font-bold text-amber-700 mt-1">${data?.total_estimated_cost_usd_7d?.toFixed(2) ?? '—'}</div>
        </div>
        <div className="bg-white border border-slate-200 rounded-lg p-3">
          <div className="text-[10px] uppercase tracking-wider text-slate-500">Rate card (per 1M tokens)</div>
          <div className="text-xs space-y-0.5 mt-1">
            {data && Object.entries(data.rate_card).slice(0, 3).map(([model, rate]) => (
              <div key={model} className="flex justify-between">
                <code className="text-slate-700">{model}</code>
                <span className="text-slate-500">${rate.input} in / ${rate.output} out</span>
              </div>
            ))}
          </div>
        </div>
        <div className="bg-white border border-slate-200 rounded-lg p-3">
          <div className="text-[10px] uppercase tracking-wider text-slate-500">Total invocations</div>
          <div className="text-3xl font-bold text-slate-800 mt-1">
            {formatNumber((data?.rows ?? []).reduce((s, r) => s + (r.invocations || 0), 0))}
          </div>
        </div>
      </div>

      <div className="bg-slate-50 border border-slate-200 rounded overflow-hidden">
        <table className="w-full text-xs">
          <thead className="bg-slate-100">
            <tr>
              <th className="text-left px-2 py-1.5 text-[10px] uppercase tracking-wider text-slate-500">Day</th>
              <th className="text-left px-2 py-1.5 text-[10px] uppercase tracking-wider text-slate-500">Agent</th>
              <th className="text-left px-2 py-1.5 text-[10px] uppercase tracking-wider text-slate-500">Model</th>
              <th className="text-right px-2 py-1.5 text-[10px] uppercase tracking-wider text-slate-500">Invocations</th>
              <th className="text-right px-2 py-1.5 text-[10px] uppercase tracking-wider text-slate-500">Tokens</th>
              <th className="text-right px-2 py-1.5 text-[10px] uppercase tracking-wider text-slate-500">Avg latency</th>
              <th className="text-right px-2 py-1.5 text-[10px] uppercase tracking-wider text-slate-500">Escalations</th>
              <th className="text-right px-2 py-1.5 text-[10px] uppercase tracking-wider text-slate-500">$ Cost</th>
            </tr>
          </thead>
          <tbody>
            {(data?.rows ?? []).map((r, i) => (
              <tr key={i} className="border-t border-slate-100">
                <td className="px-2 py-1.5 text-slate-700 text-[10px]">{String(r.day).slice(0, 10)}</td>
                <td className="px-2 py-1.5 text-slate-700">{r.agent_type}</td>
                <td className="px-2 py-1.5"><code className="text-[10px]">{r.model}</code></td>
                <td className="px-2 py-1.5 text-right font-mono">{r.invocations}</td>
                <td className="px-2 py-1.5 text-right font-mono">{formatNumber(r.tokens || 0)}</td>
                <td className="px-2 py-1.5 text-right font-mono text-slate-600">{r.avg_latency_ms ?? '—'}ms</td>
                <td className={`px-2 py-1.5 text-right font-mono ${r.escalations > 0 ? 'text-amber-600' : ''}`}>{r.escalations}</td>
                <td className="px-2 py-1.5 text-right font-mono text-amber-700">${r.estimated_cost_usd.toFixed(4)}</td>
              </tr>
            ))}
            {(data?.rows ?? []).length === 0 && (
              <tr><td colSpan={8} className="text-center py-4 text-sm text-slate-400">No AI activity in the last 7 days.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  )
}

// ── Page ──

export default function RiskAndML() {
  return (
    <div className="p-6 space-y-6 flex-1 overflow-y-auto overflow-x-hidden min-w-0">
      <div>
        <div className="flex items-center gap-3">
          <Brain size={26} className="text-indigo-600" />
          <h1 className="text-xl font-bold text-slate-800">Risk &amp; ML platform</h1>
        </div>
        <p className="text-sm text-slate-500 mt-1 max-w-3xl">
          Where the lakehouse becomes a decision platform. Real GradientBoosting risk model trained on the
          customer event store, Markov-chain roll-rate forecasting, two-proportion z-test for A/B significance,
          recovery curves, cohort vintage, and FinOps for AI spend.
        </p>
      </div>

      <ModelCardSection />
      <ScoreSection />
      <RollRateSection />
      <AbTestSection />
      <RecoverySection />
      <AiCostSection />
    </div>
  )
}
