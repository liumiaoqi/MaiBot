/**
 * dialogs —— 插件配置页的对话框与浮动面板。
 *
 * 包含：
 * - UpdatePluginDialog / DeletePluginDialog：确认 + 进度 + 关闭，模式 3 派生状态
 *   （open/disabled 联动）——进度展示统一用 PluginProgressBox（R4 债清理 P2 抽取，
 *   见 features/plugin/components/plugin-progress-box.tsx）；
 * - LoadFailureDetailDialog：加载失败详情查看；
 * - PluginDocumentFloatingPanel：可拖拽的 README/更新日志浮动面板（Portal + pointer 事件）。
 */
import { type CSSProperties, useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { PluginProgressBox } from '@/features/plugin/components/plugin-progress-box'
import { Alert, AlertDescription } from '@/components/ui/alert'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { MarkdownRenderer } from '@/components/markdown-renderer'
import {
  AlertCircle,
  ArrowUp,
  BookOpen,
  FileText,
  GripHorizontal,
  Loader2,
  Trash2,
  X,
} from 'lucide-react'
import { getLocalPluginChangelog, getLocalPluginReadme } from '@/lib/plugin-api'
import type { InstalledPlugin, PluginLoadProgress } from '@/lib/plugin-api'

// ---- UpdatePluginDialog ----
// 进度展示统一用 PluginProgressBox（公共组件——见 features/plugin/components/plugin-progress-box.tsx）

interface UpdatePluginDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  updatingPlugin: InstalledPlugin | null
  updateProgress: PluginLoadProgress | null
  onClose: () => void
  onConfirm: () => void
}

export function UpdatePluginDialog({
  open,
  onOpenChange,
  updatingPlugin,
  updateProgress,
  onClose,
  onConfirm,
}: UpdatePluginDialogProps) {
  const isLoading = updateProgress?.stage === 'loading'
  const isFinished = updateProgress?.stage === 'success' || updateProgress?.stage === 'error'

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) {
          onClose()
          return
        }
        onOpenChange(true)
      }}
    >
      <DialogContent preventOutsideClose={isLoading} hideCloseButton={isLoading}>
        <DialogHeader>
          <DialogTitle>确认更新插件</DialogTitle>
          <DialogDescription>
            {updatingPlugin
              ? `即将更新 ${updatingPlugin.manifest.name}。更新过程中请保持麦麦运行。`
              : '即将更新插件。更新过程中请保持麦麦运行。'}
          </DialogDescription>
        </DialogHeader>

        {updateProgress && <PluginProgressBox progress={updateProgress} actionLabel="更新" />}

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={isLoading}>
            {isFinished ? '关闭' : '取消'}
          </Button>
          {!isFinished && (
            <Button onClick={onConfirm} disabled={!updatingPlugin || isLoading}>
              {isLoading ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <ArrowUp className="mr-2 h-4 w-4" />
              )}
              {isLoading ? '更新中' : '确认更新'}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ---- DeletePluginDialog ----

interface DeletePluginDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  deletingPlugin: InstalledPlugin | null
  deleteProgress: PluginLoadProgress | null
  onClose: () => void
  onConfirm: () => void
}

