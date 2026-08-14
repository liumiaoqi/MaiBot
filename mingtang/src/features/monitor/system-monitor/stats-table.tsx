/**
 * StatsTable 通用统计表格（P2-C #1——system-monitor 两段原生 table 抽取）
 *
 * 泛型列配置：header 由调用方传入（i18n 文案）、数字列 align='right' 自动附加
 * text-right tabular-nums、末列去右内边距（与抽取前原生表逐像素一致）。
 */
import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

export interface StatsColumn<T> {
  key: string
  header: ReactNode
  /** 'right' 时表头/单元格右对齐且单元格使用 tabular-nums（数字列） */
  align?: 'left' | 'right'
  /** 追加到单元格的 class（如首列 truncate 限宽） */
  cellClassName?: string
  render: (row: T) => ReactNode
}

interface StatsTableProps<T> {
  columns: StatsColumn<T>[]
  rows: T[]
  rowKey: (row: T) => string
}

export function StatsTable<T>({ columns, rows, rowKey }: StatsTableProps<T>) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b text-left text-xs text-muted-foreground">
            {columns.map((col, colIndex) => (
              <th
                key={col.key}
                className={cn(
                  'pb-2 font-medium',
                  colIndex < columns.length - 1 && 'pr-3',
                  col.align === 'right' && 'text-right',
                  col.cellClassName
                )}
              >
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={rowKey(row)} className="border-b last:border-0">
              {columns.map((col, colIndex) => (
                <td
                  key={col.key}
                  className={cn(
                    'py-2',
                    colIndex < columns.length - 1 && 'pr-3',
                    col.align === 'right' && 'text-right tabular-nums',
                    col.cellClassName
                  )}
                >
                  {col.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
