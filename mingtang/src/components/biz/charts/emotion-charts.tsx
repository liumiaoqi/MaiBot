/**
 * 情绪雷达图 + 情绪柱状图（R4-3 D1 抽取——原 emotion-monitor 与 emotion-landscape 双份内联实现收敛）
 *
 * 定位：纯展示图表组件——数据 props（emotions/emotionLabels）+ 色板 props（colors/icons）注入，
 *      零 biz → features 依赖；色板由调用方从 emotion-constants 传入（数据可视化色板豁免）。
 * 行为等价：与抽取前两个内联实现逐行同构（仅色板来源从模块常量改为 props 注入）。
 */

interface EmotionRadarChartProps {
  /** 情绪强度数据（emotion key → 0-100 强度） */
  emotions: Record<string, number>
  /** 情绪标签（emotion key → 显示名） */
  emotionLabels: Record<string, string>
  /** 情绪图标色板（EMOTION_ICONS——数据可视化色板豁免） */
  icons: Record<string, string>
  /** SVG 边长（px），默认 180 */
  size?: number
  /** 数据区填充/描边色（默认 currentColor——调用方注入主导情绪色） */
  color?: string
}

export function EmotionRadarChart({
  emotions,
  emotionLabels,
  icons,
  size = 180,
  color = 'currentColor',
}: EmotionRadarChartProps) {
  const maxVal = Math.max(...Object.values(emotions), 1)
  const center = size / 2
  const radius = size / 2 - 24
  const entries = Object.entries(emotions)
  const n = entries.length

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      {[0.25, 0.5, 0.75, 1].map((ring) => (
        <polygon
          key={ring}
          points={entries
            .map((_, i) => {
              const angle = (2 * Math.PI * i) / n - Math.PI / 2
              const x = center + radius * ring * Math.cos(angle)
              const y = center + radius * ring * Math.sin(angle)
              return `${x},${y}`
            })
            .join(' ')}
          fill="none"
          stroke="currentColor"
          strokeOpacity={0.12}
          strokeWidth={1}
        />
      ))}
      {entries.map(([,], i) => {
        const angle = (2 * Math.PI * i) / n - Math.PI / 2
        const x = center + radius * Math.cos(angle)
        const y = center + radius * Math.sin(angle)
        return (
          <line
            key={i}
            x1={center}
            y1={center}
            x2={x}
            y2={y}
            stroke="currentColor"
            strokeOpacity={0.08}
            strokeWidth={1}
          />
        )
      })}
      <polygon
        points={entries
          .map(([, val], i) => {
            const ratio = val / maxVal
            const angle = (2 * Math.PI * i) / n - Math.PI / 2
            const x = center + radius * ratio * Math.cos(angle)
            const y = center + radius * ratio * Math.sin(angle)
            return `${x},${y}`
          })
          .join(' ')}
        fill={color}
        fillOpacity={0.15}
        stroke={color}
        strokeWidth={2}
      />
      {entries.map(([key], i) => {
        const angle = (2 * Math.PI * i) / n - Math.PI / 2
        const lx = center + (radius + 18) * Math.cos(angle)
        const ly = center + (radius + 18) * Math.sin(angle)
        return (
          <text
            key={key}
            x={lx}
            y={ly}
            textAnchor="middle"
            dominantBaseline="middle"
            className="fill-muted-foreground"
            fontSize={9}
          >
            {icons[key]} {emotionLabels[key] || key}
          </text>
        )
      })}
    </svg>
  )
}

interface EmotionBarChartProps {
  /** 情绪强度数据（emotion key → 0-100 强度） */
  emotions: Record<string, number>
  /** 情绪标签（emotion key → 显示名） */
  emotionLabels: Record<string, string>
  /** 情绪色板（EMOTION_COLORS——数据可视化色板豁免） */
  colors: Record<string, string>
  /** 情绪图标色板（EMOTION_ICONS——数据可视化色板豁免） */
  icons: Record<string, string>
  /** 是否显示数值（默认 true） */
  showValues?: boolean
}

export function EmotionBarChart({
  emotions,
  emotionLabels,
  colors,
  icons,
  showValues = true,
}: EmotionBarChartProps) {
  return (
    <div className="space-y-1.5">
      {Object.entries(emotions).map(([key, val]) => (
        <div key={key} className="flex items-center gap-2">
          <span className="w-14 text-xs text-muted-foreground shrink-0 truncate">
            {icons[key]} {emotionLabels[key] || key}
          </span>
          <div className="flex-1 h-1.5 bg-muted rounded-full overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-500"
              style={{
                width: `${Math.min(val, 100)}%`,
                // `#9b59b6` 为 colors 缺失兜底色（数据可视化色板豁免）
                backgroundColor: colors[key] || '#9b59b6',
              }}
            />
          </div>
          {showValues && (
            <span className="text-xs text-muted-foreground w-7 text-right">{Math.round(val)}</span>
          )}
        </div>
      ))}
    </div>
  )
}
