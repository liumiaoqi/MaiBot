/**
 * EmotionRadarChart / EmotionBarChart 测试（R4-3 D1 抽取——共享图表组件契约验证）
 *
 * 验证：色板 props（colors/icons）注入渲染 + 数据渲染 + showValues 开关
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { EmotionBarChart, EmotionRadarChart } from '../emotion-charts'

const EMOTIONS: Record<string, number> = { happy: 60, calm: 40 }
const LABELS: Record<string, string> = { happy: '开心', calm: '平静' }
const COLORS: Record<string, string> = { happy: '#fbbf24', calm: '#34d399' }
const ICONS: Record<string, string> = { happy: '😊', calm: '😌' }

describe('EmotionRadarChart', () => {
  it('渲染 SVG（默认 size=180）+ 情绪标签（图标 + 名称）', () => {
    render(<EmotionRadarChart emotions={EMOTIONS} emotionLabels={LABELS} icons={ICONS} />)

    const svg = document.querySelector('svg')
    expect(svg).toBeInTheDocument()
    expect(svg).toHaveAttribute('width', '180')
    expect(svg).toHaveAttribute('height', '180')
    expect(screen.getByText('😊 开心')).toBeInTheDocument()
    expect(screen.getByText('😌 平静')).toBeInTheDocument()
  })

  it('size/color props 注入生效（数据区多边形用注入色）', () => {
    render(
      <EmotionRadarChart
        emotions={EMOTIONS}
        emotionLabels={LABELS}
        icons={ICONS}
        size={220}
        color="#ef4444"
      />
    )

    const svg = document.querySelector('svg')
    expect(svg).toHaveAttribute('width', '220')
    // 前 4 个 polygon 是网格环（fill="none"），第 5 个是数据区多边形
    const dataPolygon = svg!.querySelectorAll('polygon')[4]
    expect(dataPolygon).toHaveAttribute('fill', '#ef4444')
    expect(dataPolygon).toHaveAttribute('stroke', '#ef4444')
  })
})

describe('EmotionBarChart', () => {
  it('渲染标签 + 注入色条 + 数值', () => {
    render(
      <EmotionBarChart
        emotions={EMOTIONS}
        emotionLabels={LABELS}
        colors={COLORS}
        icons={ICONS}
      />
    )

    expect(screen.getByText('😊 开心')).toBeInTheDocument()
    expect(screen.getByText('60')).toBeInTheDocument()
    expect(screen.getByText('40')).toBeInTheDocument()

    // 色条背景色来自注入色板（行内 [div 包裹层, div 色条]）
    const happyBar = screen.getByText('😊 开心').parentElement!.querySelectorAll('div')[1]
    expect(happyBar).toHaveStyle({ backgroundColor: '#fbbf24' })
  })

  it('showValues=false 隐藏数值', () => {
    render(
      <EmotionBarChart
        emotions={EMOTIONS}
        emotionLabels={LABELS}
        colors={COLORS}
        icons={ICONS}
        showValues={false}
      />
    )

    expect(screen.getByText('😊 开心')).toBeInTheDocument()
    expect(screen.queryByText('60')).not.toBeInTheDocument()
  })
})
