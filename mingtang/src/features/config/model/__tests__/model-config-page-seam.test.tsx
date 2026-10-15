import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createElement, type ReactNode } from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ModelConfigPage } from '../index'
import { ConfigRevisionConflictError } from '@/lib/config-api'
import { ApiError } from '@/lib/http'

const { getModelConfigMock, readConfigPathsMock, mutateConfigMock } = vi.hoisted(() => ({
  getModelConfigMock: vi.fn(),
  readConfigPathsMock: vi.fn(),
  mutateConfigMock: vi.fn(),
}))

vi.mock('@/lib/config-api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/config-api')>()
  return {
    ...actual,
    getModelConfig: getModelConfigMock,
    readConfigPaths: readConfigPathsMock,
    mutateConfig: mutateConfigMock,
    testProviderConnection: vi.fn(),
    testModelCapability: vi.fn(),
  }
})

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: 'zh-CN' } }),
}))

const SERVER_CONFIG = {
  api_providers: [
    { name: 'DeepSeek', base_url: 'https://api.deepseek.com', api_key: 'sk-PLAINTEXT' },
    { name: 'Alibaba', base_url: 'https://dashscope.aliyuncs.com', api_key: 'sk-PLAINTEXT-2' },
  ],
  models: [{ name: 'deepseek-chat', api_provider: 'DeepSeek', model_identifier: 'deepseek-chat' }],
  model_task_config: { chat: { models: ['deepseek-chat'], temperature: 0.7 } },
}

const SEAM_ENTRIES = [
  {
    path: 'api_providers[0].api_key',
    value: { $secret: true, path: 'api_providers[0].api_key', set: true, kind: 'literal' },
    inherited: false,
    revision: 1,
  },
  {
    path: 'api_providers[1].api_key',
    value: { $secret: true, path: 'api_providers[1].api_key', set: true, kind: 'reference' },
    inherited: false,
    revision: 1,
  },
]

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return function TestWrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, children)
  }
}

async function renderPage() {
  render(<ModelConfigPage />, { wrapper: createWrapper() })
  await waitFor(() => expect(screen.getByTestId('provider-table')).toBeInTheDocument())
}

beforeEach(() => {
  getModelConfigMock.mockReset().mockResolvedValue(SERVER_CONFIG)
  readConfigPathsMock
    .mockReset()
    .mockResolvedValue({ namespace: 'model', revision: 1, entries: SEAM_ENTRIES })
  mutateConfigMock.mockReset().mockResolvedValue({
    namespace: 'model',
    revision: 2,
    applied: 1,
    message: "配置 'model' 已保存",
    needs_restart: true,
    restart_required_sections: ['model'],
    hot_reload: 'ok',
  })
})

describe('C · 页面上三态可区分（生产路径）', () => {
  it('两个提供商各自渲染密钥单元格，literal 与 reference 两态**长得不一样**', async () => {
    await renderPage()

    const first = screen.getByTestId('secret-field-api_providers[0].api_key')
    const second = screen.getByTestId('secret-field-api_providers[1].api_key')

    expect(first).toHaveAttribute('data-secret-state', 'configured-literal')
    expect(second).toHaveAttribute('data-secret-state', 'configured-reference')
    expect(screen.getByTestId('secret-state-api_providers[0].api_key')).toHaveTextContent('已配置')
    expect(screen.getByTestId('secret-state-api_providers[1].api_key')).toHaveTextContent(
      '已配置（环境变量引用）',
    )
  })

  it('接缝读没提到的路径 ⇒ 该行显示"未设置"（不是空输入框冒充的"未设置"）', async () => {
    readConfigPathsMock.mockResolvedValue({
      namespace: 'model',
      revision: 1,
      entries: [SEAM_ENTRIES[0]],
    })
    await renderPage()

    expect(screen.getByTestId('secret-field-api_providers[1].api_key')).toHaveAttribute(
      'data-secret-state',
      'unset',
    )
    expect(screen.getByTestId('secret-state-api_providers[1].api_key')).toHaveTextContent('未设置')
  })
})

