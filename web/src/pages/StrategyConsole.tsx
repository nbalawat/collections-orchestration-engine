import { useState, useMemo } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api } from '@/lib/api'
import type {
  SegmentMatrixCell, TreatmentMatrixRow, ComplianceFiringRow,
  StrategyDecisionRow, StrategyVersionRow, SideBySideResult,
} from '@/lib/api'
import {
  Cog, Play, Sparkles, Workflow, GitBranch, ShieldCheck, Target,
  Filter, Brain, TrendingUp, Zap, ArrowRight, ChevronDown, ChevronRight,
  Trophy, AlertTriangle, RefreshCw, Hash, Clock,
} from 'lucide-react'
import { formatTime, stageBadgeColor } from '@/lib/utils'

// ── Canonical demo cases — each tells a different policy story ──
type CaseInput = Record<string, unknown>
type CaseScenario = { id: string; label: string; subtitle: string; tone: string; input: CaseInput }

const CASES: CaseScenario[] = [
  {
    id: 'pre_delinquent_vip',
    label: 'Pre-delinquent VIP',
    subtitle: '12 DPD · risk 35 · $85k balance · gold segment',
    tone: 'emerald',
    input: {
      dpd: 12, balance: 85000, risk_score: 35, relationship_value: 'gold',
      relationship_tenure_years: 9, prior_delinquencies: 0, prior_cures: 0,
      compliance_flags: [], failed_channels: [], channel_attempts_7d: {},
      total_attempts_7d: 0, voice_attempts_7d: 0, customer_local_hour: 14,
      late_fee_amount: 250, recent_income_change: false, conflicting_signals: [],
      hardship_flag: false,
    },
  },
  {
    id: 'mid_hardship',
    label: 'Mid-stage hardship',
    subtitle: '47 DPD · risk 68 · hardship signaled · medium value',
    tone: 'amber',
    input: {
      dpd: 47, balance: 18500, risk_score: 68, relationship_value: 'standard',
      relationship_tenure_years: 4, prior_delinquencies: 1, prior_cures: 1,
      compliance_flags: ['HARDSHIP'], hardship_flag: true,
      failed_channels: ['voice'], channel_attempts_7d: { voice: 4, sms: 2 },
      total_attempts_7d: 6, voice_attempts_7d: 4, customer_local_hour: 14,
      late_fee_amount: 75, recent_income_change: true,
      conflicting_signals: [], preferred_channel: 'sms',
    },
  },
  {
    id: 'late_high_risk',
    label: 'Late + high risk',
    subtitle: '82 DPD · risk 89 · 3 prior delinquencies · settlement candidate',
    tone: 'red',
    input: {
      dpd: 82, balance: 42000, risk_score: 89, relationship_value: 'standard',
      relationship_tenure_years: 2, prior_delinquencies: 3, prior_cures: 0,
      compliance_flags: [], hardship_flag: false,
      failed_channels: ['voice', 'sms'],
      channel_attempts_7d: { voice: 5, sms: 8, email: 3 },
      total_attempts_7d: 16, voice_attempts_7d: 5, customer_local_hour: 14,
      late_fee_amount: 200, recent_income_change: false, conflicting_signals: [],
    },
  },
  {
    id: 'bankruptcy_filed',
    label: 'Bankruptcy filed',
    subtitle: '60 DPD · BANKRUPTCY flag · all contact must stop',
    tone: 'slate',
    input: {
      dpd: 60, balance: 28000, risk_score: 70, relationship_value: 'standard',
      relationship_tenure_years: 3, prior_delinquencies: 2, prior_cures: 0,
      compliance_flags: ['BANKRUPTCY'], hardship_flag: false,
      failed_channels: [], channel_attempts_7d: {}, total_attempts_7d: 0,
      voice_attempts_7d: 0, customer_local_hour: 14, late_fee_amount: 100,
      recent_income_change: false, conflicting_signals: [],
    },
  },
]

const TONE_CLASSES: Record<string, string> = {
  emerald: 'from-emerald-50 to-white border-emerald-200',
  amber: 'from-amber-50 to-white border-amber-200',
  red: 'from-red-50 to-white border-red-200',
  slate: 'from-slate-100 to-white border-slate-300',
}

// ── Tiny components ──

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

