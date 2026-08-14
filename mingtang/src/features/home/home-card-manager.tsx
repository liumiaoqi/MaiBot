/**
 * 首页卡片管理器（R4 债清理 P1——巨型组件拆分）
 *
 * 编排职责：DndContext 拖拽排序 + 布局 state（localStorage 持久化）+ 编辑模式
 * + 隐藏卡片 Dialog + 控件 portal。
 * 拆分子模块：布局纯函数 lib/card-layout.ts · 插件卡内容 cards/plugin-card-content.tsx
 * · Sortable 包装 cards/sortable-card.tsx。
 */
import {
  closestCenter,
  DndContext,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core'
import {
  arrayMove,
  rectSortingStrategy,
  SortableContext,
  sortableKeyboardCoordinates,
} from '@dnd-kit/sortable'
import { GripVertical, Plus, RotateCcw } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState, type CSSProperties } from 'react'
import { createPortal } from 'react-dom'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { TooltipProvider } from '@/components/ui/tooltip'
import type { PluginHomeCard } from '@/lib/plugin-api'

import { PluginHomeCardView } from './cards/plugin-card-content'
import { SortableHomeCard, stringArraysEqual } from './cards/sortable-card'
import {
  buildAdaptiveCardWidths,
  buildCardRows,
  defaultRowMode,
  loadHomeCardLayout,
  normalizeRowModes,
  rowHeight,
  rowModesEqual,
  saveHomeCardLayout,
  HOME_CARD_GRID_GAP,
  type HomeCardDefinition,
  type HomeCardLayout,
} from './lib/card-layout'

export type { HomeCardDefinition } from './lib/card-layout'

interface HomeCardManagerProps {
  cards: HomeCardDefinition[]
  pluginCards: PluginHomeCard[]
  controlsPortalId?: string
}