export function DeletePluginDialog({
  open,
  onOpenChange,
  deletingPlugin,
  deleteProgress,
  onClose,
  onConfirm,
}: DeletePluginDialogProps) {
  const isLoading = deleteProgress?.stage === 'loading'
  const isFinished = deleteProgress?.stage === 'success' || deleteProgress?.stage === 'error'

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) {
          onClose()
          return
        }
        onOpenChange(true)
      }}
    >
      <DialogContent preventOutsideClose={isLoading} hideCloseButton={isLoading}>
        <DialogHeader>
          <DialogTitle>确认删除插件</DialogTitle>
          <DialogDescription>
            {deletingPlugin
              ? `即将删除 ${deletingPlugin.manifest.name}。删除后可从插件市场重新安装。`
              : '即将删除插件。删除后可从插件市场重新安装。'}
          </DialogDescription>
        </DialogHeader>

        {deleteProgress && <PluginProgressBox progress={deleteProgress} actionLabel="删除" />}

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={isLoading}>
            {isFinished ? '关闭' : '取消'}
          </Button>
          {!isFinished && (
            <Button variant="destructive" onClick={onConfirm} disabled={!deletingPlugin || isLoading}>
              {isLoading ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Trash2 className="mr-2 h-4 w-4" />
              )}
              {isLoading ? '删除中' : '确认删除'}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ---- LoadFailureDetailDialog ----

interface LoadFailureDetailDialogProps {
  plugin: InstalledPlugin | null
  onOpenChange: (open: boolean) => void
  getPluginStatusLabel: (plugin: InstalledPlugin) => string
}

export function LoadFailureDetailDialog({
  plugin,
  onOpenChange,
  getPluginStatusLabel,
}: LoadFailureDetailDialogProps) {
  return (
    <Dialog
      open={plugin !== null}
      onOpenChange={(open) => {
        if (!open) {
          onOpenChange(false)
        }
      }}
    >
      <DialogContent className="max-w-[min(92vw,44rem)]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-red-600"> {/* red 色板（错误——色板豁免） */}
            <AlertCircle className="h-5 w-5" />
            插件加载失败详情
          </DialogTitle>
          <DialogDescription>
            {plugin?.manifest.name || '插件'} 未能完成加载。
          </DialogDescription>
        </DialogHeader>

        {plugin && (
          <div className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="rounded-md border px-3 py-2">
                <div className="text-muted-foreground text-xs font-medium">插件 ID</div>
                <div className="mt-1 break-words text-sm">{plugin.id}</div>
              </div>
              <div className="rounded-md border px-3 py-2">
                <div className="text-muted-foreground text-xs font-medium">版本</div>
                <div className="mt-1 text-sm">v{plugin.manifest.version}</div>
              </div>
              <div className="rounded-md border px-3 py-2">
                <div className="text-muted-foreground text-xs font-medium">加载状态</div>
                <div className="mt-1 text-sm">{getPluginStatusLabel(plugin)}</div>
              </div>
              <div className="rounded-md border px-3 py-2">
                <div className="text-muted-foreground text-xs font-medium">安装路径</div>
                <div className="mt-1 break-words text-sm">{plugin.path}</div>
              </div>
            </div>

            <div className="space-y-2">
              <div className="text-sm font-medium">失败原因</div>
              <ScrollArea className="max-h-[min(42vh,20rem)] rounded-md border bg-muted/30 p-3">
                <pre className="whitespace-pre-wrap break-words text-sm leading-relaxed">
                  {plugin.load_error?.trim() || '运行时未返回具体失败原因'}
                </pre>
              </ScrollArea>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}

// ---- PluginDocumentFloatingPanel ----

type PluginDocumentMode = 'readme' | 'changelog'

interface PluginDocumentPanelPosition {
  left: number
  top: number
}

const DOCUMENT_PANEL_WIDTH = 560
const DOCUMENT_PANEL_HEIGHT = 620
const DOCUMENT_PANEL_MARGIN = 16

function clampPanelValue(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max)
}

function getInitialDocumentPanelPosition(): PluginDocumentPanelPosition {
  if (typeof window === 'undefined') {
    return { left: 320, top: 120 }
  }

  return {
    left: Math.max(DOCUMENT_PANEL_MARGIN, window.innerWidth - DOCUMENT_PANEL_WIDTH - 32),
    top: 112,
  }
}

interface PluginDocumentFloatingPanelProps {
  plugin: InstalledPlugin
  onClose: () => void
}

export function PluginDocumentFloatingPanel({ plugin, onClose }: PluginDocumentFloatingPanelProps) {
  const [mode, setMode] = useState<PluginDocumentMode>('readme')
  const [readme, setReadme] = useState('')
  const [changelog, setChangelog] = useState(plugin.changelog ?? '')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [dragging, setDragging] = useState(false)
  const [position, setPosition] = useState<PluginDocumentPanelPosition>(getInitialDocumentPanelPosition)
  const panelRef = useRef<HTMLDivElement | null>(null)
  const dragRef = useRef<{
    pointerId?: number
    offsetX: number
    offsetY: number
  } | null>(null)

  useEffect(() => {
    let cancelled = false

    async function loadDocument() {
      setLoading(true)
      setError('')
      try {
        if (mode === 'readme') {
          const content = await getLocalPluginReadme(plugin.id)
          if (!cancelled) {
            setReadme(content)
          }
          return
        }

        const localChangelog = plugin.changelog?.trim()
          ? plugin.changelog
          : await getLocalPluginChangelog(plugin.id)
        if (!cancelled) {
          setChangelog(localChangelog ?? '')
        }
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError instanceof Error ? loadError.message : '文档加载失败')
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }

    void loadDocument()

    return () => {
      cancelled = true
    }
  }, [mode, plugin.changelog, plugin.id])

  const movePanel = (clientX: number, clientY: number) => {
    const dragState = dragRef.current
    if (!dragState) {
      return
    }

    const panelRect = panelRef.current?.getBoundingClientRect()
    const panelWidth = panelRect?.width ?? DOCUMENT_PANEL_WIDTH
    const panelHeight = panelRect?.height ?? DOCUMENT_PANEL_HEIGHT
    const maxLeft = Math.max(
      DOCUMENT_PANEL_MARGIN,
      window.innerWidth - DOCUMENT_PANEL_MARGIN - panelWidth
    )
    const maxTop = Math.max(
      DOCUMENT_PANEL_MARGIN,
      window.innerHeight - DOCUMENT_PANEL_MARGIN - panelHeight
    )
    setPosition({
      left: clampPanelValue(clientX - dragState.offsetX, DOCUMENT_PANEL_MARGIN, maxLeft),
      top: clampPanelValue(clientY - dragState.offsetY, DOCUMENT_PANEL_MARGIN, maxTop),
    })
  }

  const startDrag = (clientX: number, clientY: number, pointerId?: number) => {
    const rect = panelRef.current?.getBoundingClientRect()
    if (!rect) {
      return
    }

    dragRef.current = {
      pointerId,
      offsetX: clientX - rect.left,
      offsetY: clientY - rect.top,
    }
    setDragging(true)
  }

  useEffect(() => {
    if (!dragging) {
      return
    }

    const handleMouseMove = (event: MouseEvent) => {
      if (dragRef.current?.pointerId !== undefined) {
        return
      }
      movePanel(event.clientX, event.clientY)
    }
    const handleMouseUp = () => {
      if (dragRef.current?.pointerId !== undefined) {
        return
      }
      dragRef.current = null
      setDragging(false)
    }

    window.addEventListener('mousemove', handleMouseMove)
    window.addEventListener('mouseup', handleMouseUp)
    return () => {
      window.removeEventListener('mousemove', handleMouseMove)
      window.removeEventListener('mouseup', handleMouseUp)
    }
  }, [dragging])

  const handlePointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    if (event.button !== 0 || dragRef.current) {
      return
    }

    startDrag(event.clientX, event.clientY, event.pointerId)
    event.currentTarget.setPointerCapture(event.pointerId)
  }

  const handlePointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
    const dragState = dragRef.current
    if (!dragState || dragState.pointerId !== event.pointerId) {
      return
    }

    movePanel(event.clientX, event.clientY)
  }

  const endDrag = (event: React.PointerEvent<HTMLDivElement>) => {
    if (dragRef.current?.pointerId === event.pointerId) {
      dragRef.current = null
      setDragging(false)
      if (event.currentTarget.hasPointerCapture(event.pointerId)) {
        event.currentTarget.releasePointerCapture(event.pointerId)
      }
    }
  }

  const handleMouseDown = (event: React.MouseEvent<HTMLDivElement>) => {
    if (event.button !== 0 || dragRef.current) {
      return
    }

    startDrag(event.clientX, event.clientY)
  }

  const content = mode === 'readme' ? readme : changelog
  const panelStyle = {
    left: position.left,
    top: position.top,
  } satisfies CSSProperties

  const panel = (
    <div
      ref={panelRef}
      data-dashboard-floating-content="true"
      className="fixed z-50 w-[min(calc(100vw-2rem),35rem)] overflow-hidden rounded-md border bg-background shadow-2xl"
      style={panelStyle}
    >
      <div
        className={`flex touch-none select-none items-center gap-2 border-b bg-muted/70 px-3 py-2 ${
          dragging ? 'cursor-grabbing' : 'cursor-grab'
        }`}
        onPointerCancel={endDrag}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={endDrag}
        onMouseDown={handleMouseDown}
      >
        <GripHorizontal className="text-muted-foreground h-4 w-4 shrink-0" />
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-semibold">插件文档</div>
          <div className="text-muted-foreground truncate text-xs">{plugin.manifest.name}</div>
        </div>
        <div
          className="flex shrink-0 items-center gap-1"
          onPointerDown={(event) => event.stopPropagation()}
        >
          <Button
            type="button"
            variant={mode === 'readme' ? 'default' : 'outline'}
            size="sm"
            className="h-8"
            onClick={() => setMode('readme')}
          >
            <BookOpen className="mr-1.5 h-3.5 w-3.5" />
            README
          </Button>
          <Button
            type="button"
            variant={mode === 'changelog' ? 'default' : 'outline'}
            size="sm"
            className="h-8"
            onClick={() => setMode('changelog')}
          >
            <FileText className="mr-1.5 h-3.5 w-3.5" />
            更新日志
          </Button>
          <Button type="button" variant="ghost" size="icon" className="h-8 w-8" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>
      </div>

      <div className="p-3">
        {loading ? (
          <div className="text-muted-foreground flex h-64 items-center justify-center gap-2 text-sm">
            <Loader2 className="h-4 w-4 animate-spin" />
            正在加载文档
          </div>
        ) : error ? (
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        ) : content ? (
          <ScrollArea className="h-[min(62vh,31rem)] pr-4">
            <MarkdownRenderer content={content} />
          </ScrollArea>
        ) : (
          <div className="text-muted-foreground flex h-64 items-center justify-center rounded-md border border-dashed text-sm">
            {mode === 'readme' ? '暂无 README' : '暂无更新日志'}
          </div>
        )}
      </div>
    </div>
  )

  if (typeof document === 'undefined') {
    return panel
  }

  return createPortal(panel, document.body)
}