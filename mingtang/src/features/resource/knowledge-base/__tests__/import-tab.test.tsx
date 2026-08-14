/**
 * ImportTab 组件测试（R4-2-10）
 *
 * 核心验证：
 * - 渲染基本结构（创建导入任务卡片 + 导入队列卡片）
 * - 核心交互（点击"创建导入任务" → submitImportByMode）
 * - 加载态（creatingImport: true → 按钮禁用）
 * - 错误态（importErrorText 非空 → Alert 局部呈现）
 * - 空态（任务列表为空 → 空态文案）
 *
 * 模式：props 注入 mock hook 结果（R4-1 教训 #6/#7）
 */
import type { ReactNode } from 'react'

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { Tabs } from '@/components/ui/tabs'

import type { UseImportFormResult } from '../hooks/useImportForm'
import type { UseImportQueueResult } from '../hooks/useImportQueue'
import { ImportTab } from '../tabs/import/ImportTab'

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

function renderImportTab(queue: UseImportQueueResult, form: UseImportFormResult) {
  return render(
    <Tabs value="import">
      <ImportTab queue={queue} form={form} />
    </Tabs>,
    { wrapper: makeWrapper() },
  )
}

function makeMockQueue(overrides: Partial<UseImportQueueResult> = {}): UseImportQueueResult {
  return {
    refreshImportQueue: vi.fn(),
    runningImportTasks: [],
    queuedImportTasks: [],
    recentImportTasks: [],
    selectedImportTaskId: '',
    selectImportTask: vi.fn(),
    importAutoPolling: true,
    setImportAutoPolling: vi.fn(),
    importPollInterval: 1000,
    importErrorText: '',
    cancelSelectedImportTask: vi.fn(),
    retrySelectedImportTask: vi.fn(),
    selectedImportTaskLoading: false,
    selectedImportTaskResolved: null,
    selectedImportRetrySummary: null,
    selectedImportTaskErrorText: '',
    selectedImportFiles: [],
    selectedImportFileId: '',
    selectImportFile: vi.fn(),
    importChunkTotal: 0,
    importChunkOffset: 0,
    moveImportChunkPage: vi.fn(),
    canImportChunkPrev: false,
    canImportChunkNext: false,
    importChunksLoading: false,
    selectedImportChunks: [],
    afterCreated: vi.fn(),
    invalidate: vi.fn(),
    ...overrides,
  }
}

