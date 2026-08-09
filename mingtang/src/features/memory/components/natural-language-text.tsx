import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Badge } from '@/components/ui/badge'

import { NATURAL_LANGUAGE_TEXT_STYLE } from '../utils/format'
import {
  buildAvatarFallbackText,
  parseNaturalTextBlocks,
  type ReasoningPromptMessageAvatarMap,
} from '../utils/tag-parse'

function renderMessageTagMeta(attrs: Record<string, string>, avatarMap: ReasoningPromptMessageAvatarMap) {
  const user = attrs.user || ''
  const time = attrs.time || ''
  const msgId = attrs.msg_id || ''
  const chatId = attrs.chat_id || ''
  const avatar = msgId ? avatarMap[msgId] : undefined
  const avatarLabel = avatar?.display_name || user || avatar?.user_id || '用户'

  return (
    <div className="text-muted-foreground mb-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
      {avatar && (
        <Avatar className="h-6 w-6 shrink-0 border bg-background">
          {avatar.avatar_url && <AvatarImage src={avatar.avatar_url} alt={`${avatarLabel} 的头像`} />}
          <AvatarFallback className="text-[10px]">
            {buildAvatarFallbackText(avatarLabel, avatar.user_id)}
          </AvatarFallback>
        </Avatar>
      )}
      {user && (
        <Badge variant="outline" className="px-1.5 py-0 text-[11px]">
          {user}
        </Badge>
      )}
      {time && <span>{time}</span>}
      {msgId && (
        <span className="max-w-full truncate" title={msgId}>
          msg {msgId}
        </span>
      )}
      {chatId && (
        <span className="max-w-full truncate" title={chatId}>
          chat {chatId}
        </span>
      )}
    </div>
  )
}

export function NaturalLanguageText({
  text,
  avatarMap = {},
}: {
  text: string
  avatarMap?: ReasoningPromptMessageAvatarMap
}) {
  const blocks = parseNaturalTextBlocks(text)
  const baseClassName = 'text-foreground text-sm leading-6 whitespace-pre-wrap'
  if (blocks.length === 1 && blocks[0].type === 'text') {
    return (
      <pre className={baseClassName} style={NATURAL_LANGUAGE_TEXT_STYLE}>
        {blocks[0].text}
      </pre>
    )
  }

  return (
    <div className="space-y-2" style={NATURAL_LANGUAGE_TEXT_STYLE}>
      {blocks.map((block, index) => {
        if (block.type === 'text') {
          return (
            <pre key={`text-${index}`} className={baseClassName}>
              {block.text.trim()}
            </pre>
          )
        }

        return (
          <div key={`message-${index}`} className="border-primary/60 pl-2 border-l-2">
            {renderMessageTagMeta(block.attrs, avatarMap)}
            <pre className={baseClassName}>{block.body || '空消息'}</pre>
          </div>
        )
      })}
    </div>
  )
}
