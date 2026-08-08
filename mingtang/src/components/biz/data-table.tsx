import * as React from 'react'
import { ChevronDownIcon, ChevronUpIcon, ChevronsUpDownIcon } from 'lucide-react'

import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'

/** 排序方向 */
export type SortDirection = 'asc' | 'desc' | null

/** 列定义 */
export interface Column<T> {
  /** 唯一标识 */
  key: keyof T | string
  /** 列标题 */
  header: string
  /** 单元格渲染函数 */
  cell?: (row: T) => React.ReactNode
  /** 是否可排序 */
  sortable?: boolean
  /** 列宽度 */
  width?: string
  /** 对齐方式 */
  align?: 'left' | 'center' | 'right'
}

/** DataTable 属性 */
export interface DataTableProps<T> {
  /** 数据源 */
  data: T[]
  /** 列定义 */
  columns: Column<T>[]
  /** 行唯一标识 */
  rowKey: (row: T) => string
  /** 空状态渲染 */
  emptyState?: React.ReactNode
  /** 行点击回调 */
  onRowClick?: (row: T) => void
  /** 分页大小（null = 不分页） */
  pageSize?: number | null
  /** 初始排序 */
  initialSort?: { key: string; direction: SortDirection }
  /** 自定义类名 */
  className?: string
}

/** 通用表格组件——排序 / 分页 */
export function DataTable<T>({
  data,
  columns,
  rowKey,
  emptyState,
  onRowClick,
  pageSize = null,
  initialSort,
  className,
}: DataTableProps<T>) {
  const [sortKey, setSortKey] = React.useState<string | null>(initialSort?.key ?? null)
  const [sortDir, setSortDir] = React.useState<SortDirection>(initialSort?.direction ?? null)
  const [currentPage, setCurrentPage] = React.useState(0)

  // 排序
  const sortedData = React.useMemo(() => {
    if (!sortKey || !sortDir) return data
    return [...data].sort((a, b) => {
      const aVal = a[sortKey as keyof T]
      const bVal = b[sortKey as keyof T]
      if (aVal == null) return 1
      if (bVal == null) return -1
      const cmp = String(aVal) < String(bVal) ? -1 : String(aVal) > String(bVal) ? 1 : 0
      return sortDir === 'asc' ? cmp : -cmp
    })
  }, [data, sortKey, sortDir])

  // 分页
  const totalPages = pageSize ? Math.ceil(sortedData.length / pageSize) : 1
  const pageData = pageSize
    ? sortedData.slice(currentPage * pageSize, (currentPage + 1) * pageSize)
    : sortedData

  // 排序切换
  const handleSort = (key: string) => {
    if (sortKey !== key) {
      setSortKey(key)
      setSortDir('asc')
    } else if (sortDir === 'asc') {
      setSortDir('desc')
    } else if (sortDir === 'desc') {
      setSortKey(null)
      setSortDir(null)
    } else {
      setSortDir('asc')
    }
  }

  return (
    <div className={cn('w-full', className)}>
      <div className="overflow-x-auto rounded-md border border-border">
        <table className="w-full text-sm">
          <thead className="bg-muted/50">
            <tr>
              {columns.map((col) => (
                <th
                  key={String(col.key)}
                  className={cn(
                    'px-4 py-2.5 font-medium text-muted-foreground',
                    col.align === 'center' && 'text-center',
                    col.align === 'right' && 'text-right',
                    col.sortable && 'cursor-pointer select-none hover:text-foreground',
                    col.width
                  )}
                  onClick={col.sortable ? () => handleSort(String(col.key)) : undefined}
                >
                  <span className="inline-flex items-center gap-1">
                    {col.header}
                    {col.sortable && (
                      <span className="text-muted-foreground/50">
                        {sortKey === String(col.key) && sortDir === 'asc' ? (
                          <ChevronUpIcon className="size-3.5" />
                        ) : sortKey === String(col.key) && sortDir === 'desc' ? (
                          <ChevronDownIcon className="size-3.5" />
                        ) : (
                          <ChevronsUpDownIcon className="size-3.5" />
                        )}
                      </span>
                    )}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {pageData.length === 0 ? (
              <tr>
                <td colSpan={columns.length} className="px-4 py-8 text-center text-muted-foreground">
                  {emptyState ?? '暂无数据'}
                </td>
              </tr>
            ) : (
              pageData.map((row) => (
                <tr
                  key={rowKey(row)}
                  onClick={onRowClick ? () => onRowClick(row) : undefined}
                  className={cn(
                    'border-t border-border transition-colors',
                    onRowClick && 'cursor-pointer hover:bg-accent/50'
                  )}
                >
                  {columns.map((col) => (
                    <td
                      key={String(col.key)}
                      className={cn(
                        'px-4 py-2.5',
                        col.align === 'center' && 'text-center',
                        col.align === 'right' && 'text-right'
                      )}
                    >
                      {col.cell ? col.cell(row) : String(row[col.key as keyof T] ?? '')}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* 分页 */}
      {pageSize && totalPages > 1 && (
        <div className="flex items-center justify-between px-2 py-3 text-sm">
          <span className="text-muted-foreground">
            第 {currentPage + 1} / {totalPages} 页（共 {sortedData.length} 条）
          </span>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={currentPage === 0}
              onClick={() => setCurrentPage((p) => Math.max(0, p - 1))}
            >
              上一页
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={currentPage >= totalPages - 1}
              onClick={() => setCurrentPage((p) => Math.min(totalPages - 1, p + 1))}
            >
              下一页
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}