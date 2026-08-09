/**
 * ChatManagementPage 会话档案管理（R3-2-5 主组件组装）
 *
 * 从 dashboard routes/chat-management.tsx 1875-2237 行搬移。
 * 双视图（streams/groups）+ 头部统计卡 + streams 视图（搜索+过滤+DataTable+分页）
 * + groups 视图（MutualGroupsView）+ 详情弹窗 + 删除流
 *
 * 适配点：
 * - DashboardTabBar/DashboardTabEabTrigger → TabsList/TabsTrigger
 * - DialogBody → SessionDetailDialog（ScrollArea 内封装）
 * - AgentIndicator/AgentSelectPopover → 去掉（R4 范围，同 ChatPage）
 * - useToast → sonner toast()
 * - t() i18n → 硬编码简体中文
 */
import { useQuery } from '@tanstack/react-query'
import {
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  RefreshCw,
  Search,
  Trash2,
} from 'lucide-react'
import { useMemo, useState } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { getAgentList, type AgentConfigInfo } from '@/lib/agent-api'
import {
  getChatStreamDetail,
  getChatStreams,
  type ChatStream,
} from '@/lib/chat-management-api'
import { cn } from '@/lib/utils'

import {
  formatTimestamp,
  getChatLogicalId,
  getChatTypeLabel,
  matchesSearch,
  matchesTypeFilter,
  type ChatManagementView,
  type ChatTypeFilter,
} from './chat-management-utils'
import { DeleteChatStreamDialog } from './components/delete-chat-stream-dialog'
import { HoverScrollText } from './components/hover-scroll-text'
import { MutualGroupsView } from './components/mutual-groups-view'
import { ChatStreamAvatar, SessionDetailDialog } from './components/session-detail-dialog'

/** 每页条数 */
const PAGE_SIZE = 10

