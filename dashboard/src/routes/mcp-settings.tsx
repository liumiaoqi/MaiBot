import { useCallback, useEffect, useState } from 'react'

import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { DynamicConfigForm } from '@/components/dynamic-form'
import { RestartOverlay } from '@/components/restart-overlay'
import { useToast } from '@/hooks/use-toast'
import { getBotConfig, getBotConfigSchema, updateBotConfigSection } from '@/lib/config-api'
import { fieldHooks } from '@/lib/field-hooks'
import { RestartProvider, useRestart } from '@/lib/restart-context'
import type { ConfigSchema } from '@/types/config-schema'
import { Info, Power, Save } from 'lucide-react'

import { MCPRootItemsHook, MCPServersHook } from './config/bot/hooks'

type ConfigSectionData = Record<string, unknown>

function updateNestedValue(
  target: ConfigSectionData | null | undefined,
  pathSegments: string[],
  value: unknown
): ConfigSectionData {
  const currentTarget = target && typeof target === 'object' && !Array.isArray(target) ? target : {}
  const [currentPath, ...restPath] = pathSegments

  if (!currentPath) {
    return currentTarget
  }

  if (restPath.length === 0) {
    return {
      ...currentTarget,
      [currentPath]: value,
    }
  }

  return {
    ...currentTarget,
    [currentPath]: updateNestedValue(currentTarget[currentPath] as ConfigSectionData | undefined, restPath, value),
  }
}

export function MCPSettingsPage() {
  return (
    <RestartProvider>
      <MCPSettingsPageContent />
    </RestartProvider>
  )
}

function MCPSettingsPageContent() {
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false)
  const [mcpConfig, setMcpConfig] = useState<ConfigSectionData>({})
  const [mcpSchema, setMcpSchema] = useState<ConfigSchema | null>(null)
  const { toast } = useToast()
  const { triggerRestart, isRestarting } = useRestart()

  useEffect(() => {
    const hookEntries = [
      ['mcp.client.roots.items', MCPRootItemsHook],
      ['mcp.servers', MCPServersHook],
    ] as const

    for (const [fieldPath, hookComponent] of hookEntries) {
      fieldHooks.register(fieldPath, hookComponent, 'replace')
    }

    return () => {
      for (const [fieldPath] of hookEntries) {
        fieldHooks.unregister(fieldPath)
      }
    }
  }, [])

  const loadConfig = useCallback(async () => {
    try {
      setLoading(true)
      const [configResult, schemaResult] = await Promise.all([getBotConfig(), getBotConfigSchema()])

      if (!configResult.success) {
        toast({
          title: '加载失败',
          description: configResult.error,
          variant: 'destructive',
        })
        return
      }

      if (!schemaResult.success) {
        toast({
          title: '加载失败',
          description: schemaResult.error,
          variant: 'destructive',
        })
        return
      }

      const configPayload = configResult.data as { config?: Record<string, unknown> } & Record<string, unknown>
      const fullConfig = (configPayload.config ?? configPayload) as Record<string, unknown>
      const schemaPayload = schemaResult.data as { schema?: ConfigSchema } & ConfigSchema
      const fullSchema = (schemaPayload.schema ?? schemaPayload) as ConfigSchema

      setMcpConfig((fullConfig.mcp ?? {}) as ConfigSectionData)
      setMcpSchema(fullSchema.nested?.mcp ?? null)
      setHasUnsavedChanges(false)
    } catch (error) {
      console.error('加载 MCP 设置失败:', error)
      toast({
        title: '加载失败',
        description: (error as Error).message,
        variant: 'destructive',
      })
    } finally {
      setLoading(false)
    }
  }, [toast])

  useEffect(() => {
    void loadConfig()
  }, [loadConfig])

  const saveConfig = useCallback(async (): Promise<boolean> => {
    try {
      setSaving(true)
      const result = await updateBotConfigSection('mcp', mcpConfig)

      if (!result.success) {
        toast({
          title: '保存失败',
          description: result.error,
          variant: 'destructive',
        })
        return false
      }

      setHasUnsavedChanges(false)
      toast({
        title: '保存成功',
        description: 'MCP 设置已保存，重启后生效。',
      })
      return true
    } catch (error) {
      console.error('保存 MCP 设置失败:', error)
      toast({
        title: '保存失败',
        description: (error as Error).message,
        variant: 'destructive',
      })
      return false
    } finally {
      setSaving(false)
    }
  }, [mcpConfig, toast])

  const saveAndRestart = useCallback(async () => {
    const saved = await saveConfig()
    if (!saved) {
      return
    }
    await triggerRestart({ delay: 500 })
  }, [saveConfig, triggerRestart])

  const formSchema: ConfigSchema | null = mcpSchema
    ? {
        className: 'MCPSettings',
        classDoc: 'MCP 设置',
        fields: [],
        nested: {
          mcp: mcpSchema,
        },
      }
    : null

  return (
    <ScrollArea className="h-full">
      <div className="space-y-4 sm:space-y-6 p-4 sm:p-6">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0">
            <h1 className="text-xl sm:text-2xl md:text-3xl font-bold">MCP 设置</h1>
            <p className="text-muted-foreground mt-1 text-xs sm:text-sm">
              管理 MCP 客户端能力与服务器连接配置
            </p>
          </div>
          <div className="flex gap-2">
            <Button
              onClick={saveConfig}
              disabled={loading || saving || !hasUnsavedChanges || isRestarting}
              size="sm"
              variant="outline"
              className="w-24"
            >
              <Save className="h-4 w-4" strokeWidth={2} fill="none" />
              <span className="ml-1 text-xs sm:text-sm">{saving ? '保存中' : hasUnsavedChanges ? '保存' : '已保存'}</span>
            </Button>
            <Button
              onClick={saveAndRestart}
              disabled={loading || saving || isRestarting}
              size="sm"
              className="w-28"
            >
              <Power className="h-4 w-4" />
              <span className="ml-1 text-xs sm:text-sm">{isRestarting ? '重启中' : '保存重启'}</span>
            </Button>
          </div>
        </div>

        <Alert>
          <Info className="h-4 w-4" />
          <AlertDescription>
            MCP 设置保存后需要重启麦麦才会生效。这里与主程序配置中的 MCP 栏目使用同一份配置。
          </AlertDescription>
        </Alert>

        {loading && (
          <div className="flex h-64 items-center justify-center text-sm text-muted-foreground">
            加载中...
          </div>
        )}

        {!loading && formSchema && (
          <DynamicConfigForm
            schema={formSchema}
            values={{ mcp: mcpConfig }}
            onChange={(fieldPath, value) => {
              const [, ...restPath] = fieldPath.split('.')
              const nextConfig = restPath.length === 0
                ? (value as ConfigSectionData)
                : updateNestedValue(mcpConfig, restPath, value)

              setMcpConfig(nextConfig)
              setHasUnsavedChanges(true)
            }}
            hooks={fieldHooks}
          />
        )}

        {!loading && !formSchema && (
          <Alert>
            <Info className="h-4 w-4" />
            <AlertDescription>当前配置 schema 中没有找到 MCP 设置。</AlertDescription>
          </Alert>
        )}

        <RestartOverlay />
      </div>
    </ScrollArea>
  )
}
