import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createElement, type ReactNode } from 'react'
import { PluginMarketplacePage } from '../index'

vi.mock('@/lib/plugin-api', () => ({
  fetchPluginList: vi.fn().mockResolvedValue([
    { id: 'test-plugin', name: 'test-plugin', description: '测试插件', version: '1.0.0', author: 'test', url: 'https://github.com/test/plugin', type: 'normal', tags: [], stars: 10, updated_at: '2024-01-01', manifest: { id: 'test-plugin', name: 'test-plugin', version: '1.0.0', description: '测试插件' } },
  ]),
  getCachedPluginList: vi.fn().mockReturnValue(null),
  getInstalledPlugins: vi.fn().mockResolvedValue([]),
  checkPluginInstalled: vi.fn().mockReturnValue(false),
  getInstalledPluginVersion: vi.fn().mockReturnValue(null),
  getMaimaiVersion: vi.fn().mockResolvedValue('1.0.0'),
  checkGitStatus: vi.fn().mockResolvedValue({ available: true }),
  isPluginCompatible: vi.fn().mockReturnValue(true),
  installPlugin: vi.fn().mockResolvedValue(undefined),
  uninstallPlugin: vi.fn().mockResolvedValue(undefined),
  updatePlugin: vi.fn().mockResolvedValue(undefined),
  connectPluginProgressWebSocket: vi.fn().mockResolvedValue(vi.fn()),
}))

vi.mock('@/lib/plugin-stats', () => ({
  getPluginStatsSummary: vi.fn().mockResolvedValue({ likes: 0, downloads: 0, rating: 0 }),
  getCachedPluginStatsSummary: vi.fn().mockReturnValue(null),
  likePlugin: vi.fn().mockResolvedValue(undefined),
  recordPluginDownload: vi.fn().mockResolvedValue(undefined),
}))

vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => vi.fn(),
}))

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k, i18n: { resolvedLanguage: 'zh', language: 'zh' } }),
}))

vi.mock('@/lib/restart-context', () => ({
  RestartProvider: ({ children }: { children: ReactNode }) => children,
  useRestart: () => ({ triggerRestart: vi.fn(), isRestarting: false }),
}))

vi.mock('@/components/restart-overlay', () => ({
  RestartOverlay: () => null,
}))

vi.mock('@/features/plugin/detail', () => ({
  PluginDetailPage: () => createElement('div', { 'data-testid': 'plugin-detail' }),
}))

function createWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return function TestWrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: qc }, children)
  }
}

describe('R4-4a §15.1：插件市场页', () => {
  beforeEach(() => vi.clearAllMocks())

  it('渲染页面壳 + 标题', async () => {
    render(<PluginMarketplacePage />, { wrapper: createWrapper() })
    await waitFor(() => expect(screen.getByText('插件市场')).toBeInTheDocument())
  })

  it('渲染搜索框', async () => {
    render(<PluginMarketplacePage />, { wrapper: createWrapper() })
    await waitFor(() => expect(screen.getByPlaceholderText('搜索插件...')).toBeInTheDocument())
  })

  it('embedded prop 切换路由前缀', async () => {
    render(<PluginMarketplacePage embedded />, { wrapper: createWrapper() })
    await waitFor(() => expect(screen.getByText('插件市场')).toBeInTheDocument())
  })
})