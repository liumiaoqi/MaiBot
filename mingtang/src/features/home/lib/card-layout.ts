/**
 * 首页卡片布局纯函数与常量（R4 债清理 P1——从 home-card-manager.tsx 机械拆分）
 *
 * 职责：localStorage 布局持久化 + 12 列栅格自适应宽度 + 行打包。
 * 零 React 依赖（仅类型引用 ReactNode），纯函数可独立单测。
 */
import type { ReactNode } from 'react'

import type { PluginHomeCardWidth } from '@/lib/plugin-api'

export const HOME_CARD_LAYOUT_STORAGE_KEY = 'maibot-home-card-layout-v1'
export const HOME_CARD_LOW_ROW_HEIGHT = 236
export const HOME_CARD_HIGH_ROW_HEIGHT = 360
export const HOME_CARD_GRID_GAP = 16

export type HomeCardSource = 'builtin' | 'plugin'
export type HomeCardRowMode = 'low' | 'high'

export interface HomeCardDefinition {
  id: string
  title: string
  description?: string
  width?: PluginHomeCardWidth
  source: HomeCardSource
  render: () => ReactNode
}

export interface HomeCardLayout {
  order: string[]
  hidden: string[]
  rowModes: Record<string, HomeCardRowMode>
}

export function loadHomeCardLayout(): HomeCardLayout {
  if (typeof window === 'undefined') {
    return { order: [], hidden: [], rowModes: {} }
  }

  try {
    const parsed = JSON.parse(localStorage.getItem(HOME_CARD_LAYOUT_STORAGE_KEY) || '{}')
    return {
      order: Array.isArray(parsed.order) ? parsed.order.filter((item: unknown): item is string => typeof item === 'string') : [],
      hidden: Array.isArray(parsed.hidden) ? parsed.hidden.filter((item: unknown): item is string => typeof item === 'string') : [],
      rowModes: normalizeRowModes(parsed.rowModes),
    }
  } catch {
    return { order: [], hidden: [], rowModes: {} }
  }
}

export function saveHomeCardLayout(layout: HomeCardLayout): void {
  localStorage.setItem(HOME_CARD_LAYOUT_STORAGE_KEY, JSON.stringify(layout))
}

export function cardWidthClass(width: PluginHomeCardWidth | undefined): string {
  switch (width) {
    case 'small':
      return 'lg:col-span-2'
    case 'medium':
      return 'lg:col-span-3'
    case 'large':
      return 'lg:col-span-5'
    case 'wide':
      return 'lg:col-span-7'
    case 'full':
      return 'lg:col-span-10'
    default:
      return 'lg:col-span-3'
  }
}

export function normalizeRowModes(value: unknown): Record<string, HomeCardRowMode> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return {}
  return Object.entries(value).reduce<Record<string, HomeCardRowMode>>((result, [key, mode]) => {
    if (/^\d+$/.test(key) && (mode === 'low' || mode === 'high')) {
      result[key] = mode
    }
    return result
  }, {})
}

export function rowModesEqual(left: Record<string, HomeCardRowMode>, right: Record<string, HomeCardRowMode>): boolean {
  const leftKeys = Object.keys(left)
  const rightKeys = Object.keys(right)
  return leftKeys.length === rightKeys.length && leftKeys.every((key) => left[key] === right[key])
}

export function defaultRowMode(rowIndex: number): HomeCardRowMode {
  return rowIndex === 0 ? 'low' : 'high'
}

export function rowHeight(mode: HomeCardRowMode): number {
  return mode === 'high' ? HOME_CARD_HIGH_ROW_HEIGHT : HOME_CARD_LOW_ROW_HEIGHT
}

export function cardWidthColumns(width: PluginHomeCardWidth | undefined): number {
  switch (width) {
    case 'small':
      return 2
    case 'medium':
      return 3
    case 'large':
      return 5
    case 'wide':
      return 7
    case 'full':
      return 10
    default:
      return 3
  }
}

export function shrinkCardWidthOneStep(width: PluginHomeCardWidth | undefined): PluginHomeCardWidth | undefined {
  switch (width) {
    case 'full':
      return 'wide'
    case 'wide':
      return 'large'
    case 'large':
      return 'medium'
    case 'medium':
      return 'small'
    case 'small':
    default:
      return width
  }
}

export function buildAdaptiveCardWidths(cards: HomeCardDefinition[]): Map<string, PluginHomeCardWidth | undefined> {
  const widths = new Map<string, PluginHomeCardWidth | undefined>()
  let currentRowColumns = 0

  for (const card of cards) {
    const preferredWidth = card.width
    const preferredColumns = cardWidthColumns(preferredWidth)
    const remainingColumns = 10 - currentRowColumns
    let renderedWidth = preferredWidth
    let renderedColumns = preferredColumns

    if (currentRowColumns > 0 && preferredColumns > remainingColumns) {
      const shrunkWidth = shrinkCardWidthOneStep(preferredWidth)
      const shrunkColumns = cardWidthColumns(shrunkWidth)
      if (shrunkColumns <= remainingColumns) {
        renderedWidth = shrunkWidth
        renderedColumns = shrunkColumns
      } else {
        currentRowColumns = 0
      }
    }

    widths.set(card.id, renderedWidth)
    currentRowColumns += renderedColumns
    if (currentRowColumns >= 10) {
      currentRowColumns = 0
    }
  }

  return widths
}

export function buildCardRows(
  cards: HomeCardDefinition[],
  widths: Map<string, PluginHomeCardWidth | undefined>
): HomeCardDefinition[][] {
  const rows: HomeCardDefinition[][] = []
  let currentRow: HomeCardDefinition[] = []
  let currentRowColumns = 0

  for (const card of cards) {
    const columns = cardWidthColumns(widths.get(card.id) ?? card.width)
    if (currentRow.length > 0 && currentRowColumns + columns > 10) {
      rows.push(currentRow)
      currentRow = []
      currentRowColumns = 0
    }

    currentRow.push(card)
    currentRowColumns += columns
    if (currentRowColumns >= 10) {
      rows.push(currentRow)
      currentRow = []
      currentRowColumns = 0
    }
  }

  if (currentRow.length > 0) {
    rows.push(currentRow)
  }
  return rows
}
