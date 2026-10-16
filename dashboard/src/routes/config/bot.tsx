import { Fragment, type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from '@tanstack/react-router'
import {
  Check,
  ChevronDown,
  Code2,
  ExternalLink,
  Layout,
  RefreshCw,
  Save,
} from 'lucide-react'

import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ThinkingIllustration } from '@/components/ui/thinking-illustration'
import { ConfigSectionNav } from '@/components/dynamic-form/ConfigSectionNav'
import type { ConfigSection } from '@/components/dynamic-form/ConfigSectionNav'
import { DynamicConfigForm } from '@/components/dynamic-form'
import { RestartOverlay } from '@/components/restart-overlay'
import { useToast } from '@/hooks/use-toast'
import {
  getBotConfig,
  getBotConfigCached,
  getBotConfigSchema,
  updateBotConfig,
} from '@/lib/config-api'
import { fieldHooks } from '@/lib/field-hooks'
import { RestartProvider, useRestart } from '@/lib/restart-context'
import { useUnsavedChangesGuard } from '@/hooks/useUnsavedChangesGuard'
import { cn } from '@/lib/utils'

import type { ConfigSchema } from '@/types/config-schema'
import {
  AliasNamesHook,
  AMemorixSharedMemoryGroupsHook,
  AMemorixRetrievalChatsHook,
  AMemorixRetrievalFilterGroupHook,
  BehaviorFocusGroupsHook,
  BotPlatformAccountsHook,
  ChatPromptsHook,
  ChatTalkValueRulesHook,
  ExpressionGroupsHook,
  ExpressionLearningListHook,
  FocusWhitelistHook,
  JargonGroupsHook,
  JargonLearningListHook,
  KeywordRulesHook,
  HiddenFieldHook,
  MCPRootItemsHook,
  MCPServersHook,
  MultipleReplyStyleHook,
  RegexRulesHook,
  useAutoSave,
} from './bot/hooks'

type ConfigSectionData = Record<string, unknown>
// ==================== 常量定义 ====================
/** Toast 显示前的延迟时间 (毫秒) */
const TOAST_DISPLAY_DELAY = 500

// ==================== Tab 分组类型与构建 ====================
interface TabGroup {
  id: string
  label: string
  advanced: boolean
  order: number
  sections: string[]
}

interface SubtabPane {
  advanced: boolean
  content: ReactNode
  id: string
  label: string
}

/**
 * 从 schema 的 nested 字段解析出 tab 分组信息。
 * - 有 uiLabel 且无 uiParent → 独立 tab
 * - 有 uiParent → 递归找到最终 host，并归入对应 tab
 */
function buildTabGroupsFromSchema(schema: ConfigSchema): TabGroup[] {
  const nested = schema.nested || {}
  const nestedEntries = Object.entries(nested)
  const hosts = new Map<string, TabGroup>()

  const resolveHostId = (fieldName: string, visited: Set<string> = new Set()): string | null => {
    if (visited.has(fieldName)) {
      return null
    }

    const fieldSchema = nested[fieldName]
    if (!fieldSchema) {
      return null
    }

    if (!fieldSchema.uiParent) {
      return fieldSchema.uiLabel ? fieldName : null
    }

    visited.add(fieldName)
    return resolveHostId(fieldSchema.uiParent, visited)
  }

  for (const [fieldName, fieldSchema] of nestedEntries) {
    if (fieldSchema.uiLabel && !fieldSchema.uiParent) {
      hosts.set(fieldName, {
        id: fieldName,
        label: fieldSchema.uiLabel,
        advanced: Boolean(fieldSchema.uiAdvanced),
        order: fieldSchema.uiOrder ?? Number.POSITIVE_INFINITY,
        sections: [fieldName],
      })
    }
  }

  for (const [fieldName] of nestedEntries) {
    const hostId = resolveHostId(fieldName)
    if (!hostId || hostId === fieldName) {
      continue
    }

    const parent = hosts.get(hostId)
    if (parent && !parent.sections.includes(fieldName)) {
      parent.sections.push(fieldName)
    }
  }

  return Array.from(hosts.values()).sort((a, b) => {
    const orderDelta = a.order - b.order
    if (orderDelta !== 0) {
      return orderDelta
    }
    return a.label.localeCompare(b.label, 'zh-CN')
  })
}

