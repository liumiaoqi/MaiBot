/**
 * path-precheck-card —— Card2「路径预检」：在创建本地扫描/转换/迁移任务前确认路径解析。
 * 字段（alias/relative_path/must_exist）由 PATH_PRECHECK_SCHEMA 声明、hook 生成 state。
 */
import { Loader2, RefreshCw } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'

import type { UseImportFormResult } from '../../hooks/useImportForm'

export function PathPrecheckCard({ form }: { form: UseImportFormResult }) {
  const {
    pathResolveAlias,
    setPathResolveAlias,
    importAliasKeys,
    pathResolveRelativePath,
    setPathResolveRelativePath,
    pathResolveMustExist,
    setPathResolveMustExist,
    resolveImportPath,
    resolvingPath,
    pathResolveOutput,
  } = form
  return (
    <Card className="rounded-2xl border-border/70 bg-card/85 shadow-sm">
      <CardHeader>
        <CardTitle>路径预检</CardTitle>
        <CardDescription>在创建本地扫描、转换或迁移任务前，先确认路径会被解析到哪里。</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3">
          <div className="space-y-1">
            <Label>路径别名</Label>
            <div className="text-xs text-muted-foreground">选择后端允许访问的数据根目录。</div>
            <Select value={pathResolveAlias} onValueChange={setPathResolveAlias}>
              <SelectTrigger aria-label="import-path-alias">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {importAliasKeys.length > 0 ? importAliasKeys.map((alias) => (
                  <SelectItem key={alias} value={alias}>{alias}</SelectItem>
                )) : (
                  <SelectItem value="raw">raw</SelectItem>
                )}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label>相对路径</Label>
            <div className="text-xs text-muted-foreground">填写相对于路径别名的子路径，不需要填写完整磁盘路径。</div>
            <Input
              value={pathResolveRelativePath}
              onChange={(event) => setPathResolveRelativePath(event.target.value)}
              placeholder="例如 exports/weekly"
            />
          </div>
        </div>
        <div className="flex items-center gap-2 text-sm">
          <Checkbox
            checked={pathResolveMustExist}
            onCheckedChange={(value) => setPathResolveMustExist(Boolean(value))}
          />
          要求路径已存在
        </div>
        <Button
          variant="outline"
          onClick={() => void resolveImportPath()}
          disabled={resolvingPath || !pathResolveAlias.trim()}
        >
          {resolvingPath ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-2 h-4 w-4" />}
          解析路径
        </Button>
        <Textarea value={pathResolveOutput} readOnly rows={6} placeholder="解析结果会显示在这里" />
      </CardContent>
    </Card>
  )
}
