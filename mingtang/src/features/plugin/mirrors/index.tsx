// plugin-mirrors 镜像源管理页——从 dashboard/src/routes/plugin-mirrors.tsx 搬移。
// 适配：useToast→sonner；默认源不可删（DEFAULT_MIRROR_IDS）；useMutation+invalidateQueries；模式 3 派生状态。
import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import { toast } from 'sonner'

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Switch } from '@/components/ui/switch'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { backendApi } from '@/lib/http'
import { PLUGIN_MARKET_COMPATIBLE_ONLY_KEY } from '@/features/plugin/marketplace/constants'
import {
  AlertTriangle,
  ArrowLeft,
  ChevronDown,
  ChevronUp,
  Loader2,
  Pencil,
  Plus,
  Trash2,
} from 'lucide-react'

import { MirrorFormDialog, type MirrorFormData } from './mirror-form-dialog'

interface MirrorConfig {
  id: string
  name: string
  raw_prefix: string
  clone_prefix: string
  enabled: boolean
  priority: number
  created_at?: string
  updated_at?: string
}

// 默认镜像源 ID 集合——后端 git_mirror_service.DEFAULT_MIRRORS 中的 6 个内置源不可删
const DEFAULT_MIRROR_IDS: ReadonlySet<string> = new Set([
  'gitproxy-mrhjx',
  'ghproxy-vip',
  'github',
  'gh-proxy-com',
  'v6-gh-proxy',
  'cdn-gh-proxy-com',
])

interface PluginMirrorsPageProps {
  embedded?: boolean
}

