/**
 * 知识库管理主页面测试（R4-2-15）
 *
 * 核心验证：
 * - 渲染 4 tabs（import/tuning/delete/feedback）
 * - tab 切换
 * - 运行时概览区
 * - 深链接解析
 * - 页面三态（加载/错误/正常）
 * - 禁止 CorrectionTab（grep 零命中）
 * - 禁止 5 tabs（不含 graph/timeline/episodes/profiles/maintenance）
 * - 主题零黑字
 *
 * 模式：vi.mock hooks 注入 mock hook 结果（R4-1 教训 #6/#7）
 */
import type { ReactNode } from 'react'

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

// mock 所有 hooks —— 注入 mock hook 结果
vi.mock('../hooks/useMemoryRuntimeConfig', () => ({
  useMemoryRuntimeConfig: vi.fn(() => ({
    runtimeConfig: null,
    runtimeLoading: false,
    runtimeErrorText: '',
    refreshRuntimeConfig: vi.fn(),
    refreshingCheck: false,
    refreshSelfCheck: vi.fn(),
    vectorRebuildDialogOpen: false,
    setVectorRebuildDialogOpen: vi.fn(),
    vectorRebuildPreview: null,
    vectorRebuilding: false,
    openVectorRebuildDialog: vi.fn(),
    confirmVectorRebuild: vi.fn(),
  })),
}))

vi.mock('../hooks/useImportQueue', () => ({
  useImportQueue: vi.fn(() => ({
    refreshImportQueue: vi.fn(),
    runningImportTasks: [],
    queuedImportTasks: [],
    recentImportTasks: [],
    selectedImportTaskId: '',
    selectImportTask: vi.fn(),
    importAutoPolling: true,
    setImportAutoPolling: vi.fn(),
    importPollInterval: 2000,
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
  })),
}))

vi.mock('../hooks/useImportForm', () => ({
  useImportForm: vi.fn(() => ({
    importCreateMode: 'upload',
    setImportCreateMode: vi.fn(),
    importSettings: { aliases: [] },
    importChatTargets: [],
    importCommonFileConcurrency: '4',
    setImportCommonFileConcurrency: vi.fn(),
    importCommonChunkConcurrency: '4',
    setImportCommonChunkConcurrency: vi.fn(),
    importCommonNarrativeWindowSize: '50',
    setImportCommonNarrativeWindowSize: vi.fn(),
    importCommonNarrativeOverlap: '10',
    setImportCommonNarrativeOverlap: vi.fn(),
    importCommonFactualTargetSize: '20',
    setImportCommonFactualTargetSize: vi.fn(),
    importCommonLlmEnabled: true,
    setImportCommonLlmEnabled: vi.fn(),
    importCommonStrategyOverride: '',
    setImportCommonStrategyOverride: vi.fn(),
    importCommonDedupePolicy: 'skip',
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
    uploadInputMode: 'file',
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
    rawInputMode: 'file',
    setRawInputMode: vi.fn(),
    rawRelativePath: '',
    setRawRelativePath: vi.fn(),
    rawGlob: '',
    setRawGlob: vi.fn(),
    rawRecursive: true,
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
    convertDimension: '',
    setConvertDimension: vi.fn(),
    convertBatchSize: '',
    setConvertBatchSize: vi.fn(),
    backfillAlias: '',
    setBackfillAlias: vi.fn(),
    backfillLimit: '',
    setBackfillLimit: vi.fn(),
    backfillRelativePath: '',
    setBackfillRelativePath: vi.fn(),
    backfillDryRun: false,
    setBackfillDryRun: vi.fn(),
    backfillNoCreatedFallback: false,
    setBackfillNoCreatedFallback: vi.fn(),
    maibotSourceDb: '',
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
    submitUploadImport: vi.fn(),
    submitPasteImport: vi.fn(),
    submitRawScanImport: vi.fn(),
    submitOpenieImport: vi.fn(),
    submitConvertImport: vi.fn(),
    submitBackfillImport: vi.fn(),
    submitMaibotMigrationImport: vi.fn(),
    buildCommonImportPayload: vi.fn(() => ({})),
  })),
}))

