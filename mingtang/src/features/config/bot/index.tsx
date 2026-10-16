import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { RefreshCw, Save, Check } from 'lucide-react'
import { PageShell } from '@/components/biz/page-shell'
import { LoadingSkeleton } from '@/components/biz/loading-skeleton'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { resolveLocalizedText } from '@/lib/config-label'
import { CodeEditor } from '../components/code-editor'
import { DynamicConfigForm } from '../components/dynamic-config-form'
import {
  WIRED_DOMAIN_PATHS,
  countAllDomains,
  listWiredDomains,
  prepareDomainForm,
  readDomainValues,
  resolveDomainSchema,
} from '../domains/wired-domains'
import { registerAllConfigHooks } from '../hooks'
import {
  getBotConfig,
  getBotConfigSchema,
  getBotConfigRaw,
  updateBotConfigSection,
  updateBotConfigRaw,
} from '@/lib/config-api'

type ConfigMode = 'core' | 'detail' | 'source'

/** 麦麦主配置页（/config/bot）——三模式 Tabs + 自动保存 + 25 fieldHooks */
export function BotConfigPage() {
  const { t, i18n } = useTranslation()
  const queryClient = useQueryClient()

  const [mode, setMode] = useState<ConfigMode>('core')
  const [savedTick, setSavedTick] = useState(false)
  // 详细模式当前选中的域。默认「基础」（本页就是 bot 主配置；它也是 `uiOrder` 最小那个，
  // 与切换器的第一个按钮一致）。⚠️ 别写成 `WIRED_DOMAIN_PATHS[0]`——那个是 `agent_autonomy`，
  // 跟 `uiOrder` 排序后的首个**不是**同一个，会让"默认选中项"和"第一个按钮"对不上。
  const [activeDomain, setActiveDomain] = useState<string>('bot')

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

  // 服务端数据变化时同步草稿——渲染期调整模式（React 官方——替代 effect 里 setState）
  const [prevRawConfig, setPrevRawConfig] = useState(rawConfig)
  if (rawConfig !== prevRawConfig) {
    setPrevRawConfig(rawConfig)
    if (rawConfig !== undefined) {
      setRawDraft(rawConfig)
      setRawDirty(false)
    }
  }

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

  // ── 详细模式 · 已接入域的字段（(a)-⑤：只接**纯标量域**，清单见 `../domains/wired-domains.ts`）──
  // 服务端数据变化时同步草稿——与 rawDraft 同一套"渲染期调整模式"。
  // 比较的是 `config` 的对象引用：react-query 默认 structural sharing ⇒ 引用稳定，不会自激。
  const [domainDrafts, setDomainDrafts] = useState<Record<string, Record<string, unknown>>>({})
  const [prevConfigSource, setPrevConfigSource] = useState(config)
  if (config !== prevConfigSource) {
    setPrevConfigSource(config)
    if (config) {
      const drafts: Record<string, Record<string, unknown>> = {}
      for (const path of WIRED_DOMAIN_PATHS) {
        drafts[path] = readDomainValues(config, path)
      }
      setDomainDrafts(drafts)
    }
  }

  // 编辑只进页面 state（本批是"约束在 UI 上真拦住"的有界证明）；
  // 落盘走 `scheduleSectionSave(<域>, …)` 那条 2s 防抖路径——**故意没接**：
  // 写路径刚迁到 2 段接缝（`mutateConfig`），本批不顺手改写入语义。
  const handleDomainFieldChange = useCallback(
    (field: string, value: unknown) => {
      setDomainDrafts((prev) => ({
        ...prev,
        [activeDomain]: { ...(prev[activeDomain] ?? {}), [field]: value },
      }))
    },
    [activeDomain],
  )

  const wiredDomains = useMemo(() => (schema ? listWiredDomains(schema) : []), [schema])
  const allDomainCount = useMemo(() => (schema ? countAllDomains(schema) : 0), [schema])
  const activeDomainSchema = useMemo(
    () => (schema ? resolveDomainSchema(schema, activeDomain) : undefined),
    [schema, activeDomain],
  )
  const activeDomainForm = useMemo(
    () => (activeDomainSchema ? prepareDomainForm(activeDomainSchema) : undefined),
    [activeDomainSchema],
  )

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
                  {/* 已接入域的切换器（本批 6 个）——其余域**不渲染**，只如实报出数量 */}
                  <div className="flex flex-wrap items-center gap-2" data-testid="wired-domain-tabs">
                    {wiredDomains.map((domain) => (
                      <button
                        key={domain.path}
                        type="button"
                        onClick={() => setActiveDomain(domain.path)}
                        data-testid={`wired-domain-${domain.path}`}
                        data-active={domain.path === activeDomain}
                        className={cn(
                          'rounded-md px-3 py-1.5 text-sm transition-colors',
                          domain.path === activeDomain
                            ? 'bg-primary text-primary-foreground'
                            : 'hover:bg-muted',
                        )}
                      >
                        {resolveLocalizedText(domain.label, i18n.language)}
                        <span className="ml-1 text-xs opacity-70">{domain.renderableCount}</span>
                      </button>
                    ))}
                    <span className="text-xs text-muted-foreground" data-testid="unwired-domain-count">
                      其余 {Math.max(allDomainCount - wiredDomains.length, 0)} 个域本批未接入
                    </span>
                  </div>

                  {activeDomainForm ? (
                    <div
                      data-testid="wired-domain-form"
                      data-domain-path={activeDomain}
                      className="space-y-2"
                    >
                      <DynamicConfigForm
                        schema={activeDomainForm.schema}
                        values={domainDrafts[activeDomain] ?? {}}
                        onChange={handleDomainFieldChange}
                      />
                      {/* 异形字段**显式不渲染**并如实报出（不静默兜底——那是写坏数据的入口） */}
                      {activeDomainForm.skipped.length > 0 && (
                        <p
                          className="text-xs text-muted-foreground"
                          data-testid="domain-skipped-fields"
                        >
                          未渲染 {activeDomainForm.skipped.length} 个字段（数组/复杂类型，需列表编辑器）：
                          {activeDomainForm.skipped.map((item) => item.name).join('、')}
                        </p>
                      )}
                    </div>
                  ) : (
                    <p className="text-sm text-muted-foreground" data-testid="wired-domain-missing">
                      该域在当前 schema 里不存在
                    </p>
                  )}
                </>
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
