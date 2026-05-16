// Standard persona-page layout. Drop into your React app and adapt.
//
// Conventions:
//   - Header with persona context + status indicator
//   - Pulse strip (4-6 tiles) with live data
//   - Sections with consistent typography (SectionHeader + content)
//   - Markdown for any AI-generated text (react-markdown + remark-gfm)

import { useQuery } from '@tanstack/react-query'
import { Activity, Radio } from 'lucide-react'
// import { Markdown } from '@/components/Markdown'   // your shared markdown component

interface PersonaPageProps {
  pageTitle: string
  pageSubtitle: string
  persona: 'COO' | 'CRO' | 'CCO' | 'CTO' | 'CDO' | 'SRE'
}

function PulseTile({ label, value, sub, tone = 'default', live }: {
  label: string; value: string | number; sub?: string;
  tone?: 'default' | 'good' | 'warn' | 'bad'; live?: boolean
}) {
  const toneClass = {
    default: 'bg-white border-slate-200',
    good:    'bg-emerald-50 border-emerald-300',
    warn:    'bg-amber-50 border-amber-300',
    bad:     'bg-red-50 border-red-300',
  }[tone]
  return (
    <div className={`border rounded-xl p-4 ${toneClass} relative`}>
      {live && (
        <span className="absolute top-3 right-3 w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
      )}
      <div className="text-[11px] uppercase tracking-wider text-slate-500">{label}</div>
      <div className="text-3xl font-bold text-slate-800 mt-1">{value}</div>
      {sub && <div className="text-xs text-slate-500 mt-1">{sub}</div>}
    </div>
  )
}

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

export default function PersonaPage({ pageTitle, pageSubtitle, persona }: PersonaPageProps) {
  // Replace with your real data hook
  const { data: pulse } = useQuery({
    queryKey: ['pulse'],
    queryFn: async () => ({ active: 88, eventsPerMin: 110, pending: 12 }),
    refetchInterval: 3000,
  })

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      <div className="px-6 py-3 border-b border-slate-200 bg-white flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Radio size={22} className="text-blue-600" />
          <div>
            <h1 className="text-lg font-bold text-slate-800">{pageTitle}</h1>
            <p className="text-xs text-slate-500">{pageSubtitle}</p>
          </div>
        </div>
        <div className="flex items-center gap-2 text-sm">
          <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
          <span className="text-emerald-700 text-xs">{persona} view · streaming</span>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {/* Pulse strip — top of every persona page */}
        <div className="grid grid-cols-4 gap-3">
          <PulseTile label="Active" value={pulse?.active ?? '—'} sub="right now" live />
          <PulseTile label="Events / min" value={pulse?.eventsPerMin ?? '—'} sub="last 60 sec" live />
          <PulseTile label="Pending" value={pulse?.pending ?? '—'} tone={pulse && pulse.pending > 10 ? 'warn' : 'default'} />
          <PulseTile label="Status" value="OK" tone="good" />
        </div>

        {/* Sections — one per persona concern */}
        <section>
          <SectionHeader
            icon={<Activity size={16} />}
            title="Live activity"
            subtitle="Real-time view tailored to this persona's first ten questions"
          />
          {/* persona-specific content here */}
        </section>
      </div>
    </div>
  )
}
