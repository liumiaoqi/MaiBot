/**
 * useImportForm —— 长期记忆「导入表单」领域 hook（schema 化重构版）。
 *
 * 旧实现（881 行）的问题：65 个平铺 useState + 7 个逐字重复的 submit 骨架。
 * 本次重构（目标 ~300 行，接口完全不变——121 字段与旧版逐字一致）：
 * - useImportFormFields(schema)：按 import-mode-schemas 声明一次生成全部表单 state，
 *   替代平铺 useState（含 7 模式 + 路径预检 54 个字段）；
 * - runCreateImport：统一 try → create → error 检查 → onCreated → toast → catch → finally 骨架，
 *   7 个 submit 收敛为 SUBMIT_CONFIGS 配置表（precheck/execute/afterSuccess），
 *   payload 构建器全部外置到 import-payloads.ts（纯函数）；
 * - 保留：settings 服务端默认值 seed（渲染期版本标记模式）、别名联动、resolveImportPath、
 *   dispatcher 语义——行为与旧版等价（golden 测试锁定）。
 *
 * 与 useImportQueue 共享 settings 查询（同 queryKey 由 React Query 去重）。
 */
import { useCallback, useMemo, useState } from 'react'

import { useQuery } from '@tanstack/react-query'

import { toast } from 'sonner'
import {
  createMemoryLpmmConvertImport,
  createMemoryLpmmOpenieImport,
  createMemoryMaibotMigrationImport,
  createMemoryPasteImport,
  createMemoryRawScanImport,
  createMemoryTemporalBackfillImport,
  createMemoryUploadImport,
  getMemoryImportChatTargets,
  getMemoryImportPathAliases,
  getMemoryImportSettings,
  resolveMemoryImportPath,
  type MemoryImportActionPayload,
  type MemoryImportChatTargetPayload,
  type MemoryImportInputMode,
  type MemoryImportSettings,
  type MemoryImportTaskKind,
} from '@/lib/memory-api'

import {
  buildBackfillPayload,
  buildCommonPayload,
  buildConvertPayload,
  buildMaibotMigrationPayload,
  buildOpeniePayload,
  buildPastePayload,
  buildRawScanPayload,
  buildUploadPayload,
} from '../import-payloads'
import {
  ALL_IMPORT_FORM_FIELDS,
  ALIAS_LINK_FIELDS,
  type ImportFieldValue,
  type ModeFieldSchema,
} from '../import-mode-schemas'

export interface UseImportFormOptions {
  /** 导入面板是否激活；非激活时不拉取设置/别名/聊天流 */
  active: boolean
  /** 创建任务成功后回调（由 useImportQueue.afterCreated 提供），刷新队列并选中新任务 */
  onCreated: (taskId: string) => Promise<void>
}

export interface UseImportFormResult {
  importCreateMode: MemoryImportTaskKind
  setImportCreateMode: React.Dispatch<React.SetStateAction<MemoryImportTaskKind>>
  importSettings: MemoryImportSettings
  importChatTargets: MemoryImportChatTargetPayload[]

  importCommonFileConcurrency: string
  setImportCommonFileConcurrency: React.Dispatch<React.SetStateAction<string>>
  importCommonChunkConcurrency: string
  setImportCommonChunkConcurrency: React.Dispatch<React.SetStateAction<string>>
  importCommonNarrativeWindowSize: string
  setImportCommonNarrativeWindowSize: React.Dispatch<React.SetStateAction<string>>
  importCommonNarrativeOverlap: string
  setImportCommonNarrativeOverlap: React.Dispatch<React.SetStateAction<string>>
  importCommonFactualTargetSize: string
  setImportCommonFactualTargetSize: React.Dispatch<React.SetStateAction<string>>
  importCommonLlmEnabled: boolean
  setImportCommonLlmEnabled: React.Dispatch<React.SetStateAction<boolean>>
  importCommonStrategyOverride: string
  setImportCommonStrategyOverride: React.Dispatch<React.SetStateAction<string>>
  importCommonDedupePolicy: string
  setImportCommonDedupePolicy: React.Dispatch<React.SetStateAction<string>>
  importCommonChatLog: boolean
  setImportCommonChatLog: React.Dispatch<React.SetStateAction<boolean>>
  importCommonChatId: string
  setImportCommonChatId: React.Dispatch<React.SetStateAction<string>>
  importCommonChatReferenceTime: string
  setImportCommonChatReferenceTime: React.Dispatch<React.SetStateAction<string>>
  importCommonForce: boolean
  setImportCommonForce: React.Dispatch<React.SetStateAction<boolean>>
  importCommonClearManifest: boolean
  setImportCommonClearManifest: React.Dispatch<React.SetStateAction<boolean>>

