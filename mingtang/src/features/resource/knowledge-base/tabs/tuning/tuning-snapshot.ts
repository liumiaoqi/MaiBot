/**
 * tabs/tuning/tuning-snapshot —— 调优「快照/结果」展示的纯函数与常量（P2-B 从 TuningTab.tsx 迁出）。
 *
 * 与 TuningTab.tsx 的分工：这里只放「快照条目收集 → 可读化 → 前后差异」的纯转换、
 * 调优结果评估的纯计算与相关类型/常量；组件渲染（卡片/表格 JSX）留在 tuning/ 各组件文件。
 * 纯函数不依赖 React——可独立单测。
 */

/** 快照条目：扁平化后的配置路径 + 原始值 */
export interface SnapshotEntry {
  path: string
  rawValue: unknown
}

/** 快照差异条目：运行时 vs 可持久化的可读化对比 */
export interface SnapshotDiffEntry {
  path: string
  label: string
  runtime: string
  persistable: string
}

/** 可读快照条目：参数路径 + i18n 标签 + 格式化值 */
export interface ReadableSnapshotEntry {
  path: string
  label: string
  value: string
}

/** 调优评估摘要（从 validation_summary / deltas 提炼） */
export interface TuningEvaluationSummary {
  baselineScore?: number
  bestScore?: number
  scoreDelta?: number
  holdoutCaseCount?: number
  reason: string
  recommended: boolean
  hasEvaluation: boolean
  baselineMetrics: Record<string, unknown>
  bestMetrics: Record<string, unknown>
  deltas: Record<string, unknown>
}

const PARAMETER_ORDER = [
  'retrieval.top_k',
  'retrieval.top_k_paragraphs',
  'retrieval.top_k_relations',
  'retrieval.top_k_final',
  'retrieval.alpha',
  'retrieval.enable_ppr',
  'retrieval.ppr_alpha',
  'retrieval.ppr_timeout_seconds',
  'retrieval.search.smart_fallback.enabled',
  'retrieval.sparse.enabled',
  'retrieval.sparse.mode',
  'retrieval.sparse.candidate_k',
  'retrieval.sparse.relation_candidate_k',
  'retrieval.fusion.method',
  'retrieval.fusion.rrf_k',
  'retrieval.fusion.vector_weight',
  'retrieval.fusion.bm25_weight',
  'retrieval.vector_pools.mode',
  'retrieval.vector_pools.paragraph_top_k',
  'retrieval.vector_pools.graph_top_k',
  'retrieval.vector_pools.graph_expand_paragraph_k',
  'retrieval.vector_pools.relation_expand_per_hit',
  'retrieval.vector_pools.entity_expand_per_hit',
  'retrieval.vector_pools.relation_evidence_weight',
  'retrieval.vector_pools.entity_evidence_weight',
  'threshold.percentile',
  'threshold.min_results',
  'threshold.min_threshold',
  'threshold.max_threshold',
  'threshold.enable_auto_adjust',
]

export const RESULT_METRICS = [
  { key: 'precision_at_1', labelKey: 'memory.tuning.result.metrics.precisionAt1', format: 'percent' },
  { key: 'recall_at_k', labelKey: 'memory.tuning.result.metrics.recallAtK', format: 'percent' },
  { key: 'empty_rate', labelKey: 'memory.tuning.result.metrics.emptyRate', format: 'percent' },
  { key: 'avg_elapsed_ms', labelKey: 'memory.tuning.result.metrics.avgElapsedMs', format: 'ms' },
] as const

const PARAMETER_KEYS = Object.fromEntries(
  PARAMETER_ORDER.map((path) => [path, path.replaceAll('.', '_')]),
) as Record<string, string>

const VALUE_LABEL_KEYS: Record<string, Record<string, string>> = {
  'retrieval.sparse.mode': {
    auto: 'memory.tuning.values.auto',
    always: 'memory.tuning.values.always',
    off: 'memory.tuning.values.off',
  },
  'retrieval.fusion.method': {
    weighted_rrf: 'memory.tuning.values.weightedRrf',
    rrf: 'memory.tuning.values.rrf',
    alpha_legacy: 'memory.tuning.values.alphaLegacy',
  },
  'retrieval.vector_pools.mode': {
    single: 'memory.tuning.values.singlePool',
    dual: 'memory.tuning.values.dualPool',
  },
}

const TUNING_REASON_KEYS: Record<string, string> = {
  holdout_empty: 'memory.tuning.result.reasons.holdoutEmpty',
  holdout_online_like_validation_failed: 'memory.tuning.result.reasons.holdoutOnlineLikeValidationFailed',
}

export function formatSnapshotValue(
  value: unknown,
  t: (key: string, options?: Record<string, unknown>) => string,
  path?: string,
): string {
  if (value === null) {
    return 'null'
  }
  if (value === undefined) {
    return '-'
  }
  if (typeof value === 'boolean') {
    return value ? t('memory.tuning.values.enabled') : t('memory.tuning.values.disabled')
  }
  if (typeof value === 'number') {
    return Number.isFinite(value) ? String(value) : '-'
  }
  if (typeof value === 'string') {
    const valueLabelKey = path ? VALUE_LABEL_KEYS[path]?.[value] : undefined
    if (valueLabelKey) {
      return t(valueLabelKey)
    }
    return value || '""'
  }
  return JSON.stringify(value)
}

export function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {}
}

export function numberFrom(value: unknown): number | undefined {
  const numberValue = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(numberValue) ? numberValue : undefined
}

