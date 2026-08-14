/**
 * 快照结果卡片（P2-B 从 TuningTab.tsx 拆出）——标题 + 描述的单格卡片。
 */
export function SnapshotResultCard({
  title,
  description,
}: {
  title: string
  description: string
}) {
  return (
    <div className="min-w-0 rounded-md border bg-muted/15 p-4">
      <div className="text-sm font-medium">{title}</div>
      <div className="mt-2 text-sm leading-6 text-muted-foreground">{description}</div>
    </div>
  )
}
