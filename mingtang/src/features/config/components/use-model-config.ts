/**
 * useModelConfig —— model 域核心领域 hook
 *
 * 三份草稿（providers/models/tasks）+ CRUD + 搜索分页 + 批量 + 连接测试 + 级联删除 + 状态
 * 页面只留纯 UI 态（关注点分离）
 */
import { useState, useMemo, useCallback } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ConfigRevisionConflictError,
  getModelConfig,
  mutateConfig,
  readConfigPaths,
  testProviderConnection,
  testModelCapability,
  type ConfigSecretMarker,
  type TestConnectionResult,
  type ModelTestResult,
} from '@/lib/config-api'
import { diffToMutateOps } from '../seam/config-adapter'
import { isSecretMarker } from '../seam/config-paths'
import { providerSecretPath, secretStateOf, type SecretState } from '../seam/secret-state'

// === 类型定义 ===

export interface ProviderConfig {
  name: string
  base_url: string
  /**
   * 密钥**明文**草稿位（2 段接缝迁移后的语义）。
   *
   * - 从服务端加载时**被摘掉**（见 `withoutSecretPlaintext`）：旧读端点会把明文交给浏览器，
   *   但只要它留在草稿里，浏览器内存就多存一份密钥，而**三态展示根本不需要明文**。
   * - 只有用户输入新值时它才存在；写路径把该明文发出去 = **替换**这份密钥。
   * - `undefined` = 未触碰（**不等于"清空"**）：未触碰的密钥一个 op 都不发，服务端那份原样留着。
   */
  api_key?: string
  client_type?: string
  [key: string]: unknown
}

export interface ModelInfo {
  name: string
  api_provider: string
  model_identifier: string
  [key: string]: unknown
}

export interface TaskConfig {
  models: string[]
  temperature?: number
  max_tokens?: number
  model_selection_strategy?: string
  [key: string]: unknown
}

export type ModelTaskConfig = Record<string, TaskConfig>

// === 接缝（2 段写路径）用的小工具 ===

/** 深拷贝草稿——基线必须与草稿彻底脱钩（共享引用会让"没变"也看起来变了） */
function cloneDraft(draft: Record<string, unknown>): Record<string, unknown> {
  return structuredClone(draft) as Record<string, unknown>
}

/**
 * 摘掉提供商草稿里的密钥明文（语义见 `ProviderConfig.api_key`）。
 *
 * ⚠️ **摘掉 ≠ 清空**：草稿里没有这个键 = "用户没碰过" ⇒ 写路径不为它发任何 op；
 * 若改成写空串，反而会把服务端那份密钥**抹掉**——这正是"只发改动的点"要防住的事。
 */
function withoutSecretPlaintext(provider: ProviderConfig): ProviderConfig {
  const next = { ...provider }
  delete next.api_key
  return next
}

export interface UseModelConfigReturn {
  // 三份草稿
  providers: ProviderConfig[]
  models: ModelInfo[]
  taskConfig: ModelTaskConfig

  // 状态
  isLoading: boolean
  isError: boolean
  error: unknown
  isSaving: boolean
  hasUnsavedChanges: boolean

  // CRUD——厂商
  addProvider: (provider: ProviderConfig) => void
  updateProvider: (index: number, provider: ProviderConfig) => void
  deleteProvider: (index: number) => void
  cascadeDeleteProvider: (index: number) => void

  // CRUD——模型
  addModel: (model: ModelInfo) => void
  updateModel: (index: number, model: ModelInfo) => void
  deleteModel: (index: number) => void

  // CRUD——任务
  updateTask: (taskName: string, config: TaskConfig) => void

  // 搜索分页
  searchQuery: string
  setSearchQuery: (query: string) => void
  filteredProviders: ProviderConfig[]
  filteredModels: ModelInfo[]

  // 批量
  selectedProviderIndices: Set<number>
  selectedModelIndices: Set<number>
  toggleProviderSelection: (index: number) => void
  toggleModelSelection: (index: number) => void
  batchDeleteProviders: () => void
  batchDeleteModels: () => void

  // 连接测试
  testingProviders: Set<string>
  testResults: Map<string, TestConnectionResult>
  testProvider: (providerName: string) => Promise<void>
  testingModels: Set<string>
  modelTestResults: Map<string, ModelTestResult>
  testModel: (modelName: string) => Promise<void>

  // 保存
  saveConfig: () => Promise<void>
  resetDrafts: () => void

