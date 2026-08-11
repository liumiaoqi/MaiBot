/**
 * useImportForm hook 测试（R4-2-5）
 *
 * 核心验证：
 * - settings/aliases/chat-targets 仅在 active 时拉取（enabled: active 门控）
 * - settings seed：服务端默认值到达后回填通用参数
 * - 别名联动：alias 到达后各模式 alias 字段自动选第一个可用别名
 * - submitImportByMode (upload) 成功 → createMemoryUploadImport + onCreated + toast.success
 * - submitImportByMode (upload) 无文件 → toast.error
 */
import type { ReactNode } from 'react'

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { toast } from 'sonner'

vi.mock('@/lib/memory-api', () => ({
  getMemoryImportSettings: vi.fn(),
  getMemoryImportPathAliases: vi.fn(),
  getMemoryImportChatTargets: vi.fn(),
  createMemoryUploadImport: vi.fn(),
  createMemoryPasteImport: vi.fn(),
  createMemoryRawScanImport: vi.fn(),
  createMemoryLpmmOpenieImport: vi.fn(),
  createMemoryLpmmConvertImport: vi.fn(),
  createMemoryTemporalBackfillImport: vi.fn(),
  createMemoryMaibotMigrationImport: vi.fn(),
  resolveMemoryImportPath: vi.fn(),
}))

vi.mock('../utils', () => ({
  parseCommaSeparatedList: vi.fn((input: string) => input.split(',').map((s) => s.trim()).filter(Boolean)),
  parseOptionalNonNegativeInt: vi.fn((input: string) => {
    const n = Number(input)
    return Number.isFinite(n) && n >= 0 ? n : undefined
  }),
  parseOptionalPositiveInt: vi.fn((input: string) => {
    const n = Number(input)
    return Number.isFinite(n) && n > 0 ? n : undefined
  }),
}))

import {
  createMemoryUploadImport,
  getMemoryImportChatTargets,
  getMemoryImportPathAliases,
  getMemoryImportSettings,
  resolveMemoryImportPath,
} from '@/lib/memory-api'
import { useImportForm } from '../hooks/useImportForm'

function makeWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
  Wrapper.displayName = 'QueryWrapper'
  return Wrapper
}

const mockSettings = {
  settings: {
    default_file_concurrency: 4,
    default_chunk_concurrency: 8,
    default_narrative_window_size: 2000,
    default_narrative_overlap: 500,
    default_factual_target_size: 1500,
    maibot_source_db_default: '/data/maibot.db',
    poll_interval_ms: 1000,
  },
}

const mockPathAliases = {
  path_aliases: {
    raw: '/data/raw',
    lpmm: '/data/lpmm',
    plugin_data: '/data/plugin',
  },
}

const mockChatTargets = {
  data: [
    { chat_id: 'c1', chat_name: '测试聊天', is_group: false },
  ],
}

