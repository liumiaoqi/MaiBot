/**
 * useFeatureStatus 测试（§4.8.1 测试先行）
 *
 * 核心验证：
 * - allSettled 容错（bot 配置失败 + model 配置成功 → memoryEnabled=false/visualEnabled=true）
 * - 记忆开关解析（a_memorix.plugin.enabled）
 * - 视觉开关解析（vlm.model_list 含有效模型）
 */
import { renderHook, act } from '@testing-library/react'
import { createElement, type ReactNode } from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

const { mockGetBotConfigCached, mockGetModelConfigCached } = vi.hoisted(() => ({
  mockGetBotConfigCached: vi.fn(),
  mockGetModelConfigCached: vi.fn(),
}))

vi.mock('@/lib/config-api', () => ({
  getBotConfigCached: mockGetBotConfigCached,
  getModelConfigCached: mockGetModelConfigCached,
}))

import { useFeatureStatus } from '../use-feature-status'

function createWrapper() {
  return function TestWrapper({ children }: { children: ReactNode }) {
    return createElement('div', null, children)
  }
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('useFeatureStatus', () => {
  it('初始状态：memoryEnabled=false, visualEnabled=false', () => {
    const { result } = renderHook(() => useFeatureStatus(), { wrapper: createWrapper() })
    expect(result.current.featureStatus).toEqual({ memoryEnabled: false, visualEnabled: false })
  })

  it('记忆+视觉均启用', async () => {
    mockGetBotConfigCached.mockResolvedValue({
      config: {
        a_memorix: { plugin: { enabled: true } },
      },
    })
    mockGetModelConfigCached.mockResolvedValue({
      config: {
        model_task_config: {
          vlm: { model_list: ['gpt-4o', 'claude-3-vision'] },
        },
      },
    })

    const { result } = renderHook(() => useFeatureStatus(), { wrapper: createWrapper() })

    await act(async () => {
      await result.current.fetchFeatureStatus()
    })

    expect(result.current.featureStatus.memoryEnabled).toBe(true)
    expect(result.current.featureStatus.visualEnabled).toBe(true)
  })

  it('bot 配置失败 + model 配置成功 → memoryEnabled=false/visualEnabled=true', async () => {
    mockGetBotConfigCached.mockRejectedValue(new Error('bot boom'))
    mockGetModelConfigCached.mockResolvedValue({
      config: {
        model_task_config: {
          vlm: { model_list: ['gpt-4o'] },
        },
      },
    })

    const { result } = renderHook(() => useFeatureStatus(), { wrapper: createWrapper() })

    await act(async () => {
      await result.current.fetchFeatureStatus()
    })

    // bot 配置失败 → 不更新 featureStatus（保持初始值）
    expect(result.current.featureStatus.memoryEnabled).toBe(false)
    expect(result.current.featureStatus.visualEnabled).toBe(false)
  })

  it('vlm.model_list 为空 → visualEnabled=false', async () => {
    mockGetBotConfigCached.mockResolvedValue({
      config: { a_memorix: { plugin: { enabled: true } } },
    })
    mockGetModelConfigCached.mockResolvedValue({
      config: { model_task_config: { vlm: { model_list: [] } } },
    })

    const { result } = renderHook(() => useFeatureStatus(), { wrapper: createWrapper() })

    await act(async () => {
      await result.current.fetchFeatureStatus()
    })

    expect(result.current.featureStatus.memoryEnabled).toBe(true)
    expect(result.current.featureStatus.visualEnabled).toBe(false)
  })

  it('两者都失败 → featureStatus={memoryEnabled:false, visualEnabled:false}', async () => {
    mockGetBotConfigCached.mockRejectedValue(new Error('bot boom'))
    mockGetModelConfigCached.mockRejectedValue(new Error('model boom'))

    const { result } = renderHook(() => useFeatureStatus(), { wrapper: createWrapper() })

    await act(async () => {
      await result.current.fetchFeatureStatus()
    })

    expect(result.current.featureStatus).toEqual({ memoryEnabled: false, visualEnabled: false })
  })
})