// Vendor stub: re-exports @warding/ui from the host.
const m = window.__warding_modules?.['@warding/ui']
if (!m) throw new Error('[vendor/warding-ui] Host modules not initialized.')
export const {
  Card, CardTitle, Btn, SendBtn, Input, SearchInput,
  Badge, SourceBadge, StatCard, Skeleton, ContentSkeleton,
  EmptyState, PageHeader, Toggle, InfoTip, SegmentedControl,
  MarkdownRenderer,
} = m