/** ChatManagementPage 会话档案管理页面 */
export function ChatManagementPage() {
  const [activeView, setActiveView] = useState<ChatManagementView>(() => {
    if (typeof window === 'undefined') {
      return 'streams'
    }
    return new URLSearchParams(window.location.search).get('view') === 'groups' ? 'groups' : 'streams'
  })
  const [search, setSearch] = useState('')
  const [typeFilter, setTypeFilter] = useState<ChatTypeFilter>('all')
  const [agentFilter, setAgentFilter] = useState<string>('all')
  const [page, setPage] = useState(1)
  const [selectedChat, setSelectedChat] = useState<ChatStream | null>(null)
  const [deletingChat, setDeletingChat] = useState<ChatStream | null>(null)
  const {
    data: chats = [],
    error,
    isFetching,
    isLoading,
    refetch,
  } = useQuery({
    queryKey: ['chat-streams'],
    queryFn: () => getChatStreams(),
  })
  const detailQuery = useQuery({
    queryKey: ['chat-stream-detail', selectedChat?.session_id],
    queryFn: () => getChatStreamDetail(selectedChat?.session_id ?? ''),
    enabled: Boolean(selectedChat?.session_id),
  })
  const { data: agentList = [] } = useQuery({
    queryKey: ['agent', 'list'],
    queryFn: getAgentList,
  })

  const filteredChats = useMemo(
    () =>
      chats.filter((chat) => matchesTypeFilter(chat, typeFilter) && matchesSearch(chat, search) && (agentFilter === 'all' || (chat.agent_id || 'silver_wolf') === agentFilter)),
    [chats, search, typeFilter, agentFilter]
  )
  const pageCount = Math.max(1, Math.ceil(filteredChats.length / PAGE_SIZE))
  const currentPage = Math.min(page, pageCount)
  const paginatedChats = useMemo(() => {
    const start = (currentPage - 1) * PAGE_SIZE
    return filteredChats.slice(start, start + PAGE_SIZE)
  }, [currentPage, filteredChats])
  const visibleStart = filteredChats.length === 0 ? 0 : (currentPage - 1) * PAGE_SIZE + 1
  const visibleEnd = Math.min(currentPage * PAGE_SIZE, filteredChats.length)
  const groupCount = chats.filter((chat) => chat.chat_type === 'group').length
  const privateCount = chats.length - groupCount

  // 过滤条件变化 → 翻页复位——渲染期调整模式（R3 审核修复：rAF 规避 → React 官方模式）
  const [prevFilters, setPrevFilters] = useState({ search, typeFilter, agentFilter })
  if (
    search !== prevFilters.search ||
    typeFilter !== prevFilters.typeFilter ||
    agentFilter !== prevFilters.agentFilter
  ) {
    setPrevFilters({ search, typeFilter, agentFilter })
    setPage(1)
  }

  // 页数越界钳制——渲染期调整（条件稳定收敛）
  if (page > pageCount) {
    setPage(pageCount)
  }

  const handleChatDeleted = (sessionId: string) => {
    if (selectedChat?.session_id === sessionId) {
      setSelectedChat(null)
    }
  }

  return (
    <main className="flex h-full min-h-0 flex-col gap-4 overflow-hidden p-4 md:p-6">
      <header className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="bg-background grid w-full grid-cols-3 border-2 text-sm sm:w-auto">
          <div className="px-4 py-2">
            <div className="text-muted-foreground">全部</div>
            <div className="text-lg leading-tight font-semibold">{chats.length}</div>
          </div>
          <div className="border-l-2 px-4 py-2">
            <div className="text-muted-foreground">群聊</div>
            <div className="text-lg leading-tight font-semibold">{groupCount}</div>
          </div>
          <div className="border-l-2 px-4 py-2">
            <div className="text-muted-foreground">私聊</div>
            <div className="text-lg leading-tight font-semibold">{privateCount}</div>
          </div>
        </div>
        <Tabs
          value={activeView}
          onValueChange={(value) => setActiveView(value as ChatManagementView)}
        >
          <TabsList className="bg-background h-10 w-full border-2 sm:w-fit">
            <TabsTrigger value="streams" className="h-8 px-4">聊天流</TabsTrigger>
            <TabsTrigger value="groups" className="h-8 px-4">共享组</TabsTrigger>
          </TabsList>
        </Tabs>
      </header>

      {activeView === 'groups' ? (
        <MutualGroupsView chats={chats} />
      ) : (
        <>
          <section className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="relative w-full sm:max-w-sm">
              <Search className="text-muted-foreground pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2" />
              <Input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="搜索名称、平台、ID、会话 ID 等"
                className="pl-9"
              />
            </div>
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
              <Tabs
                value={typeFilter}
                onValueChange={(value) => setTypeFilter(value as ChatTypeFilter)}
              >
                <TabsList className="bg-background h-10 w-full border-2 sm:w-fit">
                  <TabsTrigger value="all" className="h-8 px-4">全部</TabsTrigger>
                  <TabsTrigger value="group" className="h-8 px-4">群聊</TabsTrigger>
                  <TabsTrigger value="private" className="h-8 px-4">私聊</TabsTrigger>
                </TabsList>
              </Tabs>
              <select
                className="border-input bg-background h-9 rounded-md border px-2 text-sm"
                value={agentFilter}
                onChange={(e) => setAgentFilter(e.target.value)}
              >
                <option value="all">全部智能体</option>
                {agentList.map((a: AgentConfigInfo) => (
                  <option key={a.agent_id} value={a.agent_id}>{a.display_name}</option>
                ))}
              </select>
              <Button
                type="button"
                variant="outline"
                onClick={() => void refetch()}
                disabled={isFetching}
                className="shrink-0"
              >
                <RefreshCw className={cn('mr-2 h-4 w-4', isFetching && 'animate-spin')} />
                刷新
              </Button>
            </div>
          </section>

          <section className="bg-background flex min-h-0 flex-1 flex-col overflow-hidden rounded-md border">
            <div className="min-h-0 flex-1 overflow-auto">
              <Table className="table-fixed">
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-[7rem] px-3">聊天流</TableHead>
                    <TableHead className="w-[2rem] px-2">平台</TableHead>
                    <TableHead className="w-[5rem] px-2">ID</TableHead>
                    <TableHead className="w-[2.5rem] px-2">Type</TableHead>
                    <TableHead className="w-[3rem] px-2 text-right">消息数</TableHead>
                    <TableHead className="w-[3rem] px-2 text-right">表达数</TableHead>
                    <TableHead className="w-[3rem] px-2 text-right">黑话数</TableHead>
                    <TableHead className="w-[3rem] px-2">最后活跃</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {isLoading ? (
                    <TableRow>
                      <TableCell colSpan={8} className="text-muted-foreground h-28 text-center">
                        正在加载聊天流...
                      </TableCell>
                    </TableRow>
                  ) : error ? (
                    <TableRow>
                      <TableCell colSpan={8} className="text-destructive h-28 text-center">
                        加载聊天流失败
                      </TableCell>
                    </TableRow>
                  ) : filteredChats.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={8} className="text-muted-foreground h-28 text-center">
                        暂无匹配的聊天流
                      </TableCell>
                    </TableRow>
                  ) : (
                    paginatedChats.map((chat) => (
                      <TableRow
                        key={chat.session_id}
                        role="button"
                        tabIndex={0}
                        aria-label={`查看 ${chat.display_name} 详情`}
                        className="cursor-pointer hover:bg-primary/10 focus-visible:bg-primary/10 focus-visible:outline-primary/60 focus-visible:outline-2 focus-visible:outline-offset-[-2px]"
                        onClick={() => setSelectedChat(chat)}
                        onKeyDown={(event) => {
                          if (event.key === 'Enter' || event.key === ' ') {
                            event.preventDefault()
                            setSelectedChat(chat)
                          }
                        }}
                      >
                        <TableCell className="px-3">
                          <div className="flex min-w-0 items-center gap-3">
                            <ChatStreamAvatar chat={chat} />
                            <div className="min-w-0">
                              <HoverScrollText
                                className="font-medium"
                                maxChars={12}
                                value={chat.display_name}
                              />
                            </div>
                          </div>
                        </TableCell>
                        <TableCell className="text-muted-foreground px-2 font-mono text-xs">
                          <HoverScrollText maxChars={4} value={chat.platform} />
                        </TableCell>
                        <TableCell className="text-muted-foreground px-2 font-mono text-xs">
                          <HoverScrollText maxChars={12} value={getChatLogicalId(chat)} />
                        </TableCell>
                        <TableCell className="px-2">
                          <Badge variant="outline">{getChatTypeLabel(chat)}</Badge>
                        </TableCell>
                        <TableCell className="px-2 text-right tabular-nums">
                          {chat.message_count}
                        </TableCell>
                        <TableCell className="px-2 text-right tabular-nums">
                          {chat.expression_count}
                        </TableCell>
                        <TableCell className="px-2 text-right tabular-nums">
                          {chat.jargon_count}
                        </TableCell>
                        <TableCell className="text-muted-foreground px-2">
                          {formatTimestamp(chat.last_active_at)}
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </div>
            <div className="text-muted-foreground flex shrink-0 flex-col gap-2 border-t px-3 py-2 text-xs sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0">
                显示 {visibleStart}-{visibleEnd} / {filteredChats.length} 个聊天流
              </div>
              <div className="flex max-w-full min-w-0 items-center gap-1 overflow-x-auto sm:justify-end">
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7 shrink-0"
                  disabled={currentPage <= 1}
                  aria-label="第一页"
                  onClick={() => setPage(1)}
                >
                  <ChevronsLeft className="h-3.5 w-3.5" />
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7 shrink-0"
                  disabled={currentPage <= 1}
                  aria-label="上一页"
                  onClick={() => setPage((value) => Math.max(1, value - 1))}
                >
                  <ChevronLeft className="h-3.5 w-3.5" />
                </Button>
                <span className="min-w-16 shrink-0 px-1 text-center tabular-nums">
                  {currentPage} / {pageCount}
                </span>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7 shrink-0"
                  disabled={currentPage >= pageCount}
                  aria-label="下一页"
                  onClick={() => setPage((value) => Math.min(pageCount, value + 1))}
                >
                  <ChevronRight className="h-3.5 w-3.5" />
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7 shrink-0"
                  disabled={currentPage >= pageCount}
                  aria-label="最后一页"
                  onClick={() => setPage(pageCount)}
                >
                  <ChevronsRight className="h-3.5 w-3.5" />
                </Button>
              </div>
            </div>
          </section>
        </>
      )}

      <SessionDetailDialog
        chat={selectedChat}
        detail={detailQuery.data}
        loading={detailQuery.isLoading || detailQuery.isFetching}
        error={detailQuery.error}
        open={selectedChat !== null}
        onOpenChange={(open) => !open && setSelectedChat(null)}
      />
      {selectedChat && (
        <div className="flex justify-end">
          <Button
            type="button"
            variant="destructive"
            onClick={() => setDeletingChat(selectedChat)}
          >
            <Trash2 className="mr-2 h-4 w-4" />
            删除聊天流
          </Button>
        </div>
      )}
      <DeleteChatStreamDialog
        chat={deletingChat}
        onDeleted={handleChatDeleted}
        onOpenChange={(open) => !open && setDeletingChat(null)}
      />
    </main>
  )
}