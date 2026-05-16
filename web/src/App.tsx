import { Routes, Route, NavLink } from 'react-router-dom'
import { LayoutDashboard, Users, Brain, Cog, Play } from 'lucide-react'
import OpsDashboard from './pages/OpsDashboard'
import AgentDesktop from './pages/AgentDesktop'
import AIExplorer from './pages/AIExplorer'
import StrategyConsole from './pages/StrategyConsole'
import Scenarios from './pages/Scenarios'

const NAV = [
  { to: '/', icon: LayoutDashboard, label: 'Ops Dashboard' },
  { to: '/agent', icon: Users, label: 'Agent Desktop' },
  { to: '/ai', icon: Brain, label: 'AI Explorer' },
  { to: '/strategy', icon: Cog, label: 'Strategy Console' },
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
          <Route path="/" element={<OpsDashboard />} />
          <Route path="/agent" element={<AgentDesktop />} />
          <Route path="/ai" element={<AIExplorer />} />
          <Route path="/strategy" element={<StrategyConsole />} />
          <Route path="/scenarios" element={<Scenarios />} />
        </Routes>
      </main>
    </div>
  )
}
