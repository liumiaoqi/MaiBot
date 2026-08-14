/**
 * 调优结果总览（P2-B 从 TuningTab.tsx 拆出）——任务状态/进度卡片 + 评估摘要 + 指标行。
 */
import {
  formatResultDelta,
  formatResultValue,
  formatTuningReason,
  getTuningEvaluationSummary,
  numberFrom,
  RESULT_METRICS,
} from './tuning-snapshot'
import { SnapshotResultCard } from './snapshot-result-card'
import { TuningResultMetricRow } from './tuning-result-metric-row'

export function TuningResultOverview({
  task,
  t,
}: {
  task?: Record<string, unknown>
  t: (key: string, options?: Record<string, unknown>) => string
}) {
  if (!task) {
    return (
      <section className="rounded-md border border-dashed p-4 text-sm text-muted-foreground">
        {t('memory.tuning.result.noTask')}
      </section>
    )
  }

  const status = String(task.status ?? '-')
  const statusLabel = t(`memory.tuning.status.${status}`, { defaultValue: status })
  const reasonText = formatTuningReason(String(task.error ?? ''), t)
  const evaluation = getTuningEvaluationSummary(task)
  const isCompleted = status === 'completed'
  const progress = numberFrom(task.progress)
  const roundsDone = numberFrom(task.rounds_done)
  const roundsTotal = numberFrom(task.rounds_total)

  if (!isCompleted || !evaluation?.hasEvaluation) {
    return (
      <section className="space-y-3">
        <div className="grid gap-3 md:grid-cols-3">
          <SnapshotResultCard
            title={t('memory.tuning.result.statusTitle')}
            description={statusLabel}
          />
          <SnapshotResultCard
            title={t('memory.tuning.result.progressTitle')}
            description={progress !== undefined ? `${Math.round(progress)}%` : '-'}
          />
          <SnapshotResultCard
            title={t('memory.tuning.result.roundsTitle')}
            description={roundsDone !== undefined && roundsTotal !== undefined ? `${roundsDone}/${roundsTotal}` : '-'}
          />
        </div>
        {reasonText ? (
          <div className="rounded-md border border-dashed bg-background/60 p-3 text-xs text-muted-foreground">
            {t('memory.tuning.result.errorReason', { reason: reasonText })}
          </div>
        ) : null}
      </section>
    )
  }

  const scoreText = evaluation.baselineScore !== undefined || evaluation.bestScore !== undefined
    ? `${formatResultValue(evaluation.baselineScore, 'number')} → ${formatResultValue(evaluation.bestScore, 'number')}${evaluation.scoreDelta !== undefined ? ` · Δ ${formatResultDelta(evaluation.scoreDelta, 'number')}` : ''}`
    : '-'
  const validationText = evaluation.holdoutCaseCount !== undefined
    ? t('memory.tuning.result.holdoutWithCount', {
      count: evaluation.holdoutCaseCount,
      result: evaluation.recommended ? t('memory.tuning.result.validationPassed') : t('memory.tuning.result.validationFailed'),
    })
    : evaluation.recommended ? t('memory.tuning.result.validationPassed') : t('memory.tuning.result.validationFailed')
  const metricRows = RESULT_METRICS.map((metric) => {
    const baseline = numberFrom(evaluation.baselineMetrics[metric.key])
    const best = numberFrom(evaluation.bestMetrics[metric.key])
    const delta = numberFrom(evaluation.deltas[metric.key]) ?? (
      baseline !== undefined && best !== undefined ? best - baseline : undefined
    )
    return { ...metric, baseline, best, delta }
  }).filter((metric) => metric.baseline !== undefined || metric.best !== undefined || metric.delta !== undefined)

  return (
    <section className="space-y-4">
      <div className="grid gap-3 md:grid-cols-3">
        <SnapshotResultCard
          title={t('memory.tuning.result.recommendationTitle')}
          description={evaluation.recommended ? t('memory.tuning.result.recommended') : t('memory.tuning.result.notRecommended')}
        />
        <SnapshotResultCard
          title={t('memory.tuning.result.scoreTitle')}
          description={scoreText}
        />
        <SnapshotResultCard
          title={t('memory.tuning.result.validationTitle')}
          description={validationText}
        />
      </div>
      {metricRows.length > 0 ? (
        <div className="space-y-2 rounded-md border bg-muted/15 p-4">
          <div>
            <div className="text-sm font-medium">{t('memory.tuning.result.metricsTitle')}</div>
            <div className="text-xs text-muted-foreground">{t('memory.tuning.result.metricsDescription')}</div>
          </div>
          <div className="grid gap-2 xl:grid-cols-2">
            {metricRows.map((metric) => (
              <TuningResultMetricRow
                key={metric.key}
                label={t(metric.labelKey)}
                baseline={metric.baseline}
                best={metric.best}
                delta={metric.delta}
                format={metric.format}
              />
            ))}
          </div>
        </div>
      ) : null}
      {!evaluation.recommended && evaluation.reason ? (
        <div className="rounded-md border border-dashed bg-background/60 p-3 text-xs text-muted-foreground">
          {t('memory.tuning.result.reason', { reason: formatTuningReason(evaluation.reason, t) })}
        </div>
      ) : null}
    </section>
  )
}