  uploadInputMode: MemoryImportInputMode
  setUploadInputMode: React.Dispatch<React.SetStateAction<MemoryImportInputMode>>
  uploadFiles: File[]
  setUploadFiles: React.Dispatch<React.SetStateAction<File[]>>

  pasteName: string
  setPasteName: React.Dispatch<React.SetStateAction<string>>
  pasteMode: MemoryImportInputMode
  setPasteMode: React.Dispatch<React.SetStateAction<MemoryImportInputMode>>
  pasteContent: string
  setPasteContent: React.Dispatch<React.SetStateAction<string>>

  rawAlias: string
  setRawAlias: React.Dispatch<React.SetStateAction<string>>
  rawInputMode: MemoryImportInputMode
  setRawInputMode: React.Dispatch<React.SetStateAction<MemoryImportInputMode>>
  rawRelativePath: string
  setRawRelativePath: React.Dispatch<React.SetStateAction<string>>
  rawGlob: string
  setRawGlob: React.Dispatch<React.SetStateAction<string>>
  rawRecursive: boolean
  setRawRecursive: React.Dispatch<React.SetStateAction<boolean>>

  openieAlias: string
  setOpenieAlias: React.Dispatch<React.SetStateAction<string>>
  openieRelativePath: string
  setOpenieRelativePath: React.Dispatch<React.SetStateAction<string>>
  openieIncludeAllJson: boolean
  setOpenieIncludeAllJson: React.Dispatch<React.SetStateAction<boolean>>

  convertAlias: string
  setConvertAlias: React.Dispatch<React.SetStateAction<string>>
  convertTargetAlias: string
  setConvertTargetAlias: React.Dispatch<React.SetStateAction<string>>
  convertRelativePath: string
  setConvertRelativePath: React.Dispatch<React.SetStateAction<string>>
  convertTargetRelativePath: string
  setConvertTargetRelativePath: React.Dispatch<React.SetStateAction<string>>
  convertDimension: string
  setConvertDimension: React.Dispatch<React.SetStateAction<string>>
  convertBatchSize: string
  setConvertBatchSize: React.Dispatch<React.SetStateAction<string>>

  backfillAlias: string
  setBackfillAlias: React.Dispatch<React.SetStateAction<string>>
  backfillLimit: string
  setBackfillLimit: React.Dispatch<React.SetStateAction<string>>
  backfillRelativePath: string
  setBackfillRelativePath: React.Dispatch<React.SetStateAction<string>>
  backfillDryRun: boolean
  setBackfillDryRun: React.Dispatch<React.SetStateAction<boolean>>
  backfillNoCreatedFallback: boolean
  setBackfillNoCreatedFallback: React.Dispatch<React.SetStateAction<boolean>>

  maibotSourceDb: string
  setMaibotSourceDb: React.Dispatch<React.SetStateAction<string>>
  maibotTimeFrom: string
  setMaibotTimeFrom: React.Dispatch<React.SetStateAction<string>>
  maibotTimeTo: string
  setMaibotTimeTo: React.Dispatch<React.SetStateAction<string>>
  maibotStartId: string
  setMaibotStartId: React.Dispatch<React.SetStateAction<string>>
  maibotEndId: string
  setMaibotEndId: React.Dispatch<React.SetStateAction<string>>
  maibotStreamIds: string
  setMaibotStreamIds: React.Dispatch<React.SetStateAction<string>>
  maibotGroupIds: string
  setMaibotGroupIds: React.Dispatch<React.SetStateAction<string>>
  maibotUserIds: string
  setMaibotUserIds: React.Dispatch<React.SetStateAction<string>>
  maibotReadBatchSize: string
  setMaibotReadBatchSize: React.Dispatch<React.SetStateAction<string>>
  maibotCommitWindowRows: string
  setMaibotCommitWindowRows: React.Dispatch<React.SetStateAction<string>>
  maibotEmbedWorkers: string
  setMaibotEmbedWorkers: React.Dispatch<React.SetStateAction<string>>
  maibotNoResume: boolean
  setMaibotNoResume: React.Dispatch<React.SetStateAction<boolean>>
  maibotResetState: boolean
  setMaibotResetState: React.Dispatch<React.SetStateAction<boolean>>
  maibotDryRun: boolean
  setMaibotDryRun: React.Dispatch<React.SetStateAction<boolean>>
  maibotVerifyOnly: boolean
  setMaibotVerifyOnly: React.Dispatch<React.SetStateAction<boolean>>

