import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

interface MarkdownProps {
  children: string
  /** "narrative" gets richer typography; "rationale" is compact for inline use. */
  variant?: 'narrative' | 'rationale' | 'note'
}

/** Renders AI-generated text with proper markdown formatting.
 *
 * The narrative endpoint and several agent tools return markdown (headings,
 * bold, bullet lists, inline code). Plain-text rendering looks broken; this
 * component is the single source of truth for how AI output is displayed.
 */
export function Markdown({ children, variant = 'narrative' }: MarkdownProps) {
  const text = (children ?? '').trim()
  if (!text) return null

  const wrapper = {
    narrative: 'text-sm text-slate-700 leading-relaxed space-y-3',
    rationale: 'text-xs text-slate-600 leading-snug space-y-1.5',
    note: 'text-[11px] text-slate-500 leading-snug space-y-1',
  }[variant]

  return (
    <div className={wrapper}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: ({ children }) => <h3 className="text-base font-bold text-slate-800 mt-2">{children}</h3>,
          h2: ({ children }) => <h4 className="text-sm font-bold text-slate-800 mt-2">{children}</h4>,
          h3: ({ children }) => <h5 className="text-sm font-bold text-slate-800 mt-2">{children}</h5>,
          p: ({ children }) => <p className="leading-relaxed">{children}</p>,
          strong: ({ children }) => <strong className="font-semibold text-slate-900">{children}</strong>,
          em: ({ children }) => <em className="text-slate-700 italic">{children}</em>,
          ul: ({ children }) => <ul className="list-disc ml-5 space-y-1">{children}</ul>,
          ol: ({ children }) => <ol className="list-decimal ml-5 space-y-1">{children}</ol>,
          li: ({ children }) => <li className="leading-snug">{children}</li>,
          code: ({ children, ...props }) => {
            const inline = !(props as { className?: string }).className?.includes('language-')
            return inline ? (
              <code className="px-1 py-0.5 rounded bg-slate-100 text-slate-700 text-[0.95em] font-mono">
                {children}
              </code>
            ) : (
              <code className="block p-2 rounded bg-slate-900 text-slate-100 text-[0.85em] overflow-auto font-mono">
                {children}
              </code>
            )
          },
          a: ({ children, href }) => (
            <a href={href} target="_blank" rel="noreferrer" className="text-blue-600 hover:underline">
              {children}
            </a>
          ),
          blockquote: ({ children }) => (
            <blockquote className="border-l-2 border-slate-300 pl-3 italic text-slate-600">{children}</blockquote>
          ),
          hr: () => <hr className="border-slate-200 my-2" />,
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  )
}
