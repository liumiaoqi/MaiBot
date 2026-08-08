import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createElement, type ReactNode } from 'react'
import { useModelConfig } from '../use-model-config'
import type { TestConnectionResult, ModelTestResult } from '@/lib/config-api'

// 用 vi.hoisted 定义 mock 数据（vitest 4 hoisting 规则）
const { mockConfigData, mockTestResult, mockModelTestResult } = vi.hoisted(() => ({
  mockConfigData: {
    api_providers: [
      { name: 'provider1', base_url: 'http://a', api_key: 'key1' },
      { name: 'provider2', base_url: 'http://b', api_key: 'key2' },
    ],
    models: [
      { name: 'model1', api_provider: 'provider1', model_identifier: 'gpt-4' },
      { name: 'model2', api_provider: 'provider2', model_identifier: 'claude-3' },
    ],
    model_task_config: {
      chat: { models: ['model1'], temperature: 0.7 },
      memory: { models: ['model2'], temperature: 0.5 },
    },
  },
  mockTestResult: {
    network_ok: true, api_key_valid: true, latency_ms: 100, error: null, http_status: 200,
  } as TestConnectionResult,
  mockModelTestResult: {
    success: true, model_name: 'model1', visual_tested: false, tool_call_ok: true,
    response: 'ok', reasoning: '', tool_calls: [], latency_ms: 50, error: null,
    prompt_tokens: 10, completion_tokens: 5, total_tokens: 15,
  } as ModelTestResult,
}))

vi.mock('@/lib/config-api', () => ({
  getModelConfig: vi.fn().mockResolvedValue(mockConfigData),
  updateModelConfig: vi.fn().mockResolvedValue({ success: true, message: 'ok', needs_restart: false, restart_required_sections: [] }),
  updateModelConfigSection: vi.fn().mockResolvedValue({ success: true, message: 'ok', needs_restart: false, restart_required_sections: [] }),
  testProviderConnection: vi.fn().mockResolvedValue(mockTestResult),
  testModelCapability: vi.fn().mockResolvedValue(mockModelTestResult),
}))


function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children)
}

