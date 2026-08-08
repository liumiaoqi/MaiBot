import { useState, useCallback, useEffect, useMemo, useRef } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'

import { cn } from '@/lib/utils'
import { settingsRegistry } from '@/settings-registry/settings-registry'
import { projectToSearchItems } from '@/settings-registry/project'
import { getSearchScore } from '@/settings-registry/pinyin-search'
import { highlightMatch } from '@/settings-registry/search-highlight'
import { registerManualEntries } from '@/settings-registry/manual'
import { registerDynamicEntries } from '@/settings-registry/dynamic'
import { buildEntriesFromSchema } from '@/settings-registry/builder'
import { getBotConfigSchema, getModelConfigSchema } from '@/lib/config-api'
import { getPromptCatalog } from '@/lib/prompt-api'
import { listPacks } from '@/lib/pack-api'
import type { SearchItem } from '@/types/search-item'

const RECENT_SEARCH_ROUTES_KEY = 'maibot-search-recent-routes'
const MAX_RECENT_SEARCH_ROUTES = 8
const MAX_RESULTS = 80
const DEBOUNCE_MS = 100

interface SearchDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

/** 加载最近搜索路由 */
function loadRecentSearchRoutes(): string[] {
  if (typeof window === 'undefined') return []
  const stored = localStorage.getItem(RECENT_SEARCH_ROUTES_KEY)
  if (!stored) return []
  try {
    const parsed = JSON.parse(stored)
    return Array.isArray(parsed)
      ? parsed.filter((p): p is string => typeof p === 'string').slice(0, MAX_RECENT_SEARCH_ROUTES)
      : []
  } catch {
    return []
  }
}

/** 保存最近搜索路由 */
function saveRecentSearchRoutes(paths: string[]): void {
  localStorage.setItem(RECENT_SEARCH_ROUTES_KEY, JSON.stringify(paths.slice(0, MAX_RECENT_SEARCH_ROUTES)))
}

/** 确保注册表已初始化（schema 自动 + 手动 + 动态） */
async function ensureRegistryInitialized(): Promise<void> {
  // 手动登记（同步）
  registerManualEntries()

  // schema 自动登记（并行加载，allSettled 容错）
  const [botResult, modelResult] = await Promise.allSettled([
    getBotConfigSchema(),
    getModelConfigSchema(),
  ])

  if (botResult.status === 'fulfilled') {
    const entries = buildEntriesFromSchema(botResult.value, 'bot', '/config/bot')
    settingsRegistry.registerAll(entries)
  }
  if (modelResult.status === 'fulfilled') {
    const entries = buildEntriesFromSchema(modelResult.value, 'model', '/config/model')
    settingsRegistry.registerAll(entries)
  }

  // 动态登记（异步，不阻塞——错误不静默）
  registerDynamicEntries(
    async () => {
      const catalog = await getPromptCatalog()
      return Object.values(catalog.files).flat().map((f) => ({
        name: f.name,
        description: f.display_name,
      }))
    },
    async () => {
      const result = await listPacks()
      return result.packs.map((p) => ({
        id: p.id,
        name: p.name,
        description: p.description,
      }))
    }
  ).catch((e) => {
    console.error('动态登记失败:', e)
  })
}

