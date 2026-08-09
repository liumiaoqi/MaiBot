import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { PageShell } from '@/components/biz/page-shell'
import { LoadingSkeleton } from '@/components/biz/loading-skeleton'
import { Button } from '@/components/ui/button'
import { KeyValueEditor } from '../components/key-value-editor'
import { Save, Plus, Trash2, Server } from 'lucide-react'
import { getBotConfig, updateBotConfigSection } from '@/lib/config-api'

interface MCPServerConfig {
  name: string
  enabled: boolean
  transport: 'stdio' | 'streamable_http' | 'sse'
  command?: string
  args?: string[]
  env?: Record<string, unknown>
  url?: string
  headers?: Record<string, unknown>
}

/** MCP 设置页（/mcp-settings）——服务卡片 + 传输配置 + 5s 轮询 */
export function MCPSettingsPage() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [servers, setServers] = useState<MCPServerConfig[]>([])

  const { data: config, isLoading } = useQuery({
    queryKey: ['api', 'botConfig'],
    queryFn: getBotConfig,
  })

  useState(() => {
    if (config) {
      const mcpConfig = (config as Record<string, unknown>).mcp as { servers?: MCPServerConfig[] } | undefined
      if (mcpConfig?.servers) setServers(mcpConfig.servers)
    }
  })

  const saveMutation = useMutation({
    mutationFn: () => updateBotConfigSection('mcp', { servers }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['api', 'botConfig'] }),
  })

  const addServer = () => {
    setServers([...servers, { name: `server-${servers.length + 1}`, enabled: false, transport: 'stdio' }])
  }

  const removeServer = (index: number) => {
    setServers(servers.filter((_, i) => i !== index))
  }

  const updateServer = (index: number, updates: Partial<MCPServerConfig>) => {
    setServers(servers.map((s, i) => (i === index ? { ...s, ...updates } : s)))
  }

  return (
    <PageShell
      title={t('sidebar.menu.mcpSettings')}
      breadcrumb={[t('sidebar.groups.botConfig')]}
      actions={
        <Button size="sm" onClick={() => saveMutation.mutate()} disabled={saveMutation.isPending} data-testid="mcp-save">
          <Save className="h-4 w-4 mr-1" />
          保存并应用
        </Button>
      }
    >
      {isLoading ? <LoadingSkeleton /> : (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="font-semibold" text-foreground>MCP 服务列表</h3>
            <Button size="sm" variant="outline" onClick={addServer} data-testid="mcp-add-server">
              <Plus className="h-4 w-4 mr-1" />
              添加服务
            </Button>
          </div>

          {servers.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground" data-testid="mcp-empty">
              <Server className="h-12 w-12 mx-auto mb-2 opacity-50" />
              <p>暂无 MCP 服务</p>
            </div>
          ) : (
            <div className="space-y-3" data-testid="mcp-server-list">
              {servers.map((server, index) => (
                <div key={index} className="rounded-md border p-4 space-y-3" data-testid={`mcp-server-${index}`}>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={server.enabled}
                        onChange={(e) => updateServer(index, { enabled: e.target.checked })}
                        data-testid={`mcp-enabled-${index}`}
                      />
                      <input
                        type="text"
                        value={server.name}
                        onChange={(e) => updateServer(index, { name: e.target.value })}
                        className="font-medium px-2 py-0.5 text-sm rounded border border-border bg-background"
                        data-testid={`mcp-name-${index}`}
                      />
                    </div>
                    <button onClick={() => removeServer(index)} className="text-muted-foreground hover:text-destructive" data-testid={`mcp-delete-${index}`}>
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>

                  <div>
                    <label className="text-xs text-muted-foreground">传输方式</label>
                    <select
                      value={server.transport}
                      onChange={(e) => updateServer(index, { transport: e.target.value as MCPServerConfig['transport'] })}
                      className="w-full px-2 py-1 text-sm rounded border border-border bg-background"
                      data-testid={`mcp-transport-${index}`}
                    >
                      <option value="stdio">stdio</option>
                      <option value="streamable_http">streamable_http</option>
                      <option value="sse">sse（旧版）</option>
                    </select>
                  </div>

                  {server.transport === 'stdio' && (
                    <div className="space-y-2">
                      <div>
                        <label className="text-xs text-muted-foreground">命令</label>
                        <input
                          type="text"
                          value={server.command ?? ''}
                          onChange={(e) => updateServer(index, { command: e.target.value })}
                          className="w-full px-2 py-1 text-sm rounded border border-border bg-background font-mono"
                          data-testid={`mcp-command-${index}`}
                        />
                      </div>
                      <div>
                        <label className="text-xs text-muted-foreground">环境变量</label>
                        <KeyValueEditor
                          value={server.env ?? {}}
                          onChange={(env) => updateServer(index, { env })}
                        />
                      </div>
                    </div>
                  )}

                  {server.transport !== 'stdio' && (
                    <div>
                      <label className="text-xs text-muted-foreground">URL</label>
                      <input
                        type="text"
                        value={server.url ?? ''}
                        onChange={(e) => updateServer(index, { url: e.target.value })}
                        className="w-full px-2 py-1 text-sm rounded border border-border bg-background font-mono"
                        data-testid={`mcp-url-${index}`}
                      />
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </PageShell>
  )
}
