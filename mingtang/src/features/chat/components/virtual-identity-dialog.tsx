/**
 * 虚拟身份创建弹窗（孤儿补全——ADR-6）
 *
 * 从 dashboard routes/chat/VirtualIdentityDialog.tsx 搬移适配（224 行——行为等价）。
 * dashboard 原版组件完整但无"新建虚拟会话"入口——R3 在 ChatWorkspaceSidebar 补入口触发本弹窗。
 *
 * 适配点：
 * - mingtang dialog 无 DialogBody/confirmOnEnter 扩展——用标准 DialogContent + ScrollArea 替代
 * - 确认按钮加 data-dialog-action="confirm" / 取消按钮加 data-dialog-cancel="true" 便于测试查询
 *
 * 核心职责（REQ-R3-05 孤儿补全）：
 * - person-api 加载身份数据源（platforms/persons 由父组件传入）
 * - 平台选择 → 用户搜索 → 选择用户 → 虚拟群名 → 创建虚拟会话
 * - localStorage 持久化由父组件通过 onCreateVirtualTab 处理
 */
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Button } from '@/components/ui/button'
import {
  Dialog,
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
import { cn } from '@/lib/utils'
import { Globe, Loader2, Search, UserCircle2, Users } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import type { PersonInfo, PlatformInfo, VirtualIdentityConfig } from '../types'

interface VirtualIdentityDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  platforms: PlatformInfo[]
  persons: PersonInfo[]
  isLoadingPlatforms: boolean
  isLoadingPersons: boolean
  personSearchQuery: string
  setPersonSearchQuery: (query: string) => void
  tempVirtualConfig: VirtualIdentityConfig
  setTempVirtualConfig: React.Dispatch<React.SetStateAction<VirtualIdentityConfig>>
  onSelectPerson: (person: PersonInfo) => void
  onCreateVirtualTab: () => void
}

/**
 * 虚拟身份创建弹窗。
 *
 * 选择平台 → 搜索用户 → 选择用户 → 可选虚拟群名 → 创建虚拟会话标签。
 */
export function VirtualIdentityDialog({
  open,
  onOpenChange,
  platforms,
  persons,
  isLoadingPlatforms,
  isLoadingPersons,
  personSearchQuery,
  setPersonSearchQuery,
  tempVirtualConfig,
  setTempVirtualConfig,
  onSelectPerson,
  onCreateVirtualTab,
}: VirtualIdentityDialogProps) {
  const { t } = useTranslation()

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[85vh] flex-col overflow-hidden sm:max-w-[32rem]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <UserCircle2 className="h-5 w-5" />
            {t('chat.dialog.title')}
          </DialogTitle>
          <DialogDescription>{t('chat.dialog.description')}</DialogDescription>
        </DialogHeader>

        <div className="flex-1 space-y-4 overflow-hidden">
          {/* 平台选择 */}
          <div className="space-y-2">
            <Label className="flex items-center gap-2">
              <Globe className="h-4 w-4" />
              {t('chat.dialog.platform')}
            </Label>
            <Select
              value={tempVirtualConfig.platform}
              onValueChange={(value) => {
                setTempVirtualConfig((prev) => ({
                  ...prev,
                  platform: value,
                  personId: '',
                  userId: '',
                  userName: '',
                }))
              }}
            >
              <SelectTrigger disabled={isLoadingPlatforms}>
                <SelectValue
                  placeholder={
                    isLoadingPlatforms
                      ? t('chat.dialog.loading')
                      : t('chat.dialog.platformPlaceholder')
                  }
                />
              </SelectTrigger>
              <SelectContent>
                {platforms.map((p) => (
                  <SelectItem key={p.platform} value={p.platform}>
                    {p.platform} {t('chat.dialog.personCount', { count: p.count })}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* 用户搜索和选择 */}
          {tempVirtualConfig.platform && (
            <div className="flex flex-1 flex-col space-y-2 overflow-hidden">
              <Label className="flex items-center gap-2">
                <Users className="h-4 w-4" />
                {t('chat.dialog.user')}
              </Label>
              <div className="relative">
                <Search className="text-muted-foreground absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2" />
                <Input
                  placeholder={t('chat.dialog.searchUser')}
                  value={personSearchQuery}
                  onChange={(e) => setPersonSearchQuery(e.target.value)}
                  className="pl-9"
                />
              </div>
              <ScrollArea className="bg-background/40 h-62.5 rounded-lg border">
                <div className="p-1.5">
                  {isLoadingPersons ? (
                    <div className="flex items-center justify-center py-10">
                      <Loader2 className="text-muted-foreground h-6 w-6 animate-spin" />
                    </div>
                  ) : persons.length === 0 ? (
                    <div className="text-muted-foreground flex flex-col items-center justify-center py-10">
                      <Users className="mb-2 h-8 w-8 opacity-50" />
                      <p className="text-sm">{t('chat.dialog.noUsers')}</p>
                    </div>
                  ) : (
                    <div className="space-y-0.5">
                      {persons.map((person) => {
                        const selected = tempVirtualConfig.personId === person.person_id
                        const display = person.nickname || person.person_name
                        return (
                          <button
                            key={person.person_id}
                            type="button"
                            onClick={() => onSelectPerson(person)}
                            className={cn(
                              'flex w-full items-center gap-3 rounded-md p-2 text-left transition-colors',
                              selected
                                ? 'bg-primary/12 text-foreground'
                                : 'hover:bg-muted/70'
                            )}
                          >
                            <Avatar className="h-9 w-9 shrink-0 ring-1 ring-border/60">
                              <AvatarFallback
                                className={cn(
                                  'text-xs font-semibold',
                                  selected
                                    ? 'bg-primary text-primary-foreground'
                                    : 'bg-muted text-foreground'
                                )}
                              >
                                {(display || '?').charAt(0).toUpperCase()}
                              </AvatarFallback>
                            </Avatar>
                            <div className="min-w-0 flex-1">
                              <div className="flex items-center gap-1.5">
                                <span className="truncate text-sm font-medium">{display}</span>
                                {person.is_known && (
                                  <span className="bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 rounded-full px-1.5 py-0.5 text-[10px] font-medium">
                                    {t('chat.dialog.knownUserSuffix').replace(/^\s*·\s*/, '')}
                                  </span>
                                )}
                              </div>
                              <div className="text-muted-foreground truncate font-mono text-[11px]">
                                {person.user_id}
                              </div>
                            </div>
                          </button>
                        )
                      })}
                    </div>
                  )}
                </div>
              </ScrollArea>
            </div>
          )}

          {/* 虚拟群名配置 */}
          {tempVirtualConfig.personId && (
            <div className="space-y-2">
              <Label>{t('chat.dialog.groupName')}</Label>
              <Input
                placeholder={t('chat.virtualGroupFallback')}
                value={tempVirtualConfig.groupName}
                onChange={(e) =>
                  setTempVirtualConfig((prev) => ({
                    ...prev,
                    groupName: e.target.value,
                  }))
                }
              />
              <p className="text-muted-foreground text-xs">{t('chat.dialog.groupNameHint')}</p>
            </div>
          )}
        </div>

        <DialogFooter className="gap-2 sm:gap-0">
          <Button variant="outline" data-dialog-cancel="true" onClick={() => onOpenChange(false)}>
            {t('chat.actions.cancel')}
          </Button>
          <Button
            data-dialog-action="confirm"
            onClick={onCreateVirtualTab}
            disabled={!tempVirtualConfig.platform || !tempVirtualConfig.personId}
          >
            {t('chat.dialog.create')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}