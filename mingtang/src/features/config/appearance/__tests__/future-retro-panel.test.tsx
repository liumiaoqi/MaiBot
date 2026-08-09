import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { FutureRetroPanel } from '../future-retro-panel'
import { THEME_STORAGE_KEYS } from '@/lib/theme/storage'
import { DEFAULT_FUTURE_RETRO_STYLE_CONFIG } from '@/lib/theme/tokens'

// 模拟 i18n
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}))

describe('R2-1-4：FutureRetroPanel 六维参数面板', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('渲染六维参数控件', () => {
    render(<FutureRetroPanel />)
    expect(screen.getByTestId('fr-font-size')).toBeInTheDocument()
    expect(screen.getByTestId('fr-paper-warmth')).toBeInTheDocument()
    expect(screen.getByTestId('fr-texture-style')).toBeInTheDocument()
    expect(screen.getByTestId('fr-texture-intensity')).toBeInTheDocument()
    expect(screen.getByTestId('fr-panel-depth')).toBeInTheDocument()
    expect(screen.getByTestId('fr-stroke-scale')).toBeInTheDocument()
  })

  it('纹理风格 5 张缩略卡片（fine/coarse/dot-grid/ruled/none）', () => {
    render(<FutureRetroPanel />)
    const cards = screen.getAllByTestId(/fr-texture-card-/)
    expect(cards).toHaveLength(5)
    expect(screen.getByTestId('fr-texture-card-fine')).toBeInTheDocument()
    expect(screen.getByTestId('fr-texture-card-coarse')).toBeInTheDocument()
    expect(screen.getByTestId('fr-texture-card-dot-grid')).toBeInTheDocument()
    expect(screen.getByTestId('fr-texture-card-ruled')).toBeInTheDocument()
    expect(screen.getByTestId('fr-texture-card-none')).toBeInTheDocument()
  })

  it('字号滑块 12-20px 范围', () => {
    render(<FutureRetroPanel />)
    const slider = screen.getByTestId('fr-font-size') as HTMLInputElement
    expect(Number(slider.min)).toBe(12)
    expect(Number(slider.max)).toBe(20)
  })

  it('纸暖度 0-100% 范围', () => {
    render(<FutureRetroPanel />)
    const slider = screen.getByTestId('fr-paper-warmth') as HTMLInputElement
    expect(Number(slider.min)).toBe(0)
    expect(Number(slider.max)).toBe(100)
  })

  it('纹理强度 10-100% 范围', () => {
    render(<FutureRetroPanel />)
    const slider = screen.getByTestId('fr-texture-intensity') as HTMLInputElement
    expect(Number(slider.min)).toBe(10)
    expect(Number(slider.max)).toBe(100)
  })

  it('面板深度 0-100% 范围', () => {
    render(<FutureRetroPanel />)
    const slider = screen.getByTestId('fr-panel-depth') as HTMLInputElement
    expect(Number(slider.min)).toBe(0)
    expect(Number(slider.max)).toBe(100)
  })

  it('描边比例 50-100% 范围', () => {
    render(<FutureRetroPanel />)
    const slider = screen.getByTestId('fr-stroke-scale') as HTMLInputElement
    expect(Number(slider.min)).toBe(50)
    expect(Number(slider.max)).toBe(100)
  })

  it('纹理风格选 none 时纹理强度 disabled', () => {
    render(<FutureRetroPanel />)
    fireEvent.click(screen.getByTestId('fr-texture-card-none'))
    const intensitySlider = screen.getByTestId('fr-texture-intensity') as HTMLInputElement
    expect(intensitySlider).toBeDisabled()
  })

  it('即拖即生效——参数变化写入 localStorage', () => {
    render(<FutureRetroPanel />)
    const slider = screen.getByTestId('fr-paper-warmth') as HTMLInputElement
    fireEvent.change(slider, { target: { value: '50' } })
    const stored = localStorage.getItem(THEME_STORAGE_KEYS.STYLE_CONFIG)
    expect(stored).not.toBeNull()
    const config = JSON.parse(stored!)
    expect(config.futureRetro.paperWarmth).toBe(50)
  })

  it('恢复默认按钮 → 六维回到默认值', () => {
    render(<FutureRetroPanel />)
    // 先修改一个值
    const slider = screen.getByTestId('fr-paper-warmth') as HTMLInputElement
    fireEvent.change(slider, { target: { value: '50' } })
    // 点恢复默认
    fireEvent.click(screen.getByTestId('fr-reset-default'))
    const stored = localStorage.getItem(THEME_STORAGE_KEYS.STYLE_CONFIG)
    const config = JSON.parse(stored!)
    expect(config.futureRetro).toEqual(DEFAULT_FUTURE_RETRO_STYLE_CONFIG)
  })

  it('无存储时显示默认值', () => {
    render(<FutureRetroPanel />)
    const warmthSlider = screen.getByTestId('fr-paper-warmth') as HTMLInputElement
    expect(Number(warmthSlider.value)).toBe(DEFAULT_FUTURE_RETRO_STYLE_CONFIG.paperWarmth)
    const intensitySlider = screen.getByTestId('fr-texture-intensity') as HTMLInputElement
    expect(Number(intensitySlider.value)).toBe(DEFAULT_FUTURE_RETRO_STYLE_CONFIG.textureIntensity)
  })

  it('TE-1-2：所有 label 有 text-foreground 类（7 处——六维参数 + 实时预览）', () => {
    render(<FutureRetroPanel />)
    const labels = document.querySelectorAll('label.text-foreground')
    expect(labels).toHaveLength(7)
  })

  it('TE-1-2：label 不硬编码颜色（类名含 text-foreground 非 hex/rgb）', () => {
    render(<FutureRetroPanel />)
     const labels = document.querySelectorAll('label')
     labels.forEach((label) => {
       const cls = label.className
       expect(cls).toContain('text-foreground')
       expect(cls).not.toMatch(/#[0-9a-fA-F]{3,8}/)
       expect(cls).not.toMatch(/rgb\(/)
     })
   })

  it('TE-1-3：纹理卡片 backgroundSize 为 auto（非 cover）', () => {
    render(<FutureRetroPanel />)
    const fineCard = screen.getByTestId('fr-texture-card-fine') as HTMLElement
    expect(fineCard.style.backgroundSize).toBe('auto')
  })

  it('TE-1-3：4 张纹理卡片有 backgroundImage（除 none）', () => {
    render(<FutureRetroPanel />)
    const styles = ['fine', 'coarse', 'dot-grid', 'ruled']
    styles.forEach((style) => {
      const card = screen.getByTestId(`fr-texture-card-${style}`) as HTMLElement
      expect(card.style.backgroundImage).not.toBe('')
      expect(card.style.backgroundImage).toContain('data:image/svg+xml')
    })
  })

  it('TE-1-3：none 纹理卡片无 backgroundImage', () => {
    render(<FutureRetroPanel />)
    const noneCard = screen.getByTestId('fr-texture-card-none') as HTMLElement
    expect(noneCard.style.backgroundImage).toBe('')
  })

  it('字号滑块——拖动写入 storage 的 baseFontSize（不再是纯本地 state）', () => {
    render(<FutureRetroPanel />)
    const slider = screen.getByTestId('fr-font-size') as HTMLInputElement
    fireEvent.change(slider, { target: { value: '18' } })
    const stored = localStorage.getItem(THEME_STORAGE_KEYS.STYLE_CONFIG)
    expect(stored).not.toBeNull()
    const config = JSON.parse(stored!)
    expect(config.futureRetro.baseFontSize).toBe(18)
  })

  it('实时预览卡片渲染（fr-preview + fr-preview-card）', () => {
    render(<FutureRetroPanel />)
    expect(screen.getByTestId('fr-preview')).toBeInTheDocument()
    const card = screen.getByTestId('fr-preview-card') as HTMLElement
    expect(card.style.backgroundColor).toBeTruthy()
  })

  it('面板深度变化 → 预览卡片背景色实时变化', () => {
    render(<FutureRetroPanel />)
    const card = screen.getByTestId('fr-preview-card') as HTMLElement
    const before = card.style.backgroundColor
    const depthSlider = screen.getByTestId('fr-panel-depth') as HTMLInputElement
    fireEvent.change(depthSlider, { target: { value: '0' } })
    const after = card.style.backgroundColor
    expect(after).not.toBe(before)
  })
 })