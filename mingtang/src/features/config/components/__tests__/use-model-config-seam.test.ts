import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createElement, type ReactNode } from 'react'
import { act, renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useModelConfig } from '../use-model-config'
import { ConfigRevisionConflictError } from '@/lib/config-api'
// `ApiError` 住在 `@/lib/http`——本文件只 mock 了 `@/lib/config-api`，
// 所以这里拿到的是**真类**（`instanceof` 判断才有意义）
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

/**
 * 旧读端点回的**嵌套**配置——注意它把密钥明文也带回来了（那正是 2 段要治的洞，
 * 也是本任务要防的事：明文**不许**从草稿流进写请求）。
 */
const SERVER_CONFIG = {
  api_providers: [
    {
      name: 'DeepSeek',
      base_url: 'https://api.deepseek.com',
      api_key: 'sk-REAL-PLAINTEXT-SHOULD-NEVER-BE-SENT',
    },
    { name: 'Alibaba', base_url: 'https://dashscope.aliyuncs.com', api_key: 'sk-ALSO-PLAINTEXT' },
  ],
  models: [{ name: 'deepseek-chat', api_provider: 'DeepSeek', model_identifier: 'deepseek-chat' }],
  model_task_config: { chat: { models: ['deepseek-chat'], temperature: 0.7 } },
}

/** 接缝读：`revision` + 秘密三态（`Alibaba` 未配置 ⇒ 该路径**压根不在 entries 里**） */
function seamSnapshot(revision: number) {
  return {
    namespace: 'model' as const,
    revision,
    entries: [
      { path: 'api_providers[0].name', value: 'DeepSeek', inherited: false, revision },
      {
        path: 'api_providers[0].api_key',
        value: { $secret: true, path: 'api_providers[0].api_key', set: true, kind: 'literal' },
        inherited: false,
        revision,
      },
      { path: 'api_providers[1].name', value: 'Alibaba', inherited: false, revision },
      {
        path: 'api_providers[1].api_key',
        value: { $secret: true, path: 'api_providers[1].api_key', set: true, kind: 'reference' },
        inherited: false,
        revision,
      },
    ],
  }
}

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return function TestWrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, children)
  }
}

async function renderLoadedHook() {
  const view = renderHook(() => useModelConfig(), { wrapper: createWrapper() })
  await waitFor(() => expect(view.result.current.providers).toHaveLength(2))
  await waitFor(() => expect(view.result.current.seamRevision).toBe(1))
  return view
}

