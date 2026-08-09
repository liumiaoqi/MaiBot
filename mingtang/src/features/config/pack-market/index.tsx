import { useState, useMemo, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'
import { PageShell } from '@/components/biz/page-shell'
import { Search, Heart, Package } from 'lucide-react'
import { listPacks, type ListPacksResponse } from '@/lib/pack-api'

type SortMode = 'latest' | 'downloads' | 'likes'

/** 配置模板市场页（/config/pack-market）——搜索 + 排序 + 卡片网格 + 分页 */
export function PackMarketPage() {
  const { t } = useTranslation()
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [sort, setSort] = useState<SortMode>('latest')
  const [page, setPage] = useState(1)
  const pageSize = 12

  // 300ms 防抖
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search), 300)
    return () => clearTimeout(timer)
  }, [search])

  const sortMap: Record<SortMode, { sort_by: 'created_at' | 'downloads' | 'likes'; sort_order: 'asc' | 'desc' }> = {
    latest: { sort_by: 'created_at', sort_order: 'desc' },
    downloads: { sort_by: 'downloads', sort_order: 'desc' },
    likes: { sort_by: 'likes', sort_order: 'desc' },
  }

  const { data, isLoading, isError } = useQuery({
    queryKey: ['api', 'packs', { page, sort, search: debouncedSearch }],
    queryFn: () => listPacks({ page, page_size: pageSize, search: debouncedSearch, ...sortMap[sort] }),
  })

  const packs = useMemo(() => {
    return (data as ListPacksResponse)?.packs ?? []
  }, [data])

  const total = useMemo(() => {
    return (data as ListPacksResponse)?.total ?? 0
  }, [data])

  const totalPages = Math.ceil(total / pageSize)

  return (
    <PageShell title={t('sidebar.menu.configTemplate')} breadcrumb={[t('sidebar.groups.botConfig')]}>
      <div className="space-y-4">
        {/* 搜索 + 排序 */}
        <div className="flex items-center gap-2">
          <div className="relative flex-1 max-w-xs">
            <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="搜索配置模板..."
              className="w-full pl-8 pr-3 py-1.5 text-sm rounded-md border border-border bg-background"
              data-testid="pack-search"
            />
          </div>
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value as SortMode)}
            className="px-2 py-1.5 text-sm rounded border border-border bg-background"
            data-testid="pack-sort"
          >
            <option value="latest">最新</option>
            <option value="downloads">下载最多</option>
            <option value="likes">最受欢迎</option>
          </select>
        </div>

        {/* 卡片网格 */}
        {isLoading ? (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4" data-testid="pack-skeleton">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="h-48 rounded-md border animate-pulse bg-muted/50" />
            ))}
          </div>
        ) : isError ? (
          <div className="text-center py-8 text-destructive" data-testid="pack-error">
            加载失败，请重试
          </div>
        ) : packs.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground" data-testid="pack-empty">
            <Package className="h-12 w-12 mx-auto mb-2 opacity-50" />
            <p>暂无配置模板</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4" data-testid="pack-grid">
            {packs.map((pack) => (
              <div
                key={pack.id}
                className="rounded-md border p-4 space-y-2 hover:shadow-md transition-shadow cursor-pointer"
                data-testid={`pack-card-${pack.id}`}
              >
                <div className="flex items-center justify-between">
                  <h3 className="font-semibold" text-foreground>{pack.name}</h3>
                  <span className="text-xs text-muted-foreground">v{pack.version}</span>
                </div>
                <p className="text-sm text-muted-foreground line-clamp-2">{pack.description}</p>
                <div className="flex items-center gap-3 text-xs text-muted-foreground">
                  <span>{pack.provider_count} 厂商</span>
                  <span>{pack.model_count} 模型</span>
                  <span>{pack.task_count} 任务</span>
                </div>
                <div className="flex items-center justify-between pt-2 border-t">
                  <span className="text-xs text-muted-foreground">{pack.author}</span>
                  <div className="flex items-center gap-2 text-xs">
                    <span>{pack.downloads} 下载</span>
                    <span className="flex items-center gap-0.5">
                      <Heart className="h-3 w-3" />
                      {pack.likes}
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* 分页 */}
        {totalPages > 1 && (
          <div className="flex items-center justify-center gap-2" data-testid="pack-pagination">
            <button
              onClick={() => setPage(Math.max(1, page - 1))}
              disabled={page === 1}
              className="px-3 py-1 text-sm rounded border border-border disabled:opacity-50"
              data-testid="pack-prev-page"
            >
              上一页
            </button>
            <span className="text-sm">{page} / {totalPages}</span>
            <button
              onClick={() => setPage(Math.min(totalPages, page + 1))}
              disabled={page === totalPages}
              className="px-3 py-1 text-sm rounded border border-border disabled:opacity-50"
              data-testid="pack-next-page"
            >
              下一页
            </button>
          </div>
        )}
      </div>
    </PageShell>
  )
}
