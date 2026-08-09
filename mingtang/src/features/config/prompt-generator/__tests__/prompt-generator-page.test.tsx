import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createElement, type ReactNode } from 'react'
import { PromptGeneratorPage } from '../index'

vi.mock('@/lib/prompt-generator-api', () => ({
  generatePromptPersona: vi.fn().mockResolvedValue({ config_blocks: [], toml_snippet: '', raw_response: '', prompt_tokens: 0, completion_tokens: 0, total_tokens: 0 }),
  applyPromptGeneratorBlocks: vi.fn().mockResolvedValue({ message: 'ok', applied_blocks: 0, sections: [] }),
}))

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }))

function createWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return function TestWrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: qc }, children)
  }
}

describe('R2-3-8：/config/prompt-generator 人设生成器页', () => {
  beforeEach(() => vi.clearAllMocks())

  it('渲染 PageShell + 标题', () => {
    render(<PromptGeneratorPage />, { wrapper: createWrapper() })
    expect(screen.getByTestId('page-shell')).toBeInTheDocument()
    expect(screen.getByText('sidebar.menu.promptGenerator')).toBeInTheDocument()
  })

  it('左栏输入面板渲染', () => {
    render(<PromptGeneratorPage />, { wrapper: createWrapper() })
    expect(screen.getByTestId('pg-input-panel')).toBeInTheDocument()
  })

  it('右栏结果面板渲染', () => {
    render(<PromptGeneratorPage />, { wrapper: createWrapper() })
    expect(screen.getByTestId('pg-result-panel')).toBeInTheDocument()
  })

  it('结果三 tab 渲染', () => {
    render(<PromptGeneratorPage />, { wrapper: createWrapper() })
    expect(screen.getByTestId('pg-tab-blocks')).toBeInTheDocument()
    expect(screen.getByTestId('pg-tab-toml')).toBeInTheDocument()
    expect(screen.getByTestId('pg-tab-raw')).toBeInTheDocument()
  })
})