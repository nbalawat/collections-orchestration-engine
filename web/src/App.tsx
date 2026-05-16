import { Routes, Route, NavLink } from 'react-router-dom'
import { LayoutDashboard, Users, Brain, Cog, Play, Radio, UserSearch, Server, Activity, Database, Sigma } from 'lucide-react'
import OperationsFloor from './pages/OperationsFloor'
import CommandCenter from './pages/CommandCenter'
import CustomerJourney from './pages/CustomerJourney'
import CustomerStory from './pages/CustomerStory'
import AgentDesktop from './pages/AgentDesktop'
import AIExplorer from './pages/AIExplorer'
import StrategyConsole from './pages/StrategyConsole'
import Scenarios from './pages/Scenarios'
import PlatformOps from './pages/PlatformOps'
import Lakehouse from './pages/Lakehouse'
import RiskAndML from './pages/RiskAndML'

const NAV = [
  { to: '/', icon: Activity, label: 'Operations Floor' },
  { to: '/command', icon: Radio, label: 'Command Center' },
  { to: '/customers', icon: UserSearch, label: 'Customer Search' },
  { to: '/agent', icon: Users, label: 'Agent Desktop' },
  { to: '/ai', icon: Brain, label: 'AI Explorer' },
  { to: '/strategy', icon: Cog, label: 'Strategy Console' },
  { to: '/platform', icon: Server, label: 'Platform Ops' },
  { to: '/lakehouse', icon: Database, label: 'Data Lakehouse' },
  { to: '/risk-ml', icon: Sigma, label: 'Risk & ML' },
  { to: '/scenarios', icon: Play, label: 'Scenarios' },
]

export default function App() {
  return (
    <div className="flex h-screen">
      <nav className="w-56 bg-slate-900 text-slate-300 flex flex-col shrink-0">
        <div className="p-4 border-b border-slate-700">
          <h1 className="text-sm font-bold text-white tracking-wide">Collections Engine</h1>
          <p className="text-xs text-slate-500 mt-0.5">Orchestration POC</p>
        </div>
        <div className="flex-1 py-2">
          {NAV.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.to === '/'}
              className={({ isActive }) =>
                `flex items-center gap-3 px-4 py-2.5 text-sm transition-colors ${
                  isActive
                    ? 'bg-slate-800 text-white border-r-2 border-blue-500'
                    : 'hover:bg-slate-800/50 hover:text-white'
                }`
              }
            >
              <n.icon size={18} />
              {n.label}
            </NavLink>
          ))}
        </div>
        <div className="p-4 border-t border-slate-700 text-xs text-slate-500">
          v1.0.0 &middot; Local Dev
        </div>
      </nav>

      <main className="flex-1 min-h-0 min-w-0 flex flex-col overflow-hidden">
        <Routes>
          <Route path="/" element={<OperationsFloor />} />
          <Route path="/command" element={<CommandCenter />} />
          <Route path="/customers" element={<CustomerSearch />} />
          <Route path="/customer/:id" element={<CustomerStory />} />
          <Route path="/customer/:id/timeline" element={<CustomerJourney />} />
          <Route path="/agent" element={<AgentDesktop />} />
          <Route path="/ai" element={<AIExplorer />} />
          <Route path="/strategy" element={<StrategyConsole />} />
          <Route path="/scenarios" element={<Scenarios />} />
          <Route path="/platform" element={<PlatformOps />} />
          <Route path="/lakehouse" element={<Lakehouse />} />
          <Route path="/risk-ml" element={<RiskAndML />} />
        </Routes>
      </main>
    </div>
  )
}

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api } from '@/lib/api'
import { formatCurrency, formatNumber, stageBadgeColor, channelIcon } from '@/lib/utils'
import { Search, ChevronRight } from 'lucide-react'

function CustomerSearch() {
  const [search, setSearch] = useState('')
  const [segment, setSegment] = useState('')
  const [page, setPage] = useState(1)

  const { data, isLoading } = useQuery({
    queryKey: ['customers', page, search, segment],
    queryFn: () => api.listCustomers(page, 20, search, segment),
  })

  return (
    <div className="p-6 space-y-4 flex-1 overflow-y-auto overflow-x-hidden min-w-0">
      <div className="flex items-center gap-3">
        <UserSearch size={24} className="text-slate-600" />
        <h2 className="text-xl font-bold text-slate-800">Customer Search</h2>
      </div>

      <div className="flex gap-3">
        <div className="relative flex-1 max-w-md">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            className="w-full pl-9 pr-3 py-2 border border-slate-300 rounded-lg text-sm"
            placeholder="Search by name or customer ID..."
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(1) }}
          />
        </div>
        <select
          className="px-3 py-2 border border-slate-300 rounded-lg text-sm"
          value={segment}
          onChange={(e) => { setSegment(e.target.value); setPage(1) }}
        >
          <option value="">All Stages</option>
          <option value="CURRENT">Current</option>
          <option value="PRE_DELINQUENT">Pre-Delinquent</option>
          <option value="EARLY">Early</option>
          <option value="MID">Mid</option>
          <option value="LATE">Late</option>
          <option value="SEVERE">Severe</option>
        </select>
      </div>

      {isLoading ? (
        <div className="text-center py-12 text-slate-400">Loading customers...</div>
      ) : (
        <>
          <div className="card overflow-hidden p-0">
            <table className="table">
              <thead>
                <tr>
                  <th>Customer</th>
                  <th>Channel</th>
                  <th>Risk</th>
                  <th>DPD</th>
                  <th>Balance</th>
                  <th>Past Due</th>
                  <th>Stage</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {data?.customers.map((c) => (
                  <tr key={c.customer_id}>
                    <td>
                      <div className="font-medium text-slate-800">{c.first_name} {c.last_name}</div>
                      <div className="text-xs text-slate-400 font-mono">{c.customer_id}</div>
                    </td>
                    <td className="text-lg">{channelIcon(c.preferred_channel)}</td>
                    <td>
                      <span className={`font-semibold ${c.risk_score > 70 ? 'text-red-600' : c.risk_score > 40 ? 'text-amber-600' : 'text-green-600'}`}>
                        {c.risk_score}
                      </span>
                    </td>
                    <td className="font-mono">{c.days_past_due}</td>
                    <td>{formatCurrency(c.current_balance)}</td>
                    <td className="text-red-600 font-medium">{formatCurrency(c.total_past_due)}</td>
                    <td><span className={`badge ${stageBadgeColor(c.delinquency_stage)}`}>{c.delinquency_stage}</span></td>
                    <td>
                      <Link to={`/customer/${c.customer_id}`} className="text-blue-600 hover:text-blue-800">
                        <ChevronRight size={18} />
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {data && (
            <div className="flex items-center justify-between text-sm text-slate-500">
              <span>Showing {((page - 1) * 20) + 1}-{Math.min(page * 20, data.total)} of {data.total}</span>
              <div className="flex gap-2">
                <button className="btn btn-outline btn-sm" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>Previous</button>
                <button className="btn btn-outline btn-sm" disabled={page * 20 >= data.total} onClick={() => setPage(p => p + 1)}>Next</button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
