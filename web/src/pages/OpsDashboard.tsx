import { useQuery } from '@tanstack/react-query'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts'
import { api } from '@/lib/api'
import { formatCurrency, formatNumber } from '@/lib/utils'
import { useWebSocket } from '@/hooks/useWebSocket'
import { Activity, DollarSign, Users, AlertTriangle, TrendingUp } from 'lucide-react'

const COLORS = ['#3b82f6', '#f59e0b', '#ef4444', '#8b5cf6', '#10b981']

export default function OpsDashboard() {
  const { data: metrics } = useQuery({ queryKey: ['dashboard'], queryFn: api.dashboardMetrics })
  const { data: activity } = useQuery({ queryKey: ['channel-activity'], queryFn: () => api.channelActivity(30) })
  const { events, connected } = useWebSocket('/ws/events/all', 50)

  const summary = metrics?.summary
  const breakdown = metrics?.delinquency?.breakdown ?? []

  const chartData = breakdown.map((b) => ({
    name: b.delinquency_stage.replace('_', ' '),
    count: b.count,
    balance: b.total_balance,
  }))

  const pieData = summary
    ? [
        { name: '1-29 DPD', value: summary.bucket_1_29 },
        { name: '30-59 DPD', value: summary.bucket_30_59 },
        { name: '60-89 DPD', value: summary.bucket_60_89 },
        { name: '90+ DPD', value: summary.bucket_90_plus },
      ]
    : []

  return (
    <div className="p-6 space-y-6 flex-1 overflow-y-auto overflow-x-hidden min-w-0">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold text-slate-800">Operations Dashboard</h2>
        <div className="flex items-center gap-2 text-sm">
          <span className={`w-2.5 h-2.5 rounded-full ${connected ? 'bg-green-500' : 'bg-red-500'} pulse-dot`} />
          <span className={connected ? 'text-green-600 font-medium' : 'text-red-500 font-medium'}>{connected ? 'Live' : 'Disconnected'}</span>
        </div>
      </div>

      {/* Stat Cards — 3+2 layout for breathing room */}
      {summary && (
        <div className="space-y-4">
          <div className="grid grid-cols-3 gap-4">
            <StatCard icon={<Users size={20} />} label="Total Customers" value={formatNumber(summary.total_customers)} color="blue" />
            <StatCard icon={<DollarSign size={20} />} label="Total Outstanding" value={formatCurrency(summary.total_outstanding)} color="green" />
            <StatCard icon={<AlertTriangle size={20} />} label="Total Past Due" value={formatCurrency(summary.total_past_due)} color="red" />
          </div>
          <div className="grid grid-cols-3 gap-4">
            <StatCard icon={<TrendingUp size={20} />} label="Avg Days Past Due" value={`${Math.round(summary.avg_dpd)} days`} color="yellow" />
            <StatCard icon={<Activity size={20} />} label="Active Accounts" value={formatNumber(summary.total_accounts)} color="purple" />
            <StatCard icon={<DollarSign size={20} />} label="Recovery Rate" value="—" color="green" subtitle="No payments yet" />
          </div>
        </div>
      )}

      {/* Charts Row */}
      <div className="grid grid-cols-2 gap-6">
        <div className="card">
          <h3 className="text-sm font-semibold text-slate-700 mb-4">Delinquency Distribution</h3>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={chartData} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
              <XAxis dataKey="name" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip formatter={(v) => formatNumber(Number(v))} />
              <Bar dataKey="count" fill="#3b82f6" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="card">
          <h3 className="text-sm font-semibold text-slate-700 mb-4">DPD Bucket Breakdown</h3>
          <div className="flex items-center gap-6">
            <div className="w-48 h-48 shrink-0">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={pieData} cx="50%" cy="50%" innerRadius={40} outerRadius={70} dataKey="value" paddingAngle={2} strokeWidth={0}>
                    {pieData.map((_, i) => (
                      <Cell key={i} fill={COLORS[i % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(v) => formatNumber(Number(v))} />
                </PieChart>
              </ResponsiveContainer>
            </div>
            <div className="flex-1 space-y-3">
              {pieData.map((d, i) => (
                <div key={d.name} className="flex items-center gap-2">
                  <span className="w-3 h-3 rounded-sm shrink-0" style={{ backgroundColor: COLORS[i] }} />
                  <span className="text-sm text-slate-600">{d.name}</span>
                  <span className="text-sm font-bold text-slate-800">({d.value})</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Live Events Feed */}
      <div className="card">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-slate-700">Live Event Feed</h3>
          {events.length > 0 && <span className="text-xs text-slate-400">{events.length} events</span>}
        </div>
        <div className="max-h-64 overflow-auto">
          {events.length === 0 ? (
            <div className="text-center py-8">
              <Activity size={32} className="mx-auto text-slate-300 mb-2" />
              <p className="text-sm text-slate-400">Waiting for events...</p>
              <p className="text-xs text-slate-300 mt-1">Run a scenario or start services to see live events</p>
            </div>
          ) : (
            <table className="table">
              <thead>
                <tr>
                  <th>Customer</th>
                  <th>Type</th>
                  <th>Category</th>
                  <th>Channel</th>
                </tr>
              </thead>
              <tbody>
                {events.slice(0, 20).map((e, i) => (
                  <tr key={i}>
                    <td className="font-mono text-xs">{e.customer_id || '-'}</td>
                    <td>{String(e.event_type || '-')}</td>
                    <td><span className="badge badge-blue">{String(e.category || '-')}</span></td>
                    <td>{String(e.topic || '-').split('.').pop()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* Channel Activity */}
      {activity && activity.activity.length > 0 && (
        <div className="card">
          <h3 className="text-sm font-semibold text-slate-700 mb-3">Channel Activity (30 days)</h3>
          <table className="table">
            <thead>
              <tr>
                <th>Channel</th>
                <th>Direction</th>
                <th>Category</th>
                <th>Events</th>
                <th>Unique Customers</th>
              </tr>
            </thead>
            <tbody>
              {activity.activity.map((a, i) => (
                <tr key={i}>
                  <td className="font-medium">{a.channel}</td>
                  <td>{a.direction}</td>
                  <td><span className="badge badge-gray">{a.event_category}</span></td>
                  <td>{formatNumber(a.event_count)}</td>
                  <td>{formatNumber(a.unique_customers)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function StatCard({ icon, label, value, color, subtitle }: { icon: React.ReactNode; label: string; value: string; color: string; subtitle?: string }) {
  const colorMap: Record<string, string> = {
    blue: 'text-blue-600 bg-blue-50',
    green: 'text-green-600 bg-green-50',
    red: 'text-red-600 bg-red-50',
    yellow: 'text-amber-600 bg-amber-50',
    purple: 'text-purple-600 bg-purple-50',
  }
  return (
    <div className="card flex items-center gap-4">
      <div className={`p-2.5 rounded-lg ${colorMap[color]}`}>{icon}</div>
      <div className="min-w-0">
        <div className="stat-value text-lg truncate">{value}</div>
        <div className="stat-label">{label}</div>
        {subtitle && <div className="text-xs text-slate-400 mt-0.5">{subtitle}</div>}
      </div>
    </div>
  )
}
