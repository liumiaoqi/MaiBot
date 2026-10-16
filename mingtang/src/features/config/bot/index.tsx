import { useState, useEffect, useCallback, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { RefreshCw } from 'lucide-react'
import { PageShell } from '@/components/biz/page-shell'
import { LoadingSkeleton } from '@/components/biz/loading-skeleton'
import { Button } from '@/components/ui/button'
import { DynamicConfigForm } from '../components/dynamic-config-form'
import { DynamicConfigTabs } from '../components/dynamic-config-tabs'
import { registerAllConfigHooks } from '../hooks'
import {
  getBotConfig,
  getBotConfigSchema,
  updateBotConfigSection,
} from '@/lib/config-api'
import type { ConfigSchema } from '@/types/config-schema'

type ConfigMode = 'core' | 'detail' | 'source'

/** 取某个域的字段值字典——配置数据是 `section → 字段值` 的嵌套对象 */
function sectionFieldValues(section: unknown): Record<string, unknown> {
  if (section && typeof section === 'object' && !Array.isArray(section)) {
    return section as Record<string, unknown>
  }
  return {}
}

/** 麦麦主配置页（/config/bot）——三模式 Tabs + 自动保存 + 25 fieldHooks */
export function BotConfigPage() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()

  const [mode, setMode] = useState<ConfigMode>('core')

  // 注册 fieldHooks（mount 时一次性注册）
  useEffect(() => {
    registerAllConfigHooks()
  }, [])

  // 加载配置 + schema
  const { data: config, isLoading } = useQuery({
    queryKey: ['api', 'botConfig'],
    queryFn: getBotConfig,
  })

  const { data: schema } = useQuery({
    queryKey: ['api', 'botConfigSchema'],
    queryFn: getBotConfigSchema,
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

  // ⚠️ 「源文件」模式的读取/保存已于 5 段**下线**（2026-10-16 lmq 拍板）：
  // 它走的是 `GET|POST /config/bot/raw`，而那个端点**直出整份 TOML 原文**
  // （含 `maim_message.auth_token` / `api_server_allowed_api_keys` 的真值），
  // 是配置面上已知的明文密钥出站路径；端点连同兼容别名 `/api/config/raw` 已从后端移除。
  // ⇒ 本页签保留为**说明性占位**（见下方渲染），不再有任何读写调用。

  const handleRefresh = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ['api', 'botConfig'] })
    queryClient.invalidateQueries({ queryKey: ['api', 'botConfigSchema'] })
  }, [queryClient])

  // ── 详细模式 · bot 域字段（有界接线：**只有 bot 域**渲染字段，其余域待定）──
  // 服务端数据变化时同步草稿——"渲染期调整模式"（React 官方，替代 effect 里 setState）。
  // 比较的是 `config.bot` 的对象引用：react-query 默认 structural sharing ⇒ 引用稳定，不会自激。
  const botSectionSource = config?.['bot']
  const [botDraft, setBotDraft] = useState<Record<string, unknown>>({})
  const [prevBotSectionSource, setPrevBotSectionSource] = useState(botSectionSource)
  if (botSectionSource !== prevBotSectionSource) {
    setPrevBotSectionSource(botSectionSource)
    setBotDraft(sectionFieldValues(botSectionSource))
  }

  // 编辑只进页面 state（本任务是"约束链可达"的有界证明）；
  // 落盘走 `scheduleSectionSave('bot', …)` 那条 2s 防抖路径——**故意没接**：
  // 读/写接缝正在 2 段换形，写路径不该由本任务顺手改。见回执遗留。
  const handleBotFieldChange = useCallback((field: string, value: unknown) => {
    setBotDraft((prev) => ({ ...prev, [field]: value }))
  }, [])

  const botSectionSchema = schema?.nested?.['bot']

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
                    <h3 className="font-semibold text-lg text-foreground">{section.label}</h3>
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
            <div data-testid="bot-detail-mode" className="space-y-4">
              {schema ? (
                <>
                  {/* 节导航（现状保留：只出按钮，不改其它域的渲染） */}
                  <DynamicConfigTabs schema={schema as ConfigSchema} />
                  {botSectionSchema ? (
                    <div data-testid="bot-domain-form">
                      <DynamicConfigForm
                        schema={botSectionSchema}
                        values={botDraft}
                        onChange={handleBotFieldChange}
                      />
                    </div>
                  ) : null}
                </>
              ) : (
                <LoadingSkeleton />
              )}
            </div>
          )}

          {/* 源文件模式 —— 已于 5 段下线，保留**说明性占位**（不留会报错的按钮） */}
          {mode === 'source' && (
            <div className="rounded-lg border border-border p-4 space-y-2" data-testid="bot-source-mode">
              <h3 className="font-semibold text-foreground">「源文件」模式已下线</h3>
              <p className="text-sm text-muted-foreground">
                原「源文件」页签让你在网页里直接编辑整份配置的 TOML 原文，它依赖
                <code className="mx-1">/config/bot/raw</code>
                端点；该端点会把整份文件（含密钥真值）原样发给浏览器，因此已于 5 段移除。
              </p>
              <p className="text-sm text-muted-foreground">
                配置编辑能力没有减少：「核心」与「详细」两个模式照旧；逐字段的改动走新的按路径读写接缝。
                若确实需要手工改 TOML 原文，请直接编辑服务器上的配置文件后重启。
              </p>
            </div>
          )}
        </div>
      )}
    </PageShell>
  )
}
