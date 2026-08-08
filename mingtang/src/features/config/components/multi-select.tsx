import { useState, useMemo, type ChangeEvent } from 'react'
import { X, Check, ChevronsUpDown } from 'lucide-react'

export interface MultiSelectOption {
  label: string
  value: string
}

export interface MultiSelectProps {
  options: MultiSelectOption[]
  selected: string[]
  onChange: (values: string[]) => void
  placeholder?: string
  emptyText?: string
  className?: string
  disabled?: boolean
}

/** 多选下拉框——搜索 + 徽章展示 */
export function MultiSelect({
  options,
  selected,
  onChange,
  placeholder = '请选择...',
  emptyText = '无匹配项',
  className = '',
  disabled = false,
}: MultiSelectProps) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')

  const filteredOptions = useMemo(() => {
    if (!search.trim()) return options
    return options.filter((opt) =>
      opt.label.toLowerCase().includes(search.toLowerCase()) ||
      opt.value.toLowerCase().includes(search.toLowerCase())
    )
  }, [options, search])

  const toggleOption = (value: string) => {
    if (selected.includes(value)) {
      onChange(selected.filter((v) => v !== value))
    } else {
      onChange([...selected, value])
    }
  }

  const removeOption = (value: string) => {
    onChange(selected.filter((v) => v !== value))
  }

  const selectedLabels = useMemo(() => {
    return selected.map((v) => options.find((opt) => opt.value === v)).filter(Boolean) as MultiSelectOption[]
  }, [selected, options])

  return (
    <div className={`relative ${className}`} data-testid="multi-select">
      <div
        className={`flex flex-wrap items-center gap-1 rounded-md border border-border bg-background px-2 py-1.5 min-h-9 ${
          disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'
        }`}
        onClick={() => !disabled && setOpen(!open)}
        data-testid="multi-select-trigger"
      >
        {selectedLabels.length === 0 && (
          <span className="text-sm text-muted-foreground">{placeholder}</span>
        )}
        {selectedLabels.map((opt) => (
          <span
            key={opt.value}
            className="inline-flex items-center gap-1 rounded bg-muted px-2 py-0.5 text-xs"
            data-testid={`multi-select-badge-${opt.value}`}
          >
            {opt.label}
            {!disabled && (
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation()
                  removeOption(opt.value)
                }}
                className="text-muted-foreground hover:text-foreground"
                aria-label={`移除 ${opt.label}`}
              >
                <X className="h-3 w-3" />
              </button>
            )}
          </span>
        ))}
        <ChevronsUpDown className="h-4 w-4 text-muted-foreground ml-auto" />
      </div>

      {open && !disabled && (
        <div className="absolute z-10 mt-1 w-full rounded-md border border-border bg-background shadow-md" data-testid="multi-select-dropdown">
          <input
            type="text"
            value={search}
            onChange={(e: ChangeEvent<HTMLInputElement>) => setSearch(e.target.value)}
            placeholder="搜索..."
            className="w-full border-b border-border px-3 py-2 text-sm focus:outline-none"
            data-testid="multi-select-search"
          />
          <div className="max-h-48 overflow-auto py-1">
            {filteredOptions.length === 0 ? (
              <div className="px-3 py-2 text-sm text-muted-foreground">{emptyText}</div>
            ) : (
              filteredOptions.map((opt) => (
                <div
                  key={opt.value}
                  onClick={() => toggleOption(opt.value)}
                  className="flex items-center gap-2 px-3 py-1.5 text-sm hover:bg-muted cursor-pointer"
                  data-testid={`multi-select-option-${opt.value}`}
                >
                  <span className="flex-1">{opt.label}</span>
                  {selected.includes(opt.value) && (
                    <Check className="h-4 w-4 text-foreground" />
                  )}
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  )
}