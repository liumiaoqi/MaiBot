import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Loader2, Play, RefreshCw, RotateCcw, Search } from 'lucide-react'

import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Textarea } from '@/components/ui/textarea'
import { useToast } from '@/hooks/use-toast'
import {
  getMemoryEpisode,
  getMemoryEpisodes,
  getMemoryEpisodeStatus,
  processMemoryEpisodePending,
  rebuildMemoryEpisodes,
  type MemoryEpisodeDetailPayload,
  type MemoryEpisodeItemPayload,
  type MemoryEpisodeParagraphPayload,
  type MemoryEpisodeStatusPayload,
} from '@/lib/memory-api'
import { cn } from '@/lib/utils'

function formatMemoryTime(timestamp?: number | null): string {
  if (!timestamp) {
    return '-'
  }
  const normalized = timestamp > 1_000_000_000_000 ? timestamp : timestamp * 1000
  const value = new Date(normalized)
  if (Number.isNaN(value.getTime())) {
    return '-'
  }
  return value.toLocaleString('zh-CN', {
    hour12: false,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function parseOptionalNumber(value: string): number | undefined {
  const trimmed = value.trim()
  if (!trimmed) {
    return undefined
  }
  const parsed = Number(trimmed)
  return Number.isFinite(parsed) ? parsed : undefined
}

function parsePositiveInt(value: string, fallback: number): number {
  const parsed = Number(value)
  if (!Number.isInteger(parsed) || parsed <= 0) {
    return fallback
  }
  return parsed
}

function getEpisodeId(item: MemoryEpisodeItemPayload | null | undefined): string {
  return String(item?.episode_id ?? item?.id ?? '')
}

function getEpisodeTitle(item: MemoryEpisodeItemPayload): string {
  return String(item.title ?? item.summary ?? item.content ?? getEpisodeId(item) ?? '未命名 Episode')
}

function getEpisodeParagraphs(
  item: MemoryEpisodeItemPayload | MemoryEpisodeDetailPayload['episode'] | null | undefined,
): MemoryEpisodeParagraphPayload[] {
  const paragraphs = item?.paragraphs
  return Array.isArray(paragraphs) ? paragraphs : []
}

function getStatusCount(status: MemoryEpisodeStatusPayload | null, key: string): number {
  const counts = status?.counts
  if (counts && typeof counts[key] === 'number') {
    return counts[key]
  }
  const value = status?.[key]
  return typeof value === 'number' ? value : 0
}

export function MemoryEpisodeManager() {
  const { toast } = useToast()
  const [query, setQuery] = useState('')
  const [source, setSource] = useState('')
  const [personId, setPersonId] = useState('')
  const [timeStart, setTimeStart] = useState('')
  const [timeEnd, setTimeEnd] = useState('')
  const [limit, setLimit] = useState('20')
  const [items, setItems] = useState<MemoryEpisodeItemPayload[]>([])
  const [status, setStatus] = useState<MemoryEpisodeStatusPayload | null>(null)
  const [selectedId, setSelectedId] = useState('')
  const [detail, setDetail] = useState<MemoryEpisodeDetailPayload | null>(null)
  const [loading, setLoading] = useState(false)
  const [detailLoading, setDetailLoading] = useState(false)
  const [actionLoading, setActionLoading] = useState(false)
  const [rebuildSource, setRebuildSource] = useState('')
  const [rebuildSources, setRebuildSources] = useState('')
  const [rebuildAll, setRebuildAll] = useState(false)
  const [pendingLimit, setPendingLimit] = useState('20')
  const [pendingMaxRetry, setPendingMaxRetry] = useState('3')
  const initialLoadedRef = useRef(false)

  const selectedEpisode = useMemo(() => detail?.episode ?? items.find((item) => getEpisodeId(item) === selectedId), [detail?.episode, items, selectedId])
  const selectedEpisodeParagraphs = useMemo(() => getEpisodeParagraphs(selectedEpisode), [selectedEpisode])
  const failedItems = Array.isArray(status?.failed) ? status.failed : []

  const loadStatus = useCallback(async () => {
    const payload = await getMemoryEpisodeStatus(parsePositiveInt(limit, 20))
    setStatus(payload)
  }, [limit])

  const loadEpisodes = useCallback(async () => {
    setLoading(true)
    try {
      const [listPayload] = await Promise.all([
        getMemoryEpisodes({
          query,
          source,
          personId,
          limit: parsePositiveInt(limit, 20),
          timeStart: parseOptionalNumber(timeStart),
          timeEnd: parseOptionalNumber(timeEnd),
        }),
        loadStatus(),
      ])
      const nextItems = listPayload.items ?? []
      setItems(nextItems)
      if (!selectedId && nextItems.length > 0) {
        setSelectedId(getEpisodeId(nextItems[0]))
      }
    } catch (error) {
      toast({
        title: '加载情节记忆失败',
        description: error instanceof Error ? error.message : String(error),
        variant: 'destructive',
      })
    } finally {
      setLoading(false)
    }
  }, [limit, loadStatus, personId, query, selectedId, source, timeEnd, timeStart, toast])

  const loadDetail = useCallback(async (episodeId: string) => {
    if (!episodeId) {
      setDetail(null)
      return
    }
    setDetailLoading(true)
    try {
      const payload = await getMemoryEpisode(episodeId)
      setDetail(payload)
    } catch (error) {
      toast({
        title: '加载 Episode 详情失败',
        description: error instanceof Error ? error.message : String(error),
        variant: 'destructive',
      })
    } finally {
      setDetailLoading(false)
    }
  }, [toast])

  useEffect(() => {
    if (initialLoadedRef.current) {
      return
    }
    initialLoadedRef.current = true
    void loadEpisodes()
  }, [loadEpisodes])

  useEffect(() => {
    if (selectedId) {
      void loadDetail(selectedId)
    }
  }, [loadDetail, selectedId])

  const submitRebuild = useCallback(async () => {
    if (rebuildAll && !window.confirm('确认重建全部可用来源的 Episode？这个操作可能耗时较长。')) {
      return
    }
    const sources = rebuildSources
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean)
    setActionLoading(true)
    try {
      const payload = await rebuildMemoryEpisodes({
        source: rebuildSource.trim(),
        sources,
        all: rebuildAll,
      })
      toast({
        title: payload.success ? 'Episode 重建已提交' : 'Episode 重建失败',
        description: String(payload.detail ?? payload.error ?? `影响来源 ${payload.rebuilt ?? 0} 个`),
        variant: payload.success ? 'default' : 'destructive',
      })
      await loadEpisodes()
    } catch (error) {
      toast({
        title: 'Episode 重建失败',
        description: error instanceof Error ? error.message : String(error),
        variant: 'destructive',
      })
    } finally {
      setActionLoading(false)
    }
  }, [loadEpisodes, rebuildAll, rebuildSource, rebuildSources, toast])

  const submitProcessPending = useCallback(async () => {
    setActionLoading(true)
    try {
      const payload = await processMemoryEpisodePending({
        limit: parsePositiveInt(pendingLimit, 20),
        max_retry: parsePositiveInt(pendingMaxRetry, 3),
      })
      toast({
        title: payload.success ? '已处理待生成 Episode' : '处理待生成 Episode 失败',
        description: String(payload.detail ?? payload.error ?? `已处理 ${payload.processed ?? 0} 项`),
        variant: payload.success ? 'default' : 'destructive',
      })
      await loadEpisodes()
    } catch (error) {
      toast({
        title: '处理待生成 Episode 失败',
        description: error instanceof Error ? error.message : String(error),
        variant: 'destructive',
      })
    } finally {
      setActionLoading(false)
    }
  }, [loadEpisodes, pendingLimit, pendingMaxRetry, toast])

  return (
    <div className="space-y-4">
      <div className="grid gap-4 xl:grid-cols-4">
        {[
          { label: '待处理队列', value: Number(status?.pending_queue ?? 0) },
          { label: '待重建', value: getStatusCount(status, 'pending') },
          { label: '运行中', value: getStatusCount(status, 'running') },
          { label: '失败来源', value: failedItems.length || getStatusCount(status, 'failed') },
        ].map((item) => (
          <Card key={item.label}>
            <CardHeader className="pb-3">
              <CardDescription>{item.label}</CardDescription>
              <CardTitle className="text-2xl">{item.value}</CardTitle>
            </CardHeader>
          </Card>
        ))}
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)]">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Search className="h-4 w-4" />
              Episode 查询
            </CardTitle>
            <CardDescription>按来源、人物和时间范围查看情节记忆构建结果。</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-3 md:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="episode-query">关键词</Label>
                <Input id="episode-query" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索摘要或内容" />
              </div>
              <div className="space-y-2">
                <Label htmlFor="episode-source">来源</Label>
                <Input id="episode-source" value={source} onChange={(event) => setSource(event.target.value)} placeholder="chat_summary:..." />
              </div>
              <div className="space-y-2">
                <Label htmlFor="episode-person">人物 ID</Label>
                <Input id="episode-person" value={personId} onChange={(event) => setPersonId(event.target.value)} placeholder="person_id" />
              </div>
              <div className="space-y-2">
                <Label htmlFor="episode-limit">数量</Label>
                <Input id="episode-limit" type="number" value={limit} onChange={(event) => setLimit(event.target.value)} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="episode-time-start">开始时间戳</Label>
                <Input id="episode-time-start" value={timeStart} onChange={(event) => setTimeStart(event.target.value)} placeholder="可选" />
              </div>
              <div className="space-y-2">
                <Label htmlFor="episode-time-end">结束时间戳</Label>
                <Input id="episode-time-end" value={timeEnd} onChange={(event) => setTimeEnd(event.target.value)} placeholder="可选" />
              </div>
            </div>
            <Button onClick={() => void loadEpisodes()} disabled={loading}>
              <RefreshCw className={cn('mr-2 h-4 w-4', loading && 'animate-spin')} />
              刷新 Episode
            </Button>

            <ScrollArea className="h-[420px] rounded-lg border">
              <Table>
                <TableHeader className="sticky top-0 bg-background">
                  <TableRow>
                    <TableHead>Episode</TableHead>
                    <TableHead>来源</TableHead>
                    <TableHead>更新时间</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {items.length > 0 ? items.map((item) => {
                    const episodeId = getEpisodeId(item)
                    return (
                      <TableRow
                        key={episodeId || getEpisodeTitle(item)}
                        className={cn('cursor-pointer', selectedId === episodeId && 'bg-muted/60')}
                        onClick={() => setSelectedId(episodeId)}
                      >
                        <TableCell>
                          <div className="max-w-[280px] truncate font-medium">{getEpisodeTitle(item)}</div>
                          <div className="font-mono text-[11px] text-muted-foreground break-all">{episodeId || '-'}</div>
                        </TableCell>
                        <TableCell className="max-w-[180px] truncate">{String(item.source ?? '-')}</TableCell>
                        <TableCell>{formatMemoryTime(item.updated_at ?? item.created_at)}</TableCell>
                      </TableRow>
                    )
                  }) : (
                    <TableRow>
                      <TableCell colSpan={3} className="text-center text-muted-foreground">
                        {loading ? '正在加载 Episode...' : '没有匹配的 Episode'}
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </ScrollArea>
          </CardContent>
        </Card>

        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Episode 详情</CardTitle>
              <CardDescription>查看情节摘要、原始字段和关联段落。</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {detailLoading ? (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  正在加载详情
                </div>
              ) : selectedEpisode ? (
                <>
                  <div className="flex flex-wrap gap-2">
                    <Badge variant="outline">{getEpisodeId(selectedEpisode) || '无 ID'}</Badge>
                    {selectedEpisode.source ? <Badge variant="secondary">{String(selectedEpisode.source)}</Badge> : null}
                    {selectedEpisode.person_id ? <Badge>{String(selectedEpisode.person_id)}</Badge> : null}
                  </div>
                  <Textarea value={String(selectedEpisode.summary ?? selectedEpisode.content ?? '')} readOnly className="min-h-[120px]" />
                  <pre className="max-h-56 overflow-auto rounded-lg border bg-muted/20 p-3 text-xs break-words whitespace-pre-wrap">
                    {JSON.stringify(selectedEpisode, null, 2)}
                  </pre>
                  <div className="space-y-2">
                    <div className="text-sm font-medium">关联段落</div>
                    {selectedEpisodeParagraphs.length > 0 ? (
                      <ScrollArea className="h-[220px] rounded-lg border bg-background/60">
                        <div className="space-y-2 p-3">
                          {selectedEpisodeParagraphs.map((paragraph, index) => (
                            <div key={String(paragraph.hash ?? index)} className="rounded-lg border bg-muted/20 p-3">
                              <div className="font-mono text-[11px] text-muted-foreground break-all">{String(paragraph.hash ?? '-')}</div>
                              <div className="mt-2 text-sm break-words">{String(paragraph.preview ?? paragraph.content ?? '')}</div>
                            </div>
                          ))}
                        </div>
                      </ScrollArea>
                    ) : (
                      <div className="rounded-lg border border-dashed bg-muted/20 p-4 text-sm text-muted-foreground">当前详情没有段落明细。</div>
                    )}
                  </div>
                </>
              ) : (
                <div className="rounded-lg border border-dashed bg-muted/20 p-6 text-center text-sm text-muted-foreground">选择一个 Episode 查看详情。</div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <RotateCcw className="h-4 w-4" />
                Episode 运维
              </CardTitle>
              <CardDescription>重建来源或处理待生成队列。</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {failedItems.length > 0 ? (
                <Alert>
                  <AlertDescription>
                    最近失败来源：{failedItems.slice(0, 3).map((item) => String(item.source ?? item.id ?? item.error ?? '未知')).join('、')}
                  </AlertDescription>
                </Alert>
              ) : null}
              <div className="grid gap-3 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="episode-rebuild-source">单个来源</Label>
                  <Input id="episode-rebuild-source" value={rebuildSource} onChange={(event) => setRebuildSource(event.target.value)} />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="episode-rebuild-sources">多个来源（逗号分隔）</Label>
                  <Input id="episode-rebuild-sources" value={rebuildSources} onChange={(event) => setRebuildSources(event.target.value)} />
                </div>
              </div>
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={rebuildAll} onChange={(event) => setRebuildAll(event.target.checked)} />
                重建全部可用来源
              </label>
              <Button onClick={() => void submitRebuild()} disabled={actionLoading}>
                <RotateCcw className="mr-2 h-4 w-4" />
                重建 Episode
              </Button>
              <div className="grid gap-3 md:grid-cols-[1fr_1fr_auto] md:items-end">
                <div className="space-y-2">
                  <Label htmlFor="episode-pending-limit">处理数量</Label>
                  <Input id="episode-pending-limit" type="number" value={pendingLimit} onChange={(event) => setPendingLimit(event.target.value)} />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="episode-pending-retry">最大重试</Label>
                  <Input id="episode-pending-retry" type="number" value={pendingMaxRetry} onChange={(event) => setPendingMaxRetry(event.target.value)} />
                </div>
                <Button variant="outline" onClick={() => void submitProcessPending()} disabled={actionLoading}>
                  <Play className="mr-2 h-4 w-4" />
                  处理 pending
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
