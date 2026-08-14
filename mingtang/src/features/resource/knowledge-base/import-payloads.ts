/**
 * import-payloads —— 7 种导入模式的 payload 构建器（纯函数，独立于 React）。
 *
 * 从 useImportForm 的 7 个 submit 中提取：每个构建器接收 schema 字段值（Record），
 * 返回 createMemory*Import 的请求体。校验规则与旧实现逐字一致：
 * - 公共参数（upload/paste/raw_scan/lpmm_openie 携带；lpmm_convert/temporal_backfill/
 *   maibot_migration 不带——已固化的行为，golden 测试锁定）；
 * - maibot_migration 单字段校验走 schema.validate（validateSchemaFields），
 *   跨字段校验（时间倒挂 / ID 倒挂）留在这里，报错文案与旧实现一致。
 */
import type { ImportFieldValue, ModeFieldSchema } from './import-mode-schemas'
import { IMPORT_MODE_SCHEMAS } from './import-mode-schemas'
import {
  parseCommaSeparatedList,
  parseOptionalNonNegativeInt,
  parseOptionalPositiveInt,
} from './utils'

const DATE_TIME_LOCAL_PATTERN = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d{1,3})?)?$/
const POSITIVE_INTEGER_PATTERN = /^[1-9]\d*$/

/** 逐字段跑 schema.validate，第一个错误文案即返回（schema 声明顺序 = 校验顺序） */
export function validateSchemaFields(
  schema: readonly ModeFieldSchema[],
  values: Readonly<Record<string, ImportFieldValue>>,
): string | null {
  for (const field of schema) {
    if (!field.validate) {
      continue
    }
    const raw = values[field.key]
    const error = field.validate(typeof raw === 'string' ? raw : String(raw ?? ''))
    if (error) {
      return error
    }
  }
  return null
}

/** 正整数解析（maibot 专属严格版：非空时非正整数直接抛错） */
function parseMaibotPositiveInt(input: string, fieldName: string): number | undefined {
  const value = input.trim()
  if (!value) {
    return undefined
  }
  if (!POSITIVE_INTEGER_PATTERN.test(value)) {
    throw new Error(`${fieldName} 必须填写正整数`)
  }
  const parsed = Number(value)
  if (!Number.isSafeInteger(parsed)) {
    throw new Error(`${fieldName} 超过可支持的整数范围`)
  }
  return parsed
}

/** datetime-local 解析为时间戳（maibot 时间倒挂比较用；格式错误抛错） */
function getMaibotDateTimeLocalTimestamp(input: string, fieldName: string): number | undefined {
  const value = input.trim()
  if (!value) {
    return undefined
  }
  if (!DATE_TIME_LOCAL_PATTERN.test(value)) {
    throw new Error(`${fieldName}格式无效，请使用时间选择器填写`)
  }
  const timestamp = new Date(value).getTime()
  if (!Number.isFinite(timestamp)) {
    throw new Error(`${fieldName}不是有效时间`)
  }
  return timestamp
}

/** datetime-local 转 ISO 字符串（API 请求用；格式错误抛错） */
function formatMaibotDateTimeLocalForApi(input: string, fieldName: string): string | undefined {
  const value = input.trim()
  if (!value) {
    return undefined
  }
  if (!DATE_TIME_LOCAL_PATTERN.test(value)) {
    throw new Error(`${fieldName}格式无效，请使用时间选择器填写`)
  }
  const date = new Date(value)
  if (!Number.isFinite(date.getTime())) {
    throw new Error(`${fieldName}不是有效时间`)
  }
  return date.toISOString()
}

function readString(values: Readonly<Record<string, ImportFieldValue>>, key: string): string {
  return String(values[key] ?? '')
}

function readBoolean(values: Readonly<Record<string, ImportFieldValue>>, key: string): boolean {
  return Boolean(values[key])
}

/** 公共导入参数（重试 overrides 与 4 个携带公共参数的模式共用） */
export function buildCommonPayload(values: Readonly<Record<string, ImportFieldValue>>): Record<string, unknown> {
  const chatId = readString(values, 'importCommonChatId').trim()
  const payload: Record<string, unknown> = {
    llm_enabled: readBoolean(values, 'importCommonLlmEnabled'),
    strategy_override: readString(values, 'importCommonStrategyOverride'),
    dedupe_policy: readString(values, 'importCommonDedupePolicy'),
    chat_log: readBoolean(values, 'importCommonChatLog'),
    force: readBoolean(values, 'importCommonForce'),
    clear_manifest: readBoolean(values, 'importCommonClearManifest'),
  }

  const fileConcurrency = parseOptionalPositiveInt(readString(values, 'importCommonFileConcurrency'))
  const chunkConcurrency = parseOptionalPositiveInt(readString(values, 'importCommonChunkConcurrency'))
  const narrativeWindowSize = parseOptionalPositiveInt(readString(values, 'importCommonNarrativeWindowSize'))
  const narrativeOverlap = parseOptionalNonNegativeInt(readString(values, 'importCommonNarrativeOverlap'))
  const factualTargetSize = parseOptionalPositiveInt(readString(values, 'importCommonFactualTargetSize'))
  if (fileConcurrency !== undefined) {
    payload.file_concurrency = fileConcurrency
  }
  if (chunkConcurrency !== undefined) {
    payload.chunk_concurrency = chunkConcurrency
  }
  if (narrativeWindowSize !== undefined) {
    payload.narrative_window_size = narrativeWindowSize
  }
  if (narrativeOverlap !== undefined) {
    payload.narrative_overlap = narrativeOverlap
  }
  if (factualTargetSize !== undefined) {
    payload.factual_target_size = factualTargetSize
  }
  if (readString(values, 'importCommonChatReferenceTime').trim()) {
    payload.chat_reference_time = readString(values, 'importCommonChatReferenceTime').trim()
  }
  if (chatId) {
    payload.chat_id = chatId
  }
  return payload
}

