/**
 * useQuickShortcuts 测试（§4.6.1 测试先行）
 *
 * 核心验证：
 * - localStorage 持久化选择（选"重启"+"日志" → 刷新仍展示）
 * - 15 内置快捷项
 * - 搜索过滤（输入"插件" → 仅展示含"插件"项）
 * - toggle/reset 操作
 */
import { renderHook, act, waitFor } from '@testing-library/react'
import { createElement, type ReactNode } from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

const { mockGetInstalledPlugins, mockGetPluginConfigSchema } = vi.hoisted(() => ({
  mockGetInstalledPlugins: vi.fn(),
  mockGetPluginConfigSchema: vi.fn(),
}))

vi.mock('@/lib/plugin-api', () => ({
  getInstalledPlugins: mockGetInstalledPlugins,
  getPluginConfigSchema: mockGetPluginConfigSchema,
}))

const stableT = (key: string, params?: Record<string, unknown>) => {
  if (params && typeof params === 'object') {
    const entries = Object.entries(params)
    if (entries.length > 0) {
      return `${key}:${entries.map(([k, v]) => `${k}=${v}`).join(',')}`
    }
  }
  return key
}

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: stableT }),
}))

import { useQuickShortcuts } from '../use-quick-shortcuts'

function createWrapper() {
  return function TestWrapper({ children }: { children: ReactNode }) {
    return createElement('div', null, children)
  }
}

const defaultParams = {
  isRestarting: false,
  handleRestart: vi.fn(),
  uncheckedCount: 0,
  onOpenReviewer: vi.fn(),
}

beforeEach(() => {
  vi.clearAllMocks()
  mockGetInstalledPlugins.mockResolvedValue([])
  mockGetPluginConfigSchema.mockResolvedValue({ layout: { type: 'single' }, sections: [] })
  localStorage.clear()
})

describe('useQuickShortcuts', () => {
  it('初始状态：默认 6 快捷项 + 15 内置选项', async () => {
    const { result } = renderHook(() => useQuickShortcuts(defaultParams), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.isPluginShortcutsLoading).toBe(false)
    })

    // 默认选中 6 项
    expect(result.current.quickShortcutIds).toHaveLength(6)
    // 15 内置选项（无插件快捷入口时）
    expect(result.current.filteredQuickShortcutOptions).toHaveLength(15)
  })

  it('toggleQuickShortcut 添加新项 → localStorage 持久化', async () => {
    const { result } = renderHook(() => useQuickShortcuts(defaultParams), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.isPluginShortcutsLoading).toBe(false)
    })

    act(() => result.current.toggleQuickShortcut('route:bot-config', true))

    expect(result.current.quickShortcutIds).toContain('route:bot-config')
    const stored = JSON.parse(localStorage.getItem('maibot-home-quick-shortcuts') ?? '[]')
    expect(stored).toContain('route:bot-config')
  })

  it('toggleQuickShortcut 移除项 → localStorage 更新', async () => {
    const { result } = renderHook(() => useQuickShortcuts(defaultParams), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.isPluginShortcutsLoading).toBe(false)
    })

    act(() => result.current.toggleQuickShortcut('action:restart', false))

    expect(result.current.quickShortcutIds).not.toContain('action:restart')
    const stored = JSON.parse(localStorage.getItem('maibot-home-quick-shortcuts') ?? '[]')
    expect(stored).not.toContain('action:restart')
  })

  it('resetQuickShortcuts → 恢复默认 6 项', async () => {
    const { result } = renderHook(() => useQuickShortcuts(defaultParams), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.isPluginShortcutsLoading).toBe(false)
    })

    act(() => result.current.toggleQuickShortcut('route:bot-config', true))
    expect(result.current.quickShortcutIds).toHaveLength(7)

    act(() => result.current.resetQuickShortcuts())
    expect(result.current.quickShortcutIds).toHaveLength(6)
  })

  it('搜索过滤（输入"pluginManage" → 仅展示匹配项）', async () => {
    const { result } = renderHook(() => useQuickShortcuts(defaultParams), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.isPluginShortcutsLoading).toBe(false)
    })

    act(() => result.current.setQuickShortcutSearch('pluginManage'))

    // t(key) 返回 key 本身，所以搜索匹配 key 中的文本
    expect(result.current.filteredQuickShortcutOptions.length).toBeLessThan(15)
    expect(result.current.filteredQuickShortcutOptions.length).toBeGreaterThanOrEqual(1)
  })

  it('uncheckedCount > 0 → expression-review 项带 badge', async () => {
    const { result } = renderHook(
      () => useQuickShortcuts({ ...defaultParams, uncheckedCount: 5 }),
      { wrapper: createWrapper() }
    )

    await waitFor(() => {
      expect(result.current.isPluginShortcutsLoading).toBe(false)
    })

    const reviewItem = result.current.filteredQuickShortcutOptions.find(
      (item) => item.id === 'action:expression-review'
    )
    expect(reviewItem?.badge).toBe('5')
  })

  it('uncheckedCount > 99 → badge 显示 99+', async () => {
    const { result } = renderHook(
      () => useQuickShortcuts({ ...defaultParams, uncheckedCount: 150 }),
      { wrapper: createWrapper() }
    )

    await waitFor(() => {
      expect(result.current.isPluginShortcutsLoading).toBe(false)
    })

    const reviewItem = result.current.filteredQuickShortcutOptions.find(
      (item) => item.id === 'action:expression-review'
    )
    expect(reviewItem?.badge).toBe('99+')
  })
})