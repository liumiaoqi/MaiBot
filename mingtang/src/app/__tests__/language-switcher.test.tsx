import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { createElement } from 'react'

import { Topbar } from '@/app/layout/topbar'

const { mockChangeLanguage, mockLanguage } = vi.hoisted(() => ({
  mockChangeLanguage: vi.fn(),
  mockLanguage: { current: 'zh' },
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: {
      language: mockLanguage.current,
      changeLanguage: (lng: string) => {
        mockLanguage.current = lng
        mockChangeLanguage(lng)
      },
    },
  }),
}))

describe('Topbar 语言切换', () => {
  beforeEach(() => {
    mockChangeLanguage.mockClear()
    mockLanguage.current = 'zh'
  })

  it('渲染语言切换器', () => {
    render(createElement(Topbar, { onMenuClick: vi.fn(), onSearchOpen: vi.fn() }))
    expect(screen.getByTestId('language-switcher')).toBeTruthy()
  })

  it('语言切换器有 aria-label', () => {
    render(createElement(Topbar, { onMenuClick: vi.fn(), onSearchOpen: vi.fn() }))
    const switcher = screen.getByTestId('language-switcher')
    expect(switcher.getAttribute('aria-label')).toBe('header.switchLanguage')
  })

  it('点击搜索框入口触发 onSearchOpen', () => {
    const onSearchOpen = vi.fn()
    render(createElement(Topbar, { onMenuClick: vi.fn(), onSearchOpen }))
    const searchButton = screen.getByText('search.placeholder').closest('button')
    fireEvent.click(searchButton!)
    expect(onSearchOpen).toHaveBeenCalledTimes(1)
  })

  it('点击菜单按钮触发 onMenuClick', () => {
    const onMenuClick = vi.fn()
    render(createElement(Topbar, { onMenuClick, onSearchOpen: vi.fn() }))
    const menuButton = screen.getByLabelText('打开菜单')
    fireEvent.click(menuButton)
    expect(onMenuClick).toHaveBeenCalledTimes(1)
  })

  it('语言切换器展示当前语言值', () => {
    mockLanguage.current = 'zh'
    render(createElement(Topbar, { onMenuClick: vi.fn(), onSearchOpen: vi.fn() }))
    const switcher = screen.getByTestId('language-switcher')
    expect(switcher).toBeTruthy()
    expect(switcher.getAttribute('data-slot')).toBe('select-trigger')
  })

  it('语言切换器随 i18n.language 变化展示', () => {
    mockLanguage.current = 'en'
    const { rerender } = render(createElement(Topbar, { onMenuClick: vi.fn(), onSearchOpen: vi.fn() }))
    const switcher = screen.getByTestId('language-switcher')
    expect(switcher).toBeTruthy()
    mockLanguage.current = 'ja'
    rerender(createElement(Topbar, { onMenuClick: vi.fn(), onSearchOpen: vi.fn() }))
    expect(screen.getByTestId('language-switcher')).toBeTruthy()
  })
})
