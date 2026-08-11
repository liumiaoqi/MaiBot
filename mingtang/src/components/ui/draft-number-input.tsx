/**
 * DraftNumberInput —— 数字输入占位组件。
 *
 * 维持 field-renderer 中调用方 props 契约：受控 value + onValueChange 回调，
 * 支持可选 min/max/step/placeholder/disabled。defaultValue 保留以兼容调用方传参，
 * 本占位实现以受控 value 优先。
 */
import type { CSSProperties } from 'react'

interface DraftNumberInputProps {
  value?: unknown
  defaultValue?: unknown
  onValueChange: (value: unknown) => void
  min?: number
  max?: number
  step?: number
  placeholder?: string
  disabled?: boolean
  className?: string
  style?: CSSProperties
}

export function DraftNumberInput({
  value,
  defaultValue,
  onValueChange,
  min,
  max,
  step,
  placeholder,
  disabled,
  className,
  style,
}: DraftNumberInputProps) {
  const numericValue =
    typeof value === 'number'
      ? value
      : typeof defaultValue === 'number'
        ? defaultValue
        : Number.NaN

  return (
    <input
      type="number"
      value={Number.isNaN(numericValue) ? '' : numericValue}
      onChange={(event) => {
        const parsed = Number(event.target.value)
        onValueChange(Number.isNaN(parsed) ? event.target.value : parsed)
      }}
      min={min}
      max={max}
      step={step}
      placeholder={placeholder}
      disabled={disabled}
      className={className}
      style={style}
    />
  )
}