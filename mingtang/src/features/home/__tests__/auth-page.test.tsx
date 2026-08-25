/**
 * AuthPage 认证页测试
 *
 * 核心验证（13 用例）：
 * 1. 无 Layout DOM
 * 2. checkingAuth 态显示加载提示
 * 3. 已认证态自动 navigate('/')
 * 4. 未认证态渲染输入框 + 提交按钮
 * 5. 空提交显示 tokenRequired 不发请求
 * 6. 非空提交调用 authApi.post verify
 * 7. 验证成功 navigate('/')
 * 8. 验证失败显示 message + 保留输入
 * 9. 网络错误显示 connFailed
 * 10. 提交中按钮禁用 + verifyingLabel
 * 11. 主题切换按钮点击调用 setTheme
 * 12. future-retro 主题渲染齿轮 SVG
 * 13. URL 含 ?token=xxx 自动登录 + history.replaceState 剥离
 */
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

const { mockCheckAuth } = vi.hoisted(() => ({
  mockCheckAuth: vi.fn(),
}))
vi.mock('@/lib/auth', () => ({
  checkAuthStatus: mockCheckAuth,
}))

const { mockAuthApiPost } = vi.hoisted(() => ({
  mockAuthApiPost: vi.fn(),
}))
vi.mock('@/lib/http', () => ({
  authApi: { post: mockAuthApiPost },
}))

const { mockSetTheme } = vi.hoisted(() => ({
  mockSetTheme: vi.fn(),
}))

vi.mock('@/lib/theme-context', async () => {
  const { createContext } = await import('react')
  return {
    ThemeProviderContext: createContext({}),
  }
})

const { mockNavigate } = vi.hoisted(() => ({
  mockNavigate: vi.fn(),
}))
vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => mockNavigate,
}))

vi.mock('@/lib/version', () => ({
  APP_FULL_NAME: 'MaiBot test',
}))

import { AuthPage } from '../auth-page'
import { ThemeProviderContext } from '@/lib/theme-context'

/** 用 ThemeProviderContext.Provider 包裹渲染，可覆盖主题值 */
function renderAuthPage(themeOverrides: Record<string, unknown> = {}) {
  const value = {
    resolvedTheme: 'dark' as const,
    setTheme: mockSetTheme,
    dashboardStyle: 'modern' as const,
    ...themeOverrides,
  }
  return render(
    <ThemeProviderContext.Provider value={value as never}>
      <AuthPage />
    </ThemeProviderContext.Provider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  mockCheckAuth.mockResolvedValue(false)
  mockAuthApiPost.mockResolvedValue({ valid: true })
})

afterEach(() => {
  // 重置 URL
  window.history.replaceState({}, '', '/')
})

