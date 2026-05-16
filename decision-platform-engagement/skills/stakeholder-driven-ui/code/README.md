# stakeholder-driven-ui · reference code

A short cheat sheet of the React/TypeScript surface conventions used in the reference engagement. Drop into your repo as a starting point.

## Files

- `page-layout-template.tsx` — standard page layout: header with persona context, pulse strip, sections with consistent typography
- `pulse-tile.tsx` — the standardized stat tile used at the top of every persona page

## Stack assumed

- React + TypeScript
- Tailwind CSS
- TanStack Query for live polling
- lucide-react for iconography
- react-markdown + remark-gfm for AI text rendering

If your stack is different (Vue, Angular, server-rendered), the same conventions apply — adapt the components.

## Conventions

- **Pulse strip** at top — 4-6 high-level metrics, polled every 3-5s
- **Color-code by domain** consistently across pages (compliance = emerald, AI = purple, decisions = amber, lakehouse = slate, risk = indigo)
- **Markdown for AI text** — never render as plain text
- **Cross-link aggressively** — every entity ID (customer, event, action) is clickable into the appropriate detail page
- **Section headers with icons + subtitles** — `<SectionHeader icon={...} title="..." subtitle="..." />` pattern
- **No JSON textareas as the primary view** — collapse into `<details>` summaries