describe('B · 页面写路径真的走 config/mutate（生产调用点）', () => {
  it('在密钥框里输入新值 → 点保存 → mutateConfig 收到**只含该路径**的 ops', async () => {
    await renderPage()

    fireEvent.change(screen.getByTestId('secret-input-api_providers[1].api_key'), {
      target: { value: 'sk-NEW-KEY' },
    })
    fireEvent.click(screen.getByTestId('model-save'))

    await waitFor(() => expect(mutateConfigMock).toHaveBeenCalledTimes(1))
    const params = mutateConfigMock.mock.calls[0][0]
    expect(params.namespace).toBe('model')
    expect(params.expectedRevision).toBe(1)
    expect(params.ops).toEqual([
      { op: 'set', path: 'api_providers[1].api_key', value: 'sk-NEW-KEY' },
    ])
  })

  it('页面里不出现密钥明文：旧读端点回了明文，但草稿摘掉它 ⇒ DOM 只有三态、输入框恒空', async () => {
    await renderPage()

    const secretInput = screen.getByTestId('secret-input-api_providers[0].api_key')
    expect(secretInput).toHaveValue('')
    expect(secretInput).toHaveAttribute('type', 'password')
    // 明文既不在 DOM 里，也不在任何属性上
    expect(document.body.textContent ?? '').not.toContain('sk-PLAINTEXT')
    expect(document.body.innerHTML).not.toContain('sk-PLAINTEXT')
  })

  it('没有改动时保存按钮是禁用的（不会凭空发请求）', async () => {
    await renderPage()
    expect(screen.getByTestId('model-save')).toBeDisabled()
    expect(mutateConfigMock).not.toHaveBeenCalled()
  })

  it('409 ⇒ 冲突横幅可见 + 「重新加载」按钮；点它触发重新拉取', async () => {
    await renderPage()
    mutateConfigMock.mockRejectedValueOnce(
      new ConfigRevisionConflictError('revision 冲突：期望 1，当前 9', {
        namespace: 'model',
        expectedRevision: 1,
        currentRevision: 9,
      }),
    )

    fireEvent.change(screen.getByTestId('secret-input-api_providers[0].api_key'), {
      target: { value: 'sk-X' },
    })
    fireEvent.click(screen.getByTestId('model-save'))

    await waitFor(() => expect(screen.getByTestId('model-revision-conflict')).toBeInTheDocument())
    expect(screen.getByTestId('model-revision-conflict')).toHaveTextContent('配置已被别处修改')
    expect(screen.getByTestId('model-revision-conflict')).toHaveTextContent('本次未保存')
    // 未写成功 ⇒ 不该出现成功文案；且没有第二次请求（不静默重试）
    expect(screen.queryByTestId('model-save-message')).not.toBeInTheDocument()
    expect(mutateConfigMock).toHaveBeenCalledTimes(1)

    const refetchBefore = readConfigPathsMock.mock.calls.length
    fireEvent.click(screen.getByTestId('model-reload-after-conflict'))
    await waitFor(() =>
      expect(readConfigPathsMock.mock.calls.length).toBeGreaterThan(refetchBefore),
    )
    await waitFor(() =>
      expect(screen.queryByTestId('model-revision-conflict')).not.toBeInTheDocument(),
    )
  })

  it('后端拒绝（400 认领被拒）⇒ 横幅显示原文，不当成功', async () => {
    await renderPage()
    const refusal = '秘密占位认领失败：占位指向的位置没有值（set: false）'
    mutateConfigMock.mockRejectedValueOnce(
      new ApiError(refusal, { status: 400, errorCode: 'PARAM_INVALID' }),
    )

    fireEvent.change(screen.getByTestId('secret-input-api_providers[0].api_key'), {
      target: { value: 'sk-X' },
    })
    fireEvent.click(screen.getByTestId('model-save'))

    await waitFor(() => expect(screen.getByTestId('model-save-error')).toBeInTheDocument())
    expect(screen.getByTestId('model-save-error')).toHaveTextContent(refusal)
    expect(screen.queryByTestId('model-save-message')).not.toBeInTheDocument()
  })
})
