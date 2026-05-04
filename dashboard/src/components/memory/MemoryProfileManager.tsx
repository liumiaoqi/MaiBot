import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Loader2, RefreshCw, Save, Search, Trash2 } from 'lucide-react'

import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Textarea } from '@/components/ui/textarea'
import { useToast } from '@/hooks/use-toast'
import {
  deleteMemoryProfileOverride,
  getMemoryProfiles,
  queryMemoryProfile,
  setMemoryProfileOverride,
  type MemoryProfileItemPayload,
  type MemoryProfileQueryPayload,
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

function parsePositiveInt(value: string, fallback: number): number {
  const parsed = Number(value)
  if (!Number.isInteger(parsed) || parsed <= 0) {
    return fallback
  }
  return parsed
}

function stringifyOverride(value: MemoryProfileItemPayload['manual_override']): string {
  if (!value) {
    return ''
  }
  if (typeof value === 'string') {
    return value
  }
  const text = value.override_text ?? value.text
  if (typeof text === 'string') {
    return text
  }
  return JSON.stringify(value, null, 2)
}

function resolveProfileText(queryResult: MemoryProfileQueryPayload | null, selectedProfile: MemoryProfileItemPayload | null): string {
  if (typeof queryResult?.profile_text === 'string') {
    return queryResult.profile_text
  }
  const queryProfile = queryResult?.profile
  if (queryProfile && typeof queryProfile === 'object' && typeof queryProfile.profile_text === 'string') {
    return queryProfile.profile_text
  }
  return selectedProfile?.profile_text ?? ''
}

export function MemoryProfileManager() {
  const { toast } = useToast()
  const [profiles, setProfiles] = useState<MemoryProfileItemPayload[]>([])
  const [selectedPersonId, setSelectedPersonId] = useState('')
  const [queryPersonId, setQueryPersonId] = useState('')
  const [queryKeyword, setQueryKeyword] = useState('')
  const [queryPlatform, setQueryPlatform] = useState('')
  const [queryUserId, setQueryUserId] = useState('')
  const [queryLimit, setQueryLimit] = useState('12')
  const [forceRefresh, setForceRefresh] = useState(false)
  const [overrideText, setOverrideText] = useState('')
  const [queryResult, setQueryResult] = useState<MemoryProfileQueryPayload | null>(null)
  const [loading, setLoading] = useState(false)
  const [querying, setQuerying] = useState(false)
  const [saving, setSaving] = useState(false)
  const initialLoadedRef = useRef(false)

  const selectedProfile = useMemo(
    () => profiles.find((item) => item.person_id === selectedPersonId) ?? null,
    [profiles, selectedPersonId],
  )
  const profileText = resolveProfileText(queryResult, selectedProfile)

  const loadProfiles = useCallback(async () => {
    setLoading(true)
    try {
      const payload = await getMemoryProfiles(80)
      const nextItems = payload.items ?? []
      setProfiles(nextItems)
      if (!selectedPersonId && nextItems.length > 0) {
        setSelectedPersonId(nextItems[0].person_id)
      }
    } catch (error) {
      toast({
        title: '加载人物画像失败',
        description: error instanceof Error ? error.message : String(error),
        variant: 'destructive',
      })
    } finally {
      setLoading(false)
    }
  }, [selectedPersonId, toast])

  useEffect(() => {
    if (initialLoadedRef.current) {
      return
    }
    initialLoadedRef.current = true
    void loadProfiles()
  }, [loadProfiles])

  useEffect(() => {
    setOverrideText(stringifyOverride(selectedProfile?.manual_override))
    if (selectedProfile?.person_id) {
      setQueryPersonId(selectedProfile.person_id)
    }
  }, [selectedProfile])

  const submitQuery = useCallback(async () => {
    const hasAccountLocator = queryPlatform.trim() && queryUserId.trim()
    if (!queryPersonId.trim() && !queryKeyword.trim() && !hasAccountLocator) {
      toast({
        title: '请输入查询条件',
        description: 'person_id、关键词、或平台与账号至少填写一种。',
        variant: 'destructive',
      })
      return
    }
    setQuerying(true)
    try {
      const payload = await queryMemoryProfile({
        personId: queryPersonId.trim(),
        personKeyword: queryKeyword.trim(),
        platform: queryPlatform.trim(),
        userId: queryUserId.trim(),
        limit: parsePositiveInt(queryLimit, 12),
        forceRefresh,
      })
      setQueryResult(payload)
      const nextPersonId = String(payload.person_id ?? payload.profile?.person_id ?? queryPersonId ?? '')
      if (nextPersonId) {
        setSelectedPersonId(nextPersonId)
        setQueryPersonId(nextPersonId)
      }
      toast({
        title: '人物画像查询完成',
        description: forceRefresh ? '已请求强制刷新画像。' : '已获取画像结果。',
      })
      await loadProfiles()
    } catch (error) {
      toast({
        title: '人物画像查询失败',
        description: error instanceof Error ? error.message : String(error),
        variant: 'destructive',
      })
    } finally {
      setQuerying(false)
    }
  }, [forceRefresh, loadProfiles, queryKeyword, queryLimit, queryPersonId, queryPlatform, queryUserId, toast])

  const saveOverride = useCallback(async () => {
    const personId = selectedPersonId || queryPersonId.trim()
    if (!personId) {
      toast({
        title: '缺少人物 ID',
        description: '请选择或输入一个 person_id 后再保存 override。',
        variant: 'destructive',
      })
      return
    }
    setSaving(true)
    try {
      await setMemoryProfileOverride({
        person_id: personId,
        override_text: overrideText,
        updated_by: 'knowledge_base',
        source: 'webui',
      })
      toast({ title: '人物画像 override 已保存' })
      await loadProfiles()
    } catch (error) {
      toast({
        title: '保存人物画像 override 失败',
        description: error instanceof Error ? error.message : String(error),
        variant: 'destructive',
      })
    } finally {
      setSaving(false)
    }
  }, [loadProfiles, overrideText, queryPersonId, selectedPersonId, toast])

  const deleteOverride = useCallback(async () => {
    const personId = selectedPersonId || queryPersonId.trim()
    if (!personId) {
      return
    }
    if (!window.confirm(`确认删除 ${personId} 的人物画像 override？`)) {
      return
    }
    setSaving(true)
    try {
      await deleteMemoryProfileOverride(personId)
      setOverrideText('')
      toast({ title: '人物画像 override 已删除' })
      await loadProfiles()
    } catch (error) {
      toast({
        title: '删除人物画像 override 失败',
        description: error instanceof Error ? error.message : String(error),
        variant: 'destructive',
      })
    } finally {
      setSaving(false)
    }
  }, [loadProfiles, queryPersonId, selectedPersonId, toast])

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Search className="h-4 w-4" />
            人物画像查询
          </CardTitle>
          <CardDescription>查看最近画像快照，或按 person_id、关键词、平台账号触发查询与刷新。</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="profile-person-id">person_id</Label>
              <Input id="profile-person-id" value={queryPersonId} onChange={(event) => setQueryPersonId(event.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="profile-keyword">人物关键词</Label>
              <Input id="profile-keyword" value={queryKeyword} onChange={(event) => setQueryKeyword(event.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="profile-platform">平台</Label>
              <Input
                id="profile-platform"
                value={queryPlatform}
                onChange={(event) => setQueryPlatform(event.target.value)}
                placeholder="例如 qq、telegram、webui"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="profile-user-id">平台账号</Label>
              <Input
                id="profile-user-id"
                value={queryUserId}
                onChange={(event) => setQueryUserId(event.target.value)}
                placeholder="输入平台侧 user_id"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="profile-limit">证据数量</Label>
              <Input id="profile-limit" type="number" value={queryLimit} onChange={(event) => setQueryLimit(event.target.value)} />
            </div>
            <div className="flex items-center gap-2 self-end pb-2">
              <Checkbox
                id="profile-force-refresh"
                checked={forceRefresh}
                onCheckedChange={(value) => setForceRefresh(Boolean(value))}
              />
              <Label htmlFor="profile-force-refresh" className="text-sm font-normal">
                强制刷新画像
              </Label>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => void submitQuery()} disabled={querying}>
              <Search className="mr-2 h-4 w-4" />
              查询人物画像
            </Button>
            <Button variant="outline" onClick={() => void loadProfiles()} disabled={loading}>
              <RefreshCw className={cn('mr-2 h-4 w-4', loading && 'animate-spin')} />
              刷新列表
            </Button>
          </div>

          <ScrollArea className="h-[520px] rounded-lg border">
            <Table>
              <TableHeader className="sticky top-0 bg-background">
                <TableRow>
                  <TableHead>人物</TableHead>
                  <TableHead>版本</TableHead>
                  <TableHead>更新时间</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {profiles.length > 0 ? profiles.map((item) => (
                  <TableRow
                    key={item.person_id}
                    className={cn('cursor-pointer', selectedPersonId === item.person_id && 'bg-muted/60')}
                    onClick={() => setSelectedPersonId(item.person_id)}
                  >
                    <TableCell>
                      <div className="font-medium break-all">{item.person_id}</div>
                      <div className="mt-1 flex flex-wrap gap-1">
                        {item.has_manual_override ? <Badge variant="secondary">手动 override</Badge> : null}
                        {item.source_note ? <Badge variant="outline">{item.source_note}</Badge> : null}
                      </div>
                    </TableCell>
                    <TableCell>{Number(item.profile_version ?? 0)}</TableCell>
                    <TableCell>{formatMemoryTime(item.updated_at)}</TableCell>
                  </TableRow>
                )) : (
                  <TableRow>
                    <TableCell colSpan={3} className="text-center text-muted-foreground">
                      {loading ? '正在加载人物画像...' : '还没有人物画像快照'}
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
            <CardTitle>画像详情</CardTitle>
            <CardDescription>展示当前快照、查询结果和原始响应。</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {querying ? (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                正在查询人物画像
              </div>
            ) : null}
            {selectedProfile || queryResult ? (
              <>
                <div className="flex flex-wrap gap-2">
                  <Badge variant="outline">{selectedPersonId || String(queryResult?.person_id ?? '未选择')}</Badge>
                  {selectedProfile?.expires_at ? <Badge variant="secondary">过期时间 {formatMemoryTime(selectedProfile.expires_at)}</Badge> : null}
                </div>
                <Textarea value={profileText} readOnly className="min-h-[180px]" placeholder="当前没有画像文本" />
                <pre className="max-h-72 overflow-auto rounded-lg border bg-muted/20 p-3 text-xs break-words whitespace-pre-wrap">
                  {JSON.stringify(queryResult ?? selectedProfile ?? {}, null, 2)}
                </pre>
              </>
            ) : (
              <div className="rounded-lg border border-dashed bg-muted/20 p-6 text-center text-sm text-muted-foreground">
                选择一个人物或执行查询后查看详情。
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>手动 Override</CardTitle>
            <CardDescription>用人工画像覆盖自动生成结果；留空保存表示清空文本但保留 override 记录。</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {!selectedPersonId && !queryPersonId.trim() ? (
              <Alert>
                <AlertDescription>请选择或输入 person_id 后再编辑 override。</AlertDescription>
              </Alert>
            ) : null}
            <Textarea
              value={overrideText}
              onChange={(event) => setOverrideText(event.target.value)}
              className="min-h-[180px]"
              placeholder="输入希望固定使用的人物画像文本"
            />
            <div className="flex flex-wrap gap-2">
              <Button onClick={() => void saveOverride()} disabled={saving}>
                <Save className="mr-2 h-4 w-4" />
                保存 override
              </Button>
              <Button variant="outline" onClick={() => void deleteOverride()} disabled={saving || (!selectedPersonId && !queryPersonId.trim())}>
                <Trash2 className="mr-2 h-4 w-4" />
                删除 override
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
