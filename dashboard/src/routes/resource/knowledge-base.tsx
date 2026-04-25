import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from '@tanstack/react-router'

import {
  ChevronLeft,
  ChevronRight,
  Database,
  Gauge,
  Loader2,
  RefreshCw,
  RotateCcw,
  Save,
  SlidersHorizontal,
  Sparkles,
  Trash2,
  Upload,
  CheckCircle2,
  CircleAlert,
  FolderOpen,
  HardDrive,
} from 'lucide-react'

import { CodeEditor } from '@/components/CodeEditor'
import { MemoryDeleteDialog } from '@/components/memory/MemoryDeleteDialog'
import { MemoryConfigEditor } from '@/components/memory/MemoryConfigEditor'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Progress } from '@/components/ui/progress'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import { useToast } from '@/hooks/use-toast'
import { cn } from '@/lib/utils'
import {
  cancelMemoryImportTask,
  createMemoryLpmmConvertImport,
  createMemoryLpmmOpenieImport,
  createMemoryMaibotMigrationImport,
  createMemoryRawScanImport,
  createMemoryTemporalBackfillImport,
  executeMemoryDelete,
  getMemoryFeedbackCorrection,
  getMemoryFeedbackCorrections,
  getMemoryImportPathAliases,
  getMemoryImportSettings,
  getMemoryImportTask,
  getMemoryImportTaskChunks,
  applyBestMemoryTuningProfile,
  createMemoryPasteImport,
  createMemoryTuningTask,
  createMemoryUploadImport,
  getMemoryConfig,
  getMemoryConfigRaw,
  getMemoryConfigSchema,
  getMemoryDeleteOperation,
  getMemoryDeleteOperations,
  getMemoryImportTasks,
  getMemoryRuntimeConfig,
  getMemorySources,
  getMemoryTuningProfile,
  getMemoryTuningTasks,
  type MemoryDeleteRequestPayload,
  type MemoryImportChunkListPayload,
  type MemoryImportInputMode,
  type MemoryImportSettings,
  type MemoryImportTaskKind,
  type MemoryImportTaskPayload,
  previewMemoryDelete,
  refreshMemoryRuntimeSelfCheck,
  rollbackMemoryFeedbackCorrection,
  resolveMemoryImportPath,
  retryMemoryImportTask,
  restoreMemoryDelete,
  updateMemoryConfig,
  updateMemoryConfigRaw,
  type MemoryConfigSchemaPayload,
  type MemoryDeleteExecutePayload,
  type MemoryDeleteOperationPayload,
  type MemoryFeedbackActionLogPayload,
  type MemoryFeedbackCorrectionDetailTaskPayload,
  type MemoryFeedbackCorrectionSummaryPayload,
  type MemorySourceItemPayload,
  type MemoryRuntimeConfigPayload,
  type MemoryTaskPayload,
} from '@/lib/memory-api'

const DELETE_OPERATION_FETCH_LIMIT = 100
const DELETE_OPERATION_PAGE_SIZE = 6
const DELETE_OPERATION_ITEM_PAGE_SIZE = 8
const FEEDBACK_CORRECTION_FETCH_LIMIT = 100
const FEEDBACK_CORRECTION_PAGE_SIZE = 6
const FEEDBACK_ACTION_LOG_PAGE_SIZE = 8
const IMPORT_CHUNK_PAGE_SIZE = 50

const RUNNING_IMPORT_STATUS = new Set(['preparing', 'running', 'cancel_requested'])
const QUEUED_IMPORT_STATUS = new Set(['queued'])

const IMPORT_STATUS_TEXT: Record<string, string> = {
  queued: '排队中',
  preparing: '准备中',
  running: '运行中',
  cancel_requested: '取消中',
  cancelled: '已取消',
  completed: '已完成',
  completed_with_errors: '完成（有错误）',
  failed: '失败',
}

const IMPORT_STEP_TEXT: Record<string, string> = {
  queued: '排队中',
  preparing: '准备中',
  running: '运行中',
  splitting: '分块中',
  extracting: '抽取中',
  writing: '写入中',
  saving: '保存中',
  backfilling: '回填中',
  converting: '转换中',
  verifying: '校验中',
  switching: '切换中',
  cancel_requested: '取消中',
  cancelled: '已取消',
  completed: '已完成',
  completed_with_errors: '完成（有错误）',
  failed: '失败',
}

const IMPORT_KIND_OPTIONS: Array<{ value: MemoryImportTaskKind; label: string; description: string }> = [
  { value: 'upload', label: '上传文件', description: '从本地批量上传资料文件' },
  { value: 'paste', label: '粘贴导入', description: '直接粘贴文本或 JSON 内容创建任务' },
  { value: 'raw_scan', label: '本地扫描', description: '按路径别名和匹配规则批量扫描导入' },
  { value: 'lpmm_openie', label: 'LPMM OpenIE', description: '读取 LPMM 数据并抽取关系' },
  { value: 'lpmm_convert', label: 'LPMM 转换', description: '将 LPMM 数据转换到目标目录' },
  { value: 'temporal_backfill', label: '时序回填', description: '为已有数据补充时间字段' },
  { value: 'maibot_migration', label: 'MaiBot 迁移', description: '从 MaiBot 历史数据迁移长期记忆' },
]

function normalizeProgress(value: number | string | null | undefined): number {
  const numeric = Number(value ?? 0)
  if (!Number.isFinite(numeric)) {
    return 0
  }
  if (numeric < 0) {
    return 0
  }
  if (numeric > 100) {
    return 100
  }
  return numeric
}

function parseOptionalPositiveInt(input: string): number | undefined {
  const value = input.trim()
  if (!value) {
    return undefined
  }
  const parsed = Number(value)
  if (!Number.isInteger(parsed) || parsed <= 0) {
    return undefined
  }
  return parsed
}

function parseCommaSeparatedList(input: string): string[] {
  return input
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
}

function normalizeImportInputMode(value: string): MemoryImportInputMode {
  return value === 'json' ? 'json' : 'text'
}

function getImportStatusLabel(status: string): string {
  const normalized = String(status ?? '').trim()
  if (!normalized) {
    return '-'
  }
  return IMPORT_STATUS_TEXT[normalized] ?? normalized
}

function getImportStepLabel(step: string): string {
  const normalized = String(step ?? '').trim()
  if (!normalized) {
    return '-'
  }
  return IMPORT_STEP_TEXT[normalized] ?? normalized
}

function getImportStatusVariant(status: string): 'default' | 'secondary' | 'destructive' | 'outline' {
  if (status === 'failed') {
    return 'destructive'
  }
  if (status === 'completed') {
    return 'default'
  }
  if (status === 'completed_with_errors' || status === 'cancelled') {
    return 'secondary'
  }
  if (RUNNING_IMPORT_STATUS.has(status) || QUEUED_IMPORT_STATUS.has(status)) {
    return 'outline'
  }
  return 'secondary'
}

