import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type {
  EventLineage, LineageSuggestion, LineageGoldContribution,
} from '@/lib/api'
import {
  Hash, ArrowRight, Database, MessageSquare, Radio, Archive, Filter,
  BarChart3, Search, RefreshCw, CheckCircle, AlertTriangle, Layers,
  Cpu, FileText, Brain,
} from 'lucide-react'
import { formatTime } from '@/lib/utils'

function formatBytes(b: number | undefined): string {
  if (!b) return '0 B'
  if (b < 1024) return `${b} B`
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`
  return `${(b / (1024 * 1024)).toFixed(2)} MB`
}

function Station({
  icon, label, tech, color, found, location, children,
}: {
  icon: React.ReactNode; label: string; tech: string; color: string;
  found?: boolean; location?: string; children?: React.ReactNode;
}) {
  return (
    <div className={`flex flex-col border-2 rounded-xl ${color} min-w-[230px] max-w-[230px] shrink-0`}>
      <div className="px-3 py-2 border-b border-current/10">
        <div className="flex items-center gap-2">
          {icon}
          <span className="text-sm font-bold text-slate-800">{label}</span>
          {found === true && <CheckCircle size={12} className="text-emerald-600 ml-auto" />}
          {found === false && <AlertTriangle size={12} className="text-amber-600 ml-auto" />}
        </div>
        <div className="text-[10px] text-slate-500 mt-0.5">{tech}</div>
      </div>
      {location && (
        <div className="px-3 py-1.5 border-b border-current/10 bg-white/40">
          <div className="text-[9px] uppercase tracking-wider text-slate-500">location</div>
          <code className="text-[10px] text-slate-700 break-all leading-tight block">{location}</code>
        </div>
      )}
      <div className="px-3 py-2 text-[11px] text-slate-700 leading-relaxed flex-1">
        {children}
      </div>
    </div>
  )
}

function FlowEdge({ label }: { label: string }) {
  return (
    <div className="flex flex-col items-center justify-center shrink-0 px-1 py-12">
      <ArrowRight size={20} className="text-slate-400" />
      <div className="text-[9px] uppercase tracking-wider text-slate-500 mt-1 max-w-[80px] text-center leading-tight">{label}</div>
    </div>
  )
}

function CollapsibleJSON({ label, data }: { label: string; data: unknown }) {
  const [open, setOpen] = useState(false)
  if (!data || (typeof data === 'object' && Object.keys(data as object).length === 0)) {
    return null
  }
  return (
    <details className="mt-1.5" open={open} onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}>
      <summary className="text-[10px] text-blue-600 cursor-pointer">{label}</summary>
      <pre className="text-[9px] mt-1 bg-white/70 border border-slate-200 rounded p-1.5 overflow-auto max-h-40 leading-tight">
        {JSON.stringify(data, null, 2)}
      </pre>
    </details>
  )
}

export function DataLineage() {
  const [eventId, setEventId] = useState('')
  const [submitted, setSubmitted] = useState<string | null>(null)

  const { data: suggestions } = useQuery({
    queryKey: ['lineage-suggestions'],
    queryFn: () => api.lakehouseLineageSuggestions(10),
    refetchInterval: 15000,
  })

  const { data: lineage, isFetching, error, refetch } = useQuery({
    queryKey: ['lineage', submitted],
    queryFn: () => api.lakehouseLineage(submitted!),
    enabled: !!submitted,
  })

  const pickSuggestion = (sug: LineageSuggestion) => {
    setEventId(sug.event_id)
    setSubmitted(sug.event_id)
  }

  const submit = () => {
    if (eventId.trim()) setSubmitted(eventId.trim())
  }

  const k = lineage?.tiers.kafka
  const p = lineage?.tiers.postgres
  const r = lineage?.tiers.redis
  const b = lineage?.tiers.bronze
  const sl = lineage?.tiers.silver
  const g = lineage?.tiers.gold

  return (
    <section>
      <h2 className="text-sm font-bold text-slate-700 mb-3 flex items-center gap-2">
        <Layers size={16} className="text-indigo-600" />
        Data lineage · trace one event through every tier
      </h2>

      <div className="bg-white border border-slate-200 rounded-lg p-3 space-y-3">
        <div className="flex items-center gap-2 flex-wrap">
          <Search size={14} className="text-slate-500" />
          <input
            className="flex-1 min-w-[300px] px-3 py-1.5 border border-slate-200 rounded font-mono text-xs"
            placeholder="paste an event_id (UUID) or pick a recent one →"
            value={eventId}
            onChange={(e) => setEventId(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') submit() }}
          />
          <button
            className="btn btn-primary text-xs px-3 py-1.5 flex items-center gap-1"
            onClick={submit}
            disabled={!eventId.trim() || isFetching}
          >
            {isFetching ? <><RefreshCw size={12} className="animate-spin" /> tracing…</> : <><Hash size={12} /> trace lineage</>}
          </button>
          {submitted && (
            <button
              className="text-xs px-2 py-1 text-slate-500 hover:text-slate-700"
              onClick={() => refetch()}
            >refresh</button>
          )}
        </div>

        <div>
          <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-1.5">
            Recent events from the orchestrator · click to trace
          </div>
          <div className="flex flex-wrap gap-1.5">
            {(suggestions?.suggestions ?? []).map((sug) => (
              <button
                key={sug.event_id}
                onClick={() => pickSuggestion(sug)}
                className={`text-[10px] px-2 py-1 rounded border ${
                  submitted === sug.event_id
                    ? 'bg-indigo-100 border-indigo-300 text-indigo-800'
                    : 'bg-slate-50 border-slate-200 text-slate-700 hover:border-indigo-200 hover:bg-indigo-50'
                }`}
              >
                <span className="font-mono">{sug.event_type}</span>
                <span className="text-slate-400 ml-1">{sug.customer_id}</span>
                {sug.linked_agent_actions > 0 && (
                  <span className="ml-1 text-purple-600">· {sug.linked_agent_actions} AI</span>
                )}
                <span className="ml-1 text-slate-400">{formatTime(sug.occurred_at)}</span>
              </button>
            ))}
          </div>
        </div>

        {error && (
          <div className="bg-red-50 border border-red-200 rounded p-2 text-xs text-red-700">
            {String(error)}
          </div>
        )}

        {lineage && (
          <>
            <div className="bg-gradient-to-r from-indigo-50 to-blue-50 border border-indigo-200 rounded-lg p-3">
              <div className="flex items-center gap-3 flex-wrap text-xs">
                <Hash size={12} className="text-indigo-600" />
                <code className="font-mono text-slate-800">{lineage.event_id}</code>
                <span className="text-slate-400">·</span>
                <span>customer <code className="font-mono">{lineage.customer_id}</code></span>
                <span className="text-slate-400">·</span>
                <span>topic <code className="font-mono">{lineage.topic}</code></span>
                {lineage.correlation_id && (
                  <>
                    <span className="text-slate-400">·</span>
                    <span>trace <code className="font-mono">{lineage.correlation_id.slice(0, 8)}…</code></span>
                  </>
                )}
                <span className="ml-auto text-slate-500">@ {new Date(lineage.occurred_at).toLocaleString()}</span>
              </div>
            </div>

            <div className="overflow-x-auto pb-2">
              <div className="flex items-stretch">
                <Station
                  icon={<MessageSquare size={14} className="text-slate-600" />}
                  label="Kafka"
                  tech="event spine · partitioned topic"
                  color="bg-slate-50 border-slate-300"
                  found={true}
                  location={k ? `topic = ${k.topic}\nkey = ${k.key}` : undefined}
                >
                  <div className="space-y-1">
                    <div className="flex justify-between"><span className="text-slate-500">partitions</span><span>{k?.topic_partitions}</span></div>
                    <div className="flex justify-between"><span className="text-slate-500">retention</span><span>{k?.retention_hours}h</span></div>
                    <div className="text-[10px] text-slate-500 mt-1.5 leading-snug">{k?.key_purpose}</div>
                  </div>
                </Station>

                <FlowEdge label="signal-bridge + event-projector + lake-sink (3 consumer groups)" />

                <Station
                  icon={<Database size={14} className="text-blue-600" />}
                  label="Postgres"
                  tech="OLTP audit-of-record"
                  color="bg-blue-50 border-blue-300"
                  found={true}
                  location={p ? `${p.database}.${p.table}\npk = ${p.primary_key?.slice(0, 8)}…` : undefined}
                >
                  <div className="space-y-1">
                    <div className="flex items-center gap-1">
                      <span className="text-emerald-700 font-semibold">{p?.audit_status}</span>
                    </div>
                    <div className="text-[10px] text-slate-500 leading-snug">{p?.audit_note}</div>
                    <CollapsibleJSON label="see full row" data={p?.row} />
                  </div>
                </Station>

                <FlowEdge label="real-time pub/sub" />

                <Station
                  icon={<Radio size={14} className="text-red-500" />}
                  label="Redis"
                  tech="pub/sub fan-out"
                  color="bg-red-50 border-red-300"
                  found={true}
                  location={r?.channels.join('\n')}
                >
                  <div className="space-y-1">
                    <div className="text-[10px] text-slate-500 leading-snug">{r?.purpose}</div>
                    <div className="flex justify-between"><span className="text-slate-500">ttl</span><span>{r?.ttl}</span></div>
                  </div>
                </Station>

                <FlowEdge label="lake-sink · gzip JSONL · 30s flush" />

                <Station
                  icon={<Archive size={14} className="text-amber-700" />}
                  label="Bronze (S3)"
                  tech="raw landing · gzip ndjson"
                  color="bg-amber-50 border-amber-300"
                  found={b?.found}
                  location={b?.key}
                >
                  {b?.found ? (
                    <div className="space-y-1">
                      <div className="flex justify-between"><span className="text-slate-500">line</span><span>{b.line_number} of {b.events_in_file}</span></div>
                      <div className="flex justify-between"><span className="text-slate-500">file size</span><span>{formatBytes(b.object_size_bytes)}</span></div>
                      <div className="flex justify-between"><span className="text-slate-500">format</span><span>{b.format} + {b.compression}</span></div>
                      <CollapsibleJSON label="see raw bronze record" data={b.raw_record} />
                    </div>
                  ) : (
                    <div className="text-[10px] text-amber-700">
                      Not yet flushed to bronze. The lake-sink buffers up to 30s or 500 events before writing.
                      <div className="mt-1 text-slate-500">Search partition: {b?.partition}</div>
                    </div>
                  )}
                </Station>

                <FlowEdge label="silver compactor · 120s · pyarrow + snappy" />

                <Station
                  icon={<Filter size={14} className="text-slate-700" />}
                  label="Silver (S3)"
                  tech="typed Parquet · deduplicated"
                  color="bg-slate-100 border-slate-400"
                  found={sl?.found}
                  location={sl?.partition_pattern}
                >
                  {sl?.found ? (
                    <div className="space-y-1">
                      <div className="text-[10px] text-slate-500 leading-snug">{sl.row_format}</div>
                      <div className="text-[10px] text-slate-500 leading-snug">{sl.schema_note}</div>
                      <CollapsibleJSON label="see Parquet row (DuckDB)" data={sl.row} />
                    </div>
                  ) : (
                    <div className="text-[10px] text-slate-600">
                      Not yet compacted. Silver compactor runs every 120s.
                      {sl?.error && <div className="text-red-600 mt-1">err: {sl.error}</div>}
                    </div>
                  )}
                </Station>

                <FlowEdge label="gold builder · DuckDB SQL · 300s" />

                <Station
                  icon={<BarChart3 size={14} className="text-yellow-700" />}
                  label="Gold (S3)"
                  tech="curated marts · aggregated"
                  color="bg-yellow-50 border-yellow-400"
                  found={(g?.contributions.length ?? 0) > 0}
                  location={g?.bucket}
                >
                  <div className="space-y-1.5">
                    {(g?.contributions ?? []).map((c: LineageGoldContribution, i: number) => (
                      <div key={i} className="bg-white/60 border border-yellow-300 rounded p-1.5">
                        <div className="font-mono text-[10px] text-slate-800">{c.mart}</div>
                        <div className="flex flex-wrap gap-1 mt-0.5">
                          {c.columns.map((col) => (
                            <span key={col} className="text-[9px] bg-yellow-200/60 px-1 py-0.5 rounded">{col}</span>
                          ))}
                        </div>
                      </div>
                    ))}
                    {(g?.contributions.length ?? 0) === 0 && (
                      <div className="text-[10px] text-slate-500">No marts include this topic.</div>
                    )}
                  </div>
                </Station>
              </div>
            </div>

            {(lineage.downstream.related_events.length > 0 ||
              lineage.downstream.agent_actions.length > 0 ||
              lineage.downstream.escalations.length > 0) && (
              <div className="bg-purple-50 border border-purple-200 rounded-lg p-3">
                <div className="flex items-center gap-2 mb-2">
                  <Brain size={14} className="text-purple-600" />
                  <span className="text-xs font-bold text-purple-800">
                    Downstream of this event · shared correlation_id
                    {lineage.correlation_id && (
                      <code className="font-mono text-[10px] ml-2 text-purple-600">{lineage.correlation_id}</code>
                    )}
                  </span>
                </div>
                <div className="grid grid-cols-3 gap-3 text-xs">
                  <div>
                    <div className="text-[10px] uppercase tracking-wider text-purple-700 mb-1">Related events · {lineage.downstream.related_events.length}</div>
                    <div className="space-y-0.5 max-h-32 overflow-auto">
                      {lineage.downstream.related_events.map((evt: Record<string, unknown>, i: number) => (
                        <div key={i} className="text-[10px] text-slate-700 truncate">
                          <code className="font-mono">{String(evt.event_type)}</code>
                          <span className="text-slate-400 ml-1">{String(evt.event_category)}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                  <div>
                    <div className="text-[10px] uppercase tracking-wider text-purple-700 mb-1">AI actions · {lineage.downstream.agent_actions.length}</div>
                    <div className="space-y-0.5 max-h-32 overflow-auto">
                      {lineage.downstream.agent_actions.map((a: Record<string, unknown>, i: number) => (
                        <div key={i} className="text-[10px] text-slate-700">
                          <code className="font-mono">{String(a.action_type)}</code>
                          <span className="text-slate-400 ml-1">{Math.round((Number(a.confidence) || 0) * 100)}%</span>
                        </div>
                      ))}
                      {lineage.downstream.agent_actions.length === 0 && (
                        <div className="text-[10px] text-slate-400">none</div>
                      )}
                    </div>
                  </div>
                  <div>
                    <div className="text-[10px] uppercase tracking-wider text-purple-700 mb-1">Escalations · {lineage.downstream.escalations.length}</div>
                    <div className="space-y-0.5 max-h-32 overflow-auto">
                      {lineage.downstream.escalations.map((e: Record<string, unknown>, i: number) => (
                        <div key={i} className="text-[10px] text-slate-700 truncate">
                          <span className="badge text-[9px]">{String(e.urgency)}</span>
                          <span className="ml-1 text-slate-500">{String(e.status)}</span>
                        </div>
                      ))}
                      {lineage.downstream.escalations.length === 0 && (
                        <div className="text-[10px] text-slate-400">none</div>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </section>
  )
}