  submitImportByMode: () => Promise<void>
  creatingImport: boolean
  /** 构建公共导入参数载荷，供队列重试（retry overrides）复用当前表单参数 */
  buildCommonImportPayload: () => Record<string, unknown>

  pathResolveAlias: string
  setPathResolveAlias: React.Dispatch<React.SetStateAction<string>>
  importAliasKeys: string[]
  pathResolveRelativePath: string
  setPathResolveRelativePath: React.Dispatch<React.SetStateAction<string>>
  pathResolveMustExist: boolean
  setPathResolveMustExist: React.Dispatch<React.SetStateAction<boolean>>
  resolveImportPath: () => Promise<void>
  resolvingPath: boolean
  pathResolveOutput: string
}

export interface UseImportFormFieldsResult {
  values: Record<string, ImportFieldValue>
  setValue: (key: string, value: ImportFieldValue) => void
  setValues: (updates: Record<string, ImportFieldValue>) => void
}

/**
 * useImportFormFields(schema) —— 按字段 schema 生成表单 state。
 * 替代旧版平铺的 65 个 useState：单一 values 对象 + setValue/setValues，
 * 默认值来自 schema.defaultValue（同名值写入返回原引用，避免无谓重渲染）。
 */
export function useImportFormFields(schema: readonly ModeFieldSchema[]): UseImportFormFieldsResult {
  const initialValues = useMemo(() => {
    const map: Record<string, ImportFieldValue> = {}
    for (const field of schema) {
      map[field.key] = field.defaultValue
    }
    return map
  }, [schema])

  const [values, setValuesState] = useState<Record<string, ImportFieldValue>>(initialValues)

  const setValue = useCallback((key: string, value: ImportFieldValue) => {
    setValuesState((current) => (current[key] === value ? current : { ...current, [key]: value }))
  }, [])

  const setValues = useCallback((updates: Record<string, ImportFieldValue>) => {
    setValuesState((current) => {
      let changed = false
      const next = { ...current }
      for (const key of Object.keys(updates)) {
        if (next[key] !== updates[key]) {
          next[key] = updates[key]
          changed = true
        }
      }
      return changed ? next : current
    })
  }, [])

  return { values, setValue, setValues }
}

interface SubmitImportConfig {
  /** API 报错时的兜底文案 */
  failText: string
  /** 提交前检查：返回错误文案则中止（不进入 creating 流程，与旧 upload/paste 前置检查一致） */
  precheck?: (values: Record<string, ImportFieldValue>, files: File[]) => string | null
  execute: (values: Record<string, ImportFieldValue>, files: File[]) => Promise<MemoryImportActionPayload>
  /** 创建成功后、刷新队列前的本地清理（upload 清文件、paste 清内容） */
  afterSuccess?: (
    values: Record<string, ImportFieldValue>,
    setValue: (key: string, value: ImportFieldValue) => void,
    files: File[],
    setFiles: React.Dispatch<React.SetStateAction<File[]>>,
  ) => void
}

const SUBMIT_CONFIGS: Record<MemoryImportTaskKind, SubmitImportConfig> = {
  upload: {
    failText: '创建上传导入任务失败',
    precheck: (_values, files) => (files.length <= 0 ? '至少选择一个 txt/md/json 文件后再提交' : null),
    execute: (values, files) => createMemoryUploadImport(files, buildUploadPayload(values)),
    afterSuccess: (_values, _setValue, _files, setFiles) => setFiles([]),
  },
  paste: {
    failText: '创建粘贴导入任务失败',
    precheck: (values) => (String(values.pasteContent ?? '').trim() ? null : '请填写导入内容后再提交'),
    execute: (values) => createMemoryPasteImport(buildPastePayload(values)),
    afterSuccess: (_values, setValue) => {
      setValue('pasteContent', '')
      setValue('pasteName', '')
    },
  },
  raw_scan: {
    failText: '创建本地扫描任务失败',
    execute: (values) => createMemoryRawScanImport(buildRawScanPayload(values)),
  },
  lpmm_openie: {
    failText: '创建 LPMM OpenIE 任务失败',
    execute: (values) => createMemoryLpmmOpenieImport(buildOpeniePayload(values)),
  },
  lpmm_convert: {
    failText: '创建 LPMM 转换任务失败',
    execute: (values) => createMemoryLpmmConvertImport(buildConvertPayload(values)),
  },
  temporal_backfill: {
    failText: '创建时序回填任务失败',
    execute: (values) => createMemoryTemporalBackfillImport(buildBackfillPayload(values)),
  },
  maibot_migration: {
    failText: '创建 MaiBot 迁移任务失败',
    // 校验在 buildMaibotMigrationPayload 内抛 Error，由统一骨架 catch 后 toast 呈现
    execute: (values) => createMemoryMaibotMigrationImport(buildMaibotMigrationPayload(values)),
  },
}

