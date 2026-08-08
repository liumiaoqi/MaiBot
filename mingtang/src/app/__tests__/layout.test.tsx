import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { Layout } from '@/app/layout'

// 模拟 navigate
const mockNavigate = vi.fn()
vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => mockNavigate,
  useRouterState: () => ({ location: { pathname: '/' } }),
}))

// 模拟 i18n
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'zh' },
  }),
}))

// 模拟 SearchDialog（避免触发注册表初始化）
vi.mock('@/app/layout/search-dialog', () => ({
  SearchDialog: ({ open }: { open: boolean }) =>
    open ? <div data-testid="search-dialog">SearchDialog</div> : null,
}))

describe('Layout', () => {
  it('渲染侧边栏和顶栏', () => {
    render(
      <Layout>
        <div>content</div>
      </Layout>
    )
    expect(screen.getByText('MaiBot')).toBeTruthy()
    expect(screen.getByText('search.placeholder')).toBeTruthy()
    expect(screen.getByText('content')).toBeTruthy()
  })

  it('点击搜索框入口打开搜索对话框', () => {
    render(
      <Layout>
        <div>content</div>
      </Layout>
    )
    const searchButton = screen.getByText('search.placeholder').closest('button')
    fireEvent.click(searchButton!)
    expect(screen.getByTestId('search-dialog')).toBeTruthy()
  })

  it('侧边栏渲染菜单分区', () => {
    render(
      <Layout>
        <div>content</div>
      </Layout>
    )
    // 检查分区标题存在（overview 分区是 sr-only）
    expect(screen.getByText('sidebar.groups.botConfig')).toBeTruthy()
    expect(screen.getByText('sidebar.groups.botResources')).toBeTruthy()
    expect(screen.getByText('sidebar.groups.extensionsMonitor')).toBeTruthy()
  })

  it('侧边栏渲染菜单项', () => {
    render(
      <Layout>
        <div>content</div>
      </Layout>
    )
    // 检查菜单项存在
    expect(screen.getByText('sidebar.menu.home')).toBeTruthy()
    expect(screen.getByText('sidebar.menu.botMainConfig')).toBeTruthy()
    expect(screen.getByText('sidebar.menu.modelManagement')).toBeTruthy()
    expect(screen.getByText('sidebar.menu.pluginMarket')).toBeTruthy()
  })

  it('菜单项点击导航', () => {
    render(
      <Layout>
        <div>content</div>
      </Layout>
    )
    const button = screen.getByText('sidebar.menu.home').closest('button')
    fireEvent.click(button!)
    expect(mockNavigate).toHaveBeenCalledWith({ to: '/' })
  })

  it('无 path 的菜单项不渲染', () => {
    render(
      <Layout>
        <div>content</div>
      </Layout>
    )
    // behavior 菜单项无 path，不应渲染为按钮
    expect(screen.queryByText('sidebar.menu.behavior')).toBeNull()
  })

  it('主内容区有 main-content id 和 tabIndex', () => {
    render(
      <Layout>
        <div>content</div>
      </Layout>
    )
    const main = document.getElementById('main-content')
    expect(main).toBeTruthy()
    expect(main?.tabIndex).toBe(-1)
  })
})