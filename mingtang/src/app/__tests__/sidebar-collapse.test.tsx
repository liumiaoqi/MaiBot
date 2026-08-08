import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { createElement } from 'react'

import { Sidebar } from '@/app/layout/sidebar'

const { mockNavigate, mockPathname } = vi.hoisted(() => ({
  mockNavigate: vi.fn(),
  mockPathname: vi.fn(() => '/'),
}))

vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => mockNavigate,
  useRouterState: ({ select }: { select: (s: { location: { pathname: string } }) => string }) =>
    select({ location: { pathname: mockPathname() } }),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'zh' },
  }),
}))

describe('Sidebar 收起/展开', () => {
  beforeEach(() => {
    mockNavigate.mockClear()
    localStorage.clear()
  })

  it('默认展开——显示 Logo 和分区标题', () => {
    render(createElement(Sidebar, {}))
    expect(screen.getByText('MaiBot')).toBeTruthy()
    expect(screen.getByText('sidebar.groups.botConfig')).toBeTruthy()
    expect(screen.getByText('sidebar.menu.home')).toBeTruthy()
  })

  it('点击收起按钮——侧边栏收起', () => {
    render(createElement(Sidebar, {}))
    const toggle = screen.getByTestId('sidebar-collapse-toggle')
    fireEvent.click(toggle)
    expect(screen.queryByText('MaiBot')).toBeNull()
    expect(screen.queryByText('sidebar.groups.botConfig')).toBeNull()
    expect(screen.queryByText('sidebar.menu.home')).toBeNull()
  })

  it('再次点击——展开恢复', () => {
    render(createElement(Sidebar, {}))
    const toggle = screen.getByTestId('sidebar-collapse-toggle')
    fireEvent.click(toggle)
    fireEvent.click(toggle)
    expect(screen.getByText('MaiBot')).toBeTruthy()
    expect(screen.getByText('sidebar.menu.home')).toBeTruthy()
  })

  it('收起状态持久化到 localStorage', () => {
    render(createElement(Sidebar, {}))
    const toggle = screen.getByTestId('sidebar-collapse-toggle')
    fireEvent.click(toggle)
    expect(localStorage.getItem('maibot-sidebar-collapsed')).toBe('true')
  })

  it('展开状态持久化到 localStorage', () => {
    localStorage.setItem('maibot-sidebar-collapsed', 'true')
    render(createElement(Sidebar, {}))
    const toggle = screen.getByTestId('sidebar-collapse-toggle')
    fireEvent.click(toggle)
    expect(localStorage.getItem('maibot-sidebar-collapsed')).toBe('false')
  })

  it('从 localStorage 恢复收起状态', () => {
    localStorage.setItem('maibot-sidebar-collapsed', 'true')
    render(createElement(Sidebar, {}))
    expect(screen.queryByText('MaiBot')).toBeNull()
    expect(screen.queryByText('sidebar.groups.botConfig')).toBeNull()
  })

  it('收起时菜单项仍可点击导航', () => {
    render(createElement(Sidebar, {}))
    const toggle = screen.getByTestId('sidebar-collapse-toggle')
    fireEvent.click(toggle)
    const homeButton = screen.getByTestId('sidebar-item-/').closest('button')
    expect(homeButton).toBeTruthy()
    fireEvent.click(homeButton!)
    expect(mockNavigate).toHaveBeenCalledWith({ to: '/' })
  })

  it('收起时 data-collapsed 属性为 true', () => {
    render(createElement(Sidebar, {}))
    const aside = document.querySelector('[data-dashboard-sidebar="true"]')
    expect(aside?.getAttribute('data-collapsed')).toBe('false')
    const toggle = screen.getByTestId('sidebar-collapse-toggle')
    fireEvent.click(toggle)
    expect(aside?.getAttribute('data-collapsed')).toBe('true')
  })

  it('收起按钮 aria-label 随状态切换', () => {
    render(createElement(Sidebar, {}))
    const toggle = screen.getByTestId('sidebar-collapse-toggle')
    expect(toggle.getAttribute('aria-label')).toBe('收起侧边栏')
    fireEvent.click(toggle)
    expect(toggle.getAttribute('aria-label')).toBe('展开侧边栏')
  })

  it('收起时菜单项有 title 属性（悬停提示）', () => {
    render(createElement(Sidebar, {}))
    const toggle = screen.getByTestId('sidebar-collapse-toggle')
    fireEvent.click(toggle)
    const homeButton = screen.getByTestId('sidebar-item-/').closest('button')
    expect(homeButton?.getAttribute('title')).toBe('sidebar.menu.home')
  })
})