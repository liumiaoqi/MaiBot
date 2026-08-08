import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createElement, type ReactNode } from 'react'
import { PromptManagementPage } from '../index'

vi.mock('@/lib/prompt-api', () => ({
  getPromptCatalog: vi.fn().mockResolvedValue({ languages: ['zh'], files: { zh: [{ name: 'personality', custom_version_count: 0 }] } }),
  getPromptFile: vi.fn().mockResolvedValue({ content: 'test content', language: 'zh', filename: 'personality', customized: false, active_version_id: null, versions: [], validation: { valid: true, missing_placeholders: [], extra_placeholders: [], message: '' } }),
  updatePromptFile: vi.fn().mockResolvedValue({}),
  getDefaultPromptFile: vi.fn(),
  resetPromptFile: vi.fn(),
  getPromptVersionFile: vi.fn(),
  activatePromptVersion: vi.fn(),
}))

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }))

function createWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: ReactNode }) => createElement(QueryClientProvider, { client: qc }, children)
}

describe('R2-3-5：/config/prompts Prompt 管理页', () => {
  beforeEach(() => vi.clearAllMocks())

  it('渲染 PageShell + 标题', async () => {
    render(<PromptManagementPage />, { wrapper: createWrapper() })
    expect(screen.getByTestId('page-shell')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText('sidebar.menu.promptManagement')).toBeInTheDocument())
  })

  it('语言选择渲染', async () => {
    render(<PromptManagementPage />, { wrapper: createWrapper() })
    await waitFor(() => expect(screen.getByTestId('prompts-lang-select')).toBeInTheDocument())
  })

  it('文件列表渲染', async () => {
    render(<PromptManagementPage />, { wrapper: createWrapper() })
    await waitFor(() => expect(screen.getByTestId('prompts-file-personality')).toBeInTheDocument())
  })

  it('选择文件后编辑器渲染', async () => {
    render(<PromptManagementPage />, { wrapper: createWrapper() })
    await waitFor(() => expect(screen.getByTestId('prompts-file-personality')).toBeInTheDocument())
    expect(screen.getByTestId('prompts-editor')).toBeInTheDocument()
  })
})