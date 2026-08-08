import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createElement, type ReactNode } from 'react'
import { PackMarketPage } from '../index'

vi.mock('@/lib/pack-api', () => ({
  listPacks: vi.fn().mockResolvedValue({ packs: [{ id: 'pack1', name: '测试模板', version: '1.0', description: 'desc', author: 'a', downloads: 10, likes: 5, provider_count: 1, model_count: 2, task_count: 3 }], total: 1, page: 1, page_size: 12, total_pages: 1 }),
}))

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }))

function createWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: ReactNode }) => createElement(QueryClientProvider, { client: qc }, children)
}

describe('R2-3-9：/config/pack-market 配置模板市场页', () => {
  beforeEach(() => vi.clearAllMocks())

  it('渲染 PageShell + 标题', async () => {
    render(<PackMarketPage />, { wrapper: createWrapper() })
    expect(screen.getByTestId('page-shell')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText('sidebar.menu.configTemplate')).toBeInTheDocument())
  })

  it('搜索 + 排序渲染', async () => {
    render(<PackMarketPage />, { wrapper: createWrapper() })
    await waitFor(() => expect(screen.getByTestId('pack-search')).toBeInTheDocument())
    expect(screen.getByTestId('pack-sort')).toBeInTheDocument()
  })

  it('卡片网格渲染', async () => {
    render(<PackMarketPage />, { wrapper: createWrapper() })
    await waitFor(() => expect(screen.getByTestId('pack-card-pack1')).toBeInTheDocument())
  })
})