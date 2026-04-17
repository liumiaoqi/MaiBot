import { useState, useCallback, useEffect, useMemo, useRef } from 'react'
import { Search } from 'lucide-react'
import { useNavigate } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'
import type { LucideProps } from 'lucide-react'

import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { ShortcutKbd } from '@/components/ui/kbd'
import { menuSections } from '@/components/layout/constants'
import { registeredRoutePaths } from '@/router'
import { cn } from '@/lib/utils'

interface SearchDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

interface SearchItem {
  icon: React.ComponentType<LucideProps>
  title: string
  description: string
  path: string
  category: string
}

export function SearchDialog({ open, onOpenChange }: SearchDialogProps) {
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedIndex, setSelectedIndex] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)
  const navigate = useNavigate()
  const { t } = useTranslation()

  useEffect(() => {
    if (!open) {
      return
    }

    const frameId = window.requestAnimationFrame(() => {
      inputRef.current?.focus()
    })

    return () => window.cancelAnimationFrame(frameId)
  }, [open])

  const searchItems: SearchItem[] = useMemo(
    () =>
      menuSections.flatMap((section) =>
        section.items
          .filter((item) => registeredRoutePaths.has(item.path))
          .map((item) => ({
            icon: item.icon,
            title: t(item.label),
            description: item.searchDescription ? t(item.searchDescription) : item.path,
            path: item.path,
            category: t(section.title),
          }))
      ),
    [t]
  )

  // 过滤搜索结果
  const filteredItems = searchItems.filter(
    (item) =>
      item.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      item.description.toLowerCase().includes(searchQuery.toLowerCase()) ||
      item.category.toLowerCase().includes(searchQuery.toLowerCase())
  )

  // 导航到页面
  const handleNavigate = useCallback((path: string) => {
    navigate({ to: path })
    onOpenChange(false)
    // 在导航后重置状态
    setSearchQuery('')
    setSelectedIndex(0)
  }, [navigate, onOpenChange])

  // 键盘导航
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'ArrowDown') {
        e.preventDefault()
        setSelectedIndex((prev) => (prev + 1) % filteredItems.length)
      } else if (e.key === 'ArrowUp') {
        e.preventDefault()
        setSelectedIndex((prev) => (prev - 1 + filteredItems.length) % filteredItems.length)
      } else if (e.key === 'Enter' && filteredItems[selectedIndex]) {
        e.preventDefault()
        handleNavigate(filteredItems[selectedIndex].path)
      }
    },
    [filteredItems, selectedIndex, handleNavigate]
  )

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl p-0 gap-0" confirmOnEnter>
        <DialogHeader className="px-4 pt-4 pb-0">
          <DialogTitle className="sr-only">{t('search.title')}</DialogTitle>
          <div className="relative">
            <Search className="absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-muted-foreground" />
            <Input
              ref={inputRef}
              value={searchQuery}
              onChange={(e) => {
                setSearchQuery(e.target.value)
                setSelectedIndex(0)
              }}
              onKeyDown={handleKeyDown}
              placeholder={t('search.placeholder')}
              className="h-12 pl-11 text-base border-0 focus-visible:ring-0 shadow-none"
            />
          </div>
        </DialogHeader>

        <div className="border-t">
          <DialogBody className="h-100" viewportClassName="px-0">
            {filteredItems.length > 0 ? (
              <div className="p-2">
                {filteredItems.map((item, index) => {
                  const Icon = item.icon
                  return (
                    <button
                      key={item.path}
                      onClick={() => handleNavigate(item.path)}
                      onMouseEnter={() => setSelectedIndex(index)}
                      className={cn(
                        'w-full flex items-center gap-3 px-3 py-2.5 rounded-md text-left transition-colors',
                        index === selectedIndex
                          ? 'bg-accent text-accent-foreground'
                          : 'hover:bg-accent/50'
                      )}
                    >
                      <Icon className="h-5 w-5 shrink-0" />
                      <div className="flex-1 min-w-0">
                        <div className="font-medium text-sm">{item.title}</div>
                        <div className="text-xs text-muted-foreground truncate">
                          {item.description}
                        </div>
                      </div>
                      <div className="text-xs text-muted-foreground px-2 py-1 bg-muted rounded">
                        {item.category}
                      </div>
                    </button>
                  )
                })}
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center py-12 text-center">
                <Search className="h-12 w-12 text-muted-foreground/50 mb-4" />
                <p className="text-sm text-muted-foreground">
                  {searchQuery ? t('search.noResults') : t('search.startSearch')}
                </p>
              </div>
            )}
          </DialogBody>
        </div>

        <div className="border-t px-4 py-3 flex items-center justify-between text-xs text-muted-foreground">
          <div className="flex items-center gap-4">
            <span className="flex items-center gap-1">
              <ShortcutKbd size="sm" keys={['up']} />
              <ShortcutKbd size="sm" keys={['down']} />
              {t('search.navigate')}
            </span>
            <span className="flex items-center gap-1">
              <ShortcutKbd size="sm" keys={['enter']} />
              {t('search.select')}
            </span>
            <span className="flex items-center gap-1">
              <ShortcutKbd size="sm" keys={['esc']} />
              {t('search.close')}
            </span>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
