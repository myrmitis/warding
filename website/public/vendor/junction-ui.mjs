// Vendor stub: re-exports @junction/ui from the host.
const m = window.__junction_modules?.['@junction/ui']
if (!m) throw new Error('[vendor/junction-ui] Host modules not initialized.')
export const {
  Card, CardTitle, Btn, SendBtn, Input, SearchInput,
  Badge, SourceBadge, StatCard, Skeleton, ContentSkeleton,
  EmptyState, PageHeader, Toggle, InfoTip, SegmentedControl,
  MarkdownRenderer,
} = m