  // 接缝（2 段写路径）
  /** 读到的命名空间版本号（乐观锁前置条件）；`null` = 还没读到 */
  seamRevision: number | null
  /** 409 冲突（**未写成功**）——UI 要提示"配置已被别处修改"并给「重新加载」 */
  conflict: ConfigRevisionConflictError | null
  /** 非冲突类保存失败的可读文案（含后端**认领被拒**的原文，不吞） */
  saveError: string | null
  /** 保存成功后的后端文案 */
  saveMessage: string | null
  /** 每个提供商行的密钥三态（与 `providers` 同序） */
  providerSecretStates: SecretState[]
  /** 显式重新加载（用户点「重新加载」才走）——重放是**用户动作**，不是自动重试 */
  reloadFromServer: () => Promise<void>
}

// === Hook 实现 ===

export function useModelConfig(): UseModelConfigReturn {
  const queryClient = useQueryClient()

  // 服务端数据加载
  const { data: configData, isLoading, isError, error } = useQuery({
    queryKey: ['api', 'modelConfig'],
    queryFn: getModelConfig,
  })

  // 2 段接缝读——一次拿到两样旧端点给不了的东西：
  // ① `revision`（写时的乐观锁前置条件）② 秘密**三态标记**（旧端点只回明文，没有"未配置"这一态）
  const { data: seamSnapshot } = useQuery({
    queryKey: ['api', 'modelConfigSeam'],
    queryFn: () => readConfigPaths({ namespace: 'model' }),
  })

  // 三份草稿
  const [providers, setProviders] = useState<ProviderConfig[]>([])
  const [models, setModels] = useState<ModelInfo[]>([])
  const [taskConfig, setTaskConfig] = useState<ModelTaskConfig>({})

  // 接缝状态
  const [seamRevision, setSeamRevision] = useState<number | null>(null)
  const [baseline, setBaseline] = useState<Record<string, unknown> | null>(null)
  const [conflict, setConflict] = useState<ConfigRevisionConflictError | null>(null)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [saveMessage, setSaveMessage] = useState<string | null>(null)

  // 状态
  const [isSaving, setIsSaving] = useState(false)
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false)

  // 搜索
  const [searchQuery, setSearchQuery] = useState('')

  // 批量选择
  const [selectedProviderIndices, setSelectedProviderIndices] = useState<Set<number>>(new Set())
  const [selectedModelIndices, setSelectedModelIndices] = useState<Set<number>>(new Set())

  // 连接测试
  const [testingProviders, setTestingProviders] = useState<Set<string>>(new Set())
  const [testResults, setTestResults] = useState<Map<string, TestConnectionResult>>(new Map())
  const [testingModels, setTestingModels] = useState<Set<string>>(new Set())
  const [modelTestResults, setModelTestResults] = useState<Map<string, ModelTestResult>>(new Map())

  // 从服务端数据初始化草稿——渲染期调整模式（React 官方——替代 effect 里 setState）
  const [prevConfigData, setPrevConfigData] = useState(configData)
  if (configData !== prevConfigData) {
    setPrevConfigData(configData)
    if (configData) {
      const rawProviders = ((configData.api_providers ?? []) as ProviderConfig[]).map(
        withoutSecretPlaintext,
      )
      const rawModels = (configData.models ?? []) as ModelInfo[]
      const rawTasks = (configData.model_task_config ?? {}) as ModelTaskConfig
      setProviders(rawProviders)
      setModels(rawModels)
      setTaskConfig(rawTasks)
      // 基线 = 与服务端一致的"未改动"快照：写的时候拿它做差分（只发改动的点）。
      // 必须**深拷贝**：草稿后续是不可变更新，但嵌套对象可能与基线共享引用。
      setBaseline(
        cloneDraft({ api_providers: rawProviders, models: rawModels, model_task_config: rawTasks }),
      )
      setHasUnsavedChanges(false)
    }
  }

  // 接缝读回来时记住 revision——写的时候**原样带回**（乐观锁的前置条件）
  const [prevSeamSnapshot, setPrevSeamSnapshot] = useState(seamSnapshot)
  if (seamSnapshot !== prevSeamSnapshot) {
    setPrevSeamSnapshot(seamSnapshot)
    if (seamSnapshot) {
      setSeamRevision(seamSnapshot.revision)
    }
  }

  /** 秘密三态：`path → 标记`（来自接缝读；旧端点没有"未配置"这一态） */
  const secretMarkers = useMemo(() => {
    const markerByPath = new Map<string, ConfigSecretMarker>()
    for (const entry of seamSnapshot?.entries ?? []) {
      if (isSecretMarker(entry.value)) {
        markerByPath.set(entry.path, entry.value)
      }
    }
    return markerByPath
  }, [seamSnapshot])

  /** 每个提供商行的密钥三态（与 `providers` 同序）——UI 必须把三态渲染得**不一样** */
  const providerSecretStates = useMemo(
    () => providers.map((_, index) => secretStateOf(secretMarkers.get(providerSecretPath(index)))),
    [providers, secretMarkers],
  )

  // 搜索过滤
  const filteredProviders = useMemo(() => {
    if (!searchQuery.trim()) return providers
    const q = searchQuery.toLowerCase()
    return providers.filter((p) => p.name.toLowerCase().includes(q))
  }, [providers, searchQuery])

  const filteredModels = useMemo(() => {
    if (!searchQuery.trim()) return models
    const q = searchQuery.toLowerCase()
    return models.filter((m) => m.name.toLowerCase().includes(q) || m.api_provider.toLowerCase().includes(q))
  }, [models, searchQuery])

  // 标记脏
  const markDirty = useCallback(() => setHasUnsavedChanges(true), [])

  // CRUD——厂商
  const addProvider = useCallback((provider: ProviderConfig) => {
    setProviders((prev) => [...prev, provider])
    markDirty()
  }, [markDirty])

  const updateProvider = useCallback((index: number, provider: ProviderConfig) => {
    setProviders((prev) => prev.map((p, i) => (i === index ? provider : p)))
    markDirty()
  }, [markDirty])

  const deleteProvider = useCallback((index: number) => {
    setProviders((prev) => prev.filter((_, i) => i !== index))
    markDirty()
  }, [markDirty])

  // 级联删除——删厂商级联删关联模型
  const cascadeDeleteProvider = useCallback((index: number) => {
    const providerName = providers[index]?.name
    setProviders((prev) => prev.filter((_, i) => i !== index))
    if (providerName) {
      setModels((prev) => prev.filter((m) => m.api_provider !== providerName))
    }
    markDirty()
  }, [providers, markDirty])

  // CRUD——模型
  const addModel = useCallback((model: ModelInfo) => {
    setModels((prev) => [...prev, model])
    markDirty()
  }, [markDirty])

  const updateModel = useCallback((index: number, model: ModelInfo) => {
    setModels((prev) => prev.map((m, i) => (i === index ? model : m)))
    markDirty()
  }, [markDirty])

  const deleteModel = useCallback((index: number) => {
    setModels((prev) => prev.filter((_, i) => i !== index))
    markDirty()
  }, [markDirty])

  // CRUD——任务
  const updateTask = useCallback((taskName: string, config: TaskConfig) => {
    setTaskConfig((prev) => ({ ...prev, [taskName]: config }))
    markDirty()
  }, [markDirty])

  // 批量选择
  const toggleProviderSelection = useCallback((index: number) => {
    setSelectedProviderIndices((prev) => {
      const next = new Set(prev)
      if (next.has(index)) next.delete(index)
      else next.add(index)
      return next
    })
  }, [])

  const toggleModelSelection = useCallback((index: number) => {
    setSelectedModelIndices((prev) => {
      const next = new Set(prev)
      if (next.has(index)) next.delete(index)
      else next.add(index)
      return next
    })
  }, [])

  const batchDeleteProviders = useCallback(() => {
    const indicesToDelete = Array.from(selectedProviderIndices).sort((a, b) => b - a)
    const providerNames = new Set(indicesToDelete.map((i) => providers[i]?.name).filter(Boolean))
    setProviders((prev) => prev.filter((_, i) => !selectedProviderIndices.has(i)))
    setModels((prev) => prev.filter((m) => !providerNames.has(m.api_provider)))
    setSelectedProviderIndices(new Set())
    markDirty()
  }, [selectedProviderIndices, providers, markDirty])

  const batchDeleteModels = useCallback(() => {
    setModels((prev) => prev.filter((_, i) => !selectedModelIndices.has(i)))
    setSelectedModelIndices(new Set())
    markDirty()
  }, [selectedModelIndices, markDirty])

  // 连接测试
  const testProvider = useCallback(async (providerName: string) => {
    setTestingProviders((prev) => new Set(prev).add(providerName))
    try {
      const result = await testProviderConnection(providerName)
      setTestResults((prev) => {
        const next = new Map(prev)
        next.set(providerName, result)
        return next
      })
    } finally {
      setTestingProviders((prev) => {
        const next = new Set(prev)
        next.delete(providerName)
        return next
      })
    }
  }, [])

  const testModel = useCallback(async (modelName: string) => {
    setTestingModels((prev) => new Set(prev).add(modelName))
    try {
      const result = await testModelCapability(modelName)
      setModelTestResults((prev) => {
        const next = new Map(prev)
        next.set(modelName, result)
        return next
      })
    } finally {
      setTestingModels((prev) => {
        const next = new Set(prev)
        next.delete(modelName)
        return next
      })
    }
  }, [])

  // 保存——**走 2 段写接缝**：只发改动的点，带 expectedRevision
  const saveConfig = useCallback(async () => {
    setSaveError(null)
    setSaveMessage(null)
    setConflict(null)

    if (baseline === null || seamRevision === null) {
      // 没拿到基线/revision 就写 = 盲写（乐观锁形同虚设）⇒ 明确拒绝并让用户重载
      setSaveError('配置版本尚未就绪，请点「重新加载」后再保存')
      return
    }

    const next = {
      api_providers: providers,
      models,
      model_task_config: taskConfig,
    }
    const ops = diffToMutateOps(baseline, next)

    if (ops.length === 0) {
      setSaveMessage('没有需要保存的改动')
      setHasUnsavedChanges(false)
      return
    }

    setIsSaving(true)
    try {
      const result = await mutateConfig({
        namespace: 'model',
        expectedRevision: seamRevision,
        ops,
      })
      setSeamRevision(result.revision)
      // 写成功后基线前移——否则下一次保存会把同样的 ops 再发一遍
      setBaseline(cloneDraft(next))
      setHasUnsavedChanges(false)
      setSaveMessage(result.message)
      await queryClient.invalidateQueries({ queryKey: ['api', 'modelConfig'] })
      await queryClient.invalidateQueries({ queryKey: ['api', 'modelConfigSeam'] })
    } catch (caught: unknown) {
      if (caught instanceof ConfigRevisionConflictError) {
        // **不静默重试、不自动合并**：把"读到的是旧版本"这件事原样交给用户，
        // 由他点「重新加载」——重放必须是显式动作，否则等于把用户的改动盖到别人的新版本上。
        setConflict(caught)
      } else {
        // 含后端**认领被拒**（400）等：文案原样呈现，不吞（吞掉它 = 用户以为"保存了"）
        setSaveError(caught instanceof Error ? caught.message : String(caught))
      }
    } finally {
      setIsSaving(false)
    }
  }, [baseline, providers, models, taskConfig, seamRevision, queryClient])

  /** 显式重新加载：拉最新内容与 revision，并清掉冲突/错误态（草稿由数据到达时重置） */
  const reloadFromServer = useCallback(async () => {
    setConflict(null)
    setSaveError(null)
    setSaveMessage(null)
    await queryClient.invalidateQueries({ queryKey: ['api', 'modelConfig'] })
    await queryClient.invalidateQueries({ queryKey: ['api', 'modelConfigSeam'] })
  }, [queryClient])

  // 重置草稿
  const resetDrafts = useCallback(() => {
    if (configData) {
      setProviders((configData.api_providers ?? []) as ProviderConfig[])
      setModels((configData.models ?? []) as ModelInfo[])
      setTaskConfig((configData.model_task_config ?? {}) as ModelTaskConfig)
      setHasUnsavedChanges(false)
    }
  }, [configData])

  return {
    providers,
    models,
    taskConfig,
    isLoading,
    isError,
    error,
    isSaving,
    hasUnsavedChanges,
    addProvider,
    updateProvider,
    deleteProvider,
    cascadeDeleteProvider,
    addModel,
    updateModel,
    deleteModel,
    updateTask,
    searchQuery,
    setSearchQuery,
    filteredProviders,
    filteredModels,
    selectedProviderIndices,
    selectedModelIndices,
    toggleProviderSelection,
    toggleModelSelection,
    batchDeleteProviders,
    batchDeleteModels,
    testingProviders,
    testResults,
    testProvider,
    testingModels,
    modelTestResults,
    testModel,
    saveConfig,
    resetDrafts,
    seamRevision,
    conflict,
    saveError,
    saveMessage,
    providerSecretStates,
    reloadFromServer,
  }
}