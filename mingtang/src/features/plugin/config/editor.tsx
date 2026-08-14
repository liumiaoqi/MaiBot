/**
 * plugin-config 编辑器（PluginConfigEditor）——单个插件的配置编辑器（可视化 / 源代码双模式
 * + 未保存拦截）。R4 债清理 P1 从 config/index.tsx 纯文件级拆分（不改逻辑）。
 */
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { CodeEditor } from '@/components/CodeEditor'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Switch } from '@/components/ui/switch'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import type { InstalledPlugin } from '@/lib/plugin-api'
import { getPluginTypeLabel } from '@/features/plugin/shared/types'
import {
  AlertCircle,
  ArrowLeft,
  BookOpen,
  Code2,
  Info,
  Layout,
  Loader2,
  RotateCcw,
  Save,
} from 'lucide-react'

import { PluginDetailsPanel } from './details-panel'
import { PluginDocumentFloatingPanel } from './dialogs'
import { SectionRenderer, resolveLocalizedText } from './field-renderer'
import { usePluginConfigEditor } from './hooks/use-plugin-config-editor'

// ---- PluginConfigEditor ----
interface PluginConfigEditorProps {
  plugin: InstalledPlugin
  onBack: () => void
  initialTab?: string
}

export function PluginConfigEditor({ plugin, onBack, initialTab }: PluginConfigEditorProps) {
  const { i18n } = useTranslation()
  const language = i18n.resolvedLanguage || i18n.language || 'zh'
  const [documentPanelOpen, setDocumentPanelOpen] = useState(false)

  const {
    editMode,
    setEditMode,
    pluginPageTab,
    setPluginPageTab,
    activeConfigTab,
    handleConfigTabChange,
    schema,
    config,
    sourceCode,
    handleSourceCodeChange,
    handleFieldChange,
    loading,
    saving,
    hasChanges,
    hasTomlError,
    handleSave,
    handleReset,
    handleToggle,
    resetDialogOpen,
    setResetDialogOpen,
    navigationBlocker,
    internalLeavePromptOpen,
    handleBack,
    closeLeavePrompt,
    leaveWithoutSaving,
    saveAndLeave,
  } = usePluginConfigEditor({ plugin, onBack, initialTab })

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loader2 className="text-muted-foreground h-8 w-8 animate-spin" />
      </div>
    )
  }

  if (!schema) {
    return (
      <div className="flex h-64 flex-col items-center justify-center space-y-4">
        <AlertCircle className="text-muted-foreground h-12 w-12" />
        <p className="text-muted-foreground">无法加载配置</p>
        <Button onClick={onBack} variant="outline">
          <ArrowLeft className="mr-2 h-4 w-4" />
          返回
        </Button>
      </div>
    )
  }

  // 按 order 排序 sections
  const sortedSections = Object.entries(schema.sections).sort(
    ([, a], [, b]) => (a.order ?? 0) - (b.order ?? 0)
  )
  const schemaTabs = schema.layout.type === 'tabs' ? schema.layout.tabs : []
  const selectedConfigTab = schemaTabs.some((tab) => tab.id === activeConfigTab)
    ? activeConfigTab
    : schemaTabs[0]?.id

  // 获取当前启用状态
  const isEnabled = (config.plugin as Record<string, unknown>)?.enabled !== false
  const pluginName = resolveLocalizedText(
    schema.plugin_info.name,
    language,
    plugin.manifest.name,
    schema.plugin_info.i18n,
    'name'
  )
  const manifestUrls = plugin.manifest.urls as
    | {
        repository?: string
        homepage?: string
        documentation?: string
        issues?: string
      }
    | undefined
  const pluginHomepageUrl = plugin.manifest.homepage_url || manifestUrls?.homepage
  const pluginRepositoryUrl = plugin.manifest.repository_url || manifestUrls?.repository
  const pluginDetailItems = [
    { label: '插件 ID', value: plugin.manifest.id || plugin.id },
    { label: '版本', value: schema.plugin_info.version || plugin.manifest.version },
    { label: '类型', value: getPluginTypeLabel(plugin) },
    { label: '作者', value: plugin.manifest.author?.name },
    { label: '许可证', value: plugin.manifest.license },
    { label: '最低麦麦版本', value: plugin.manifest.host_application?.min_version },
    { label: '安装路径', value: plugin.path },
  ].filter(
    (item): item is { label: string; value: string } =>
      typeof item.value === 'string' && item.value.trim().length > 0
  )

  return (
    <div className="space-y-4 sm:space-y-6">
      {/* 头部 */}
      <div
        className="sticky top-0 z-40 -mx-5 flex items-center justify-between gap-3 overflow-x-auto border-b px-5 py-2.5 shadow-sm backdrop-blur sm:-mx-7 sm:px-7 lg:-mx-8 lg:px-8"
        style={{ backgroundColor: 'hsl(var(--background) / 0.96)' }}
      >
        <div className="flex min-w-0 items-center gap-2">
          <Button variant="ghost" size="icon" className="h-8 w-8 shrink-0" onClick={handleBack}>
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <div className="flex min-w-0 items-center gap-2">
            <h1 className="min-w-0 truncate text-lg font-semibold sm:text-xl" data-plugin-config-title>
              {pluginName}
            </h1>
            <Badge variant={isEnabled ? 'default' : 'secondary'} className="shrink-0">
              {isEnabled ? '已启用' : '已禁用'}
            </Badge>
            <span className="text-muted-foreground shrink-0 text-sm">
              v{schema.plugin_info.version || plugin.manifest.version}
            </span>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2 whitespace-nowrap sm:gap-3">
          <Button
            variant="outline"
            size="sm"
            className="h-8"
            onClick={() => setDocumentPanelOpen(true)}
          >
            <BookOpen className="mr-2 h-4 w-4" />
            打开文档
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="h-8"
            onClick={() => setEditMode(editMode === 'visual' ? 'source' : 'visual')}
          >
            {editMode === 'visual' ? (
              <>
                <Code2 className="mr-2 h-4 w-4" />
                源代码
              </>
            ) : (
              <>
                <Layout className="mr-2 h-4 w-4" />
                可视化
              </>
            )}
          </Button>
          <div
            data-dashboard-input="true"
            className="border-input flex h-8 items-center gap-2 rounded-md border bg-transparent px-2 text-sm font-medium shadow-sm"
          >
            <Switch
              checked={isEnabled}
              onCheckedChange={() => void handleToggle()}
              aria-label={isEnabled ? '禁用插件' : '启用插件'}
            />
            <span className="text-xs">启用</span>
          </div>
          <Button
            variant="outline"
            size="sm"
            className="h-8"
            onClick={() => setResetDialogOpen(true)}
          >
            <RotateCcw className="mr-2 h-4 w-4" />
            重置
          </Button>
          <Button size="sm" className="h-8" onClick={handleSave} disabled={!hasChanges || saving}>
            {saving ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Save className="mr-2 h-4 w-4" />
            )}
            保存
          </Button>
        </div>
      </div>

      {/* 未保存提示 */}
      {hasChanges && (
        <Card className="border-orange-200 bg-orange-50 dark:border-orange-900 dark:bg-orange-950/20"> {/* orange 色板（警告——色板豁免） */}
          <CardContent className="py-3!">
            <div className="flex items-center gap-2">
              <Info className="h-4 w-4 text-orange-600" /> {/* orange 色板（警告——色板豁免） */}
              <p className="text-sm text-orange-800 dark:text-orange-200">有未保存的更改</p> {/* orange 色板（警告——色板豁免） */}
            </div>
          </CardContent>
        </Card>
      )}

      <Tabs
        value={pluginPageTab}
        onValueChange={(value) => setPluginPageTab(value as 'settings' | 'details')}
      >
        <TabsList>
          <TabsTrigger value="settings">设置</TabsTrigger>
          <TabsTrigger value="details">详情</TabsTrigger>
        </TabsList>
        <TabsContent value="settings" className="mt-4">
          {/* 源代码模式 */}
          {editMode === 'source' && (
            <div className="space-y-4">
              <Alert>
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>
                  <strong>文件模式：</strong>直接编辑原始配置文件。此功能仅适用于熟悉
                  TOML语法的用户。只有格式完全正确才能保存。
                  {hasTomlError && (
                    <span className="text-destructive ml-2 font-semibold">
                      ⚠️ 上次保存失败，请检查 TOML 格式
                    </span>
                  )}
                </AlertDescription>
              </Alert>

              <CodeEditor
                value={sourceCode}
                onChange={handleSourceCodeChange}
                language="toml"
                height="calc(100vh - 350px)"
                minHeight="500px"
                placeholder="TOML 配置内容"
              />
            </div>
          )}

          {/* 可视化模式 */}
          {editMode === 'visual' && (
            <>
              {/* 配置区域 */}
              {schema.layout.type === 'tabs' && schemaTabs.length > 0 ? (
                // 标签页布局
                <Tabs value={selectedConfigTab} onValueChange={handleConfigTabChange}>
                  <TabsList>
                    {schemaTabs.map((tab) => (
                      <TabsTrigger key={tab.id} value={tab.id}>
                        {resolveLocalizedText(tab.title, language, tab.id, tab.i18n, 'title')}
                        {tab.badge && (
                          <Badge variant="secondary" className="ml-2 text-xs">
                            {tab.badge}
                          </Badge>
                        )}
                      </TabsTrigger>
                    ))}
                  </TabsList>
                  {schemaTabs.map((tab) => (
                    <TabsContent key={tab.id} value={tab.id} className="mt-4 space-y-4">
                      {tab.sections.map((sectionName) => {
                        const section = schema.sections[sectionName]
                        if (!section) return null
                        return (
                          <SectionRenderer
                            key={sectionName}
                            sectionName={sectionName}
                            section={section}
                            config={config}
                            onChange={handleFieldChange}
                          />
                        )
                      })}
                    </TabsContent>
                  ))}
                </Tabs>
              ) : (
                // 自动布局
                <div className="space-y-4">
                  {sortedSections.map(([sectionName, section]) => (
                    <SectionRenderer
                      key={sectionName}
                      sectionName={sectionName}
                      section={section}
                      config={config}
                      onChange={handleFieldChange}
                    />
                  ))}
                </div>
              )}
            </>
          )}
        </TabsContent>
        <TabsContent value="details" className="mt-4">
          <PluginDetailsPanel
            plugin={plugin}
            description={plugin.manifest.description || ''}
            detailItems={pluginDetailItems}
            homepageUrl={pluginHomepageUrl}
            repositoryUrl={pluginRepositoryUrl}
            documentationUrl={manifestUrls?.documentation}
            issuesUrl={manifestUrls?.issues}
            changelog={plugin.changelog}
          />
        </TabsContent>
      </Tabs>

      {documentPanelOpen && (
        <PluginDocumentFloatingPanel
          plugin={plugin}
          onClose={() => setDocumentPanelOpen(false)}
        />
      )}

      <Dialog
        open={internalLeavePromptOpen || navigationBlocker.status === 'blocked'}
        onOpenChange={(open) => {
          if (!open) {
            closeLeavePrompt()
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>有未保存的更改</DialogTitle>
            <DialogDescription>当前插件配置文件有修改，离开页面前是否保存？</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={closeLeavePrompt} disabled={saving}>
              取消
            </Button>
            <Button variant="outline" onClick={leaveWithoutSaving} disabled={saving}>
              不保存
            </Button>
            <Button onClick={saveAndLeave} disabled={saving}>
              {saving ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Save className="mr-2 h-4 w-4" />
              )}
              保存并离开
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 重置确认对话框 */}
      <Dialog open={resetDialogOpen} onOpenChange={setResetDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>确认重置配置</DialogTitle>
            <DialogDescription>
              这将删除当前配置文件，下次加载插件时将使用默认配置。此操作不可撤销。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setResetDialogOpen(false)}>
              取消
            </Button>
            <Button variant="destructive" onClick={handleReset}>
              确认重置
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
