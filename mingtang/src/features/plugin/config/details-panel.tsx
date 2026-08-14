/**
 * plugin-config 详情面板（PluginDetailsPanel）——详情 tab 展示插件元信息 / 市场反馈 /
 * README / 更新日志 / 注册组件。R4 债清理 P1 从 config/index.tsx 纯文件级拆分（不改逻辑）。
 */
import { useEffect, useState } from 'react'

import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area'
import { MarkdownRenderer } from '@/components/markdown-renderer'
import { PluginStats } from '@/components/plugin-stats'
import { getLocalPluginReadme, getPluginRuntimeComponents, type InstalledPlugin, type PluginRuntimeComponent, type PluginRuntimeComponentType } from '@/lib/plugin-api'
import { AlertCircle, Loader2, Terminal, Wrench } from 'lucide-react'

// ---- PluginDetailsPanel ----
interface PluginDetailItem {
  label: string
  value: string
}

interface PluginDetailsPanelProps {
  plugin: InstalledPlugin
  description: string
  detailItems: PluginDetailItem[]
  homepageUrl?: string
  repositoryUrl?: string
  documentationUrl?: string
  issuesUrl?: string
  changelog?: string | null
}

type ComponentDisplayGroup = 'tool' | 'command'

const COMPONENT_GROUP_LABELS: Record<ComponentDisplayGroup, string> = {
  tool: '工具',
  command: '命令',
}

const COMPONENT_GROUP_DESCRIPTIONS: Record<ComponentDisplayGroup, string> = {
  tool: '包含 Tool 与旧版本兼容的 Action',
  command: '通过命令文本触发的组件',
}

const COMPONENT_TYPE_LABELS: Record<PluginRuntimeComponentType, string> = {
  action: '旧版动作',
  command: '命令',
  tool: '工具',
}

const COMPONENT_GROUP_ICONS = {
  tool: Wrench,
  command: Terminal,
}

function getSchemaPropertyNames(schema: Record<string, unknown> | undefined): string[] {
  const properties = schema?.properties
  if (!properties || typeof properties !== 'object' || Array.isArray(properties)) {
    return []
  }
  return Object.keys(properties)
}

function resolveComponentDisplayGroup(component: PluginRuntimeComponent): ComponentDisplayGroup {
  return component.component_type === 'command' ? 'command' : 'tool'
}

function groupComponentsByDisplayGroup(components: PluginRuntimeComponent[]) {
  return components.reduce<Record<ComponentDisplayGroup, PluginRuntimeComponent[]>>(
    (grouped, component) => {
      grouped[resolveComponentDisplayGroup(component)].push(component)
      return grouped
    },
    { tool: [], command: [] }
  )
}