describe('AuthPage', () => {
  it('1. 无 Layout DOM', async () => {
    const { container } = renderAuthPage()
    await waitFor(() => expect(mockCheckAuth).toHaveBeenCalled())
    expect(container.querySelector('[data-dashboard-shell]')).toBeNull()
    expect(container.querySelector('[data-auth-page="true"]')).not.toBeNull()
  })

  it('2. checkingAuth 态显示加载提示', () => {
    // checkAuthStatus 返回永不 resolve 的 Promise，保持 checkingAuth 态
    mockCheckAuth.mockReturnValue(new Promise(() => {}))
    renderAuthPage()
    expect(screen.getByText('auth.checkingAuth')).toBeInTheDocument()
  })

  it('3. 已认证态自动 navigate("/")', async () => {
    mockCheckAuth.mockResolvedValue(true)
    renderAuthPage()
    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith({ to: '/' }))
  })

  it('4. 未认证态渲染输入框 + 提交按钮', async () => {
    renderAuthPage()
    await waitFor(() => expect(screen.getByPlaceholderText('auth.tokenPlaceholder')).toBeInTheDocument())
    expect(screen.getByText('auth.verifyEnter')).toBeInTheDocument()
  })

  it('5. 空提交显示 tokenRequired 不发请求', async () => {
    renderAuthPage()
    await waitFor(() => expect(screen.getByPlaceholderText('auth.tokenPlaceholder')).toBeInTheDocument())
    fireEvent.click(screen.getByText('auth.verifyEnter'))
    await waitFor(() => expect(screen.getByText('auth.tokenRequired')).toBeInTheDocument())
    expect(mockAuthApiPost).not.toHaveBeenCalled()
  })

  it('6. 非空提交调用 authApi.post verify', async () => {
    renderAuthPage()
    const input = await screen.findByPlaceholderText('auth.tokenPlaceholder')
    fireEvent.change(input, { target: { value: 'test-token' } })
    fireEvent.click(screen.getByText('auth.verifyEnter'))
    await waitFor(() =>
      expect(mockAuthApiPost).toHaveBeenCalledWith(
        '/api/webui/auth/verify',
        expect.objectContaining({ body: { token: 'test-token' } }),
      ),
    )
  })

  it('7. 验证成功 navigate("/")', async () => {
    mockAuthApiPost.mockResolvedValue({ valid: true })
    renderAuthPage()
    const input = await screen.findByPlaceholderText('auth.tokenPlaceholder')
    fireEvent.change(input, { target: { value: 'test-token' } })
    fireEvent.click(screen.getByText('auth.verifyEnter'))
    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith({ to: '/' }))
  })

  it('8. 验证失败显示 message + 保留输入', async () => {
    mockAuthApiPost.mockResolvedValue({ valid: false, message: 'Token 错误' })
    renderAuthPage()
    const input = await screen.findByPlaceholderText('auth.tokenPlaceholder')
    fireEvent.change(input, { target: { value: 'test-token' } })
    fireEvent.click(screen.getByText('auth.verifyEnter'))
    await waitFor(() => expect(screen.getByText('Token 错误')).toBeInTheDocument())
    expect(input).toHaveValue('test-token')
  })

  it('9. 网络错误显示 connFailed', async () => {
    mockAuthApiPost.mockRejectedValue(new Error('Network error'))
    renderAuthPage()
    const input = await screen.findByPlaceholderText('auth.tokenPlaceholder')
    fireEvent.change(input, { target: { value: 'test-token' } })
    fireEvent.click(screen.getByText('auth.verifyEnter'))
    await waitFor(() => expect(screen.getByText('Network error')).toBeInTheDocument())
  })

  it('10. 提交中按钮禁用 + verifyingLabel', async () => {
    // authApi.post 返回永不 resolve 的 Promise，保持 validating 态
    mockAuthApiPost.mockReturnValue(new Promise(() => {}))
    renderAuthPage()
    const input = await screen.findByPlaceholderText('auth.tokenPlaceholder')
    fireEvent.change(input, { target: { value: 'test-token' } })
    fireEvent.click(screen.getByText('auth.verifyEnter'))
    await waitFor(() => expect(screen.getByText('auth.verifyingLabel')).toBeInTheDocument())
    expect(screen.getByRole('button', { name: /auth.verifyingLabel/ })).toBeDisabled()
  })

  it('11. 主题切换按钮点击调用 setTheme', async () => {
    renderAuthPage()
    await waitFor(() => expect(screen.getByPlaceholderText('auth.tokenPlaceholder')).toBeInTheDocument())
    const toggle = screen.getByTitle('auth.switchToLight')
    fireEvent.click(toggle)
    expect(mockSetTheme).toHaveBeenCalledWith('light')
  })

  it('12. future-retro 主题渲染齿轮 SVG', async () => {
    renderAuthPage({ dashboardStyle: 'future-retro' })
    await waitFor(() => expect(screen.getByPlaceholderText('auth.tokenPlaceholder')).toBeInTheDocument())
    const gears = document.querySelector('.auth-retro-gears')
    expect(gears).not.toBeNull()
    expect(gears?.getAttribute('aria-hidden')).toBe('true')
  })

  it('13. URL 含 ?token=xxx 自动登录 + history.replaceState 剥离', async () => {
    // 设置 URL 带 token
    window.history.pushState({}, '', '/auth?token=url-test-token')
    const replaceStateSpy = vi.spyOn(window.history, 'replaceState')

    renderAuthPage()
    // 自动登录应触发 authApi.post
    await waitFor(() =>
      expect(mockAuthApiPost).toHaveBeenCalledWith(
        '/api/webui/auth/verify',
        expect.objectContaining({ body: { token: 'url-test-token' } }),
      ),
    )
    // replaceState 应被调用来剥离 URL 中的 token
    expect(replaceStateSpy).toHaveBeenCalled()
    // URL 中不应再包含 token
    expect(window.location.search).not.toContain('token')
  })
})