/** settings 服务端默认值 seed 规则（渲染期版本标记模式，等价旧实现） */
const SETTINGS_SEED_RULES: Array<{
  key: string
  settingsKey: keyof MemoryImportSettings
  mode: 'equals-default' | 'empty'
}> = [
  { key: 'importCommonFileConcurrency', settingsKey: 'default_file_concurrency', mode: 'equals-default' },
  { key: 'importCommonChunkConcurrency', settingsKey: 'default_chunk_concurrency', mode: 'equals-default' },
  { key: 'importCommonNarrativeWindowSize', settingsKey: 'default_narrative_window_size', mode: 'equals-default' },
  { key: 'importCommonNarrativeOverlap', settingsKey: 'default_narrative_overlap', mode: 'equals-default' },
  { key: 'importCommonFactualTargetSize', settingsKey: 'default_factual_target_size', mode: 'equals-default' },
  { key: 'maibotSourceDb', settingsKey: 'maibot_source_db_default', mode: 'empty' },
]

const SCHEMA_DEFAULT_BY_KEY = new Map(ALL_IMPORT_FORM_FIELDS.map((field) => [field.key, String(field.defaultValue)]))

/** 按 schema 键生成 { key: value, setKey: setter } 字段对，暴露为 UseImportFormResult 的命名成员 */
function buildFieldProps(
  values: Record<string, ImportFieldValue>,
  setValue: (key: string, value: ImportFieldValue) => void,
): Record<string, unknown> {
  const props: Record<string, unknown> = {}
  for (const key of Object.keys(values)) {
    props[key] = values[key]
    props[`set${key.charAt(0).toUpperCase()}${key.slice(1)}`] = (value: ImportFieldValue) => setValue(key, value)
  }
  return props
}

