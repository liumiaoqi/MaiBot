/**
 * MutualGroupsView 共享组管理（R3-2-4）
 *
 * 从 dashboard routes/chat-management.tsx 1257-1626 行搬移。
 * 三类共享组（表达/黑话/记忆）+ 新建/添加/删除 + 搜索多选 50 条 + 成员徽章
 *
 * 适配点：
 * - useToast → sonner toast()
 * - DialogBody → ScrollArea（R3-W-12 教训）
 * - CSSProperties dialog width → className max-w
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2, X } from 'lucide-react'
import { useMemo, useState } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Skeleton } from '@/components/ui/skeleton'
import { getBotConfig, updateBotConfigSection } from '@/lib/config-api'
import type { ChatStream } from '@/lib/chat-management-api'
import { toast } from 'sonner'

import {
  chatToTarget,
  getChatLogicalId,
  getChatTypeText,
  MUTUAL_GROUP_CHAT_RESULT_LIMIT,
  MUTUAL_GROUP_KIND_LABEL,
  normalizeMutualGroups,
  serializeMutualGroups,
  targetKey,
  targetLabel,
  getTargetDisplayName,
  type ChatStreamGroupConfig,
  type MutualGroupKind,
  type TargetItem,
} from '../chat-management-utils'

/** 共享组管理视图 */
function MutualGroupsView({ chats }: { chats: ChatStream[] }) {
  const queryClient = useQueryClient()
  const [kind, setKind] = useState<MutualGroupKind>(() => {
    if (typeof window === 'undefined') {
      return 'expression'
    }
    const queryKind = new URLSearchParams(window.location.search).get('kind')
    return queryKind === 'memory' || queryKind === 'jargon' ? queryKind : 'expression'
  })
  const [addDialogGroupIndex, setAddDialogGroupIndex] = useState<number | null>(null)
  const [addDialogSearch, setAddDialogSearch] = useState('')
  const [selectedTargetKeys, setSelectedTargetKeys] = useState<string[]>([])
  const configQuery = useQuery({
    queryKey: ['chat-management-mutual-groups-config'],
    queryFn: () => getBotConfig(),
  })
  const sectionName = kind === 'memory' ? 'a_memorix' : kind
  const groupFieldName =
    kind === 'memory'
      ? 'shared_memory_groups'
      : kind === 'expression'
        ? 'expression_groups'
        : 'jargon_groups'
  const sectionData = useMemo(
    () => (configQuery.data?.[sectionName] && typeof configQuery.data[sectionName] === 'object'
      ? configQuery.data[sectionName]
      : {}) as Record<string, unknown>,
    [configQuery.data, sectionName]
  )
  const globalMemorySharingEnabled =
    kind === 'memory' && sectionData.global_memory_sharing_enabled === true
  const groups = useMemo(
    () => normalizeMutualGroups(sectionData[groupFieldName]),
    [groupFieldName, sectionData]
  )
  const addDialogGroup = addDialogGroupIndex === null ? null : (groups[addDialogGroupIndex] ?? null)
  const selectedTargetKeySet = useMemo(() => new Set(selectedTargetKeys), [selectedTargetKeys])
  const addDialogExistingKeySet = useMemo(
    () => new Set((addDialogGroup?.targets ?? []).map(targetKey)),
    [addDialogGroup]
  )
  const chatNameByTargetKey = useMemo(
    () => new Map(chats.map((chat) => [targetKey(chatToTarget(chat)), chat.display_name])),
    [chats]
  )
  const addDialogChats = useMemo(() => {
    const keyword = addDialogSearch.trim().toLowerCase()
    return chats.filter((chat) => {
      const target = chatToTarget(chat)
      if (addDialogExistingKeySet.has(targetKey(target))) {
        return false
      }
      if (!keyword) {
        return true
      }
      return [
        chat.display_name,
        chat.platform,
        getChatLogicalId(chat),
        chat.user_id,
        chat.group_id,
        chat.session_id,
        getChatTypeText(chat.chat_type),
      ]
        .join(' ')
        .toLowerCase()
        .includes(keyword)
    })
  }, [addDialogExistingKeySet, addDialogSearch, chats])
  const visibleAddDialogChats = addDialogChats.slice(0, MUTUAL_GROUP_CHAT_RESULT_LIMIT)
  const isAddDialogLimited = addDialogChats.length > visibleAddDialogChats.length

  const saveMutation = useMutation({
    mutationFn: (nextSectionData: Record<string, unknown>) =>
      updateBotConfigSection(sectionName, nextSectionData),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['chat-management-mutual-groups-config'] })
      toast.success('共享组已保存', {
        description: `${MUTUAL_GROUP_KIND_LABEL[kind]}共享组配置已更新。`,
      })
    },
    onError: (error) => {
      toast.error('保存共享组失败', {
        description: error instanceof Error ? error.message : '请稍后重试',
      })
    },
  })

  const updateGroups = (nextGroups: ChatStreamGroupConfig[]) => {
    if (globalMemorySharingEnabled) {
      return
    }
    saveMutation.mutate({
      ...sectionData,
      [groupFieldName]: serializeMutualGroups(nextGroups),
    })
  }

  const createGroup = () => {
    if (globalMemorySharingEnabled) {
      return
    }
    updateGroups([...groups, { targets: [] }])
  }

  const openAddDialog = (groupIndex: number) => {
    if (globalMemorySharingEnabled) {
      return
    }
    setAddDialogGroupIndex(groupIndex)
    setAddDialogSearch('')
    setSelectedTargetKeys([])
  }

  const closeAddDialog = () => {
    setAddDialogGroupIndex(null)
    setAddDialogSearch('')
    setSelectedTargetKeys([])
  }

  const toggleAddDialogChat = (target: TargetItem) => {
    const key = targetKey(target)
    setSelectedTargetKeys((currentKeys) =>
      currentKeys.includes(key)
        ? currentKeys.filter((currentKey) => currentKey !== key)
        : [...currentKeys, key]
    )
  }

  const applySelectedChatsToGroup = () => {
    if (globalMemorySharingEnabled || addDialogGroupIndex === null || selectedTargetKeys.length === 0) {
      return
    }
    const selectedKeySet = new Set(selectedTargetKeys)
    const selectedTargets = chats
      .map(chatToTarget)
      .filter((target) => selectedKeySet.has(targetKey(target)))
    const nextGroups = groups.map((group, index) => {
      if (index !== addDialogGroupIndex) {
        return group
      }
      const targets = group.targets ?? []
      const existingKeys = new Set(targets.map(targetKey))
      const nextTargets = selectedTargets.filter((target) => !existingKeys.has(targetKey(target)))
      return { targets: [...targets, ...nextTargets] }
    })
    updateGroups(nextGroups)
    closeAddDialog()
  }

  const removeTarget = (groupIndex: number, targetIndex: number) => {
    if (globalMemorySharingEnabled) {
      return
    }
    updateGroups(
      groups.map((group, index) =>
        index === groupIndex
          ? {
              targets: (group.targets ?? []).filter(
                (_, memberIndex) => memberIndex !== targetIndex
              ),
            }
          : group
      )
    )
  }

  const deleteGroup = (groupIndex: number) => {
    if (globalMemorySharingEnabled) {
      return
    }
    updateGroups(groups.filter((_, index) => index !== groupIndex))
  }
  const editingDisabled = saveMutation.isPending || globalMemorySharingEnabled

  return (
    <section className="bg-background flex min-h-0 flex-1 flex-col overflow-hidden rounded-md border">
      <div className="flex shrink-0 flex-col gap-3 border-b p-4 lg:flex-row lg:items-end lg:justify-between">
        <div className="space-y-1">
          <h2 className="text-base font-semibold">共享组管理</h2>
          <p className="text-sm text-muted-foreground">
            管理表达、黑话和记忆的聊天流共享组。
          </p>
        </div>
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <div className="bg-background inline-flex rounded-md border p-1">
            {([
              ['expression', '表达'],
              ['jargon', '黑话'],
              ['memory', '记忆'],
            ] as const).map(([value, label]) => (
              <Button
                key={value}
                type="button"
                variant={kind === value ? 'secondary' : 'ghost'}
                size="sm"
                className="h-8"
                onClick={() => setKind(value)}
              >
                {label}
              </Button>
            ))}
          </div>
          <Button type="button" disabled={editingDisabled} onClick={createGroup}>
            <Plus className="mr-2 h-4 w-4" />
            新建共享组
          </Button>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-auto p-4">
        {globalMemorySharingEnabled && (
          <div className="mb-3 rounded-md border bg-muted/30 px-3 py-2 text-sm text-muted-foreground">
            全局共享记忆已开启，记忆共享组暂不参与普通记忆检索范围控制。
          </div>
        )}
        {configQuery.isLoading ? (
          <div className="space-y-3">
            <Skeleton className="h-20" />
            <Skeleton className="h-20" />
          </div>
        ) : configQuery.error ? (
          <div className="border-destructive/40 text-destructive rounded-md border p-4 text-sm">
            加载共享组失败
          </div>
        ) : groups.length === 0 ? (
          <div className="text-muted-foreground rounded-md border border-dashed p-6 text-center text-sm">
            暂无{MUTUAL_GROUP_KIND_LABEL[kind]}共享组。
          </div>
        ) : (
          <div className="grid gap-3">
            {groups.map((group, groupIndex) => (
              <div key={groupIndex} className="rounded-md border p-3">
                <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                  <div className="font-medium">共享组 {groupIndex + 1}</div>
                  <div className="flex items-center gap-2">
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      disabled={editingDisabled}
                      onClick={() => openAddDialog(groupIndex)}
                    >
                      <Plus className="mr-2 h-4 w-4" />
                      添加聊天
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      className="text-destructive hover:text-destructive"
                      disabled={editingDisabled}
                      aria-label={`删除共享组 ${groupIndex + 1}`}
                      onClick={() => deleteGroup(groupIndex)}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  {(group.targets ?? []).length === 0 ? (
                    <span className="text-muted-foreground text-sm">空共享组</span>
                  ) : (
                    (group.targets ?? []).map((target, targetIndex) => (
                      <Badge
                        key={`${targetKey(target)}:${targetIndex}`}
                        variant="outline"
                        className="gap-2"
                        title={targetLabel(target)}
                      >
                        <span className="max-w-48 truncate text-xs">
                          {getTargetDisplayName(target, chatNameByTargetKey)}
                        </span>
                        <button
                          type="button"
                          className="text-muted-foreground hover:text-destructive"
                          disabled={editingDisabled}
                          aria-label={`移除 ${getTargetDisplayName(target, chatNameByTargetKey)}`}
                          onClick={() => removeTarget(groupIndex, targetIndex)}
                        >
                          <X className="h-3 w-3" />
                        </button>
                      </Badge>
                    ))
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <Dialog
        open={addDialogGroupIndex !== null}
        onOpenChange={(open) => !open && closeAddDialog()}
      >
        <DialogContent className="max-w-[min(calc(100vw-2rem),42rem)]">
          <DialogHeader>
            <DialogTitle>添加聊天</DialogTitle>
            <DialogDescription>
              选择要加入共享组 {addDialogGroupIndex === null ? '' : addDialogGroupIndex + 1}{' '}
              的聊天流。
            </DialogDescription>
          </DialogHeader>
          <ScrollArea className="max-h-[24rem]">
            <div className="pr-4 space-y-3">
              <Input
                value={addDialogSearch}
                onChange={(event) => setAddDialogSearch(event.target.value)}
                placeholder="搜索名称、平台、用户、群号或会话 ID"
              />
              <div className="max-h-[22rem] overflow-auto rounded-md border">
                {addDialogChats.length === 0 ? (
                  <div className="text-muted-foreground p-4 text-center text-sm">
                    没有可加入的聊天流
                  </div>
                ) : (
                  <div className="divide-y">
                    {visibleAddDialogChats.map((chat) => {
                      const target = chatToTarget(chat)
                      const key = targetKey(target)
                      const checked = selectedTargetKeySet.has(key)
                      return (
                        <label
                          key={chat.session_id}
                          className="hover:bg-muted/60 flex cursor-pointer items-center gap-3 px-3 py-2"
                        >
                          <Checkbox
                            checked={checked}
                            onCheckedChange={() => toggleAddDialogChat(target)}
                            aria-label={`选择 ${chat.display_name}`}
                          />
                          <div className="min-w-0 flex-1">
                            <div className="truncate text-sm font-medium">{chat.display_name}</div>
                            <div className="text-muted-foreground truncate font-mono text-xs">
                              {chat.platform}:{getChatLogicalId(chat)}
                            </div>
                          </div>
                          <Badge variant="outline">{getChatTypeText(chat.chat_type)}</Badge>
                        </label>
                      )
                    })}
                  </div>
                )}
              </div>
              {isAddDialogLimited && (
                <div className="text-xs text-muted-foreground">
                  仅显示前 {MUTUAL_GROUP_CHAT_RESULT_LIMIT} 个匹配项，请输入关键词缩小范围。
                </div>
              )}
            </div>
          </ScrollArea>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={closeAddDialog}>
              取消
            </Button>
            <Button
              type="button"
              disabled={selectedTargetKeys.length === 0 || editingDisabled}
              onClick={applySelectedChatsToGroup}
            >
              加入 {selectedTargetKeys.length} 个聊天
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  )
}

export { MutualGroupsView }