beforeEach(() => {
  getModelConfigMock.mockReset().mockResolvedValue(SERVER_CONFIG)
  readConfigPathsMock.mockReset().mockResolvedValue(seamSnapshot(1))
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

describe('B · 写路径迁到 config/mutate（只发改动的点）', () => {
  it('改一个字段 ⇒ ops 只有那一条，带读到的 expectedRevision', async () => {
    const { result } = await renderLoadedHook()

    act(() => result.current.updateProvider(0, { ...result.current.providers[0], base_url: 'https://x' }))
    await act(async () => {
      await result.current.saveConfig()
    })

    expect(mutateConfigMock).toHaveBeenCalledTimes(1)
    const params = mutateConfigMock.mock.calls[0][0]
    expect(params.namespace).toBe('model')
    expect(params.expectedRevision).toBe(1)
    expect(params.ops).toEqual([
      { op: 'set', path: 'api_providers[0].base_url', value: 'https://x' },
    ])
  })

  it('**不把整份覆盖语义带过来**：ops 里没有整棵子树，也没点名未改动的字段', async () => {
    const { result } = await renderLoadedHook()

    act(() => result.current.updateProvider(0, { ...result.current.providers[0], name: 'Renamed' }))
    await act(async () => {
      await result.current.saveConfig()
    })

    const ops = mutateConfigMock.mock.calls[0][0].ops as Array<{ path: string }>
    expect(ops.map((op) => op.path)).toEqual(['api_providers[0].name'])
    expect(ops.some((op) => op.path === 'api_providers')).toBe(false)
    expect(ops.some((op) => op.path === 'models')).toBe(false)
    expect(ops.some((op) => op.path === 'model_task_config')).toBe(false)
  })

  it('旧读端点回的密钥明文**绝不进写请求**（未触碰 ⇒ 一个 op 都不发）', async () => {
    const { result } = await renderLoadedHook()

    // 加载后草稿里就不该留着明文
    expect(result.current.providers[0].api_key).toBeUndefined()

    act(() => result.current.updateProvider(0, { ...result.current.providers[0], base_url: 'https://x' }))
    await act(async () => {
      await result.current.saveConfig()
    })

    const payload = JSON.stringify(mutateConfigMock.mock.calls[0][0])
    expect(payload).not.toContain('sk-REAL-PLAINTEXT-SHOULD-NEVER-BE-SENT')
    expect(payload).not.toContain('sk-ALSO-PLAINTEXT')
    expect(payload).not.toContain('api_key')
  })

  it('用户输入新密钥 ⇒ 只为那一条发 set（替换语义）', async () => {
    const { result } = await renderLoadedHook()

    act(() =>
      result.current.updateProvider(1, { ...result.current.providers[1], api_key: 'sk-NEW-KEY' }),
    )
    await act(async () => {
      await result.current.saveConfig()
    })

    expect(mutateConfigMock.mock.calls[0][0].ops).toEqual([
      { op: 'set', path: 'api_providers[1].api_key', value: 'sk-NEW-KEY' },
    ])
  })

  it('没有改动 ⇒ 不发请求（空 ops 不会打到后端）', async () => {
    const { result } = await renderLoadedHook()

    await act(async () => {
      await result.current.saveConfig()
    })

    expect(mutateConfigMock).not.toHaveBeenCalled()
    expect(result.current.saveMessage).toBe('没有需要保存的改动')
  })

  it('保存成功后基线前移：再点一次保存不会把同样的 ops 重发', async () => {
    const { result } = await renderLoadedHook()

    act(() => result.current.updateProvider(0, { ...result.current.providers[0], name: 'Renamed' }))
    await act(async () => {
      await result.current.saveConfig()
    })
    expect(mutateConfigMock).toHaveBeenCalledTimes(1)

    await act(async () => {
      await result.current.saveConfig()
    })
    expect(mutateConfigMock).toHaveBeenCalledTimes(1)
    expect(result.current.saveMessage).toBe('没有需要保存的改动')
  })
})

describe('B · 409 冲突：可见、未写成功、不静默重试', () => {
  it('读 A → 别处写 B → 用 A 的 revision 写 ⇒ conflict 状态，且只发了一次请求', async () => {
    const { result } = await renderLoadedHook()

    mutateConfigMock.mockRejectedValueOnce(
      new ConfigRevisionConflictError('revision 冲突：期望 1，当前 9', {
        namespace: 'model',
        expectedRevision: 1,
        currentRevision: 9,
      }),
    )

    act(() => result.current.updateProvider(0, { ...result.current.providers[0], name: 'X' }))
    await act(async () => {
      await result.current.saveConfig()
    })

    expect(result.current.conflict).not.toBeNull()
    expect(result.current.conflict?.expectedRevision).toBe(1)
    expect(result.current.conflict?.currentRevision).toBe(9)
    // 未写成功：仍是脏的，且没有成功文案
    expect(result.current.hasUnsavedChanges).toBe(true)
    expect(result.current.saveMessage).toBeNull()
    // **不静默重试**：一次冲突只对应一次请求
    expect(mutateConfigMock).toHaveBeenCalledTimes(1)
  })

  it('「重新加载」后能正常写：用刷新到的 revision，用户的改动仍在草稿里', async () => {
    const { result } = await renderLoadedHook()

    mutateConfigMock.mockRejectedValueOnce(
      new ConfigRevisionConflictError('冲突', {
        namespace: 'model',
        expectedRevision: 1,
        currentRevision: 9,
      }),
    )
    act(() => result.current.updateProvider(0, { ...result.current.providers[0], name: 'X' }))
    await act(async () => {
      await result.current.saveConfig()
    })
    expect(result.current.conflict).not.toBeNull()

    // 服务端已经是 9；重载后 revision 跟上，冲突态清掉
    readConfigPathsMock.mockResolvedValue(seamSnapshot(9))
    mutateConfigMock.mockResolvedValueOnce({
      namespace: 'model',
      revision: 10,
      applied: 1,
      message: 'ok',
      needs_restart: false,
      restart_required_sections: [],
      hot_reload: null,
    })
    await act(async () => {
      await result.current.reloadFromServer()
    })
    await waitFor(() => expect(result.current.seamRevision).toBe(9))
    expect(result.current.conflict).toBeNull()

    await act(async () => {
      await result.current.saveConfig()
    })

    expect(mutateConfigMock).toHaveBeenCalledTimes(2)
    expect(mutateConfigMock.mock.calls[1][0].expectedRevision).toBe(9)
    expect(result.current.saveMessage).toBe('ok')
  })
})

describe('C · 秘密三态与拒绝可见（数据侧）', () => {
  it('三态按标记判定：literal / reference / 未在 entries 里 ⇒ unset', async () => {
    readConfigPathsMock.mockResolvedValue({
      namespace: 'model',
      revision: 1,
      entries: [
        {
          path: 'api_providers[0].api_key',
          value: { $secret: true, path: 'api_providers[0].api_key', set: true, kind: 'literal' },
          inherited: false,
          revision: 1,
        },
      ],
    })
    const { result } = await renderLoadedHook()

    expect(result.current.providerSecretStates).toEqual(['configured-literal', 'unset'])
  })

  it('后端拒绝（400 占位认领被拒）⇒ saveError 保留原文，不吞、不误报成功', async () => {
    const { result } = await renderLoadedHook()
    const refusal = '秘密占位认领失败：占位指向的位置没有值（set: false）'
    mutateConfigMock.mockRejectedValueOnce(
      new ApiError(refusal, { status: 400, errorCode: 'PARAM_INVALID' }),
    )

    act(() =>
      result.current.updateProvider(0, { ...result.current.providers[0], api_key: 'sk-NEW' }),
    )
    await act(async () => {
      await result.current.saveConfig()
    })

    expect(result.current.saveError).toBe(refusal)
    expect(result.current.conflict).toBeNull()
    expect(result.current.hasUnsavedChanges).toBe(true)
    expect(result.current.saveMessage).toBeNull()
  })

  it('revision 尚未就绪时**拒绝盲写**（乐观锁不是可选项）', async () => {
    readConfigPathsMock.mockRejectedValue(new ApiError('读取配置失败', { status: 500 }))
    const view = renderHook(() => useModelConfig(), { wrapper: createWrapper() })
    await waitFor(() => expect(view.result.current.providers).toHaveLength(2))

    await act(async () => {
      await view.result.current.saveConfig()
    })

    expect(mutateConfigMock).not.toHaveBeenCalled()
    expect(view.result.current.saveError).toContain('重新加载')
  })
})
