/**
 * useClientSideList 测试（R4 任务 5——客户端过滤版列表状态机）。
 *
 * 核心验证：
 * - 过滤：filtered 应用过滤函数；paged 按 pageSize 切当前页；totalPages 向上取整、至少 1
 * - 筛选变化（filters 引用变化）→ 自动重置页码到 1 + 清空选中
 * - 页码超界（数据变少）→ 自动回拉到末页
 * - setPage 钳制到 [1, totalPages]（含函数式更新）
 * - 选中对齐：selectedItem 按 id 在过滤结果中匹配；落空 → null（selectedId 保留，由调用方回退）
 */
import { act, renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { useClientSideList } from '../useClientSideList'

interface TestItem {
  id: string
  name: string
}

interface TestFilters {
  keyword: string
}

const ALL_ITEMS: TestItem[] = Array.from({ length: 25 }, (_, index) => ({
  id: `item-${index + 1}`,
  name: `name-${index + 1}`,
}))

function filterByName(items: TestItem[], filters: TestFilters): TestItem[] {
  const keyword = filters.keyword.trim().toLowerCase()
  if (!keyword) {
    return items
  }
  return items.filter((item) => item.name.toLowerCase().includes(keyword))
}

function renderList(initialFilters: TestFilters, config: Partial<Parameters<typeof useClientSideList<TestItem, TestFilters, string>>[0]> = {}) {
  const utils = renderHook(
    ({ filters, items }: { filters: TestFilters; items: TestItem[] }) =>
      useClientSideList({
        items,
        filters,
        pageSize: 10,
        filter: filterByName,
        getId: (item) => item.id,
        ...config,
      }),
    { initialProps: { filters: initialFilters, items: ALL_ITEMS } },
  )
  return utils
}

describe('useClientSideList', () => {
  it('过滤：filtered 应用过滤函数，paged 按 pageSize 切当前页', () => {
    const { result } = renderList({ keyword: 'name-2' })
    // name-2, name-20 ~ name-25 共 7 条
    expect(result.current.filtered).toHaveLength(7)
    expect(result.current.filtered.map((item) => item.id)).toEqual([
      'item-2',
      'item-20',
      'item-21',
      'item-22',
      'item-23',
      'item-24',
      'item-25',
    ])
    expect(result.current.paged).toEqual(result.current.filtered)
    expect(result.current.totalPages).toBe(1)
    expect(result.current.page).toBe(1)
  })

  it('分页：25 条 / 每页 10 → 3 页，翻页切片正确', () => {
    const { result } = renderList({ keyword: '' })
    expect(result.current.totalPages).toBe(3)
    expect(result.current.paged).toHaveLength(10)
    expect(result.current.paged[0].id).toBe('item-1')
    act(() => {
      result.current.setPage(2)
    })
    expect(result.current.page).toBe(2)
    expect(result.current.paged[0].id).toBe('item-11')
    act(() => {
      result.current.setPage(3)
    })
    expect(result.current.paged).toHaveLength(5)
    expect(result.current.paged[4].id).toBe('item-25')
  })

  it('totalPages：空数据时至少为 1', () => {
    const { result, rerender } = renderList({ keyword: '' })
    act(() => {
      rerender({ filters: { keyword: '' }, items: [] })
    })
    expect(result.current.filtered).toEqual([])
    expect(result.current.paged).toEqual([])
    expect(result.current.totalPages).toBe(1)
    expect(result.current.page).toBe(1)
  })

  it('筛选变化 → 自动重置页码到 1 + 清空选中', () => {
    const { result, rerender } = renderList({ keyword: '' }, { initialPage: 2, initialSelectedId: 'item-15' })
    act(() => {
      result.current.setPage(2)
      result.current.setSelectedId('item-15')
    })
    expect(result.current.page).toBe(2)
    expect(result.current.selectedId).toBe('item-15')
    // 筛选变化（新 filters 引用）→ 页码重置 + 选中清空
    act(() => {
      rerender({ filters: { keyword: 'name-2' }, items: ALL_ITEMS })
    })
    expect(result.current.page).toBe(1)
    expect(result.current.selectedId).toBeNull()
    expect(result.current.selectedItem).toBeNull()
  })

  it('筛选变化 + 旧页码超界 → 重置到 1（重置优先于回拉）', () => {
    const { result, rerender } = renderList({ keyword: '' }, { initialPage: 3 })
    expect(result.current.page).toBe(3)
    act(() => {
      rerender({ filters: { keyword: 'name-2' }, items: ALL_ITEMS })
    })
    // 新筛选只命中 7 条（1 页）；筛选变化重置为 1，而非回拉到 1
    expect(result.current.totalPages).toBe(1)
    expect(result.current.page).toBe(1)
  })

  it('页码超界（数据变少、筛选未变）→ 回拉到末页', () => {
    const { result, rerender } = renderList({ keyword: '' }, { initialPage: 3 })
    expect(result.current.page).toBe(3)
    act(() => {
      rerender({ filters: { keyword: '' }, items: ALL_ITEMS.slice(0, 5) })
    })
    // 5 条 → 1 页；page 3 超界 → 回拉到 1
    expect(result.current.totalPages).toBe(1)
    expect(result.current.page).toBe(1)
    // 回拉后选中不受影响（筛选未变不清选中）——初始无选中，再验证保留场景
  })

  it('页码超界回拉不清空选中（筛选未变）', () => {
    const emptyFilters: TestFilters = { keyword: '' }
    const { result, rerender } = renderList(emptyFilters, { initialPage: 3, initialSelectedId: 'item-3' })
    expect(result.current.selectedId).toBe('item-3')
    act(() => {
      rerender({ filters: emptyFilters, items: ALL_ITEMS.slice(0, 5) })
    })
    expect(result.current.totalPages).toBe(1)
    expect(result.current.page).toBe(1)
    expect(result.current.selectedId).toBe('item-3')
    expect(result.current.selectedItem?.id).toBe('item-3')
  })

  it('setPage 钳制到 [1, totalPages]（含函数式更新）', () => {
    const { result } = renderList({ keyword: '' })
    act(() => {
      result.current.setPage(99)
    })
    expect(result.current.page).toBe(3)
    act(() => {
      result.current.setPage(0)
    })
    expect(result.current.page).toBe(1)
    act(() => {
      result.current.setPage(-5)
    })
    expect(result.current.page).toBe(1)
    // 函数式更新越界同样钳制
    act(() => {
      result.current.setPage(3)
      result.current.setPage((current) => current + 10)
    })
    expect(result.current.page).toBe(3)
  })

  it('选中对齐：命中 → selectedItem；落空 → null 且 selectedId 保留', () => {
    const emptyFilters: TestFilters = { keyword: '' }
    const { result, rerender } = renderList(emptyFilters)
    act(() => {
      result.current.setSelectedId('item-15')
    })
    expect(result.current.selectedItem?.id).toBe('item-15')
    // 选中项跨页仍在过滤结果中 → 不受页码影响
    act(() => {
      result.current.setPage(2)
    })
    expect(result.current.selectedItem?.id).toBe('item-15')
    // 数据变化（筛选未变、选中项被移除）→ 选中项落空 → selectedItem null，selectedId 保留
    act(() => {
      rerender({ filters: emptyFilters, items: ALL_ITEMS.filter((item) => item.id !== 'item-15') })
    })
    expect(result.current.selectedItem).toBeNull()
    expect(result.current.selectedId).toBe('item-15')
  })

  it('选中项在筛选结果中可命中（筛选变化清空后再选中）', () => {
    const emptyFilters: TestFilters = { keyword: '' }
    const filteredFilters: TestFilters = { keyword: 'name-6' }
    const { result, rerender } = renderList(emptyFilters)
    act(() => {
      result.current.setSelectedId('item-6')
    })
    expect(result.current.selectedItem?.id).toBe('item-6')
    // 筛选变化 → 清空选中
    act(() => {
      rerender({ filters: filteredFilters, items: ALL_ITEMS })
    })
    expect(result.current.selectedId).toBeNull()
    // 重新选中匹配项 → selectedItem 命中
    act(() => {
      result.current.setSelectedId('item-6')
    })
    expect(result.current.selectedItem?.id).toBe('item-6')
    expect(result.current.paged[0].id).toBe('item-6')
  })
})