export function PluginDetailsPanel({
  plugin,
  description,
  detailItems,
  homepageUrl,
  repositoryUrl,
  documentationUrl,
  issuesUrl,
  changelog,
}: PluginDetailsPanelProps) {
  const [components, setComponents] = useState<PluginRuntimeComponent[]>([])
  const [componentsLoading, setComponentsLoading] = useState(true)
  const [componentsError, setComponentsError] = useState('')
  const [readme, setReadme] = useState('')
  const [readmeLoading, setReadmeLoading] = useState(true)
  const [readmeError, setReadmeError] = useState('')

  useEffect(() => {
    let cancelled = false

    // eslint-disable-next-line react-hooks/set-state-in-effect -- plugin.id 变化时重置加载状态；首次渲染初值已对齐（loading=true, error=''），setState 为 no-op
    setComponentsLoading(true)
    setComponentsError('')
    getPluginRuntimeComponents(plugin.id)
      .then((data) => {
        if (!cancelled) {
          setComponents(data)
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setComponentsError(error instanceof Error ? error.message : '组件加载失败')
        }
      })
      .finally(() => {
        if (!cancelled) {
          setComponentsLoading(false)
        }
      })

    return () => {
      cancelled = true
    }
  }, [plugin.id])

  useEffect(() => {
    let cancelled = false

    // eslint-disable-next-line react-hooks/set-state-in-effect -- plugin.id 变化时重置加载状态；首次渲染初值已对齐（loading=true, error='', readme=''），setState 为 no-op
    setReadmeLoading(true)
    setReadmeError('')
    setReadme('')
    getLocalPluginReadme(plugin.id)
      .then((content) => {
        if (!cancelled) {
          setReadme(content)
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setReadmeError(error instanceof Error ? error.message : 'README 加载失败')
        }
      })
      .finally(() => {
        if (!cancelled) {
          setReadmeLoading(false)
        }
      })

    return () => {
      cancelled = true
    }
  }, [plugin.id])

  const groupedComponents = groupComponentsByDisplayGroup(components)
  const componentCount = components.length
  const statsPluginId = plugin.manifest.id || plugin.id

  return (
    <div className="space-y-4">
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.4fr)_minmax(320px,0.8fr)]">
        <Card>
          <CardHeader>
            <CardTitle>插件详情</CardTitle>
            <CardDescription>{description || '暂无描述'}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-2">
              {detailItems.map((item) => (
                <div key={item.label} className="bg-muted/20 min-w-0 rounded-md border px-3 py-2">
                  <div className="text-muted-foreground text-xs font-medium">{item.label}</div>
                  <div className="mt-1 text-sm break-words">{item.value}</div>
                </div>
              ))}
            </div>
            {(homepageUrl || repositoryUrl || documentationUrl || issuesUrl) && (
              <div className="flex flex-wrap gap-2">
                {homepageUrl && (
                  <Button variant="outline" size="sm" asChild>
                    <a href={homepageUrl} target="_blank" rel="noreferrer">
                      主页
                    </a>
                  </Button>
                )}
                {repositoryUrl && (
                  <Button variant="outline" size="sm" asChild>
                    <a href={repositoryUrl} target="_blank" rel="noreferrer">
                      仓库
                    </a>
                  </Button>
                )}
                {documentationUrl && (
                  <Button variant="outline" size="sm" asChild>
                    <a href={documentationUrl} target="_blank" rel="noreferrer">
                      文档
                    </a>
                  </Button>
                )}
                {issuesUrl && (
                  <Button variant="outline" size="sm" asChild>
                    <a href={issuesUrl} target="_blank" rel="noreferrer">
                      问题反馈
                    </a>
                  </Button>
                )}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>市场反馈</CardTitle>
            <CardDescription>点赞、评分和评论会提交到插件市场统计服务。</CardDescription>
          </CardHeader>
          <CardContent>
            <PluginStats pluginId={statsPluginId} />
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>README</CardTitle>
          <CardDescription>插件根目录中的说明文档。</CardDescription>
        </CardHeader>
        <CardContent>
          {readmeLoading ? (
            <div className="text-muted-foreground flex items-center justify-center gap-2 py-8 text-sm">
              <Loader2 className="h-4 w-4 animate-spin" />
              正在加载 README
            </div>
          ) : readmeError ? (
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>{readmeError}</AlertDescription>
            </Alert>
          ) : readme ? (
            <ScrollArea className="h-[min(48vh,540px)] pr-4">
              <MarkdownRenderer content={readme} />
            </ScrollArea>
          ) : (
            <div className="text-muted-foreground rounded-md border border-dashed px-4 py-8 text-center text-sm">
              暂无 README
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>更新日志</CardTitle>
          <CardDescription>插件作者提供的版本变更记录。</CardDescription>
        </CardHeader>
        <CardContent>
          {changelog ? (
            <ScrollArea className="h-[min(36vh,420px)] pr-4">
              <MarkdownRenderer content={changelog} />
            </ScrollArea>
          ) : (
            <div className="text-muted-foreground rounded-md border border-dashed px-4 py-8 text-center text-sm">
              暂无更新日志
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <CardTitle>注册组件</CardTitle>
              <CardDescription>当前插件运行时已注册的 Tool、旧版 Action 和 Command。</CardDescription>
            </div>
            <Badge variant="secondary">{componentCount} 个组件</Badge>
          </div>
        </CardHeader>
        <CardContent>
          {componentsLoading ? (
            <div className="text-muted-foreground flex items-center justify-center gap-2 py-8 text-sm">
              <Loader2 className="h-4 w-4 animate-spin" />
              正在加载组件
            </div>
          ) : componentsError ? (
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>{componentsError}</AlertDescription>
            </Alert>
          ) : componentCount === 0 ? (
            <div className="text-muted-foreground rounded-md border border-dashed px-4 py-8 text-center text-sm">
              当前插件未注册运行时组件
            </div>
          ) : (
            <div className="grid gap-4 lg:grid-cols-2">
              {(Object.keys(COMPONENT_GROUP_LABELS) as ComponentDisplayGroup[]).map((componentGroup) => {
                const Icon = COMPONENT_GROUP_ICONS[componentGroup]
                const typedComponents = groupedComponents[componentGroup]
                return (
                  <section key={componentGroup} className="min-w-0 space-y-3">
                    <div className="flex items-center justify-between gap-2">
                      <div className="min-w-0">
                        <h3 className="flex items-center gap-2 text-sm font-semibold">
                          <Icon className="h-4 w-4 text-muted-foreground" />
                          {COMPONENT_GROUP_LABELS[componentGroup]}
                        </h3>
                        <p className="text-muted-foreground mt-1 text-xs">
                          {COMPONENT_GROUP_DESCRIPTIONS[componentGroup]}
                        </p>
                      </div>
                      <Badge variant="outline">{typedComponents.length}</Badge>
                    </div>
                    {typedComponents.length === 0 ? (
                      <div className="text-muted-foreground rounded-md border border-dashed px-3 py-4 text-center text-xs">
                        暂无{COMPONENT_GROUP_LABELS[componentGroup]}组件
                      </div>
                    ) : (
                      <div className="space-y-2">
                        {typedComponents.map((component) => {
                          const schemaProperties = getSchemaPropertyNames(component.parameters_schema)
                          return (
                            <div key={`${component.component_type}-${component.name}`} className="rounded-md border p-3">
                              <div className="mb-2 flex items-start justify-between gap-2">
                                <div className="min-w-0">
                                  <div className="break-words text-sm font-medium">{component.name}</div>
                                  {component.description && (
                                    <p className="text-muted-foreground mt-1 line-clamp-3 text-xs">
                                      {component.description}
                                    </p>
                                  )}
                                </div>
                                <Badge variant={component.enabled ? 'default' : 'secondary'} className="shrink-0">
                                  {component.enabled ? '启用' : '禁用'}
                                </Badge>
                              </div>
                              <Badge variant="outline" className="mb-2 text-[0.68rem]">
                                {COMPONENT_TYPE_LABELS[component.component_type]}
                              </Badge>

                              {component.component_type === 'action' && (
                                <div className="text-muted-foreground space-y-1 text-xs">
                                  {component.activation_type && <div>触发方式：{component.activation_type}</div>}
                                  {component.activation_keywords && component.activation_keywords.length > 0 && (
                                    <div className="flex flex-wrap gap-1">
                                      {component.activation_keywords.map((keyword) => (
                                        <Badge key={keyword} variant="outline" className="text-[0.68rem]">
                                          {keyword}
                                        </Badge>
                                      ))}
                                    </div>
                                  )}
                                </div>
                              )}

                              {component.component_type === 'tool' && schemaProperties.length > 0 && (
                                <div className="mt-2 flex flex-wrap gap-1">
                                  {schemaProperties.map((propertyName) => (
                                    <Badge key={propertyName} variant="outline" className="text-[0.68rem]">
                                      {propertyName}
                                    </Badge>
                                  ))}
                                </div>
                              )}
                            </div>
                          )
                        })}
                      </div>
                    )}
                  </section>
                )
              })}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
