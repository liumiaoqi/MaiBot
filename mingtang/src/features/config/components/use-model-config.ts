/**
 * useModelConfig —— model 域核心领域 hook
 *
 * 三份草稿（providers/models/tasks）+ CRUD + 搜索分页 + 批量 + 连接测试 + 级联删除 + 状态
 * 页面只留纯 UI 态（关注点分离）
 */
import { useState, useMemo, useCallback, useEffect } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  getModelConfig,
  updateModelConfig,
  testProviderConnection,
  testModelCapability,
  type TestConnectionResult,
  type ModelTestResult,
} from '@/lib/config-api'

// === 类型定义 ===

export interface ProviderConfig {
  name: string
  base_url: string
  api_key: string
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
}

// === Hook 实现 ===

export function useModelConfig(): UseModelConfigReturn {
  const queryClient = useQueryClient()

  // 服务端数据加载
  const { data: configData, isLoading, isError, error } = useQuery({
    queryKey: ['api', 'modelConfig'],
    queryFn: getModelConfig,
  })

  // 三份草稿
  const [providers, setProviders] = useState<ProviderConfig[]>([])
  const [models, setModels] = useState<ModelInfo[]>([])
  const [taskConfig, setTaskConfig] = useState<ModelTaskConfig>({})

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

  // 从服务端数据初始化草稿
  useEffect(() => {
    if (configData) {
      const rawProviders = (configData.api_providers ?? []) as ProviderConfig[]
      const rawModels = (configData.models ?? []) as ModelInfo[]
      const rawTasks = (configData.model_task_config ?? {}) as ModelTaskConfig
      setProviders(rawProviders)
      setModels(rawModels)
      setTaskConfig(rawTasks)
      setHasUnsavedChanges(false)
    }
  }, [configData])

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
  }, [])

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

  // 保存
  const saveConfig = useCallback(async () => {
    setIsSaving(true)
    try {
      await updateModelConfig({
        api_providers: providers,
        models,
        model_task_config: taskConfig,
      })
      setHasUnsavedChanges(false)
      await queryClient.invalidateQueries({ queryKey: ['api', 'modelConfig'] })
    } finally {
      setIsSaving(false)
    }
  }, [providers, models, taskConfig, queryClient])

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
  }
}