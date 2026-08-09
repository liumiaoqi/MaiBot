import { describe, it, expect, beforeEach, vi } from 'vitest'

describe('TE-2-1：FOUC 防止（index.html 内联脚本逻辑验证）', () => {
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.className = ''
    document.documentElement.dataset.dashboardStyle = ''
  })

  function applyFoucScript() {
    try {
      const mode = localStorage.getItem('maibot-theme-mode')
      let isDark: boolean
      if (mode === 'light') {
        isDark = false
      } else if (mode === 'system') {
        isDark = window.matchMedia('(prefers-color-scheme: dark)').matches
      } else {
        isDark = true
      }
      if (isDark) {
        document.documentElement.classList.add('dark')
      } else {
        document.documentElement.classList.remove('dark')
      }
      const style = localStorage.getItem('maibot-theme-dashboard-style')
      document.documentElement.dataset.dashboardStyle =
        style === 'modern' || style === 'future-retro' ? style : 'future-retro'
    } catch {
      document.documentElement.classList.add('dark')
      document.documentElement.dataset.dashboardStyle = 'future-retro'
    }
  }

  it('mode=dark → documentElement class 含 dark', () => {
    localStorage.setItem('maibot-theme-mode', 'dark')
    applyFoucScript()
    expect(document.documentElement.classList.contains('dark')).toBe(true)
  })

  it('mode=light → documentElement class 不含 dark', () => {
    localStorage.setItem('maibot-theme-mode', 'light')
    applyFoucScript()
    expect(document.documentElement.classList.contains('dark')).toBe(false)
  })

  it('mode=system + matchMedia dark → class 含 dark', () => {
    localStorage.setItem('maibot-theme-mode', 'system')
    vi.spyOn(window, 'matchMedia').mockReturnValue({
      matches: true,
      media: '',
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })
    applyFoucScript()
    expect(document.documentElement.classList.contains('dark')).toBe(true)
  })

  it('mode=system + matchMedia light → class 不含 dark', () => {
    localStorage.setItem('maibot-theme-mode', 'system')
    vi.spyOn(window, 'matchMedia').mockReturnValue({
      matches: false,
      media: '',
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })
    applyFoucScript()
    expect(document.documentElement.classList.contains('dark')).toBe(false)
  })

  it('首次进入（无存储键）→ 默认 dark（深色默认 REQ-R2-01）', () => {
    applyFoucScript()
    expect(document.documentElement.classList.contains('dark')).toBe(true)
    expect(document.documentElement.dataset.dashboardStyle).toBe('future-retro')
  })

  it('dashboard-style=modern → dataset.dashboardStyle=modern', () => {
    localStorage.setItem('maibot-theme-dashboard-style', 'modern')
    applyFoucScript()
    expect(document.documentElement.dataset.dashboardStyle).toBe('modern')
  })

  it('dashboard-style=future-retro → dataset.dashboardStyle=future-retro', () => {
    localStorage.setItem('maibot-theme-dashboard-style', 'future-retro')
    applyFoucScript()
    expect(document.documentElement.dataset.dashboardStyle).toBe('future-retro')
  })

  it('非法 dashboard-style → 默认 future-retro', () => {
    localStorage.setItem('maibot-theme-dashboard-style', 'bogus')
    applyFoucScript()
    expect(document.documentElement.dataset.dashboardStyle).toBe('future-retro')
  })

  it('非法 mode → 默认 dark', () => {
    localStorage.setItem('maibot-theme-mode', 'bogus')
    applyFoucScript()
    expect(document.documentElement.classList.contains('dark')).toBe(true)
  })
})