vi.mock('../hooks/useMemoryDelete', () => ({
  useMemoryDelete: vi.fn(() => ({
    sourceSearch: '',
    setSourceSearch: vi.fn(),
    selectedSources: [],
    setSelectedSources: vi.fn(),
    filteredSources: [],
    openSourceDeletePreview: vi.fn(),
    toggleSourceSelection: vi.fn(),
    refreshSources: vi.fn(),
    operationSearch: '',
    setOperationSearch: vi.fn(),
    operationModeFilter: 'all',
    setOperationModeFilter: vi.fn(),
    operationStatusFilter: 'all',
    setOperationStatusFilter: vi.fn(),
    filteredDeleteOperations: [],
    deleteOperations: [],
    operationPage: 1,
    setOperationPage: vi.fn(),
    deleteOperationPageCount: 1,
    pagedDeleteOperations: [],
    selectedDeleteOperation: null,
    setSelectedOperationId: vi.fn(),
    restoreDeleteOperation: vi.fn(),
    deleteRestoring: false,
    selectedOperationCounts: {},
    selectedOperationDetailLoading: false,
    selectedOperationDetailError: '',
    selectedOperationSources: [],
    selectedOperationItems: [],
    filteredSelectedOperationItems: [],
    selectedOperationItemSearch: '',
    setSelectedOperationItemSearch: vi.fn(),
    selectedOperationItemPage: 1,
    setSelectedOperationItemPage: vi.fn(),
    selectedOperationItemPageCount: 1,
    pagedSelectedOperationItems: [],
    deleteDialogOpen: false,
    closeDeleteDialog: vi.fn(),
    deleteDialogTitle: '',
    deleteDialogDescription: '',
    deletePreview: null,
    deletePreviewError: null,
    deletePreviewLoading: false,
    deleteExecuting: false,
    deleteResult: null,
    executePendingDelete: vi.fn(),
    deleteErrorText: '',
  })),
}))

vi.mock('../hooks/useMemoryFeedback', () => ({
  useMemoryFeedback: vi.fn(() => ({
    feedbackSearch: '',
    setFeedbackSearch: vi.fn(),
    feedbackStatusFilter: 'all',
    setFeedbackStatusFilter: vi.fn(),
    feedbackRollbackFilter: 'all',
    setFeedbackRollbackFilter: vi.fn(),
    filteredFeedbackCorrections: [],
    feedbackCorrections: [],
    pagedFeedbackCorrections: [],
    feedbackPage: 1,
    setFeedbackPage: vi.fn(),
    feedbackPageCount: 1,
    selectedFeedbackCorrection: null,
    setSelectedFeedbackTaskId: vi.fn(),
    selectedFeedbackResolved: null,
    selectedFeedbackPreview: null,
    selectedFeedbackImpactSummary: [],
    openFeedbackRollbackDialog: vi.fn(),
    feedbackRollingBack: false,
    selectedFeedbackTaskLoading: false,
    selectedFeedbackTaskError: null,
    feedbackActionLogPage: 1,
    setFeedbackActionLogPage: vi.fn(),
    feedbackActionLogPageCount: 1,
    feedbackActionLogSearch: '',
    setFeedbackActionLogSearch: vi.fn(),
    pagedFeedbackActionLogs: [],
    selectedFeedbackActionLogs: [],
    feedbackRollbackDialogOpen: false,
    setFeedbackRollbackDialogOpen: vi.fn(),
    feedbackRollbackReason: '',
    setFeedbackRollbackReason: vi.fn(),
    executeFeedbackRollback: vi.fn(),
    feedbackErrorText: '',
  })),
}))

