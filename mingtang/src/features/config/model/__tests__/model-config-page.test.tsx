import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createElement, type ReactNode } from 'react'
import { ModelConfigPage } from '../index'

const { mockConfigData } = vi.hoisted(() => ({
  mockConfigData: {
    api_providers: [
      { name: 'deepseek', base_url: 'https://api.deepseek.com', api_key: 'sk-***' },
    ],
    models: [
      { name: 'deepseek-chat', api_provider: 'deepseek', model_identifier: 'deepseek-chat' },
    ],
    model_task_config: {
      chat: { models: ['deepseek-chat'], temperature: 0.7, max_tokens: 4096 },
    },
  },
}))

vi.mock('@/lib/config-api', () => ({
  getModelConfig: vi.fn().mockResolvedValue(mockConfigData),
  updateModelConfig: vi.fn().mockResolvedValue({ success: true, message: 'ok', needs_restart: false, restart_required_sections: [] }),
  updateModelConfigSection: vi.fn().mockResolvedValue({ success: true, message: 'ok', needs_restart: false, restart_required_sections: [] }),
  testProviderConnection: vi.fn().mockResolvedValue({ network_ok: true, api_key_valid: true, latency_ms: 100, error: null, http_status: 200 }),
  testModelCapability: vi.fn().mockResolvedValue({ success: true, model_name: 'test', visual_tested: false, tool_call_ok: true, response: '', reasoning: '', tool_calls: [], latency_ms: 50, error: null, prompt_tokens: 0, completion_tokens: 0, total_tokens: 0 }),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return function TestWrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, children)
  }
}

describe('R2-3-4：/config/model 模型配置页', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('渲染 PageShell + 标题', async () => {
    render(<ModelConfigPage />, { wrapper: createWrapper() })
    expect(screen.getByTestId('page-shell')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText('sidebar.menu.modelManagement')).toBeInTheDocument())
  })

  it('三 tab 渲染（厂商/模型/任务）', async () => {
    render(<ModelConfigPage />, { wrapper: createWrapper() })
    await waitFor(() => expect(screen.getByTestId('model-tabs')).toBeInTheDocument())
    expect(screen.getByTestId('model-tab-providers')).toBeInTheDocument()
    expect(screen.getByTestId('model-tab-models')).toBeInTheDocument()
    expect(screen.getByTestId('model-tab-tasks')).toBeInTheDocument()
  })

  it('Tab1 厂商——表格 + 搜索 + 添加按钮', async () => {
    render(<ModelConfigPage />, { wrapper: createWrapper() })
    await waitFor(() => expect(screen.getByTestId('model-providers-tab')).toBeInTheDocument())
    expect(screen.getByTestId('provider-table')).toBeInTheDocument()
    expect(screen.getByTestId('provider-search')).toBeInTheDocument()
    expect(screen.getByTestId('provider-add')).toBeInTheDocument()
  })

  it('Tab1 厂商——数据行渲染', async () => {
    render(<ModelConfigPage />, { wrapper: createWrapper() })
    await waitFor(() => expect(screen.getByTestId('provider-row-0')).toBeInTheDocument())
    expect(screen.getByText('deepseek')).toBeInTheDocument()
  })

  it('切换到 Tab2 模型', async () => {
    render(<ModelConfigPage />, { wrapper: createWrapper() })
    await waitFor(() => expect(screen.getByTestId('model-tab-models')).toBeInTheDocument())
    fireEvent.click(screen.getByTestId('model-tab-models'))
    expect(screen.getByTestId('model-models-tab')).toBeInTheDocument()
    expect(screen.getByTestId('model-table')).toBeInTheDocument()
  })

  it('切换到 Tab3 任务', async () => {
    render(<ModelConfigPage />, { wrapper: createWrapper() })
    await waitFor(() => expect(screen.getByTestId('model-tab-tasks')).toBeInTheDocument())
    fireEvent.click(screen.getByTestId('model-tab-tasks'))
    expect(screen.getByTestId('model-tasks-tab')).toBeInTheDocument()
  })

  it('保存按钮渲染', async () => {
    render(<ModelConfigPage />, { wrapper: createWrapper() })
    await waitFor(() => expect(screen.getByTestId('model-save')).toBeInTheDocument())
  })
})