/**
 * graph-dialogs 4 个详情 Dialog 渲染测试（R4 债清理 P1——安全网）
 *
 * 覆盖：NodeDetailDialog / EdgeDetailDialog / RelationDetailDialog / ParagraphDetailDialog
 * - 打开状态：open=false 不渲染内容；open=true 渲染标题与内容字段
 * - 内容字段：实体/边/关系/段落各字段逐项断言（含空态与 loading 态）
 * - 关闭：点击 Dialog 右上关闭按钮 → onOpenChange(false)
 * - 回调：onOpenEvidence / onDeleteEntity / onDeleteEdgeGroup / onDeleteRelation / onDeleteParagraph
 *
 * 注意：
 * - graph-types 是纯类型模块（import type——运行时被擦除），无需 vi.mock，
 *   直接用符合 graph-types / memory-api 类型的 fixture（mock 数据）即可；
 * - 相对路径：本文件在 __tests__/ 目录，graph-types 在其上三级（resource/types/）——
 *   用 ../../../types/graph-types（vitest 不做类型检查，路径写错只有 tsc 会报 TS2307）；
 * - Radix Dialog 用 Portal 渲染到 document.body——screen 查询即可；
 * - DialogBody 内部 ScrollArea 依赖 ResizeObserver（test-setup.ts 已 mock）。
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type {
  MemoryEvidenceGraphPayload,
  MemoryGraphEdgeDetailPayload,
  MemoryGraphNodeDetailPayload,
  MemoryGraphParagraphDetailPayload,
  MemoryGraphRelationDetailPayload,
} from '@/lib/memory-api'

import type { GraphNode, SelectedEdgeData } from '../../../types/graph-types'
import {
  EdgeDetailDialog,
  NodeDetailDialog,
  ParagraphDetailDialog,
  RelationDetailDialog,
} from '../graph-dialogs'

// ---------- fixtures（类型化 mock 数据） ----------

const emptyEvidenceGraph: MemoryEvidenceGraphPayload = {
  nodes: [],
  edges: [],
  focus_entities: [],
}

const relationFixture: MemoryGraphRelationDetailPayload = {
  hash: 'rel-1',
  subject: 'Alice',
  predicate: 'works_at',
  object: 'ACME',
  text: 'Alice 在 ACME 工作',
  confidence: 0.95,
  paragraph_count: 2,
  paragraph_hashes: ['para-1', 'para-2'],
  source_paragraph: 'para-1',
}

const paragraphFixture: MemoryGraphParagraphDetailPayload = {
  hash: 'para-1',
  content: 'Alice 是 ACME 的工程师。',
  preview: 'Alice 是 ACME 的工程师。',
  source: 'chat_123',
  created_at: 1700000000,
  updated_at: 1700000100,
  entity_count: 2,
  relation_count: 1,
  entities: ['Alice', 'ACME'],
  relations: ['rel-1'],
}

const nodeDetailFixture: MemoryGraphNodeDetailPayload = {
  node: {
    id: 'n1',
    type: 'entity',
    content: 'Alice',
    hash: 'hash-n1',
    appearance_count: 5,
  },
  relations: [relationFixture],
  paragraphs: [paragraphFixture],
  evidence_graph: emptyEvidenceGraph,
}

const edgeDetailFixture: MemoryGraphEdgeDetailPayload = {
  edge: {
    source: 'n1',
    target: 'n2',
    weight: 0.87654321,
    predicates: ['works_at'],
    relation_count: 3,
    evidence_count: 7,
  },
  relations: [relationFixture],
  paragraphs: [paragraphFixture],
  evidence_graph: emptyEvidenceGraph,
}

const graphNodeFixture: GraphNode = {
  id: 'n1',
  type: 'entity',
  content: 'Alice',
}

const selectedEdgeFixture: SelectedEdgeData = {
  source: graphNodeFixture,
  target: { id: 'n2', type: 'entity', content: 'ACME' },
  edge: {
    source: 'n1',
    target: 'n2',
    weight: 0.87654321,
    predicates: ['works_at'],
    relationCount: 3,
    evidenceCount: 7,
  },
}

// ---------- NodeDetailDialog ----------

describe('R4-P1 NodeDetailDialog', () => {
  it('open=false 时不渲染内容', () => {
    render(
      <NodeDetailDialog
        open={false}
        onOpenChange={() => {}}
        selectedNodeData={graphNodeFixture}
        nodeDetail={nodeDetailFixture}
      />,
    )
    expect(screen.queryByText('实体详情')).toBeNull()
    expect(screen.queryByText('Alice')).toBeNull()
  })

  it('open=true 渲染实体标题 + 内容字段（出现次数/相关关系/支持段落）', () => {
    render(
      <NodeDetailDialog
        open={true}
        onOpenChange={() => {}}
        selectedNodeData={graphNodeFixture}
        nodeDetail={nodeDetailFixture}
      />,
    )
    expect(screen.getByText('实体详情')).toBeTruthy()
    expect(screen.getByText('出现次数 5')).toBeTruthy()
    expect(screen.getByRole('heading', { level: 3 }).textContent).toBe('Alice')
    expect(screen.getByText('n1')).toBeTruthy() // node.id
    expect(screen.getByText('相关关系')).toBeTruthy()
    expect(screen.getByText('支持段落')).toBeTruthy()
    // 关系列表字段
    expect(screen.getByText('works_at')).toBeTruthy()
    expect(screen.getByText('证据段落 2')).toBeTruthy()
    expect(screen.getByText('置信度 0.950')).toBeTruthy()
    expect(screen.getByText('Alice 在 ACME 工作')).toBeTruthy()
    expect(screen.getByText('rel-1')).toBeTruthy()
    // 段落列表字段
    expect(screen.getByText('chat_123')).toBeTruthy()
    expect(screen.getByText('实体 2')).toBeTruthy()
    expect(screen.getByText('关系 1')).toBeTruthy()
    expect(screen.getByText('Alice 是 ACME 的工程师。')).toBeTruthy()
    expect(screen.getByText(/更新时间/)).toBeTruthy()
  })

  it('nodeDetail 为 null 时回退 selectedNodeData（无出现次数徽章）', () => {
    render(
      <NodeDetailDialog
        open={true}
        onOpenChange={() => {}}
        selectedNodeData={graphNodeFixture}
        nodeDetail={null}
      />,
    )
    expect(screen.getByRole('heading', { level: 3 }).textContent).toBe('Alice')
    expect(screen.getByText('n1')).toBeTruthy()
    expect(screen.queryByText(/出现次数/)).toBeNull()
    // 无 detail → 空态文案
    expect(screen.getByText('暂无可展示的关系语义。')).toBeTruthy()
    expect(screen.getByText('暂无可展示的来源段落。')).toBeTruthy()
  })

  it('未选中实体时显示空态', () => {
    render(
      <NodeDetailDialog open={true} onOpenChange={() => {}} selectedNodeData={null} nodeDetail={null} />,
    )
    expect(screen.getByText('尚未选中实体。')).toBeTruthy()
    expect(screen.queryByText('实体详情')).toBeTruthy() // 标题仍在
  })

  it('loading=true 显示加载态且不渲染关系/段落区', () => {
    render(
      <NodeDetailDialog
        open={true}
        onOpenChange={() => {}}
        selectedNodeData={graphNodeFixture}
        nodeDetail={nodeDetailFixture}
        loading={true}
      />,
    )
    expect(screen.getByLabelText('加载中')).toBeTruthy()
    expect(screen.queryByText('相关关系')).toBeNull()
    expect(screen.queryByText('支持段落')).toBeNull()
  })

  it('点击「切到证据视图」触发 onOpenEvidence', () => {
    const onOpenEvidence = vi.fn()
    render(
      <NodeDetailDialog
        open={true}
        onOpenChange={() => {}}
        selectedNodeData={graphNodeFixture}
        nodeDetail={nodeDetailFixture}
        onOpenEvidence={onOpenEvidence}
      />,
    )
    fireEvent.click(screen.getByText('切到证据视图'))
    expect(onOpenEvidence).toHaveBeenCalledTimes(1)
  })

  it('点击「删除实体」默认 includeParagraphs=false；勾选复选框后为 true', () => {
    const onDeleteEntity = vi.fn()
    const view = render(
      <NodeDetailDialog
        open={true}
        onOpenChange={() => {}}
        selectedNodeData={graphNodeFixture}
        nodeDetail={nodeDetailFixture}
        onDeleteEntity={onDeleteEntity}
      />,
    )
    fireEvent.click(screen.getByText('删除实体'))
    expect(onDeleteEntity).toHaveBeenCalledWith({ includeParagraphs: false })

    fireEvent.click(screen.getByRole('checkbox', { name: '删除该实体相关证据段落' }))
    fireEvent.click(screen.getByText('删除实体'))
    expect(onDeleteEntity).toHaveBeenLastCalledWith({ includeParagraphs: true })
    view.unmount()
  })

  it('点击关系列表「删除关系」/「删除段落」触发对应回调', () => {
    const onDeleteRelation = vi.fn()
    const onDeleteParagraph = vi.fn()
    render(
      <NodeDetailDialog
        open={true}
        onOpenChange={() => {}}
        selectedNodeData={graphNodeFixture}
        nodeDetail={nodeDetailFixture}
        onDeleteRelation={onDeleteRelation}
        onDeleteParagraph={onDeleteParagraph}
      />,
    )
    fireEvent.click(screen.getByText('删除关系'))
    expect(onDeleteRelation).toHaveBeenCalledWith(relationFixture)
    fireEvent.click(screen.getByText('删除段落'))
    expect(onDeleteParagraph).toHaveBeenCalledWith(paragraphFixture)
  })

  it('点击右上关闭按钮触发 onOpenChange(false)', () => {
    const onOpenChange = vi.fn()
    render(
      <NodeDetailDialog
        open={true}
        onOpenChange={onOpenChange}
        selectedNodeData={graphNodeFixture}
        nodeDetail={nodeDetailFixture}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: '关闭' }))
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })
})

// ---------- EdgeDetailDialog ----------

describe('R4-P1 EdgeDetailDialog', () => {
  it('open=false 时不渲染内容', () => {
    render(
      <EdgeDetailDialog
        open={false}
        onOpenChange={() => {}}
        selectedEdgeData={selectedEdgeFixture}
        edgeDetail={edgeDetailFixture}
      />,
    )
    expect(screen.queryByText('关系详情')).toBeNull()
  })

  it('open=true 渲染边详情字段（source→target/聚合权重/谓词/关系语义/支持段落）', () => {
    render(
      <EdgeDetailDialog
        open={true}
        onOpenChange={() => {}}
        selectedEdgeData={selectedEdgeFixture}
        edgeDetail={edgeDetailFixture}
      />,
    )
    expect(screen.getByText('关系详情')).toBeTruthy()
    expect(screen.getByText('Alice → ACME')).toBeTruthy()
    expect(screen.getByText('聚合权重 0.8765')).toBeTruthy()
    expect(screen.getByText('关系 3')).toBeTruthy()
    expect(screen.getByText('证据 7')).toBeTruthy()
    expect(screen.getAllByText('works_at').length).toBeGreaterThanOrEqual(1) // 谓词徽章 + 关系列表谓词
    expect(screen.getByText('关系语义')).toBeTruthy()
    expect(screen.getByText('支持段落')).toBeTruthy()
    expect(screen.getByText('Alice 在 ACME 工作')).toBeTruthy()
    expect(screen.getByText('Alice 是 ACME 的工程师。')).toBeTruthy()
  })

  it('edgeDetail 为 null 时回退 selectedEdgeData 的 source/target', () => {
    render(
      <EdgeDetailDialog
        open={true}
        onOpenChange={() => {}}
        selectedEdgeData={selectedEdgeFixture}
        edgeDetail={null}
      />,
    )
    expect(screen.getByText('Alice → ACME')).toBeTruthy()
    expect(screen.getByText('聚合权重 0.8765')).toBeTruthy()
    expect(screen.getByText('关系 3')).toBeTruthy()
    expect(screen.getByText('证据 7')).toBeTruthy()
  })

  it('未选中关系时显示空态', () => {
    render(<EdgeDetailDialog open={true} onOpenChange={() => {}} selectedEdgeData={null} edgeDetail={null} />)
    expect(screen.getByText('尚未选中关系。')).toBeTruthy()
  })

  it('loading=true 显示加载态且不渲染关系语义/支持段落', () => {
    render(
      <EdgeDetailDialog
        open={true}
        onOpenChange={() => {}}
        selectedEdgeData={selectedEdgeFixture}
        edgeDetail={edgeDetailFixture}
        loading={true}
      />,
    )
    expect(screen.getByLabelText('加载中')).toBeTruthy()
    expect(screen.queryByText('关系语义')).toBeNull()
    expect(screen.queryByText('支持段落')).toBeNull()
  })

  it('点击「切到证据视图」触发 onOpenEvidence', () => {
    const onOpenEvidence = vi.fn()
    render(
      <EdgeDetailDialog
        open={true}
        onOpenChange={() => {}}
        selectedEdgeData={selectedEdgeFixture}
        edgeDetail={edgeDetailFixture}
        onOpenEvidence={onOpenEvidence}
      />,
    )
    fireEvent.click(screen.getByText('切到证据视图'))
    expect(onOpenEvidence).toHaveBeenCalledTimes(1)
  })

  it('点击「删除此关系组」默认 includeParagraphs=false；勾选复选框后为 true', () => {
    const onDeleteEdgeGroup = vi.fn()
    const view = render(
      <EdgeDetailDialog
        open={true}
        onOpenChange={() => {}}
        selectedEdgeData={selectedEdgeFixture}
        edgeDetail={edgeDetailFixture}
        onDeleteEdgeGroup={onDeleteEdgeGroup}
      />,
    )
    fireEvent.click(screen.getByText('删除此关系组'))
    expect(onDeleteEdgeGroup).toHaveBeenCalledWith({ includeParagraphs: false })

    fireEvent.click(screen.getByRole('checkbox', { name: '同时删除支撑段落' }))
    fireEvent.click(screen.getByText('删除此关系组'))
    expect(onDeleteEdgeGroup).toHaveBeenLastCalledWith({ includeParagraphs: true })
    view.unmount()
  })

  it('点击右上关闭按钮触发 onOpenChange(false)', () => {
    const onOpenChange = vi.fn()
    render(
      <EdgeDetailDialog
        open={true}
        onOpenChange={onOpenChange}
        selectedEdgeData={selectedEdgeFixture}
        edgeDetail={edgeDetailFixture}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: '关闭' }))
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })
})

// ---------- RelationDetailDialog ----------

describe('R4-P1 RelationDetailDialog', () => {
  it('relation 为 null 时不渲染任何内容', () => {
    render(<RelationDetailDialog open={true} onOpenChange={() => {}} relation={null} />)
    expect(screen.queryByText('关系明细')).toBeNull()
  })

  it('open=false 时不渲染内容', () => {
    render(
      <RelationDetailDialog
        open={false}
        onOpenChange={() => {}}
        relation={relationFixture}
      />,
    )
    expect(screen.queryByText('关系明细')).toBeNull()
  })

  it('open=true 渲染关系明细字段（谓词/证据段落/置信度/文本/hash）', () => {
    render(
      <RelationDetailDialog
        open={true}
        onOpenChange={() => {}}
        relation={relationFixture}
      />,
    )
    expect(screen.getByText('关系明细')).toBeTruthy()
    expect(screen.getByText('works_at')).toBeTruthy()
    expect(screen.getByText('证据段落 2')).toBeTruthy()
    expect(screen.getByText('置信度 0.950')).toBeTruthy()
    expect(screen.getByText('Alice 在 ACME 工作')).toBeTruthy()
    expect(screen.getByText('rel-1')).toBeTruthy()
  })

  it('predicate 为空时回退 metadata.predicate', () => {
    render(
      <RelationDetailDialog
        open={true}
        onOpenChange={() => {}}
        relation={{ ...relationFixture, predicate: '' }}
        metadata={{ predicate: 'lives_in' }}
      />,
    )
    expect(screen.getByText('lives_in')).toBeTruthy()
  })

  it('点击「删除这条关系」默认 includeParagraphs=false；勾选复选框后为 true', () => {
    const onDeleteRelation = vi.fn()
    const view = render(
      <RelationDetailDialog
        open={true}
        onOpenChange={() => {}}
        relation={relationFixture}
        onDeleteRelation={onDeleteRelation}
      />,
    )
    fireEvent.click(screen.getByText('删除这条关系'))
    expect(onDeleteRelation).toHaveBeenCalledWith(relationFixture, false)

    fireEvent.click(screen.getByRole('checkbox', { name: '同时删除支撑该关系的段落' }))
    fireEvent.click(screen.getByText('删除这条关系'))
    expect(onDeleteRelation).toHaveBeenLastCalledWith(relationFixture, true)
    view.unmount()
  })

  it('点击右上关闭按钮触发 onOpenChange(false)', () => {
    const onOpenChange = vi.fn()
    render(
      <RelationDetailDialog
        open={true}
        onOpenChange={onOpenChange}
        relation={relationFixture}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: '关闭' }))
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })
})

// ---------- ParagraphDetailDialog ----------

describe('R4-P1 ParagraphDetailDialog', () => {
  it('paragraph 为 null 时不渲染任何内容', () => {
    render(<ParagraphDetailDialog open={true} onOpenChange={() => {}} paragraph={null} />)
    expect(screen.queryByText('段落明细')).toBeNull()
  })

  it('open=false 时不渲染内容', () => {
    render(
      <ParagraphDetailDialog
        open={false}
        onOpenChange={() => {}}
        paragraph={paragraphFixture}
      />,
    )
    expect(screen.queryByText('段落明细')).toBeNull()
  })

  it('open=true 渲染段落明细字段（来源/实体/关系/更新时间/内容/hash/实体徽章）', () => {
    render(
      <ParagraphDetailDialog
        open={true}
        onOpenChange={() => {}}
        paragraph={paragraphFixture}
      />,
    )
    expect(screen.getByText('段落明细')).toBeTruthy()
    expect(screen.getByText('chat_123')).toBeTruthy()
    expect(screen.getByText('实体 2')).toBeTruthy()
    expect(screen.getByText('关系 1')).toBeTruthy()
    expect(screen.getByText(/更新时间/)).toBeTruthy()
    expect(screen.getByText('Alice 是 ACME 的工程师。')).toBeTruthy()
    expect(screen.getByText('para-1')).toBeTruthy()
    expect(screen.getByText('Alice')).toBeTruthy()
    expect(screen.getByText('ACME')).toBeTruthy()
  })

  it('source 为空时回退 metadata.source', () => {
    render(
      <ParagraphDetailDialog
        open={true}
        onOpenChange={() => {}}
        paragraph={{ ...paragraphFixture, source: '' }}
        metadata={{ source: 'fallback_src' }}
      />,
    )
    expect(screen.getByText('fallback_src')).toBeTruthy()
  })

  it('点击「删除这段证据」触发 onDeleteParagraph', () => {
    const onDeleteParagraph = vi.fn()
    render(
      <ParagraphDetailDialog
        open={true}
        onOpenChange={() => {}}
        paragraph={paragraphFixture}
        onDeleteParagraph={onDeleteParagraph}
      />,
    )
    fireEvent.click(screen.getByText('删除这段证据'))
    expect(onDeleteParagraph).toHaveBeenCalledWith(paragraphFixture)
  })

  it('点击右上关闭按钮触发 onOpenChange(false)', () => {
    const onOpenChange = vi.fn()
    render(
      <ParagraphDetailDialog
        open={true}
        onOpenChange={onOpenChange}
        paragraph={paragraphFixture}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: '关闭' }))
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })
})