vi.mock('../hooks/useMemoryTuning', () => ({
  useMemoryTuning: vi.fn(() => ({
    tuningObjective: 'precision_priority',
    setTuningObjective: vi.fn(),
    tuningIntensity: 'standard',
    setTuningIntensity: vi.fn(),
    tuningSampleSize: '24',
    setTuningSampleSize: vi.fn(),
    tuningTopKEval: '20',
    setTuningTopKEval: vi.fn(),
    persistBestProfile: false,
    setPersistBestProfile: vi.fn(),
    submitTuningTask: vi.fn(),
    creatingTuning: false,
    tuningProfile: { runtime: {}, persistable: {} },
    tuningProfileToml: '',
    tuningTasks: [],
    applyBestTask: vi.fn(),
    tuningErrorText: '',
  })),
}))

// mock tab 组件 —— 简化为可识别的占位
vi.mock('../tabs/ImportTab', () => ({
  ImportTab: () => <div data-testid="import-tab">ImportTab</div>,
}))
vi.mock('../tabs/TuningTab', () => ({
  TuningTab: () => <div data-testid="tuning-tab">TuningTab</div>,
}))
vi.mock('../tabs/DeleteTab', () => ({
  DeleteTab: () => <div data-testid="delete-tab">DeleteTab</div>,
}))
vi.mock('../tabs/FeedbackTab', () => ({
  FeedbackTab: () => <div data-testid="feedback-tab">FeedbackTab</div>,
}))

// mock MemoryDeleteDialog
vi.mock('@/components/biz/memory-delete-dialog', () => ({
  MemoryDeleteDialog: () => <div data-testid="memory-delete-dialog" />,
}))

// mock sonner
vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}))

import { useMemoryRuntimeConfig } from '../hooks/useMemoryRuntimeConfig'
import { KnowledgeBasePage } from '../index'

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

function renderPage() {
  return render(<KnowledgeBasePage />, { wrapper: makeWrapper() })
}

function setRuntimeConfig(overrides: Record<string, unknown> = {}) {
  vi.mocked(useMemoryRuntimeConfig).mockReturnValue({
    runtimeConfig: {
      runtime_ready: true,
      embedding_degraded: false,
      embedding_dimension: 1024,
      relation_vectors_enabled: true,
      data_dir: '/data/memory',
      vector_rebuild_required: false,
      vector_rebuild_message: '',
      vector_pools: { configured_mode: 'single', effective_mode: 'single', ready: true, single_pool: { num_vectors: 100 } },
      ...overrides,
    } as never,
    runtimeLoading: false,
    runtimeErrorText: '',
    refreshRuntimeConfig: vi.fn(),
    refreshingCheck: false,
    refreshSelfCheck: vi.fn(),
    vectorRebuildDialogOpen: false,
    setVectorRebuildDialogOpen: vi.fn(),
    vectorRebuildPreview: null,
    vectorRebuilding: false,
    openVectorRebuildDialog: vi.fn(),
    confirmVectorRebuild: vi.fn(),
  })
}

