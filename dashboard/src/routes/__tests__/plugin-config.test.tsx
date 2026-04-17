import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ReactNode } from 'react'

import { PluginConfigPage } from '../plugin-config'
import * as pluginApi from '@/lib/plugin-api'

const toastMock = vi.fn()

vi.mock('@/hooks/use-toast', () => ({
  useToast: () => ({ toast: toastMock }),
}))

vi.mock('@/lib/restart-context', () => ({
  RestartProvider: ({ children }: { children: ReactNode }) => <>{children}</>,
  useRestart: () => ({
    showRestartPrompt: false,
    markRestartRequired: vi.fn(),
    clearRestartRequired: vi.fn(),
  }),
}))

vi.mock('@/components/restart-overlay', () => ({
  RestartOverlay: () => null,
}))

vi.mock('@/components', () => ({
  CodeEditor: ({ value }: { value: string }) => <pre>{value}</pre>,
  ListFieldEditor: () => <div>list-field-editor</div>,
}))

vi.mock('@/lib/plugin-api', () => ({
  getInstalledPlugins: vi.fn(),
  getPluginConfigSchema: vi.fn(),
  getPluginConfig: vi.fn(),
  getPluginConfigRaw: vi.fn(),
  updatePluginConfig: vi.fn(),
  updatePluginConfigRaw: vi.fn(),
  resetPluginConfig: vi.fn(),
  togglePlugin: vi.fn(),
}))

describe('PluginConfigPage', () => {
  beforeEach(() => {
    toastMock.mockReset()
    vi.mocked(pluginApi.getInstalledPlugins).mockResolvedValue({
      success: true,
      data: [
        {
          id: 'test.emoji',
          path: '/plugins/test_emoji',
          manifest: {
            manifest_version: 2,
            name: 'Emoji Plugin',
            version: '1.0.0',
            description: 'emoji tools',
            author: { name: 'tester' },
            license: 'MIT',
            host_application: { min_version: '1.0.0' },
          },
        },
      ],
    })
    vi.mocked(pluginApi.getPluginConfigSchema).mockResolvedValue({} as never)
    vi.mocked(pluginApi.getPluginConfig).mockResolvedValue({} as never)
    vi.mocked(pluginApi.getPluginConfigRaw).mockResolvedValue({} as never)
    vi.mocked(pluginApi.updatePluginConfig).mockResolvedValue({} as never)
    vi.mocked(pluginApi.updatePluginConfigRaw).mockResolvedValue({} as never)
    vi.mocked(pluginApi.resetPluginConfig).mockResolvedValue({} as never)
    vi.mocked(pluginApi.togglePlugin).mockResolvedValue({} as never)
  })

  it('shows real plugins and no longer surfaces A_Memorix in plugin config list', async () => {
    render(<PluginConfigPage />)

    expect(await screen.findByText('Emoji Plugin')).toBeInTheDocument()
    expect(screen.getByText('点击插件查看和编辑配置')).toBeInTheDocument()
    expect(screen.queryByText(/A_Memorix/i)).not.toBeInTheDocument()
  })
})
