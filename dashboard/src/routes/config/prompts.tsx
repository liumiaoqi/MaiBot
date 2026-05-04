import { useCallback, useEffect, useMemo, useState } from 'react'
import { FileText, Loader2, RefreshCw, Save, Search } from 'lucide-react'

import { CodeEditor } from '@/components/CodeEditor'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Separator } from '@/components/ui/separator'
import { useToast } from '@/hooks/use-toast'
import {
  getPromptCatalog,
  getPromptFile,
  updatePromptFile,
  type PromptCatalog,
  type PromptFileInfo,
} from '@/lib/prompt-api'
import { cn } from '@/lib/utils'

function formatFileSize(size: number) {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

export function PromptManagementPage() {
  const { toast } = useToast()
  const [catalog, setCatalog] = useState<PromptCatalog | null>(null)
  const [language, setLanguage] = useState('zh-CN')
  const [filename, setFilename] = useState('')
  const [content, setContent] = useState('')
  const [savedContent, setSavedContent] = useState('')
  const [loadingCatalog, setLoadingCatalog] = useState(true)
  const [loadingFile, setLoadingFile] = useState(false)
  const [saving, setSaving] = useState(false)
  const [query, setQuery] = useState('')

  const hasUnsavedChanges = content !== savedContent

  const promptFiles = useMemo<PromptFileInfo[]>(() => {
    if (!catalog || !language) return []
    return catalog.files[language] ?? []
  }, [catalog, language])

  const filteredFiles = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase()
    if (!normalizedQuery) return promptFiles
    return promptFiles.filter((file) => file.name.toLowerCase().includes(normalizedQuery))
  }, [promptFiles, query])

  const selectedFile = promptFiles.find((file) => file.name === filename)

  const loadCatalog = useCallback(async () => {
    try {
      setLoadingCatalog(true)
      const result = await getPromptCatalog()
      if (!result.success) {
        toast({ title: '加载 Prompt 目录失败', description: result.error, variant: 'destructive' })
        return
      }

      setCatalog(result.data)
      const nextLanguage = language && result.data.languages.includes(language)
        ? language
        : result.data.languages.includes('zh-CN')
          ? 'zh-CN'
        : result.data.languages[0] ?? ''
      setLanguage(nextLanguage)

      const nextFiles = nextLanguage ? result.data.files[nextLanguage] ?? [] : []
      setFilename((current) => nextFiles.some((file) => file.name === current) ? current : nextFiles[0]?.name ?? '')
    } catch (error) {
      toast({
        title: '加载 Prompt 目录失败',
        description: (error as Error).message,
        variant: 'destructive',
      })
    } finally {
      setLoadingCatalog(false)
    }
  }, [language, toast])

  useEffect(() => {
    void loadCatalog()
  }, [loadCatalog])

  useEffect(() => {
    if (!language || !filename) {
      setContent('')
      setSavedContent('')
      return
    }

    let cancelled = false
    const loadFile = async () => {
      try {
        setLoadingFile(true)
        const result = await getPromptFile(language, filename)
        if (cancelled) return
        if (!result.success) {
          toast({ title: '读取 Prompt 失败', description: result.error, variant: 'destructive' })
          return
        }
        setContent(result.data.content)
        setSavedContent(result.data.content)
      } catch (error) {
        if (!cancelled) {
          toast({
            title: '读取 Prompt 失败',
            description: (error as Error).message,
            variant: 'destructive',
          })
        }
      } finally {
        if (!cancelled) {
          setLoadingFile(false)
        }
      }
    }

    void loadFile()
    return () => {
      cancelled = true
    }
  }, [filename, language, toast])

  const handleLanguageChange = (nextLanguage: string) => {
    setLanguage(nextLanguage)
    setQuery('')
    const nextFiles = catalog?.files[nextLanguage] ?? []
    setFilename(nextFiles[0]?.name ?? '')
  }

  const handleSave = async () => {
    if (!language || !filename) return

    try {
      setSaving(true)
      const result = await updatePromptFile(language, filename, content)
      if (!result.success) {
        toast({ title: '保存 Prompt 失败', description: result.error, variant: 'destructive' })
        return
      }

      setContent(result.data.content)
      setSavedContent(result.data.content)
      toast({ title: 'Prompt 已保存', description: `${language}/${filename}` })
      void loadCatalog()
    } catch (error) {
      toast({
        title: '保存 Prompt 失败',
        description: (error as Error).message,
        variant: 'destructive',
      })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="flex h-[calc(100vh-140px)] flex-col gap-4 p-4 sm:p-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl font-bold sm:text-2xl md:text-3xl">Prompt 管理</h1>
          <p className="mt-1 text-sm text-muted-foreground">编辑 prompts 目录下不同语言的系统提示词模板</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Select value={language} onValueChange={handleLanguageChange} disabled={loadingCatalog}>
            <SelectTrigger className="w-[160px]">
              <SelectValue placeholder="选择语言" />
            </SelectTrigger>
            <SelectContent>
              {(catalog?.languages ?? []).map((item) => (
                <SelectItem key={item} value={item}>{item}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button variant="outline" size="sm" onClick={() => void loadCatalog()} disabled={loadingCatalog}>
            <RefreshCw className={cn('mr-2 h-4 w-4', loadingCatalog && 'animate-spin')} />
            刷新
          </Button>
          <Button size="sm" onClick={handleSave} disabled={!hasUnsavedChanges || saving || loadingFile || !filename}>
            <Save className="mr-2 h-4 w-4" />
            {saving ? '保存中' : hasUnsavedChanges ? '保存' : '已保存'}
          </Button>
        </div>
      </div>

      <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-[18rem_minmax(0,1fr)]">
        <Card className="min-h-0 overflow-hidden">
          <CardHeader className="space-y-3 pb-3">
            <CardTitle className="flex items-center gap-2 text-sm">
              <FileText className="h-4 w-4" />
              Prompt 文件
              <Badge variant="secondary" className="ml-auto">{promptFiles.length}</Badge>
            </CardTitle>
            <div className="relative">
              <Search className="pointer-events-none absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
              <Input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="搜索文件"
                className="pl-8"
              />
            </div>
          </CardHeader>
          <Separator />
          <ScrollArea className="h-full">
            <div className="space-y-1 p-2">
              {loadingCatalog ? (
                <div className="flex items-center justify-center gap-2 p-6 text-sm text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  加载中
                </div>
              ) : filteredFiles.length > 0 ? (
                filteredFiles.map((file) => (
                  <button
                    key={file.name}
                    type="button"
                    onClick={() => setFilename(file.name)}
                    className={cn(
                      'w-full rounded-md px-3 py-2 text-left text-sm transition-colors',
                      'hover:bg-accent hover:text-accent-foreground',
                      filename === file.name ? 'bg-accent text-accent-foreground' : 'text-muted-foreground',
                    )}
                  >
                    <div className="truncate font-medium" title={file.name}>{file.name}</div>
                    <div className="mt-0.5 text-xs text-muted-foreground">{formatFileSize(file.size)}</div>
                  </button>
                ))
              ) : (
                <div className="p-6 text-center text-sm text-muted-foreground">没有可编辑的 Prompt 文件</div>
              )}
            </div>
          </ScrollArea>
        </Card>

        <Card className="min-h-0 overflow-hidden">
          <CardHeader className="flex flex-row items-center justify-between gap-3 space-y-0 pb-3">
            <div className="min-w-0">
              <CardTitle className="truncate text-sm">{filename || '未选择文件'}</CardTitle>
              <p className="mt-1 text-xs text-muted-foreground">
                {language}
                {selectedFile ? ` · ${formatFileSize(selectedFile.size)}` : ''}
                {hasUnsavedChanges ? ' · 有未保存修改' : ''}
              </p>
            </div>
          </CardHeader>
          <CardContent className="min-h-0 p-0">
            {loadingFile ? (
              <div className="flex h-[calc(100vh-290px)] items-center justify-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                读取中
              </div>
            ) : (
              <CodeEditor
                value={content}
                onChange={setContent}
                language="text"
                height="calc(100vh - 290px)"
                minHeight="520px"
                placeholder="选择一个 Prompt 文件后开始编辑"
              />
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