// 主导出组件：包装 RestartProvider
export function BotConfigPage() {
  return (
    <RestartProvider>
      <BotConfigPageContent />
    </RestartProvider>
  )
}

// 内部实现组件
function BotConfigPageContent() {
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [autoSaving, setAutoSaving] = useState(false)
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false)
  const [editMode, setEditMode] = useState<'visual' | 'source'>('visual')
  const { toast } = useToast()
  const { triggerRestart, isRestarting } = useRestart()

  const [sectionValues, setSectionValues] = useState<Record<string, ConfigSectionData | null>>({})

  // 脏状态路由守卫
  useUnsavedChangesGuard({
    isDirty: hasUnsavedChanges,
    onDiscard: () => setHasUnsavedChanges(false),
  })

  // Schema 状态（用于动态 tab 分组）
  const [configSchema, setConfigSchema] = useState<ConfigSchema | null>(null)

  // 用于标记初始加载和配置缓存
  const initialLoadRef = useRef(true)
  const configRef = useRef<Record<string, unknown>>({})

  // ==================== 辅助函数 ====================

  /**
   * 解析并设置所有配置状态
   * 抽取自 loadConfig 和 handleModeChange 中的重复逻辑
   */
  const parseAndSetConfig = useCallback((config: Record<string, unknown>) => {
    const { memory: _legacyMemory, ...configWithoutLegacyMemory } = config
    configRef.current = configWithoutLegacyMemory

    setSectionValues(
      Object.fromEntries(
        Object.entries(configWithoutLegacyMemory).map(([sectionName, sectionValue]) => [
          sectionName,
          (sectionValue ?? {}) as ConfigSectionData,
        ])
      )
    )
  }, [])

  /**
   * 构建完整的配置对象用于保存
   */
  const buildFullConfig = useCallback(() => {
    const cleanSectionValues = Object.fromEntries(
      Object.entries(sectionValues).filter(([, value]) => value !== null)
    )

    return {
      ...configRef.current,
      ...cleanSectionValues,
    }
  }, [sectionValues])

  // 加载配置
  const loadConfig = useCallback(async () => {
    try {
      setLoading(true)
      // 用 allSettled：主配置为必需，schema 为可选，二者失败互不影响
      const [result, schemaResult] = await Promise.allSettled([
        getBotConfigCached(),
        getBotConfigSchema(),
      ])
      if (result.status !== 'fulfilled') {
        toast({
          title: '加载失败',
          description: result.reason instanceof Error ? result.reason.message : '加载配置失败',
          variant: 'destructive',
        })
        setLoading(false)
        return
      }
      parseAndSetConfig(result.value)
      if (schemaResult.status === 'fulfilled' && schemaResult.value) {
        setConfigSchema(
          (schemaResult.value as unknown as Record<string, unknown>).schema as ConfigSchema
        )
      }
      setHasUnsavedChanges(false)
      initialLoadRef.current = false
    } catch (error) {
      console.error('加载配置失败:', error)
      toast({
        title: '加载失败',
        description: '无法加载配置文件',
        variant: 'destructive',
      })
    } finally {
      setLoading(false)
    }
  }, [toast, parseAndSetConfig])

  useEffect(() => {
    loadConfig()
  }, [loadConfig])

  useEffect(() => {
    const hookEntries = [
      ['bot.platform', BotPlatformAccountsHook, 'replace'],
      ['bot.alias_names', AliasNamesHook],
      ['bot.qq_account', HiddenFieldHook, 'hidden'],
      ['bot.platforms', HiddenFieldHook, 'hidden'],
      ['personality.multiple_reply_style', MultipleReplyStyleHook],
      ['chat.reply_style.chat_prompts', ChatPromptsHook],
      ['chat.reply_timing.talk_value_rules', ChatTalkValueRulesHook],
      ['experimental.focus_chat_whitelist', FocusWhitelistHook],
      ['experimental.focus_groups', BehaviorFocusGroupsHook],
      ['expression.expression_groups', ExpressionGroupsHook],
      ['expression.learning_list', ExpressionLearningListHook],
      ['jargon.jargon_groups', JargonGroupsHook],
      ['jargon.learning_list', JargonLearningListHook],
      ['a_memorix.global_memory_sharing_enabled', HiddenFieldHook, 'hidden'],
      ['a_memorix.shared_memory_groups', AMemorixSharedMemoryGroupsHook],
      ['a_memorix.filter.chats', AMemorixRetrievalChatsHook],
      ['a_memorix.filter.retrieval', AMemorixRetrievalFilterGroupHook, 'wrapper'],
      ['a_memorix.filter.retrieval.chat_stream.chats', AMemorixRetrievalChatsHook],
      ['a_memorix.filter.retrieval.chat_summary.chats', AMemorixRetrievalChatsHook],
      ['a_memorix.filter.retrieval.episode.chats', AMemorixRetrievalChatsHook],
      ['keyword_reaction.keyword_rules', KeywordRulesHook],
      ['keyword_reaction.regex_rules', RegexRulesHook],
      ['mcp.client.roots.items', MCPRootItemsHook],
      ['mcp.servers', MCPServersHook],
    ] as const

    for (const [fieldPath, hookComponent, hookType = 'replace'] of hookEntries) {
      fieldHooks.register(fieldPath, hookComponent, hookType)
    }

    return () => {
      for (const [fieldPath] of hookEntries) {
        fieldHooks.unregister(fieldPath)
      }
    }
  })

  const { triggerAutoSave, cancelPendingAutoSave } = useAutoSave(
    initialLoadRef.current,
    setAutoSaving,
    setHasUnsavedChanges
  )

  // 处理模式切换
  const handleModeChange = async (mode: 'visual' | 'source') => {
    if (hasUnsavedChanges) {
      toast({
        variant: 'destructive',
        title: '切换失败',
        description: '请先保存当前更改',
      })
      return
    }

    setEditMode(mode)
    // ⚠️ 「文件」模式已于 5 段**下线**（见下方说明占位）⇒ 不再有"要加载的原文"这一步。
    // 保留"切回可视化时重新拉取配置"的既有行为；切到「文件」只切视图、不发请求。
    if (mode === 'visual') {
      // 切换回可视化时,直接重新加载配置但不显示全局 loading
      try {
        const result = await getBotConfig()
        parseAndSetConfig(result)
        setHasUnsavedChanges(false)
      } catch (error) {
        console.error('加载配置失败:', error)
        toast({
          title: '加载失败',
          description: '无法加载配置文件',
          variant: 'destructive',
        })
      }
    }
  }

  // 手动保存
  const saveConfig = async () => {
    try {
      setSaving(true)
      cancelPendingAutoSave()

      const result = await updateBotConfig(buildFullConfig())
      setHasUnsavedChanges(false)
      if (result.needs_restart) {
        toast({
          title: '保存成功',
          description: '部分配置需要重启生效，可点击重启按钮应用更改',
        })
      } else {
        toast({
          title: '保存成功',
          description: '麦麦设置已保存',
        })
      }
    } catch (error) {
      console.error('保存配置失败:', error)
      toast({
        title: '保存失败',
        description: (error as Error).message,
        variant: 'destructive',
      })
    } finally {
      setSaving(false)
    }
  }

  const handleReloadFromFile = async () => {
    cancelPendingAutoSave()
    await loadConfig()
    setHasUnsavedChanges(false)
    toast({
      title: '已刷新',
      description: '已从 bot_config.toml 重新读取配置',
    })
  }

  // 重启麦麦
  const handleRestart = async () => {
    await triggerRestart()
  }

  // 保存并重启
  const handleSaveAndRestart = async () => {
    try {
      setSaving(true)
      // 取消待处理的自动保存
      cancelPendingAutoSave()

      await updateBotConfig(buildFullConfig())
      setHasUnsavedChanges(false)
      toast({
        title: '保存成功',
        description: '配置已保存，即将重启麦麦...',
      })
      // 等待一下让用户看到保存成功的提示
      await new Promise((resolve) => setTimeout(resolve, TOAST_DISPLAY_DELAY))
      await handleRestart()
    } catch (error) {
      console.error('保存失败:', error)
      toast({
        title: '保存失败',
        description: (error as Error).message,
        variant: 'destructive',
      })
    } finally {
      setSaving(false)
    }
  }
  // 保留给后续恢复重启入口或快捷操作复用；当前页面不渲染重启按钮。
  void handleSaveAndRestart

  // 根据 schema 构建 tab 分组
  const tabGroups = useMemo(() => {
    if (!configSchema) return []
    return buildTabGroupsFromSchema(configSchema)
  }, [configSchema])

  const setSectionValue = useCallback((sectionName: string, value: ConfigSectionData) => {
    setSectionValues((current) => ({
      ...current,
      [sectionName]: value,
    }))
    triggerAutoSave(sectionName, value)
  }, [triggerAutoSave])

  if (loading) {
    return (
      <ScrollArea className="h-full">
        <div className="space-y-4 p-4 sm:space-y-6 sm:p-6">
          <div className="flex h-64 items-center justify-center">
            <ThinkingIllustration size="lg" />
          </div>
        </div>
      </ScrollArea>
    )
  }

  return (
    <ScrollArea className="h-full min-w-0" scrollbars="vertical">
      <div className="max-w-full space-y-4 overflow-x-hidden p-4 sm:space-y-6 sm:p-6">
        {/* 页面标题 */}
        <div className="flex flex-col gap-3 sm:gap-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0">
              <h1 className="text-xl font-bold sm:text-2xl md:text-3xl">麦麦设置</h1>
            </div>
            {/* 按钮组 - 桌面端靠右 */}
            <div className="flex w-full min-w-0 flex-wrap gap-2 sm:w-auto sm:flex-shrink-0 sm:justify-end">
              <Tabs
                value={editMode}
                onValueChange={(v) => handleModeChange(v as 'visual' | 'source')}
                className="w-full min-w-0 sm:w-[14rem]"
              >
                <TabsList data-config-bot-mode-tabs="true" className="grid h-9 w-full grid-cols-2">
                  <TabsTrigger value="visual" className="px-2 text-sm">
                    <Layout className="mr-1 h-4 w-4" />
                    可视化
                  </TabsTrigger>
                  <TabsTrigger value="source" className="px-2 text-sm">
                    <Code2 className="mr-1 h-4 w-4" />
                    文件
                  </TabsTrigger>
                </TabsList>
              </Tabs>
              <Button
                onClick={handleReloadFromFile}
                disabled={saving || autoSaving || isRestarting}
                size="sm"
                variant="outline"
                className="h-9 w-9 flex-none px-0"
                aria-label="刷新"
                title="刷新"
              >
                <RefreshCw className="h-4 w-4" />
              </Button>
              <Button
                onClick={saveConfig}
                disabled={saving || autoSaving || !hasUnsavedChanges || isRestarting}
                size="sm"
                variant="outline"
                className="h-9 w-9 flex-none px-0"
                aria-label={
                  saving
                    ? '保存中'
                    : autoSaving
                      ? '自动保存中'
                      : hasUnsavedChanges
                        ? '保存'
                        : '已保存'
                }
                title={
                  saving
                    ? '保存中'
                    : autoSaving
                      ? '自动保存中'
                      : hasUnsavedChanges
                        ? '保存'
                        : '已保存'
                }
              >
                <span className="relative inline-flex h-4 w-4 items-center justify-center">
                  <Save className="h-4 w-4" strokeWidth={2} fill="none" />
                  {!saving && !autoSaving && !hasUnsavedChanges && (
                    <Check
                      className="pointer-events-none absolute -right-2 -bottom-2 !h-3 !w-3"
                      strokeWidth={3.4}
                    />
                  )}
                </span>
              </Button>
            </div>
          </div>
        </div>

        {/* 「文件」模式 —— 已于 5 段下线，保留**说明性占位**（不留会报错的按钮） */}
        {editMode === 'source' && (
          <div className="space-y-3 rounded-lg border p-4" data-testid="bot-file-mode-retired">
            <h2 className="text-base font-semibold">「文件」模式已下线</h2>
            <p className="text-muted-foreground text-sm">
              原先这个页签让你在网页里直接编辑整份配置的 TOML 原文，它依赖
              <code className="mx-1">/config/bot/raw</code>
              端点；该端点会把整份文件（含密钥真值）原样发给浏览器，是配置面上已知的明文密钥出站路径，因此已于 5 段移除。
            </p>
            <p className="text-muted-foreground text-sm">
              配置编辑能力没有减少：「可视化」模式照旧；逐字段的改动走新的按路径读写接缝。
              若确实需要手工改 TOML 原文，请直接编辑服务器上的配置文件后重启。
            </p>
          </div>
        )}

        {/* 可视化模式 */}
        {editMode === 'visual' && (
          <DynamicConfigTabs
            configSchema={configSchema}
            tabGroups={tabGroups}
            sectionValues={sectionValues}
            setSectionValue={setSectionValue}
            setHasUnsavedChanges={setHasUnsavedChanges}
            hasUnsavedChanges={hasUnsavedChanges}
          />
        )}

        {/* 重启遮罩层 */}
        <RestartOverlay />
      </div>
    </ScrollArea>
  )
}