describe('R4-2-5 useImportForm', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(getMemoryImportSettings).mockResolvedValue(mockSettings)
    vi.mocked(getMemoryImportPathAliases).mockResolvedValue(mockPathAliases)
    vi.mocked(getMemoryImportChatTargets).mockResolvedValue(mockChatTargets)
    vi.mocked(createMemoryUploadImport).mockResolvedValue({ task: { task_id: 'new-task-1' } as never })
    vi.mocked(resolveMemoryImportPath).mockResolvedValue({
      alias: 'raw',
      relative_path: '',
      resolved_path: '/data/raw',
      exists: true,
      is_file: false,
      is_dir: true,
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('active: true 时拉取 settings + aliases + chat-targets', async () => {
    const onCreated = vi.fn().mockResolvedValue(undefined)
    const { result } = renderHook(() => useImportForm({ active: true, onCreated }), { wrapper: makeWrapper() })
    await waitFor(() => {
      expect(result.current.importAliasKeys).toHaveLength(3)
    })
    expect(getMemoryImportSettings).toHaveBeenCalled()
    expect(getMemoryImportPathAliases).toHaveBeenCalled()
    expect(getMemoryImportChatTargets).toHaveBeenCalled()
    expect(result.current.importChatTargets).toHaveLength(1)
  })

  it('active: false 时不拉取', () => {
    const onCreated = vi.fn().mockResolvedValue(undefined)
    renderHook(() => useImportForm({ active: false, onCreated }), { wrapper: makeWrapper() })
    expect(getMemoryImportSettings).not.toHaveBeenCalled()
    expect(getMemoryImportPathAliases).not.toHaveBeenCalled()
    expect(getMemoryImportChatTargets).not.toHaveBeenCalled()
  })

  it('settings seed：服务端默认值到达后回填通用参数', async () => {
    const onCreated = vi.fn().mockResolvedValue(undefined)
    const { result } = renderHook(() => useImportForm({ active: true, onCreated }), { wrapper: makeWrapper() })
    await waitFor(() => {
      expect(result.current.importCommonFileConcurrency).toBe('4')
    })
    expect(result.current.importCommonChunkConcurrency).toBe('8')
    expect(result.current.importCommonNarrativeWindowSize).toBe('2000')
    expect(result.current.maibotSourceDb).toBe('/data/maibot.db')
  })

  it('别名联动：importAliasKeys 排序后可用', async () => {
    const onCreated = vi.fn().mockResolvedValue(undefined)
    const { result } = renderHook(() => useImportForm({ active: true, onCreated }), { wrapper: makeWrapper() })
    await waitFor(() => {
      expect(result.current.importAliasKeys).toHaveLength(3)
    })
    // 排序后：lpmm, plugin_data, raw
    expect(result.current.importAliasKeys).toEqual(['lpmm', 'plugin_data', 'raw'])
    // rawAlias 初始为 'raw'，在可用列表中，保持不变
    expect(result.current.rawAlias).toBe('raw')
    // openieAlias 初始为 'lpmm'，在可用列表中，保持不变
    expect(result.current.openieAlias).toBe('lpmm')
  })

  it('submitImportByMode (upload) 无文件 → toast.error', async () => {
    const toastSpy = vi.spyOn(toast, 'error').mockImplementation(() => 'id')
    const onCreated = vi.fn().mockResolvedValue(undefined)
    const { result } = renderHook(() => useImportForm({ active: true, onCreated }), { wrapper: makeWrapper() })
    await waitFor(() => {
      expect(result.current.importAliasKeys).toHaveLength(3)
    })
    // upload 模式默认无文件
    await act(async () => {
      await result.current.submitImportByMode()
    })
    expect(toastSpy).toHaveBeenCalledWith('至少选择一个 txt/md/json 文件后再提交')
  })

  it('submitImportByMode (upload) 成功 → toast.success + onCreated', async () => {
    const toastSpy = vi.spyOn(toast, 'success').mockImplementation(() => 'id')
    const onCreated = vi.fn().mockResolvedValue(undefined)
    const { result } = renderHook(() => useImportForm({ active: true, onCreated }), { wrapper: makeWrapper() })
    await waitFor(() => {
      expect(result.current.importAliasKeys).toHaveLength(3)
    })
    // 设置上传文件
    const mockFile = new File(['test content'], 'test.txt', { type: 'text/plain' })
    act(() => {
      result.current.setUploadFiles([mockFile])
    })
    await act(async () => {
      await result.current.submitImportByMode()
    })
    expect(createMemoryUploadImport).toHaveBeenCalled()
    expect(onCreated).toHaveBeenCalledWith('new-task-1')
    expect(toastSpy).toHaveBeenCalledWith('任务 new-task-1 已加入导入队列')
  })

  it('resolveImportPath 成功 → pathResolveOutput 写入解析结果', async () => {
    const onCreated = vi.fn().mockResolvedValue(undefined)
    const { result } = renderHook(() => useImportForm({ active: true, onCreated }), { wrapper: makeWrapper() })
    await waitFor(() => {
      expect(result.current.importAliasKeys).toHaveLength(3)
    })
    await act(async () => {
      await result.current.resolveImportPath()
    })
    expect(resolveMemoryImportPath).toHaveBeenCalled()
    expect(result.current.pathResolveOutput).toContain('解析结果: /data/raw')
  })
})