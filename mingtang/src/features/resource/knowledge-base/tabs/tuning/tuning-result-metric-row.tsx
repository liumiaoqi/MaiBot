/**
 * 调优结果指标行（P2-B 从 TuningTab.tsx 拆出）——baseline → best + Δ 的一行对比。
 */
import { formatResultDelta, formatResultValue } from './tuning-snapshot'

export function TuningResultMetricRow({
  label,
  baseline,
  best,
  delta,
  format,
}: {
  label: string
  baseline?: number
  best?: number
  delta?: number
  format: 'percent' | 'ms'
}) {
  return (
    <div className="grid gap-2 rounded-md border bg-background px-3 py-2 sm:grid-cols-[minmax(0,1fr)_auto]">
      <div className="text-sm font-medium">{label}</div>
      <div className="text-sm leading-6 text-muted-foreground sm:text-right">
        {formatResultValue(baseline, format)}
        <span className="mx-1.5">→</span>
        {formatResultValue(best, format)}
        {delta !== undefined ? (
          <span className="ml-2 text-xs">Δ {formatResultDelta(delta, format)}</span>
        ) : null}
      </div>
    </div>
  )
}
