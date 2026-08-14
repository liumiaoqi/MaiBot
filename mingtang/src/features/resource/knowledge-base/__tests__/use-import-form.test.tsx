/**
 * useImportForm hook 测试（R4-2-5）
 *
 * 核心验证：
 * - settings/aliases/chat-targets 仅在 active 时拉取（enabled: active 门控）
 * - settings seed：服务端默认值到达后回填通用参数
 * - 别名联动：alias 到达后各模式 alias 字段自动选第一个可用别名
 * - submitImportByMode (upload) 成功 → createMemoryUploadImport + onCreated + toast.success
 * - submitImportByMode (upload) 无文件 → toast.error
 *
 * R4 债清理 P1 增补（安全网——为后续重构提供 golden 基线）：
 * - 其余 6 模式（paste/raw_scan/lpmm_openie/lpmm_convert/temporal_backfill/maibot_migration）
 *   的 submit payload 逐字段 golden 断言（active: false 下默认值确定、不受 settings seed 干扰）
 * - maibot_migration 校验分支（空 source_db / 时间倒挂 / ID 倒挂 → 不调 API + toast.error）
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
  createMemoryLpmmConvertImport,
  createMemoryLpmmOpenieImport,
  createMemoryMaibotMigrationImport,
  createMemoryPasteImport,
  createMemoryRawScanImport,
  createMemoryTemporalBackfillImport,
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

describe('R4-P1 其余 6 模式 submit payload golden', () => {
  // 模块级 mock fn 跨测试累积调用记录——每个测试前清空，保证 mock.calls[0] 是本测试的调用
  beforeEach(() => {
    vi.clearAllMocks()
  })

  // active: false —— settings/aliases 不拉取 → 无 seed/无别名联动 → 表单字段保持初始默认值，
  // golden 断言完全确定（不受 mock settings 影响）。
  async function renderInactiveForm() {
    const onCreated = vi.fn().mockResolvedValue(undefined)
    const successSpy = vi.spyOn(toast, 'success').mockImplementation(() => 'id')
    const errorSpy = vi.spyOn(toast, 'error').mockImplementation(() => 'id')
    const { result } = renderHook(() => useImportForm({ active: false, onCreated }), {
      wrapper: makeWrapper(),
    })
    return { onCreated, successSpy, errorSpy, result }
  }

  // 初始默认值下的公共导入参数（buildCommonImportPayload 输出）
  function commonGoldenPayload(): Record<string, unknown> {
    return {
      llm_enabled: true,
      strategy_override: 'auto',
      dedupe_policy: 'content_hash',
      chat_log: false,
      force: false,
      clear_manifest: false,
      file_concurrency: 2,
      chunk_concurrency: 4,
      narrative_window_size: 1600,
      narrative_overlap: 400,
      factual_target_size: 1200,
    }
  }

  it('paste：payload 含公共参数 + name/content/input_mode', async () => {
    const { result } = await renderInactiveForm()
    act(() => {
      result.current.setImportCreateMode('paste')
      result.current.setPasteName('我的笔记')
      result.current.setPasteMode('json')
      result.current.setPasteContent('{"hello":"world"}')
    })
    await act(async () => {
      await result.current.submitImportByMode()
    })
    expect(vi.mocked(createMemoryPasteImport)).toHaveBeenCalledWith({
      ...commonGoldenPayload(),
      name: '我的笔记',
      content: '{"hello":"world"}',
      input_mode: 'json',
    })
  })

  it('paste：name 为空时 payload 的 name 为 undefined（不携带名字）', async () => {
    const { result } = await renderInactiveForm()
    act(() => {
      result.current.setImportCreateMode('paste')
      result.current.setPasteName('')
      result.current.setPasteContent('只有内容')
    })
    await act(async () => {
      await result.current.submitImportByMode()
    })
    const payload = vi.mocked(createMemoryPasteImport).mock.calls[0][0]
    expect(payload).toMatchObject({
      ...commonGoldenPayload(),
      content: '只有内容',
      input_mode: 'text',
    })
    expect(payload).toHaveProperty('name')
    expect(payload.name).toBeUndefined()
  })

  it('raw_scan：payload 含公共参数 + alias/relative_path/glob/recursive/input_mode', async () => {
    const { result } = await renderInactiveForm()
    act(() => {
      result.current.setImportCreateMode('raw_scan')
      result.current.setRawAlias('raw')
      result.current.setRawRelativePath('memories/raw')
      result.current.setRawGlob('**/*.md')
      result.current.setRawRecursive(false)
      result.current.setRawInputMode('json')
    })
    await act(async () => {
      await result.current.submitImportByMode()
    })
    expect(vi.mocked(createMemoryRawScanImport)).toHaveBeenCalledWith({
      ...commonGoldenPayload(),
      alias: 'raw',
      relative_path: 'memories/raw',
      glob: '**/*.md',
      recursive: false,
      input_mode: 'json',
    })
  })

  it('lpmm_openie：payload 含公共参数 + alias/relative_path/include_all_json（无 input_mode）', async () => {
    const { result } = await renderInactiveForm()
    act(() => {
      result.current.setImportCreateMode('lpmm_openie')
      result.current.setOpenieAlias('lpmm')
      result.current.setOpenieRelativePath('lpmm/out')
      result.current.setOpenieIncludeAllJson(true)
    })
    await act(async () => {
      await result.current.submitImportByMode()
    })
    expect(vi.mocked(createMemoryLpmmOpenieImport)).toHaveBeenCalledWith({
      ...commonGoldenPayload(),
      alias: 'lpmm',
      relative_path: 'lpmm/out',
      include_all_json: true,
    })
    // openie 模式不携带 input_mode / 公共文件参数字段之外的额外键
    const payload = vi.mocked(createMemoryLpmmOpenieImport).mock.calls[0][0]
    expect(payload).not.toHaveProperty('input_mode')
  })

  it('lpmm_convert：payload 只含转换字段（不带公共参数）', async () => {
    const { result } = await renderInactiveForm()
    act(() => {
      result.current.setImportCreateMode('lpmm_convert')
      result.current.setConvertAlias('lpmm')
      result.current.setConvertRelativePath('lpmm/in')
      result.current.setConvertTargetAlias('plugin_data')
      result.current.setConvertTargetRelativePath('plugin/out')
      result.current.setConvertDimension('128')
      result.current.setConvertBatchSize('2048')
    })
    await act(async () => {
      await result.current.submitImportByMode()
    })
    expect(vi.mocked(createMemoryLpmmConvertImport)).toHaveBeenCalledWith({
      alias: 'lpmm',
      relative_path: 'lpmm/in',
      target_alias: 'plugin_data',
      target_relative_path: 'plugin/out',
      dimension: 128,
      batch_size: 2048,
    })
    const payload = vi.mocked(createMemoryLpmmConvertImport).mock.calls[0][0]
    expect(payload).not.toHaveProperty('llm_enabled')
  })

  it('lpmm_convert：dimension 为空时 payload 为 undefined（默认 batch_size=1024）', async () => {
    const { result } = await renderInactiveForm()
    act(() => {
      result.current.setImportCreateMode('lpmm_convert')
    })
    await act(async () => {
      await result.current.submitImportByMode()
    })
    const payload = vi.mocked(createMemoryLpmmConvertImport).mock.calls[0][0]
    expect(payload).toMatchObject({
      alias: 'lpmm',
      relative_path: '',
      target_alias: 'plugin_data',
      target_relative_path: '',
      batch_size: 1024,
    })
    expect(payload).toHaveProperty('dimension')
    expect(payload.dimension).toBeUndefined()
  })

  it('temporal_backfill：payload 只含回填字段（不带公共参数）', async () => {
    const { result } = await renderInactiveForm()
    act(() => {
      result.current.setImportCreateMode('temporal_backfill')
      result.current.setBackfillAlias('plugin_data')
      result.current.setBackfillRelativePath('plugin/backfill')
      result.current.setBackfillLimit('50000')
      result.current.setBackfillDryRun(true)
      result.current.setBackfillNoCreatedFallback(true)
    })
    await act(async () => {
      await result.current.submitImportByMode()
    })
    expect(vi.mocked(createMemoryTemporalBackfillImport)).toHaveBeenCalledWith({
      alias: 'plugin_data',
      relative_path: 'plugin/backfill',
      limit: 50000,
      dry_run: true,
      no_created_fallback: true,
    })
    const payload = vi.mocked(createMemoryTemporalBackfillImport).mock.calls[0][0]
    expect(payload).not.toHaveProperty('llm_enabled')
  })

  it('maibot_migration：完整 payload golden（时间转 ISO、ID/批大小转整数、逗号列表拆分）', async () => {
    const { result } = await renderInactiveForm()
    act(() => {
      result.current.setImportCreateMode('maibot_migration')
      result.current.setMaibotSourceDb('/data/maibot.db')
      result.current.setMaibotTimeFrom('2024-01-01T08:00:00')
      result.current.setMaibotTimeTo('2024-01-02T08:00:00')
      result.current.setMaibotStartId('100')
      result.current.setMaibotEndId('200')
      result.current.setMaibotStreamIds('s1, s2')
      result.current.setMaibotGroupIds('g1')
      result.current.setMaibotUserIds('u1,u2')
      result.current.setMaibotReadBatchSize('3000')
      result.current.setMaibotCommitWindowRows('15000')
      result.current.setMaibotEmbedWorkers('4')
      result.current.setMaibotNoResume(true)
      result.current.setMaibotResetState(false)
      result.current.setMaibotDryRun(true)
      result.current.setMaibotVerifyOnly(true)
    })
    await act(async () => {
      await result.current.submitImportByMode()
    })
    expect(vi.mocked(createMemoryMaibotMigrationImport)).toHaveBeenCalledWith({
      source_db: '/data/maibot.db',
      time_from: new Date('2024-01-01T08:00:00').toISOString(),
      time_to: new Date('2024-01-02T08:00:00').toISOString(),
      start_id: 100,
      end_id: 200,
      stream_ids: ['s1', 's2'],
      group_ids: ['g1'],
      user_ids: ['u1', 'u2'],
      read_batch_size: 3000,
      commit_window_rows: 15000,
      embed_workers: 4,
      no_resume: true,
      reset_state: false,
      dry_run: true,
      verify_only: true,
    })
  })

  it('maibot_migration：embed_workers 为空时 payload 为 undefined（默认批大小/窗口）', async () => {
    const { result } = await renderInactiveForm()
    act(() => {
      result.current.setImportCreateMode('maibot_migration')
      result.current.setMaibotSourceDb('/data/maibot.db')
    })
    await act(async () => {
      await result.current.submitImportByMode()
    })
    const payload = vi.mocked(createMemoryMaibotMigrationImport).mock.calls[0][0]
    expect(payload).toMatchObject({
      source_db: '/data/maibot.db',
      stream_ids: [],
      group_ids: [],
      user_ids: [],
      read_batch_size: 2000,
      commit_window_rows: 20000,
      no_resume: false,
      reset_state: false,
      dry_run: false,
      verify_only: false,
    })
    // 可选字段显式断言：键存在且值为 undefined（toMatchObject 对 undefined 不敏感）
    for (const key of ['time_from', 'time_to', 'start_id', 'end_id', 'embed_workers'] as const) {
      expect(payload).toHaveProperty(key)
      expect(payload[key]).toBeUndefined()
    }
  })

  it('maibot_migration：source_db 为空 → 不调 API + toast.error', async () => {
    const { errorSpy, result } = await renderInactiveForm()
    act(() => {
      result.current.setImportCreateMode('maibot_migration')
    })
    await act(async () => {
      await result.current.submitImportByMode()
    })
    expect(vi.mocked(createMemoryMaibotMigrationImport)).not.toHaveBeenCalled()
    expect(errorSpy).toHaveBeenCalledWith('请填写源数据库路径')
  })

  it('maibot_migration：起始时间晚于结束时间 → 不调 API + toast.error', async () => {
    const { errorSpy, result } = await renderInactiveForm()
    act(() => {
      result.current.setImportCreateMode('maibot_migration')
      result.current.setMaibotSourceDb('/data/maibot.db')
      result.current.setMaibotTimeFrom('2024-01-02T08:00:00')
      result.current.setMaibotTimeTo('2024-01-01T08:00:00')
    })
    await act(async () => {
      await result.current.submitImportByMode()
    })
    expect(vi.mocked(createMemoryMaibotMigrationImport)).not.toHaveBeenCalled()
    expect(errorSpy).toHaveBeenCalledWith('起始时间不能晚于结束时间')
  })

  it('maibot_migration：起始 ID 大于结束 ID → 不调 API + toast.error', async () => {
    const { errorSpy, result } = await renderInactiveForm()
    act(() => {
      result.current.setImportCreateMode('maibot_migration')
      result.current.setMaibotSourceDb('/data/maibot.db')
      result.current.setMaibotStartId('200')
      result.current.setMaibotEndId('100')
    })
    await act(async () => {
      await result.current.submitImportByMode()
    })
    expect(vi.mocked(createMemoryMaibotMigrationImport)).not.toHaveBeenCalled()
    expect(errorSpy).toHaveBeenCalledWith('起始 ID 不能大于结束 ID')
  })
})