export function HomeCardManager({ cards, pluginCards, controlsPortalId }: HomeCardManagerProps) {
  const { t } = useTranslation()
  const [layout, setLayout] = useState<HomeCardLayout>(loadHomeCardLayout)
  const [editing, setEditing] = useState(false)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [controlsContainer, setControlsContainer] = useState<HTMLElement | null>(null)

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
  )

  const pluginDefinitions = useMemo<HomeCardDefinition[]>(
    () =>
      pluginCards.map((card) => ({
        id: card.id,
        title: card.title,
        description: card.description,
        width: card.width,
        source: 'plugin' as const,
        render: () => <PluginHomeCardView card={card} />,
      })),
    [pluginCards]
  )

  const allCards = useMemo(
    () => [...cards, ...pluginDefinitions],
    [cards, pluginDefinitions]
  )
  const cardMap = useMemo(() => new Map(allCards.map((card) => [card.id, card])), [allCards])
  const allCardIds = useMemo(() => allCards.map((card) => card.id), [allCards])

  const updateLayout = useCallback((updater: (current: HomeCardLayout) => HomeCardLayout) => {
    setLayout((current) => {
      const next = updater(current)
      saveHomeCardLayout(next)
      return next
    })
  }, [])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- allCardIds 变化时同步布局（order/hidden/rowModes），setState 仅在布局实际变化时执行（内部有浅比较短路）
    updateLayout((current) => {
      const knownIds = new Set(allCardIds)
      const order = [...current.order.filter((id) => knownIds.has(id)), ...allCardIds.filter((id) => !current.order.includes(id))]
      const hidden = current.hidden.filter((id) => knownIds.has(id))
      const rowModes = normalizeRowModes(current.rowModes)
      if (
        stringArraysEqual(order, current.order)
        && stringArraysEqual(hidden, current.hidden)
        && rowModesEqual(rowModes, current.rowModes)
      ) {
        return current
      }
      return { ...current, order, hidden, rowModes }
    })
  }, [allCardIds, updateLayout])

  useEffect(() => {
    if (!controlsPortalId || typeof document === 'undefined') {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- controlsPortalId 失效时清空容器引用，与外部 DOM 节点同步
      setControlsContainer(null)
      return
    }

    setControlsContainer(document.getElementById(controlsPortalId))
  }, [controlsPortalId])

  const visibleCards = useMemo(
    () =>
      layout.order
        .map((id) => cardMap.get(id))
        .filter((card): card is HomeCardDefinition => card !== undefined && !layout.hidden.includes(card.id)),
    [cardMap, layout.hidden, layout.order]
  )
  const hiddenCards = useMemo(
    () =>
      layout.hidden
        .map((id) => cardMap.get(id))
        .filter((card): card is HomeCardDefinition => card !== undefined),
    [cardMap, layout.hidden]
  )
  const adaptiveCardWidths = useMemo(() => buildAdaptiveCardWidths(visibleCards), [visibleCards])
  const cardRows = useMemo(() => buildCardRows(visibleCards, adaptiveCardWidths), [adaptiveCardWidths, visibleCards])
  const rowModes = useMemo(
    () => cardRows.map((_, index) => layout.rowModes[String(index)] ?? defaultRowMode(index)),
    [cardRows, layout.rowModes]
  )
  const rowControls = useMemo(() => {
    let rowTop = 0
    return rowModes.map((mode, index) => {
      const top = rowTop
      // eslint-disable-next-line react-hooks/immutability -- 累加偏移量是纯计算逻辑（非渲染状态），闭包内局部变量赋值安全
      rowTop += rowHeight(mode) + HOME_CARD_GRID_GAP
      return { index, mode, top }
    })
  }, [rowModes])
  const gridStyle = cardRows.length > 0
    ? ({
      '--home-card-grid-rows': rowModes.map((mode) => `${rowHeight(mode)}px`).join(' '),
    } as CSSProperties)
    : undefined

  const handleDragEnd = useCallback(
    (event: DragEndEvent) => {
      const { active, over } = event
      if (!over || active.id === over.id) return
      updateLayout((current) => {
        const visibleIds = visibleCards.map((card) => card.id)
        const oldIndex = visibleIds.indexOf(String(active.id))
        const newIndex = visibleIds.indexOf(String(over.id))
        if (oldIndex < 0 || newIndex < 0) return current
        const reorderedVisibleIds = arrayMove(visibleIds, oldIndex, newIndex)
        const remainingIds = current.order.filter((id) => !visibleIds.includes(id))
        return { ...current, order: [...reorderedVisibleIds, ...remainingIds] }
      })
    },
    [updateLayout, visibleCards]
  )

  const hideCard = useCallback((id: string) => {
    updateLayout((current) => ({ ...current, hidden: Array.from(new Set([...current.hidden, id])) }))
  }, [updateLayout])

  const restoreCard = useCallback((id: string) => {
    updateLayout((current) => ({ ...current, hidden: current.hidden.filter((item) => item !== id) }))
  }, [updateLayout])

  const toggleRowMode = useCallback((rowIndex: number) => {
    updateLayout((current) => {
      const key = String(rowIndex)
      const currentMode = current.rowModes[key] ?? defaultRowMode(rowIndex)
      return {
        ...current,
        rowModes: {
          ...current.rowModes,
          [key]: currentMode === 'high' ? 'low' : 'high',
        },
      }
    })
  }, [updateLayout])

  const resetLayout = useCallback(() => {
    updateLayout(() => ({
      order: allCardIds,
      hidden: [],
      rowModes: {},
    }))
  }, [allCardIds, updateLayout])

  const controls = (
    <div className="flex flex-wrap items-center justify-end gap-2">
      <Button variant="outline" size="sm" onClick={resetLayout} className="gap-2">
        <RotateCcw className="h-4 w-4" />
        {t('home.cards.reset')}
      </Button>
      <Button variant="outline" size="sm" onClick={() => setDialogOpen(true)} className="gap-2">
        <Plus className="h-4 w-4" />
        {t('home.cards.add')}
      </Button>
      <Button variant={editing ? 'default' : 'outline'} size="sm" onClick={() => setEditing((value) => !value)} className="gap-2">
        <GripVertical className="h-4 w-4" />
        {editing ? t('home.cards.done') : t('home.cards.edit')}
      </Button>
    </div>
  )

  return (
    <TooltipProvider>
      <div className="space-y-3">
        {controlsPortalId && controlsContainer ? createPortal(controls, controlsContainer) : null}
        {!controlsPortalId && controls}

        <div className="relative">
          {editing && rowControls.length > 0 && (
            <div className="pointer-events-none absolute inset-x-0 top-0 z-30 hidden lg:block">
              {rowControls.map((row) => (
                <Button
                  key={row.index}
                  type="button"
                  variant={row.mode === 'high' ? 'default' : 'outline'}
                  size="sm"
                  className="pointer-events-auto absolute left-2 h-7 bg-background/95 px-2 text-xs shadow-sm backdrop-blur"
                  style={{ top: row.top + 8 }}
                  onClick={() => toggleRowMode(row.index)}
                >
                  {row.mode === 'high' ? t('home.cards.row.high') : t('home.cards.row.low')}
                </Button>
              ))}
            </div>
          )}

          <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
            <SortableContext items={visibleCards.map((card) => card.id)} strategy={rectSortingStrategy}>
              <div
                data-home-summary-cards="true"
                data-home-row-sizing="custom"
                className="grid grid-cols-1 items-stretch gap-4 lg:grid-cols-10"
                style={gridStyle}
              >
                {visibleCards.map((card) => (
                  <SortableHomeCard
                    key={card.id}
                    card={card}
                    displayWidth={adaptiveCardWidths.get(card.id)}
                    editing={editing}
                    onHide={hideCard}
                  />
                ))}
              </div>
            </SortableContext>
          </DndContext>
        </div>

        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>{t('home.cards.dialog.title')}</DialogTitle>
              <DialogDescription>{t('home.cards.dialog.description')}</DialogDescription>
            </DialogHeader>
            <DialogBody viewportClassName="max-h-[62vh]">
              <div className="space-y-5 pr-1">
                <div className="space-y-2">
                  <div className="text-sm font-medium">{t('home.cards.dialog.hiddenCards')}</div>
                  {hiddenCards.length === 0 ? (
                    <div className="rounded-md border border-dashed p-3 text-sm text-muted-foreground">
                      {t('home.cards.dialog.noHiddenCards')}
                    </div>
                  ) : (
                    <div className="space-y-2">
                      {hiddenCards.map((card) => (
                        <div key={card.id} className="flex items-center justify-between gap-3 rounded-md border p-3">
                          <div className="min-w-0">
                            <div className="truncate text-sm font-medium">{card.title}</div>
                            {card.description && <div className="truncate text-xs text-muted-foreground">{card.description}</div>}
                          </div>
                          <Button variant="outline" size="sm" onClick={() => restoreCard(card.id)}>
                            {t('home.cards.dialog.restore')}
                          </Button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

              </div>
            </DialogBody>
            <DialogFooter>
              <Button variant="outline" onClick={resetLayout} className="mr-auto gap-2">
                <RotateCcw className="h-4 w-4" />
                {t('home.cards.dialog.reset')}
              </Button>
              <Button variant="outline" onClick={() => setDialogOpen(false)}>
                {t('home.cards.dialog.cancel')}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    </TooltipProvider>
  )
}
