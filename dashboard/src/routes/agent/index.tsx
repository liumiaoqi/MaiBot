import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Bot,
  ChevronRight,
  Heart,
  Link2,
  MessageSquare,
  RefreshCw,
  Search,
  Unlink,
  Users,
} from 'lucide-react'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Separator } from '@/components/ui/separator'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'

import { useToast } from '@/hooks/use-toast'

import {
  bindSessionAgent,
  getAgentDetail,
  getAgentEmotion,
  getAgentList,
  getAgentRelationships,
  getSessionsByAgent,
  reloadAgents,
  unbindSessionAgent,
  type AgentConfigInfo,
  type EmotionStateInfo,
  type RelationshipInfo,
  type SessionAgentInfo,
} from '@/lib/agent-api'
import { getChatStreams, type ChatStream } from '@/lib/chat-management-api'

import { cn } from '@/lib/utils'

const EMOTION_COLORS: Record<string, string> = {
  happy: '#fbbf24',
  sad: '#60a5fa',
  anxious: '#a78bfa',
  angry: '#ef4444',
  calm: '#34d399',
  excited: '#f97316',
  lonely: '#94a3b8',
}

const EMOTION_ICONS: Record<string, string> = {
  happy: '😊',
  sad: '😢',
  anxious: '😰',
  angry: '😠',
  calm: '😌',
  excited: '🤩',
  lonely: '😔',
}

function EmotionRadar({ emotions, emotionLabels }: { emotions: Record<string, number>; emotionLabels: Record<string, string> }) {
  const maxVal = Math.max(...Object.values(emotions), 1)
  const size = 160
  const center = size / 2
  const radius = size / 2 - 20
  const entries = Object.entries(emotions)
  const n = entries.length

  return (
    <div className="flex items-center justify-center">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        {[0.25, 0.5, 0.75, 1].map((ring) => (
          <polygon
            key={ring}
            points={entries
              .map((_, i) => {
                const angle = (2 * Math.PI * i) / n - Math.PI / 2
                const x = center + radius * ring * Math.cos(angle)
                const y = center + radius * ring * Math.sin(angle)
                return `${x},${y}`
              })
              .join(' ')}
            fill="none"
            stroke="currentColor"
            strokeOpacity={0.15}
            strokeWidth={1}
          />
        ))}
        {entries.map(([, val], i) => {
          const angle = (2 * Math.PI * i) / n - Math.PI / 2
          const x = center + radius * Math.cos(angle)
          const y = center + radius * Math.sin(angle)
          return (
            <line
              key={i}
              x1={center}
              y1={center}
              x2={x}
              y2={y}
              stroke="currentColor"
              strokeOpacity={0.1}
              strokeWidth={1}
            />
          )
        })}
        <polygon
          points={entries
            .map(([, val], i) => {
              const ratio = val / maxVal
              const angle = (2 * Math.PI * i) / n - Math.PI / 2
              const x = center + radius * ratio * Math.cos(angle)
              const y = center + radius * ratio * Math.sin(angle)
              return `${x},${y}`
            })
            .join(' ')}
          fill="currentColor"
          fillOpacity={0.15}
          stroke="currentColor"
          strokeWidth={2}
        />
        {entries.map(([key, val], i) => {
          const angle = (2 * Math.PI * i) / n - Math.PI / 2
          const lx = center + (radius + 14) * Math.cos(angle)
          const ly = center + (radius + 14) * Math.sin(angle)
          return (
            <text
              key={key}
              x={lx}
              y={ly}
              textAnchor="middle"
              dominantBaseline="middle"
              className="fill-muted-foreground"
              fontSize={10}
            >
              {EMOTION_ICONS[key] || ''} {emotionLabels[key] || key}
            </text>
          )
        })}
      </svg>
    </div>
  )
}

