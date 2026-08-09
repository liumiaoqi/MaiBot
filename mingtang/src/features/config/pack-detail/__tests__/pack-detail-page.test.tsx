import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createElement, type ReactNode } from 'react'
import { PackDetailPage } from '../index'

vi.mock('@tanstack/react-router', () => ({
  useParams: () => ({ packId: 'test-pack' }),
}))

vi.mock('@/lib/pack-api', () => ({
  getPack: vi.fn().mockResolvedValue({ id: 'test-pack', name: '测试', version: '1.0', description: 'desc', author: 'a', downloads: 0, likes: 0, providers: [{ name: 'p1', base_url: 'http://a' }], models: [{ name: 'm1', api_provider: 'p1', model_identifier: 'm1' }], task_config: { chat: { models: ['m1'] } } }),
  detectPackConflicts: vi.fn().mockResolvedValue({ existing_providers: [], new_providers: [], conflicting_models: [] }),
  applyPack: vi.fn().mockResolvedValue(undefined),
  recordPackDownload: vi.fn().mockResolvedValue(undefined),
}))

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }))

function createWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return function TestWrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: qc }, children)
  }
}

describe('R2-3-10：/config/pack-detail 配置模板详情页', () => {
  beforeEach(() => vi.clearAllMocks())

  it('渲染 PageShell + 标题', async () => {
    render(<PackDetailPage />, { wrapper: createWrapper() })
    expect(screen.getByTestId('page-shell')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText('测试')).toBeInTheDocument())
  })

  it('统计卡片渲染', async () => {
    render(<PackDetailPage />, { wrapper: createWrapper() })
    await waitFor(() => expect(screen.getByTestId('pack-detail-stats')).toBeInTheDocument())
  })

  it('应用模板按钮渲染', async () => {
    render(<PackDetailPage />, { wrapper: createWrapper() })
    await waitFor(() => expect(screen.getByTestId('pack-apply')).toBeInTheDocument())
  })
})