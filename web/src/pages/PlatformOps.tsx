import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type {
  ServiceHeartbeat, KafkaTopicInfo, ConsumerGroupLag,
  OpaPolicy, OpaDecision, TraceResult,
} from '@/lib/api'
import {
  Server, Database, Activity, ArrowRight, Layers, Search,
  CheckCircle, AlertTriangle, Clock, Cpu, Hash, X,
} from 'lucide-react'
import { formatNumber, formatTime, formatDateTime } from '@/lib/utils'

function StatPill({ label, value, sub, tone = 'default' }: {
  label: string; value: string; sub?: string; tone?: 'default' | 'good' | 'warn' | 'bad'
}) {
  const toneClass = {
    default: 'bg-slate-50 border-slate-200 text-slate-700',
    good: 'bg-emerald-50 border-emerald-200 text-emerald-800',
    warn: 'bg-amber-50 border-amber-200 text-amber-800',
    bad: 'bg-red-50 border-red-200 text-red-800',
  }[tone]
  return (
    <div className={`px-4 py-3 rounded-lg border ${toneClass}`}>
      <div className="text-[11px] uppercase tracking-wider opacity-70">{label}</div>
      <div className="text-2xl font-bold mt-1">{value}</div>
      {sub && <div className="text-[11px] opacity-70 mt-0.5">{sub}</div>}
    </div>
  )
}

function ServiceCard({ s }: { s: ServiceHeartbeat }) {
  const stale = s.status === 'stale' || s.seconds_since_last_seen > 30
  const tone = stale ? 'bg-red-50 border-red-300' :
               s.error_count_5m > 0 ? 'bg-amber-50 border-amber-300' :
               'bg-emerald-50 border-emerald-300'
  return (
    <div className={`border rounded-lg p-3 ${tone}`}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="font-semibold text-sm text-slate-800 truncate">{s.service_name}</div>
          <div className="text-[10px] text-slate-500 font-mono truncate">{s.instance_id}</div>
        </div>
        {stale ? (
          <AlertTriangle size={16} className="text-red-600 shrink-0" />
        ) : (
          <CheckCircle size={16} className="text-emerald-600 shrink-0" />
        )}
      </div>
      <div className="grid grid-cols-2 gap-2 mt-2 text-[11px]">
        <div>
          <div className="text-slate-400">Throughput</div>
          <div className="font-bold text-slate-700">{(s.throughput_per_sec ?? 0).toFixed(1)}/s</div>
        </div>
        <div>
          <div className="text-slate-400">p99 latency</div>
          <div className="font-bold text-slate-700">
            {s.p99_latency_ms != null ? `${s.p99_latency_ms}ms` : '—'}
          </div>
        </div>
        <div>
          <div className="text-slate-400">Errors (5m)</div>
          <div className={`font-bold ${s.error_count_5m > 0 ? 'text-red-600' : 'text-slate-700'}`}>
            {s.error_count_5m}
          </div>
        </div>
        <div>
          <div className="text-slate-400">Last seen</div>
          <div className="font-bold text-slate-700">{s.seconds_since_last_seen}s ago</div>
        </div>
      </div>
    </div>
  )
}

function TopicRow({ t }: { t: KafkaTopicInfo }) {
  return (
    <tr className="border-b border-slate-100 hover:bg-slate-50">
      <td className="py-2 px-3">
        <code className="text-xs text-slate-700">{t.topic}</code>
      </td>
      <td className="py-2 px-3 text-sm text-slate-600">{t.partition_count}</td>
      <td className="py-2 px-3 text-sm font-mono text-slate-700">{formatNumber(t.total_messages)}</td>
      <td className="py-2 px-3 text-sm font-mono">
        {t.throughput_per_sec != null ? (
          <span className={t.throughput_per_sec > 0 ? 'text-emerald-700' : 'text-slate-400'}>
            {t.throughput_per_sec.toFixed(1)}/s
          </span>
        ) : (
          <span className="text-slate-400">measuring…</span>
        )}
      </td>
      <td className="py-2 px-3 text-xs text-slate-500">
        {t.partitions.map(p => (
          <span key={p.id} className="inline-block mr-2">
            P{p.id}: <span className="font-mono">{p.end_offset}</span>
          </span>
        ))}
      </td>
    </tr>
  )
}

