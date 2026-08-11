/**
 * useReviewStats 测试（§4.5.1 测试先行）
 *
 * 核心验证：
 * - 审核统计加载（5 条未审核 → uncheckedCount=5）
 * - 错误态
 */
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createElement, type ReactNode } from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

const { mockGetReviewStats } = vi.hoisted(() => ({
  mockGetReviewStats: vi.fn(),
}))

vi.mock('@/lib/expression-api', () => ({
  getReviewStats: mockGetReviewStats,
}))

import { useReviewStats } from '../use-review-stats'

function createWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return function TestWrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: qc }, children)
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  mockGetReviewStats.mockResolvedValue({ unchecked: 5, total: 20 })
})

describe('useReviewStats', () => {
  it('初始状态：uncheckedCount=0 + loading', () => {
    const { result } = renderHook(() => useReviewStats(), { wrapper: createWrapper() })
    expect(result.current.uncheckedCount).toBe(0)
    expect(result.current.isLoading).toBe(true)
  })

  it('加载后返回未审核数量', async () => {
    const { result } = renderHook(() => useReviewStats(), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.uncheckedCount).toBe(5)
    })
    expect(result.current.isLoading).toBe(false)
    expect(result.current.error).toBeNull()
  })

  it('加载失败时 uncheckedCount=0 + error 不为空', async () => {
    mockGetReviewStats.mockRejectedValue(new Error('boom'))

    const { result } = renderHook(() => useReviewStats(), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.error).not.toBeNull()
    })
    expect(result.current.uncheckedCount).toBe(0)
    expect(result.current.isLoading).toBe(false)
  })
})