export function formatResultValue(value: number | undefined, format: 'number' | 'percent' | 'ms'): string {
  if (value === undefined) {
    return '-'
  }
  if (format === 'percent') {
    return `${(value * 100).toFixed(1)}%`
  }
  if (format === 'ms') {
    return `${value.toFixed(0)} ms`
  }
  return value.toFixed(3)
}

export function formatTuningReason(
  reason: string,
  t: (key: string, options?: Record<string, unknown>) => string,
): string {
  const normalized = reason.trim()
  if (!normalized) {
    return ''
  }

  const reasonKey = TUNING_REASON_KEYS[normalized]
  if (reasonKey) {
    return t(reasonKey)
  }
  return t('memory.tuning.result.reasons.unknown', { reason: normalized })
}

export function formatResultDelta(value: number | undefined, format: 'number' | 'percent' | 'ms'): string {
  if (value === undefined) {
    return ''
  }
  const prefix = value > 0 ? '+' : ''
  if (format === 'percent') {
    return `${prefix}${(value * 100).toFixed(1)}%`
  }
  if (format === 'ms') {
    return `${prefix}${value.toFixed(0)} ms`
  }
  return `${prefix}${value.toFixed(3)}`
}

export function isTuningTaskRecommended(task: Record<string, unknown>): boolean {
  const validation = asRecord(task.validation_summary)
  return validation.recommended === true || task.recommended === true
}

export function getTuningEvaluationSummary(task: Record<string, unknown> | undefined): TuningEvaluationSummary | null {
  if (!task) {
    return null
  }

  const validation = asRecord(task.validation_summary)
  const onlineLike = asRecord(validation.online_like)
  const stable = asRecord(validation.stable)
  const evaluationMode = Object.keys(onlineLike).length > 0 ? onlineLike : stable
  const baselineEval = asRecord(evaluationMode.baseline)
  const bestEval = asRecord(evaluationMode.best)
  const baselineMetrics = asRecord(baselineEval.metrics)
  const bestMetrics = asRecord(bestEval.metrics)
  const deltas = asRecord(validation.deltas)
  const baselineScore = numberFrom(baselineEval.score)
  const bestScore = numberFrom(bestEval.score) ?? numberFrom(task.best_score)
  const directScoreDelta = numberFrom(deltas.score)
  const scoreDelta = directScoreDelta ?? (
    baselineScore !== undefined && bestScore !== undefined ? bestScore - baselineScore : undefined
  )
  const holdoutCaseCount = numberFrom(validation.holdout_case_count)
  const recommended = isTuningTaskRecommended(task)
  const hasEvaluation = baselineScore !== undefined
    || bestScore !== undefined
    || Object.keys(baselineMetrics).length > 0
    || Object.keys(bestMetrics).length > 0
    || Object.keys(deltas).length > 0

  return {
    baselineScore,
    bestScore,
    scoreDelta,
    holdoutCaseCount,
    reason: String(validation.reason ?? task.error ?? ''),
    recommended,
    hasEvaluation,
    baselineMetrics,
    bestMetrics,
    deltas,
  }
}

export function collectSnapshotEntries(value: unknown, prefix = ''): SnapshotEntry[] {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return prefix ? [{ path: prefix, rawValue: value }] : []
  }

  return Object.entries(value as Record<string, unknown>).flatMap(([key, item]) => {
    const nextPath = prefix ? `${prefix}.${key}` : key
    if (item && typeof item === 'object' && !Array.isArray(item)) {
      return collectSnapshotEntries(item, nextPath)
    }
    return [{ path: nextPath, rawValue: item }]
  })
}

export function buildReadableSnapshotEntries(
  entries: SnapshotEntry[],
  t: (key: string, options?: Record<string, unknown>) => string,
): { readableEntries: ReadableSnapshotEntry[], technicalCount: number } {
  const entryMap = new Map(entries.map((entry) => [entry.path, entry.rawValue]))
  const readableEntries = PARAMETER_ORDER
    .filter((path) => entryMap.has(path))
    .map((path) => ({
      path,
      label: t(`memory.tuning.parameters.${PARAMETER_KEYS[path]}`),
      value: formatSnapshotValue(entryMap.get(path), t, path),
    }))
  const technicalCount = entries.filter((entry) => !PARAMETER_KEYS[entry.path]).length

  return { readableEntries, technicalCount }
}

export function buildSnapshotDiff(
  runtimeEntries: SnapshotEntry[],
  persistableEntries: SnapshotEntry[],
  t: (key: string, options?: Record<string, unknown>) => string,
): { readableDiffs: SnapshotDiffEntry[], technicalDiffCount: number } {
  const runtimeMap = new Map(runtimeEntries.map((entry) => [entry.path, entry.rawValue]))
  const persistableMap = new Map(persistableEntries.map((entry) => [entry.path, entry.rawValue]))
  const allPaths = Array.from(new Set([...runtimeMap.keys(), ...persistableMap.keys()])).sort()
  const diffPaths = allPaths.filter((path) => {
    const runtimeValue = formatSnapshotValue(runtimeMap.get(path), t, path)
    const persistableValue = formatSnapshotValue(persistableMap.get(path), t, path)
    return runtimeValue !== persistableValue
  })
  const readableDiffs = diffPaths
    .filter((path) => PARAMETER_KEYS[path])
    .map((path) => ({
      path,
      label: t(`memory.tuning.parameters.${PARAMETER_KEYS[path]}`),
      runtime: formatSnapshotValue(runtimeMap.get(path), t, path),
      persistable: formatSnapshotValue(persistableMap.get(path), t, path),
    }))
  const technicalDiffCount = diffPaths.length - readableDiffs.length

  return { readableDiffs, technicalDiffCount }
}
