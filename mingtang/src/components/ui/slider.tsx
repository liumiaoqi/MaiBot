import * as SliderPrimitive from '@radix-ui/react-slider'
import * as React from 'react'

import { cn } from '@/lib/utils'

/**
 * Slider 滑块组件
 *
 * 支持显示当前值的 config 模式（thumb 内嵌值标签）。
 * 对齐 dashboard 原版行为，去掉 data-dashboard-* 属性。
 */
type SliderProps = React.ComponentPropsWithoutRef<typeof SliderPrimitive.Root> & {
  /** config 模式：thumb 显示当前值 */
  showValue?: boolean
  /** 值格式化：fixed-2 保留两位小数 */
  valueFormat?: 'fixed-2'
}

function Slider({
  className,
  value,
  defaultValue,
  showValue,
  valueFormat,
  ...props
}: SliderProps) {
  const currentValues = Array.isArray(value)
    ? value
    : Array.isArray(defaultValue)
      ? defaultValue
      : []
  const thumbCount = Array.isArray(value)
    ? value.length
    : Array.isArray(defaultValue)
      ? defaultValue.length
      : 1

  return (
    <SliderPrimitive.Root
      data-slot="slider"
      className={cn(
        'relative flex w-full touch-none select-none items-center',
        className
      )}
      value={value}
      defaultValue={defaultValue}
      {...props}
    >
      <SliderPrimitive.Track
        data-slot="slider-track"
        className={cn(
          'relative h-1.5 w-full grow overflow-hidden rounded-full bg-primary/20',
          showValue && 'h-3'
        )}
      >
        <SliderPrimitive.Range
          data-slot="slider-range"
          className="absolute h-full bg-primary"
        />
      </SliderPrimitive.Track>
      {Array.from({ length: Math.max(1, thumbCount) }).map((_, index) => (
        <SliderPrimitive.Thumb
          key={index}
          data-slot="slider-thumb"
          className={cn(
            'block h-4 w-4 rounded-full border border-primary/50 bg-background shadow transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50',
            showValue &&
              'inline-flex h-7 min-w-9 items-center justify-center rounded-full border-2 border-primary bg-background px-1 text-xs font-semibold leading-none text-foreground'
          )}
        >
          {showValue && (
            <span
              data-slot="slider-value"
              className="pointer-events-none select-none"
            >
              {valueFormat === 'fixed-2' && typeof currentValues[index] === 'number'
                ? currentValues[index].toFixed(2)
                : currentValues[index]}
            </span>
          )}
        </SliderPrimitive.Thumb>
      ))}
    </SliderPrimitive.Root>
  )
}

export { Slider }