export function buildUploadPayload(values: Readonly<Record<string, ImportFieldValue>>): Record<string, unknown> {
  return {
    ...buildCommonPayload(values),
    input_mode: readString(values, 'uploadInputMode'),
  }
}

export function buildPastePayload(values: Readonly<Record<string, ImportFieldValue>>): Record<string, unknown> {
  return {
    ...buildCommonPayload(values),
    name: readString(values, 'pasteName') || undefined,
    content: readString(values, 'pasteContent'),
    input_mode: readString(values, 'pasteMode'),
  }
}

export function buildRawScanPayload(values: Readonly<Record<string, ImportFieldValue>>): Record<string, unknown> {
  return {
    ...buildCommonPayload(values),
    alias: readString(values, 'rawAlias'),
    relative_path: readString(values, 'rawRelativePath'),
    glob: readString(values, 'rawGlob'),
    recursive: readBoolean(values, 'rawRecursive'),
    input_mode: readString(values, 'rawInputMode'),
  }
}

export function buildOpeniePayload(values: Readonly<Record<string, ImportFieldValue>>): Record<string, unknown> {
  return {
    ...buildCommonPayload(values),
    alias: readString(values, 'openieAlias'),
    relative_path: readString(values, 'openieRelativePath'),
    include_all_json: readBoolean(values, 'openieIncludeAllJson'),
  }
}

/** LPMM 转换：不带公共参数（已固化行为） */
export function buildConvertPayload(values: Readonly<Record<string, ImportFieldValue>>): Record<string, unknown> {
  return {
    alias: readString(values, 'convertAlias'),
    relative_path: readString(values, 'convertRelativePath'),
    target_alias: readString(values, 'convertTargetAlias'),
    target_relative_path: readString(values, 'convertTargetRelativePath'),
    dimension: parseOptionalPositiveInt(readString(values, 'convertDimension')),
    batch_size: parseOptionalPositiveInt(readString(values, 'convertBatchSize')),
  }
}

/** 时序回填：不带公共参数（已固化行为） */
export function buildBackfillPayload(values: Readonly<Record<string, ImportFieldValue>>): Record<string, unknown> {
  return {
    alias: readString(values, 'backfillAlias'),
    relative_path: readString(values, 'backfillRelativePath'),
    limit: parseOptionalPositiveInt(readString(values, 'backfillLimit')),
    dry_run: readBoolean(values, 'backfillDryRun'),
    no_created_fallback: readBoolean(values, 'backfillNoCreatedFallback'),
  }
}

/** MaiBot 迁移：不带公共参数；校验失败抛 Error（submit 骨架统一 toast 呈现） */
export function buildMaibotMigrationPayload(
  values: Readonly<Record<string, ImportFieldValue>>,
): Record<string, unknown> {
  const validationError = validateSchemaFields(IMPORT_MODE_SCHEMAS.maibot_migration, values)
  if (validationError) {
    throw new Error(validationError)
  }

  const timeFrom = getMaibotDateTimeLocalTimestamp(readString(values, 'maibotTimeFrom'), '起始时间')
  const timeTo = getMaibotDateTimeLocalTimestamp(readString(values, 'maibotTimeTo'), '结束时间')
  if (timeFrom !== undefined && timeTo !== undefined && timeFrom > timeTo) {
    throw new Error('起始时间不能晚于结束时间')
  }
  const startId = parseMaibotPositiveInt(readString(values, 'maibotStartId'), '起始 ID')
  const endId = parseMaibotPositiveInt(readString(values, 'maibotEndId'), '结束 ID')
  if (startId !== undefined && endId !== undefined && startId > endId) {
    throw new Error('起始 ID 不能大于结束 ID')
  }

  return {
    source_db: readString(values, 'maibotSourceDb').trim(),
    time_from: formatMaibotDateTimeLocalForApi(readString(values, 'maibotTimeFrom'), '起始时间'),
    time_to: formatMaibotDateTimeLocalForApi(readString(values, 'maibotTimeTo'), '结束时间'),
    start_id: startId,
    end_id: endId,
    stream_ids: parseCommaSeparatedList(readString(values, 'maibotStreamIds')),
    group_ids: parseCommaSeparatedList(readString(values, 'maibotGroupIds')),
    user_ids: parseCommaSeparatedList(readString(values, 'maibotUserIds')),
    read_batch_size: parseMaibotPositiveInt(readString(values, 'maibotReadBatchSize'), '读取批大小'),
    commit_window_rows: parseMaibotPositiveInt(readString(values, 'maibotCommitWindowRows'), '提交窗口行数'),
    embed_workers: parseMaibotPositiveInt(readString(values, 'maibotEmbedWorkers'), '向量线程数'),
    no_resume: readBoolean(values, 'maibotNoResume'),
    reset_state: readBoolean(values, 'maibotResetState'),
    dry_run: readBoolean(values, 'maibotDryRun'),
    verify_only: readBoolean(values, 'maibotVerifyOnly'),
  }
}
