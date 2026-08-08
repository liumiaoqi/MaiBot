import { useState, useEffect, useCallback, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { RefreshCw, Save, Check } from 'lucide-react'
import { PageShell } from '@/components/biz/page-shell'
import { LoadingSkeleton } from '@/components/biz/loading-skeleton'
import { Button } from '@/components/ui/button'
import { CodeEditor } from '../components/code-editor'
import { DynamicConfigTabs } from '../components/dynamic-config-tabs'
import { registerAllConfigHooks } from '../hooks'
import {
  getBotConfig,
  getBotConfigSchema,
  getBotConfigRaw,
  updateBotConfigSection,
  updateBotConfigRaw,
} from '@/lib/config-api'
import type { ConfigSchema } from '@/types/config-schema'

type ConfigMode = 'core' | 'detail' | 'source'

/** 麦麦主配置页（/config/bot）——三模式 Tabs + 自动保存 + 25 fieldHooks */
export function BotConfigPage() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()

  const [mode, setMode] = useState<ConfigMode>('core')
  const [savedTick, setSavedTick] = useState(false)

  // 注册 fieldHooks（mount 时一次性注册）
  useEffect(() => {
    registerAllConfigHooks()
  }, [])

  // 加载配置 + schema + raw
  const { data: config, isLoading } = useQuery({
    queryKey: ['api', 'botConfig'],
    queryFn: getBotConfig,
  })

  const { data: schema } = useQuery({
    queryKey: ['api', 'botConfigSchema'],
    queryFn: getBotConfigSchema,
  })

  const { data: rawConfig, isLoading: rawLoading } = useQuery({
    queryKey: ['api', 'botConfigRaw'],
    queryFn: getBotConfigRaw,
  })

  // 分节自动保存（2s 防抖）——详细模式各节编辑时触发
  const saveTimers = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map())

  const scheduleSectionSave = useCallback((sectionName: string, sectionData: unknown) => {
    const timers = saveTimers.current
    const existing = timers.get(sectionName)
    if (existing) clearTimeout(existing)
    timers.set(sectionName, setTimeout(async () => {
      await updateBotConfigSection(sectionName, sectionData)
      await queryClient.invalidateQueries({ queryKey: ['api', 'botConfig'] })
      timers.delete(sectionName)
    }, 2000))
  }, [queryClient])

  // 暴露给详细模式子组件使用
  void scheduleSectionSave

  // 源文件保存
  const rawSaveMutation = useMutation({
    mutationFn: (raw: string) => updateBotConfigRaw(raw),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['api', 'botConfigRaw'] })
      queryClient.invalidateQueries({ queryKey: ['api', 'botConfig'] })
      setSavedTick(true)
      setTimeout(() => setSavedTick(false), 2000)
    },
  })

  const [rawDraft, setRawDraft] = useState('')
  const [rawDirty, setRawDirty] = useState(false)

  useEffect(() => {
    if (rawConfig !== undefined) {
      setRawDraft(rawConfig)
      setRawDirty(false)
    }
  }, [rawConfig])

  const handleRawChange = useCallback((value: string) => {
    setRawDraft(value)
    setRawDirty(true)
  }, [])

  const handleRawSave = useCallback(() => {
    rawSaveMutation.mutate(rawDraft)
  }, [rawSaveMutation, rawDraft])

  const handleRefresh = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ['api', 'botConfig'] })
    queryClient.invalidateQueries({ queryKey: ['api', 'botConfigSchema'] })
    queryClient.invalidateQueries({ queryKey: ['api', 'botConfigRaw'] })
  }, [queryClient])

  // 核心模式三卡片
  const coreSections = [
    { key: 'personality', label: '人格', color: 'border-purple-500/40' },
    { key: 'reply_style', label: '表达', color: 'border-blue-500/40' },
    { key: 'behavior_style', label: '行为', color: 'border-amber-500/40' },
  ]

  const modeTabs: { key: ConfigMode; label: string }[] = [
    { key: 'core', label: '核心' },
    { key: 'detail', label: '详细' },
    { key: 'source', label: '源文件' },
  ]

  return (
    <PageShell
      title={t('sidebar.menu.botMainConfig')}
      breadcrumb={[t('sidebar.groups.botConfig')]}
      actions={
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={handleRefresh} data-testid="bot-refresh">
            <RefreshCw className="h-4 w-4 mr-1" />
            刷新
          </Button>
          {mode === 'source' && (
            <Button size="sm" onClick={handleRawSave} disabled={!rawDirty || rawSaveMutation.isPending} data-testid="bot-save-raw">
              {savedTick ? <Check className="h-4 w-4 mr-1" /> : <Save className="h-4 w-4 mr-1" />}
              {savedTick ? '已保存' : '保存'}
            </Button>
          )}
        </div>
      }
    >
      {isLoading ? <LoadingSkeleton /> : (
        <div className="space-y-4">
          {/* 模式 Tabs */}
          <div className="flex items-center gap-1 border-b pb-2" data-testid="bot-mode-tabs">
            {modeTabs.map((tab) => (
              <button
                key={tab.key}
                onClick={() => setMode(tab.key)}
                data-testid={`bot-mode-${tab.key}`}
                className={`px-3 py-1.5 text-sm rounded-t ${
                  mode === tab.key
                    ? 'bg-background border border-border border-b-0 font-medium'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* 核心模式 */}
          {mode === 'core' && (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4" data-testid="bot-core-mode">
              {coreSections.map((section) => {
                const sectionData = (config as Record<string, unknown>)?.[section.key]
                return (
                  <div
                    key={section.key}
                    className={`rounded-lg border ${section.color} p-4 space-y-2`}
                    data-testid={`bot-core-${section.key}`}
                  >
                    <h3 className="font-semibold text-lg">{section.label}</h3>
                    <p className="text-sm text-muted-foreground">
                      {sectionData ? `${Object.keys(sectionData as object).length} 项配置` : '未配置'}
                    </p>
                  </div>
                )
              })}
            </div>
          )}

          {/* 详细模式 */}
          {mode === 'detail' && (
            <div data-testid="bot-detail-mode">
              {schema ? (
                <DynamicConfigTabs schema={schema as ConfigSchema} />
              ) : (
                <LoadingSkeleton />
              )}
            </div>
          )}

          {/* 源文件模式 */}
          {mode === 'source' && (
            <div data-testid="bot-source-mode">
              {rawLoading ? <LoadingSkeleton /> : (
                <CodeEditor
                  value={rawDraft}
                  onChange={handleRawChange}
                  language="toml"
                  height="600px"
                  placeholder="# 麦麦配置 TOML"
                />
              )}
            </div>
          )}
        </div>
      )}
    </PageShell>
  )
}