export function PluginMirrorsPage({ embedded = false }: PluginMirrorsPageProps) {
  const navigate = useNavigate()
  const pluginsRoute: '/plugins' | '/plugins/embed' = embedded ? '/plugins/embed' : '/plugins'
  const queryClient = useQueryClient()
  const [editingMirror, setEditingMirror] = useState<MirrorConfig | null>(null)
  const [isAddDialogOpen, setIsAddDialogOpen] = useState(false)
  const [isEditDialogOpen, setIsEditDialogOpen] = useState(false)
  const [mirrorToDelete, setMirrorToDelete] = useState<MirrorConfig | null>(null)
  const [showCompatibleOnly, setShowCompatibleOnly] = useState(
    () => localStorage.getItem(PLUGIN_MARKET_COMPATIBLE_ONLY_KEY) !== 'false'
  )

  // 表单状态（add/edit 共用——MirrorFormDialog 只做展示与透传）
  const [formData, setFormData] = useState<MirrorFormData>({
    id: '',
    name: '',
    raw_prefix: '',
    clone_prefix: '',
    enabled: true,
    priority: 1
  })

  // 加载镜像源列表：失败由 mirrorsQuery.isError 局部呈现，不弹全局 toast
  const mirrorsQuery = useQuery({
    queryKey: ['plugin-mirrors'],
    queryFn: () =>
      backendApi.get<{ mirrors?: MirrorConfig[] }>('/api/webui/plugins/mirrors', {
        errorMessage: '获取镜像源列表失败',
      }),
  })
  const mirrors = mirrorsQuery.data?.mirrors || []
  const loading = mirrorsQuery.isPending

  // 任何写操作成功后，整体失效镜像源列表
  const invalidateMirrors = () =>
    queryClient.invalidateQueries({ queryKey: ['plugin-mirrors'] })

  useEffect(() => {
    localStorage.setItem(PLUGIN_MARKET_COMPATIBLE_ONLY_KEY, String(showCompatibleOnly))
  }, [showCompatibleOnly])

  // 添加镜像源（失败由全局 mutation 错误 toast 呈现）
  const addMutation = useMutation({
    mutationFn: (body: MirrorFormData) =>
      backendApi.post('/api/webui/plugins/mirrors', {
        body,
        errorMessage: '添加镜像源失败',
      }),
    meta: { errorTitle: '添加失败' },
    onSuccess: () => {
      toast.success('添加成功', {
        description: '镜像源已添加'
      })

      setIsAddDialogOpen(false)
      setFormData({
        id: '',
        name: '',
        raw_prefix: '',
        clone_prefix: '',
        enabled: true,
        priority: 1
      })
      invalidateMirrors()
    },
  })

  const handleAddMirror = () => {
    addMutation.mutate(formData)
  }

  // 更新镜像源（失败由全局 mutation 错误 toast 呈现）
  const updateMutation = useMutation({
    mutationFn: (vars: { id: string; body: Partial<MirrorConfig> }) =>
      backendApi.put(`/api/webui/plugins/mirrors/${vars.id}`, {
        body: vars.body,
        errorMessage: '更新镜像源失败',
      }),
    meta: { errorTitle: '更新失败' },
    onSuccess: () => {
      toast.success('更新成功', {
        description: '镜像源已更新'
      })

      setIsEditDialogOpen(false)
      setEditingMirror(null)
      invalidateMirrors()
    },
  })

  const handleUpdateMirror = () => {
    if (!editingMirror) return

    updateMutation.mutate({
      id: editingMirror.id,
      body: {
        name: formData.name,
        raw_prefix: formData.raw_prefix,
        clone_prefix: formData.clone_prefix,
        enabled: formData.enabled,
        priority: formData.priority
      },
    })
  }

  // 删除镜像源（失败由全局 mutation 错误 toast 呈现）
  const deleteMutation = useMutation({
    mutationFn: (id: string) =>
      backendApi.delete(`/api/webui/plugins/mirrors/${id}`, {
        errorMessage: '删除镜像源失败',
      }),
    meta: { errorTitle: '删除失败' },
    onSuccess: () => {
      toast.success('删除成功', {
        description: '镜像源已删除'
      })

      invalidateMirrors()
    },
  })

  const handleDeleteMirror = (mirror: MirrorConfig) => {
    // 默认源不可删——按钮已禁用，此处兜底防御
    if (DEFAULT_MIRROR_IDS.has(mirror.id)) return
    // 原生 confirm() 已替换为 Radix AlertDialog 二次确认（R4 债清理 P2）
    setMirrorToDelete(mirror)
  }

  const confirmDeleteMirror = () => {
    if (!mirrorToDelete) return
    deleteMutation.mutate(mirrorToDelete.id)
    setMirrorToDelete(null)
  }

  // 切换启用状态
  const toggleEnabledMutation = useMutation({
    mutationFn: (mirror: MirrorConfig) =>
      backendApi.put(`/api/webui/plugins/mirrors/${mirror.id}`, {
        body: {
          enabled: !mirror.enabled
        },
        errorMessage: '更新状态失败',
      }),
    meta: { errorTitle: '更新失败' },
    onSuccess: () => {
      invalidateMirrors()
    },
  })

  const handleToggleEnabled = (mirror: MirrorConfig) => {
    toggleEnabledMutation.mutate(mirror)
  }

  // 打开编辑对话框
  const openEditDialog = (mirror: MirrorConfig) => {
    setEditingMirror(mirror)
    setFormData({
      id: mirror.id,
      name: mirror.name,
      raw_prefix: mirror.raw_prefix,
      clone_prefix: mirror.clone_prefix,
      enabled: mirror.enabled,
      priority: mirror.priority
    })
    setIsEditDialogOpen(true)
  }

  // 调整优先级（失败由全局 mutation 错误 toast 呈现）
  const adjustPriorityMutation = useMutation({
    mutationFn: (vars: { id: string; priority: number }) =>
      backendApi.put(`/api/webui/plugins/mirrors/${vars.id}`, {
        body: {
          priority: vars.priority
        },
        errorMessage: '更新优先级失败',
      }),
    meta: { errorTitle: '更新失败' },
    onSuccess: () => {
      invalidateMirrors()
    },
  })

  const adjustPriority = (mirror: MirrorConfig, direction: 'up' | 'down') => {
    const newPriority = direction === 'up' ? mirror.priority - 1 : mirror.priority + 1
    if (newPriority < 1) return

    adjustPriorityMutation.mutate({ id: mirror.id, priority: newPriority })
  }

  return (
    <ScrollArea className="h-full">
      <div className="space-y-6 p-4 sm:p-6">
        {/* 页面标题 */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div className="flex items-center gap-4">
            <Button
              variant="ghost"
              size="icon"
              onClick={() => navigate({ to: pluginsRoute as never })}
            >
              <ArrowLeft className="h-5 w-5" />
            </Button>
            <div>
              <h1 className="text-2xl sm:text-3xl font-bold">插件商店设置</h1>
              <p className="text-sm text-muted-foreground mt-1">
                管理插件市场筛选偏好和插件安装镜像源
              </p>
            </div>
          </div>
          <Button onClick={() => setIsAddDialogOpen(true)}>
            <Plus className="h-4 w-4 mr-2" />
            添加镜像源
          </Button>
        </div>

        <Card className="p-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="space-y-1">
              <Label htmlFor="plugin-market-compatible-only" className="text-sm font-medium">
                仅显示当前版本
              </Label>
              <p className="text-sm text-muted-foreground">
                在插件市场默认隐藏不兼容当前麦麦版本的插件
              </p>
            </div>
            <Switch
              id="plugin-market-compatible-only"
              checked={showCompatibleOnly}
              onCheckedChange={setShowCompatibleOnly}
            />
          </div>
        </Card>

        {/* 加载状态 */}
        {loading ? (
          <Card className="p-6">
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-8 w-8 animate-spin text-primary" />
            </div>
          </Card>
        ) : mirrorsQuery.isError ? (
          <Card className="p-6">
            <div className="flex flex-col items-center justify-center py-8 text-center">
              <AlertTriangle className="h-12 w-12 text-destructive mb-4" />
              <h3 className="text-lg font-semibold mb-2">加载失败</h3>
              <p className="text-sm text-muted-foreground mb-4">{mirrorsQuery.error.message}</p>
              <Button onClick={() => mirrorsQuery.refetch()}>重新加载</Button>
            </div>
          </Card>
        ) : (
          <Card>
            {/* 桌面端表格 */}
            <div className="hidden md:block">
              <Table aria-label="插件镜像源列表">
                <TableHeader>
                  <TableRow>
                    <TableHead>状态</TableHead>
                    <TableHead>名称</TableHead>
                    <TableHead>ID</TableHead>
                    <TableHead>优先级</TableHead>
                    <TableHead className="text-right">操作</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {mirrors.map((mirror) => {
                    const isDefaultMirror = DEFAULT_MIRROR_IDS.has(mirror.id)
                    return (
                      <TableRow key={mirror.id}>
                        <TableCell>
                          <Switch
                            checked={mirror.enabled}
                            onCheckedChange={() => handleToggleEnabled(mirror)}
                          />
                        </TableCell>
                        <TableCell>
                          <div>
                            <div className="font-medium">{mirror.name}</div>
                            <div className="text-xs text-muted-foreground mt-1">
                              Raw: {mirror.raw_prefix}
                            </div>
                          </div>
                        </TableCell>
                        <TableCell>
                          <Badge variant="outline">{mirror.id}</Badge>
                        </TableCell>
                        <TableCell>
                          <div className="flex items-center gap-2">
                            <span className="font-mono">{mirror.priority}</span>
                            <div className="flex flex-col gap-1">
                              <Button
                                variant="ghost"
                                size="icon"
                                className="h-5 w-5"
                                onClick={() => adjustPriority(mirror, 'up')}
                                disabled={mirror.priority === 1}
                              >
                                <ChevronUp className="h-3 w-3" />
                              </Button>
                              <Button
                                variant="ghost"
                                size="icon"
                                className="h-5 w-5"
                                onClick={() => adjustPriority(mirror, 'down')}
                              >
                                <ChevronDown className="h-3 w-3" />
                              </Button>
                            </div>
                          </div>
                        </TableCell>
                        <TableCell className="text-right">
                          <div className="flex items-center justify-end gap-2">
                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={() => openEditDialog(mirror)}
                            >
                              <Pencil className="h-4 w-4" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={() => handleDeleteMirror(mirror)}
                              disabled={isDefaultMirror}
                              title={isDefaultMirror ? '默认源不可删' : undefined}
                            >
                              <Trash2 className="h-4 w-4 text-destructive" />
                            </Button>
                          </div>
                        </TableCell>
                      </TableRow>
                    )
                  })}
                </TableBody>
              </Table>
            </div>

            {/* 移动端卡片 */}
            <div className="md:hidden p-4 space-y-4">
              {mirrors.map((mirror) => {
                const isDefaultMirror = DEFAULT_MIRROR_IDS.has(mirror.id)
                return (
                  <Card key={mirror.id} className="p-4">
                    <div className="space-y-3">
                      <div className="flex items-start justify-between">
                        <div className="flex-1">
                          <div className="flex items-center gap-2">
                            <h3 className="font-semibold">{mirror.name}</h3>
                            {mirror.enabled && (
                              <Badge variant="default" className="text-xs">启用</Badge>
                            )}
                          </div>
                          <Badge variant="outline" className="mt-1 text-xs">{mirror.id}</Badge>
                        </div>
                        <Switch
                          checked={mirror.enabled}
                          onCheckedChange={() => handleToggleEnabled(mirror)}
                        />
                      </div>

                      <div className="text-sm space-y-1">
                        <div className="text-muted-foreground">
                          <span className="font-medium">Raw: </span>
                          <span className="break-all">{mirror.raw_prefix}</span>
                        </div>
                        <div className="text-muted-foreground">
                          <span className="font-medium">优先级: </span>
                          <span className="font-mono">{mirror.priority}</span>
                        </div>
                      </div>

                      <div className="flex items-center gap-2 pt-2 border-t">
                        <Button
                          variant="outline"
                          size="sm"
                          className="flex-1"
                          onClick={() => openEditDialog(mirror)}
                        >
                          <Pencil className="h-4 w-4 mr-1" />
                          编辑
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => adjustPriority(mirror, 'up')}
                          disabled={mirror.priority === 1}
                        >
                          <ChevronUp className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => adjustPriority(mirror, 'down')}
                        >
                          <ChevronDown className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="destructive"
                          size="sm"
                          onClick={() => handleDeleteMirror(mirror)}
                          disabled={isDefaultMirror}
                          title={isDefaultMirror ? '默认源不可删' : undefined}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </div>
                  </Card>
                )
              })}
            </div>
          </Card>
        )}

        {/* 添加/编辑镜像源对话框——MirrorFormDialog 公共组件（R4 债清理 P2） */}
        <MirrorFormDialog
          mode="add"
          open={isAddDialogOpen}
          onOpenChange={setIsAddDialogOpen}
          formData={formData}
          onFormDataChange={setFormData}
          onSubmit={handleAddMirror}
        />
        <MirrorFormDialog
          mode="edit"
          open={isEditDialogOpen}
          onOpenChange={setIsEditDialogOpen}
          formData={formData}
          onFormDataChange={setFormData}
          onSubmit={handleUpdateMirror}
        />

        {/* 删除镜像源二次确认——Radix AlertDialog（原生 confirm() 已移除） */}
        <AlertDialog
          open={mirrorToDelete !== null}
          onOpenChange={(open) => { if (!open) setMirrorToDelete(null) }}
        >
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>确认删除镜像源</AlertDialogTitle>
              <AlertDialogDescription>
                确定要删除镜像源「{mirrorToDelete?.name}」吗？删除后不可恢复。
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>取消</AlertDialogCancel>
              <AlertDialogAction variant="destructive" onClick={confirmDeleteMirror}>
                删除
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </div>
    </ScrollArea>
  )
}