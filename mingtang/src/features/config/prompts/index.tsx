import { useState, useMemo, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { PageShell } from '@/components/biz/page-shell'
import { LoadingSkeleton } from '@/components/biz/loading-skeleton'
import { Button } from '@/components/ui/button'
import { CodeEditor } from '../components/code-editor'
import { RefreshCw, Save, FileText, GitBranch } from 'lucide-react'
import {
  getPromptCatalog,
  getPromptFile,
  updatePromptFile,
  type PromptCatalog,
  type PromptFileContent,
} from '@/lib/prompt-api'

/** Prompt 管理页（/config/prompts）——语言 Select + 文件列表 + 编辑卡片 + 版本管理 */
export function PromptManagementPage() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()

  const [selectedLang, setSelectedLang] = useState('zh')
  const [selectedFile, setSelectedFile] = useState<string | null>(null)
  const [draft, setDraft] = useState('')

  const { data: catalog, isLoading } = useQuery({
    queryKey: ['api', 'prompts', 'catalog'],
    queryFn: getPromptCatalog,
  })

  const files = useMemo(() => {
    if (!catalog) return []
    return (catalog as PromptCatalog).files?.[selectedLang] ?? []
  }, [catalog, selectedLang])

  const { data: fileContent } = useQuery({
    queryKey: ['api', 'prompts', 'file', selectedLang, selectedFile],
    queryFn: () => getPromptFile(selectedLang, selectedFile!),
    enabled: !!selectedFile,
  })

  useEffect(() => {
    if (fileContent) {
      setDraft((fileContent as PromptFileContent).content ?? '')
    }
  }, [fileContent])

  const saveMutation = useMutation({
    mutationFn: () => updatePromptFile(selectedLang, selectedFile!, draft),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['api', 'prompts'] })
    },
  })

  const handleFileSelect = (filename: string) => {
    setSelectedFile(filename)
    setDraft('')
  }

  return (
    <PageShell
      title={t('sidebar.menu.promptManagement')}
      breadcrumb={[t('sidebar.groups.botConfig')]}
      actions={
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => queryClient.invalidateQueries({ queryKey: ['api', 'prompts'] })}
            data-testid="prompts-refresh"
          >
            <RefreshCw className="h-4 w-4 mr-1" />
            刷新
          </Button>
          {selectedFile && (
            <Button
              size="sm"
              onClick={() => saveMutation.mutate()}
              disabled={saveMutation.isPending}
              data-testid="prompts-save"
            >
              <Save className="h-4 w-4 mr-1" />
              保存
            </Button>
          )}
        </div>
      }
    >
      {isLoading ? <LoadingSkeleton /> : (
        <div className="space-y-4">
          {/* 语言选择 */}
          <div className="flex items-center gap-2">
            <label className="text-sm text-muted-foreground">语言</label>
            <select
              value={selectedLang}
              onChange={(e) => setSelectedLang(e.target.value)}
              className="px-2 py-1 text-sm rounded border border-border bg-background"
              data-testid="prompts-lang-select"
            >
              <option value="zh">中文</option>
              <option value="en">English</option>
              <option value="ja">日本語</option>
            </select>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-[200px_1fr] gap-4">
            {/* 左栏文件列表 */}
            <div className="space-y-1" data-testid="prompts-file-list">
              {files.map((file) => (
                <button
                  key={file.name}
                  onClick={() => handleFileSelect(file.name)}
                  data-testid={`prompts-file-${file.name}`}
                  className={`w-full text-left px-3 py-2 text-sm rounded flex items-center gap-2 ${
                    selectedFile === file.name
                      ? 'bg-muted font-medium'
                      : 'hover:bg-muted/50'
                  }`}
                >
                  <FileText className="h-3.5 w-3.5" />
                  {file.name}
                  {file.custom_version_count > 0 && (
                    <span className="ml-auto text-xs text-muted-foreground">
                      <GitBranch className="h-3 w-3 inline" />
                      {file.custom_version_count}
                    </span>
                  )}
                </button>
              ))}
            </div>

            {/* 右栏编辑卡片 */}
            <div data-testid="prompts-editor">
              {selectedFile ? (
                <div className="space-y-2">
                  <h3 className="font-semibold">{selectedFile}</h3>
                  <CodeEditor
                    value={draft}
                    onChange={setDraft}
                    language="text"
                    height="500px"
                    placeholder="提示词内容..."
                  />
                </div>
              ) : (
                <div className="flex items-center justify-center h-full text-muted-foreground">
                  请选择一个文件
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </PageShell>
  )
}