export function SearchDialog({ open, onOpenChange }: SearchDialogProps) {
  const [searchQuery, setSearchQuery] = useState('')
  const [debouncedQuery, setDebouncedQuery] = useState('')
  const [selectedIndex, setSelectedIndex] = useState(0)
  const [registryReady, setRegistryReady] = useState(false)
  const [recentSearchRoutes, setRecentSearchRoutes] = useState<string[]>(loadRecentSearchRoutes)
  const inputRef = useRef<HTMLInputElement>(null)
  const navigate = useNavigate()
  const { i18n, t } = useTranslation()

  // 打开时聚焦输入框
  useEffect(() => {
    if (!open) return
    const frameId = window.requestAnimationFrame(() => {
      inputRef.current?.focus()
    })
    return () => window.cancelAnimationFrame(frameId)
  }, [open])

  // 打开时初始化注册表
  useEffect(() => {
    if (!open || registryReady) return

    let cancelled = false
    ensureRegistryInitialized().then(() => {
      if (!cancelled) setRegistryReady(true)
    }).catch(() => {
      if (!cancelled) setRegistryReady(true)
    })

    return () => { cancelled = true }
  }, [open, registryReady, i18n.language])

  // 防抖
  useEffect(() => {
    const timer = window.setTimeout(() => {
      setDebouncedQuery(searchQuery)
    }, DEBOUNCE_MS)
    return () => window.clearTimeout(timer)
  }, [searchQuery])

  // 从注册表获取所有条目并投影为 SearchItem
  const allSearchItems: SearchItem[] = useMemo(() => {
    if (!registryReady) return []
    const entries = settingsRegistry.getAll()
    return projectToSearchItems(entries, i18n.language)
  }, [registryReady, i18n.language])

  // 最近搜索条目
  const recentSearchItems = useMemo<SearchItem[]>(() => {
    const itemMap = new Map(allSearchItems.map((item) => [item.path, item]))
    return recentSearchRoutes
      .map((path) => itemMap.get(path))
      .filter((item): item is SearchItem => item !== undefined)
      .map((item) => ({
        ...item,
        id: `recent:${item.path}`,
        category: t('search.recent'),
      }))
  }, [recentSearchRoutes, allSearchItems, t])

  // 搜索结果：过滤 + 排序 + 去重 + 截断
  const filteredItems = useMemo(() => {
    const query = debouncedQuery.trim().toLowerCase()
    if (!query) {
      // 空查询：最近搜索 + 全部条目
      return [...recentSearchItems, ...allSearchItems]
        .filter((item, index, all) => all.findIndex((c) => c.path === item.path) === index)
        .slice(0, MAX_RESULTS)
    }

    // 有查询：搜索匹配 + 打分排序
    const scored = [...allSearchItems]
      .map((item) => {
        const keywords = item.keywords.split(' ')
        const result = getSearchScore(item.title, keywords, query)
        return { item, score: result.score, matched: result.matched }
      })
      .filter((r) => r.matched)

    return scored
      .sort((a, b) => {
        const scoreDiff = b.score - a.score
        return scoreDiff === 0 ? a.item.title.localeCompare(b.item.title) : scoreDiff
      })
      .map((r) => r.item)
      .filter((item, index, all) => all.findIndex((c) => c.path === item.path) === index)
      .slice(0, MAX_RESULTS)
  }, [debouncedQuery, allSearchItems, recentSearchItems])

  // 导航
  const handleNavigate = useCallback((path: string) => {
    const nextRoutes = [path, ...recentSearchRoutes.filter((p) => p !== path)]
      .slice(0, MAX_RECENT_SEARCH_ROUTES)
    setRecentSearchRoutes(nextRoutes)
    saveRecentSearchRoutes(nextRoutes)
    navigate({ to: path })
    onOpenChange(false)
    setSearchQuery('')
    setDebouncedQuery('')
    setSelectedIndex(0)
  }, [navigate, onOpenChange, recentSearchRoutes])

  // 键盘导航
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        onOpenChange(false)
        return
      }
      if (e.key === 'ArrowDown') {
        e.preventDefault()
        if (filteredItems.length === 0) return
        setSelectedIndex((prev) => (prev + 1) % filteredItems.length)
      } else if (e.key === 'ArrowUp') {
        e.preventDefault()
        if (filteredItems.length === 0) return
        setSelectedIndex((prev) => (prev - 1 + filteredItems.length) % filteredItems.length)
      } else if (e.key === 'Home') {
        e.preventDefault()
        setSelectedIndex(0)
      } else if (e.key === 'End') {
        e.preventDefault()
        setSelectedIndex(Math.max(0, filteredItems.length - 1))
      } else if (e.key === 'Enter' && filteredItems[selectedIndex]) {
        e.preventDefault()
        handleNavigate(filteredItems[selectedIndex].path)
      }
    },
    [filteredItems, selectedIndex, handleNavigate, onOpenChange]
  )

  if (!open) return null

  const query = debouncedQuery.trim()

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/50 pt-[15vh]"
      onClick={() => onOpenChange(false)}
    >
      <div
        className="w-full max-w-2xl overflow-hidden rounded-lg border border-border bg-background shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 搜索输入区 */}
        <div className="relative border-b px-4 pt-4 pb-3">
          <input
            ref={inputRef}
            type="text"
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value)
              setSelectedIndex(0)
            }}
            onKeyDown={handleKeyDown}
            placeholder={t('search.placeholder')}
            className="h-12 w-full pl-10 text-base outline-none placeholder:text-muted-foreground"
          />
          <svg
            className="absolute left-6 top-1/2 h-5 w-5 -translate-y-1/2 text-muted-foreground"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
        </div>

        {/* 搜索结果区 */}
        <div className="max-h-[400px] overflow-y-auto">
          {filteredItems.length > 0 ? (
            <div className="space-y-1.5 p-2">
              {filteredItems.map((item, index) => (
                <button
                  key={item.id}
                  onClick={() => handleNavigate(item.path)}
                  onMouseEnter={() => setSelectedIndex(index)}
                  title={`${item.title} · ${item.description} · ${item.path}`}
                  className={cn(
                    'w-full flex items-center gap-3 rounded-md px-3 py-2.5 text-left transition-colors',
                    index === selectedIndex
                      ? 'bg-accent text-accent-foreground'
                      : 'hover:bg-accent/50'
                  )}
                >
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm font-medium">
                      {highlightMatch(item.title, query)}
                    </div>
                    <div className="truncate text-xs text-muted-foreground">
                      {item.description}
                    </div>
                  </div>
                  <div className="max-w-28 shrink-0 truncate rounded bg-muted px-2 py-1 text-xs text-muted-foreground">
                    {item.category}
                  </div>
                </button>
              ))}
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <p className="text-sm text-muted-foreground">
                {searchQuery ? t('search.noResults') : t('search.startSearch')}
              </p>
            </div>
          )}
        </div>

        {/* 底部快捷键提示 */}
        <div className="border-t px-4 py-3 flex items-center justify-between text-xs text-muted-foreground">
          <div className="flex items-center gap-4">
            <span className="flex items-center gap-1">
              <kbd className="rounded border px-1">↑</kbd>
              <kbd className="rounded border px-1">↓</kbd>
              {t('search.navigate')}
            </span>
            <span className="flex items-center gap-1">
              <kbd className="rounded border px-1">↵</kbd>
              {t('search.select')}
            </span>
            <span className="flex items-center gap-1">
              <kbd className="rounded border px-1">Esc</kbd>
              {t('search.close')}
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}