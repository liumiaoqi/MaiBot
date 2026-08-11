/**
 * DeleteTab 组件测试（R4-2-12）
 *
 * 核心验证：
 * - 渲染基本结构（来源批量删除 + 删除操作恢复）
 * - 核心交互（点击"预览删除" → openSourceDeletePreview）
 * - 加载态（selectedOperationDetailLoading: true → 加载区呈现）
 * - 错误态（selectedOperationDetailError 非空 → Alert 局部呈现）
 * - 空态（filteredSources 为空 → 空态文案）
 *
 * 模式：props 注入 mock hook 结果（R4-1 教训 #6/#7）
 */
import type { ReactNode } from 'react'

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { Tabs } from '@/components/ui/tabs'

import type { UseMemoryDeleteResult } from '../hooks/useMemoryDelete'
import { DeleteTab } from '../tabs/DeleteTab'

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

function renderDeleteTab(deleteOps: UseMemoryDeleteResult) {
  return render(
    <Tabs value="delete">
      <DeleteTab delete={deleteOps} />
    </Tabs>,
    { wrapper: makeWrapper() },
  )
}

function makeMockDelete(overrides: Partial<UseMemoryDeleteResult> = {}): UseMemoryDeleteResult {
  return {
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
    ...overrides,
  }
}

describe('R4-2-12 DeleteTab', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('渲染基本结构：来源批量删除 + 删除操作恢复', () => {
    renderDeleteTab(makeMockDelete())
    expect(screen.getByText('来源批量删除')).toBeInTheDocument()
    expect(screen.getByText('删除操作恢复')).toBeInTheDocument()
  })

  it('核心交互：点击"预览删除" → openSourceDeletePreview 调用', () => {
    const deleteOps = makeMockDelete({ selectedSources: ['source-1'] })
    renderDeleteTab(deleteOps)
    const button = screen.getByRole('button', { name: /预览删除/ })
    fireEvent.click(button)
    expect(deleteOps.openSourceDeletePreview).toHaveBeenCalledTimes(1)
  })

  it('加载态：selectedOperationDetailLoading + 选中操作 → 加载区呈现', () => {
    const deleteOps = makeMockDelete({
      selectedDeleteOperation: {
        operation_id: 'op-1',
        mode: 'source',
        status: 'executed',
        created_at: 1700000000,
        selector: {},
      },
      selectedOperationDetailLoading: true,
    })
    renderDeleteTab(deleteOps)
    // ThinkingIllustration 渲染为 role="status" + aria-label="加载中"
    expect(screen.getAllByRole('status', { name: '加载中' }).length).toBeGreaterThan(0)
  })

  it('错误态：selectedOperationDetailError 非空 → Alert 局部呈现', () => {
    const deleteOps = makeMockDelete({
      selectedDeleteOperation: {
        operation_id: 'op-1',
        mode: 'source',
        status: 'executed',
        created_at: 1700000000,
        selector: {},
      },
      selectedOperationDetailError: '加载操作详情失败',
    })
    renderDeleteTab(deleteOps)
    expect(screen.getByText('加载操作详情失败')).toBeInTheDocument()
  })

  it('空态：filteredSources 为空 → 空态文案呈现', () => {
    renderDeleteTab(makeMockDelete())
    expect(screen.getByText('当前没有可删除的来源')).toBeInTheDocument()
    expect(screen.getByText('当前筛选条件下没有删除操作')).toBeInTheDocument()
  })
})