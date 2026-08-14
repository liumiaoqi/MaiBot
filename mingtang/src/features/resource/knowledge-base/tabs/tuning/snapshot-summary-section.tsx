/**
 * 快照摘要区块（P2-B 从 TuningTab.tsx 拆出）——展示一组可读参数条目与未翻译技术项计数。
 */
import type { ReadableSnapshotEntry } from './tuning-snapshot'

export function SnapshotSummarySection({
  title,
  description,
  entries,
  technicalCount,
  technicalNote,
  emptyText,
}: {
  title: string
  description: string
  entries: ReadableSnapshotEntry[]
  technicalCount: number
  technicalNote: string
  emptyText: string
}) {
  return (
    <section className="space-y-3 rounded-md border bg-muted/15 p-4">
      <div>
        <div className="text-sm font-medium">{title}</div>
        <div className="text-xs text-muted-foreground">{description}</div>
      </div>
      {entries.length > 0 ? (
        <div className="grid gap-2 md:grid-cols-2">
          {entries.map((entry) => (
            <div key={entry.path} className="min-w-0 rounded-md border bg-background px-3 py-2">
              <div className="text-xs leading-5 text-muted-foreground">{entry.label}</div>
              <div className="break-all text-sm leading-6">{entry.value}</div>
            </div>
          ))}
        </div>
      ) : (
        <div className="rounded-md border border-dashed p-3 text-sm text-muted-foreground">{emptyText}</div>
      )}
      {technicalCount > 0 ? (
        <div className="rounded-md border border-dashed bg-background/60 p-3 text-xs text-muted-foreground">
          {technicalNote}
        </div>
      ) : null}
    </section>
  )
}