function makeMockForm(overrides: Partial<UseImportFormResult> = {}): UseImportFormResult {
  return {
    importCreateMode: 'upload',
    setImportCreateMode: vi.fn(),
    importSettings: {},
    importChatTargets: [],
    importCommonFileConcurrency: '2',
    setImportCommonFileConcurrency: vi.fn(),
    importCommonChunkConcurrency: '4',
    setImportCommonChunkConcurrency: vi.fn(),
    importCommonNarrativeWindowSize: '1600',
    setImportCommonNarrativeWindowSize: vi.fn(),
    importCommonNarrativeOverlap: '400',
    setImportCommonNarrativeOverlap: vi.fn(),
    importCommonFactualTargetSize: '1200',
    setImportCommonFactualTargetSize: vi.fn(),
    importCommonLlmEnabled: true,
    setImportCommonLlmEnabled: vi.fn(),
    importCommonStrategyOverride: '',
    setImportCommonStrategyOverride: vi.fn(),
    importCommonDedupePolicy: '',
    setImportCommonDedupePolicy: vi.fn(),
    importCommonChatLog: false,
    setImportCommonChatLog: vi.fn(),
    importCommonChatId: '',
    setImportCommonChatId: vi.fn(),
    importCommonChatReferenceTime: '',
    setImportCommonChatReferenceTime: vi.fn(),
    importCommonForce: false,
    setImportCommonForce: vi.fn(),
    importCommonClearManifest: false,
    setImportCommonClearManifest: vi.fn(),
    uploadInputMode: 'text',
    setUploadInputMode: vi.fn(),
    uploadFiles: [],
    setUploadFiles: vi.fn(),
    pasteName: '',
    setPasteName: vi.fn(),
    pasteMode: 'text',
    setPasteMode: vi.fn(),
    pasteContent: '',
    setPasteContent: vi.fn(),
    rawAlias: '',
    setRawAlias: vi.fn(),
    rawInputMode: 'text',
    setRawInputMode: vi.fn(),
    rawRelativePath: '',
    setRawRelativePath: vi.fn(),
    rawGlob: '',
    setRawGlob: vi.fn(),
    rawRecursive: false,
    setRawRecursive: vi.fn(),
    openieAlias: '',
    setOpenieAlias: vi.fn(),
    openieRelativePath: '',
    setOpenieRelativePath: vi.fn(),
    openieIncludeAllJson: false,
    setOpenieIncludeAllJson: vi.fn(),
    convertAlias: '',
    setConvertAlias: vi.fn(),
    convertTargetAlias: '',
    setConvertTargetAlias: vi.fn(),
    convertRelativePath: '',
    setConvertRelativePath: vi.fn(),
    convertTargetRelativePath: '',
    setConvertTargetRelativePath: vi.fn(),
    convertDimension: '1024',
    setConvertDimension: vi.fn(),
    convertBatchSize: '100',
    setConvertBatchSize: vi.fn(),
    backfillAlias: '',
    setBackfillAlias: vi.fn(),
    backfillLimit: '1000',
    setBackfillLimit: vi.fn(),
    backfillRelativePath: '',
    setBackfillRelativePath: vi.fn(),
    backfillDryRun: false,
    setBackfillDryRun: vi.fn(),
    backfillNoCreatedFallback: false,
    setBackfillNoCreatedFallback: vi.fn(),
    maibotSourceDb: 'data/MaiBot.db',
    setMaibotSourceDb: vi.fn(),
    maibotTimeFrom: '',
    setMaibotTimeFrom: vi.fn(),
    maibotTimeTo: '',
    setMaibotTimeTo: vi.fn(),
    maibotStartId: '',
    setMaibotStartId: vi.fn(),
    maibotEndId: '',
    setMaibotEndId: vi.fn(),
    maibotStreamIds: '',
    setMaibotStreamIds: vi.fn(),
    maibotGroupIds: '',
    setMaibotGroupIds: vi.fn(),
    maibotUserIds: '',
    setMaibotUserIds: vi.fn(),
    maibotReadBatchSize: '500',
    setMaibotReadBatchSize: vi.fn(),
    maibotCommitWindowRows: '1000',
    setMaibotCommitWindowRows: vi.fn(),
    maibotEmbedWorkers: '4',
    setMaibotEmbedWorkers: vi.fn(),
    maibotNoResume: false,
    setMaibotNoResume: vi.fn(),
    maibotResetState: false,
    setMaibotResetState: vi.fn(),
    maibotDryRun: false,
    setMaibotDryRun: vi.fn(),
    maibotVerifyOnly: false,
    setMaibotVerifyOnly: vi.fn(),
    submitImportByMode: vi.fn(),
    creatingImport: false,
    buildCommonImportPayload: vi.fn(() => ({})),
    pathResolveAlias: '',
    setPathResolveAlias: vi.fn(),
    importAliasKeys: [],
    pathResolveRelativePath: '',
    setPathResolveRelativePath: vi.fn(),
    pathResolveMustExist: false,
    setPathResolveMustExist: vi.fn(),
    resolveImportPath: vi.fn(),
    resolvingPath: false,
    pathResolveOutput: '',
    ...overrides,
  }
}

describe('R4-2-10 ImportTab', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('渲染基本结构：创建导入任务 + 导入队列 + 任务详情', () => {
    renderImportTab(makeMockQueue(), makeMockForm())
    // "创建导入任务"同时出现在 CardTitle 和按钮中（双视图——getAllByText）
    expect(screen.getAllByText('创建导入任务').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('导入队列')).toBeInTheDocument()
    expect(screen.getByText('任务详情')).toBeInTheDocument()
    expect(screen.getByText('路径预检')).toBeInTheDocument()
  })

  it('核心交互：点击"创建导入任务" → submitImportByMode 调用', () => {
    const form = makeMockForm()
    renderImportTab(makeMockQueue(), form)
    // 双视图：创建导入任务卡片和任务详情卡片都有"创建导入任务"相关按钮
    // 创建导入任务卡片内的按钮文本是"创建导入任务"
    const buttons = screen.getAllByRole('button', { name: /创建导入任务/ })
    fireEvent.click(buttons[0])
    expect(form.submitImportByMode).toHaveBeenCalledTimes(1)
  })

  it('加载态：creatingImport: true → 创建按钮禁用', () => {
    const form = makeMockForm({ creatingImport: true })
    renderImportTab(makeMockQueue(), form)
    const buttons = screen.getAllByRole('button', { name: /创建导入任务/ })
    expect(buttons[0]).toBeDisabled()
  })

  it('错误态：importErrorText 非空 → Alert 局部呈现', () => {
    const queue = makeMockQueue({ importErrorText: '刷新导入任务失败' })
    renderImportTab(queue, makeMockForm())
    expect(screen.getByText('刷新导入任务失败')).toBeInTheDocument()
  })

  it('空态：任务列表为空 → 空态文案呈现', () => {
    renderImportTab(makeMockQueue(), makeMockForm())
    // 运行中 / 排队中 / 最近完成 三处空态
    expect(screen.getByText('当前没有运行中任务')).toBeInTheDocument()
    expect(screen.getByText('当前没有排队任务')).toBeInTheDocument()
    expect(screen.getByText('暂时没有历史任务')).toBeInTheDocument()
  })
})