function PolicyStation({
  icon, title, color, headline, fields,
}: {
  icon: React.ReactNode; title: string; color: string;
  headline?: string; fields: { label: string; value: React.ReactNode }[]
}) {
  return (
    <div className={`flex flex-col border rounded-xl ${color} min-w-[220px] max-w-[220px] shrink-0`}>
      <div className="px-3 py-2 border-b border-current/10">
        <div className="flex items-center gap-2">
          {icon}
          <span className="text-sm font-bold text-slate-800">{title}</span>
        </div>
      </div>
      <div className="px-3 py-2.5 flex-1">
        {headline && (
          <div className="text-sm font-semibold text-slate-800 mb-1.5 leading-tight">{headline}</div>
        )}
        <div className="space-y-1">
          {fields.map((f, i) => (
            <div key={i} className="flex items-baseline justify-between gap-2 text-[11px]">
              <span className="text-slate-500 shrink-0">{f.label}</span>
              <span className="text-slate-800 text-right truncate">{f.value}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function Edge({ label }: { label: string }) {
  return (
    <div className="flex flex-col items-center justify-center shrink-0 px-1 py-12">
      <ArrowRight size={18} className="text-slate-400" />
      <div className="text-[9px] uppercase tracking-wider text-slate-500 mt-1 max-w-[80px] text-center leading-tight">{label}</div>
    </div>
  )
}

// ── Story 1: "Why did we do that?" — case study flow ──

function StoryOne() {
  const [caseId, setCaseId] = useState(CASES[1].id)
  const sel = CASES.find((c) => c.id === caseId)!

  const mutation = useMutation({
    mutationFn: () => api.evaluateFull(sel.input),
  })

  const policies = (mutation.data ?? {}) as Record<string, Record<string, unknown>>
  const seg = (policies.segmentation as Record<string, unknown>) || {}
  const treat = (policies.treatment as Record<string, unknown>) || {}
  const route = (policies.channel_routing as Record<string, unknown>) || {}
  const comp = (policies.compliance as Record<string, unknown>) || {}

  const tone = TONE_CLASSES[sel.tone] || TONE_CLASSES.slate

  return (
    <section className="bg-white border border-slate-200 rounded-xl p-5">
      <SectionHeader
        icon={<Sparkles size={20} className="text-indigo-600" />}
        title='Why did we do that?'
        subtitle="Run a real case through Segmentation → Treatment → Routing → Compliance. Every verdict comes from the live OPA policy stack with citations."
        action={
          <button
            className="btn btn-primary text-sm flex items-center gap-1.5"
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending}
          >
            {mutation.isPending ? <><RefreshCw size={14} className="animate-spin" /> Evaluating</> : <><Play size={14} /> Evaluate</>}
          </button>
        }
      />

      <div className="grid grid-cols-4 gap-2 mb-4">
        {CASES.map((c) => {
          const active = c.id === caseId
          return (
            <button
              key={c.id}
              onClick={() => { setCaseId(c.id); mutation.reset() }}
              className={`text-left p-3 border rounded-lg bg-gradient-to-br transition ${
                active ? `${TONE_CLASSES[c.tone]} ring-2 ring-offset-1 ring-indigo-300` : 'border-slate-200 hover:border-indigo-200'
              }`}
            >
              <div className="text-sm font-bold text-slate-800">{c.label}</div>
              <div className="text-[11px] text-slate-500 mt-0.5">{c.subtitle}</div>
            </button>
          )
        })}
      </div>

      {mutation.data && (
        <div className={`bg-gradient-to-r ${tone} border rounded-lg p-3 overflow-x-auto`}>
          <div className="flex items-stretch">
            <PolicyStation
              icon={<Hash size={14} className="text-slate-600" />}
              title="Case input"
              color="bg-white border-slate-300"
              fields={[
                { label: 'dpd', value: String(sel.input.dpd) },
                { label: 'balance', value: `$${Number(sel.input.balance).toLocaleString()}` },
                { label: 'risk', value: String(sel.input.risk_score) },
                { label: 'value', value: String(sel.input.relationship_value) },
                { label: 'flags', value: ((sel.input.compliance_flags as string[]) ?? []).join(', ') || '—' },
                { label: 'attempts/7d', value: String(sel.input.total_attempts_7d) },
              ]}
            />

            <Edge label="collections.segmentation.rego" />

            <PolicyStation
              icon={<Filter size={14} className="text-blue-600" />}
              title="Segmentation"
              color="bg-blue-50 border-blue-300"
              headline={String(seg.dpd_bucket ?? '—')}
              fields={[
                { label: 'risk tier', value: String(seg.risk_tier ?? '—') },
                { label: 'value seg', value: String(seg.value_segment ?? '—') },
                { label: 'self-cure', value: String((seg.self_cure_probability as string) ?? (seg.self_cure_likely as unknown) ?? '—') },
                { label: 'first-time', value: seg.first_time_delinquent ? 'yes' : 'no' },
                { label: 'hardship?', value: seg.hardship_indicated ? 'yes' : 'no' },
              ]}
            />

            <Edge label="collections.treatment.rego" />

            <PolicyStation
              icon={<Target size={14} className="text-amber-600" />}
              title="Treatment"
              color="bg-amber-50 border-amber-300"
              headline={String(treat.action ?? '—')}
              fields={[
                { label: 'tone', value: String(treat.message_tone ?? '—') },
                { label: 'priority', value: String((treat.priority as string) ?? '—') },
                { label: 'ai review?', value: treat.requires_ai_review ? 'yes' : 'no' },
              ]}
            />

            <Edge label="collections.channel_routing.rego" />

            <PolicyStation
              icon={<Workflow size={14} className="text-purple-600" />}
              title="Routing"
              color="bg-purple-50 border-purple-300"
              headline={(((route.recommended_channels as string[]) ?? []).join(' → ')) || '—'}
              fields={[
                { label: 'primary', value: String(((route.recommended_channels as string[]) ?? [])[0] ?? '—') },
                { label: 'fallbacks', value: (((route.recommended_channels as string[]) ?? []).slice(1).join(', ')) || '—' },
                { label: 'window', value: String((route.contact_window as string) ?? '8a–9p local') },
              ]}
            />

            <Edge label="collections.compliance.rego" />

            <PolicyStation
              icon={<ShieldCheck size={14} className={comp.can_contact ? 'text-emerald-600' : 'text-red-600'} />}
              title="Compliance"
              color={comp.can_contact ? 'bg-emerald-50 border-emerald-300' : 'bg-red-50 border-red-300'}
              headline={comp.can_contact ? 'allowed' : 'SUPPRESSED'}
              fields={[
                { label: 'full suppress', value: comp.full_suppression ? 'yes' : 'no' },
                { label: 'written-only', value: comp.written_only ? 'yes' : 'no' },
                { label: 'scra', value: comp.scra_protected ? 'yes' : 'no' },
                { label: 'dispute', value: comp.dispute_active ? 'yes' : 'no' },
              ]}
            />
          </div>

          <div className="mt-3 text-[11px] text-slate-500 flex items-center gap-1.5">
            <Brain size={11} />
            <span>Each station above is the verbatim output of an OPA Rego rule. Click a recent decision below to see the same flow on a real customer's audit log.</span>
          </div>
        </div>
      )}

      {!mutation.data && !mutation.isPending && (
        <div className="text-sm text-slate-400 text-center py-8 border border-dashed border-slate-200 rounded-lg">
          Pick a case above and hit <span className="font-semibold text-slate-600">Evaluate</span> to run it through the policy stack.
        </div>
      )}
    </section>
  )
}

// ── Story 2: Champion vs challenger ──

function StoryTwo() {
  const { data } = useQuery({
    queryKey: ['strategy-version-comparison'],
    queryFn: api.strategyVersionComparison,
    refetchInterval: 10000,
  })
  const [caseId, setCaseId] = useState(CASES[2].id)
  const sel = CASES.find((c) => c.id === caseId)!
  const ab = useMutation({
    mutationFn: () => api.strategySideBySide(sel.input),
  })

  const versions = data?.versions ?? []

  return (
    <section className="bg-white border border-slate-200 rounded-xl p-5">
      <SectionHeader
        icon={<Trophy size={20} className="text-amber-600" />}
        title='Champion vs Challenger · live A/B'
        subtitle="Customers are partitioned by strategy version. Performance is computed from real strategy_audit_log + agent_actions over the last 24 hours."
      />

      <div className={`grid gap-3 mb-4 ${versions.length === 2 ? 'grid-cols-2' : 'grid-cols-3'}`}>
        {versions.map((v) => {
          const isChamp = v.role === 'champion'
          return (
            <div key={v.strategy_version}
                 className={`relative border-2 rounded-xl p-4 ${
                   isChamp ? 'bg-gradient-to-br from-yellow-50 to-amber-50 border-amber-300'
                           : 'bg-gradient-to-br from-indigo-50 to-blue-50 border-indigo-300'
                 }`}>
              <div className="flex items-center justify-between mb-2">
                <div>
                  <code className="text-lg font-bold text-slate-800">{v.strategy_version}</code>
                  <span className={`badge ml-2 text-[10px] ${isChamp ? 'badge-yellow' : 'badge-blue'}`}>{v.role}</span>
                </div>
                <div className="text-right">
                  <div className="text-[10px] uppercase tracking-wider text-slate-500">Allocation</div>
                  <div className="text-lg font-bold text-slate-800">{Number(v.allocation_pct ?? 0).toFixed(0)}%</div>
                </div>
              </div>
              <p className="text-xs text-slate-600 leading-relaxed">{v.description}</p>

              <div className="grid grid-cols-3 gap-2 mt-3 text-center">
                <div className="bg-white/70 rounded p-2">
                  <div className="text-[10px] uppercase tracking-wider text-slate-500">Customers</div>
                  <div className="text-lg font-bold text-slate-800">{v.customers_24h}</div>
                </div>
                <div className="bg-white/70 rounded p-2">
                  <div className="text-[10px] uppercase tracking-wider text-slate-500">Eval / 24h</div>
                  <div className="text-lg font-bold text-slate-800">{v.evaluations_24h}</div>
                </div>
                <div className="bg-white/70 rounded p-2">
                  <div className="text-[10px] uppercase tracking-wider text-slate-500">Actions / 24h</div>
                  <div className="text-lg font-bold text-slate-800">{v.agent_actions_24h}</div>
                </div>
                <div className="bg-white/70 rounded p-2">
                  <div className="text-[10px] uppercase tracking-wider text-slate-500">Escalations</div>
                  <div className={`text-lg font-bold ${(v.escalations_24h ?? 0) > 0 ? 'text-amber-700' : 'text-slate-800'}`}>{v.escalations_24h}</div>
                </div>
                <div className="bg-white/70 rounded p-2">
                  <div className="text-[10px] uppercase tracking-wider text-slate-500">Cure rate</div>
                  <div className="text-lg font-bold text-emerald-700">{v.cure_rate_24h != null ? `${v.cure_rate_24h}%` : '—'}</div>
                </div>
                <div className="bg-white/70 rounded p-2">
                  <div className="text-[10px] uppercase tracking-wider text-slate-500">AI conf</div>
                  <div className="text-lg font-bold text-slate-800">{v.avg_confidence != null ? `${Math.round(v.avg_confidence * 100)}%` : '—'}</div>
                </div>
              </div>
            </div>
          )
        })}
      </div>

      <div className="border-t border-slate-100 pt-3">
        <div className="flex items-center justify-between mb-2 gap-3 flex-wrap">
          <div className="text-xs font-semibold text-slate-700">Side-by-side · run the same case through both versions</div>
          <div className="flex items-center gap-2">
            <select
              value={caseId}
              onChange={(e) => { setCaseId(e.target.value); ab.reset() }}
              className="text-xs border border-slate-200 rounded px-2 py-1 bg-white"
            >
              {CASES.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}
            </select>
            <button
              className="btn btn-primary text-xs flex items-center gap-1"
              onClick={() => ab.mutate()}
              disabled={ab.isPending}
            >
              {ab.isPending ? <><RefreshCw size={11} className="animate-spin" /> running</> : <><Play size={11} /> compare</>}
            </button>
          </div>
        </div>

        {ab.data && (
          <div className={`grid gap-3 ${ab.data.results.length === 2 ? 'grid-cols-2' : 'grid-cols-1'}`}>
            {ab.data.results.map((r: SideBySideResult) => {
              const seg = (r.policies.segmentation as Record<string, unknown>) || {}
              const tr = (r.policies.treatment as Record<string, unknown>) || {}
              const ro = (r.policies.channel_routing as Record<string, unknown>) || {}
              const co = (r.policies.compliance as Record<string, unknown>) || {}
              return (
                <div key={r.strategy_version} className="border border-slate-200 rounded-lg p-3">
                  <div className="flex items-center gap-2 mb-2">
                    <code className="text-sm font-bold text-slate-800">{r.strategy_version}</code>
                    <span className={`badge text-[10px] ${r.role === 'champion' ? 'badge-yellow' : 'badge-blue'}`}>{r.role}</span>
                  </div>
                  <div className="grid grid-cols-2 gap-2 text-[11px]">
                    <div className="bg-blue-50 rounded p-2"><div className="text-[10px] text-slate-500">segment</div><div className="font-mono text-slate-800">{String(seg.dpd_bucket ?? '—')} · {String(seg.risk_tier ?? '—')}</div></div>
                    <div className="bg-amber-50 rounded p-2"><div className="text-[10px] text-slate-500">treatment</div><div className="font-mono text-slate-800">{String(tr.action ?? '—')}</div></div>
                    <div className="bg-purple-50 rounded p-2"><div className="text-[10px] text-slate-500">channels</div><div className="font-mono text-slate-800">{((ro.recommended_channels as string[]) ?? []).join(', ') || '—'}</div></div>
                    <div className={`${co.can_contact ? 'bg-emerald-50' : 'bg-red-50'} rounded p-2`}><div className="text-[10px] text-slate-500">compliance</div><div className="font-mono text-slate-800">{co.can_contact ? 'can_contact ✓' : 'SUPPRESSED'}</div></div>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </section>
  )
}

// ── Story 3: Policy heatmaps ──

function StoryThree() {
  const { data: seg } = useQuery({ queryKey: ['strategy-segment-matrix'], queryFn: api.strategySegmentMatrix, refetchInterval: 30000 })
  const { data: tx } = useQuery({ queryKey: ['strategy-treatment-matrix'], queryFn: api.strategyTreatmentMatrix, refetchInterval: 30000 })
  const { data: cf } = useQuery({ queryKey: ['strategy-compliance-firing'], queryFn: api.strategyComplianceFiring, refetchInterval: 30000 })

  const { dpdBuckets, riskTiers, segmentGrid, segmentMax } = useMemo(() => {
    const cells = (seg?.cells ?? []) as SegmentMatrixCell[]
    const dpd = ['pre_delinquent', 'early', 'mid', 'late', 'severe']
    const risk = ['low_risk', 'medium_risk', 'high_risk']
    const grid: Record<string, Record<string, number>> = {}
    let max = 0
    for (const c of cells) {
      grid[c.dpd_bucket] ??= {}
      grid[c.dpd_bucket][c.risk_tier] = (grid[c.dpd_bucket][c.risk_tier] || 0) + c.n
      if (grid[c.dpd_bucket][c.risk_tier] > max) max = grid[c.dpd_bucket][c.risk_tier]
    }
    return { dpdBuckets: dpd, riskTiers: risk, segmentGrid: grid, segmentMax: max }
  }, [seg])

  return (
    <section className="bg-white border border-slate-200 rounded-xl p-5">
      <SectionHeader
        icon={<Workflow size={20} className="text-emerald-600" />}
        title="What is the policy actually doing?"
        subtitle="Live distributions from the last 24 hours of OPA evaluations. The heatmap shows how customers map onto the 2-D strategy segment space; the treatment table shows what action each segment actually got; the firing table shows which compliance reasons are doing the work."
      />

      <div className="grid grid-cols-2 gap-6">
        {/* Segment heatmap */}
        <div>
          <h3 className="text-sm font-bold text-slate-700 mb-2">Segment distribution · DPD × risk</h3>
          <div className="overflow-x-auto">
            <table className="text-xs border border-slate-200 rounded overflow-hidden">
              <thead className="bg-slate-50">
                <tr>
                  <th className="px-2 py-1.5 text-left text-[10px] uppercase tracking-wider text-slate-500">DPD bucket</th>
                  {riskTiers.map((r) => (
                    <th key={r} className="px-2 py-1.5 text-[10px] uppercase tracking-wider text-slate-500">{r.replace('_', ' ')}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {dpdBuckets.map((d) => (
                  <tr key={d} className="border-t border-slate-100">
                    <td className="px-2 py-1.5 font-mono text-slate-700">{d}</td>
                    {riskTiers.map((r) => {
                      const v = segmentGrid[d]?.[r] || 0
                      const intensity = segmentMax > 0 ? v / segmentMax : 0
                      return (
                        <td key={r} className="px-2 py-1.5 text-center font-mono"
                            style={{
                              backgroundColor: v > 0 ? `rgba(99, 102, 241, ${0.08 + intensity * 0.55})` : 'transparent',
                              color: intensity > 0.55 ? 'white' : 'rgb(30, 41, 59)',
                              fontWeight: intensity > 0.4 ? 600 : 400,
                            }}>
                          {v || '·'}
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Treatment matrix */}
        <div>
          <h3 className="text-sm font-bold text-slate-700 mb-2">Treatment action by segment</h3>
          <div className="bg-slate-50 border border-slate-200 rounded max-h-72 overflow-y-auto">
            <table className="w-full text-xs">
              <thead className="bg-slate-100 sticky top-0">
                <tr>
                  <th className="text-left px-2 py-1.5 text-[10px] uppercase tracking-wider text-slate-500">Segment</th>
                  <th className="text-left px-2 py-1.5 text-[10px] uppercase tracking-wider text-slate-500">→ Treatment</th>
                  <th className="text-left px-2 py-1.5 text-[10px] uppercase tracking-wider text-slate-500">Tone</th>
                  <th className="text-right px-2 py-1.5 text-[10px] uppercase tracking-wider text-slate-500">N</th>
                </tr>
              </thead>
              <tbody>
                {(tx?.rows ?? []).slice(0, 12).map((row: TreatmentMatrixRow, i: number) => (
                  <tr key={i} className="border-t border-slate-100">
                    <td className="px-2 py-1.5 text-slate-700 font-mono text-[10px]">{row.dpd_bucket} · {row.risk_tier}</td>
                    <td className="px-2 py-1.5">
                      <span className="badge badge-blue text-[9px]">{row.treatment_action ?? '—'}</span>
                    </td>
                    <td className="px-2 py-1.5 text-slate-600 text-[10px]">{row.message_tone ?? '—'}</td>
                    <td className="px-2 py-1.5 text-right font-mono text-slate-700">{row.n}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Compliance firing */}
        <div className="col-span-2">
          <h3 className="text-sm font-bold text-slate-700 mb-2 flex items-center gap-2">
            <ShieldCheck size={14} className="text-emerald-600" /> Compliance gate · what's firing
          </h3>
          <div className="bg-slate-50 border border-slate-200 rounded max-h-64 overflow-y-auto">
            <table className="w-full text-xs">
              <thead className="bg-slate-100 sticky top-0">
                <tr>
                  <th className="text-left px-2 py-1.5 text-[10px] uppercase tracking-wider text-slate-500">Reason</th>
                  <th className="text-left px-2 py-1.5 text-[10px] uppercase tracking-wider text-slate-500">Check</th>
                  <th className="text-left px-2 py-1.5 text-[10px] uppercase tracking-wider text-slate-500">Action blocked</th>
                  <th className="text-center px-2 py-1.5 text-[10px] uppercase tracking-wider text-slate-500">Passed</th>
                  <th className="text-right px-2 py-1.5 text-[10px] uppercase tracking-wider text-slate-500">N</th>
                </tr>
              </thead>
              <tbody>
                {(cf?.reasons ?? []).map((row: ComplianceFiringRow, i: number) => (
                  <tr key={i} className="border-t border-slate-100">
                    <td className="px-2 py-1.5 text-slate-700">{row.reason || '—'}</td>
                    <td className="px-2 py-1.5 font-mono text-slate-700 text-[10px]">{row.check_type || '—'}</td>
                    <td className="px-2 py-1.5 text-slate-700 text-[10px]">{row.action_blocked || '—'}</td>
                    <td className="px-2 py-1.5 text-center">
                      {row.passed ? (
                        <span className="badge badge-green text-[9px]">pass</span>
                      ) : (
                        <span className="badge badge-red text-[9px]">block</span>
                      )}
                    </td>
                    <td className="px-2 py-1.5 text-right font-mono text-slate-700">{row.n}</td>
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

// ── Story 4: Recent OPA decisions feed ──

function StoryFour() {
  const { data } = useQuery({
    queryKey: ['strategy-recent-decisions'],
    queryFn: () => api.strategyRecentDecisions(30),
    refetchInterval: 8000,
  })
  const [expandedId, setExpandedId] = useState<string | null>(null)

  return (
    <section className="bg-white border border-slate-200 rounded-xl p-5">
      <SectionHeader
        icon={<GitBranch size={20} className="text-slate-700" />}
        title='Live OPA evaluations · the audit trail'
        subtitle="Every customer journey iteration runs the policy stack; every result is persisted to strategy_audit_log with full input + output context. Click a row to drill in."
      />

      <div className="border border-slate-200 rounded overflow-hidden">
        <table className="w-full text-xs">
          <thead className="bg-slate-50">
            <tr>
              <th className="text-left px-2 py-1.5 text-[10px] uppercase tracking-wider text-slate-500">When</th>
              <th className="text-left px-2 py-1.5 text-[10px] uppercase tracking-wider text-slate-500">Customer</th>
              <th className="text-left px-2 py-1.5 text-[10px] uppercase tracking-wider text-slate-500">Version</th>
              <th className="text-left px-2 py-1.5 text-[10px] uppercase tracking-wider text-slate-500">Segment</th>
              <th className="text-left px-2 py-1.5 text-[10px] uppercase tracking-wider text-slate-500">Treatment</th>
              <th className="text-left px-2 py-1.5 text-[10px] uppercase tracking-wider text-slate-500">Channels</th>
              <th className="text-center px-2 py-1.5 text-[10px] uppercase tracking-wider text-slate-500">Allowed</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {(data?.decisions ?? []).map((d: StrategyDecisionRow) => {
              const isOpen = expandedId === d.audit_id
              const allowed = String(d.can_contact) === 'true'
              return (
                <>
                  <tr key={d.audit_id} className="border-t border-slate-100 hover:bg-slate-50 cursor-pointer"
                      onClick={() => setExpandedId(isOpen ? null : d.audit_id)}>
                    <td className="px-2 py-1.5 text-slate-500 text-[10px]">{formatTime(d.evaluated_at)}</td>
                    <td className="px-2 py-1.5">
                      <Link to={`/customer/${d.customer_id}`} className="font-mono text-indigo-600 hover:underline">{d.customer_id}</Link>
                    </td>
                    <td className="px-2 py-1.5"><code className="text-[10px] text-slate-700">{d.strategy_version}</code></td>
                    <td className="px-2 py-1.5 text-slate-700 text-[10px]">{d.dpd_bucket} · {d.risk_tier}</td>
                    <td className="px-2 py-1.5"><span className="badge badge-blue text-[9px]">{d.treatment_action ?? '—'}</span></td>
                    <td className="px-2 py-1.5 text-slate-700 text-[10px]">{Array.isArray(d.recommended_channels) ? (d.recommended_channels as string[]).join(', ') : '—'}</td>
                    <td className="px-2 py-1.5 text-center">
                      {allowed
                        ? <span className="badge badge-green text-[9px]">yes</span>
                        : <span className="badge badge-red text-[9px]">no</span>}
                    </td>
                    <td className="px-1 py-1.5">{isOpen ? <ChevronDown size={11} /> : <ChevronRight size={11} />}</td>
                  </tr>
                  {isOpen && (
                    <tr className="bg-slate-50/70 border-t border-slate-100">
                      <td colSpan={8} className="px-3 py-3">
                        <div className="grid grid-cols-2 gap-3">
                          <div>
                            <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-1">OPA input</div>
                            <pre className="bg-white border border-slate-200 rounded p-2 text-[10px] overflow-auto max-h-72">
                              {JSON.stringify(d.input_context, null, 2)}
                            </pre>
                          </div>
                          <div>
                            <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-1">Decision</div>
                            <pre className="bg-white border border-slate-200 rounded p-2 text-[10px] overflow-auto max-h-72">
                              {JSON.stringify(d.decision, null, 2)}
                            </pre>
                          </div>
                        </div>
                      </td>
                    </tr>
                  )}
                </>
              )
            })}
          </tbody>
        </table>
      </div>
    </section>
  )
}

// ── Page ──

export default function StrategyConsole() {
  return (
    <div className="p-6 space-y-6 flex-1 overflow-y-auto overflow-x-hidden min-w-0">
      <div>
        <div className="flex items-center gap-3">
          <Cog size={26} className="text-indigo-600" />
          <h1 className="text-xl font-bold text-slate-800">Strategy Console</h1>
        </div>
        <p className="text-sm text-slate-500 mt-1 max-w-3xl">
          Four stories about the live strategy engine — explainable case studies, champion vs challenger,
          what the policy is actually doing across the portfolio, and the complete audit trail. All numbers
          come from real OPA evaluations and real customer events.
        </p>
      </div>

      <StoryOne />
      <StoryTwo />
      <StoryThree />
      <StoryFour />
    </div>
  )
}
