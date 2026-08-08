import { useState, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import type { ConfigSchema } from '@/types/config-schema'

interface DynamicConfigTabsProps {
  /** 配置 schema（顶层含 nested 子配置） */
  schema: ConfigSchema
  /** 当前激活 tab */
  activeTab?: string
  /** tab 切换回调 */
  onTabChange?: (tab: string) => void
}

/** tab 分组 schema 驱动——uiUseSubTabs/uiParent 元数据驱动 */
export function DynamicConfigTabs({ schema, activeTab, onTabChange }: DynamicConfigTabsProps) {
  const { t } = useTranslation()
  const [internalTab, setInternalTab] = useState(activeTab ?? '')
  const [advancedVisible, setAdvancedVisible] = useState(false)
  const currentTab = activeTab ?? internalTab

  /** 从 schema.nested 提取 tab 列表 */
  const tabs = useMemo(() => {
    if (!schema.nested) return []
    return Object.entries(schema.nested).map(([key, subSchema]) => ({
      key,
      label: subSchema.uiSubLabel ?? subSchema.uiLabel ?? key,
      advanced: subSchema.uiAdvanced ?? false,
      order: subSchema.uiOrder ?? 0,
    })).sort((a, b) => a.order - b.order)
  }, [schema])

  const visibleTabs = tabs.filter((tab) => !tab.advanced || advancedVisible)
  const hiddenAdvancedTabs = tabs.filter((tab) => tab.advanced && !advancedVisible)

  const handleTabChange = (tab: string) => {
    setInternalTab(tab)
    onTabChange?.(tab)
  }

  return (
    <div className="space-y-4" data-testid="dynamic-config-tabs">
      {/* Tab 按钮组 */}
      <div className="flex items-center gap-2 border-b pb-2">
        {visibleTabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => handleTabChange(tab.key)}
            data-testid={`tab-${tab.key}`}
            className={cn(
              'px-3 py-1.5 rounded-md text-sm transition-colors',
              currentTab === tab.key
                ? 'bg-primary text-primary-foreground'
                : 'hover:bg-muted'
            )}
          >
            {tab.label}
          </button>
        ))}

        {/* "更多"按钮展开高级 tab */}
        {hiddenAdvancedTabs.length > 0 && !advancedVisible && (
          <button
            onClick={() => setAdvancedVisible(true)}
            data-testid="tabs-more-btn"
            className="px-3 py-1.5 rounded-md text-sm hover:bg-muted"
          >
            {t('common.more')}
          </button>
        )}

        {/* "高级设置"开关 */}
        {tabs.some((tab) => tab.advanced) && (
          <label className="ml-auto flex items-center gap-1 text-xs">
            <input
              type="checkbox"
              checked={advancedVisible}
              onChange={(e) => setAdvancedVisible(e.target.checked)}
              data-testid="tabs-advanced-toggle"
            />
            {t('common.advancedSettings')}
          </label>
        )}
      </div>
    </div>
  )
}