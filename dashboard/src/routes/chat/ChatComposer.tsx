import { Send } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'

interface ChatComposerProps {
  value: string
  onChange: (value: string) => void
  onSend: () => void
  disabled: boolean
  isConnected: boolean
}

/**
 * 聊天输入区：自适应高度的输入框 + 浮动发送按钮，带快捷键提示。
 */
export function ChatComposer({ value, onChange, onSend, disabled, isConnected }: ChatComposerProps) {
  const { t } = useTranslation()

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      if (!disabled) onSend()
    }
  }

  const canSend = !disabled && value.trim().length > 0

  return (
    <div className="bg-card/85 supports-backdrop-filter:bg-card/65 shrink-0 border-t backdrop-blur">
      <div className="mx-auto max-w-4xl px-3 py-3 sm:px-6 sm:py-4">
        <div
          className={cn(
            'group bg-background/80 focus-within:border-primary/60 focus-within:ring-primary/20 relative flex items-end gap-2 rounded-2xl border px-3 py-2 shadow-sm transition focus-within:ring-2',
            !isConnected && 'opacity-70'
          )}
        >
          <Textarea
            aria-label={t('chat.input.placeholder')}
            autoResize
            className="max-h-40 min-h-9 flex-1 resize-none border-0 bg-transparent px-1 py-1.5 text-sm shadow-none focus-visible:ring-0"
            disabled={!isConnected}
            maxHeight={160}
            minHeight={36}
            placeholder={isConnected ? t('chat.input.placeholder') : t('chat.input.waiting')}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={handleKeyDown}
          />
          <Button
            aria-label={t('chat.actions.send')}
            className={cn(
              'h-9 w-9 shrink-0 rounded-full transition',
              canSend ? 'shadow-md' : 'opacity-60'
            )}
            disabled={!canSend}
            size="icon"
            title={t('chat.actions.send')}
            onClick={onSend}
          >
            <Send className="h-4 w-4" />
          </Button>
        </div>
        <p className="text-muted-foreground mt-1.5 hidden px-2 text-[11px] sm:block">
          {t('chat.composer.hint')}
        </p>
      </div>
    </div>
  )
}
