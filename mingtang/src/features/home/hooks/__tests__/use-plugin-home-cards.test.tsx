/**
 * usePluginHomeCards 测试（§4.4.1 测试先行）
 *
 * 核心验证：
 * - 插件卡片加载（2 插件各 1 卡片 → pluginHomeCards 长度 2）
 * - 错误态降级（空数组）
 */
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createElement, type ReactNode } from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

const { mockGetPluginHomeCards } = vi.hoisted(() => ({
  mockGetPluginHomeCards: vi.fn(),
}))

vi.mock('@/lib/plugin-api', () => ({
  getPluginHomeCards: mockGetPluginHomeCards,
}))

import { usePluginHomeCards } from '../use-plugin-home-cards'
import type { PluginHomeCard } from '@/lib/plugin-api'

function createWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return function TestWrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: qc }, children)
  }
}

function makeCard(pluginId: string, title: string): PluginHomeCard {
  return {
    id: `${pluginId}-card`,
    name: title,
    plugin_id: pluginId,
    title,
    description: `${title} 描述`,
    content: '',
    link_url: `/plugin-config?plugin=${pluginId}`,
    link_label: '配置',
    icon: 'puzzle',
    width: 'medium',
    order: 0,
    enabled: true,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  mockGetPluginHomeCards.mockResolvedValue([makeCard('chat-logger', '聊天记录'), makeCard('weather', '天气查询')])
})

describe('usePluginHomeCards', () => {
  it('初始状态：空数组 + loading', () => {
    const { result } = renderHook(() => usePluginHomeCards(), { wrapper: createWrapper() })
    expect(result.current.pluginHomeCards).toEqual([])
    expect(result.current.isLoading).toBe(true)
  })

  it('加载后返回插件卡片列表', async () => {
    const { result } = renderHook(() => usePluginHomeCards(), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.pluginHomeCards).toHaveLength(2)
    })
    expect(result.current.pluginHomeCards[0].plugin_id).toBe('chat-logger')
    expect(result.current.pluginHomeCards[1].title).toBe('天气查询')
    expect(result.current.isLoading).toBe(false)
    expect(result.current.error).toBeNull()
  })

  it('加载失败时降级为空数组 + error 不为空', async () => {
    mockGetPluginHomeCards.mockRejectedValue(new Error('boom'))

    const { result } = renderHook(() => usePluginHomeCards(), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.error).not.toBeNull()
    })
    expect(result.current.pluginHomeCards).toEqual([])
    expect(result.current.isLoading).toBe(false)
  })
})