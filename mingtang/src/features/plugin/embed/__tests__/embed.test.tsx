import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { createElement, type ReactNode } from 'react'
import { PluginMarketplaceEmbedPage } from '../marketplace-embed'
import { PluginConfigEmbedPage } from '../config-embed'
import { PluginMirrorsEmbedPage } from '../mirrors-embed'

vi.mock('@/hooks/use-auth', () => ({
  useAuthGuard: () => ({ checking: false }),
}))

vi.mock('@/features/plugin/marketplace', () => ({
  PluginMarketplacePage: ({ embedded }: { embedded?: boolean }) =>
    createElement('div', { 'data-testid': 'marketplace-page', 'data-embedded': String(embedded ?? false) }),
}))

vi.mock('@/features/plugin/config', () => ({
  PluginConfigPage: () => createElement('div', { 'data-testid': 'config-page' }),
}))

vi.mock('@/features/plugin/mirrors', () => ({
  PluginMirrorsPage: ({ embedded }: { embedded?: boolean }) =>
    createElement('div', { 'data-testid': 'mirrors-page', 'data-embedded': String(embedded ?? false) }),
}))

function TestWrapper({ children }: { children: ReactNode }) {
  return children
}

describe('R4-4a §15.5：embed wrapper 页面', () => {
  beforeEach(() => vi.clearAllMocks())

  it('marketplace-embed 渲染 EmbedPageShell + 透传 embedded', () => {
    render(<PluginMarketplaceEmbedPage />, { wrapper: TestWrapper })
    expect(screen.getByTestId('marketplace-page')).toBeInTheDocument()
    expect(screen.getByTestId('marketplace-page')).toHaveAttribute('data-embedded', 'true')
    expect(document.querySelector('[data-dashboard-shell="embed-plugin-marketplace"]')).toBeInTheDocument()
  })

  it('config-embed 渲染 EmbedPageShell', () => {
    render(<PluginConfigEmbedPage />, { wrapper: TestWrapper })
    expect(screen.getByTestId('config-page')).toBeInTheDocument()
    expect(document.querySelector('[data-dashboard-shell="embed-plugin-config"]')).toBeInTheDocument()
  })

  it('mirrors-embed 渲染 EmbedPageShell + 透传 embedded', () => {
    render(<PluginMirrorsEmbedPage />, { wrapper: TestWrapper })
    expect(screen.getByTestId('mirrors-page')).toBeInTheDocument()
    expect(screen.getByTestId('mirrors-page')).toHaveAttribute('data-embedded', 'true')
    expect(document.querySelector('[data-dashboard-shell="embed-plugin-mirrors"]')).toBeInTheDocument()
  })
})