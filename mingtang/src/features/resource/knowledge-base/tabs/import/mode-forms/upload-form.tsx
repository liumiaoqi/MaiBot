/**
 * upload 模式表单（schema 消费渲染）——输入模式 + 文件选择。
 * uploadFiles 是 File[] 特殊输入（不进 schema），在此手写。
 */
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { TabsContent } from '@/components/ui/tabs'
import type { MemoryImportInputMode } from '@/lib/memory-api'

import { buildImportFieldMap, IMPORT_MODE_SCHEMAS } from '../../../import-mode-schemas'
import type { UseImportFormResult } from '../../../hooks/useImportForm'
import { SchemaField } from '../schema-field'

export function UploadForm({ form }: { form: UseImportFormResult }) {
  const fields = buildImportFieldMap(IMPORT_MODE_SCHEMAS.upload)
  return (
    <TabsContent value="upload" className="mt-0">
      <div className="space-y-3 rounded-xl border bg-background/70 p-4">
        <div className="text-xs text-muted-foreground">选择一个或多个本地文件创建导入任务，适合批量导入资料或聊天记录。</div>
        <div className="grid gap-3">
          <SchemaField
            field={fields.uploadInputMode}
            value={form.uploadInputMode}
            onChange={(value) => form.setUploadInputMode(value as MemoryImportInputMode)}
          />
          <div className="space-y-1">
            <Label>文件选择</Label>
            <Input
              type="file"
              multiple
              accept=".txt,.md,.json,.jsonl,.csv,.log,.html,.htm,.xml"
              onChange={(event) => form.setUploadFiles(Array.from(event.target.files ?? []))}
            />
          </div>
        </div>
        <div className="text-xs text-muted-foreground">已选择 {form.uploadFiles.length} 个文件</div>
      </div>
    </TabsContent>
  )
}
