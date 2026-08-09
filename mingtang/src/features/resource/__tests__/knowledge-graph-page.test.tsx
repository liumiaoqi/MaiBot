/**
 * KnowledgeGraphPage 主页面测试（R3-4-4 测试先行）
 *
 * 核心验证：页面渲染 + 空状态 + 刷新按钮 + 搜索输入 + toast适配
 */
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}))

vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => vi.fn(),
}))

vi.mock('@xyflow/react', () => ({
  ReactFlow: () => null,
  Background: () => null,
  BackgroundVariant: { Dots: 'dots' },
  Controls: () => null,
  Handle: () => null,
  MarkerType: { ArrowClosed: 'arrowclosed' },
  Position: { Top: 'top', Bottom: 'bottom' },
  useNodesState: (initial: unknown) => [initial, vi.fn(), vi.fn()],
}))

const {
  mockGetMemoryGraph,
  mockGetMemoryGraphSearch,
  mockGetMemoryGraphNodeDetail,
  mockGetMemoryGraphEdgeDetail,
  mockGetMemoryGraphParagraphDetail,
  mockPreviewMemoryDelete,
  mockExecuteMemoryDelete,
  mockRestoreMemoryDelete,
} = vi.hoisted(() => ({
  mockGetMemoryGraph: vi.fn(),
  mockGetMemoryGraphSearch: vi.fn(),
  mockGetMemoryGraphNodeDetail: vi.fn(),
  mockGetMemoryGraphEdgeDetail: vi.fn(),
  mockGetMemoryGraphParagraphDetail: vi.fn(),
  mockPreviewMemoryDelete: vi.fn(),
  mockExecuteMemoryDelete: vi.fn(),
  mockRestoreMemoryDelete: vi.fn(),
}))

vi.mock('@/lib/memory-api', () => ({
  getMemoryGraph: mockGetMemoryGraph,
  getMemoryGraphSearch: mockGetMemoryGraphSearch,
  getMemoryGraphNodeDetail: mockGetMemoryGraphNodeDetail,
  getMemoryGraphEdgeDetail: mockGetMemoryGraphEdgeDetail,
  getMemoryGraphParagraphDetail: mockGetMemoryGraphParagraphDetail,
  previewMemoryDelete: mockPreviewMemoryDelete,
  executeMemoryDelete: mockExecuteMemoryDelete,
  restoreMemoryDelete: mockRestoreMemoryDelete,
}))

vi.mock('@/lib/api-base', () => ({
  resolveApiPath: vi.fn((path: string) => Promise.resolve(path)),
}))

import { KnowledgeGraphPage } from '../knowledge-graph'

function makeEmptyGraphPayload() {
  return {
    nodes: [],
    edges: [],
    total_nodes: 0,
    total_edges: 0,
  }
}

function makeSimpleGraphPayload() {
  return {
    nodes: [
      { id: 'entity-1', name: '麦麦', attributes: { hash: 'h1' }, appearance_count: 5 },
      { id: 'entity-2', name: '聊天', attributes: { hash: 'h2' }, appearance_count: 3 },
    ],
    edges: [
      {
        source: 'entity-1',
        target: 'entity-2',
        weight: 2.5,
        label: '喜欢',
        relation_hashes: ['r1'],
        predicates: ['喜欢'],
        relation_count: 1,
        evidence_count: 2,
      },
    ],
    total_nodes: 2,
    total_edges: 1,
  }
}

describe('KnowledgeGraphPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockGetMemoryGraph.mockResolvedValue(makeEmptyGraphPayload())
  })

  it('渲染页面标题和统计徽章', async () => {
    render(<KnowledgeGraphPage />)
    expect(screen.getByText('长期记忆图谱')).toBeInTheDocument()
    expect(screen.getByText('基于 A_Memorix 的实体关系图与证据视图')).toBeInTheDocument()
    await waitFor(() => {
      expect(mockGetMemoryGraph).toHaveBeenCalled()
    })
  })

  it('空图谱时显示空状态提示', async () => {
    render(<KnowledgeGraphPage />)
    await waitFor(() => {
      expect(screen.getByText('还没有可展示的长期记忆图谱')).toBeInTheDocument()
    })
    expect(screen.getByText('前往长期记忆控制台')).toBeInTheDocument()
  })

  it('点击刷新按钮触发 loadGraph', async () => {
    render(<KnowledgeGraphPage />)
    await waitFor(() => {
      expect(mockGetMemoryGraph).toHaveBeenCalledTimes(1)
    })
    const refreshButton = screen.getByText('刷新图谱')
    fireEvent.click(refreshButton)
    await waitFor(() => {
      expect(mockGetMemoryGraph).toHaveBeenCalledTimes(2)
    })
  })

  it('节点上限选择器存在', async () => {
    render(<KnowledgeGraphPage />)
    expect(screen.getByText('120 节点')).toBeInTheDocument()
  })

  it('实体关系图/证据视图标签切换存在', async () => {
    render(<KnowledgeGraphPage />)
    expect(screen.getByText('实体关系图')).toBeInTheDocument()
    expect(screen.getByText('证据视图')).toBeInTheDocument()
  })

  it('搜索输入框存在且可输入', async () => {
    render(<KnowledgeGraphPage />)
    const searchInput = screen.getByPlaceholderText('搜索实体、关系、hash（后端全库）')
    expect(searchInput).toBeInTheDocument()
    fireEvent.change(searchInput, { target: { value: '麦麦' } })
    expect((searchInput as HTMLInputElement).value).toBe('麦麦')
  })

  it('有数据时不显示空状态提示', async () => {
    mockGetMemoryGraph.mockResolvedValue(makeSimpleGraphPayload())
    render(<KnowledgeGraphPage />)
    await waitFor(() => {
      expect(mockGetMemoryGraph).toHaveBeenCalled()
    })
    await waitFor(() => {
      expect(screen.queryByText('还没有可展示的长期记忆图谱')).not.toBeInTheDocument()
    })
  })

  it('embedded 模式隐藏标题', async () => {
    render(<KnowledgeGraphPage embedded={true} />)
    expect(screen.queryByText('长期记忆图谱')).not.toBeInTheDocument()
  })

  it('初始加载调用 getMemoryGraph 传入节点上限', async () => {
    render(<KnowledgeGraphPage />)
    await waitFor(() => {
      expect(mockGetMemoryGraph).toHaveBeenCalledWith(120)
    })
  })
})
