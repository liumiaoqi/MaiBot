/**
 * 主题参数公共滑块行——两套界面风格（modern 手风琴 / future-retro 面板）共用
 * 控件语言统一的关键：label + 滑块 + 数值 + 说明 一行式，两套面板长得一样
 */
interface ThemeSliderRowProps {
  label: string
  /** 受控模式值（与 defaultValue 互斥） */
  value?: number
  /** 非受控模式默认值（与 value 互斥） */
  defaultValue?: number
  min: number
  max: number
  step?: number
  onChange: (value: number) => void
  /** 说明文字（参数作用——用户"不知道看哪里"的答案） */
  hint?: string
  /** 当前值显示（如 "55%"——与 hint 同行） */
  displayValue?: string
  disabled?: boolean
  dataTestId?: string
}

export function ThemeSliderRow({
  label,
  value,
  defaultValue,
  min,
  max,
  step = 1,
  onChange,
  hint,
  displayValue,
  disabled,
  dataTestId,
}: ThemeSliderRowProps) {
  const meta = displayValue || hint
  const controlled = value !== undefined
  return (
    <div className="space-y-1">
      <label className="text-sm font-medium text-foreground">{label}</label>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        {...(controlled ? { value } : { defaultValue })}
        disabled={disabled}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full"
        data-testid={dataTestId}
      />
      {meta && (
        <span className="text-xs text-muted-foreground">
          {displayValue ? `${displayValue} — ${hint ?? ''}` : hint}
        </span>
      )}
    </div>
  )
}
