/**
 * MemoryDeleteDialog 测试（R4-2-14）
 *
 * 核心验证：
 * - 渲染基本结构（标题 + 描述 + 关闭按钮）
 * - 核心交互（点击"确认删除" → onExecute 调用）
 * - 错误态（error 非空 → Alert 局部呈现）
 * - 加载态（loadingPreview → "正在生成删除预览" 文案呈现）
 *
 * 模式：props 注入 mock 数据（R4-1 教训 #6/#7）
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { MemoryDeleteDialog } from '../memory-delete-dialog'

describe('R4-2-14 MemoryDeleteDialog', () => {
  it('渲染基本结构：标题 + 描述 + 关闭按钮', () => {
    render(
      <MemoryDeleteDialog
        open={true}
        onOpenChange={vi.fn()}
        title="确认删除来源"
        description="将删除所选来源下的全部记忆"
        preview={null}
        result={null}
        onExecute={vi.fn()}
      />,
    )
    expect(screen.getByText('确认删除来源')).toBeInTheDocument()
    expect(screen.getByText('将删除所选来源下的全部记忆')).toBeInTheDocument()
    // DialogContent 的 X 按钮 + DialogFooter 的关闭按钮均有 accessible name "关闭"
    expect(screen.getAllByRole('button', { name: '关闭' }).length).toBeGreaterThanOrEqual(1)
  })

  it('核心交互：点击"确认删除" → onExecute 调用', () => {
    const onExecute = vi.fn()
    render(
      <MemoryDeleteDialog
        open={true}
        onOpenChange={vi.fn()}
        title="确认删除"
        preview={{
          mode: 'source',
          item_count: 2,
          items: [],
          sources: ['src-1'],
          counts: { entities: 1, relations: 0, paragraphs: 1, sources: 1 },
          selector: {},
        }}
        result={null}
        onExecute={onExecute}
      />,
    )
    const button = screen.getByRole('button', { name: /确认删除/ })
    fireEvent.click(button)
    expect(onExecute).toHaveBeenCalledTimes(1)
  })

  it('错误态：error 非空 → Alert 局部呈现', () => {
    render(
      <MemoryDeleteDialog
        open={true}
        onOpenChange={vi.fn()}
        title="确认删除"
        preview={null}
        result={null}
        error="删除预览失败：来源不存在"
        onExecute={vi.fn()}
      />,
    )
    expect(screen.getByText('删除预览失败：来源不存在')).toBeInTheDocument()
  })

  it('加载态：loadingPreview → "正在生成删除预览" 文案呈现', () => {
    render(
      <MemoryDeleteDialog
        open={true}
        onOpenChange={vi.fn()}
        title="确认删除"
        preview={null}
        result={null}
        loadingPreview={true}
        onExecute={vi.fn()}
      />,
    )
    expect(screen.getByText('正在生成删除预览...')).toBeInTheDocument()
  })

  it('预览项搜索/分页：搜索命中数呈现、筛选变化重置页码（useClientSideList 驱动）', () => {
    const items = Array.from({ length: 10 }, (_, index) => ({
      item_type: 'paragraph',
      item_hash: `hash-${index + 1}`,
      item_key: `key-${index + 1}`,
      label: `label-${index + 1}`,
      source: 'src-1',
    }))
    render(
      <MemoryDeleteDialog
        open={true}
        onOpenChange={vi.fn()}
        title="确认删除"
        preview={{ mode: 'source', item_count: 10, items, sources: ['src-1'], counts: {}, selector: {} }}
        result={null}
        onExecute={vi.fn()}
      />,
    )
    // 每页 8 条 → 第 1 / 2 页
    expect(screen.getByText('第 1 / 2 页')).toBeInTheDocument()
    // 翻到第 2 页
    fireEvent.click(screen.getByRole('button', { name: '下一页' }))
    expect(screen.getByText('第 2 / 2 页')).toBeInTheDocument()
    // 搜索变化 → 自动重置到第 1 页；命中 2 条（label-2 / hash-2 / key-2）
    fireEvent.change(screen.getByPlaceholderText('搜索类型 / hash / item_key / source'), {
      target: { value: 'key-2' },
    })
    expect(screen.getByText('第 1 / 1 页')).toBeInTheDocument()
    // 仅 item_key='key-2' 命中 → 1 条
    expect(screen.getByText('命中 1 / 10 项')).toBeInTheDocument()
    // 上一页在第 1 页时禁用
    expect(screen.getByRole('button', { name: '上一页' })).toBeDisabled()
  })

  it('成功态：result 无 error → 操作 ID 呈现 + 恢复按钮', () => {
    const onRestore = vi.fn()
    render(
      <MemoryDeleteDialog
        open={true}
        onOpenChange={vi.fn()}
        title="确认删除"
        preview={null}
        result={{
          mode: 'source',
          operation_id: 'op-abc',
          counts: { entities: 1, relations: 0, paragraphs: 2, sources: 1 },
          sources: ['src-1'],
          deleted_count: 4,
          error: undefined,
          deleted_entity_count: 1,
          deleted_relation_count: 0,
          deleted_paragraph_count: 2,
          deleted_source_count: 1,
        }}
        onExecute={vi.fn()}
        onRestore={onRestore}
      />,
    )
    expect(screen.getByText('op-abc')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /恢复本次删除/ })).toBeInTheDocument()
  })
})