function ConsumerLagRow({ g }: { g: ConsumerGroupLag }) {
  const totalLag = g.total_lag ?? g.partitions.reduce((s, p) => s + p.lag, 0)
  const tone = totalLag > 100 ? 'text-red-600' : totalLag > 0 ? 'text-amber-600' : 'text-emerald-700'
  return (
    <div className="border border-slate-200 rounded-lg p-3 bg-white">
      <div className="flex items-center justify-between mb-2">
        <code className="text-sm font-semibold text-slate-800">{g.group_id}</code>
        <span className={`text-sm font-bold ${tone}`}>Total lag: {formatNumber(totalLag)}</span>
      </div>
      <div className="space-y-1">
        {g.partitions.map((p, i) => (
          <div key={i} className="flex items-center justify-between text-xs">
            <span className="text-slate-600">
              <code>{p.topic}</code> <span className="text-slate-400">P{p.partition}</span>
            </span>
            <span className="font-mono text-slate-500">
              {p.committed} / {p.end_offset}
              <span className={`ml-2 ${p.lag > 0 ? 'text-amber-600 font-semibold' : 'text-emerald-600'}`}>
                (lag {p.lag})
              </span>
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

function DecisionFeedRow({ d, onClick }: { d: OpaDecision; onClick: () => void }) {
  const dec = d.decision || {}
  const treatment = (dec.treatment as Record<string, unknown>) || {}
  const compliance = (dec.compliance_view as Record<string, unknown>) || (dec.compliance as Record<string, unknown>) || {}
  return (
    <div className="border-b border-slate-100 px-3 py-2 hover:bg-slate-50 cursor-pointer" onClick={onClick}>
      <div className="flex items-center gap-2 text-xs">
        <code className="text-slate-500 font-mono">{d.customer_id}</code>
        <span className="text-slate-700 font-medium">{d.policy_name}</span>
        {treatment.action != null && (
          <span className="badge badge-blue text-[10px]">{String(treatment.action)}</span>
        )}
        {compliance.can_contact === false && (
          <span className="badge badge-red text-[10px]">suppression active</span>
        )}
        <span className="ml-auto text-slate-400">{formatTime(d.evaluated_at)}</span>
      </div>
    </div>
  )
}

function TraceView({ trace, onClose }: { trace: TraceResult; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-6">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-4xl max-h-[85vh] flex flex-col overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-200 flex items-center justify-between">
          <div>
            <div className="text-lg font-bold text-slate-800">End-to-end trace</div>
            <code className="text-xs text-slate-500">correlation_id: {trace.correlation_id}</code>
          </div>
          <button onClick={onClose} className="p-1 hover:bg-slate-100 rounded">
            <X size={18} />
          </button>
        </div>
        <div className="overflow-y-auto p-6 space-y-3">
          {trace.trace.map((hop, i) => {
            const isPrimary = hop.event_id === trace.event.event_id
            return (
              <div key={hop.event_id} className={`relative pl-8 border-l-2 ${isPrimary ? 'border-blue-500' : 'border-slate-200'}`}>
                <div className={`absolute -left-2 top-0 w-4 h-4 rounded-full ${isPrimary ? 'bg-blue-500' : 'bg-slate-300'} ring-2 ring-white`} />
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-xs text-slate-400 font-mono">#{i + 1}</span>
                  <span className="font-semibold text-sm text-slate-800">{hop.event_type}</span>
                  <span className="badge badge-gray text-[10px]">{hop.event_category}</span>
                  {hop.channel && <span className="badge badge-blue text-[10px]">{hop.channel}</span>}
                  <span className="text-xs text-slate-400 ml-auto">{formatDateTime(hop.occurred_at)}</span>
                </div>
                <div className="text-xs text-slate-500 mt-1">
                  source: <code>{hop.source_service}</code>
                </div>
                {hop.payload && Object.keys(hop.payload).length > 0 && (
                  <details className="mt-1">
                    <summary className="text-xs text-blue-600 cursor-pointer">payload</summary>
                    <pre className="text-[10px] bg-slate-50 p-2 rounded mt-1 overflow-auto max-h-40">
                      {JSON.stringify(hop.payload, null, 2)}
                    </pre>
                  </details>
                )}
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

export default function PlatformOps() {
  const [traceId, setTraceId] = useState<string | null>(null)

  const { data: health } = useQuery({
    queryKey: ['platform-health'],
    queryFn: api.platformHealth,
    refetchInterval: 5000,
  })

  const { data: services } = useQuery({
    queryKey: ['platform-services'],
    queryFn: api.platformServices,
    refetchInterval: 5000,
  })

  const { data: topics } = useQuery({
    queryKey: ['platform-kafka-topics'],
    queryFn: api.platformKafkaTopics,
    refetchInterval: 5000,
  })

  const { data: lag } = useQuery({
    queryKey: ['platform-consumer-lag'],
    queryFn: api.platformConsumerLag,
    refetchInterval: 5000,
  })

  const { data: policies } = useQuery({
    queryKey: ['platform-opa-policies'],
    queryFn: api.platformOpaPolicies,
    refetchInterval: 30000,
  })

  const { data: decisions } = useQuery({
    queryKey: ['platform-opa-decisions'],
    queryFn: () => api.platformOpaDecisions(50),
    refetchInterval: 5000,
  })

  const { data: trace } = useQuery({
    queryKey: ['platform-trace', traceId],
    queryFn: () => api.platformTrace(traceId!),
    enabled: !!traceId,
  })

  const recentDecisions = decisions?.decisions ?? []

  const totalLag = useMemo(() => {
    return (lag?.consumer_groups ?? []).reduce((acc, g) => acc + (g.total_lag ?? g.partitions.reduce((s, p) => s + p.lag, 0)), 0)
  }, [lag])

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      <div className="px-6 py-4 border-b border-slate-200 bg-white">
        <div className="flex items-center gap-3">
          <Server size={22} className="text-slate-700" />
          <div>
            <h1 className="text-lg font-bold text-slate-800">Platform Operations</h1>
            <p className="text-xs text-slate-500">Live system health, Kafka topology, OPA decisions, end-to-end traces</p>
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        <div className="grid grid-cols-5 gap-3">
          <StatPill
            label="Events / sec"
            value={health ? health.events_per_sec_estimate.toFixed(1) : '—'}
            sub={health ? `${formatNumber(health.events_last_5m)} in last 5 min` : ''}
          />
          <StatPill
            label="Services"
            value={health ? `${health.services_healthy}/${health.services_total}` : '—'}
            sub="healthy"
            tone={health && health.services_healthy === health.services_total ? 'good' : 'warn'}
          />
          <StatPill
            label="Kafka topics"
            value={health ? String(health.kafka_topics) : '—'}
            sub="orchestrating"
          />
          <StatPill
            label="OPA policies"
            value={policies ? String(policies.count) : '—'}
            sub="loaded"
          />
          <StatPill
            label="Total consumer lag"
            value={lag ? formatNumber(totalLag) : '—'}
            sub="messages"
            tone={totalLag > 100 ? 'bad' : totalLag > 0 ? 'warn' : 'good'}
          />
        </div>

        <section>
          <h2 className="text-sm font-bold text-slate-700 mb-3 flex items-center gap-2">
            <Activity size={16} /> Service topology
          </h2>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
            {(services?.services ?? []).map((s) => (
              <ServiceCard key={s.service_name} s={s} />
            ))}
            {(services?.services ?? []).length === 0 && (
              <div className="col-span-4 text-sm text-slate-400 text-center py-6">
                No heartbeats yet — services starting up.
              </div>
            )}
          </div>
        </section>

        <section>
          <h2 className="text-sm font-bold text-slate-700 mb-3 flex items-center gap-2">
            <Layers size={16} /> Kafka topics
          </h2>
          <div className="bg-white rounded-lg border border-slate-200 overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-[10px] uppercase tracking-wider text-slate-500">
                <tr>
                  <th className="text-left px-3 py-2">Topic</th>
                  <th className="text-left px-3 py-2">Partitions</th>
                  <th className="text-left px-3 py-2">Messages</th>
                  <th className="text-left px-3 py-2">Throughput</th>
                  <th className="text-left px-3 py-2">Per-partition end offset</th>
                </tr>
              </thead>
              <tbody>
                {(topics?.topics ?? []).map((t) => (
                  <TopicRow key={t.topic} t={t} />
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="grid grid-cols-2 gap-6">
          <div>
            <h2 className="text-sm font-bold text-slate-700 mb-3 flex items-center gap-2">
              <Database size={16} /> Consumer lag by group
            </h2>
            <div className="space-y-3">
              {(lag?.consumer_groups ?? []).map((g) => (
                <ConsumerLagRow key={g.group_id} g={g} />
              ))}
              {(lag?.consumer_groups ?? []).length === 0 && (
                <p className="text-sm text-slate-400">No consumer groups detected yet.</p>
              )}
            </div>
          </div>

          <div>
            <h2 className="text-sm font-bold text-slate-700 mb-3 flex items-center gap-2">
              <Cpu size={16} /> OPA decision feed
            </h2>
            <div className="bg-white border border-slate-200 rounded-lg max-h-[400px] overflow-y-auto">
              {recentDecisions.length === 0 ? (
                <p className="p-4 text-sm text-slate-400">No decisions yet.</p>
              ) : (
                recentDecisions.map((d) => (
                  <DecisionFeedRow key={d.audit_id} d={d} onClick={() => { /* future: open detail */ }} />
                ))
              )}
            </div>
          </div>
        </section>

        <section>
          <h2 className="text-sm font-bold text-slate-700 mb-3 flex items-center gap-2">
            <Search size={16} /> Trace event end-to-end
          </h2>
          <div className="bg-white border border-slate-200 rounded-lg p-4 flex items-center gap-3">
            <input
              className="flex-1 border border-slate-200 rounded px-3 py-2 text-sm font-mono"
              placeholder="paste an event_id or correlation_id..."
              value={traceId ?? ''}
              onChange={(e) => setTraceId(e.target.value || null)}
            />
            <button
              className="btn btn-primary text-sm px-4 py-2"
              disabled={!traceId}
              onClick={() => { /* query is keyed on traceId, already firing */ }}
            >
              Trace
            </button>
          </div>
          {trace && trace.event && (
            <TraceView trace={trace} onClose={() => setTraceId(null)} />
          )}
        </section>
      </div>
    </div>
  )
}
