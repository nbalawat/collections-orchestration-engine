import { useState, useMemo } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type {
  LakehouseTopology, SilverPartition, GoldMart, SavedQuery, QueryResult, S3Object,
} from '@/lib/api'
import {
  Database, Layers, Activity, Play, RefreshCw, ArrowRight,
  Archive, Filter, BarChart3, Hash,
} from 'lucide-react'
import { DataLineage } from '@/components/DataLineage'

function formatBytes(b: number): string {
  if (!b) return '0 B'
  if (b < 1024) return `${b} B`
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`
  if (b < 1024 * 1024 * 1024) return `${(b / (1024 * 1024)).toFixed(1)} MB`
  return `${(b / (1024 * 1024 * 1024)).toFixed(2)} GB`
}

function TierCard({ tier, icon, label, color }: {
  tier: { bucket: string | null; object_count: number; total_bytes: number; per_topic?: Record<string, { objects: number; bytes: number }> };
  icon: React.ReactNode; label: string; color: string;
}) {
  const topics = tier.per_topic ? Object.entries(tier.per_topic).slice(0, 8) : []
  return (
    <div className={`border rounded-lg ${color}`}>
      <div className="p-3 border-b border-slate-200/50">
        <div className="flex items-center gap-2">
          {icon}
          <h3 className="text-sm font-bold text-slate-800">{label}</h3>
        </div>
        <code className="text-[10px] text-slate-500 block mt-0.5">s3://{tier.bucket ?? '(not configured)'}</code>
      </div>
      <div className="p-3 grid grid-cols-2 gap-2">
        <div>
          <div className="text-[10px] uppercase tracking-wider text-slate-500">Objects</div>
          <div className="text-2xl font-bold text-slate-800">{tier.object_count}</div>
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-wider text-slate-500">Size</div>
          <div className="text-2xl font-bold text-slate-800">{formatBytes(tier.total_bytes)}</div>
        </div>
      </div>
      {topics.length > 0 && (
        <div className="border-t border-slate-200/50 p-3">
          <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-1.5">Top topics</div>
          <div className="space-y-1">
            {topics.map(([topic, m]) => (
              <div key={topic} className="flex items-center justify-between text-xs">
                <code className="text-slate-700 truncate">{topic}</code>
                <span className="text-slate-500">{m.objects} · {formatBytes(m.bytes)}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function FlowArrow() {
  return (
    <div className="flex items-center justify-center text-slate-400 px-1">
      <ArrowRight size={20} />
    </div>
  )
}

function QueryResultsTable({ result }: { result: QueryResult }) {
  return (
    <div className="border border-slate-200 rounded-lg overflow-hidden">
      <div className="bg-slate-50 px-3 py-1.5 text-[11px] flex items-center gap-3 border-b border-slate-200">
        <span className="text-slate-600">{result.rows.length} rows</span>
        <span className="text-slate-400">·</span>
        <span className="text-slate-600">{result.elapsed_ms}ms (DuckDB)</span>
      </div>
      <div className="overflow-x-auto max-h-96 overflow-y-auto">
        <table className="w-full text-xs">
          <thead className="bg-slate-50 text-[10px] uppercase tracking-wider text-slate-500 sticky top-0">
            <tr>
              {result.columns.map((c) => (
                <th key={c} className="text-left px-3 py-1.5 border-b border-slate-200">{c}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {result.rows.map((row, i) => (
              <tr key={i} className="border-b border-slate-100 hover:bg-slate-50">
                {result.columns.map((c) => {
                  const v = row[c]
                  const display = v == null ? '—' :
                    typeof v === 'object' ? JSON.stringify(v) : String(v)
                  return (
                    <td key={c} className="px-3 py-1.5 text-slate-700 font-mono truncate max-w-xs">{display}</td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default function Lakehouse() {
  const [sql, setSql] = useState('')
  const [queryResult, setQueryResult] = useState<QueryResult | null>(null)
  const [queryError, setQueryError] = useState<string | null>(null)

  const { data: topology } = useQuery({
    queryKey: ['lakehouse-topology'],
    queryFn: api.lakehouseTopology,
    refetchInterval: 8000,
  })

  const { data: bronzeObjects } = useQuery({
    queryKey: ['lakehouse-bronze'],
    queryFn: () => api.lakehouseBronzeObjects(undefined, 12),
    refetchInterval: 10000,
  })

  const { data: silverPartitions } = useQuery({
    queryKey: ['lakehouse-silver'],
    queryFn: api.lakehouseSilverPartitions,
    refetchInterval: 20000,
  })

  const { data: gold } = useQuery({
    queryKey: ['lakehouse-gold'],
    queryFn: api.lakehouseGoldMarts,
    refetchInterval: 30000,
  })

  const { data: savedQueries } = useQuery({
    queryKey: ['lakehouse-queries'],
    queryFn: api.lakehouseSavedQueries,
  })

  const queryMutation = useMutation({
    mutationFn: () => api.lakehouseQuery(sql, 200),
    onSuccess: (data) => { setQueryResult(data); setQueryError(null) },
    onError: (err: unknown) => {
      setQueryResult(null)
      setQueryError(err instanceof Error ? err.message : String(err))
    },
  })

  const bronze = topology?.tiers?.bronze
  const silver = topology?.tiers?.silver
  const goldTier = topology?.tiers?.gold

  const recentBronze = useMemo(() => bronzeObjects?.objects ?? [], [bronzeObjects])

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      <div className="px-6 py-3 border-b border-slate-200 bg-white">
        <div className="flex items-center gap-3">
          <Database size={22} className="text-indigo-600" />
          <div>
            <h1 className="text-lg font-bold text-slate-800">Data Lakehouse</h1>
            <p className="text-xs text-slate-500">
              Real AWS S3 medallion architecture · Kafka → bronze (raw) → silver (typed Parquet) → gold (curated marts) · queryable from DuckDB
            </p>
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        <section>
          <h2 className="text-sm font-bold text-slate-700 mb-3 flex items-center gap-2">
            <Layers size={16} /> Medallion topology
          </h2>
          <div className="grid grid-cols-[1fr_auto_1fr_auto_1fr] items-stretch gap-2">
            {bronze && <TierCard tier={bronze} icon={<Archive size={14} className="text-amber-700" />} label="Bronze · raw landing" color="bg-amber-50 border-amber-200" />}
            <FlowArrow />
            {silver && <TierCard tier={silver} icon={<Filter size={14} className="text-slate-600" />} label="Silver · typed Parquet" color="bg-slate-50 border-slate-300" />}
            <FlowArrow />
            {goldTier && <TierCard tier={goldTier} icon={<BarChart3 size={14} className="text-yellow-700" />} label="Gold · business marts" color="bg-yellow-50 border-yellow-300" />}
          </div>
          <div className="mt-2 text-[11px] text-slate-500 flex items-center gap-1">
            <Activity size={11} />
            <span>Kafka spine → Lake Sink (group <code>lake-sink-bronze</code>) writes gzipped JSONL hourly; Silver Compactor reads bronze, dedupes by event_id, writes Parquet; Gold Builder runs DuckDB SQL across silver to produce curated marts.</span>
          </div>
        </section>

        <DataLineage />

        <section className="grid grid-cols-2 gap-6">
          <div>
            <h2 className="text-sm font-bold text-slate-700 mb-3 flex items-center gap-2">
              <Archive size={16} className="text-amber-700" /> Recent bronze objects
            </h2>
            <div className="bg-white border border-slate-200 rounded-lg overflow-hidden">
              <table className="w-full text-xs">
                <thead className="bg-slate-50 text-[10px] uppercase tracking-wider text-slate-500">
                  <tr>
                    <th className="text-left px-3 py-1.5">Object key</th>
                    <th className="text-right px-3 py-1.5">Size</th>
                    <th className="text-right px-3 py-1.5">Last modified</th>
                  </tr>
                </thead>
                <tbody>
                  {recentBronze.map((o: S3Object) => (
                    <tr key={o.key} className="border-t border-slate-100">
                      <td className="px-3 py-1.5 text-slate-700 font-mono text-[10px] truncate max-w-md">{o.key}</td>
                      <td className="px-3 py-1.5 text-right text-slate-600">{formatBytes(o.size)}</td>
                      <td className="px-3 py-1.5 text-right text-slate-500 text-[10px]">{new Date(o.last_modified).toLocaleTimeString()}</td>
                    </tr>
                  ))}
                  {recentBronze.length === 0 && (
                    <tr><td colSpan={3} className="p-4 text-sm text-slate-400 text-center">No bronze objects yet.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          <div>
            <h2 className="text-sm font-bold text-slate-700 mb-3 flex items-center gap-2">
              <Filter size={16} className="text-slate-600" /> Silver partitions
            </h2>
            <div className="bg-white border border-slate-200 rounded-lg overflow-hidden">
              <table className="w-full text-xs">
                <thead className="bg-slate-50 text-[10px] uppercase tracking-wider text-slate-500">
                  <tr>
                    <th className="text-left px-3 py-1.5">Topic</th>
                    <th className="text-left px-3 py-1.5">Date</th>
                    <th className="text-right px-3 py-1.5">Rows</th>
                    <th className="text-right px-3 py-1.5">Size</th>
                  </tr>
                </thead>
                <tbody>
                  {(silverPartitions?.partitions ?? []).slice(0, 12).map((p: SilverPartition) => (
                    <tr key={p.key} className="border-t border-slate-100">
                      <td className="px-3 py-1.5 text-slate-700 font-mono text-[10px]">{p.topic}</td>
                      <td className="px-3 py-1.5 text-slate-500 text-[10px]">{p.date}</td>
                      <td className="px-3 py-1.5 text-right text-slate-700">{p.rows_hint}</td>
                      <td className="px-3 py-1.5 text-right text-slate-600">{formatBytes(p.size)}</td>
                    </tr>
                  ))}
                  {(silverPartitions?.partitions ?? []).length === 0 && (
                    <tr><td colSpan={4} className="p-4 text-sm text-slate-400 text-center">No silver partitions yet.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </section>

        <section>
          <h2 className="text-sm font-bold text-slate-700 mb-3 flex items-center gap-2">
            <BarChart3 size={16} className="text-yellow-700" /> Gold marts
            {gold?.manifest?.last_run_at && (
              <span className="text-[11px] text-slate-500 font-normal ml-2">
                last built {new Date(gold.manifest.last_run_at).toLocaleTimeString()} · build #{gold.manifest.build_number}
              </span>
            )}
          </h2>
          <div className="grid grid-cols-2 gap-3">
            {(gold?.marts ?? []).map((m: GoldMart) => (
              <div key={m.mart} className="bg-white border border-slate-200 rounded-lg p-3">
                <div className="flex items-center justify-between">
                  <code className="text-sm font-bold text-slate-800">{m.mart}</code>
                  <div className="text-[10px] text-slate-500">{m.row_count} rows · {formatBytes(m.size_bytes)}</div>
                </div>
                {m.sample.length > 0 && (
                  <div className="mt-2 overflow-x-auto">
                    <table className="w-full text-[10px]">
                      <thead>
                        <tr>
                          {Object.keys(m.sample[0]).slice(0, 5).map((c) => (
                            <th key={c} className="text-left text-[9px] uppercase tracking-wider text-slate-500 px-1.5 py-1">{c}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {m.sample.slice(0, 3).map((row, ri) => (
                          <tr key={ri} className="border-t border-slate-100">
                            {Object.keys(m.sample[0]).slice(0, 5).map((c) => {
                              const v = row[c]
                              const display = v == null ? '—' : typeof v === 'object' ? JSON.stringify(v).slice(0, 30) : String(v).slice(0, 30)
                              return (
                                <td key={c} className="px-1.5 py-1 text-slate-700 font-mono truncate">{display}</td>
                              )
                            })}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            ))}
          </div>
        </section>

        <section>
          <h2 className="text-sm font-bold text-slate-700 mb-3 flex items-center gap-2">
            <Hash size={16} /> Ad-hoc query · DuckDB over S3 Parquet
          </h2>
          <div className="bg-white border border-slate-200 rounded-lg p-3">
            <div className="flex items-center justify-between gap-3 mb-2 flex-wrap">
              <div className="flex flex-wrap gap-1">
                {(savedQueries?.queries ?? []).map((q: SavedQuery) => (
                  <button
                    key={q.id}
                    onClick={() => { setSql(q.sql); setQueryError(null) }}
                    className="text-[10px] px-2 py-1 rounded bg-slate-100 text-slate-700 hover:bg-slate-200"
                  >
                    {q.label}
                  </button>
                ))}
              </div>
              <button
                className="btn btn-primary text-xs px-3 py-1 flex items-center gap-1"
                disabled={queryMutation.isPending || !sql.trim()}
                onClick={() => queryMutation.mutate()}
              >
                {queryMutation.isPending ? (
                  <><RefreshCw size={12} className="animate-spin" /> running…</>
                ) : (
                  <><Play size={12} /> run query</>
                )}
              </button>
            </div>
            <textarea
              className="w-full h-32 font-mono text-xs border border-slate-200 rounded p-2 bg-slate-50"
              placeholder="SELECT ... FROM read_parquet('s3://…/topic=events.decisions/date=*/part-*.parquet') ..."
              value={sql}
              onChange={(e) => setSql(e.target.value)}
            />
            {queryError && (
              <div className="mt-2 p-2 bg-red-50 border border-red-200 rounded text-xs text-red-700 font-mono">
                {queryError}
              </div>
            )}
            {queryResult && (
              <div className="mt-3">
                <QueryResultsTable result={queryResult} />
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  )
}