export function useImportForm({ active, onCreated }: UseImportFormOptions): UseImportFormResult {
  const [importCreateMode, setImportCreateMode] = useState<MemoryImportTaskKind>('upload')
  const [creatingImport, setCreatingImport] = useState(false)
  // uploadFiles 是 File[] 特殊输入，不进 schema（见 import-mode-schemas 设计边界）
  const [uploadFiles, setUploadFiles] = useState<File[]>([])
  const [pathResolveOutput, setPathResolveOutput] = useState('')
  const [resolvingPath, setResolvingPath] = useState(false)

  const { values, setValue, setValues } = useImportFormFields(ALL_IMPORT_FORM_FIELDS)

  // 导入设置 / 路径别名 / 聊天流：仅在面板激活时拉取；settings 与 useImportQueue 共享查询缓存
  const settingsQuery = useQuery({
    queryKey: ['memory-import', 'settings'],
    queryFn: () => getMemoryImportSettings(),
    enabled: active,
  })
  const pathAliasesQuery = useQuery({
    queryKey: ['memory-import', 'path-aliases'],
    queryFn: () => getMemoryImportPathAliases(),
    enabled: active,
  })
  const chatTargetsQuery = useQuery({
    queryKey: ['memory-import', 'chat-targets'],
    queryFn: () => getMemoryImportChatTargets(),
    enabled: active,
  })

  const importSettings: MemoryImportSettings = settingsQuery.data?.settings ?? {}
  const importPathAliases = useMemo(
    () => pathAliasesQuery.data?.path_aliases ?? {},
    [pathAliasesQuery.data?.path_aliases],
  )
  const importChatTargets = useMemo(
    () => chatTargetsQuery.data?.data ?? [],
    [chatTargetsQuery.data?.data],
  )
  const importAliasKeys = useMemo(
    () => Object.keys(importPathAliases).sort((left, right) => left.localeCompare(right)),
    [importPathAliases],
  )

  // 服务端默认值 seed：settings 首次到达时按默认值回填通用参数与 maibot 源库一次。
  // 用「渲染期版本标记」模式（React 官方推荐）替代 effect 内 setState，避免级联渲染告警。
  const settingsVersion = settingsQuery.data !== undefined ? String(settingsQuery.dataUpdatedAt) : null
  const [seededSettingsVersion, setSeededSettingsVersion] = useState<string | null>(null)
  if (settingsVersion !== null && settingsVersion !== seededSettingsVersion) {
    setSeededSettingsVersion(settingsVersion)
    const updates: Record<string, ImportFieldValue> = {}
    for (const rule of SETTINGS_SEED_RULES) {
      const raw = importSettings[rule.settingsKey]
      const seedValue = raw === undefined || raw === null ? '' : String(raw).trim()
      if (!seedValue) {
        continue
      }
      const current = String(values[rule.key] ?? '')
      const shouldSeed = rule.mode === 'empty' ? !current.trim() : current === SCHEMA_DEFAULT_BY_KEY.get(rule.key)
      if (shouldSeed) {
        updates[rule.key] = seedValue
      }
    }
    if (Object.keys(updates).length > 0) {
      setValues(updates)
    }
  }

  // 别名联动：别名到达后，各模式 alias 字段为空或不在可用列表中时自动选第一个可用别名。
  // 同样用「渲染期版本标记」模式，避免 effect 内 setState 级联。
  const aliasVersion = importAliasKeys.length > 0 ? importAliasKeys.join('|') : null
  const [linkedAliasVersion, setLinkedAliasVersion] = useState<string | null>(null)
  if (aliasVersion !== null && aliasVersion !== linkedAliasVersion) {
    setLinkedAliasVersion(aliasVersion)
    const pickAlias = (current: string, preferred: string): string => {
      if (current && importAliasKeys.includes(current)) {
        return current
      }
      if (importAliasKeys.includes(preferred)) {
        return preferred
      }
      return importAliasKeys[0]
    }
    const updates: Record<string, ImportFieldValue> = {}
    for (const field of ALIAS_LINK_FIELDS) {
      const current = String(values[field.key] ?? '')
      const next = pickAlias(current, String(field.defaultValue))
      if (next !== current) {
        updates[field.key] = next
      }
    }
    if (Object.keys(updates).length > 0) {
      setValues(updates)
    }
  }

  const buildCommonImportPayload = useCallback(
    () => buildCommonPayload(values),
    [values],
  )

  // 统一提交骨架：try → create → error 检查 → 清理 → onCreated → toast.success → catch → finally
  const runCreateImport = useCallback(
    async (config: SubmitImportConfig): Promise<void> => {
      try {
        setCreatingImport(true)
        const result = await config.execute(values, uploadFiles)
        if (result.error) {
          throw new Error(result.error || config.failText)
        }
        const taskId = String(result.task?.task_id ?? '')
        config.afterSuccess?.(values, setValue, uploadFiles, setUploadFiles)
        await onCreated(taskId)
        toast.success(taskId ? `任务 ${taskId.slice(0, 12)} 已加入导入队列` : '导入任务已加入队列')
      } catch (error) {
        const message = error instanceof Error ? error.message : config.failText
        toast.error(message)
      } finally {
        setCreatingImport(false)
      }
    },
    [onCreated, setValue, uploadFiles, values],
  )

  const submitImportByMode = useCallback(async () => {
    if (creatingImport) {
      return
    }
    const config = SUBMIT_CONFIGS[importCreateMode]
    const precheckError = config.precheck?.(values, uploadFiles) ?? null
    if (precheckError) {
      toast.error(precheckError)
      return
    }
    await runCreateImport(config)
  }, [creatingImport, importCreateMode, runCreateImport, uploadFiles, values])

  const resolveImportPath = useCallback(async () => {
    if (!String(values.pathResolveAlias ?? '').trim()) {
      return
    }
    try {
      setResolvingPath(true)
      const payload = await resolveMemoryImportPath({
        alias: String(values.pathResolveAlias ?? ''),
        relative_path: String(values.pathResolveRelativePath ?? ''),
        must_exist: Boolean(values.pathResolveMustExist),
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
  }, [values.pathResolveAlias, values.pathResolveMustExist, values.pathResolveRelativePath])

  return {
    importCreateMode,
    setImportCreateMode,
    importSettings,
    importChatTargets,
    uploadFiles,
    setUploadFiles,
    submitImportByMode,
    creatingImport,
    buildCommonImportPayload,
    importAliasKeys,
    resolveImportPath,
    resolvingPath,
    pathResolveOutput,
    ...buildFieldProps(values, setValue),
  } as UseImportFormResult
}
