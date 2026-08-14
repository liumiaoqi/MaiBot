/**
 * ImportTab —— 导入面板编排容器（schema 化重构版，从 1422 行收敛到 ~50 行）。
 *
 * 职责只剩布局编排：左列（创建导入任务 Card1 + 路径预检 Card2）+
 * 右列（导入队列 Card3）+ 底部任务详情（Card4）。
 * 具体卡片组件在 ./ 下（import-create-card / common-params-form / mode-forms /
 * path-precheck-card / import-queue-card / import-task-detail-card），
 * 字段声明在 import-mode-schemas，提交收敛在 hooks/useImportForm。
 */
import { TabsContent } from '@/components/ui/tabs'

import type { UseImportFormResult } from '../../hooks/useImportForm'
import type { UseImportQueueResult } from '../../hooks/useImportQueue'
import { ImportCreateCard } from './import-create-card'
import { ImportQueueCard } from './import-queue-card'
import { ImportTaskDetailCard } from './import-task-detail-card'
import { PathPrecheckCard } from './path-precheck-card'

export interface ImportTabProps {
  queue: UseImportQueueResult
  form: UseImportFormResult
}

export function ImportTab({ queue, form }: ImportTabProps) {
  return (
    <TabsContent
      value="import"
      className="space-y-6 [&_input]:h-10 [&_[role=combobox]]:h-10 [&_textarea]:min-h-[96px]"
    >
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div className="order-2 space-y-6 lg:order-1">
          <ImportCreateCard form={form} />
          <PathPrecheckCard form={form} />
        </div>
        <div className="order-1 space-y-6 lg:order-2">
          <ImportQueueCard queue={queue} />
        </div>
      </div>
      <ImportTaskDetailCard queue={queue} />
    </TabsContent>
  )
}
