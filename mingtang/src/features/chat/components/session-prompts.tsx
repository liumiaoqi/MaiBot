/**
 * SessionPrompts 聊天 Prompt 区块（R3-2-3 第④区块）
 *
 * 从 dashboard routes/chat-management.tsx 1067-1255 行搬移。
 * 包含：PromptTextBlock + PromptRuleEditor + NewPromptEditor + ChatPromptSection
 *
 * 适配点：useToast → sonner toast()
 */
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Edit3, Plus, Save, Trash2 } from 'lucide-react'
import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import {
  deleteChatStreamPrompt,
  upsertChatStreamPrompt,
  type ChatPromptRule,
  type ChatStreamDetail,
} from '@/lib/chat-management-api'
import { toast } from 'sonner'

/** Prompt 文本块（只读展示） */
function PromptTextBlock({
  content,
  emptyText,
  title,
}: {
  content: string
  emptyText: string
  title: string
}) {
  const normalizedContent = content.trim()
  return (
    <div className="space-y-2">
      <div className="text-sm font-medium">{title}</div>
      {normalizedContent ? (
        <pre className="bg-muted/25 text-foreground max-h-40 overflow-auto rounded-md border p-3 text-xs leading-5 break-words whitespace-pre-wrap">
          {normalizedContent}
        </pre>
      ) : (
        <div className="text-muted-foreground rounded-md border border-dashed px-3 py-2 text-sm">
          {emptyText}
        </div>
      )}
    </div>
  )
}

/** 专属 Prompt 规则编辑器 */
function PromptRuleEditor({
  detail,
  prompt,
}: {
  detail: ChatStreamDetail
  prompt: ChatPromptRule
}) {
  const queryClient = useQueryClient()
  const [draft, setDraft] = useState(prompt.prompt)
  const saveMutation = useMutation({
    mutationFn: () => upsertChatStreamPrompt(detail.session_id, { prompt: draft }, prompt.index),
    onSuccess: (nextDetail) => {
      queryClient.setQueryData(['chat-stream-detail', detail.session_id], nextDetail)
      toast.success('聊天 Prompt 已保存')
    },
    onError: (error) => {
      toast.error('聊天 Prompt 保存失败', {
        description: error instanceof Error ? error.message : '请稍后重试',
      })
    },
  })
  const deleteMutation = useMutation({
    mutationFn: () => deleteChatStreamPrompt(detail.session_id, prompt.index),
    onSuccess: (nextDetail) => {
      queryClient.setQueryData(['chat-stream-detail', detail.session_id], nextDetail)
      toast.success('聊天 Prompt 已删除')
    },
    onError: (error) => {
      toast.error('聊天 Prompt 删除失败', {
        description: error instanceof Error ? error.message : '请稍后重试',
      })
    },
  })
  const isBusy = saveMutation.isPending || deleteMutation.isPending
  const normalizedDraft = draft.trim()
  const changed = normalizedDraft !== prompt.prompt.trim()

  // prompt 变化 → 填充草稿——渲染期调整模式（R3 审核修复：rAF 规避 → React 官方模式）
  const [prevPromptText, setPrevPromptText] = useState(prompt.prompt)
  if (prompt.prompt !== prevPromptText) {
    setPrevPromptText(prompt.prompt)
    setDraft(prompt.prompt)
  }

  return (
    <div className="bg-muted/20 space-y-2 rounded-md border p-3">
      <div className="flex items-center justify-between gap-3">
        <div className="text-muted-foreground min-w-0 text-xs">
          专属目标：
          <span className="font-mono break-all">
            {prompt.platform}:{prompt.item_id}:{prompt.rule_type}
          </span>
        </div>
        <Button
          type="button"
          size="icon"
          variant="ghost"
          disabled={isBusy}
          aria-label="删除聊天 Prompt"
          onClick={() => deleteMutation.mutate()}
        >
          <Trash2 className="text-destructive h-4 w-4" />
        </Button>
      </div>
      <Textarea
        value={draft}
        disabled={isBusy}
        onChange={(event) => setDraft(event.target.value)}
        className="min-h-24 text-xs leading-5"
      />
      <div className="flex justify-end">
        <Button
          type="button"
          size="sm"
          disabled={!changed || !normalizedDraft || isBusy}
          onClick={() => saveMutation.mutate()}
        >
          <Save className="mr-2 h-3.5 w-3.5" />
          保存
        </Button>
      </div>
    </div>
  )
}

/** 新增 Prompt 编辑器 */
function NewPromptEditor({ detail }: { detail: ChatStreamDetail }) {
  const queryClient = useQueryClient()
  const [draft, setDraft] = useState('')
  const saveMutation = useMutation({
    mutationFn: () => upsertChatStreamPrompt(detail.session_id, { prompt: draft }),
    onSuccess: (nextDetail) => {
      setDraft('')
      queryClient.setQueryData(['chat-stream-detail', detail.session_id], nextDetail)
      toast.success('聊天 Prompt 已新增')
    },
    onError: (error) => {
      toast.error('聊天 Prompt 新增失败', {
        description: error instanceof Error ? error.message : '请稍后重试',
      })
    },
  })
  const normalizedDraft = draft.trim()

  return (
    <div className="space-y-2 rounded-md border border-dashed p-3">
      <div className="flex items-center gap-2 text-sm font-medium">
        <Edit3 className="h-4 w-4" />
        新增当前聊天流专属 Prompt
      </div>
      <Textarea
        value={draft}
        disabled={saveMutation.isPending}
        onChange={(event) => setDraft(event.target.value)}
        placeholder="只写这个聊天流额外需要遵守的发言要求。"

        className="min-h-24 text-xs leading-5"
      />
      <div className="flex justify-end">
        <Button
          type="button"
          size="sm"
          disabled={!normalizedDraft || saveMutation.isPending}
          onClick={() => saveMutation.mutate()}
        >
          <Plus className="mr-2 h-3.5 w-3.5" />
          新增
        </Button>
      </div>
    </div>
  )
}

/** 聊天 Prompt 区块 */
function SessionPrompts({ detail }: { detail: ChatStreamDetail }) {
  return (
    <section className="space-y-3 rounded-md border p-3">
      <div className="font-medium">聊天 Prompt</div>
      <PromptTextBlock
        title={detail.prompts.base_prompt_title}
        content={detail.prompts.base_prompt}
        emptyText="当前基础 Prompt 为空。"
      />
      <div className="space-y-2">
        <div className="text-sm font-medium">额外聊天流 Prompt</div>
        {detail.prompts.chat_prompts.length === 0 ? (
          <div className="text-muted-foreground rounded-md border border-dashed px-3 py-2 text-sm">
            当前聊天流没有专属额外 Prompt。
          </div>
        ) : (
          <div className="space-y-2">
            {detail.prompts.chat_prompts.map((prompt, index) => (
              <PromptRuleEditor key={`${prompt.index}:${index}`} detail={detail} prompt={prompt} />
            ))}
          </div>
        )}
      </div>
      <NewPromptEditor detail={detail} />
    </section>
  )
}

export { NewPromptEditor, PromptRuleEditor, PromptTextBlock, SessionPrompts }