/**
 * 多选下拉框组件（R4-1-2-3）
 *
 * 从 dashboard 行为等价搬移——适配无 dnd-kit/command 依赖
 * 核心行为保留：搜索过滤 + 单击选择/取消 + 标签展示
 * 简化：无拖拽排序（dnd-kit 不可用——R4-1 无新增依赖约束）
 *
 * design.md §3.8.3 / ADR-5 主题零黑字
 */
import * as React from 'react'
import { X, Check, ChevronsUpDown } from 'lucide-react'

import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'

export interface MultiSelectOption {
  label: string
  value: string
}

interface MultiSelectProps {
  options: MultiSelectOption[]
  selected: string[]
  onChange: (values: string[]) => void
  placeholder?: string
  emptyText?: string
  className?: string
  compact?: boolean
  disabled?: boolean
}

export function MultiSelect({
  options,
  selected,
  onChange,
  placeholder = '选择选项...',
  emptyText = '未找到选项',
  className,
  compact = false,
  disabled = false,
}: MultiSelectProps) {
  const [openState, setOpenState] = React.useState(false)
  const [search, setSearch] = React.useState('')
  const open = disabled ? false : openState

  const handleSelect = (value: string) => {
    if (disabled) return
    if (selected.includes(value)) {
      onChange(selected.filter((item) => item !== value))
    } else {
      onChange([...selected, value])
    }
  }

  const handleRemove = (value: string) => {
    if (disabled) return
    onChange(selected.filter((item) => item !== value))
  }

  const filteredOptions = search
    ? options.filter((opt) =>
        opt.label.toLowerCase().includes(search.toLowerCase()) ||
        opt.value.toLowerCase().includes(search.toLowerCase())
      )
    : options

  return (
    <Popover
      open={disabled ? false : open}
      onOpenChange={(nextOpen) => {
        if (!disabled) {
          setOpenState(nextOpen)
          if (!nextOpen) setSearch('')
        }
      }}
    >
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          role="combobox"
          aria-expanded={open}
          disabled={disabled}
          className={cn(
            'h-auto w-full justify-between',
            compact ? 'min-h-9 px-2 py-1.5' : 'min-h-10',
            className
          )}
        >
          <div className="flex flex-1 flex-wrap gap-1">
            {selected.length === 0 ? (
              <span className={cn('text-muted-foreground', compact && 'text-sm')}>{placeholder}</span>
            ) : (
              selected.map((value) => {
                const option = options.find((opt) => opt.value === value)
                return (
                  <Badge
                    key={value}
                    variant="secondary"
                    className={cn(
                      'flex items-center gap-1 hover:bg-secondary/80',
                      disabled && 'opacity-60',
                      compact && 'min-h-6 max-w-[calc(100vw-5rem)] px-1.5 py-0 text-[11px] leading-none sm:max-w-full'
                    )}
                  >
                    <span className={cn(compact && 'min-w-0 truncate')}>{option?.label || value}</span>
                    <span
                      role="button"
                      tabIndex={0}
                      className={cn(
                        'ml-1 inline-flex shrink-0 cursor-pointer items-center justify-center rounded-sm hover:bg-destructive/20 focus:outline-none focus:ring-1 focus:ring-destructive',
                        compact ? 'h-4 w-4' : 'h-5 w-5'
                      )}
                      onClick={(e) => {
                        e.preventDefault()
                        e.stopPropagation()
                        handleRemove(value)
                      }}
                      aria-disabled={disabled}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault()
                          handleRemove(value)
                        }
                      }}
                    >
                      <X
                        className="h-3 w-3 hover:text-destructive"
                        strokeWidth={2}
                        fill="none"
                      />
                    </span>
                  </Badge>
                )
              })
            )}
          </div>
          <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" strokeWidth={2} fill="none" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-full p-0" align="start">
        <div className="p-2">
          <Input
            placeholder="搜索..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="h-9"
          />
        </div>
        <div className="max-h-48 overflow-y-auto p-1">
          {filteredOptions.length === 0 ? (
            <p className="px-2 py-4 text-center text-sm text-muted-foreground">{emptyText}</p>
          ) : (
            filteredOptions.map((option) => {
              const isSelected = selected.includes(option.value)
              return (
                <button
                  key={option.value}
                  type="button"
                  disabled={disabled}
                  onClick={() => handleSelect(option.value)}
                  className={cn(
                    'flex w-full items-center rounded-sm px-2 py-1.5 text-sm transition-colors',
                    isSelected
                      ? 'bg-accent text-accent-foreground'
                      : 'text-foreground hover:bg-muted'
                  )}
                >
                  <div
                    className={cn(
                      'mr-2 flex h-4 w-4 items-center justify-center rounded-sm border border-primary',
                      isSelected
                        ? 'bg-primary text-primary-foreground'
                        : 'opacity-50 [&_svg]:invisible'
                    )}
                  >
                    <Check className="h-3 w-3" strokeWidth={2} fill="none" />
                  </div>
                  <span>{option.label}</span>
                </button>
              )
            })
          )}
        </div>
      </PopoverContent>
    </Popover>
  )
}