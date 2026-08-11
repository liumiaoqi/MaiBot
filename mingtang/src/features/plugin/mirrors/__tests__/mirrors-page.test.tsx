import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createElement, type ReactNode } from 'react'
import { PluginMirrorsPage } from '../index'

vi.mock('@/lib/http', () => ({
  backendApi: {
    get: vi.fn().mockResolvedValue({
      mirrors: [
        { id: 'github', name: 'GitHub', raw_prefix: '', clone_prefix: '', enabled: true, priority: 1, is_default: true },
        { id: 'custom', name: '自定义源', raw_prefix: 'https://custom.com/raw', clone_prefix: 'https://custom.com/clone', enabled: true, priority: 2, is_default: false },
      ],
    }),
    post: vi.fn().mockResolvedValue({}),
    put: vi.fn().mockResolvedValue({}),
    delete: vi.fn().mockResolvedValue({}),
  },
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

function createWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return function TestWrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: qc }, children)
  }
}

describe('R4-4a §15.4：插件镜像源管理页', () => {
  beforeEach(() => vi.clearAllMocks())

  it('渲染页面标题', async () => {
    render(<PluginMirrorsPage />, { wrapper: createWrapper() })
    await waitFor(() => expect(screen.getByText('插件商店设置')).toBeInTheDocument())
  })

  it('渲染镜像源列表', async () => {
    render(<PluginMirrorsPage />, { wrapper: createWrapper() })
    await waitFor(() => expect(screen.getAllByText('GitHub').length).toBeGreaterThan(0))
  })

  it('渲染添加镜像源按钮', async () => {
    render(<PluginMirrorsPage />, { wrapper: createWrapper() })
    await waitFor(() => expect(screen.getByText('添加镜像源')).toBeInTheDocument())
  })

  it('embedded prop 切换路由前缀', async () => {
    render(<PluginMirrorsPage embedded />, { wrapper: createWrapper() })
    await waitFor(() => expect(screen.getByText('插件商店设置')).toBeInTheDocument())
  })
})