function formatImportTime(timestamp?: number | null): string {
  if (!timestamp) {
    return '-'
  }
  const normalized = timestamp > 1_000_000_000_000 ? timestamp : timestamp * 1000
  const value = new Date(normalized)
  if (Number.isNaN(value.getTime())) {
    return '-'
  }
  return value.toLocaleString('zh-CN', {
    hour12: false,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function formatDeleteOperationMode(mode: string): string {
  switch (mode) {
    case 'entity':
      return '实体'
    case 'relation':
      return '关系'
    case 'paragraph':
      return '段落'
    case 'source':
      return '来源'
    case 'mixed':
      return '混合'
    default:
      return mode || '未知'
  }
}

function formatDeleteOperationStatus(status: string): string {
  switch (status) {
    case 'executed':
      return '已执行'
    case 'restored':
      return '已恢复'
    default:
      return status || '未知'
  }
}

function formatDeleteOperationTime(timestamp?: number | null): string {
  if (!timestamp) {
    return '未知时间'
  }
  const normalized = timestamp > 1_000_000_000_000 ? timestamp : timestamp * 1000
  const value = new Date(normalized)
  if (Number.isNaN(value.getTime())) {
    return '未知时间'
  }
  return value.toLocaleString('zh-CN', {
    hour12: false,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function formatFeedbackDecision(decision: string): string {
  switch (decision) {
    case 'correct':
      return '纠正'
    case 'reject':
      return '否定'
    case 'confirm':
      return '确认'
    case 'supplement':
      return '补充'
    case 'none':
      return '无动作'
    default:
      return decision || '未知'
  }
}

function formatFeedbackTaskStatus(status: string): string {
  switch (status) {
    case 'pending':
      return '待处理'
    case 'running':
      return '处理中'
    case 'applied':
      return '已应用'
    case 'skipped':
      return '已跳过'
    case 'error':
      return '失败'
    default:
      return status || '未知'
  }
}

function formatFeedbackRollbackStatus(status: string): string {
  switch (status) {
    case 'none':
      return '未回退'
    case 'running':
      return '回退中'
    case 'rolled_back':
      return '已回退'
    case 'error':
      return '回退失败'
    default:
      return status || '未知'
  }
}

function getFeedbackStatusVariant(
  status: string,
): 'default' | 'secondary' | 'destructive' | 'outline' {
  if (status === 'applied' || status === 'rolled_back') {
    return 'default'
  }
  if (status === 'error') {
    return 'destructive'
  }
  if (status === 'running' || status === 'pending') {
    return 'outline'
  }
  return 'secondary'
}

function summarizeFeedbackActionPayload(value: Record<string, unknown> | undefined): string {
  if (!value) {
    return ''
  }
  const hash = String(value.hash ?? '').trim()
  const subject = String(value.subject ?? '').trim()
  const predicate = String(value.predicate ?? '').trim()
  const object = String(value.object ?? '').trim()
  if (subject && predicate && object) {
    return formatDeleteRelationText(subject, predicate, object)
  }
  if (hash) {
    return hash
  }
  if (Array.isArray(value.target_hashes) && value.target_hashes.length > 0) {
    return `targets ${value.target_hashes.length}`
  }
  return trimDeleteItemText(JSON.stringify(value, null, 2), 120)
}

function pickFeedbackRelationTriplet(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object') {
    return null
  }
  const record = value as Record<string, unknown>
  const subject = String(record.subject ?? '').trim()
  const predicate = String(record.predicate ?? '').trim()
  const object = String(record.object ?? '').trim()
  if (!subject || !predicate || !object) {
    return null
  }
  return record
}

function formatFeedbackRelationTriplet(value: unknown): string {
  const triplet = pickFeedbackRelationTriplet(value)
  if (!triplet) {
    return ''
  }
  return formatDeleteRelationText(
    String(triplet.subject ?? ''),
    String(triplet.predicate ?? ''),
    String(triplet.object ?? ''),
  )
}

function getFeedbackCorrectionPreview(task: MemoryFeedbackCorrectionDetailTaskPayload | MemoryFeedbackCorrectionSummaryPayload | null): {
  headline: string
  oldRelation: string
  newRelation: string
} {
  if (!task) {
    return {
      headline: '当前没有纠错摘要',
      oldRelation: '',
      newRelation: '',
    }
  }

  const detailTask = task as MemoryFeedbackCorrectionDetailTaskPayload
  const rollbackPlanSummary = detailTask.rollback_plan_summary ?? {}
  const forgottenRelations = Array.isArray(rollbackPlanSummary.forgotten_relations)
    ? rollbackPlanSummary.forgotten_relations
    : []
  const correctedWrite = rollbackPlanSummary.corrected_write && typeof rollbackPlanSummary.corrected_write === 'object'
    ? rollbackPlanSummary.corrected_write
    : {}
  const correctedRelations = Array.isArray((correctedWrite as Record<string, unknown>).corrected_relations)
    ? ((correctedWrite as Record<string, unknown>).corrected_relations as unknown[])
    : []

  const oldRelation = formatFeedbackRelationTriplet(forgottenRelations[0])
  const newRelation = formatFeedbackRelationTriplet(correctedRelations[0])

  if (oldRelation && newRelation) {
    return {
      headline: `将“${oldRelation}”纠正为“${newRelation}”`,
      oldRelation,
      newRelation,
    }
  }
  if (newRelation) {
    return {
      headline: `补充了新的纠错结论：“${newRelation}”`,
      oldRelation: '',
      newRelation,
    }
  }
  if (oldRelation) {
    return {
      headline: `撤销了旧记忆关系：“${oldRelation}”`,
      oldRelation,
      newRelation: '',
    }
  }
  return {
    headline: task.query_text || '当前纠错没有可读摘要',
    oldRelation: '',
    newRelation: '',
  }
}

function buildFeedbackImpactSummary(task: MemoryFeedbackCorrectionDetailTaskPayload | MemoryFeedbackCorrectionSummaryPayload | null): string[] {
  if (!task) {
    return []
  }

  const counts = task.affected_counts ?? {}
  const items: string[] = []
  if (Number(counts.relations ?? 0) > 0) {
    items.push(`影响关系 ${Number(counts.relations ?? 0)} 条`)
  }
  if (Number(counts.corrected_relations ?? 0) > 0) {
    items.push(`新增纠正关系 ${Number(counts.corrected_relations ?? 0)} 条`)
  }
  if (Number(counts.correction_paragraphs ?? 0) > 0) {
    items.push(`写入纠错段落 ${Number(counts.correction_paragraphs ?? 0)} 条`)
  }
  if (Number(counts.stale_paragraphs ?? 0) > 0) {
    items.push(`标记旧段落 ${Number(counts.stale_paragraphs ?? 0)} 条`)
  }
  if (Number(counts.episode_sources ?? 0) > 0) {
    items.push(`触发 Episode 修复 ${Number(counts.episode_sources ?? 0)} 个来源`)
  }
  if (Number(counts.profile_person_ids ?? 0) > 0) {
    items.push(`触发 Profile 刷新 ${Number(counts.profile_person_ids ?? 0)} 个对象`)
  }
  return items
}

function formatFeedbackActionType(actionType: string): string {
  switch (actionType) {
    case 'classification':
      return '判定纠错'
    case 'forget_relation':
      return '撤销旧关系'
    case 'mark_stale_paragraph':
      return '标记旧段落'
    case 'write_correction':
      return '写入纠错'
    case 'rollback_restore_relation':
      return '恢复旧关系'
    case 'rollback_delete_correction_paragraph':
      return '隐藏纠错段落'
    case 'rollback_revert_corrected_relation':
      return '撤销纠正关系'
    case 'rollback_clear_stale_mark':
      return '清除脏段落标记'
    case 'rollback_enqueue_episode_rebuild':
      return '加入 Episode 修复队列'
    case 'rollback_enqueue_profile_refresh':
      return '加入 Profile 刷新队列'
    case 'rollback_error':
      return '回退失败'
    case 'error':
      return '处理失败'
    case 'skip':
      return '跳过处理'
    default:
      return actionType || '未知动作'
  }
}

function describeFeedbackActionLog(item: MemoryFeedbackActionLogPayload): string {
  const beforeSummary = summarizeFeedbackActionPayload(item.before_payload)
  const afterSummary = summarizeFeedbackActionPayload(item.after_payload)

  switch (item.action_type) {
    case 'classification':
      return afterSummary ? `系统完成判定：${afterSummary}` : '系统完成纠错判定'
    case 'forget_relation':
      return beforeSummary ? `旧关系已失效：${beforeSummary}` : '旧关系已被标记为失效'
    case 'mark_stale_paragraph':
      return '旧段落已标记为待复核，后续检索会更谨慎地使用它'
    case 'write_correction':
      return afterSummary ? `已写入新的纠错结果：${afterSummary}` : '已写入新的纠错段落和关系'
    case 'rollback_restore_relation':
      return afterSummary ? `已恢复旧关系状态：${afterSummary}` : '已恢复旧关系状态'
    case 'rollback_delete_correction_paragraph':
      return '已隐藏这次纠错写入的段落'
    case 'rollback_revert_corrected_relation':
      return '已撤销纠错阶段新增的关系'
    case 'rollback_clear_stale_mark':
      return '已清除旧段落的待复核标记'
    case 'rollback_enqueue_episode_rebuild':
      return '已重新加入 Episode 修复队列'
    case 'rollback_enqueue_profile_refresh':
      return '已重新加入 Profile 刷新队列'
    case 'rollback_error':
      return item.reason || '这次回退执行失败'
    case 'error':
      return item.reason || '这次纠错处理失败'
    case 'skip':
      return item.reason || '这次纠错被跳过'
    default:
      return afterSummary || beforeSummary || item.reason || '记录了一条动作日志'
  }
}

type DeleteOperationItem = NonNullable<MemoryDeleteOperationPayload['items']>[number]

function trimDeleteItemText(value: string, maxLength: number = 140): string {
  const normalized = String(value ?? '').trim().replace(/\s+/g, ' ')
  if (!normalized) {
    return ''
  }
  if (normalized.length <= maxLength) {
    return normalized
  }
  return `${normalized.slice(0, maxLength)}...`
}

function formatDeleteRelationText(subject: string, predicate: string, object: string): string {
  const left = String(subject ?? '').trim()
  const middle = String(predicate ?? '').trim()
  const right = String(object ?? '').trim()
  return [left, middle, right].filter(Boolean).join(' -> ')
}

function getDeleteOperationItemLabel(item: DeleteOperationItem): string {
  const payload = item.payload ?? {}
  if (item.item_type === 'entity') {
    const entity = (payload.entity ?? {}) as Record<string, unknown>
    return String(entity.name ?? item.item_key ?? item.item_hash ?? '未命名实体')
  }
  if (item.item_type === 'relation') {
    const relation = (payload.relation ?? {}) as Record<string, unknown>
    return (
      formatDeleteRelationText(
        String(relation.subject ?? ''),
        String(relation.predicate ?? ''),
        String(relation.object ?? ''),
      ) || String(item.item_key ?? item.item_hash ?? '未命名关系')
    )
  }
  if (item.item_type === 'paragraph') {
    const paragraph = (payload.paragraph ?? {}) as Record<string, unknown>
    const source = String(paragraph.source ?? '').trim()
    return source || String(item.item_key ?? item.item_hash ?? '未命名段落')
  }
  return String(item.item_key ?? item.item_hash ?? '未命名对象')
}

function getDeleteOperationItemPreview(item: DeleteOperationItem): string {
  const payload = item.payload ?? {}
  if (item.item_type === 'entity') {
    const paragraphLinks = Array.isArray(payload.paragraph_links) ? payload.paragraph_links : []
    if (paragraphLinks.length > 0) {
      return `关联段落 ${paragraphLinks.length} 个`
    }
    return '实体快照'
  }
  if (item.item_type === 'relation') {
    const relation = (payload.relation ?? {}) as Record<string, unknown>
    const paragraphHashes = Array.isArray(payload.paragraph_hashes) ? payload.paragraph_hashes : []
    const confidence = relation.confidence
    const parts = []
    if (paragraphHashes.length > 0) {
      parts.push(`证据段落 ${paragraphHashes.length} 个`)
    }
    if (typeof confidence === 'number') {
      parts.push(`置信度 ${confidence.toFixed(2)}`)
    }
    return parts.join('，') || '关系快照'
  }
  if (item.item_type === 'paragraph') {
    const paragraph = (payload.paragraph ?? {}) as Record<string, unknown>
    return trimDeleteItemText(String(paragraph.content ?? ''))
  }
  return ''
}

function getDeleteOperationItemSource(item: DeleteOperationItem): string {
  const payload = item.payload ?? {}
  if (item.item_type === 'paragraph') {
    const paragraph = (payload.paragraph ?? {}) as Record<string, unknown>
    return String(paragraph.source ?? '').trim()
  }
  return String(payload.source ?? '').trim()
}

export function KnowledgeBasePage() {
  const navigate = useNavigate()
  const { toast } = useToast()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [refreshingCheck, setRefreshingCheck] = useState(false)
  const [creatingImport, setCreatingImport] = useState(false)
  const [creatingTuning, setCreatingTuning] = useState(false)
  const [rawMode, setRawMode] = useState(false)

  const [schemaPayload, setSchemaPayload] = useState<MemoryConfigSchemaPayload | null>(null)
  const [visualConfig, setVisualConfig] = useState<Record<string, unknown>>({})
  const [rawConfig, setRawConfig] = useState('')
  const [rawConfigExists, setRawConfigExists] = useState(true)
  const [rawConfigUsingDefault, setRawConfigUsingDefault] = useState(false)
  const [runtimeConfig, setRuntimeConfig] = useState<MemoryRuntimeConfigPayload | null>(null)
  const [selfCheckReport, setSelfCheckReport] = useState<Record<string, unknown> | null>(null)
  const [importSettings, setImportSettings] = useState<MemoryImportSettings>({})
  const [importPathAliases, setImportPathAliases] = useState<Record<string, string>>({})
  const [importTasks, setImportTasks] = useState<MemoryImportTaskPayload[]>([])
  const [selectedImportTaskId, setSelectedImportTaskId] = useState('')
  const [selectedImportTask, setSelectedImportTask] = useState<MemoryImportTaskPayload | null>(null)
  const [selectedImportTaskLoading, setSelectedImportTaskLoading] = useState(false)
  const [selectedImportFileId, setSelectedImportFileId] = useState('')
  const [importChunkOffset, setImportChunkOffset] = useState(0)
  const [importChunksPayload, setImportChunksPayload] = useState<MemoryImportChunkListPayload | null>(null)
  const [importChunksLoading, setImportChunksLoading] = useState(false)
  const [importCreateMode, setImportCreateMode] = useState<MemoryImportTaskKind>('upload')
  const [importAutoPolling, setImportAutoPolling] = useState(true)
  const [importErrorText, setImportErrorText] = useState('')
  const [importCommonFileConcurrency, setImportCommonFileConcurrency] = useState('2')
  const [importCommonChunkConcurrency, setImportCommonChunkConcurrency] = useState('4')
  const [importCommonLlmEnabled, setImportCommonLlmEnabled] = useState(true)
  const [importCommonStrategyOverride, setImportCommonStrategyOverride] = useState('auto')
  const [importCommonDedupePolicy, setImportCommonDedupePolicy] = useState('content_hash')
  const [importCommonChatLog, setImportCommonChatLog] = useState(false)
  const [importCommonChatReferenceTime, setImportCommonChatReferenceTime] = useState('')
  const [importCommonForce, setImportCommonForce] = useState(false)
  const [importCommonClearManifest, setImportCommonClearManifest] = useState(false)

  const [uploadInputMode, setUploadInputMode] = useState<MemoryImportInputMode>('text')
  const [uploadFiles, setUploadFiles] = useState<File[]>([])

  const [pasteName, setPasteName] = useState('')
  const [pasteMode, setPasteMode] = useState<MemoryImportInputMode>('text')
  const [pasteContent, setPasteContent] = useState('')

  const [rawAlias, setRawAlias] = useState('raw')
  const [rawRelativePath, setRawRelativePath] = useState('')
  const [rawGlob, setRawGlob] = useState('*')
  const [rawInputMode, setRawInputMode] = useState<MemoryImportInputMode>('text')
  const [rawRecursive, setRawRecursive] = useState(true)

  const [openieAlias, setOpenieAlias] = useState('lpmm')
  const [openieRelativePath, setOpenieRelativePath] = useState('')
  const [openieIncludeAllJson, setOpenieIncludeAllJson] = useState(false)

  const [convertAlias, setConvertAlias] = useState('lpmm')
  const [convertRelativePath, setConvertRelativePath] = useState('')
  const [convertTargetAlias, setConvertTargetAlias] = useState('plugin_data')
  const [convertTargetRelativePath, setConvertTargetRelativePath] = useState('')
  const [convertDimension, setConvertDimension] = useState('')
  const [convertBatchSize, setConvertBatchSize] = useState('1024')

  const [backfillAlias, setBackfillAlias] = useState('plugin_data')
  const [backfillRelativePath, setBackfillRelativePath] = useState('')
  const [backfillLimit, setBackfillLimit] = useState('100000')
  const [backfillDryRun, setBackfillDryRun] = useState(false)
  const [backfillNoCreatedFallback, setBackfillNoCreatedFallback] = useState(false)

  const [maibotSourceDb, setMaibotSourceDb] = useState('')
  const [maibotTimeFrom, setMaibotTimeFrom] = useState('')
  const [maibotTimeTo, setMaibotTimeTo] = useState('')
  const [maibotStartId, setMaibotStartId] = useState('')
  const [maibotEndId, setMaibotEndId] = useState('')
  const [maibotStreamIds, setMaibotStreamIds] = useState('')
  const [maibotGroupIds, setMaibotGroupIds] = useState('')
  const [maibotUserIds, setMaibotUserIds] = useState('')
  const [maibotReadBatchSize, setMaibotReadBatchSize] = useState('2000')
  const [maibotCommitWindowRows, setMaibotCommitWindowRows] = useState('20000')
  const [maibotEmbedWorkers, setMaibotEmbedWorkers] = useState('')
  const [maibotNoResume, setMaibotNoResume] = useState(false)
  const [maibotResetState, setMaibotResetState] = useState(false)
  const [maibotDryRun, setMaibotDryRun] = useState(false)
  const [maibotVerifyOnly, setMaibotVerifyOnly] = useState(false)

  const [pathResolveAlias, setPathResolveAlias] = useState('raw')
  const [pathResolveRelativePath, setPathResolveRelativePath] = useState('')
  const [pathResolveMustExist, setPathResolveMustExist] = useState(true)
  const [pathResolveOutput, setPathResolveOutput] = useState('')
  const [resolvingPath, setResolvingPath] = useState(false)

  const [tuningTasks, setTuningTasks] = useState<MemoryTaskPayload[]>([])
  const [tuningProfile, setTuningProfile] = useState<Record<string, unknown>>({})
  const [tuningProfileToml, setTuningProfileToml] = useState('')
  const [memorySources, setMemorySources] = useState<MemorySourceItemPayload[]>([])
  const [deleteOperations, setDeleteOperations] = useState<MemoryDeleteOperationPayload[]>([])
  const [selectedOperationDetail, setSelectedOperationDetail] = useState<MemoryDeleteOperationPayload | null>(null)
  const [selectedOperationDetailLoading, setSelectedOperationDetailLoading] = useState(false)
  const [selectedOperationDetailError, setSelectedOperationDetailError] = useState('')
  const [sourceSearch, setSourceSearch] = useState('')
  const [operationSearch, setOperationSearch] = useState('')
  const [operationModeFilter, setOperationModeFilter] = useState('all')
  const [operationStatusFilter, setOperationStatusFilter] = useState('all')
  const [operationPage, setOperationPage] = useState(1)
  const [selectedOperationId, setSelectedOperationId] = useState('')
  const [selectedOperationItemSearch, setSelectedOperationItemSearch] = useState('')
  const [selectedOperationItemPage, setSelectedOperationItemPage] = useState(1)
  const [selectedSources, setSelectedSources] = useState<string[]>([])
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [deleteDialogTitle, setDeleteDialogTitle] = useState('删除预览')
  const [deleteDialogDescription, setDeleteDialogDescription] = useState('')
  const [deletePreview, setDeletePreview] = useState<Awaited<ReturnType<typeof previewMemoryDelete>> | null>(null)
  const [deletePreviewError, setDeletePreviewError] = useState<string | null>(null)
  const [deletePreviewLoading, setDeletePreviewLoading] = useState(false)
  const [deleteExecuting, setDeleteExecuting] = useState(false)
  const [deleteRestoring, setDeleteRestoring] = useState(false)
  const [deleteResult, setDeleteResult] = useState<MemoryDeleteExecutePayload | null>(null)
  const [pendingDeleteRequest, setPendingDeleteRequest] = useState<MemoryDeleteRequestPayload | null>(null)
  const [feedbackCorrections, setFeedbackCorrections] = useState<MemoryFeedbackCorrectionSummaryPayload[]>([])
  const [feedbackSearch, setFeedbackSearch] = useState('')
  const [feedbackStatusFilter, setFeedbackStatusFilter] = useState('all')
  const [feedbackRollbackFilter, setFeedbackRollbackFilter] = useState('all')
  const [feedbackPage, setFeedbackPage] = useState(1)
  const [selectedFeedbackTaskId, setSelectedFeedbackTaskId] = useState(0)
  const [selectedFeedbackTaskDetail, setSelectedFeedbackTaskDetail] = useState<MemoryFeedbackCorrectionDetailTaskPayload | null>(null)
  const [selectedFeedbackTaskLoading, setSelectedFeedbackTaskLoading] = useState(false)
  const [selectedFeedbackTaskError, setSelectedFeedbackTaskError] = useState('')
  const [feedbackActionLogSearch, setFeedbackActionLogSearch] = useState('')
  const [feedbackActionLogPage, setFeedbackActionLogPage] = useState(1)
  const [feedbackRollbackDialogOpen, setFeedbackRollbackDialogOpen] = useState(false)
  const [feedbackRollbackReason, setFeedbackRollbackReason] = useState('')
  const [feedbackRollingBack, setFeedbackRollingBack] = useState(false)
  const [tuningObjective, setTuningObjective] = useState('precision_priority')
  const [tuningIntensity, setTuningIntensity] = useState('standard')
  const [tuningSampleSize, setTuningSampleSize] = useState('24')
  const [tuningTopKEval, setTuningTopKEval] = useState('20')

  const loadPage = useCallback(async () => {
    try {
      setLoading(true)
      const [
        schema,
        configPayload,
        rawPayload,
        runtimePayload,
        importSettingsPayload,
        pathAliasPayload,
        importTaskPayload,
        tuningProfilePayload,
        tuningTaskPayload,
        sourcePayload,
        deleteOperationPayload,
        feedbackCorrectionPayload,
      ] = await Promise.all([
        getMemoryConfigSchema(),
        getMemoryConfig(),
        getMemoryConfigRaw(),
        getMemoryRuntimeConfig(),
        getMemoryImportSettings(),
        getMemoryImportPathAliases(),
        getMemoryImportTasks(20),
        getMemoryTuningProfile(),
        getMemoryTuningTasks(20),
        getMemorySources(),
        getMemoryDeleteOperations(DELETE_OPERATION_FETCH_LIMIT),
        getMemoryFeedbackCorrections({ limit: FEEDBACK_CORRECTION_FETCH_LIMIT }),
      ])

      setSchemaPayload(schema)
      setVisualConfig(configPayload.config ?? {})
      setRawConfig(rawPayload.config ?? '')
      setRawConfigExists(rawPayload.exists ?? true)
      setRawConfigUsingDefault(rawPayload.using_default ?? false)
      setRuntimeConfig(runtimePayload)
      setImportSettings(importSettingsPayload.settings ?? {})
      setImportPathAliases(pathAliasPayload.path_aliases ?? {})
      setImportTasks(importTaskPayload.items ?? [])
      setTuningProfile(tuningProfilePayload.profile ?? {})
      setTuningProfileToml(tuningProfilePayload.toml ?? '')
      setTuningTasks(tuningTaskPayload.items ?? [])
      setMemorySources(sourcePayload.items ?? [])
      setDeleteOperations(deleteOperationPayload.items ?? [])
      setFeedbackCorrections(feedbackCorrectionPayload.items ?? [])
      if (!selectedImportTaskId && (importTaskPayload.items ?? []).length > 0) {
        const initialTaskId = String(importTaskPayload.items?.[0]?.task_id ?? '')
        if (initialTaskId) {
          setSelectedImportTaskId(initialTaskId)
        }
      }
      if (!maibotSourceDb && String(importSettingsPayload.settings?.maibot_source_db_default ?? '').trim()) {
        setMaibotSourceDb(String(importSettingsPayload.settings?.maibot_source_db_default ?? '').trim())
      }
      if (!pathResolveAlias) {
        const aliasKeys = Object.keys(pathAliasPayload.path_aliases ?? {})
        if (aliasKeys.length > 0) {
          setPathResolveAlias(aliasKeys[0])
        }
      }
    } catch (error) {
      toast({
        title: '加载长期记忆控制台失败',
        description: error instanceof Error ? error.message : '未知错误',
        variant: 'destructive',
      })
    } finally {
      setLoading(false)
    }
  }, [maibotSourceDb, pathResolveAlias, selectedImportTaskId, toast])

  useEffect(() => {
    void loadPage()
  }, [loadPage])

  const configPath = schemaPayload?.path ?? 'config/a_memorix.toml'
  const schema = schemaPayload?.schema

  const runtimeBadges = useMemo(() => {
    if (!runtimeConfig) {
      return []
    }
    return [
      {
        label: '运行状态',
        value: runtimeConfig.runtime_ready ? '就绪' : '未就绪',
        description: runtimeConfig.embedding_degraded ? 'Embedding 降级运行' : '运行时检查通过',
        icon: runtimeConfig.runtime_ready ? CheckCircle2 : CircleAlert,
        className: runtimeConfig.runtime_ready ? 'border-emerald-500/20 bg-emerald-500/5' : 'border-amber-500/20 bg-amber-500/5',
        iconClassName: runtimeConfig.runtime_ready ? 'text-emerald-500' : 'text-amber-500',
      },
      {
        label: 'Embedding 维度',
        value: String(runtimeConfig.embedding_dimension),
        description: runtimeConfig.relation_vectors_enabled ? '关系向量已启用' : '关系向量未启用',
        icon: HardDrive,
        className: 'border-sky-500/20 bg-sky-500/5',
        iconClassName: 'text-sky-500',
      },
      {
        label: '自动保存',
        value: runtimeConfig.auto_save ? '开启' : '关闭',
        description: runtimeConfig.auto_save ? '运行数据会自动落盘' : '请留意手动保存',
        icon: runtimeConfig.auto_save ? CheckCircle2 : CircleAlert,
        className: runtimeConfig.auto_save ? 'border-primary/20 bg-primary/5' : 'border-muted-foreground/20 bg-muted/30',
        iconClassName: runtimeConfig.auto_save ? 'text-primary' : 'text-muted-foreground',
      },
      {
        label: '数据目录',
        value: runtimeConfig.data_dir,
        description: '长期记忆存储位置',
        icon: FolderOpen,
        className: 'border-violet-500/20 bg-violet-500/5',
        iconClassName: 'text-violet-500',
      },
    ]
  }, [runtimeConfig])

  const importPollInterval = useMemo(
    () => Math.max(200, Number(importSettings.poll_interval_ms ?? 1000)),
    [importSettings.poll_interval_ms],
  )

  const importAliasKeys = useMemo(
    () => Object.keys(importPathAliases).sort((left, right) => left.localeCompare(right)),
    [importPathAliases],
  )

  const runningImportTasks = useMemo(
    () => importTasks.filter((task) => RUNNING_IMPORT_STATUS.has(String(task.status ?? '').trim())),
    [importTasks],
  )
  const queuedImportTasks = useMemo(
    () => importTasks.filter((task) => QUEUED_IMPORT_STATUS.has(String(task.status ?? '').trim())),
    [importTasks],
  )
  const recentImportTasks = useMemo(
    () =>
      importTasks.filter((task) => {
        const status = String(task.status ?? '').trim()
        return !RUNNING_IMPORT_STATUS.has(status) && !QUEUED_IMPORT_STATUS.has(status)
      }),
    [importTasks],
  )
  const selectedImportTaskSummary = useMemo(() => {
    if (!selectedImportTaskId) {
      return null
    }
    return importTasks.find((task) => task.task_id === selectedImportTaskId) ?? null
  }, [importTasks, selectedImportTaskId])

  const selectedImportFiles = useMemo(() => {
    return Array.isArray(selectedImportTask?.files) ? selectedImportTask.files : []
  }, [selectedImportTask?.files])

  const selectedImportChunks = useMemo(() => {
    return Array.isArray(importChunksPayload?.items) ? importChunksPayload.items : []
  }, [importChunksPayload?.items])

  const selectedImportTaskResolved = selectedImportTask ?? selectedImportTaskSummary
  const selectedImportTaskErrorText = String(selectedImportTaskResolved?.error ?? '').trim()
  const selectedImportRetrySummary = selectedImportTaskResolved?.retry_summary

  const importChunkTotal = Number(importChunksPayload?.total ?? 0)
  const canImportChunkPrev = importChunkOffset > 0
  const canImportChunkNext = importChunkOffset + IMPORT_CHUNK_PAGE_SIZE < importChunkTotal

  const buildCommonImportPayload = useCallback((): Record<string, unknown> => {
    const payload: Record<string, unknown> = {
      llm_enabled: importCommonLlmEnabled,
      strategy_override: importCommonStrategyOverride,
      dedupe_policy: importCommonDedupePolicy,
      chat_log: importCommonChatLog,
      force: importCommonForce,
      clear_manifest: importCommonClearManifest,
    }

    const fileConcurrency = parseOptionalPositiveInt(importCommonFileConcurrency)
    const chunkConcurrency = parseOptionalPositiveInt(importCommonChunkConcurrency)
    if (fileConcurrency !== undefined) {
      payload.file_concurrency = fileConcurrency
    }
    if (chunkConcurrency !== undefined) {
      payload.chunk_concurrency = chunkConcurrency
    }
    if (importCommonChatReferenceTime.trim()) {
      payload.chat_reference_time = importCommonChatReferenceTime.trim()
    }
    return payload
  }, [
    importCommonChatLog,
    importCommonChatReferenceTime,
    importCommonChunkConcurrency,
    importCommonClearManifest,
    importCommonDedupePolicy,
    importCommonFileConcurrency,
    importCommonForce,
    importCommonLlmEnabled,
    importCommonStrategyOverride,
  ])

  const refreshImportQueue = useCallback(async (silent: boolean = false) => {
    try {
      const [taskPayload, settingsPayload, pathAliasPayload] = await Promise.all([
        getMemoryImportTasks(20),
        getMemoryImportSettings(),
        getMemoryImportPathAliases(),
      ])
      const nextTasks = taskPayload.items ?? []
      setImportTasks(nextTasks)
      setImportSettings(settingsPayload.settings ?? {})
      setImportPathAliases(pathAliasPayload.path_aliases ?? {})
      setImportErrorText('')

      if (nextTasks.length <= 0) {
        setSelectedImportTaskId('')
        setSelectedImportTask(null)
        setSelectedImportFileId('')
        setImportChunksPayload(null)
        return
      }

      if (!selectedImportTaskId || !nextTasks.some((item) => item.task_id === selectedImportTaskId)) {
        setSelectedImportTaskId(nextTasks[0].task_id)
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : '刷新导入任务失败'
      setImportErrorText(message)
      if (!silent) {
        toast({
          title: '刷新导入任务失败',
          description: message,
          variant: 'destructive',
        })
      }
    }
  }, [selectedImportTaskId, toast])

  const loadImportChunks = useCallback(
    async (
      taskId: string,
      fileId: string,
      offset: number = 0,
      silent: boolean = false,
    ) => {
      if (!taskId || !fileId) {
        setImportChunksPayload(null)
        return
      }
      try {
        setImportChunksLoading(true)
        const payload = await getMemoryImportTaskChunks(taskId, fileId, offset, IMPORT_CHUNK_PAGE_SIZE)
        if (!payload.success) {
          throw new Error(payload.error || '加载分块详情失败')
        }
        setImportChunksPayload(payload)
        setImportErrorText('')
      } catch (error) {
        const message = error instanceof Error ? error.message : '加载分块详情失败'
        setImportChunksPayload(null)
        setImportErrorText(message)
        if (!silent) {
          toast({
            title: '加载分块详情失败',
            description: message,
            variant: 'destructive',
          })
        }
      } finally {
        setImportChunksLoading(false)
      }
    },
    [toast],
  )

  const loadImportTaskDetail = useCallback(
    async (taskId: string, silent: boolean = false) => {
      if (!taskId) {
        setSelectedImportTask(null)
        setSelectedImportFileId('')
        setImportChunksPayload(null)
        return
      }
      try {
        if (!silent) {
          setSelectedImportTaskLoading(true)
        }
        const payload = await getMemoryImportTask(taskId, false)
        if (!payload.success || !payload.task) {
          throw new Error(payload.error || '任务不存在')
        }
        const task = payload.task
        setSelectedImportTask(task)
        setImportErrorText('')
        const files = Array.isArray(task.files) ? task.files : []
        const keepCurrentFile = files.some((file) => file.file_id === selectedImportFileId)
        const nextFileId = keepCurrentFile ? selectedImportFileId : String(files[0]?.file_id ?? '')
        const nextOffset = keepCurrentFile ? importChunkOffset : 0
        if (!keepCurrentFile) {
          setImportChunkOffset(0)
        }
        setSelectedImportFileId(nextFileId)
        if (nextFileId) {
          await loadImportChunks(taskId, nextFileId, nextOffset, silent)
        } else {
          setImportChunksPayload(null)
        }
      } catch (error) {
        const message = error instanceof Error ? error.message : '加载导入任务详情失败'
        setSelectedImportTask(null)
        setSelectedImportFileId('')
        setImportChunksPayload(null)
        setImportErrorText(message)
        if (!silent) {
          toast({
            title: '加载导入任务详情失败',
            description: message,
            variant: 'destructive',
          })
        }
      } finally {
        if (!silent) {
          setSelectedImportTaskLoading(false)
        }
      }
    },
    [importChunkOffset, loadImportChunks, selectedImportFileId, toast],
  )

  const afterImportTaskCreated = useCallback(
    async (taskId: string, successTitle: string) => {
      await refreshImportQueue(true)
      if (taskId) {
        setSelectedImportTaskId(taskId)
        await loadImportTaskDetail(taskId, true)
      }
      toast({
        title: successTitle,
        description: taskId ? `任务 ${taskId.slice(0, 12)} 已加入导入队列` : '导入任务已加入队列',
      })
    },
    [loadImportTaskDetail, refreshImportQueue, toast],
  )

  const submitUploadImport = useCallback(async () => {
    if (uploadFiles.length <= 0) {
      toast({
        title: '请选择上传文件',
        description: '至少选择一个 txt/md/json 文件后再提交',
        variant: 'destructive',
      })
      return
    }
    try {
      setCreatingImport(true)
      const payload = {
        ...buildCommonImportPayload(),
        input_mode: uploadInputMode,
      }
      const result = await createMemoryUploadImport(uploadFiles, payload)
      if (!result.success) {
        throw new Error(result.error || '创建上传导入任务失败')
      }
      const taskId = String(result.task?.task_id ?? '')
      setUploadFiles([])
      await afterImportTaskCreated(taskId, '上传导入任务已创建')
    } catch (error) {
      const message = error instanceof Error ? error.message : '创建上传导入任务失败'
      setImportErrorText(message)
      toast({
        title: '创建上传导入任务失败',
        description: message,
        variant: 'destructive',
      })
    } finally {
      setCreatingImport(false)
    }
  }, [afterImportTaskCreated, buildCommonImportPayload, toast, uploadFiles, uploadInputMode])

  const submitPasteImport = useCallback(async () => {
    if (!pasteContent.trim()) {
      toast({
        title: '粘贴内容不能为空',
        description: '请填写导入内容后再提交',
        variant: 'destructive',
      })
      return
    }
    try {
      setCreatingImport(true)
      const result = await createMemoryPasteImport({
        ...buildCommonImportPayload(),
        name: pasteName || undefined,
        content: pasteContent,
        input_mode: pasteMode,
      })
      if (!result.success) {
        throw new Error(result.error || '创建粘贴导入任务失败')
      }
      const taskId = String(result.task?.task_id ?? '')
      setPasteContent('')
      setPasteName('')
      await afterImportTaskCreated(taskId, '粘贴导入任务已创建')
    } catch (error) {
      const message = error instanceof Error ? error.message : '创建粘贴导入任务失败'
      setImportErrorText(message)
      toast({
        title: '创建粘贴导入任务失败',
        description: message,
        variant: 'destructive',
      })
    } finally {
      setCreatingImport(false)
    }
  }, [afterImportTaskCreated, buildCommonImportPayload, pasteContent, pasteMode, pasteName, toast])

  const submitRawScanImport = useCallback(async () => {
    try {
      setCreatingImport(true)
      const result = await createMemoryRawScanImport({
        ...buildCommonImportPayload(),
        alias: rawAlias,
        relative_path: rawRelativePath,
        glob: rawGlob,
        recursive: rawRecursive,
        input_mode: rawInputMode,
      })
      if (!result.success) {
        throw new Error(result.error || '创建本地扫描任务失败')
      }
      await afterImportTaskCreated(String(result.task?.task_id ?? ''), '本地扫描任务已创建')
    } catch (error) {
      const message = error instanceof Error ? error.message : '创建本地扫描任务失败'
      setImportErrorText(message)
      toast({
        title: '创建本地扫描任务失败',
        description: message,
        variant: 'destructive',
      })
    } finally {
      setCreatingImport(false)
    }
  }, [
    afterImportTaskCreated,
    buildCommonImportPayload,
    rawAlias,
    rawGlob,
    rawInputMode,
    rawRecursive,
    rawRelativePath,
    toast,
  ])

  const submitOpenieImport = useCallback(async () => {
    try {
      setCreatingImport(true)
      const result = await createMemoryLpmmOpenieImport({
        ...buildCommonImportPayload(),
        alias: openieAlias,
        relative_path: openieRelativePath,
        include_all_json: openieIncludeAllJson,
      })
      if (!result.success) {
        throw new Error(result.error || '创建 LPMM OpenIE 任务失败')
      }
      await afterImportTaskCreated(String(result.task?.task_id ?? ''), 'LPMM OpenIE 任务已创建')
    } catch (error) {
      const message = error instanceof Error ? error.message : '创建 LPMM OpenIE 任务失败'
      setImportErrorText(message)
      toast({
        title: '创建 LPMM OpenIE 任务失败',
        description: message,
        variant: 'destructive',
      })
    } finally {
      setCreatingImport(false)
    }
  }, [
    afterImportTaskCreated,
    buildCommonImportPayload,
    openieAlias,
    openieIncludeAllJson,
    openieRelativePath,
    toast,
  ])

  const submitConvertImport = useCallback(async () => {
    try {
      setCreatingImport(true)
      const result = await createMemoryLpmmConvertImport({
        alias: convertAlias,
        relative_path: convertRelativePath,
        target_alias: convertTargetAlias,
        target_relative_path: convertTargetRelativePath,
        dimension: parseOptionalPositiveInt(convertDimension),
        batch_size: parseOptionalPositiveInt(convertBatchSize),
      })
      if (!result.success) {
        throw new Error(result.error || '创建 LPMM 转换任务失败')
      }
      await afterImportTaskCreated(String(result.task?.task_id ?? ''), 'LPMM 转换任务已创建')
    } catch (error) {
      const message = error instanceof Error ? error.message : '创建 LPMM 转换任务失败'
      setImportErrorText(message)
      toast({
        title: '创建 LPMM 转换任务失败',
        description: message,
        variant: 'destructive',
      })
    } finally {
      setCreatingImport(false)
    }
  }, [
    afterImportTaskCreated,
    convertAlias,
    convertBatchSize,
    convertDimension,
    convertRelativePath,
    convertTargetAlias,
    convertTargetRelativePath,
    toast,
  ])

  const submitBackfillImport = useCallback(async () => {
    try {
      setCreatingImport(true)
      const result = await createMemoryTemporalBackfillImport({
        alias: backfillAlias,
        relative_path: backfillRelativePath,
        limit: parseOptionalPositiveInt(backfillLimit),
        dry_run: backfillDryRun,
        no_created_fallback: backfillNoCreatedFallback,
      })
      if (!result.success) {
        throw new Error(result.error || '创建时序回填任务失败')
      }
      await afterImportTaskCreated(String(result.task?.task_id ?? ''), '时序回填任务已创建')
    } catch (error) {
      const message = error instanceof Error ? error.message : '创建时序回填任务失败'
      setImportErrorText(message)
      toast({
        title: '创建时序回填任务失败',
        description: message,
        variant: 'destructive',
      })
    } finally {
      setCreatingImport(false)
    }
  }, [
    afterImportTaskCreated,
    backfillAlias,
    backfillDryRun,
    backfillLimit,
    backfillNoCreatedFallback,
    backfillRelativePath,
    toast,
  ])

  const submitMaibotMigrationImport = useCallback(async () => {
    try {
      setCreatingImport(true)
      const result = await createMemoryMaibotMigrationImport({
        source_db: maibotSourceDb || undefined,
        time_from: maibotTimeFrom || undefined,
        time_to: maibotTimeTo || undefined,
        start_id: parseOptionalPositiveInt(maibotStartId),
        end_id: parseOptionalPositiveInt(maibotEndId),
        stream_ids: parseCommaSeparatedList(maibotStreamIds),
        group_ids: parseCommaSeparatedList(maibotGroupIds),
        user_ids: parseCommaSeparatedList(maibotUserIds),
        read_batch_size: parseOptionalPositiveInt(maibotReadBatchSize),
        commit_window_rows: parseOptionalPositiveInt(maibotCommitWindowRows),
        embed_workers: parseOptionalPositiveInt(maibotEmbedWorkers),
        no_resume: maibotNoResume,
        reset_state: maibotResetState,
        dry_run: maibotDryRun,
        verify_only: maibotVerifyOnly,
      })
      if (!result.success) {
        throw new Error(result.error || '创建 MaiBot 迁移任务失败')
      }
      await afterImportTaskCreated(String(result.task?.task_id ?? ''), 'MaiBot 迁移任务已创建')
    } catch (error) {
      const message = error instanceof Error ? error.message : '创建 MaiBot 迁移任务失败'
      setImportErrorText(message)
      toast({
        title: '创建 MaiBot 迁移任务失败',
        description: message,
        variant: 'destructive',
      })
    } finally {
      setCreatingImport(false)
    }
  }, [
    afterImportTaskCreated,
    maibotCommitWindowRows,
    maibotDryRun,
    maibotEmbedWorkers,
    maibotEndId,
    maibotGroupIds,
    maibotNoResume,
    maibotReadBatchSize,
    maibotResetState,
    maibotSourceDb,
    maibotStartId,
    maibotStreamIds,
    maibotTimeFrom,
    maibotTimeTo,
    maibotUserIds,
    maibotVerifyOnly,
    toast,
  ])

  const cancelSelectedImportTask = useCallback(async () => {
    if (!selectedImportTaskId) {
      return
    }
    try {
      const payload = await cancelMemoryImportTask(selectedImportTaskId)
      if (!payload.success) {
        throw new Error(payload.error || '取消导入任务失败')
      }
      await refreshImportQueue(true)
      await loadImportTaskDetail(selectedImportTaskId, true)
      toast({
        title: '已请求取消任务',
        description: `任务 ${selectedImportTaskId.slice(0, 12)} 正在取消`,
      })
    } catch (error) {
      const message = error instanceof Error ? error.message : '取消导入任务失败'
      setImportErrorText(message)
      toast({
        title: '取消导入任务失败',
        description: message,
        variant: 'destructive',
      })
    }
  }, [loadImportTaskDetail, refreshImportQueue, selectedImportTaskId, toast])

  const retrySelectedImportTask = useCallback(async () => {
    if (!selectedImportTaskId) {
      return
    }
    try {
      const payload = await retryMemoryImportTask(selectedImportTaskId, {
        overrides: buildCommonImportPayload(),
      })
      if (!payload.success) {
        throw new Error(payload.error || '重试失败项失败')
      }
      const nextTaskId = String(payload.task?.task_id ?? '')
      await refreshImportQueue(true)
      if (nextTaskId) {
        setSelectedImportTaskId(nextTaskId)
        await loadImportTaskDetail(nextTaskId, true)
      } else {
        await loadImportTaskDetail(selectedImportTaskId, true)
      }
      toast({
        title: '重试任务已创建',
        description: nextTaskId ? `重试任务 ${nextTaskId.slice(0, 12)} 已进入队列` : '失败项已提交重试',
      })
    } catch (error) {
      const message = error instanceof Error ? error.message : '重试失败项失败'
      setImportErrorText(message)
      toast({
        title: '重试失败项失败',
        description: message,
        variant: 'destructive',
      })
    }
  }, [buildCommonImportPayload, loadImportTaskDetail, refreshImportQueue, selectedImportTaskId, toast])

  const resolveImportPath = useCallback(async () => {
    if (!pathResolveAlias.trim()) {
      return
    }
    try {
      setResolvingPath(true)
      const payload = await resolveMemoryImportPath({
        alias: pathResolveAlias,
        relative_path: pathResolveRelativePath,
        must_exist: pathResolveMustExist,
      })
      const lines = [
        `路径别名: ${payload.alias}`,
        `相对路径: ${payload.relative_path || '(空)'}`,
        `解析结果: ${payload.resolved_path}`,
        `是否存在: ${String(payload.exists)}`,
        `是否文件: ${String(payload.is_file)}`,
        `是否目录: ${String(payload.is_dir)}`,
      ]
      setPathResolveOutput(lines.join('\n'))
    } catch (error) {
      const message = error instanceof Error ? error.message : '路径解析失败'
      setPathResolveOutput(`解析失败：${message}`)
    } finally {
      setResolvingPath(false)
    }
  }, [pathResolveAlias, pathResolveMustExist, pathResolveRelativePath])

  const selectImportTask = useCallback(
    async (taskId: string) => {
      setSelectedImportTaskId(taskId)
      setImportChunkOffset(0)
      await loadImportTaskDetail(taskId)
    },
    [loadImportTaskDetail],
  )

  const selectImportFile = useCallback(
    async (fileId: string) => {
      if (!selectedImportTaskId) {
        return
      }
      setSelectedImportFileId(fileId)
      setImportChunkOffset(0)
      await loadImportChunks(selectedImportTaskId, fileId, 0)
    },
    [loadImportChunks, selectedImportTaskId],
  )

  const moveImportChunkPage = useCallback(
    async (direction: -1 | 1) => {
      if (!selectedImportTaskId || !selectedImportFileId) {
        return
      }
      const nextOffset =
        direction < 0
          ? Math.max(0, importChunkOffset - IMPORT_CHUNK_PAGE_SIZE)
          : importChunkOffset + IMPORT_CHUNK_PAGE_SIZE
      if (nextOffset === importChunkOffset) {
        return
      }
      setImportChunkOffset(nextOffset)
      await loadImportChunks(selectedImportTaskId, selectedImportFileId, nextOffset)
    },
    [importChunkOffset, loadImportChunks, selectedImportFileId, selectedImportTaskId],
  )

  useEffect(() => {
    if (importAliasKeys.length <= 0) {
      return
    }
    const pickAlias = (current: string, preferred: string): string => {
      if (current && importAliasKeys.includes(current)) {
        return current
      }
      if (importAliasKeys.includes(preferred)) {
        return preferred
      }
      return importAliasKeys[0]
    }
    setRawAlias((current) => pickAlias(current, 'raw'))
    setOpenieAlias((current) => pickAlias(current, 'lpmm'))
    setConvertAlias((current) => pickAlias(current, 'lpmm'))
    setConvertTargetAlias((current) => pickAlias(current, 'plugin_data'))
    setBackfillAlias((current) => pickAlias(current, 'plugin_data'))
    setPathResolveAlias((current) => pickAlias(current, 'raw'))
  }, [importAliasKeys])

  useEffect(() => {
    const defaultFileConcurrency = String(importSettings.default_file_concurrency ?? '').trim()
    const defaultChunkConcurrency = String(importSettings.default_chunk_concurrency ?? '').trim()
    if (defaultFileConcurrency && importCommonFileConcurrency === '2') {
      setImportCommonFileConcurrency(defaultFileConcurrency)
    }
    if (defaultChunkConcurrency && importCommonChunkConcurrency === '4') {
      setImportCommonChunkConcurrency(defaultChunkConcurrency)
    }
    const defaultSourceDb = String(importSettings.maibot_source_db_default ?? '').trim()
    if (defaultSourceDb && !maibotSourceDb.trim()) {
      setMaibotSourceDb(defaultSourceDb)
    }
  }, [
    importCommonChunkConcurrency,
    importCommonFileConcurrency,
    importSettings.default_chunk_concurrency,
    importSettings.default_file_concurrency,
    importSettings.maibot_source_db_default,
    maibotSourceDb,
  ])

  useEffect(() => {
    if (!selectedImportTaskId && importTasks.length > 0) {
      void selectImportTask(importTasks[0].task_id)
    }
  }, [importTasks, selectImportTask, selectedImportTaskId])

  useEffect(() => {
    if (!selectedImportTaskId) {
      setSelectedImportTask(null)
      setSelectedImportFileId('')
      setImportChunksPayload(null)
      return
    }
    if (!importTasks.some((task) => task.task_id === selectedImportTaskId) && importTasks.length > 0) {
      void selectImportTask(importTasks[0].task_id)
      return
    }
    void loadImportTaskDetail(selectedImportTaskId, true)
  }, [importTasks, loadImportTaskDetail, selectImportTask, selectedImportTaskId])

  useEffect(() => {
    if (!importAutoPolling) {
      return
    }
    const timerId = window.setInterval(() => {
      void refreshImportQueue(true)
      if (selectedImportTaskId) {
        void loadImportTaskDetail(selectedImportTaskId, true)
      }
    }, importPollInterval)
    return () => {
      window.clearInterval(timerId)
    }
  }, [importAutoPolling, importPollInterval, loadImportTaskDetail, refreshImportQueue, selectedImportTaskId])

  const filteredSources = useMemo(() => {
    const keyword = sourceSearch.trim().toLowerCase()
    if (!keyword) {
      return memorySources
    }
    return memorySources.filter((item) => String(item.source ?? '').toLowerCase().includes(keyword))
  }, [memorySources, sourceSearch])

  const filteredDeleteOperations = useMemo(() => {
    const keyword = operationSearch.trim().toLowerCase()
    return deleteOperations.filter((operation) => {
      const mode = String(operation.mode ?? '').trim()
      const status = String(operation.status ?? '').trim()
      const summary = operation.summary ?? {}
      const sources = Array.isArray(summary.sources) ? summary.sources : []

      if (operationModeFilter !== 'all' && mode !== operationModeFilter) {
        return false
      }
      if (operationStatusFilter !== 'all' && status !== operationStatusFilter) {
        return false
      }
      if (!keyword) {
        return true
      }

      return [
        operation.operation_id,
        operation.reason,
        operation.requested_by,
        mode,
        status,
        ...sources.map((item) => String(item)),
      ]
        .map((item) => String(item ?? '').toLowerCase())
        .some((item) => item.includes(keyword))
    })
  }, [deleteOperations, operationModeFilter, operationSearch, operationStatusFilter])

  const deleteOperationPageCount = Math.max(1, Math.ceil(filteredDeleteOperations.length / DELETE_OPERATION_PAGE_SIZE))
  const pagedDeleteOperations = useMemo(() => {
    const start = (operationPage - 1) * DELETE_OPERATION_PAGE_SIZE
    return filteredDeleteOperations.slice(start, start + DELETE_OPERATION_PAGE_SIZE)
  }, [filteredDeleteOperations, operationPage])

  const selectedDeleteOperation = useMemo(
    () => filteredDeleteOperations.find((operation) => operation.operation_id === selectedOperationId) ?? pagedDeleteOperations[0] ?? null,
    [filteredDeleteOperations, pagedDeleteOperations, selectedOperationId],
  )

  useEffect(() => {
    setOperationPage(1)
  }, [operationSearch, operationModeFilter, operationStatusFilter])

  useEffect(() => {
    if (operationPage > deleteOperationPageCount) {
      setOperationPage(deleteOperationPageCount)
    }
  }, [deleteOperationPageCount, operationPage])

  useEffect(() => {
    if (!selectedDeleteOperation) {
      if (selectedOperationId) {
        setSelectedOperationId('')
      }
      setSelectedOperationDetail(null)
      setSelectedOperationDetailError('')
      return
    }
    if (selectedDeleteOperation.operation_id !== selectedOperationId) {
      setSelectedOperationId(selectedDeleteOperation.operation_id)
    }
  }, [selectedDeleteOperation, selectedOperationId])

  useEffect(() => {
    const operationId = selectedDeleteOperation?.operation_id
    if (!operationId) {
      setSelectedOperationDetail(null)
      setSelectedOperationDetailError('')
      return
    }

    let cancelled = false
    setSelectedOperationDetailLoading(true)
    setSelectedOperationDetailError('')

    void getMemoryDeleteOperation(operationId)
      .then((payload) => {
        if (cancelled) {
          return
        }
        if (!payload.success || !payload.operation) {
          setSelectedOperationDetail(null)
          setSelectedOperationDetailError(payload.error || '未能加载删除操作详情')
          return
        }
        setSelectedOperationDetail(payload.operation)
      })
      .catch((error) => {
        if (cancelled) {
          return
        }
        setSelectedOperationDetail(null)
        setSelectedOperationDetailError(error instanceof Error ? error.message : '未能加载删除操作详情')
      })
      .finally(() => {
        if (!cancelled) {
          setSelectedOperationDetailLoading(false)
        }
      })

    return () => {
      cancelled = true
    }
  }, [selectedDeleteOperation?.operation_id])

  const toggleSourceSelection = useCallback((source: string, checked: boolean) => {
    setSelectedSources((current) => {
      if (checked) {
        return current.includes(source) ? current : [...current, source]
      }
      return current.filter((item) => item !== source)
    })
  }, [])

  const openSourceDeletePreview = useCallback(async () => {
    if (selectedSources.length <= 0) {
      toast({
        title: '请选择来源',
        description: '至少选择一个来源后再进行删除预览',
        variant: 'destructive',
      })
      return
    }
    const request: MemoryDeleteRequestPayload = {
      mode: 'source',
      selector: { sources: selectedSources },
      reason: 'knowledge_base_source_delete',
      requested_by: 'knowledge_base',
    }
    setDeleteDialogTitle('批量删除来源')
    setDeleteDialogDescription('删除来源只会删除该来源下的段落，以及失去全部证据的关系，不会自动删除实体')
    setPendingDeleteRequest(request)
    setDeletePreview(null)
    setDeleteResult(null)
    setDeletePreviewError(null)
    setDeleteDialogOpen(true)
    setDeletePreviewLoading(true)
    try {
      const preview = await previewMemoryDelete(request)
      setDeletePreview(preview)
    } catch (error) {
      setDeletePreviewError(error instanceof Error ? error.message : '删除预览失败')
    } finally {
      setDeletePreviewLoading(false)
    }
  }, [selectedSources, toast])

  const executePendingDelete = useCallback(async () => {
    if (!pendingDeleteRequest) {
      return
    }
    try {
      setDeleteExecuting(true)
      const result = await executeMemoryDelete(pendingDeleteRequest)
      setDeleteResult(result)
      toast({
        title: result.success ? '删除成功' : '删除失败',
        description: result.success ? `操作 ${result.operation_id} 已完成` : result.error || '未能执行删除',
        variant: result.success ? 'default' : 'destructive',
      })
      if (result.success) {
        const [sourcePayload, deleteOperationPayload] = await Promise.all([
          getMemorySources(),
          getMemoryDeleteOperations(DELETE_OPERATION_FETCH_LIMIT),
        ])
        setMemorySources(sourcePayload.items ?? [])
        setDeleteOperations(deleteOperationPayload.items ?? [])
        setSelectedSources([])
      }
    } catch (error) {
      setDeletePreviewError(error instanceof Error ? error.message : '删除失败')
      toast({
        title: '删除失败',
        description: error instanceof Error ? error.message : '未知错误',
        variant: 'destructive',
      })
    } finally {
      setDeleteExecuting(false)
    }
  }, [pendingDeleteRequest, toast])

  const restoreDeleteOperation = useCallback(async (operationId: string) => {
    try {
      setDeleteRestoring(true)
      await restoreMemoryDelete({ operation_id: operationId, requested_by: 'knowledge_base' })
      toast({
        title: '恢复成功',
        description: `删除操作 ${operationId} 已恢复`,
      })
      setDeleteDialogOpen(false)
      const [sourcePayload, deleteOperationPayload] = await Promise.all([
        getMemorySources(),
        getMemoryDeleteOperations(DELETE_OPERATION_FETCH_LIMIT),
      ])
      setMemorySources(sourcePayload.items ?? [])
      setDeleteOperations(deleteOperationPayload.items ?? [])
    } catch (error) {
      toast({
        title: '恢复失败',
        description: error instanceof Error ? error.message : '未知错误',
        variant: 'destructive',
      })
    } finally {
      setDeleteRestoring(false)
    }
  }, [toast])

  const closeDeleteDialog = useCallback((open: boolean) => {
    if (!open) {
      setDeleteDialogOpen(false)
      setDeletePreview(null)
      setDeleteResult(null)
      setDeletePreviewError(null)
      setPendingDeleteRequest(null)
      return
    }
    setDeleteDialogOpen(true)
  }, [])

  const filteredFeedbackCorrections = useMemo(() => {
    const keyword = feedbackSearch.trim().toLowerCase()
    return feedbackCorrections.filter((item) => {
      const taskStatus = String(item.task_status ?? '').trim().toLowerCase()
      const rollbackStatus = String(item.rollback_status ?? '').trim().toLowerCase()
      if (feedbackStatusFilter !== 'all' && taskStatus !== feedbackStatusFilter) {
        return false
      }
      if (feedbackRollbackFilter !== 'all' && rollbackStatus !== feedbackRollbackFilter) {
        return false
      }
      if (!keyword) {
        return true
      }
      return [
        item.query_tool_id,
        item.session_id,
        item.query_text,
        item.decision,
        item.task_status,
        item.rollback_status,
      ]
        .map((value) => String(value ?? '').toLowerCase())
        .some((value) => value.includes(keyword))
    })
  }, [feedbackCorrections, feedbackRollbackFilter, feedbackSearch, feedbackStatusFilter])

  const feedbackPageCount = Math.max(1, Math.ceil(filteredFeedbackCorrections.length / FEEDBACK_CORRECTION_PAGE_SIZE))
  const pagedFeedbackCorrections = useMemo(() => {
    const start = (feedbackPage - 1) * FEEDBACK_CORRECTION_PAGE_SIZE
    return filteredFeedbackCorrections.slice(start, start + FEEDBACK_CORRECTION_PAGE_SIZE)
  }, [feedbackPage, filteredFeedbackCorrections])

  const selectedFeedbackCorrection = useMemo(
    () =>
      filteredFeedbackCorrections.find((item) => item.task_id === selectedFeedbackTaskId)
      ?? pagedFeedbackCorrections[0]
      ?? null,
    [filteredFeedbackCorrections, pagedFeedbackCorrections, selectedFeedbackTaskId],
  )

  useEffect(() => {
    setFeedbackPage(1)
  }, [feedbackSearch, feedbackStatusFilter, feedbackRollbackFilter])

  useEffect(() => {
    if (feedbackPage > feedbackPageCount) {
      setFeedbackPage(feedbackPageCount)
    }
  }, [feedbackPage, feedbackPageCount])

  useEffect(() => {
    if (!selectedFeedbackCorrection) {
      if (selectedFeedbackTaskId) {
        setSelectedFeedbackTaskId(0)
      }
      setSelectedFeedbackTaskDetail(null)
      setSelectedFeedbackTaskError('')
      return
    }
    if (selectedFeedbackCorrection.task_id !== selectedFeedbackTaskId) {
      setSelectedFeedbackTaskId(selectedFeedbackCorrection.task_id)
    }
  }, [selectedFeedbackCorrection, selectedFeedbackTaskId])

  useEffect(() => {
    const taskId = selectedFeedbackCorrection?.task_id
    if (!taskId) {
      setSelectedFeedbackTaskDetail(null)
      setSelectedFeedbackTaskError('')
      return
    }

    let cancelled = false
    setSelectedFeedbackTaskLoading(true)
    setSelectedFeedbackTaskError('')

    void getMemoryFeedbackCorrection(taskId)
      .then((payload) => {
        if (cancelled) {
          return
        }
        if (!payload.success || !payload.task) {
          setSelectedFeedbackTaskDetail(null)
          setSelectedFeedbackTaskError(payload.error || '未能加载纠错任务详情')
          return
        }
        setSelectedFeedbackTaskDetail(payload.task)
      })
      .catch((error) => {
        if (cancelled) {
          return
        }
        setSelectedFeedbackTaskDetail(null)
        setSelectedFeedbackTaskError(error instanceof Error ? error.message : '未能加载纠错任务详情')
      })
      .finally(() => {
        if (!cancelled) {
          setSelectedFeedbackTaskLoading(false)
        }
      })

    return () => {
      cancelled = true
    }
  }, [selectedFeedbackCorrection?.task_id])

  const selectedFeedbackResolved = useMemo<MemoryFeedbackCorrectionDetailTaskPayload | null>(() => {
    if (!selectedFeedbackCorrection) {
      return null
    }
    if (selectedFeedbackTaskDetail?.task_id === selectedFeedbackCorrection.task_id) {
      return {
        ...selectedFeedbackCorrection,
        ...selectedFeedbackTaskDetail,
      } satisfies MemoryFeedbackCorrectionDetailTaskPayload
    }
    return selectedFeedbackTaskDetail ?? selectedFeedbackCorrection
  }, [selectedFeedbackCorrection, selectedFeedbackTaskDetail])
  const selectedFeedbackPreview = useMemo(
    () => getFeedbackCorrectionPreview(selectedFeedbackResolved),
    [selectedFeedbackResolved],
  )
  const selectedFeedbackImpactSummary = useMemo(
    () => buildFeedbackImpactSummary(selectedFeedbackResolved),
    [selectedFeedbackResolved],
  )

  const selectedFeedbackActionLogs: MemoryFeedbackActionLogPayload[] = Array.isArray(selectedFeedbackResolved?.action_logs)
    ? selectedFeedbackResolved.action_logs
    : []
  const filteredFeedbackActionLogs = useMemo(() => {
    const keyword = feedbackActionLogSearch.trim().toLowerCase()
    if (!keyword) {
      return selectedFeedbackActionLogs
    }
    return selectedFeedbackActionLogs.filter((item) =>
      [
        item.action_type,
        item.target_hash,
        item.reason,
        summarizeFeedbackActionPayload(item.before_payload),
        summarizeFeedbackActionPayload(item.after_payload),
      ]
        .map((value) => String(value ?? '').toLowerCase())
        .some((value) => value.includes(keyword)),
    )
  }, [feedbackActionLogSearch, selectedFeedbackActionLogs])
  const feedbackActionLogPageCount = Math.max(
    1,
    Math.ceil(filteredFeedbackActionLogs.length / FEEDBACK_ACTION_LOG_PAGE_SIZE),
  )
  const pagedFeedbackActionLogs = useMemo(() => {
    const start = (feedbackActionLogPage - 1) * FEEDBACK_ACTION_LOG_PAGE_SIZE
    return filteredFeedbackActionLogs.slice(start, start + FEEDBACK_ACTION_LOG_PAGE_SIZE)
  }, [feedbackActionLogPage, filteredFeedbackActionLogs])

  useEffect(() => {
    setFeedbackActionLogPage(1)
  }, [selectedFeedbackTaskId, feedbackActionLogSearch])

  useEffect(() => {
    if (feedbackActionLogPage > feedbackActionLogPageCount) {
      setFeedbackActionLogPage(feedbackActionLogPageCount)
    }
  }, [feedbackActionLogPage, feedbackActionLogPageCount])

  const openFeedbackRollbackDialog = useCallback(() => {
    setFeedbackRollbackReason('')
    setFeedbackRollbackDialogOpen(true)
  }, [])

  const executeFeedbackRollback = useCallback(async () => {
    const taskId = selectedFeedbackResolved?.task_id
    if (!taskId) {
      return
    }
    try {
      setFeedbackRollingBack(true)
      const payload = await rollbackMemoryFeedbackCorrection(taskId, {
        requested_by: 'knowledge_base',
        reason: feedbackRollbackReason.trim(),
      })
      if (!payload.success) {
        throw new Error(payload.error || '回退失败')
      }
      toast({
        title: payload.already_rolled_back ? '该纠错已回退' : '纠错回退成功',
        description: `任务 ${taskId} 的回退结果已写入日志`,
      })
      setFeedbackRollbackDialogOpen(false)
      const [listPayload, detailPayload] = await Promise.all([
        getMemoryFeedbackCorrections({ limit: FEEDBACK_CORRECTION_FETCH_LIMIT }),
        getMemoryFeedbackCorrection(taskId),
      ])
      setFeedbackCorrections(listPayload.items ?? [])
      setSelectedFeedbackTaskDetail(detailPayload.task ?? null)
      const [sourcePayload, runtimePayload] = await Promise.all([
        getMemorySources(),
        getMemoryRuntimeConfig(),
      ])
      setMemorySources(sourcePayload.items ?? [])
      setRuntimeConfig(runtimePayload)
    } catch (error) {
      toast({
        title: '纠错回退失败',
        description: error instanceof Error ? error.message : '未知错误',
        variant: 'destructive',
      })
    } finally {
      setFeedbackRollingBack(false)
    }
  }, [feedbackRollbackReason, selectedFeedbackResolved?.task_id, toast])

  const selectedOperationResolved = useMemo(() => {
    if (!selectedDeleteOperation) {
      return null
    }
    if (selectedOperationDetail?.operation_id === selectedDeleteOperation.operation_id) {
      return {
        ...selectedDeleteOperation,
        ...selectedOperationDetail,
      } satisfies MemoryDeleteOperationPayload
    }
    return selectedDeleteOperation
  }, [selectedDeleteOperation, selectedOperationDetail])
  const selectedOperationSummaryResolved = ((selectedOperationResolved?.summary ?? {}) as Record<string, unknown>)
  const selectedOperationCounts = ((selectedOperationSummaryResolved.counts as Record<string, number> | undefined) ?? {})
  const selectedOperationSources = Array.isArray(selectedOperationSummaryResolved.sources)
    ? selectedOperationSummaryResolved.sources.map((item) => String(item)).filter(Boolean)
    : []
  const selectedOperationItems = Array.isArray(selectedOperationResolved?.items)
    ? selectedOperationResolved.items
    : []
  const filteredSelectedOperationItems = useMemo(() => {
    const keyword = selectedOperationItemSearch.trim().toLowerCase()
    if (!keyword) {
      return selectedOperationItems
    }
    return selectedOperationItems.filter((item) => {
      const payload = item.payload ?? {}
      const source = String(payload.source ?? '').trim()
      return [
        item.item_type,
        item.item_hash,
        item.item_key,
        source,
      ]
        .map((value) => String(value ?? '').toLowerCase())
        .some((value) => value.includes(keyword))
    })
  }, [selectedOperationItemSearch, selectedOperationItems])
  const selectedOperationItemPageCount = Math.max(
    1,
    Math.ceil(filteredSelectedOperationItems.length / DELETE_OPERATION_ITEM_PAGE_SIZE),
  )
  const pagedSelectedOperationItems = useMemo(() => {
    const start = (selectedOperationItemPage - 1) * DELETE_OPERATION_ITEM_PAGE_SIZE
    return filteredSelectedOperationItems.slice(start, start + DELETE_OPERATION_ITEM_PAGE_SIZE)
  }, [filteredSelectedOperationItems, selectedOperationItemPage])

  useEffect(() => {
    setSelectedOperationItemPage(1)
  }, [selectedOperationId, selectedOperationItemSearch])

  useEffect(() => {
    if (selectedOperationItemPage > selectedOperationItemPageCount) {
      setSelectedOperationItemPage(selectedOperationItemPageCount)
    }
  }, [selectedOperationItemPage, selectedOperationItemPageCount])

  const saveVisualConfig = useCallback(async () => {
    try {
      setSaving(true)
      await updateMemoryConfig(visualConfig)
      const [nextConfig, nextRaw, nextRuntime] = await Promise.all([
        getMemoryConfig(),
        getMemoryConfigRaw(),
        getMemoryRuntimeConfig(),
      ])
      setVisualConfig(nextConfig.config)
      setRawConfig(nextRaw.config)
      setRawConfigExists(nextRaw.exists ?? true)
      setRawConfigUsingDefault(nextRaw.using_default ?? false)
      setRuntimeConfig(nextRuntime)
      toast({ title: '配置已保存', description: '长期记忆配置已经应用到运行时' })
    } catch (error) {
      toast({
        title: '保存配置失败',
        description: error instanceof Error ? error.message : '未知错误',
        variant: 'destructive',
      })
    } finally {
      setSaving(false)
    }
  }, [toast, visualConfig])

  const saveRaw = useCallback(async () => {
    try {
      setSaving(true)
      await updateMemoryConfigRaw(rawConfig)
      const [nextConfig, nextRaw, nextRuntime] = await Promise.all([
        getMemoryConfig(),
        getMemoryConfigRaw(),
        getMemoryRuntimeConfig(),
      ])
      setVisualConfig(nextConfig.config)
      setRawConfig(nextRaw.config ?? '')
      setRawConfigExists(nextRaw.exists ?? true)
      setRawConfigUsingDefault(nextRaw.using_default ?? false)
      setRuntimeConfig(nextRuntime)
      toast({ title: '原始 TOML 已保存', description: '长期记忆配置已经重新加载' })
    } catch (error) {
      toast({
        title: '保存原始配置失败',
        description: error instanceof Error ? error.message : '未知错误',
        variant: 'destructive',
      })
    } finally {
      setSaving(false)
    }
  }, [rawConfig, toast])

  const refreshSelfCheck = useCallback(async () => {
    try {
      setRefreshingCheck(true)
      const payload = await refreshMemoryRuntimeSelfCheck()
      setSelfCheckReport((payload.report ?? null) as Record<string, unknown> | null)
      const nextRuntime = await getMemoryRuntimeConfig()
      setRuntimeConfig(nextRuntime)
      toast({
        title: payload.success ? '自检通过' : '自检未通过',
        description: payload.success ? '运行时状态正常' : '请检查 embedding 配置和外部服务连通性',
        variant: payload.success ? 'default' : 'destructive',
      })
    } catch (error) {
      toast({
        title: '运行时自检失败',
        description: error instanceof Error ? error.message : '未知错误',
        variant: 'destructive',
      })
    } finally {
      setRefreshingCheck(false)
    }
  }, [toast])

  const submitImportByMode = useCallback(async () => {
    if (creatingImport) {
      return
    }
    switch (importCreateMode) {
      case 'upload':
        await submitUploadImport()
        break
      case 'paste':
        await submitPasteImport()
        break
      case 'raw_scan':
        await submitRawScanImport()
        break
      case 'lpmm_openie':
        await submitOpenieImport()
        break
      case 'lpmm_convert':
        await submitConvertImport()
        break
      case 'temporal_backfill':
        await submitBackfillImport()
        break
      case 'maibot_migration':
        await submitMaibotMigrationImport()
        break
      default:
        break
    }
  }, [
    creatingImport,
    importCreateMode,
    submitBackfillImport,
    submitConvertImport,
    submitMaibotMigrationImport,
    submitOpenieImport,
    submitPasteImport,
    submitRawScanImport,
    submitUploadImport,
  ])

  const submitTuningTask = useCallback(async () => {
    try {
      setCreatingTuning(true)
      await createMemoryTuningTask({
        objective: tuningObjective,
        intensity: tuningIntensity,
        sample_size: Number(tuningSampleSize),
        top_k_eval: Number(tuningTopKEval),
      })
      const tasks = await getMemoryTuningTasks(20)
      setTuningTasks(tasks.items ?? [])
      toast({ title: '调优任务已创建', description: '新的检索调优任务已经进入队列' })
    } catch (error) {
      toast({
        title: '创建调优任务失败',
        description: error instanceof Error ? error.message : '未知错误',
        variant: 'destructive',
      })
    } finally {
      setCreatingTuning(false)
    }
  }, [toast, tuningIntensity, tuningObjective, tuningSampleSize, tuningTopKEval])

  const applyBestTask = useCallback(async (taskId: string) => {
    try {
      await applyBestMemoryTuningProfile(taskId)
      const [profilePayload, runtimePayload, tuningTaskPayload] = await Promise.all([
        getMemoryTuningProfile(),
        getMemoryRuntimeConfig(),
        getMemoryTuningTasks(20),
      ])
      setTuningProfile(profilePayload.profile ?? {})
      setTuningProfileToml(profilePayload.toml ?? '')
      setRuntimeConfig(runtimePayload)
      setTuningTasks(tuningTaskPayload.items ?? [])
      toast({ title: '最佳参数已应用', description: `任务 ${taskId} 的最佳轮次已经写入运行时` })
    } catch (error) {
      toast({
        title: '应用最佳参数失败',
        description: error instanceof Error ? error.message : '未知错误',
        variant: 'destructive',
      })
    }
  }, [toast])

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="rounded-xl border bg-background px-6 py-5 text-sm text-muted-foreground shadow-sm">
          正在加载长期记忆控制台...
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex-none border-b bg-card/60 px-6 py-4 backdrop-blur">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <h1 className="text-2xl font-bold">长期记忆控制台</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              A_Memorix 的配置、自检、导入和检索调优，都在这里！
            </p>
          </div>

          <div className="flex flex-wrap gap-2">
            <Button variant="outline" onClick={() => navigate({ to: '/resource/knowledge-graph' })}>
              <Database className="mr-2 h-4 w-4" />
              打开图谱
            </Button>
            <Button variant="outline" onClick={() => void loadPage()}>
              <RefreshCw className="mr-2 h-4 w-4" />
              刷新数据
            </Button>
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-auto p-6">
        <div className="mx-auto flex w-full max-w-[1500px] flex-col gap-6">
          <div className="grid gap-4 xl:grid-cols-4">
            {runtimeBadges.map((item) => (
              <Card key={item.label} className={cn('overflow-hidden transition-colors', item.className)}>
                <CardHeader className="space-y-3 pb-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="space-y-1">
                      <CardDescription>{item.label}</CardDescription>
                      <CardTitle className="break-all text-base leading-relaxed">{item.value}</CardTitle>
                    </div>
                    <div className="rounded-lg border bg-background/70 p-2 shadow-sm">
                      <item.icon className={cn('h-4 w-4', item.iconClassName)} />
                    </div>
                  </div>
                  <div className="text-xs text-muted-foreground">{item.description}</div>
                </CardHeader>
              </Card>
            ))}
          </div>

          <Tabs defaultValue="overview" className="space-y-5">
            <TabsList className="h-auto flex-wrap justify-start gap-1 rounded-xl border bg-muted/30 p-1">
              <TabsTrigger value="overview" className="rounded-lg px-4 py-1.5">
                概览
              </TabsTrigger>
              <TabsTrigger value="config" className="rounded-lg px-4 py-1.5">
                配置
              </TabsTrigger>
              <TabsTrigger value="import" className="rounded-lg px-4 py-1.5">
                导入
              </TabsTrigger>
              <TabsTrigger value="tuning" className="rounded-lg px-4 py-1.5">
                调优
              </TabsTrigger>
              <TabsTrigger value="delete" className="rounded-lg px-4 py-1.5">
                删除
              </TabsTrigger>
              <TabsTrigger value="feedback" className="rounded-lg px-4 py-1.5">
                纠错历史
              </TabsTrigger>
            </TabsList>

            <TabsContent value="overview" className="space-y-4">
              <div className="grid gap-4 xl:grid-cols-[1.15fr_0.85fr]">
                <Card>
                  <CardHeader className="flex flex-row items-start justify-between space-y-0">
                    <div>
                      <CardTitle className="flex items-center gap-2">
                        <Gauge className="h-4 w-4" />
                        运行时自检
                      </CardTitle>
                      <CardDescription>用于确认 embedding、向量库与运行时状态是否一致</CardDescription>
                    </div>
                    <Button size="sm" onClick={() => void refreshSelfCheck()} disabled={refreshingCheck}>
                      <RefreshCw className={`mr-2 h-4 w-4 ${refreshingCheck ? 'animate-spin' : ''}`} />
                      重新自检
                    </Button>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    <Alert>
                      <AlertDescription>
                        当前配置文件路径：<code>{configPath}</code>
                      </AlertDescription>
                    </Alert>
                    <CodeEditor
                      value={JSON.stringify(selfCheckReport ?? runtimeConfig ?? {}, null, 2)}
                      language="json"
                      readOnly
                      height="320px"
                    />
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <Sparkles className="h-4 w-4" />
                      当前运行态摘要
                    </CardTitle>
                    <CardDescription>这里展示运行态重点指标，方便先判断是否需要导入或调优</CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-4 text-sm">
                    <div className="flex flex-wrap gap-2">
                      <Badge variant={runtimeConfig?.runtime_ready ? 'default' : 'destructive'}>
                        {runtimeConfig?.runtime_ready ? '运行就绪' : '运行未就绪'}
                      </Badge>
                      <Badge variant={runtimeConfig?.embedding_degraded ? 'destructive' : 'secondary'}>
                        {runtimeConfig?.embedding_degraded ? 'Embedding 已退化' : 'Embedding 正常'}
                      </Badge>
                    </div>
                    <div className="grid gap-3 md:grid-cols-2">
                      <div className="rounded-lg border bg-muted/30 p-3">
                        <div className="text-xs text-muted-foreground">待补回段落向量</div>
                        <div className="mt-1 text-2xl font-semibold">{runtimeConfig?.paragraph_vector_backfill_pending ?? 0}</div>
                      </div>
                      <div className="rounded-lg border bg-muted/30 p-3">
                        <div className="text-xs text-muted-foreground">失败补回任务</div>
                        <div className="mt-1 text-2xl font-semibold">{runtimeConfig?.paragraph_vector_backfill_failed ?? 0}</div>
                      </div>
                    </div>
                    <div className="rounded-lg border bg-muted/30 p-3">
                      <div className="text-xs text-muted-foreground">当前调优配置</div>
                      <pre className="mt-2 max-h-56 overflow-auto whitespace-pre-wrap break-words text-xs">
                        {JSON.stringify(tuningProfile, null, 2)}
                      </pre>
                    </div>
                  </CardContent>
                </Card>
              </div>
            </TabsContent>

            <TabsContent value="config" className="space-y-4">
              <Card>
                <CardHeader className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                  <div>
                    <CardTitle className="flex items-center gap-2">
                      <SlidersHorizontal className="h-4 w-4" />
                      长期记忆配置
                    </CardTitle>
                    <CardDescription>
                      常用字段可在这里可视化编辑；高级配置仍可通过原始 TOML 维护。
                    </CardDescription>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Button variant={rawMode ? 'outline' : 'default'} onClick={() => setRawMode(false)}>
                      可视化配置
                    </Button>
                    <Button variant={rawMode ? 'default' : 'outline'} onClick={() => setRawMode(true)}>
                      原始 TOML
                    </Button>
                    <Button onClick={() => void (rawMode ? saveRaw() : saveVisualConfig())} disabled={saving}>
                      <Save className="mr-2 h-4 w-4" />
                      保存
                    </Button>
                  </div>
                </CardHeader>
                <CardContent className="space-y-4">
                  <Alert>
                    <AlertDescription>
                      当前配置文件：<code>{configPath}</code>
                      {schema?._note ? `；${schema._note}` : ''}
                    </AlertDescription>
                  </Alert>
                  {!rawConfigExists || rawConfigUsingDefault ? (
                    <Alert>
                      <AlertDescription>
                        检测到配置文件尚未保存。当前展示的是默认模板内容，点击“保存”后会自动创建配置文件：
                        {' '}
                        <code>{configPath}</code>
                        
                      </AlertDescription>
                    </Alert>
                  ) : null}

                  {rawMode ? (
                    <CodeEditor
                      value={rawConfig}
                      onChange={setRawConfig}
                      language="toml"
                      height="620px"
                    />
                  ) : schema ? (
                    <MemoryConfigEditor
                      schema={schema}
                      config={visualConfig}
                      onChange={setVisualConfig}
                      disabled={saving}
                    />
                  ) : (
                    <div className="rounded-lg border bg-muted/30 p-4 text-sm text-muted-foreground">
                      当前未能加载配置 schema，请先刷新页面或检查后端日志
                    </div>
                  )}
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent
              value="import"
              className="space-y-7 [&_input]:h-10 [&_[role=combobox]]:h-10 [&_textarea]:min-h-[96px]"
            >
              <div className="mx-auto w-full max-w-5xl space-y-6">
                <div className="space-y-6">
                  <Card className="rounded-2xl border-border/70 shadow-sm">
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2">
                        <Upload className="h-4 w-4" />
                        创建导入任务
                      </CardTitle>
                      <CardDescription>按“选择导入方式 → 检查公共参数 → 创建任务”的顺序完成导入。</CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-6">
                      <Tabs
                        value={importCreateMode}
                        onValueChange={(value) => setImportCreateMode(value as MemoryImportTaskKind)}
                        className="space-y-4"
                      >
                        <div className="space-y-2">
                          <Label>选择导入方式</Label>
                          <TabsList className="h-auto w-full flex-wrap justify-start gap-1 rounded-xl border bg-muted/20 p-1">
                            {IMPORT_KIND_OPTIONS.map((item) => (
                              <TabsTrigger
                                key={item.value}
                                value={item.value}
                                className="rounded-lg px-3 py-1.5 text-xs"
                              >
                                {item.label}
                              </TabsTrigger>
                            ))}
                          </TabsList>
                        </div>

                        <div className="space-y-4 rounded-lg border bg-muted/30 p-4">
                        <div className="space-y-1">
                          <div className="text-sm font-medium">公共参数</div>
                          <div className="text-xs text-muted-foreground">这些设置会应用到当前导入任务。一般保持默认即可，只在批量导入或排查问题时调整。</div>
                        </div>
                        <div className="grid gap-3 md:grid-cols-2">
                          <div className="space-y-1">
                            <Label>文件并发数</Label>
                            <div className="text-xs text-muted-foreground">同时处理多少个文件；文件很多时再适当调高。</div>
                            <Input
                              type="number"
                              min={1}
                              max={Number(importSettings.max_file_concurrency ?? 128)}
                              value={importCommonFileConcurrency}
                              onChange={(event) => setImportCommonFileConcurrency(event.target.value)}
                            />
                          </div>
                          <div className="space-y-1">
                            <Label>分块并发数</Label>
                            <div className="text-xs text-muted-foreground">单个文件内并行处理多少个分块；过高会增加资源占用。</div>
                            <Input
                              type="number"
                              min={1}
                              max={Number(importSettings.max_chunk_concurrency ?? 256)}
                              value={importCommonChunkConcurrency}
                              onChange={(event) => setImportCommonChunkConcurrency(event.target.value)}
                            />
                          </div>
                          <div className="rounded-md border bg-background/70 p-3">
                            <div className="flex items-center gap-2 text-sm">
                              <Checkbox
                                checked={importCommonLlmEnabled}
                                onCheckedChange={(value) => setImportCommonLlmEnabled(Boolean(value))}
                              />
                              启用 LLM 抽取
                            </div>
                            <div className="mt-1 text-xs text-muted-foreground">需要模型参与抽取，质量更高但耗时更长。</div>
                          </div>
                          <div className="rounded-md border bg-background/70 p-3">
                            <div className="flex items-center gap-2 text-sm">
                              <Checkbox
                                checked={importCommonChatLog}
                                onCheckedChange={(value) => setImportCommonChatLog(Boolean(value))}
                              />
                              按聊天日志解析
                            </div>
                            <div className="mt-1 text-xs text-muted-foreground">适合导入聊天记录，会尽量保留时间和对话上下文。</div>
                          </div>
                        </div>

                        <details className="rounded-md border bg-background/70 p-3 text-sm">
                          <summary className="cursor-pointer text-xs font-medium text-muted-foreground">
                            高级参数（通常不用修改）
                          </summary>
                          <div className="mt-3 grid gap-3">
                            <div className="space-y-1">
                              <Label>指定抽取策略</Label>
                              <Input
                                value={importCommonStrategyOverride}
                                onChange={(event) => setImportCommonStrategyOverride(event.target.value)}
                              />
                            </div>
                            <div className="space-y-1">
                              <Label>去重策略</Label>
                              <Input
                                value={importCommonDedupePolicy}
                                onChange={(event) => setImportCommonDedupePolicy(event.target.value)}
                              />
                            </div>
                            <div className="space-y-1">
                              <Label>聊天参考时间</Label>
                              <Input
                                value={importCommonChatReferenceTime}
                                onChange={(event) => setImportCommonChatReferenceTime(event.target.value)}
                              />
                            </div>
                            <div className="flex items-center gap-2 text-sm">
                              <Checkbox
                                checked={importCommonForce}
                                onCheckedChange={(value) => setImportCommonForce(Boolean(value))}
                              />
                              强制导入
                            </div>
                            <div className="flex items-center gap-2 text-sm">
                              <Checkbox
                                checked={importCommonClearManifest}
                                onCheckedChange={(value) => setImportCommonClearManifest(Boolean(value))}
                              />
                              清空导入清单
                            </div>
                          </div>
                        </details>
                      </div>

                      <TabsContent value="upload" className="mt-0">
                        <div className="space-y-3 rounded-xl border bg-background/70 p-4">
                          <div className="text-xs text-muted-foreground">选择一个或多个本地文件创建导入任务，适合批量导入资料或聊天记录。</div>
                          <div className="grid gap-3">
                            <div className="space-y-1">
                              <Label>输入模式</Label>
                              <Select
                                value={uploadInputMode}
                                onValueChange={(value) => setUploadInputMode(normalizeImportInputMode(value))}
                              >
                                <SelectTrigger aria-label="upload-input-mode">
                                  <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                  <SelectItem value="text">文本</SelectItem>
                                  <SelectItem value="json">结构化 JSON</SelectItem>
                                </SelectContent>
                              </Select>
                            </div>
                            <div className="space-y-1">
                              <Label>文件选择</Label>
                              <Input
                                type="file"
                                multiple
                                accept=".txt,.md,.json,.jsonl,.csv,.log,.html,.htm,.xml"
                                onChange={(event) => setUploadFiles(Array.from(event.target.files ?? []))}
                              />
                            </div>
                          </div>
                          <div className="text-xs text-muted-foreground">已选择 {uploadFiles.length} 个文件</div>
                        </div>
                      </TabsContent>

                      <TabsContent value="paste" className="mt-0">
                        <div className="space-y-3 rounded-xl border bg-background/70 p-4">
                          <div className="text-xs text-muted-foreground">直接粘贴少量文本或 JSON，适合临时补充一段资料。</div>
                          <div className="grid gap-3">
                            <div className="space-y-1">
                              <Label>内容名称</Label>
                              <Input value={pasteName} onChange={(event) => setPasteName(event.target.value)} />
                            </div>
                            <div className="space-y-1">
                              <Label>输入模式</Label>
                              <Select
                                value={pasteMode}
                                onValueChange={(value) => setPasteMode(normalizeImportInputMode(value))}
                              >
                                <SelectTrigger aria-label="paste-input-mode">
                                  <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                  <SelectItem value="text">文本</SelectItem>
                                  <SelectItem value="json">结构化 JSON</SelectItem>
                                </SelectContent>
                              </Select>
                            </div>
                            <div className="space-y-1">
                              <Label>粘贴内容</Label>
                              <Textarea
                                value={pasteContent}
                                onChange={(event) => setPasteContent(event.target.value)}
                                rows={8}
                              />
                            </div>
                          </div>
                        </div>
                      </TabsContent>

                      <TabsContent value="raw_scan" className="mt-0">
                        <div className="space-y-3 rounded-xl border bg-background/70 p-4">
                          <div className="text-xs text-muted-foreground">扫描目录文件，适合本地批处理</div>
                          <div className="grid gap-3">
                            <div className="space-y-1">
                              <Label>路径别名</Label>
                              <Input value={rawAlias} onChange={(event) => setRawAlias(event.target.value)} />
                            </div>
                            <div className="space-y-1">
                              <Label>输入模式</Label>
                              <Select
                                value={rawInputMode}
                                onValueChange={(value) => setRawInputMode(normalizeImportInputMode(value))}
                              >
                                <SelectTrigger aria-label="raw-input-mode">
                                  <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                  <SelectItem value="text">文本</SelectItem>
                                  <SelectItem value="json">结构化 JSON</SelectItem>
                                </SelectContent>
                              </Select>
                            </div>
                            <div className="space-y-1">
                              <Label>相对路径</Label>
                              <Input value={rawRelativePath} onChange={(event) => setRawRelativePath(event.target.value)} />
                            </div>
                            <div className="space-y-1">
                              <Label>匹配规则（Glob）</Label>
                              <Input value={rawGlob} onChange={(event) => setRawGlob(event.target.value)} />
                            </div>
                          </div>
                          <div className="flex items-center gap-2 text-sm">
                            <Checkbox checked={rawRecursive} onCheckedChange={(value) => setRawRecursive(Boolean(value))} />
                            递归扫描
                          </div>
                        </div>
                      </TabsContent>

                      <TabsContent value="lpmm_openie" className="mt-0">
                        <div className="space-y-3 rounded-xl border bg-background/70 p-4">
                          <div className="text-xs text-muted-foreground">读取 LPMM 内容并抽取关系</div>
                          <div className="grid gap-3">
                            <div className="space-y-1">
                              <Label>路径别名</Label>
                              <Input value={openieAlias} onChange={(event) => setOpenieAlias(event.target.value)} />
                            </div>
                            <div className="space-y-1">
                              <Label>相对路径</Label>
                              <Input value={openieRelativePath} onChange={(event) => setOpenieRelativePath(event.target.value)} />
                            </div>
                          </div>
                          <div className="flex items-center gap-2 text-sm">
                            <Checkbox
                              checked={openieIncludeAllJson}
                              onCheckedChange={(value) => setOpenieIncludeAllJson(Boolean(value))}
                            />
                            包含全部 JSON 文件
                          </div>
                        </div>
                      </TabsContent>

                      <TabsContent value="lpmm_convert" className="mt-0">
                        <div className="space-y-3 rounded-xl border bg-background/70 p-4">
                          <div className="text-xs text-muted-foreground">将 LPMM 数据转换到目标目录</div>
                          <div className="grid gap-3">
                            <div className="space-y-1">
                              <Label>源路径别名</Label>
                              <Input value={convertAlias} onChange={(event) => setConvertAlias(event.target.value)} />
                            </div>
                            <div className="space-y-1">
                              <Label>目标路径别名</Label>
                              <Input value={convertTargetAlias} onChange={(event) => setConvertTargetAlias(event.target.value)} />
                            </div>
                            <div className="space-y-1">
                              <Label>源相对路径</Label>
                              <Input value={convertRelativePath} onChange={(event) => setConvertRelativePath(event.target.value)} />
                            </div>
                            <div className="space-y-1">
                              <Label>目标相对路径</Label>
                              <Input
                                value={convertTargetRelativePath}
                                onChange={(event) => setConvertTargetRelativePath(event.target.value)}
                              />
                            </div>
                            <div className="space-y-1">
                              <Label>向量维度</Label>
                              <Input
                                type="number"
                                min={1}
                                value={convertDimension}
                                onChange={(event) => setConvertDimension(event.target.value)}
                              />
                            </div>
                            <div className="space-y-1">
                              <Label>批处理大小</Label>
                              <Input
                                type="number"
                                min={1}
                                value={convertBatchSize}
                                onChange={(event) => setConvertBatchSize(event.target.value)}
                              />
                            </div>
                          </div>
                        </div>
                      </TabsContent>

                      <TabsContent value="temporal_backfill" className="mt-0">
                        <div className="space-y-3 rounded-xl border bg-background/70 p-4">
                          <div className="text-xs text-muted-foreground">为已有数据补齐时间字段</div>
                          <div className="grid gap-3">
                            <div className="space-y-1">
                              <Label>路径别名</Label>
                              <Input value={backfillAlias} onChange={(event) => setBackfillAlias(event.target.value)} />
                            </div>
                            <div className="space-y-1">
                              <Label>处理上限</Label>
                              <Input type="number" min={1} value={backfillLimit} onChange={(event) => setBackfillLimit(event.target.value)} />
                            </div>
                            <div className="space-y-1">
                              <Label>相对路径</Label>
                              <Input value={backfillRelativePath} onChange={(event) => setBackfillRelativePath(event.target.value)} />
                            </div>
                          </div>
                          <div className="grid gap-2">
                            <div className="flex items-center gap-2 text-sm">
                              <Checkbox checked={backfillDryRun} onCheckedChange={(value) => setBackfillDryRun(Boolean(value))} />
                              只预演，不写入数据
                            </div>
                            <div className="flex items-center gap-2 text-sm">
                              <Checkbox
                                checked={backfillNoCreatedFallback}
                                onCheckedChange={(value) => setBackfillNoCreatedFallback(Boolean(value))}
                              />
                              禁用创建时间回退
                            </div>
                          </div>
                        </div>
                      </TabsContent>

                      <TabsContent value="maibot_migration" className="mt-0">
                        <div className="space-y-3 rounded-xl border bg-background/70 p-4">
                          <div className="text-xs text-muted-foreground">迁移 MaiBot 历史长期记忆</div>
                          <div className="grid gap-3">
                            <div className="space-y-1">
                              <Label>源数据库路径</Label>
                              <Input value={maibotSourceDb} onChange={(event) => setMaibotSourceDb(event.target.value)} />
                            </div>
                            <div className="space-y-1">
                              <Label>起始时间</Label>
                              <Input value={maibotTimeFrom} onChange={(event) => setMaibotTimeFrom(event.target.value)} />
                            </div>
                            <div className="space-y-1">
                              <Label>结束时间</Label>
                              <Input value={maibotTimeTo} onChange={(event) => setMaibotTimeTo(event.target.value)} />
                            </div>
                            <div className="space-y-1">
                              <Label>起始 ID</Label>
                              <Input type="number" min={1} value={maibotStartId} onChange={(event) => setMaibotStartId(event.target.value)} />
                            </div>
                            <div className="space-y-1">
                              <Label>结束 ID</Label>
                              <Input type="number" min={1} value={maibotEndId} onChange={(event) => setMaibotEndId(event.target.value)} />
                            </div>
                            <div className="space-y-1">
                              <Label>会话 ID 列表</Label>
                              <Input value={maibotStreamIds} onChange={(event) => setMaibotStreamIds(event.target.value)} />
                            </div>
                            <div className="space-y-1">
                              <Label>群组 ID 列表</Label>
                              <Input value={maibotGroupIds} onChange={(event) => setMaibotGroupIds(event.target.value)} />
                            </div>
                            <div className="space-y-1">
                              <Label>用户 ID 列表</Label>
                              <Input value={maibotUserIds} onChange={(event) => setMaibotUserIds(event.target.value)} />
                            </div>
                            <div className="space-y-1">
                              <Label>读取批大小</Label>
                              <Input
                                type="number"
                                min={1}
                                value={maibotReadBatchSize}
                                onChange={(event) => setMaibotReadBatchSize(event.target.value)}
                              />
                            </div>
                            <div className="space-y-1">
                              <Label>提交窗口行数</Label>
                              <Input
                                type="number"
                                min={1}
                                value={maibotCommitWindowRows}
                                onChange={(event) => setMaibotCommitWindowRows(event.target.value)}
                              />
                            </div>
                            <div className="space-y-1">
                              <Label>向量线程数</Label>
                              <Input
                                type="number"
                                min={1}
                                value={maibotEmbedWorkers}
                                onChange={(event) => setMaibotEmbedWorkers(event.target.value)}
                              />
                            </div>
                          </div>
                          <div className="grid gap-2">
                            <div className="flex items-center gap-2 text-sm">
                              <Checkbox checked={maibotNoResume} onCheckedChange={(value) => setMaibotNoResume(Boolean(value))} />
                              从头开始，不继续上次进度
                            </div>
                            <div className="flex items-center gap-2 text-sm">
                              <Checkbox checked={maibotResetState} onCheckedChange={(value) => setMaibotResetState(Boolean(value))} />
                              重置迁移状态
                            </div>
                            <div className="flex items-center gap-2 text-sm">
                              <Checkbox checked={maibotDryRun} onCheckedChange={(value) => setMaibotDryRun(Boolean(value))} />
                              只预演，不写入数据
                            </div>
                            <div className="flex items-center gap-2 text-sm">
                              <Checkbox checked={maibotVerifyOnly} onCheckedChange={(value) => setMaibotVerifyOnly(Boolean(value))} />
                              仅校验
                            </div>
                          </div>
                        </div>
                      </TabsContent>

                      </Tabs>

                      <Button onClick={() => void submitImportByMode()} disabled={creatingImport}>
                        {creatingImport ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Upload className="mr-2 h-4 w-4" />}
                        创建导入任务
                      </Button>
                    </CardContent>
                  </Card>

                  <Card className="rounded-2xl border-border/70 bg-card/85 shadow-sm">
                    <CardHeader>
                      <CardTitle>路径预检</CardTitle>
                      <CardDescription>在创建本地扫描、转换或迁移任务前，先确认路径会被解析到哪里。</CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      <div className="grid gap-3">
                        <div className="space-y-1">
                          <Label>路径别名</Label>
                          <div className="text-xs text-muted-foreground">选择后端允许访问的数据根目录。</div>
                          <Select value={pathResolveAlias} onValueChange={setPathResolveAlias}>
                            <SelectTrigger aria-label="import-path-alias">
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              {importAliasKeys.length > 0 ? importAliasKeys.map((alias) => (
                                <SelectItem key={alias} value={alias}>{alias}</SelectItem>
                              )) : (
                                <SelectItem value="raw">raw</SelectItem>
                              )}
                            </SelectContent>
                          </Select>
                        </div>
                        <div className="space-y-1">
                          <Label>相对路径</Label>
                          <div className="text-xs text-muted-foreground">填写相对于路径别名的子路径，不需要填写完整磁盘路径。</div>
                          <Input
                            value={pathResolveRelativePath}
                            onChange={(event) => setPathResolveRelativePath(event.target.value)}
                            placeholder="例如 exports/weekly"
                          />
                        </div>
                      </div>
                      <div className="flex items-center gap-2 text-sm">
                        <Checkbox checked={pathResolveMustExist} onCheckedChange={(value) => setPathResolveMustExist(Boolean(value))} />
                        要求路径已存在
                      </div>
                      <Button
                        variant="outline"
                        onClick={() => void resolveImportPath()}
                        disabled={resolvingPath || !pathResolveAlias.trim()}
                      >
                        {resolvingPath ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-2 h-4 w-4" />}
                        解析路径
                      </Button>
                      <Textarea value={pathResolveOutput} readOnly rows={6} placeholder="解析结果会显示在这里" />
                    </CardContent>
                  </Card>
                </div>

                <div className="space-y-6">
                  <Card className="rounded-2xl border-border/70 bg-card/90 shadow-sm">
                    <CardHeader className="space-y-4 pb-4">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <CardTitle>导入队列</CardTitle>
                        <Button variant="outline" size="sm" onClick={() => void refreshImportQueue()}>
                          <RefreshCw className="mr-2 h-4 w-4" />
                          刷新
                        </Button>
                      </div>
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <CardDescription className="text-sm">
                          查看任务是否正在运行、排队等待或已经结束。点击任务卡片可查看详情。
                        </CardDescription>
                        <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
                          <Badge variant="outline" className="bg-background/70">运行中 {runningImportTasks.length}</Badge>
                          <Badge variant="outline" className="bg-background/70">排队中 {queuedImportTasks.length}</Badge>
                          <Badge variant="outline" className="bg-background/70">最近完成 {recentImportTasks.length}</Badge>
                        </div>
                        <label className="flex items-center gap-2 text-xs text-muted-foreground">
                          <Checkbox checked={importAutoPolling} onCheckedChange={(value) => setImportAutoPolling(Boolean(value))} />
                          自动轮询 {importPollInterval}ms
                        </label>
                      </div>
                    </CardHeader>
                    <CardContent className="space-y-6">
                      {importErrorText ? (
                        <Alert variant="destructive">
                          <AlertDescription>{importErrorText}</AlertDescription>
                        </Alert>
                      ) : null}

                      <div className="space-y-2.5">
                        <div className="flex items-center justify-between gap-2">
                          <div className="text-sm font-medium">运行中</div>
                          <Badge variant="outline">{runningImportTasks.length}</Badge>
                        </div>
                        {runningImportTasks.length > 0 ? (
                          <ScrollArea className="h-[208px] rounded-xl border bg-muted/10">
                            <div className="space-y-2.5 p-2.5">
                              {runningImportTasks.map((task) => {
                                const isSelected = task.task_id === selectedImportTaskId
                                return (
                                  <button
                                    key={task.task_id}
                                    type="button"
                                    onClick={() => void selectImportTask(task.task_id)}
                                    className={cn(
                                      'w-full rounded-xl border p-4 text-left transition-all',
                                      isSelected
                                        ? 'border-primary/70 bg-primary/5 shadow-sm'
                                        : 'bg-background/80 hover:border-muted-foreground/40 hover:bg-muted/20',
                                    )}
                                  >
                                    <div className="flex flex-wrap items-start justify-between gap-2">
                                      <div className="min-w-0 space-y-1">
                                        <div className="break-all font-mono text-[11px] leading-relaxed text-muted-foreground">
                                          {task.task_id}
                                        </div>
                                        <div className="text-sm font-medium">{String(task.task_kind ?? task.mode ?? '-')}</div>
                                      </div>
                                      <Badge variant={getImportStatusVariant(String(task.status ?? ''))}>
                                        {getImportStatusLabel(String(task.status ?? ''))}
                                      </Badge>
                                    </div>
                                    <div className="mt-2 flex items-center justify-between gap-2 text-xs text-muted-foreground">
                                      <span>{getImportStepLabel(String(task.current_step ?? 'running'))}</span>
                                      <span>{Number(task.progress ?? 0).toFixed(1)}%</span>
                                    </div>
                                    <Progress value={normalizeProgress(task.progress)} className="mt-2 h-1.5" />
                                  </button>
                                )
                              })}
                            </div>
                          </ScrollArea>
                        ) : (
                          <div className="rounded-xl border bg-muted/20 p-4 text-sm text-muted-foreground">当前没有运行中任务</div>
                        )}
                      </div>

                      <div className="space-y-2.5">
                        <div className="flex items-center justify-between gap-2">
                          <div className="text-sm font-medium">排队中</div>
                          <Badge variant="outline">{queuedImportTasks.length}</Badge>
                        </div>
                        {queuedImportTasks.length > 0 ? (
                          <ScrollArea className="h-[188px] rounded-xl border bg-muted/10">
                            <div className="space-y-2.5 p-2.5">
                              {queuedImportTasks.map((task) => {
                                const isSelected = task.task_id === selectedImportTaskId
                                return (
                                  <button
                                    key={task.task_id}
                                    type="button"
                                    onClick={() => void selectImportTask(task.task_id)}
                                    className={cn(
                                      'w-full rounded-xl border p-4 text-left transition-all',
                                      isSelected
                                        ? 'border-primary/70 bg-primary/5 shadow-sm'
                                        : 'bg-background/80 hover:border-muted-foreground/40 hover:bg-muted/20',
                                    )}
                                  >
                                    <div className="flex flex-wrap items-start justify-between gap-2">
                                      <div className="min-w-0 space-y-1">
                                        <div className="break-all font-mono text-[11px] leading-relaxed text-muted-foreground">
                                          {task.task_id}
                                        </div>
                                        <div className="text-sm font-medium">{String(task.task_kind ?? task.mode ?? '-')}</div>
                                      </div>
                                      <Badge variant={getImportStatusVariant(String(task.status ?? ''))}>
                                        {getImportStatusLabel(String(task.status ?? ''))}
                                      </Badge>
                                    </div>
                                    <div className="mt-2 flex items-center justify-between gap-2 text-xs text-muted-foreground">
                                      <span>创建时间</span>
                                      <span>{formatImportTime(task.created_at)}</span>
                                    </div>
                                  </button>
                                )
                              })}
                            </div>
                          </ScrollArea>
                        ) : (
                          <div className="rounded-xl border bg-muted/20 p-4 text-sm text-muted-foreground">当前没有排队任务</div>
                        )}
                      </div>

                      <div className="space-y-2.5">
                        <div className="flex items-center justify-between gap-2">
                          <div className="text-sm font-medium">最近完成</div>
                          <Badge variant="secondary">{recentImportTasks.length}</Badge>
                        </div>
                        {recentImportTasks.length > 0 ? (
                          <ScrollArea className="h-[260px] rounded-xl border bg-muted/10">
                            <div className="space-y-2.5 p-2.5">
                              {recentImportTasks.map((task) => {
                                const isSelected = task.task_id === selectedImportTaskId
                                return (
                                  <button
                                    key={task.task_id}
                                    type="button"
                                    onClick={() => void selectImportTask(task.task_id)}
                                    className={cn(
                                      'w-full rounded-xl border p-4 text-left transition-all',
                                      isSelected
                                        ? 'border-primary/70 bg-primary/5 shadow-sm'
                                        : 'bg-background/80 hover:border-muted-foreground/40 hover:bg-muted/20',
                                    )}
                                  >
                                    <div className="flex flex-wrap items-start justify-between gap-2">
                                      <div className="min-w-0 space-y-1">
                                        <div className="break-all font-mono text-[11px] leading-relaxed text-muted-foreground">
                                          {task.task_id}
                                        </div>
                                        <div className="text-sm font-medium">{String(task.task_kind ?? task.mode ?? '-')}</div>
                                      </div>
                                      <Badge variant={getImportStatusVariant(String(task.status ?? ''))}>
                                        {getImportStatusLabel(String(task.status ?? ''))}
                                      </Badge>
                                    </div>
                                    <div className="mt-2 flex items-center justify-between gap-2 text-xs text-muted-foreground">
                                      <span>完成进度</span>
                                      <span>{Number(task.progress ?? 0).toFixed(1)}%</span>
                                    </div>
                                    <Progress value={normalizeProgress(task.progress)} className="mt-2 h-1.5" />
                                  </button>
                                )
                              })}
                            </div>
                          </ScrollArea>
                        ) : (
                          <div className="rounded-xl border bg-muted/20 p-4 text-sm text-muted-foreground">暂时没有历史任务</div>
                        )}
                      </div>
                    </CardContent>
                  </Card>

                </div>

                <Card className="rounded-2xl border-border/70 bg-card/90 shadow-sm">
                  <CardHeader className="space-y-4">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <CardTitle>任务详情</CardTitle>
                      <div className="flex flex-wrap gap-2">
                        <Button
                          size="sm"
                          variant="outline"
                          aria-label="取消选中导入任务"
                          onClick={() => void cancelSelectedImportTask()}
                          disabled={!selectedImportTaskId}
                        >
                          取消任务
                        </Button>
                        <Button
                          size="sm"
                          aria-label="重试选中导入任务"
                          onClick={() => void retrySelectedImportTask()}
                          disabled={!selectedImportTaskId}
                        >
                          重试失败项
                        </Button>
                      </div>
                    </div>
                    <CardDescription>支持文件级和分块级状态观察，可直接在当前页面定位失败原因</CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-6">
                    {selectedImportTaskLoading ? (
                      <div className="flex items-center gap-2 text-sm text-muted-foreground">
                        <Loader2 className="h-4 w-4 animate-spin" />
                        正在加载任务详情...
                      </div>
                    ) : null}

                    {!selectedImportTaskResolved ? (
                      <div className="rounded-xl border bg-muted/20 p-4 text-sm text-muted-foreground">
                        请选择一个导入任务查看详情
                      </div>
                    ) : (
                      <>
                        <div className="space-y-2">
                          <div className="text-sm font-medium">任务摘要</div>
                          <div className="overflow-auto rounded-xl border bg-muted/10">
                            <Table className="min-w-[680px]">
                              <TableBody>
                                <TableRow>
                                  <TableCell className="w-[140px] text-muted-foreground">任务 ID</TableCell>
                                  <TableCell className="break-all font-mono text-xs leading-relaxed">
                                    {selectedImportTaskResolved.task_id}
                                  </TableCell>
                                </TableRow>
                                <TableRow>
                                  <TableCell className="text-muted-foreground">任务类型</TableCell>
                                  <TableCell>{String(selectedImportTaskResolved.task_kind ?? selectedImportTaskResolved.mode ?? '-')}</TableCell>
                                </TableRow>
                                <TableRow>
                                  <TableCell className="text-muted-foreground">状态 / 步骤</TableCell>
                                  <TableCell>
                                    <div className="flex flex-wrap items-center gap-2">
                                      <Badge variant={getImportStatusVariant(String(selectedImportTaskResolved.status ?? ''))}>
                                        {getImportStatusLabel(String(selectedImportTaskResolved.status ?? ''))}
                                      </Badge>
                                      <span className="text-xs text-muted-foreground">
                                        {getImportStepLabel(String(selectedImportTaskResolved.current_step ?? ''))}
                                      </span>
                                    </div>
                                  </TableCell>
                                </TableRow>
                                <TableRow>
                                  <TableCell className="text-muted-foreground">进度</TableCell>
                                  <TableCell>
                                    <div className="space-y-2">
                                      <div className="text-sm">
                                        {Number(selectedImportTaskResolved.progress ?? 0).toFixed(1)}% · 块
                                        {' '}
                                        {Number(selectedImportTaskResolved.done_chunks ?? 0)}
                                        {' / '}
                                        {Number(selectedImportTaskResolved.total_chunks ?? 0)}
                                      </div>
                                      <Progress value={normalizeProgress(selectedImportTaskResolved.progress)} className="h-1.5" />
                                    </div>
                                  </TableCell>
                                </TableRow>
                                <TableRow>
                                  <TableCell className="text-muted-foreground">创建时间</TableCell>
                                  <TableCell>{formatImportTime(selectedImportTaskResolved.created_at)}</TableCell>
                                </TableRow>
                                <TableRow>
                                  <TableCell className="text-muted-foreground">更新时间</TableCell>
                                  <TableCell>{formatImportTime(selectedImportTaskResolved.updated_at)}</TableCell>
                                </TableRow>
                              </TableBody>
                            </Table>
                          </div>
                        </div>

                        {selectedImportRetrySummary ? (
                          <div className="space-y-2">
                            <div className="text-sm font-medium">重试摘要</div>
                            <div className="overflow-auto rounded-xl border bg-muted/10">
                              <Table>
                                <TableBody>
                                  <TableRow>
                                    <TableCell className="w-[220px] text-muted-foreground">按分块重试的文件数</TableCell>
                                    <TableCell>{Number(selectedImportRetrySummary.chunk_retry_files ?? 0)}</TableCell>
                                  </TableRow>
                                  <TableRow>
                                    <TableCell className="text-muted-foreground">按分块重试的分块数</TableCell>
                                    <TableCell>{Number(selectedImportRetrySummary.chunk_retry_chunks ?? 0)}</TableCell>
                                  </TableRow>
                                  <TableRow>
                                    <TableCell className="text-muted-foreground">回退整文件重试数</TableCell>
                                    <TableCell>{Number(selectedImportRetrySummary.file_fallback_files ?? 0)}</TableCell>
                                  </TableRow>
                                  <TableRow>
                                    <TableCell className="text-muted-foreground">跳过文件数</TableCell>
                                    <TableCell>{Number(selectedImportRetrySummary.skipped_files ?? 0)}</TableCell>
                                  </TableRow>
                                </TableBody>
                              </Table>
                            </div>
                          </div>
                        ) : null}

                        {selectedImportTaskErrorText ? (
                          <Alert variant="destructive">
                            <AlertDescription>{selectedImportTaskErrorText}</AlertDescription>
                          </Alert>
                        ) : null}

                        <div className="space-y-2.5">
                          <div className="text-sm font-medium">文件状态</div>
                          {selectedImportFiles.length > 0 ? (
                            <ScrollArea className="h-[260px] rounded-xl border bg-muted/10">
                              <div className="space-y-2.5 p-2.5">
                                {selectedImportFiles.map((file) => {
                                  const isSelected = file.file_id === selectedImportFileId
                                  return (
                                    <button
                                      key={file.file_id}
                                      type="button"
                                      onClick={() => void selectImportFile(file.file_id)}
                                      className={cn(
                                        'w-full rounded-xl border p-4 text-left transition-all',
                                        isSelected
                                          ? 'border-primary/70 bg-primary/5 shadow-sm'
                                          : 'bg-background/80 hover:border-muted-foreground/40 hover:bg-muted/20',
                                      )}
                                    >
                                      <div className="flex flex-wrap items-center justify-between gap-2">
                                        <span className="truncate text-sm font-medium">{file.name || file.file_id}</span>
                                        <Badge variant={getImportStatusVariant(String(file.status ?? ''))}>
                                          {getImportStatusLabel(String(file.status ?? ''))}
                                        </Badge>
                                      </div>
                                      <div className="mt-2 flex items-center justify-between gap-2 text-xs text-muted-foreground">
                                        <span>{getImportStepLabel(String(file.current_step ?? ''))}</span>
                                        <span>{Number(file.progress ?? 0).toFixed(1)}%</span>
                                      </div>
                                      <Progress value={normalizeProgress(file.progress)} className="mt-2 h-1.5" />
                                      <div className="mt-2 text-xs text-muted-foreground">
                                        {Number(file.progress ?? 0).toFixed(1)}% · {Number(file.done_chunks ?? 0)} / {Number(file.total_chunks ?? 0)}
                                      </div>
                                      {file.error ? (
                                        <div className="mt-2 truncate text-xs text-destructive">{file.error}</div>
                                      ) : null}
                                    </button>
                                  )
                                })}
                              </div>
                            </ScrollArea>
                          ) : (
                            <div className="rounded-xl border bg-muted/20 p-4 text-sm text-muted-foreground">当前任务没有文件明细</div>
                          )}
                        </div>

                        <div className="space-y-2.5">
                          <div className="flex items-center justify-between gap-2">
                            <div className="text-sm font-medium">分块状态</div>
                            <div className="flex items-center gap-2 text-xs text-muted-foreground">
                              <Button
                                size="icon"
                                variant="outline"
                                aria-label="上一页分块"
                                onClick={() => void moveImportChunkPage(-1)}
                                disabled={!canImportChunkPrev}
                              >
                                <ChevronLeft className="h-4 w-4" />
                              </Button>
                              <span>
                                {importChunkTotal > 0
                                  ? `${importChunkOffset + 1}-${Math.min(importChunkOffset + IMPORT_CHUNK_PAGE_SIZE, importChunkTotal)}`
                                  : '0-0'}
                                {' / '}
                                {importChunkTotal}
                              </span>
                              <Button
                                size="icon"
                                variant="outline"
                                aria-label="下一页分块"
                                onClick={() => void moveImportChunkPage(1)}
                                disabled={!canImportChunkNext}
                              >
                                <ChevronRight className="h-4 w-4" />
                              </Button>
                            </div>
                          </div>

                          <div className="overflow-auto rounded-xl border bg-background/80">
                            <Table className="min-w-[700px]">
                              <TableHeader>
                                <TableRow>
                                  <TableHead className="w-[72px]">序号</TableHead>
                                  <TableHead className="w-[108px]">状态</TableHead>
                                  <TableHead className="w-[108px]">步骤</TableHead>
                                  <TableHead className="w-[84px]">进度</TableHead>
                                  <TableHead>错误 / 预览</TableHead>
                                </TableRow>
                              </TableHeader>
                              <TableBody>
                                {importChunksLoading ? (
                                  <TableRow>
                                    <TableCell colSpan={5} className="text-center text-muted-foreground">
                                      正在加载分块详情...
                                    </TableCell>
                                  </TableRow>
                                ) : selectedImportChunks.length > 0 ? (
                                  selectedImportChunks.map((chunk) => (
                                    <TableRow key={chunk.chunk_id}>
                                      <TableCell>{chunk.index}</TableCell>
                                      <TableCell>{getImportStatusLabel(String(chunk.status ?? ''))}</TableCell>
                                      <TableCell>{getImportStepLabel(String(chunk.step ?? ''))}</TableCell>
                                      <TableCell>{Number(chunk.progress ?? 0).toFixed(1)}%</TableCell>
                                      <TableCell className="max-w-[360px]">
                                        <div className="space-y-2">
                                          {String(chunk.error ?? '').trim() ? (
                                            <div className="rounded-md border border-destructive/30 bg-destructive/5 px-2.5 py-2 text-sm leading-relaxed text-destructive">
                                              {String(chunk.error)}
                                            </div>
                                          ) : null}
                                          <details className="rounded-md border bg-muted/20 px-2.5 py-2 text-xs text-muted-foreground">
                                            <summary className="cursor-pointer font-medium text-foreground">
                                              {String(chunk.error ?? '').trim() ? '查看分块预览' : '查看内容详情'}
                                            </summary>
                                            <div className="mt-2 whitespace-pre-wrap break-words leading-relaxed">
                                              {String(chunk.content_preview ?? '-') || '-'}
                                            </div>
                                          </details>
                                        </div>
                                      </TableCell>
                                    </TableRow>
                                  ))
                                ) : (
                                  <TableRow>
                                    <TableCell colSpan={5} className="text-center text-muted-foreground">
                                      当前页没有分块数据
                                    </TableCell>
                                  </TableRow>
                                )}
                              </TableBody>
                            </Table>
                          </div>
                        </div>
                      </>
                    )}
                  </CardContent>
                </Card>
              </div>
            </TabsContent>

            <TabsContent value="tuning" className="space-y-4">
              <div className="grid gap-4 xl:grid-cols-[0.95fr_1.05fr]">
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <Sparkles className="h-4 w-4" />
                      调优任务
                    </CardTitle>
                    <CardDescription>创建一次检索参数评估任务，完成后可在右侧列表中查看并应用最佳结果。</CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <div className="space-y-3 rounded-lg border bg-muted/20 p-4">
                      <div className="space-y-1">
                        <div className="text-sm font-medium">调优策略</div>
                        <div className="text-xs text-muted-foreground">先选择优化方向和搜索强度。默认的 balanced / standard 适合大多数情况。</div>
                      </div>
                      <div className="grid gap-4 md:grid-cols-2">
                        <div className="space-y-2">
                          <Label>优化目标</Label>
                          <div className="text-xs text-muted-foreground">决定本次调优更偏向准确率、召回率，还是两者平衡。</div>
                          <Select value={tuningObjective} onValueChange={setTuningObjective}>
                            <SelectTrigger><SelectValue /></SelectTrigger>
                            <SelectContent>
                              <SelectItem value="precision_priority">precision_priority</SelectItem>
                              <SelectItem value="balanced">balanced</SelectItem>
                              <SelectItem value="recall_priority">recall_priority</SelectItem>
                            </SelectContent>
                          </Select>
                        </div>
                        <div className="space-y-2">
                          <Label>评估强度</Label>
                          <div className="text-xs text-muted-foreground">强度越高，评估更充分，但任务耗时也更长。</div>
                          <Select value={tuningIntensity} onValueChange={setTuningIntensity}>
                            <SelectTrigger><SelectValue /></SelectTrigger>
                            <SelectContent>
                              <SelectItem value="quick">quick</SelectItem>
                              <SelectItem value="standard">standard</SelectItem>
                              <SelectItem value="deep">deep</SelectItem>
                            </SelectContent>
                          </Select>
                        </div>
                      </div>
                    </div>
                    <div className="space-y-3 rounded-lg border bg-muted/20 p-4">
                      <div className="space-y-1">
                        <div className="text-sm font-medium">评估范围</div>
                        <div className="text-xs text-muted-foreground">控制本次任务使用多少样本，以及每次检索评估多少候选结果。</div>
                      </div>
                      <div className="grid gap-4 md:grid-cols-2">
                        <div className="space-y-2">
                          <Label>样本量</Label>
                          <div className="text-xs text-muted-foreground">用于评估的样本数量。数量越大，结果越稳定。</div>
                          <Input type="number" value={tuningSampleSize} onChange={(event) => setTuningSampleSize(event.target.value)} />
                        </div>
                        <div className="space-y-2">
                          <Label>评估 Top-K</Label>
                          <div className="text-xs text-muted-foreground">每次检索时用于评估的候选结果数量。</div>
                          <Input type="number" value={tuningTopKEval} onChange={(event) => setTuningTopKEval(event.target.value)} />
                        </div>
                      </div>
                    </div>
                    <Button onClick={() => void submitTuningTask()} disabled={creatingTuning}>
                      <Sparkles className="mr-2 h-4 w-4" />
                      创建调优任务
                    </Button>
                  </CardContent>
                </Card>

                <div className="space-y-4">
                  <Card>
                    <CardHeader>
                      <CardTitle>当前调优配置快照</CardTitle>
                      <CardDescription>展示当前生效的检索调优参数，便于在应用新结果前做对照。</CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-3">
                      <CodeEditor
                        value={JSON.stringify(tuningProfile, null, 2)}
                        language="json"
                        readOnly
                        height="220px"
                      />
                      <CodeEditor
                        value={tuningProfileToml}
                        language="toml"
                        readOnly
                        height="180px"
                      />
                    </CardContent>
                  </Card>

                  <Card>
                    <CardHeader>
                      <CardTitle>最近调优任务</CardTitle>
                      <CardDescription>任务完成后，可以把最佳结果应用到当前调优配置。</CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-3">
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead>任务</TableHead>
                            <TableHead>状态</TableHead>
                            <TableHead>动作</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {tuningTasks.length > 0 ? tuningTasks.map((task) => (
                            <TableRow key={String(task.task_id ?? Math.random())}>
                              <TableCell className="font-mono text-xs">{String(task.task_id ?? '-')}</TableCell>
                              <TableCell>
                                <Badge variant={getImportStatusVariant(String(task.status ?? ''))}>
                                  {String(task.status ?? '-')}
                                </Badge>
                              </TableCell>
                              <TableCell>
                                <Button
                                  size="sm"
                                  variant="outline"
                                  onClick={() => void applyBestTask(String(task.task_id ?? ''))}
                                  disabled={!task.task_id}
                                >
                                  应用最佳
                                </Button>
                              </TableCell>
                            </TableRow>
                          )) : (
                            <TableRow>
                              <TableCell colSpan={3} className="text-center text-muted-foreground">
                                还没有调优任务。可以先使用默认参数创建一次评估任务。
                              </TableCell>
                            </TableRow>
                          )}
                        </TableBody>
                      </Table>
                    </CardContent>
                  </Card>
                </div>
              </div>
            </TabsContent>

            <TabsContent value="delete" className="space-y-4">
              <div className="space-y-4">
                <Card>
                  <CardHeader className="space-y-3">
                    <div>
                      <CardTitle className="flex items-center gap-2">
                        <Trash2 className="h-4 w-4" />
                        来源批量删除
                      </CardTitle>
                      <CardDescription>
                        用于按来源清理测试数据或指定导入批次。该操作不会直接删除实体，只会删除来源段落和失去全部证据的关系。
                      </CardDescription>
                    </div>
                    <Alert className="border-amber-500/30 bg-amber-500/5 text-amber-950 dark:text-amber-200">
                      <CircleAlert className="h-4 w-4 text-amber-500" />
                      <AlertDescription>
                        建议先在图谱里确认影响范围，再在这里执行批量来源删除。所有删除都会先经过预览，并支持按删除记录恢复。
                      </AlertDescription>
                    </Alert>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <div className="grid gap-3 rounded-xl border bg-muted/20 p-4 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-center">
                      <div className="space-y-2">
                        <Label>来源检索</Label>
                        <Input
                          value={sourceSearch}
                          onChange={(event) => setSourceSearch(event.target.value)}
                          placeholder="搜索 source 名称"
                        />
                      </div>
                      <div className="flex flex-wrap gap-2 lg:justify-end">
                        <Button
                          variant="outline"
                          onClick={() => setSelectedSources(filteredSources.map((item) => String(item.source ?? '')).filter(Boolean))}
                        >
                          全选当前结果
                        </Button>
                        <Button onClick={() => void openSourceDeletePreview()} disabled={selectedSources.length <= 0}>
                          <Trash2 className="mr-2 h-4 w-4" />
                          预览删除
                        </Button>
                      </div>
                    </div>

                    <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
                      <Badge variant="outline" className="bg-background/70">当前命中 {filteredSources.length} 个来源</Badge>
                      <Badge variant={selectedSources.length > 0 ? 'secondary' : 'outline'} className="bg-background/70">
                        已选择 {selectedSources.length} 个来源
                      </Badge>
                    </div>

                    <ScrollArea className="h-[320px] rounded-lg border">
                      <Table>
                        <TableHeader className="sticky top-0 bg-background">
                          <TableRow>
                            <TableHead className="w-12">选中</TableHead>
                            <TableHead>来源</TableHead>
                            <TableHead>段落数</TableHead>
                            <TableHead>关系数</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {filteredSources.length > 0 ? filteredSources.map((item) => {
                            const source = String(item.source ?? '')
                            const checked = selectedSources.includes(source)
                            return (
                              <TableRow key={source}>
                                <TableCell>
                                  <Checkbox checked={checked} onCheckedChange={(value) => toggleSourceSelection(source, Boolean(value))} />
                                </TableCell>
                                <TableCell className="font-mono text-xs break-all">{source}</TableCell>
                                <TableCell>{Number(item.paragraph_count ?? 0)}</TableCell>
                                <TableCell>{Number(item.relation_count ?? 0)}</TableCell>
                              </TableRow>
                            )
                          }) : (
                            <TableRow>
                              <TableCell colSpan={4} className="text-center text-muted-foreground">
                                当前没有可删除的来源
                              </TableCell>
                            </TableRow>
                          )}
                        </TableBody>
                      </Table>
                    </ScrollArea>
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <RotateCcw className="h-4 w-4" />
                      删除操作恢复
                    </CardTitle>
                    <CardDescription>按列表浏览最近的删除操作，先选中记录，再在下方确认影响范围并执行恢复</CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <div className="grid gap-3 rounded-xl border bg-muted/20 p-4 lg:grid-cols-[minmax(0,1fr)_180px_180px]">
                      <Input
                        value={operationSearch}
                        onChange={(event) => setOperationSearch(event.target.value)}
                        placeholder="搜索 operation / reason / requested_by / source"
                      />
                      <Select value={operationModeFilter} onValueChange={setOperationModeFilter}>
                        <SelectTrigger>
                          <SelectValue placeholder="按模式筛选" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="all">全部模式</SelectItem>
                          <SelectItem value="source">来源删除</SelectItem>
                          <SelectItem value="mixed">混合删除</SelectItem>
                          <SelectItem value="entity">实体删除</SelectItem>
                          <SelectItem value="relation">关系删除</SelectItem>
                          <SelectItem value="paragraph">段落删除</SelectItem>
                        </SelectContent>
                      </Select>
                      <Select value={operationStatusFilter} onValueChange={setOperationStatusFilter}>
                        <SelectTrigger>
                          <SelectValue placeholder="按状态筛选" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="all">全部状态</SelectItem>
                          <SelectItem value="executed">已执行</SelectItem>
                          <SelectItem value="restored">已恢复</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>

                    <div className="flex flex-wrap items-center justify-between gap-2 text-sm text-muted-foreground">
                      <span>当前命中 {filteredDeleteOperations.length} 条记录，已加载最近 {deleteOperations.length} 条</span>
                      <span>第 {operationPage} / {deleteOperationPageCount} 页，每页显示 {DELETE_OPERATION_PAGE_SIZE} 条</span>
                    </div>

                    <ScrollArea className="h-[320px] rounded-lg border">
                      <div className="space-y-3 p-3">
                        {pagedDeleteOperations.length > 0 ? pagedDeleteOperations.map((operation) => {
                          const summary = (operation.summary ?? {}) as Record<string, unknown>
                          const counts = ((summary.counts as Record<string, number> | undefined) ?? {})
                          const isSelected = selectedDeleteOperation?.operation_id === operation.operation_id
                          return (
                            <button
                              key={operation.operation_id}
                              type="button"
                              onClick={() => setSelectedOperationId(operation.operation_id)}
                              className={cn(
                                'w-full rounded-xl border p-4 text-left transition-colors',
                                isSelected
                                  ? 'border-primary bg-primary/5 shadow-sm'
                                  : 'bg-muted/20 hover:border-primary/40 hover:bg-muted/40',
                              )}
                            >
                              <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                                <div className="min-w-0 space-y-2">
                                  <div className="flex flex-wrap items-center gap-2">
                                    <Badge variant={operation.status === 'restored' ? 'secondary' : 'default'}>
                                      {formatDeleteOperationStatus(String(operation.status ?? ''))}
                                    </Badge>
                                    <Badge variant="outline">
                                      {formatDeleteOperationMode(String(operation.mode ?? ''))}
                                    </Badge>
                                  </div>
                                  <div className="font-mono text-xs break-all">{operation.operation_id}</div>
                                  <div className="text-sm text-muted-foreground">
                                    {operation.reason || '未填写原因'}
                                  </div>
                                </div>
                                <div className="flex flex-wrap gap-2 text-xs text-muted-foreground lg:max-w-[280px] lg:justify-end">
                                  <span>实体 {Number(counts.entities ?? 0)}</span>
                                  <span>关系 {Number(counts.relations ?? 0)}</span>
                                  <span>段落 {Number(counts.paragraphs ?? 0)}</span>
                                  <span>来源 {Number(counts.sources ?? 0)}</span>
                                </div>
                              </div>
                              <div className="mt-3 text-xs text-muted-foreground">
                                {formatDeleteOperationTime(operation.created_at)}
                              </div>
                            </button>
                          )
                        }) : (
                          <div className="rounded-lg border border-dashed bg-muted/20 p-6 text-center text-sm text-muted-foreground">
                            当前筛选条件下没有删除操作
                          </div>
                        )}
                      </div>
                    </ScrollArea>

                    <div className="flex items-center justify-between gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setOperationPage((current) => Math.max(1, current - 1))}
                        disabled={operationPage <= 1}
                      >
                        上一页
                      </Button>
                      <div className="text-xs text-muted-foreground">
                        支持按删除记录、模式、状态、发起人和来源检索
                      </div>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setOperationPage((current) => Math.min(deleteOperationPageCount, current + 1))}
                        disabled={operationPage >= deleteOperationPageCount}
                      >
                        下一页
                      </Button>
                    </div>

                    <div className="rounded-xl border bg-muted/20 p-4">
                      {selectedDeleteOperation ? (
                        <div className="space-y-4">
                          <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                            <div className="space-y-2">
                              <div className="flex flex-wrap items-center gap-2">
                                <Badge variant={selectedDeleteOperation.status === 'restored' ? 'secondary' : 'default'}>
                                  {formatDeleteOperationStatus(String(selectedDeleteOperation.status ?? ''))}
                                </Badge>
                                <Badge variant="outline">
                                  {formatDeleteOperationMode(String(selectedDeleteOperation.mode ?? ''))}
                                </Badge>
                              </div>
                              <div className="font-mono text-xs break-all">{selectedDeleteOperation.operation_id}</div>
                              <div className="text-sm text-muted-foreground">
                                {selectedDeleteOperation.reason || '未填写删除原因'}
                              </div>
                            </div>
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => void restoreDeleteOperation(selectedDeleteOperation.operation_id)}
                              disabled={selectedDeleteOperation.status === 'restored' || deleteRestoring}
                            >
                              <RotateCcw className="mr-2 h-4 w-4" />
                              {selectedDeleteOperation.status === 'restored' ? '已恢复' : '恢复这次删除'}
                            </Button>
                          </div>

                          <div className="grid gap-3 lg:grid-cols-4">
                            <div className="rounded-lg border bg-background/60 p-3">
                              <div className="text-xs text-muted-foreground">发起人</div>
                              <div className="mt-1 text-sm">{selectedDeleteOperation.requested_by || '-'}</div>
                            </div>
                            <div className="rounded-lg border bg-background/60 p-3">
                              <div className="text-xs text-muted-foreground">创建时间</div>
                              <div className="mt-1 text-sm">{formatDeleteOperationTime(selectedDeleteOperation.created_at)}</div>
                            </div>
                            <div className="rounded-lg border bg-background/60 p-3">
                              <div className="text-xs text-muted-foreground">恢复时间</div>
                              <div className="mt-1 text-sm">{formatDeleteOperationTime(selectedDeleteOperation.restored_at)}</div>
                            </div>
                            <div className="rounded-lg border bg-background/60 p-3">
                              <div className="text-xs text-muted-foreground">删除摘要</div>
                              <div className="mt-1 flex flex-wrap gap-2">
                                <Badge variant="outline">实体 {Number(selectedOperationCounts.entities ?? 0)}</Badge>
                                <Badge variant="outline">关系 {Number(selectedOperationCounts.relations ?? 0)}</Badge>
                                <Badge variant="outline">段落 {Number(selectedOperationCounts.paragraphs ?? 0)}</Badge>
                                <Badge variant="outline">来源 {Number(selectedOperationCounts.sources ?? 0)}</Badge>
                              </div>
                            </div>
                          </div>

                          {selectedOperationDetailLoading ? (
                            <div className="rounded-lg border bg-background/60 p-4 text-sm text-muted-foreground">
                              正在加载影响对象详情...
                            </div>
                          ) : null}

                          {selectedOperationDetailError ? (
                            <Alert variant="destructive">
                              <AlertDescription>{selectedOperationDetailError}</AlertDescription>
                            </Alert>
                          ) : null}

                          {selectedOperationSources.length > 0 ? (
                            <div className="space-y-2">
                              <div className="text-sm font-semibold">关联来源</div>
                              <div className="flex flex-wrap gap-2">
                                {selectedOperationSources.map((source) => (
                                  <Badge key={source} variant="secondary" className="max-w-full break-all">
                                    {source}
                                  </Badge>
                                ))}
                              </div>
                            </div>
                          ) : null}

                          <div className="grid gap-4 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
                            <div className="space-y-2">
                              <div className="text-sm font-semibold">选择器</div>
                              <pre className="max-h-56 overflow-auto rounded-lg border bg-background/70 p-3 text-xs break-words whitespace-pre-wrap">
                                {JSON.stringify(selectedDeleteOperation.selector ?? {}, null, 2)}
                              </pre>
                            </div>

                            <div className="space-y-2">
                              <div className="flex items-center justify-between">
                                <div className="text-sm font-semibold">影响对象</div>
                                <div className="text-xs text-muted-foreground">
                                  命中 {filteredSelectedOperationItems.length} / {selectedOperationItems.length} 项
                                </div>
                              </div>
                              <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                                <Input
                                  value={selectedOperationItemSearch}
                                  onChange={(event) => setSelectedOperationItemSearch(event.target.value)}
                                  placeholder="搜索对象类型 / 哈希 / 对象键 / 来源"
                                  className="lg:max-w-sm"
                                />
                                <div className="flex items-center justify-between gap-2 text-xs text-muted-foreground lg:min-w-[180px] lg:justify-end">
                                  <span>第 {selectedOperationItemPage} / {selectedOperationItemPageCount} 页</span>
                                  <span>每页 {DELETE_OPERATION_ITEM_PAGE_SIZE} 项</span>
                                </div>
                              </div>
                              <ScrollArea className="h-[280px] rounded-lg border bg-background/60">
                                <div className="space-y-2 p-3">
                                  {pagedSelectedOperationItems.length > 0 ? pagedSelectedOperationItems.map((item) => {
                                    const source = getDeleteOperationItemSource(item)
                                    const label = getDeleteOperationItemLabel(item)
                                    const preview = getDeleteOperationItemPreview(item)
                                    return (
                                      <div key={`${item.item_type}:${item.item_hash}:${item.item_key ?? ''}`} className="rounded-lg border bg-muted/20 p-3">
                                        <div className="flex flex-wrap items-center gap-2">
                                          <Badge variant="outline">{item.item_type}</Badge>
                                          {source ? <Badge variant="secondary">{source}</Badge> : null}
                                          {item.item_key && item.item_key !== item.item_hash ? (
                                            <span className="text-xs text-muted-foreground break-all">{item.item_key}</span>
                                          ) : null}
                                        </div>
                                        <div className="mt-2 text-sm font-medium break-words">
                                          {label}
                                        </div>
                                        {preview ? (
                                          <div className="mt-1 text-xs text-muted-foreground break-words">
                                            {preview}
                                          </div>
                                        ) : null}
                                        <div className="mt-2 font-mono text-[11px] break-all text-muted-foreground">
                                          {item.item_hash}
                                        </div>
                                      </div>
                                    )
                                  }) : (
                                    <div className="rounded-lg border border-dashed bg-muted/20 p-6 text-center text-sm text-muted-foreground">
                                      {selectedOperationItems.length > 0 ? '当前筛选条件下没有明细项' : '当前操作没有记录明细项'}
                                    </div>
                                  )}
                                </div>
                              </ScrollArea>
                              <div className="flex items-center justify-between gap-2">
                                <Button
                                  variant="outline"
                                  size="sm"
                                  onClick={() => setSelectedOperationItemPage((current) => Math.max(1, current - 1))}
                                  disabled={selectedOperationItemPage <= 1}
                                >
                                  上一页
                                </Button>
                                <div className="text-xs text-muted-foreground">
                                  支持按对象类型、哈希、对象键和来源检索
                                </div>
                                <Button
                                  variant="outline"
                                  size="sm"
                                  onClick={() => setSelectedOperationItemPage((current) => Math.min(selectedOperationItemPageCount, current + 1))}
                                  disabled={selectedOperationItemPage >= selectedOperationItemPageCount}
                                >
                                  下一页
                                </Button>
                              </div>
                            </div>
                          </div>
                        </div>
                      ) : (
                        <div className="flex min-h-[320px] items-center justify-center rounded-lg border border-dashed bg-background/40 p-6 text-center text-sm text-muted-foreground">
                          当前没有可查看的删除操作详情
                        </div>
                      )}
                    </div>
                  </CardContent>
                </Card>
              </div>
            </TabsContent>

            <TabsContent value="feedback" className="space-y-4">
              <div className="space-y-4">
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <RotateCcw className="h-4 w-4" />
                      反馈纠错历史
                    </CardTitle>
                    <CardDescription>
                      查看 feedback correction 的判定、修改轨迹与回退结果；本期仅覆盖自动纠错任务
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_180px_180px]">
                      <Input
                        value={feedbackSearch}
                        onChange={(event) => setFeedbackSearch(event.target.value)}
                        placeholder="搜索查询编号 / 会话 / 查询内容 / 原因"
                      />
                      <Select value={feedbackStatusFilter} onValueChange={setFeedbackStatusFilter}>
                        <SelectTrigger>
                          <SelectValue placeholder="按任务状态筛选" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="all">全部任务状态</SelectItem>
                          <SelectItem value="applied">已应用</SelectItem>
                          <SelectItem value="skipped">已跳过</SelectItem>
                          <SelectItem value="error">失败</SelectItem>
                          <SelectItem value="running">处理中</SelectItem>
                          <SelectItem value="pending">待处理</SelectItem>
                        </SelectContent>
                      </Select>
                      <Select value={feedbackRollbackFilter} onValueChange={setFeedbackRollbackFilter}>
                        <SelectTrigger>
                          <SelectValue placeholder="按回退状态筛选" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="all">全部回退状态</SelectItem>
                          <SelectItem value="none">未回退</SelectItem>
                          <SelectItem value="rolled_back">已回退</SelectItem>
                          <SelectItem value="error">回退失败</SelectItem>
                          <SelectItem value="running">回退中</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>

                    <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border bg-background/70 px-3 py-2 text-sm text-muted-foreground">
                      <span>当前命中 {filteredFeedbackCorrections.length} 条记录，已加载最近 {feedbackCorrections.length} 条</span>
                      <span>第 {feedbackPage} / {feedbackPageCount} 页，每页显示 {FEEDBACK_CORRECTION_PAGE_SIZE} 条</span>
                    </div>

                    <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,0.92fr)_minmax(0,1.08fr)]">
                      <ScrollArea className="h-[720px] rounded-lg border">
                        <div className="space-y-3 p-3">
                          {pagedFeedbackCorrections.length > 0 ? pagedFeedbackCorrections.map((item) => {
                            const isSelected = selectedFeedbackCorrection?.task_id === item.task_id
                            const preview = getFeedbackCorrectionPreview(item)
                            const impactSummary = buildFeedbackImpactSummary(item)
                            return (
                              <button
                                key={item.task_id}
                                type="button"
                                onClick={() => setSelectedFeedbackTaskId(item.task_id)}
                                className={cn(
                                  'w-full rounded-xl border p-4 text-left transition-colors',
                                  isSelected
                                    ? 'border-primary bg-primary/5 shadow-sm'
                                    : 'bg-muted/20 hover:border-primary/40 hover:bg-muted/40',
                                )}
                              >
                                <div className="flex flex-col gap-3">
                                  <div className="flex flex-wrap items-start justify-between gap-2">
                                    <div className="flex flex-wrap items-center gap-2">
                                      <Badge variant={getFeedbackStatusVariant(item.task_status)}>
                                        {formatFeedbackTaskStatus(item.task_status)}
                                      </Badge>
                                      <Badge variant={getFeedbackStatusVariant(item.rollback_status)}>
                                        {formatFeedbackRollbackStatus(item.rollback_status)}
                                      </Badge>
                                      <Badge variant="outline">
                                        {formatFeedbackDecision(item.decision)}
                                      </Badge>
                                    </div>
                                    <div className="text-[11px] text-muted-foreground">
                                      {formatDeleteOperationTime(item.query_timestamp ?? item.created_at)}
                                    </div>
                                  </div>
                                  <div className="space-y-1">
                                    <div className="text-sm font-semibold break-words">
                                      {preview.headline}
                                    </div>
                                    <div className="text-xs text-muted-foreground break-words">
                                      查询：{item.query_text || '无查询文本'}
                                    </div>
                                  </div>
                                  {(preview.oldRelation || preview.newRelation) ? (
                                    <div className="grid gap-2 rounded-lg border bg-background/70 p-3 text-xs shadow-sm">
                                      <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] sm:items-stretch">
                                        <div className="rounded-md border border-amber-500/20 bg-amber-500/5 p-2">
                                          <div className="text-[11px] font-medium text-amber-700 dark:text-amber-300">纠错前</div>
                                          <div className="mt-1 break-words">{preview.oldRelation || '无'}</div>
                                        </div>
                                        <div className="hidden items-center text-muted-foreground sm:flex">→</div>
                                        <div className="rounded-md border border-emerald-500/20 bg-emerald-500/5 p-2">
                                          <div className="text-[11px] font-medium text-emerald-700 dark:text-emerald-300">纠错后</div>
                                          <div className="mt-1 break-words">{preview.newRelation || '无'}</div>
                                        </div>
                                      </div>
                                    </div>
                                  ) : null}
                                  <div className="flex flex-wrap gap-2">
                                    {impactSummary.length > 0 ? impactSummary.slice(0, 3).map((summary) => (
                                      <Badge key={`${item.task_id}:${summary}`} variant="secondary" className="font-normal">
                                        {summary}
                                      </Badge>
                                    )) : (
                                      <Badge variant="secondary" className="font-normal">
                                        暂无影响摘要
                                      </Badge>
                                    )}
                                  </div>
                                  <div className="font-mono text-[11px] break-all text-muted-foreground">
                                    {item.query_tool_id}
                                  </div>
                                </div>
                              </button>
                            )
                          }) : (
                            <div className="rounded-lg border border-dashed bg-muted/20 p-6 text-center text-sm text-muted-foreground">
                              当前筛选条件下没有纠错历史
                            </div>
                          )}
                        </div>
                      </ScrollArea>

                      <div className="self-start rounded-xl border bg-muted/20 p-4">
                        {selectedFeedbackCorrection ? (
                          <div className="space-y-4">
                            <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                              <div className="space-y-2">
                                <div className="flex flex-wrap items-center gap-2">
                                  <Badge variant={getFeedbackStatusVariant(String(selectedFeedbackResolved?.task_status ?? ''))}>
                                    {formatFeedbackTaskStatus(String(selectedFeedbackResolved?.task_status ?? ''))}
                                  </Badge>
                                  <Badge variant={getFeedbackStatusVariant(String(selectedFeedbackResolved?.rollback_status ?? 'none'))}>
                                    {formatFeedbackRollbackStatus(String(selectedFeedbackResolved?.rollback_status ?? 'none'))}
                                  </Badge>
                                  <Badge variant="outline">
                                    {formatFeedbackDecision(String(selectedFeedbackResolved?.decision ?? ''))}
                                  </Badge>
                                </div>
                                <div className="text-base font-semibold break-words">
                                  {selectedFeedbackPreview.headline}
                                </div>
                                <div className="text-sm text-muted-foreground break-words">
                                  查询：{selectedFeedbackResolved?.query_text || '无查询文本'}
                                </div>
                                <div className="font-mono text-xs break-all text-muted-foreground">
                                  {selectedFeedbackResolved?.query_tool_id}
                                </div>
                              </div>
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={openFeedbackRollbackDialog}
                                disabled={
                                  String(selectedFeedbackResolved?.task_status ?? '') !== 'applied'
                                  || String(selectedFeedbackResolved?.rollback_status ?? 'none') === 'rolled_back'
                                  || feedbackRollingBack
                                }
                              >
                                <RotateCcw className="mr-2 h-4 w-4" />
                                {String(selectedFeedbackResolved?.rollback_status ?? 'none') === 'rolled_back'
                                  ? '已回退'
                                  : '回退本次纠错'}
                              </Button>
                            </div>

                            <div className="grid gap-4 xl:grid-cols-[minmax(0,1.05fr)_minmax(0,0.95fr)]">
                              <div className="rounded-xl border bg-background/70 p-4 shadow-sm">
                                <div className="text-sm font-semibold">本次纠错结论</div>
                                <div className="mt-3 grid gap-3 md:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] md:items-stretch">
                                  <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-3">
                                    <div className="text-xs font-medium text-amber-700 dark:text-amber-300">纠错前</div>
                                    <div className="mt-2 text-sm break-words">
                                      {selectedFeedbackPreview.oldRelation || '当前详情没有记录旧结论'}
                                    </div>
                                  </div>
                                  <div className="hidden items-center justify-center text-muted-foreground md:flex">→</div>
                                  <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-3">
                                    <div className="text-xs font-medium text-emerald-700 dark:text-emerald-300">纠错后</div>
                                    <div className="mt-2 text-sm break-words">
                                      {selectedFeedbackPreview.newRelation || '当前详情没有记录新结论'}
                                    </div>
                                  </div>
                                </div>
                              </div>

                              <div className="rounded-xl border bg-background/70 p-4 shadow-sm">
                                <div className="text-sm font-semibold">影响范围摘要</div>
                                <div className="mt-3 flex flex-wrap gap-2">
                                  {selectedFeedbackImpactSummary.length > 0 ? selectedFeedbackImpactSummary.map((summary) => (
                                    <Badge key={summary} variant="secondary" className="bg-primary/10 font-normal text-primary hover:bg-primary/15">
                                      {summary}
                                    </Badge>
                                  )) : (
                                    <div className="text-sm text-muted-foreground">当前没有可展示的影响范围摘要</div>
                                  )}
                                </div>
                              </div>
                            </div>

                            <div className="grid gap-3 lg:grid-cols-4">
                              <div className="rounded-lg border bg-background/60 p-3">
                                <div className="text-xs text-muted-foreground">会话</div>
                                <div className="mt-1 text-sm break-all">{selectedFeedbackResolved?.session_id || '-'}</div>
                              </div>
                              <div className="rounded-lg border bg-background/60 p-3">
                                <div className="text-xs text-muted-foreground">反馈消息数</div>
                                <div className="mt-1 text-sm">{Number(selectedFeedbackResolved?.feedback_message_count ?? 0)}</div>
                              </div>
                              <div className="rounded-lg border bg-background/60 p-3">
                                <div className="text-xs text-muted-foreground">判定置信度</div>
                                <div className="mt-1 text-sm">{Number(selectedFeedbackResolved?.decision_confidence ?? 0).toFixed(2)}</div>
                              </div>
                              <div className="rounded-lg border bg-background/60 p-3">
                                <div className="text-xs text-muted-foreground">回退时间</div>
                                <div className="mt-1 text-sm">{formatDeleteOperationTime(selectedFeedbackResolved?.rolled_back_at)}</div>
                              </div>
                            </div>

                            {selectedFeedbackTaskLoading ? (
                              <div className="rounded-lg border bg-background/60 p-4 text-sm text-muted-foreground">
                                正在加载纠错详情...
                              </div>
                            ) : null}

                            {selectedFeedbackTaskError ? (
                              <Alert variant="destructive">
                                <AlertDescription>{selectedFeedbackTaskError}</AlertDescription>
                              </Alert>
                            ) : null}

                            {selectedFeedbackResolved?.rollback_error ? (
                              <Alert variant="destructive">
                                <AlertDescription>{selectedFeedbackResolved.rollback_error}</AlertDescription>
                              </Alert>
                            ) : null}

                            <div className="grid gap-4 xl:grid-cols-[minmax(0,1.05fr)_minmax(0,0.95fr)]">
                              <div className="rounded-xl border bg-background/70 p-4">
                                <div className="text-sm font-semibold">回退后会发生什么</div>
                                <div className="mt-3 space-y-2 text-sm text-muted-foreground">
                                  <div>会恢复旧关系状态，并撤销本次纠错写入的段落与关系。</div>
                                  <div>会清理旧段落的待复核标记，并重新触发相关 Episode / Profile 修复。</div>
                                  <div>如果你当前只是核对结果，可以先查看下面的详细数据，不必立刻执行回退。</div>
                                </div>
                              </div>
                              <div className="rounded-xl border bg-background/70 p-4">
                                <div className="text-sm font-semibold">处理摘要</div>
                                <div className="mt-3 grid gap-2 text-sm text-muted-foreground">
                                  <div>判定：{formatFeedbackDecision(String(selectedFeedbackResolved?.decision ?? ''))}</div>
                                  <div>任务状态：{formatFeedbackTaskStatus(String(selectedFeedbackResolved?.task_status ?? ''))}</div>
                                  <div>回退状态：{formatFeedbackRollbackStatus(String(selectedFeedbackResolved?.rollback_status ?? 'none'))}</div>
                                  <div>反馈消息数：{Number(selectedFeedbackResolved?.feedback_message_count ?? 0)}</div>
                                </div>
                              </div>
                            </div>

                            <div className="space-y-3">
                              <div className="text-sm font-semibold">详细数据</div>
                              <div className="grid gap-3 xl:grid-cols-2">
                                <details className="rounded-lg border bg-background/70 p-3">
                                  <summary className="cursor-pointer text-sm font-medium">查询快照 JSON</summary>
                                  <pre className="mt-3 max-h-56 overflow-auto text-xs break-words whitespace-pre-wrap">
                                    {JSON.stringify(selectedFeedbackResolved?.query_snapshot ?? {}, null, 2)}
                                  </pre>
                                </details>
                                <details className="rounded-lg border bg-background/70 p-3">
                                  <summary className="cursor-pointer text-sm font-medium">判定结果 JSON</summary>
                                  <pre className="mt-3 max-h-56 overflow-auto text-xs break-words whitespace-pre-wrap">
                                    {JSON.stringify(selectedFeedbackResolved?.decision_payload ?? {}, null, 2)}
                                  </pre>
                                </details>
                                <details className="rounded-lg border bg-background/70 p-3">
                                  <summary className="cursor-pointer text-sm font-medium">回退计划摘要 JSON</summary>
                                  <pre className="mt-3 max-h-64 overflow-auto text-xs break-words whitespace-pre-wrap">
                                    {JSON.stringify(selectedFeedbackResolved?.rollback_plan_summary ?? {}, null, 2)}
                                  </pre>
                                </details>
                                <details className="rounded-lg border bg-background/70 p-3">
                                  <summary className="cursor-pointer text-sm font-medium">回退结果 JSON</summary>
                                  <pre className="mt-3 max-h-64 overflow-auto text-xs break-words whitespace-pre-wrap">
                                    {JSON.stringify(selectedFeedbackResolved?.rollback_result ?? {}, null, 2)}
                                  </pre>
                                </details>
                              </div>
                            </div>

                            <details className="rounded-xl border bg-background/70 p-4">
                              <summary className="cursor-pointer text-sm font-semibold">
                                动作时间线
                              </summary>
                              <div className="mt-4 space-y-2">
                                <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                                  <div className="text-xs text-muted-foreground">
                                    第 {feedbackActionLogPage} / {feedbackActionLogPageCount} 页，每页 {FEEDBACK_ACTION_LOG_PAGE_SIZE} 项
                                  </div>
                                  <Input
                                    value={feedbackActionLogSearch}
                                    onChange={(event) => setFeedbackActionLogSearch(event.target.value)}
                                    placeholder="搜索动作 / 目标哈希 / 预览内容"
                                    className="lg:w-80"
                                  />
                                </div>
                                <ScrollArea className="h-[240px] rounded-lg border bg-background/60">
                                  <div className="space-y-2 p-3">
                                    {pagedFeedbackActionLogs.length > 0 ? pagedFeedbackActionLogs.map((item: MemoryFeedbackActionLogPayload) => (
                                      <div key={`${item.id}:${item.action_type}`} className="rounded-lg border bg-muted/20 p-3">
                                        <div className="flex flex-wrap items-center justify-between gap-2">
                                          <div className="flex flex-wrap items-center gap-2">
                                            <Badge variant="outline">{formatFeedbackActionType(item.action_type)}</Badge>
                                            {item.target_hash ? (
                                              <span className="font-mono text-[11px] break-all text-muted-foreground">{item.target_hash}</span>
                                            ) : null}
                                          </div>
                                          <div className="text-[11px] text-muted-foreground">
                                            {formatDeleteOperationTime(item.created_at)}
                                          </div>
                                        </div>
                                        <div className="mt-2 text-sm break-words">
                                          {describeFeedbackActionLog(item)}
                                        </div>
                                        {item.reason ? (
                                          <div className="mt-2 text-xs text-muted-foreground break-words">
                                            原因：{item.reason}
                                          </div>
                                        ) : null}
                                        {item.before_payload && Object.keys(item.before_payload).length > 0 ? (
                                          <div className="mt-3 rounded-md border bg-background/70 p-2 text-xs break-words">
                                            <span className="font-medium">处理前：</span>
                                            <span className="text-muted-foreground">{summarizeFeedbackActionPayload(item.before_payload)}</span>
                                          </div>
                                        ) : null}
                                        {item.after_payload && Object.keys(item.after_payload).length > 0 ? (
                                          <div className="mt-2 rounded-md border bg-background/70 p-2 text-xs break-words">
                                            <span className="font-medium">处理后：</span>
                                            <span className="text-muted-foreground">{summarizeFeedbackActionPayload(item.after_payload)}</span>
                                          </div>
                                        ) : null}
                                      </div>
                                    )) : (
                                      <div className="rounded-lg border border-dashed bg-muted/20 p-6 text-center text-sm text-muted-foreground">
                                        {selectedFeedbackActionLogs.length > 0 ? '当前筛选条件下没有动作日志' : '当前任务没有动作日志'}
                                      </div>
                                    )}
                                  </div>
                                </ScrollArea>
                                <div className="flex items-center justify-between gap-2">
                                  <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={() => setFeedbackActionLogPage((current) => Math.max(1, current - 1))}
                                    disabled={feedbackActionLogPage <= 1}
                                  >
                                    上一页
                                  </Button>
                                  <div className="text-xs text-muted-foreground">支持按动作类型、目标哈希和摘要检索</div>
                                  <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={() => setFeedbackActionLogPage((current) => Math.min(feedbackActionLogPageCount, current + 1))}
                                    disabled={feedbackActionLogPage >= feedbackActionLogPageCount}
                                  >
                                    下一页
                                  </Button>
                                </div>
                              </div>
                            </details>
                          </div>
                        ) : (
                          <div className="flex min-h-[360px] items-center justify-center rounded-lg border border-dashed bg-background/40 p-6 text-center text-sm text-muted-foreground">
                            当前没有可查看的纠错详情
                          </div>
                        )}
                      </div>
                    </div>

                    <div className="flex items-center justify-between gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setFeedbackPage((current) => Math.max(1, current - 1))}
                        disabled={feedbackPage <= 1}
                      >
                        上一页
                      </Button>
                      <div className="text-xs text-muted-foreground">
                        支持按查询内容、任务状态和回退状态检索
                      </div>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setFeedbackPage((current) => Math.min(feedbackPageCount, current + 1))}
                        disabled={feedbackPage >= feedbackPageCount}
                      >
                        下一页
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              </div>
            </TabsContent>
          </Tabs>
        </div>
      </div>

      <MemoryDeleteDialog
        open={deleteDialogOpen}
        onOpenChange={closeDeleteDialog}
        title={deleteDialogTitle}
        description={deleteDialogDescription}
        preview={deletePreview}
        result={deleteResult}
        loadingPreview={deletePreviewLoading}
        executing={deleteExecuting}
        restoring={deleteRestoring}
        error={deletePreviewError}
        onExecute={() => void executePendingDelete()}
        onRestore={() => void (deleteResult?.operation_id ? restoreDeleteOperation(deleteResult.operation_id) : Promise.resolve())}
      />

      <Dialog open={feedbackRollbackDialogOpen} onOpenChange={setFeedbackRollbackDialogOpen}>
        <DialogContent className="max-w-lg" confirmOnEnter>
          <DialogHeader>
            <DialogTitle>回退本次纠错</DialogTitle>
            <DialogDescription>
              这会恢复旧关系状态、隐藏本次纠错写入的段落，并重新触发 Episode / Profile 的异步修复。
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div className="rounded-lg border bg-muted/20 p-3 text-sm">
              <div className="font-medium break-words">{selectedFeedbackResolved?.query_text || '无查询文本'}</div>
              <div className="mt-1 font-mono text-[11px] break-all text-muted-foreground">
                {selectedFeedbackResolved?.query_tool_id}
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="feedback-rollback-reason">回退原因</Label>
              <Textarea
                id="feedback-rollback-reason"
                value={feedbackRollbackReason}
                onChange={(event) => setFeedbackRollbackReason(event.target.value)}
                placeholder="可选，建议填写本次人工回退原因"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setFeedbackRollbackDialogOpen(false)} disabled={feedbackRollingBack}>
              取消
            </Button>
            <Button onClick={() => void executeFeedbackRollback()} disabled={feedbackRollingBack}>
              {feedbackRollingBack ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  回退中
                </>
              ) : (
                <>
                  <RotateCcw className="mr-2 h-4 w-4" />
                  确认回退
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