describe('R2-3-2：useModelConfig 领域 hook', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('加载三份草稿（providers/models/tasks）', async () => {
    const { result } = renderHook(() => useModelConfig(), { wrapper: createWrapper() })
    await waitFor(() => expect(result.current.providers).toHaveLength(2))
    expect(result.current.models).toHaveLength(2)
    expect(result.current.taskConfig.chat).toBeDefined()
    expect(result.current.taskConfig.memory).toBeDefined()
  })

  it('状态——isLoading / isError', async () => {
    const { result } = renderHook(() => useModelConfig(), { wrapper: createWrapper() })
    await waitFor(() => expect(result.current.isLoading).toBe(false))
    expect(result.current.isError).toBe(false)
  })

  it('CRUD——addProvider', async () => {
    const { result } = renderHook(() => useModelConfig(), { wrapper: createWrapper() })
    await waitFor(() => expect(result.current.providers).toHaveLength(2))
    act(() => {
      result.current.addProvider({ name: 'newProvider', base_url: 'http://c', api_key: 'key3' })
    })
    expect(result.current.providers).toHaveLength(3)
    expect(result.current.providers[2].name).toBe('newProvider')
    expect(result.current.hasUnsavedChanges).toBe(true)
  })

  it('CRUD——updateProvider', async () => {
    const { result } = renderHook(() => useModelConfig(), { wrapper: createWrapper() })
    await waitFor(() => expect(result.current.providers).toHaveLength(2))
    act(() => {
      result.current.updateProvider(0, { name: 'updated', base_url: 'http://x', api_key: 'k' })
    })
    expect(result.current.providers[0].name).toBe('updated')
    expect(result.current.hasUnsavedChanges).toBe(true)
  })

  it('CRUD——deleteProvider', async () => {
    const { result } = renderHook(() => useModelConfig(), { wrapper: createWrapper() })
    await waitFor(() => expect(result.current.providers).toHaveLength(2))
    act(() => {
      result.current.deleteProvider(0)
    })
    expect(result.current.providers).toHaveLength(1)
    expect(result.current.providers[0].name).toBe('provider2')
    expect(result.current.hasUnsavedChanges).toBe(true)
  })

  it('级联删除——cascadeDeleteProvider 删厂商级联删模型', async () => {
    const { result } = renderHook(() => useModelConfig(), { wrapper: createWrapper() })
    await waitFor(() => expect(result.current.providers).toHaveLength(2))
    act(() => {
      result.current.cascadeDeleteProvider(0)
    })
    expect(result.current.providers).toHaveLength(1)
    expect(result.current.models).toHaveLength(1)
    expect(result.current.models[0].api_provider).toBe('provider2')
    expect(result.current.hasUnsavedChanges).toBe(true)
  })

  it('CRUD——addModel', async () => {
    const { result } = renderHook(() => useModelConfig(), { wrapper: createWrapper() })
    await waitFor(() => expect(result.current.models).toHaveLength(2))
    act(() => {
      result.current.addModel({ name: 'newModel', api_provider: 'provider1', model_identifier: 'gpt-5' })
    })
    expect(result.current.models).toHaveLength(3)
    expect(result.current.hasUnsavedChanges).toBe(true)
  })

  it('CRUD——updateModel', async () => {
    const { result } = renderHook(() => useModelConfig(), { wrapper: createWrapper() })
    await waitFor(() => expect(result.current.models).toHaveLength(2))
    act(() => {
      result.current.updateModel(0, { name: 'updated', api_provider: 'provider1', model_identifier: 'gpt-4o' })
    })
    expect(result.current.models[0].name).toBe('updated')
    expect(result.current.hasUnsavedChanges).toBe(true)
  })

  it('CRUD——deleteModel', async () => {
    const { result } = renderHook(() => useModelConfig(), { wrapper: createWrapper() })
    await waitFor(() => expect(result.current.models).toHaveLength(2))
    act(() => {
      result.current.deleteModel(0)
    })
    expect(result.current.models).toHaveLength(1)
    expect(result.current.hasUnsavedChanges).toBe(true)
  })

  it('CRUD——updateTask', async () => {
    const { result } = renderHook(() => useModelConfig(), { wrapper: createWrapper() })
    await waitFor(() => expect(result.current.taskConfig.chat).toBeDefined())
    act(() => {
      result.current.updateTask('chat', { models: ['model2'], temperature: 0.9 })
    })
    expect(result.current.taskConfig.chat.models).toEqual(['model2'])
    expect(result.current.taskConfig.chat.temperature).toBe(0.9)
    expect(result.current.hasUnsavedChanges).toBe(true)
  })

  it('搜索——setSearchQuery 过滤 providers', async () => {
    const { result } = renderHook(() => useModelConfig(), { wrapper: createWrapper() })
    await waitFor(() => expect(result.current.providers).toHaveLength(2))
    act(() => {
      result.current.setSearchQuery('provider1')
    })
    expect(result.current.filteredProviders).toHaveLength(1)
    expect(result.current.filteredProviders[0].name).toBe('provider1')
  })

  it('搜索——setSearchQuery 过滤 models', async () => {
    const { result } = renderHook(() => useModelConfig(), { wrapper: createWrapper() })
    await waitFor(() => expect(result.current.models).toHaveLength(2))
    act(() => {
      result.current.setSearchQuery('model1')
    })
    expect(result.current.filteredModels).toHaveLength(1)
    expect(result.current.filteredModels[0].name).toBe('model1')
  })

  it('批量——toggleProviderSelection + batchDeleteProviders', async () => {
    const { result } = renderHook(() => useModelConfig(), { wrapper: createWrapper() })
    await waitFor(() => expect(result.current.providers).toHaveLength(2))
    act(() => {
      result.current.toggleProviderSelection(0)
      result.current.toggleProviderSelection(1)
    })
    expect(result.current.selectedProviderIndices.size).toBe(2)
    act(() => {
      result.current.batchDeleteProviders()
    })
    expect(result.current.providers).toHaveLength(0)
    expect(result.current.models).toHaveLength(0)
    expect(result.current.selectedProviderIndices.size).toBe(0)
  })

  it('批量——toggleModelSelection + batchDeleteModels', async () => {
    const { result } = renderHook(() => useModelConfig(), { wrapper: createWrapper() })
    await waitFor(() => expect(result.current.models).toHaveLength(2))
    act(() => {
      result.current.toggleModelSelection(0)
    })
    expect(result.current.selectedModelIndices.size).toBe(1)
    act(() => {
      result.current.batchDeleteModels()
    })
    expect(result.current.models).toHaveLength(1)
    expect(result.current.selectedModelIndices.size).toBe(0)
  })

  it('连接测试——testProvider', async () => {
    const { result } = renderHook(() => useModelConfig(), { wrapper: createWrapper() })
    await waitFor(() => expect(result.current.providers).toHaveLength(2))
    await act(async () => {
      await result.current.testProvider('provider1')
    })
    expect(result.current.testResults.get('provider1')).toEqual(mockTestResult)
    expect(result.current.testingProviders.size).toBe(0)
  })

  it('连接测试——testModel', async () => {
    const { result } = renderHook(() => useModelConfig(), { wrapper: createWrapper() })
    await waitFor(() => expect(result.current.models).toHaveLength(2))
    await act(async () => {
      await result.current.testModel('model1')
    })
    expect(result.current.modelTestResults.get('model1')).toEqual(mockModelTestResult)
    expect(result.current.testingModels.size).toBe(0)
  })

  it('重置草稿——resetDrafts', async () => {
    const { result } = renderHook(() => useModelConfig(), { wrapper: createWrapper() })
    await waitFor(() => expect(result.current.providers).toHaveLength(2))
    act(() => {
      result.current.addProvider({ name: 'extra', base_url: '', api_key: '' })
    })
    expect(result.current.providers).toHaveLength(3)
    act(() => {
      result.current.resetDrafts()
    })
    expect(result.current.providers).toHaveLength(2)
    expect(result.current.hasUnsavedChanges).toBe(false)
  })
})
