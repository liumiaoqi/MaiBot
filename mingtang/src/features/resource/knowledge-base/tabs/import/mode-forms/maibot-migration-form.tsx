/**
 * maibot_migration 模式表单（schema 消费渲染）——源库/时间范围/ID 范围/ID 列表 + 高级选项。
 *
 * 保留了旧版专属细节：
 * - 时间与 ID 的交叉约束（起始 ≤ 结束）通过 SchemaField 的 min/max 覆盖实现；
 * - 源库路径必填（required）；
 * - 读取批大小/提交窗口/向量线程数 + 两个迁移开关在「高级选项」details 内。
 * 单字段校验（格式/正整数）由 schema.validate 声明，payload 构建器在提交时执行。
 */
import { SlidersHorizontal } from 'lucide-react'

import { TabsContent } from '@/components/ui/tabs'

import { buildImportFieldMap, IMPORT_MODE_SCHEMAS } from '../../../import-mode-schemas'
import type { UseImportFormResult } from '../../../hooks/useImportForm'
import { SchemaField } from '../schema-field'

export function MaibotMigrationForm({ form }: { form: UseImportFormResult }) {
  const fields = buildImportFieldMap(IMPORT_MODE_SCHEMAS.maibot_migration)
  return (
    <TabsContent value="maibot_migration" className="mt-0">
      <div className="space-y-3 rounded-xl border bg-background/70 p-4">
        <div className="text-xs text-muted-foreground">迁移 MaiBot 历史长期记忆</div>
        <div className="grid gap-3">
          <SchemaField
            id="maibot-source-db"
            required
            field={fields.maibotSourceDb}
            value={form.maibotSourceDb}
            onChange={(value) => form.setMaibotSourceDb(String(value))}
          />
          <div className="grid gap-3 md:grid-cols-2">
            <SchemaField
              id="maibot-time-from"
              field={fields.maibotTimeFrom}
              value={form.maibotTimeFrom}
              max={form.maibotTimeTo || undefined}
              onChange={(value) => form.setMaibotTimeFrom(String(value))}
            />
            <SchemaField
              id="maibot-time-to"
              field={fields.maibotTimeTo}
              value={form.maibotTimeTo}
              min={form.maibotTimeFrom || undefined}
              onChange={(value) => form.setMaibotTimeTo(String(value))}
            />
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            <SchemaField
              id="maibot-start-id"
              field={fields.maibotStartId}
              value={form.maibotStartId}
              max={form.maibotEndId || undefined}
              onChange={(value) => form.setMaibotStartId(String(value))}
            />
            <SchemaField
              id="maibot-end-id"
              field={fields.maibotEndId}
              value={form.maibotEndId}
              min={form.maibotStartId || 1}
              onChange={(value) => form.setMaibotEndId(String(value))}
            />
          </div>
          <SchemaField
            id="maibot-stream-ids"
            field={fields.maibotStreamIds}
            value={form.maibotStreamIds}
            onChange={(value) => form.setMaibotStreamIds(String(value))}
          />
          <SchemaField
            id="maibot-group-ids"
            field={fields.maibotGroupIds}
            value={form.maibotGroupIds}
            onChange={(value) => form.setMaibotGroupIds(String(value))}
          />
          <SchemaField
            id="maibot-user-ids"
            field={fields.maibotUserIds}
            value={form.maibotUserIds}
            onChange={(value) => form.setMaibotUserIds(String(value))}
          />
        </div>
        <details className="rounded-md border bg-background/70 p-3 text-sm">
          <summary className="flex cursor-pointer items-center gap-2 text-sm font-medium">
            <SlidersHorizontal className="h-4 w-4" />
            高级选项
          </summary>
          <div className="mt-3 grid gap-3">
            <SchemaField
              id="maibot-read-batch-size"
              field={fields.maibotReadBatchSize}
              value={form.maibotReadBatchSize}
              onChange={(value) => form.setMaibotReadBatchSize(String(value))}
            />
            <SchemaField
              id="maibot-commit-window-rows"
              field={fields.maibotCommitWindowRows}
              value={form.maibotCommitWindowRows}
              onChange={(value) => form.setMaibotCommitWindowRows(String(value))}
            />
            <SchemaField
              id="maibot-embed-workers"
              field={fields.maibotEmbedWorkers}
              value={form.maibotEmbedWorkers}
              onChange={(value) => form.setMaibotEmbedWorkers(String(value))}
            />
            <div className="grid gap-2">
              <SchemaField
                field={fields.maibotNoResume}
                value={form.maibotNoResume}
                onChange={(value) => form.setMaibotNoResume(Boolean(value))}
              />
              <SchemaField
                field={fields.maibotResetState}
                value={form.maibotResetState}
                onChange={(value) => form.setMaibotResetState(Boolean(value))}
              />
            </div>
          </div>
        </details>
        <div className="grid gap-2">
          <SchemaField
            field={fields.maibotDryRun}
            value={form.maibotDryRun}
            onChange={(value) => form.setMaibotDryRun(Boolean(value))}
          />
          <SchemaField
            field={fields.maibotVerifyOnly}
            value={form.maibotVerifyOnly}
            onChange={(value) => form.setMaibotVerifyOnly(Boolean(value))}
          />
        </div>
      </div>
    </TabsContent>
  )
}