// ==================== 动态 Tab 渲染组件 ====================

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
    [currentPath]: updateNestedValue(
      currentTarget[currentPath] as ConfigSectionData | undefined,
      restPath,
      value
    ),
  }
}

interface DynamicConfigTabsProps {
  configSchema: ConfigSchema | null
  tabGroups: TabGroup[]
  sectionValues: Record<string, ConfigSectionData | null>
  setSectionValue: (sectionName: string, value: ConfigSectionData) => void
  setHasUnsavedChanges: (v: boolean) => void
  hasUnsavedChanges: boolean
}

function DynamicConfigTabs(props: DynamicConfigTabsProps) {
  const { configSchema, sectionValues, setHasUnsavedChanges, setSectionValue, tabGroups, hasUnsavedChanges } = props
  const [activeTab, setActiveTab] = useState(tabGroups[0]?.id ?? '')
  const [expandedSubtabGroups, setExpandedSubtabGroups] = useState<Record<string, boolean>>({})
  const [activeSubtabByGroup, setActiveSubtabByGroup] = useState<Record<string, string>>({})
  const [advancedVisible, setAdvancedVisible] = useState(false)

  useEffect(() => {
    if (!tabGroups.some((tab) => tab.id === activeTab)) {
      setActiveTab(tabGroups[0]?.id ?? '')
    }
  }, [activeTab, tabGroups])

  if (tabGroups.length === 0 || !configSchema?.nested) {
    return null
  }

  const navSections: ConfigSection[] = tabGroups.map((tab) => ({
    key: tab.id,
    label: tab.label,
    advanced: tab.advanced,
    order: tab.order,
    dirty: hasUnsavedChanges && tab.sections.some((s) => sectionValues[s] !== null),
  }))

  const updateSectionValueByPath = (sectionName: string, restPath: string[], value: unknown) => {
    const currentSectionValue = sectionValues[sectionName] ?? {}
    const nextSectionValue =
      restPath.length === 0
        ? (value as ConfigSectionData)
        : updateNestedValue(currentSectionValue, restPath, value)

    setSectionValue(sectionName, nextSectionValue)
    setHasUnsavedChanges(true)
  }

  const getSubtabLabel = (schema: ConfigSchema, fallback: string) => {
    return schema.uiSubLabel || schema.uiLabel || schema.classDoc || fallback
  }

  const getObjectSubcategoryEntries = (sectionSchema: ConfigSchema) => {
    const sectionFieldByName = new Map(sectionSchema.fields.map((field) => [field.name, field]))
    return Object.entries(sectionSchema.nested ?? {}).filter(([subcategoryName]) => {
      return sectionFieldByName.get(subcategoryName)?.type === 'object'
    })
  }

  const renderSubtabbedContent = (tabId: string, tabNestedEntries: readonly (readonly [string, ConfigSchema])[]) => {
    const subtabPanes: SubtabPane[] = []
    const chatManagementHintPaneIds = new Set(['chat.reply_timing', 'chat.reply_style'])
    const entryMap = new Map<string, ConfigSchema>(
      tabNestedEntries.map(([sectionName, schema]) => [sectionName, schema]),
    )
    const childSectionsByParent = new Map<string, Array<readonly [string, ConfigSchema]>>()

    for (const [sectionName, sectionSchema] of tabNestedEntries) {
      const parentName = sectionSchema.uiParent
      if (!parentName || !entryMap.has(parentName)) {
        continue
      }

      const childSections = childSectionsByParent.get(parentName) ?? []
      childSections.push([sectionName, sectionSchema])
      childSectionsByParent.set(parentName, childSections)
    }

    const collectDescendantEntries = (parentName: string): Array<readonly [string, ConfigSchema]> => {
      const directChildEntries = childSectionsByParent.get(parentName) ?? []

      return directChildEntries.flatMap(([childName, childSchema]) => {
        return [[childName, childSchema] as const, ...collectDescendantEntries(childName)]
      })
    }

    const renderSectionGroupContent = (sectionEntries: Array<readonly [string, ConfigSchema]>) => {
      const values = Object.fromEntries(
        sectionEntries.map(([sectionName]) => [sectionName, sectionValues[sectionName] ?? {}])
      )
      const groupSchema: ConfigSchema = {
        className: sectionEntries.map(([sectionName]) => sectionName).join('.'),
        classDoc: sectionEntries[0]?.[1].uiLabel || sectionEntries[0]?.[1].classDoc || '',
        fields: [],
        nested: Object.fromEntries(sectionEntries),
      }

      return (
        <DynamicConfigForm
          schema={groupSchema}
          values={values}
          onChange={(fieldPath, value) => {
            const [sectionName, ...restPath] = fieldPath.split('.')
            if (!sectionName) {
              return
            }

            updateSectionValueByPath(sectionName, restPath, value)
          }}
          hooks={fieldHooks}
          advancedVisible={advancedVisible}
          sectionColumns={2}
        />
      )
    }

    for (const [sectionName, sectionSchema] of tabNestedEntries) {
      if (sectionSchema.uiParent && entryMap.has(sectionSchema.uiParent)) {
        continue
      }

      const sectionValue = (sectionValues[sectionName] ?? {}) as ConfigSectionData
      const allSubcategoryEntries = sectionSchema.uiUseSubTabs ? getObjectSubcategoryEntries(sectionSchema) : []
      const subcategoryEntries = allSubcategoryEntries
      const subcategoryNames = new Set(allSubcategoryEntries.map(([subcategoryName]) => subcategoryName))
      const rootFields = sectionSchema.fields.filter((field) => !subcategoryNames.has(field.name))
      const rootSchema: ConfigSchema = {
        ...sectionSchema,
        className: `${sectionSchema.className}Root`,
        fields: rootFields,
        nested: {},
      }

      if (rootFields.length > 0) {
        subtabPanes.push({
          advanced: Boolean(sectionSchema.uiAdvanced),
          id: sectionName,
          label: sectionSchema.uiRootSubLabel || getSubtabLabel(sectionSchema, sectionName),
          content: (
            <DynamicConfigForm
              schema={rootSchema}
              values={sectionValue}
              onChange={(fieldPath, value) => updateSectionValueByPath(sectionName, fieldPath.split('.'), value)}
              basePath={sectionName}
              hooks={fieldHooks}
              advancedVisible={advancedVisible}
              sectionColumns={1}
            />
          ),
        })
      }

      for (const [subcategoryName, subcategorySchema] of subcategoryEntries) {
        subtabPanes.push({
          advanced: Boolean(subcategorySchema.uiAdvanced),
          id: `${sectionName}.${subcategoryName}`,
          label: getSubtabLabel(subcategorySchema, subcategoryName),
          content: (
            <DynamicConfigForm
              schema={subcategorySchema}
              values={(sectionValue[subcategoryName] as Record<string, unknown>) || {}}
              onChange={(fieldPath, value) =>
                updateSectionValueByPath(sectionName, [subcategoryName, ...fieldPath.split('.')], value)
              }
              basePath={`${sectionName}.${subcategoryName}`}
              hooks={fieldHooks}
              advancedVisible={advancedVisible}
              sectionColumns={1}
            />
          ),
        })
      }

      for (const [childName, childSchema] of childSectionsByParent.get(sectionName) ?? []) {
        const sectionGroupEntries = [[childName, childSchema] as const, ...collectDescendantEntries(childName)]
        subtabPanes.push({
          advanced: Boolean(childSchema.uiAdvanced),
          id: childName,
          label: getSubtabLabel(childSchema, childName),
          content: renderSectionGroupContent(sectionGroupEntries),
        })
      }
    }

    if (subtabPanes.length === 0) {
      return null
    }

    const subtabExpanded = Boolean(expandedSubtabGroups[tabId])
    const defaultSubtabPanes = subtabPanes.filter((pane) => !pane.advanced)
    const expandedSubtabPanes = subtabPanes.filter((pane) => pane.advanced)
    const visibleSubtabPanes = subtabExpanded ? [...defaultSubtabPanes, ...expandedSubtabPanes] : defaultSubtabPanes
    const hasCollapsibleSubtabs = subtabPanes.some((pane) => pane.advanced)
    const firstExpandedSubtabId = visibleSubtabPanes.find((pane) => pane.advanced)?.id
    const visibleSubtabIds = new Set(visibleSubtabPanes.map((pane) => pane.id))
    const activeSubtab = activeSubtabByGroup[tabId]
    const resolvedActiveSubtab = visibleSubtabIds.has(activeSubtab)
      ? activeSubtab
      : visibleSubtabPanes[0]?.id ?? subtabPanes[0].id

    const toggleSubtabsExpanded = () => {
      if (subtabExpanded && subtabPanes.find((pane) => pane.id === resolvedActiveSubtab)?.advanced) {
        setActiveSubtabByGroup((current) => ({
          ...current,
          [tabId]: defaultSubtabPanes[0]?.id ?? subtabPanes[0].id,
        }))
      }

      setExpandedSubtabGroups((current) => ({
        ...current,
        [tabId]: !subtabExpanded,
      }))
    }

    return (
      <Tabs
        key={subtabPanes.map((pane) => pane.id).join('|')}
        value={resolvedActiveSubtab}
        onValueChange={(value) =>
          setActiveSubtabByGroup((current) => ({
            ...current,
            [tabId]: value,
          }))
        }
        className="space-y-3"
      >
        <div className="flex items-center gap-2">
          <TabsList className="h-9 bg-muted/50">
            {visibleSubtabPanes.map((pane) => (
              <Fragment key={pane.id}>
                {pane.id === firstExpandedSubtabId && (
                  <span className="bg-border/90 mx-1 hidden h-5 w-px" />
                )}
                <TabsTrigger
                  value={pane.id}
                  className={cn(
                    'px-3 text-sm',
                    pane.advanced &&
                      'text-muted-foreground/80 underline decoration-dashed underline-offset-4 data-[state=active]:bg-primary/10 data-[state=active]:text-primary'
                  )}
                >
                  {pane.label}
                </TabsTrigger>
              </Fragment>
            ))}
          </TabsList>
          {hasCollapsibleSubtabs && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="group h-8 shrink-0 gap-1 px-2 text-xs"
              onClick={toggleSubtabsExpanded}
            >
              <ChevronDown
                className={cn('h-3.5 w-3.5 transition-transform duration-200', subtabExpanded && 'rotate-180')}
              />
              {subtabExpanded ? '收起' : '更多'}
            </Button>
          )}
        </div>

        {visibleSubtabPanes.map((pane) => (
          <TabsContent key={pane.id} value={pane.id} className="mt-0">
            {chatManagementHintPaneIds.has(pane.id) && (
              <div className="mb-3 flex flex-col gap-2 rounded-md border bg-muted/20 px-3 py-2 text-sm text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
                <span>需要按具体聊天流调整发言频率或查看聊天 Prompt 时，可以前往聊天管理。</span>
                <Button asChild size="sm" variant="outline" className="h-8 shrink-0 self-start sm:self-center">
                  <Link to="/chat-management">
                    <ExternalLink className="mr-2 h-3.5 w-3.5" />
                    聊天管理
                  </Link>
                </Button>
              </div>
            )}
            {pane.content}
          </TabsContent>
        ))}
      </Tabs>
    )
  }

  const renderTabContent = (tab: TabGroup) => {
    const tabNestedEntries = tab.sections
      .map((sectionName) => [sectionName, configSchema.nested?.[sectionName]] as const)
      .filter((entry): entry is readonly [string, ConfigSchema] => Boolean(entry[1]))

    if (tabNestedEntries.length === 0) {
      return null
    }

    if (tabNestedEntries.some(([, sectionSchema]) => sectionSchema.uiUseSubTabs)) {
      return renderSubtabbedContent(tab.id, tabNestedEntries)
    }

    const values = Object.fromEntries(
      tabNestedEntries.map(([sectionName]) => [sectionName, sectionValues[sectionName] ?? {}])
    )

    const tabSchema: ConfigSchema = {
      className: tab.id,
      classDoc: tab.label,
      fields: [],
      nested: Object.fromEntries(tabNestedEntries),
    }

    return (
      <DynamicConfigForm
        schema={tabSchema}
        values={values}
        onChange={(fieldPath, value) => {
          const [sectionName, ...restPath] = fieldPath.split('.')
          if (!sectionName) {
            return
          }

          updateSectionValueByPath(sectionName, restPath, value)
        }}
        hooks={fieldHooks}
        advancedVisible={advancedVisible}
        sectionColumns={2}
      />
    )
  }

  const activeTabGroup = tabGroups.find((tab) => tab.id === activeTab)

  return (
    <div className="flex h-full gap-0">
      <div className="w-[200px] shrink-0 border-r bg-muted/20">
        <ConfigSectionNav
          sections={navSections}
          activeKey={activeTab}
          onSectionChange={setActiveTab}
        />
        <div className="border-t p-2">
          <Button
            type="button"
            variant={advancedVisible ? 'default' : 'outline'}
            size="sm"
            className="w-full justify-center text-xs"
            onClick={() => setAdvancedVisible((current) => !current)}
          >
            高级设置
          </Button>
        </div>
      </div>
      <div className="min-w-0 flex-1 overflow-y-auto p-4">
        {activeTabGroup && renderTabContent(activeTabGroup)}
      </div>
    </div>
  )
}