describe('R4-2-15 KnowledgeBasePage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // 默认 runtimeLoading=false, runtimeConfig=null
    vi.mocked(useMemoryRuntimeConfig).mockReturnValue({
      runtimeConfig: null,
      runtimeLoading: false,
      runtimeErrorText: '',
      refreshRuntimeConfig: vi.fn(),
      refreshingCheck: false,
      refreshSelfCheck: vi.fn(),
      vectorRebuildDialogOpen: false,
      setVectorRebuildDialogOpen: vi.fn(),
      vectorRebuildPreview: null,
      vectorRebuilding: false,
      openVectorRebuildDialog: vi.fn(),
      confirmVectorRebuild: vi.fn(),
    })
  })

  it('渲染 4 tabs：import/tuning/delete/feedback', () => {
    setRuntimeConfig()
    renderPage()
    expect(screen.getByText('导入')).toBeInTheDocument()
    expect(screen.getByText('调优')).toBeInTheDocument()
    expect(screen.getByText('删除')).toBeInTheDocument()
    expect(screen.getByText('纠错历史')).toBeInTheDocument()
  })

  it('tab 切换：点击"调优" → TuningTab 渲染', async () => {
    const user = userEvent.setup()
    setRuntimeConfig()
    renderPage()
    // 初始默认 import tab
    expect(screen.getByTestId('import-tab')).toBeInTheDocument()
    // 点击调优 tab trigger（role="tab"）—— userEvent 模拟完整指针事件序列
    await user.click(screen.getByRole('tab', { name: '调优' }))
    await waitFor(() => {
      expect(screen.getByTestId('tuning-tab')).toBeInTheDocument()
    })
  })

  it('运行时概览区：runtimeConfig 就绪 → 运行状态徽章呈现', () => {
    setRuntimeConfig()
    renderPage()
    expect(screen.getByText('运行状态')).toBeInTheDocument()
    expect(screen.getByText('就绪')).toBeInTheDocument()
    expect(screen.getByText('Embedding 维度')).toBeInTheDocument()
    expect(screen.getByText('1024')).toBeInTheDocument()
  })

  it('深链接解析：?tab=delete → 默认 activeTab=delete', () => {
    // 模拟深链接
    const originalSearch = window.location.search
    Object.defineProperty(window, 'location', {
      value: { search: '?tab=delete', pathname: '/resource/knowledge-base', hash: '' },
      writable: true,
    })
    setRuntimeConfig()
    renderPage()
    expect(screen.getByTestId('delete-tab')).toBeInTheDocument()
    // 恢复
    Object.defineProperty(window, 'location', {
      value: { search: originalSearch, pathname: '/', hash: '' },
      writable: true,
    })
  })

  it('页面三态：runtimeLoading=true → LoadingSkeleton 呈现', () => {
    vi.mocked(useMemoryRuntimeConfig).mockReturnValue({
      runtimeConfig: null,
      runtimeLoading: true,
      runtimeErrorText: '',
      refreshRuntimeConfig: vi.fn(),
      refreshingCheck: false,
      refreshSelfCheck: vi.fn(),
      vectorRebuildDialogOpen: false,
      setVectorRebuildDialogOpen: vi.fn(),
      vectorRebuildPreview: null,
      vectorRebuilding: false,
      openVectorRebuildDialog: vi.fn(),
      confirmVectorRebuild: vi.fn(),
    })
    renderPage()
    expect(screen.getByTestId('loading-skeleton')).toBeInTheDocument()
  })

  it('页面三态：runtimeConfig=null 且 runtimeLoading=false → 正常渲染（无运行时徽章）', () => {
    renderPage()
    // 无运行时徽章，但 tab bar 仍渲染
    expect(screen.getByText('导入')).toBeInTheDocument()
    expect(screen.queryByText('运行状态')).not.toBeInTheDocument()
  })

  it('禁止 CorrectionTab：页面不含 CorrectionTab 引用', () => {
    setRuntimeConfig()
    const { container } = renderPage()
    // CorrectionTab 被 mock 排除，且页面无 CorrectionTab 相关文案
    expect(container.textContent).not.toContain('CorrectionTab')
    expect(container.textContent).not.toContain('记忆修正')
    expect(container.textContent).not.toContain('correction')
  })

  it('禁止 5 tabs：不含 graph/timeline/episodes/profiles/maintenance', () => {
    setRuntimeConfig()
    const { container } = renderPage()
    // 砍掉的 tab 文案不呈现
    expect(container.textContent).not.toContain('图谱')
    expect(container.textContent).not.toContain('审计时间线')
    expect(container.textContent).not.toContain('情景记忆')
    expect(container.textContent).not.toContain('人物画像')
    expect(container.textContent).not.toContain('维护')
  })

  it('主题零黑字：使用 text-foreground / text-muted-foreground（非硬编码黑色）', () => {
    setRuntimeConfig()
    const { container } = renderPage()
    // 运行时徽章用 text-muted-foreground
    expect(container.querySelector('.text-muted-foreground')).toBeTruthy()
    // 不含硬编码 text-black
    expect(container.querySelector('.text-black')).toBeNull()
  })
})