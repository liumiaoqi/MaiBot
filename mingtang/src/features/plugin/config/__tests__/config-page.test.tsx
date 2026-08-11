import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createElement, createContext, type ReactNode } from 'react'
import { PluginConfigPage } from '../index'

vi.mock('@/lib/plugin-api', () => ({
  getInstalledPlugins: vi.fn().mockResolvedValue([
    { name: 'test-plugin', version: '1.0.0', description: '测试插件', enabled: true, config: {} },
  ]),
  getPluginConfig: vi.fn().mockResolvedValue({}),
  getPluginConfigSchema: vi.fn().mockResolvedValue({ sections: [] }),
  savePluginConfig: vi.fn().mockResolvedValue(undefined),
  uninstallPlugin: vi.fn().mockResolvedValue(undefined),
  updatePlugin: vi.fn().mockResolvedValue(undefined),
  checkPluginInstalled: vi.fn().mockReturnValue(true),
  getMaimaiVersion: vi.fn().mockResolvedValue('1.0.0'),
  isPluginCompatible: vi.fn().mockReturnValue(true),
}))

vi.mock('@/lib/plugin-stats', () => ({
  getPluginStatsSummary: vi.fn().mockResolvedValue({ likes: 0, downloads: 0, rating: 0 }),
  getCachedPluginStatsSummary: vi.fn().mockReturnValue(null),
}))

vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => vi.fn(),
  useSearch: () => ({}),
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

vi.mock('@/lib/theme-context', () => ({
  ThemeProviderContext: createContext({ themeConfig: { style: 'modern' } }),
}))

function createWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return function TestWrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: qc }, children)
  }
}

describe('R4-4a §15.2：插件配置页', () => {
  beforeEach(() => vi.clearAllMocks())

  it('渲染页面壳', async () => {
    render(<PluginConfigPage />, { wrapper: createWrapper() })
    await waitFor(() => expect(screen.getByPlaceholderText('搜索插件...')).toBeInTheDocument())
  })

  it('渲染已安装插件列表', async () => {
    render(<PluginConfigPage />, { wrapper: createWrapper() })
    await waitFor(() => expect(screen.getByText(/已安装/)).toBeInTheDocument())
  })
})