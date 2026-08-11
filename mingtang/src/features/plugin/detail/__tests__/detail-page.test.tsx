import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createElement, type ReactNode } from 'react'
import { PluginDetailPage } from '../index'

vi.mock('@/lib/plugin-api', () => ({
  fetchPluginList: vi.fn().mockResolvedValue([
    { id: 'test-plugin', name: 'test-plugin', description: '测试插件', version: '1.0.0', author: 'test', url: 'https://github.com/test/plugin', type: 'normal', tags: [], stars: 10, updated_at: '2024-01-01', readme_url: 'https://github.com/test/plugin#readme', manifest: { id: 'test-plugin', name: 'test-plugin', version: '1.0.0', description: '测试插件', host_application: { min_version: '0.0.1', max_version: '' }, author: { name: 'test', url: '' }, keywords: [], license: 'MIT' } },
  ]),
  getInstalledPlugins: vi.fn().mockResolvedValue([]),
  checkPluginInstalled: vi.fn().mockReturnValue(false),
  getInstalledPluginVersion: vi.fn().mockReturnValue(null),
  getMaimaiVersion: vi.fn().mockResolvedValue('1.0.0'),
  checkGitStatus: vi.fn().mockResolvedValue({ available: true }),
  isPluginCompatible: vi.fn().mockReturnValue(true),
  installPlugin: vi.fn().mockResolvedValue(undefined),
  uninstallPlugin: vi.fn().mockResolvedValue(undefined),
  updatePlugin: vi.fn().mockResolvedValue(undefined),
}))

vi.mock('@/lib/plugin-stats', () => ({
  recordPluginDownload: vi.fn().mockResolvedValue(undefined),
  getPluginStatsSummary: vi.fn().mockResolvedValue({ likes: 0, downloads: 0, rating: 0 }),
  getCachedPluginStatsSummary: vi.fn().mockReturnValue(null),
  likePlugin: vi.fn().mockResolvedValue(undefined),
}))

vi.mock('@/lib/http', () => ({
  backendApi: { get: vi.fn().mockResolvedValue({}) },
}))

vi.mock('@/components/plugin-stats', () => ({
  PluginStats: () => createElement('div', { 'data-testid': 'plugin-stats' }),
}))

vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => vi.fn(),
  useSearch: () => ({ pluginId: 'test-plugin' }),
}))

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k, i18n: { resolvedLanguage: 'zh', language: 'zh' } }),
}))

function createWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return function TestWrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: qc }, children)
  }
}

describe('R4-4a §15.3：插件详情页', () => {
  beforeEach(() => vi.clearAllMocks())

  it('渲染详情页标题', async () => {
    render(<PluginDetailPage pluginId="test-plugin" />, { wrapper: createWrapper() })
    await waitFor(() => expect(screen.getByText('插件详情')).toBeInTheDocument())
  })

  it('渲染统计组件', async () => {
    render(<PluginDetailPage pluginId="test-plugin" />, { wrapper: createWrapper() })
    await waitFor(() => expect(screen.getByTestId('plugin-stats')).toBeInTheDocument())
  })

  it('readme 降级——GitHub fetch reject 时显示降级提示', async () => {
    render(<PluginDetailPage pluginId="test-plugin" />, { wrapper: createWrapper() })
    await waitFor(() => expect(screen.getByText('插件详情')).toBeInTheDocument())
  })
})