function EmotionBars({ emotions, emotionLabels }: { emotions: Record<string, number>; emotionLabels: Record<string, string> }) {
  return (
    <div className="space-y-2">
      {Object.entries(emotions).map(([key, val]) => (
        <div key={key} className="flex items-center gap-2">
          <span className="w-16 text-xs text-muted-foreground shrink-0">
            {EMOTION_ICONS[key]} {emotionLabels[key] || key}
          </span>
          <div className="flex-1 h-2 bg-muted rounded-full overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-500"
              style={{
                width: `${Math.min(val, 100)}%`,
                backgroundColor: EMOTION_COLORS[key] || '#9b59b6',
              }}
            />
          </div>
          <span className="text-xs text-muted-foreground w-8 text-right">{Math.round(val)}</span>
        </div>
      ))}
    </div>
  )
}

function RelationshipTable({ relationships }: { relationships: RelationshipInfo[] }) {
  if (relationships.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground text-sm">
        暂无关系数据
      </div>
    )
  }
  return (
    <div className="space-y-2">
      {relationships.map((rel) => (
        <div
          key={rel.user_id}
          className="flex items-center justify-between p-3 rounded-lg border bg-card"
        >
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-full bg-muted flex items-center justify-center">
              <Users className="h-4 w-4 text-muted-foreground" />
            </div>
            <div>
              <div className="text-sm font-medium">{rel.user_id}</div>
              <div className="text-xs text-muted-foreground">
                互动 {rel.total_interactions} 次
              </div>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div className="text-right">
              <Badge
                variant={
                  rel.level >= 3 ? 'default' : rel.level >= 2 ? 'secondary' : 'outline'
                }
              >
                {rel.level_name}
              </Badge>
              <div className="text-xs text-muted-foreground mt-1">
                {Math.round(rel.score)}/1000
              </div>
            </div>
            <div className="w-16">
              <div className="h-1.5 bg-muted rounded-full overflow-hidden">
                <div
                  className="h-full rounded-full bg-primary transition-all"
                  style={{ width: `${(rel.score / 1000) * 100}%` }}
                />
              </div>
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}

function AgentCard({
  agent,
  isSelected,
  onClick,
}: {
  agent: AgentConfigInfo
  isSelected: boolean
  onClick: () => void
}) {
  return (
    <Card
      className={cn(
        'cursor-pointer transition-all hover:shadow-md',
        isSelected && 'ring-2 ring-primary'
      )}
      onClick={onClick}
    >
      <CardHeader className="pb-2">
        <div className="flex items-center gap-3">
          <div
            className="w-10 h-10 rounded-full flex items-center justify-center text-white font-bold text-sm shrink-0"
            style={{ backgroundColor: agent.color }}
          >
            {agent.display_name.charAt(0)}
          </div>
          <div className="flex-1 min-w-0">
            <CardTitle className="text-base truncate">{agent.display_name}</CardTitle>
            <CardDescription className="text-xs truncate">
              {agent.agent_id}
            </CardDescription>
          </div>
          {agent.is_default && (
            <Badge variant="default" className="shrink-0">
              默认
            </Badge>
          )}
        </div>
      </CardHeader>
      <CardContent className="pt-0">
        <div className="flex items-center gap-4 text-xs text-muted-foreground">
          <span>活跃度 ×{agent.talk_value_modifier.toFixed(1)}</span>
          <span>关系速率 ×{agent.relationship_growth_rate.toFixed(1)}</span>
        </div>
      </CardContent>
    </Card>
  )
}

export function AgentManagementPage() {
  const { t } = useTranslation()
  const { toast } = useToast()
  const queryClient = useQueryClient()

  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [bindDialogOpen, setBindDialogOpen] = useState(false)
  const [bindSessionId, setBindSessionId] = useState('')
  const [bindTargetAgentId, setBindTargetAgentId] = useState('')

  const agentsQuery = useQuery({
    queryKey: ['agents', 'list'],
    queryFn: getAgentList,
  })

  const agentDetailQuery = useQuery({
    queryKey: ['agents', 'detail', selectedAgentId],
    queryFn: () => getAgentDetail(selectedAgentId!),
    enabled: !!selectedAgentId,
  })

  const emotionQuery = useQuery({
    queryKey: ['agents', 'emotion', selectedAgentId],
    queryFn: () => getAgentEmotion(selectedAgentId!),
    enabled: !!selectedAgentId,
  })

  const relationshipQuery = useQuery({
    queryKey: ['agents', 'relationships', selectedAgentId],
    queryFn: () => getAgentRelationships(selectedAgentId!),
    enabled: !!selectedAgentId,
  })

  const sessionsQuery = useQuery({
    queryKey: ['agents', 'sessions', selectedAgentId],
    queryFn: () => getSessionsByAgent(selectedAgentId!),
    enabled: !!selectedAgentId,
  })

  const chatStreamsQuery = useQuery({
    queryKey: ['chat', 'streams'],
    queryFn: () => getChatStreams(500),
  })

  const reloadMutation = useMutation({
    mutationFn: reloadAgents,
    onSuccess: (data) => {
      toast({ title: data.message })
      queryClient.invalidateQueries({ queryKey: ['agents'] })
    },
    onError: () => {
      toast({ title: '重新加载失败', variant: 'destructive' })
    },
  })

  const bindMutation = useMutation({
    mutationFn: ({ sessionId, agentId }: { sessionId: string; agentId: string }) =>
      bindSessionAgent(sessionId, agentId),
    onSuccess: () => {
      toast({ title: '绑定成功' })
      queryClient.invalidateQueries({ queryKey: ['agents'] })
      queryClient.invalidateQueries({ queryKey: ['chat'] })
      setBindDialogOpen(false)
      setBindSessionId('')
      setBindTargetAgentId('')
    },
    onError: () => {
      toast({ title: '绑定失败', variant: 'destructive' })
    },
  })

  const unbindMutation = useMutation({
    mutationFn: unbindSessionAgent,
    onSuccess: () => {
      toast({ title: '已解除绑定' })
      queryClient.invalidateQueries({ queryKey: ['agents'] })
      queryClient.invalidateQueries({ queryKey: ['chat'] })
    },
    onError: () => {
      toast({ title: '解除绑定失败', variant: 'destructive' })
    },
  })

  const filteredAgents = useMemo(() => {
    if (!agentsQuery.data) return []
    if (!searchQuery) return agentsQuery.data
    const q = searchQuery.toLowerCase()
    return agentsQuery.data.filter(
      (a) =>
        a.agent_id.toLowerCase().includes(q) ||
        a.display_name.toLowerCase().includes(q)
    )
  }, [agentsQuery.data, searchQuery])

  const selectedAgent = agentDetailQuery.data
  const emotionState = emotionQuery.data
  const relationships = relationshipQuery.data ?? []

  return (
    <div className="flex h-full">
      {/* 左侧：智能体列表 */}
      <div className="w-80 border-r shrink-0 flex flex-col">
        <div className="p-4 border-b">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-lg font-semibold">智能体</h2>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => reloadMutation.mutate()}
              disabled={reloadMutation.isPending}
            >
              <RefreshCw className={cn('h-4 w-4', reloadMutation.isPending && 'animate-spin')} />
            </Button>
          </div>
          <div className="relative">
            <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="搜索智能体..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-9"
            />
          </div>
        </div>
        <ScrollArea className="flex-1">
          <div className="p-3 space-y-2">
            {agentsQuery.isLoading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <Skeleton key={i} className="h-24 w-full rounded-lg" />
              ))
            ) : (
              filteredAgents.map((agent) => (
                <AgentCard
                  key={agent.agent_id}
                  agent={agent}
                  isSelected={selectedAgentId === agent.agent_id}
                  onClick={() => setSelectedAgentId(agent.agent_id)}
                />
              ))
            )}
          </div>
        </ScrollArea>
        <div className="p-3 border-t text-xs text-muted-foreground text-center">
          共 {filteredAgents.length} 个智能体
        </div>
      </div>

      {/* 右侧：智能体详情 */}
      <div className="flex-1 overflow-hidden">
        {!selectedAgentId ? (
          <div className="flex items-center justify-center h-full text-muted-foreground">
            <div className="text-center">
              <Bot className="h-12 w-12 mx-auto mb-3 opacity-30" />
              <p>选择一个智能体查看详情</p>
            </div>
          </div>
        ) : agentDetailQuery.isLoading ? (
          <div className="p-6 space-y-4">
            <Skeleton className="h-8 w-48" />
            <Skeleton className="h-4 w-32" />
            <div className="grid grid-cols-2 gap-4">
              <Skeleton className="h-64 rounded-lg" />
              <Skeleton className="h-64 rounded-lg" />
            </div>
          </div>
        ) : selectedAgent ? (
          <ScrollArea className="h-full">
            <div className="p-6 space-y-6">
              {/* 头部信息 */}
              <div className="flex items-start gap-4">
                <div
                  className="w-16 h-16 rounded-full flex items-center justify-center text-white font-bold text-2xl shrink-0"
                  style={{ backgroundColor: selectedAgent.color }}
                >
                  {selectedAgent.display_name.charAt(0)}
                </div>
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <h1 className="text-2xl font-bold">{selectedAgent.display_name}</h1>
                    {selectedAgent.is_default && <Badge>默认</Badge>}
                    <Badge variant="outline">{selectedAgent.agent_id}</Badge>
                  </div>
                  {selectedAgent.reply_style && (
                    <p className="text-muted-foreground mt-1 text-sm line-clamp-2">
                      {selectedAgent.reply_style}
                    </p>
                  )}
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    setBindDialogOpen(true)
                    setBindTargetAgentId(selectedAgent.agent_id)
                  }}
                >
                  <Link2 className="h-4 w-4 mr-1" />
                  绑定会话
                </Button>
              </div>

              <Separator />

              {/* 标签页 */}
              <Tabs defaultValue="overview">
                <TabsList>
                  <TabsTrigger value="overview">概览</TabsTrigger>
                  <TabsTrigger value="emotion">
                    <Heart className="h-3.5 w-3.5 mr-1" />
                    情绪
                  </TabsTrigger>
                  <TabsTrigger value="relationship">
                    <Users className="h-3.5 w-3.5 mr-1" />
                    关系
                  </TabsTrigger>
                  <TabsTrigger value="sessions">
                    <Link2 className="h-3.5 w-3.5 mr-1" />
                    会话
                  </TabsTrigger>
                </TabsList>

                {/* 概览标签页 */}
                <TabsContent value="overview" className="space-y-4">
                  <div className="grid grid-cols-2 gap-4">
                    <Card>
                      <CardHeader className="pb-2">
                        <CardTitle className="text-sm">行为参数</CardTitle>
                      </CardHeader>
                      <CardContent className="space-y-2">
                        <div className="flex justify-between text-sm">
                          <span className="text-muted-foreground">活跃度修正</span>
                          <span>×{selectedAgent.talk_value_modifier.toFixed(1)}</span>
                        </div>
                        <div className="flex justify-between text-sm">
                          <span className="text-muted-foreground">空闲退避修正</span>
                          <span>×{selectedAgent.idle_backoff_modifier.toFixed(1)}</span>
                        </div>
                        <div className="flex justify-between text-sm">
                          <span className="text-muted-foreground">关系进展速率</span>
                          <span>×{selectedAgent.relationship_growth_rate.toFixed(1)}</span>
                        </div>
                        <div className="flex justify-between text-sm">
                          <span className="text-muted-foreground">情绪衰减率</span>
                          <span>{selectedAgent.emotion_decay_rate}/h</span>
                        </div>
                      </CardContent>
                    </Card>

                    <Card>
                      <CardHeader className="pb-2">
                        <CardTitle className="text-sm">记忆焦点</CardTitle>
                      </CardHeader>
                      <CardContent>
                        {selectedAgent.memory_focus_areas.length > 0 ? (
                          <div className="flex flex-wrap gap-1">
                            {selectedAgent.memory_focus_areas.map((area) => (
                              <Badge key={area} variant="secondary">
                                {area}
                              </Badge>
                            ))}
                          </div>
                        ) : (
                          <span className="text-sm text-muted-foreground">无特定焦点</span>
                        )}
                      </CardContent>
                    </Card>
                  </div>

                  {selectedAgent.anti_mechanization_rules.length > 0 && (
                    <Card>
                      <CardHeader className="pb-2">
                        <CardTitle className="text-sm">反机械化规则</CardTitle>
                      </CardHeader>
                      <CardContent>
                        <ul className="space-y-1">
                          {selectedAgent.anti_mechanization_rules.map((rule, i) => (
                            <li key={i} className="text-sm text-muted-foreground">
                              {i + 1}. {rule}
                            </li>
                          ))}
                        </ul>
                      </CardContent>
                    </Card>
                  )}

                  {selectedAgent.internal_relationships.length > 0 && (
                    <Card>
                      <CardHeader className="pb-2">
                        <CardTitle className="text-sm">内部关系网</CardTitle>
                      </CardHeader>
                      <CardContent>
                        <div className="space-y-2">
                          {selectedAgent.internal_relationships.map((rel) => (
                            <div
                              key={rel.target_agent_id}
                              className="flex items-center gap-2 text-sm"
                            >
                              <Badge variant="outline">{rel.target_agent_id}</Badge>
                              <span className="text-muted-foreground">{rel.relationship_type}</span>
                              <span className="text-muted-foreground">—</span>
                              <span>{rel.attitude}</span>
                            </div>
                          ))}
                        </div>
                      </CardContent>
                    </Card>
                  )}

                  {selectedAgent.personality && (
                    <Card>
                      <CardHeader className="pb-2">
                        <CardTitle className="text-sm">人格设定</CardTitle>
                      </CardHeader>
                      <CardContent>
                        <p className="text-sm text-muted-foreground whitespace-pre-wrap leading-relaxed">
                          {selectedAgent.personality}
                        </p>
                      </CardContent>
                    </Card>
                  )}
                </TabsContent>

                {/* 情绪标签页 */}
                <TabsContent value="emotion" className="space-y-4">
                  {emotionQuery.isLoading ? (
                    <Skeleton className="h-64 w-full rounded-lg" />
                  ) : emotionState ? (
                    <>
                      <div className="flex items-center gap-2 mb-2">
                        <span className="text-sm text-muted-foreground">主导情绪：</span>
                        <Badge
                          style={{
                            backgroundColor: EMOTION_COLORS[emotionState.dominant_emotion],
                            color: 'white',
                          }}
                        >
                          {EMOTION_ICONS[emotionState.dominant_emotion]}{' '}
                          {emotionState.dominant_emotion_label}
                        </Badge>
                      </div>
                      <div className="grid grid-cols-2 gap-6">
                        <Card>
                          <CardHeader className="pb-2">
                            <CardTitle className="text-sm">情绪雷达</CardTitle>
                          </CardHeader>
                          <CardContent>
                            <EmotionRadar
                              emotions={emotionState.emotions}
                              emotionLabels={emotionState.emotion_labels}
                            />
                          </CardContent>
                        </Card>
                        <Card>
                          <CardHeader className="pb-2">
                            <CardTitle className="text-sm">情绪强度</CardTitle>
                          </CardHeader>
                          <CardContent>
                            <EmotionBars
                              emotions={emotionState.emotions}
                              emotionLabels={emotionState.emotion_labels}
                            />
                          </CardContent>
                        </Card>
                      </div>
                      <Card>
                        <CardHeader className="pb-2">
                          <CardTitle className="text-sm">情绪基线</CardTitle>
                        </CardHeader>
                        <CardContent>
                          <EmotionBars
                            emotions={Object.fromEntries(
                              Object.entries(selectedAgent.emotion_baseline).map(
                                ([k, v]) => [k, v as number]
                              )
                            )}
                            emotionLabels={emotionState.emotion_labels}
                          />
                        </CardContent>
                      </Card>
                    </>
                  ) : (
                    <div className="text-center py-8 text-muted-foreground text-sm">
                      情绪数据加载失败
                    </div>
                  )}
                </TabsContent>

                {/* 关系标签页 */}
                <TabsContent value="relationship" className="space-y-4">
                  {relationshipQuery.isLoading ? (
                    <Skeleton className="h-48 w-full rounded-lg" />
                  ) : (
                    <Card>
                      <CardHeader className="pb-2">
                        <div className="flex items-center justify-between">
                          <CardTitle className="text-sm">关系概览</CardTitle>
                          <span className="text-xs text-muted-foreground">
                            共 {relationships.length} 条关系
                          </span>
                        </div>
                      </CardHeader>
                      <CardContent>
                        <RelationshipTable relationships={relationships} />
                      </CardContent>
                    </Card>
                  )}
                </TabsContent>

                {/* 会话标签页 */}
                <TabsContent value="sessions" className="space-y-4">
                  {sessionsQuery.isLoading ? (
                    <Skeleton className="h-48 w-full rounded-lg" />
                  ) : (
                    <Card>
                      <CardHeader className="pb-2">
                        <div className="flex items-center justify-between">
                          <CardTitle className="text-sm">关联会话</CardTitle>
                          <span className="text-xs text-muted-foreground">
                            共 {sessionsQuery.data?.length ?? 0} 个会话
                          </span>
                        </div>
                      </CardHeader>
                      <CardContent>
                        {sessionsQuery.data && sessionsQuery.data.length > 0 ? (
                          <div className="space-y-2">
                            {sessionsQuery.data.map((s) => (
                              <div
                                key={s.session_id}
                                className="flex items-center justify-between p-3 rounded-lg border bg-card"
                              >
                                <div className="flex items-center gap-2">
                                  <MessageSquare className="h-4 w-4 text-muted-foreground" />
                                  <span className="text-sm font-medium">
                                    {s.display_name}
                                  </span>
                                </div>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() =>
                                    unbindMutation.mutate(s.session_id)
                                  }
                                  disabled={unbindMutation.isPending}
                                >
                                  <Unlink className="h-3.5 w-3.5 mr-1" />
                                  解绑
                                </Button>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <div className="text-center py-8 text-muted-foreground text-sm">
                            暂无关联会话
                          </div>
                        )}
                      </CardContent>
                    </Card>
                  )}
                </TabsContent>
              </Tabs>
            </div>
          </ScrollArea>
        ) : null}
      </div>

      {/* 绑定会话对话框 */}
      <Dialog open={bindDialogOpen} onOpenChange={setBindDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>绑定会话到智能体</DialogTitle>
            <DialogDescription>
              选择一个会话，将其绑定到「{selectedAgent?.display_name}」
            </DialogDescription>
          </DialogHeader>
          <DialogBody>
            <div className="space-y-4">
              <div>
                <Label>选择会话</Label>
                <Select value={bindSessionId} onValueChange={setBindSessionId}>
                  <SelectTrigger>
                    <SelectValue placeholder="选择会话..." />
                  </SelectTrigger>
                  <SelectContent>
                    {chatStreamsQuery.data?.map((stream) => (
                      <SelectItem key={stream.session_id} value={stream.session_id}>
                        {stream.display_name || stream.session_id}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" onClick={() => setBindDialogOpen(false)}>
              取消
            </Button>
            <Button
              onClick={() => {
                if (bindSessionId && bindTargetAgentId) {
                  bindMutation.mutate({
                    sessionId: bindSessionId,
                    agentId: bindTargetAgentId,
                  })
                }
              }}
              disabled={!bindSessionId || bindMutation.isPending}
            >
              绑定
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}