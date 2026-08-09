/**
 * SessionBasicInfo 基本信息区块（R3-2-3 第①区块）
 *
 * 从 dashboard routes/chat-management.tsx 1651-1658 + 1689-1702 行搬移。
 * 包含：CompactDetailItem + Session ID/Platform/Type/ID 展示。
 */
import type { ReactNode } from 'react'

import type { ChatStreamDetail } from '@/lib/chat-management-api'

import { getChatTypeText } from '../chat-management-utils'

/** 紧凑详情项（标签 + 值） */
function CompactDetailItem({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="min-w-0 space-y-1">
      <div className="text-muted-foreground text-xs">{label}</div>
      <div className="min-w-0 text-sm font-medium break-all">{value}</div>
    </div>
  )
}

/** 基本信息区块 */
function SessionBasicInfo({ detail }: { detail: ChatStreamDetail }) {
  return (
    <section className="space-y-3 rounded-md border p-3">
      <CompactDetailItem
        label="Session ID"
        value={<span className="font-mono text-xs font-normal">{detail.session_id}</span>}
      />
      <div className="grid gap-3 sm:grid-cols-3">
        <CompactDetailItem label="Platform" value={detail.platform || '-'} />
        <CompactDetailItem label="Type" value={getChatTypeText(detail.chat_type)} />
        <CompactDetailItem
          label="ID"
          value={<span className="font-mono">{detail.target_id || '-'}</span>}
        />
      </div>
    </section>
  )
}

export { CompactDetailItem, SessionBasicInfo }