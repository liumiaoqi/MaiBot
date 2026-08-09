import { useState, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { PageShell } from '@/components/biz/page-shell'
import { LoadingSkeleton } from '@/components/biz/loading-skeleton'
import { Button } from '@/components/ui/button'
import { Plus, Search, AlertTriangle, Save } from 'lucide-react'
import { useModelConfig } from '../components/use-model-config'
import { ConnectionTestBadge } from '../components/connection-test-badge'
import { MultiSelect } from '../components/multi-select'

type ModelTab = 'providers' | 'models' | 'tasks'

/** 模型管理页（/config/model）——三 tab + useModelConfig 领域 hook */
export function ModelConfigPage() {
  const { t } = useTranslation()
  const [activeTab, setActiveTab] = useState<ModelTab>('providers')

  const model = useModelConfig()

  // 无效模型引用检测
  const invalidModelRefs = useMemo(() => {
    const validModelNames = new Set(model.models.map((m) => m.name))
    const invalid: string[] = []
    for (const [taskName, task] of Object.entries(model.taskConfig)) {
      for (const modelName of task.models ?? []) {
        if (!validModelNames.has(modelName)) {
          invalid.push(`${taskName} → ${modelName}`)
        }
      }
    }
    return invalid
  }, [model.models, model.taskConfig])

  // 空任务检测
  const emptyTasks = useMemo(() => {
    return Object.entries(model.taskConfig)
      .filter(([, task]) => !task.models || task.models.length === 0)
      .map(([name]) => name)
  }, [model.taskConfig])

  const tabs: { key: ModelTab; label: string }[] = [
    { key: 'providers', label: '厂商' },
    { key: 'models', label: '模型' },
    { key: 'tasks', label: '任务' },
  ]

  return (
    <PageShell
      title={t('sidebar.menu.modelManagement')}
      breadcrumb={[t('sidebar.groups.botConfig')]}
      actions={
        <Button
          size="sm"
          onClick={() => model.saveConfig()}
          disabled={!model.hasUnsavedChanges || model.isSaving}
          data-testid="model-save"
        >
          <Save className="h-4 w-4 mr-1" />
          保存
        </Button>
      }
    >
      {model.isLoading ? <LoadingSkeleton /> : (
        <div className="space-y-4">
          {/* 无效模型引用警告 */}
          {invalidModelRefs.length > 0 && (
            <div className="rounded-md border border-amber-500/40 bg-amber-500/10 p-3 flex items-center gap-2" data-testid="invalid-model-warning">
              <AlertTriangle className="h-4 w-4 text-amber-500" />
              <span className="text-sm">
                无效模型引用（{invalidModelRefs.length}）：{invalidModelRefs.slice(0, 3).join('、')}
                {invalidModelRefs.length > 3 && '...'}
              </span>
            </div>
          )}

          {/* 空任务警告 */}
          {emptyTasks.length > 0 && (
            <div className="rounded-md border border-amber-500/40 bg-amber-500/10 p-3 flex items-center gap-2" data-testid="empty-task-warning">
              <AlertTriangle className="h-4 w-4 text-amber-500" />
              <span className="text-sm">空任务：{emptyTasks.join('、')}</span>
            </div>
          )}

          {/* Tab 按钮组 */}
          <div className="flex items-center gap-1 border-b pb-2" data-testid="model-tabs">
            {tabs.map((tab) => (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                data-testid={`model-tab-${tab.key}`}
                className={`px-3 py-1.5 text-sm rounded-t ${
                  activeTab === tab.key
                    ? 'bg-background border border-border border-b-0 font-medium'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* Tab1 厂商 */}
          {activeTab === 'providers' && (
            <div className="space-y-3" data-testid="model-providers-tab">
              <div className="flex items-center gap-2">
                <div className="relative flex-1 max-w-xs">
                  <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <input
                    type="text"
                    value={model.searchQuery}
                    onChange={(e) => model.setSearchQuery(e.target.value)}
                    placeholder="搜索厂商..."
                    className="w-full pl-8 pr-3 py-1.5 text-sm rounded-md border border-border bg-background"
                    data-testid="provider-search"
                  />
                </div>
                <Button size="sm" data-testid="provider-add">
                  <Plus className="h-4 w-4 mr-1" />
                  添加厂商
                </Button>
              </div>
              <div className="rounded-md border">
                <table className="w-full text-sm" data-testid="provider-table">
                  <thead className="border-b bg-muted/50">
                    <tr>
                      <th className="px-3 py-2 text-left">名称</th>
                      <th className="px-3 py-2 text-left">Base URL</th>
                      <th className="px-3 py-2 text-left">状态</th>
                      <th className="px-3 py-2 text-left">操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {model.filteredProviders.map((provider, index) => (
                      <tr key={index} className="border-b last:border-0" data-testid={`provider-row-${index}`}>
                        <td className="px-3 py-2">{provider.name}</td>
                        <td className="px-3 py-2 text-muted-foreground">{provider.base_url}</td>
                        <td className="px-3 py-2">
                          <ConnectionTestBadge
                            result={model.testResults.get(provider.name)}
                            isTesting={model.testingProviders.has(provider.name)}
                          />
                        </td>
                        <td className="px-3 py-2">
                          <button
                            onClick={() => model.testProvider(provider.name)}
                            className="text-xs text-blue-600 hover:underline"
                            data-testid={`provider-test-${index}`}
                          >
                            测试
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Tab2 模型 */}
          {activeTab === 'models' && (
            <div className="space-y-3" data-testid="model-models-tab">
              <div className="flex items-center gap-2">
                <div className="relative flex-1 max-w-xs">
                  <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <input
                    type="text"
                    value={model.searchQuery}
                    onChange={(e) => model.setSearchQuery(e.target.value)}
                    placeholder="搜索模型..."
                    className="w-full pl-8 pr-3 py-1.5 text-sm rounded-md border border-border bg-background"
                    data-testid="model-search"
                  />
                </div>
                <Button size="sm" data-testid="model-add">
                  <Plus className="h-4 w-4 mr-1" />
                  添加模型
                </Button>
              </div>
              <div className="rounded-md border">
                <table className="w-full text-sm" data-testid="model-table">
                  <thead className="border-b bg-muted/50">
                    <tr>
                      <th className="px-3 py-2 text-left">名称</th>
                      <th className="px-3 py-2 text-left">厂商</th>
                      <th className="px-3 py-2 text-left">标识</th>
                      <th className="px-3 py-2 text-left">操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {model.filteredModels.map((m, index) => (
                      <tr key={index} className="border-b last:border-0" data-testid={`model-row-${index}`}>
                        <td className="px-3 py-2">{m.name}</td>
                        <td className="px-3 py-2 text-muted-foreground">{m.api_provider}</td>
                        <td className="px-3 py-2 text-muted-foreground">{m.model_identifier}</td>
                        <td className="px-3 py-2">
                          <button
                            onClick={() => model.testModel(m.name)}
                            className="text-xs text-blue-600 hover:underline"
                            data-testid={`model-test-${index}`}
                          >
                            测试
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Tab3 任务 */}
          {activeTab === 'tasks' && (
            <div className="space-y-3" data-testid="model-tasks-tab">
              {Object.entries(model.taskConfig).map(([taskName, task]) => (
                <div key={taskName} className="rounded-md border p-4 space-y-3" data-testid={`task-card-${taskName}`}>
                  <h3 className="font-semibold" text-foreground>{taskName}</h3>
                  <div className="space-y-2">
                    <div>
                      <label className="text-xs text-muted-foreground">模型</label>
                      <MultiSelect
                        options={model.models.map((m) => ({ label: m.name, value: m.name }))}
                        selected={task.models ?? []}
                        onChange={(selected) => model.updateTask(taskName, { ...task, models: selected })}
                        placeholder="选择模型..."
                      />
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="text-xs text-muted-foreground">温度</label>
                        <input
                          type="number"
                          step="0.1"
                          min="0"
                          max="2"
                          value={task.temperature ?? 0.7}
                          onChange={(e) => model.updateTask(taskName, { ...task, temperature: parseFloat(e.target.value) })}
                          className="w-full px-2 py-1 text-sm rounded border border-border bg-background"
                          data-testid={`task-temperature-${taskName}`}
                        />
                      </div>
                      <div>
                        <label className="text-xs text-muted-foreground">最大 Token</label>
                        <input
                          type="number"
                          value={task.max_tokens ?? 4096}
                          onChange={(e) => model.updateTask(taskName, { ...task, max_tokens: parseInt(e.target.value) })}
                          className="w-full px-2 py-1 text-sm rounded border border-border bg-background"
                          data-testid={`task-max-tokens-${taskName}`}
                        />
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </PageShell>
  )
}
