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
})