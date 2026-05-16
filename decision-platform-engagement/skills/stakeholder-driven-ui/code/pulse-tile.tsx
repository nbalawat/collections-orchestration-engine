// Standardized stat tile used at the top of every persona page.
// Live indicator (animated dot) for real-time metrics; tone for severity coloring.

interface PulseTileProps {
  label: string
  value: string | number
  sub?: string
  tone?: 'default' | 'good' | 'warn' | 'bad'
  live?: boolean
  icon?: React.ReactNode
}

const TONE: Record<string, string> = {
  default: 'bg-white border-slate-200',
  good:    'bg-emerald-50 border-emerald-300',
  warn:    'bg-amber-50 border-amber-300',
  bad:     'bg-red-50 border-red-300',
}

export function PulseTile({ label, value, sub, tone = 'default', live, icon }: PulseTileProps) {
  return (
    <div className={`border rounded-xl p-4 ${TONE[tone]} relative`}>
      {live && (
        <span className="absolute top-3 right-3 w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
      )}
      <div className="flex items-center gap-2 text-[11px] uppercase tracking-wider text-slate-500">
        {icon}{label}
      </div>
      <div className="text-3xl font-bold text-slate-800 mt-1">{value}</div>
      {sub && <div className="text-xs text-slate-500 mt-1">{sub}</div>}
    </div>
  )
}
