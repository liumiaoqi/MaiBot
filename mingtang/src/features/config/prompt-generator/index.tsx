import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useMutation } from '@tanstack/react-query'
import { PageShell } from '@/components/biz/page-shell'
import { Button } from '@/components/ui/button'
import { CodeEditor } from '../components/code-editor'
import { Sparkles, Save, Copy, Download, Wand2 } from 'lucide-react'
import { generatePromptPersona, applyPromptGeneratorBlocks } from '@/lib/prompt-generator-api'

type ResultTab = 'blocks' | 'toml' | 'raw'

/** 人设生成器页（/config/prompt-generator）——左栏输入 + 右栏结果三 tab */
export function PromptGeneratorPage() {
  const { t } = useTranslation()

  const [model, setModel] = useState('deepseek-chat')
  const [scene, setScene] = useState('chat')
  const [lang, setLang] = useState('zh')
  const [inputText, setInputText] = useState('')
  const [extraReq, setExtraReq] = useState('')
  const [temperature, setTemperature] = useState(0.7)
  const [maxTokens, setMaxTokens] = useState(4096)

  const [result, setResult] = useState('')
  const [resultTab, setResultTab] = useState<ResultTab>('blocks')
  const [savedPersonas, setSavedPersonas] = useState<Array<{ name: string; content: string }>>([])

  const generateMutation = useMutation({
    mutationFn: () => generatePromptPersona({
      model_name: model,
      source_text: inputText,
      target_scene: scene,
      language: lang,
      extra_requirements: extraReq,
      temperature,
      max_tokens: maxTokens,
    }),
    onSuccess: (data) => setResult(JSON.stringify(data)),
  })

  const injectMutation = useMutation({
    mutationFn: () => applyPromptGeneratorBlocks(JSON.parse(result)),
  })

  const handleSave = () => {
    const name = `人设-${savedPersonas.length + 1}`
    setSavedPersonas([...savedPersonas, { name, content: result }])
  }

  const handleCopy = () => {
    navigator.clipboard.writeText(result)
  }

  const handleDownload = () => {
    const blob = new Blob([result], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'persona.toml'
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <PageShell title={t('sidebar.menu.promptGenerator')} breadcrumb={[t('sidebar.groups.botConfig')]}>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* 左栏：生成输入 */}
        <div className="space-y-3" data-testid="pg-input-panel">
          <h3 className="font-semibold text-foreground">生成输入</h3>
          <div>
            <label className="text-xs text-muted-foreground">模型</label>
            <input type="text" value={model} onChange={(e) => setModel(e.target.value)} className="w-full px-2 py-1 text-sm rounded border border-border bg-background" data-testid="pg-model" />
          </div>
          <div>
            <label className="text-xs text-muted-foreground">目标场景</label>
            <select value={scene} onChange={(e) => setScene(e.target.value)} className="w-full px-2 py-1 text-sm rounded border border-border bg-background" data-testid="pg-scene">
              <option value="chat">聊天</option>
              <option value="memory">记忆</option>
              <option value="emoji">表情</option>
            </select>
          </div>
          <div>
            <label className="text-xs text-muted-foreground">语言</label>
            <select value={lang} onChange={(e) => setLang(e.target.value)} className="w-full px-2 py-1 text-sm rounded border border-border bg-background" data-testid="pg-lang">
              <option value="zh">中文</option>
              <option value="en">English</option>
            </select>
          </div>
          <div>
            <label className="text-xs text-muted-foreground">原文（20000 上限）</label>
            <textarea
              value={inputText}
              onChange={(e) => setInputText(e.target.value.slice(0, 20000))}
              className="w-full px-2 py-1 text-sm rounded border border-border bg-background"
              rows={6}
              data-testid="pg-input-text"
            />
          </div>
          <div>
            <label className="text-xs text-muted-foreground">额外要求（4000 上限）</label>
            <textarea
              value={extraReq}
              onChange={(e) => setExtraReq(e.target.value.slice(0, 4000))}
              className="w-full px-2 py-1 text-sm rounded border border-border bg-background"
              rows={3}
              data-testid="pg-extra-req"
            />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="text-xs text-muted-foreground">温度</label>
              <input type="number" step="0.1" min="0" max="2" value={temperature} onChange={(e) => setTemperature(parseFloat(e.target.value))} className="w-full px-2 py-1 text-sm rounded border border-border bg-background" data-testid="pg-temperature" />
            </div>
            <div>
              <label className="text-xs text-muted-foreground">最大 Token</label>
              <input type="number" value={maxTokens} onChange={(e) => setMaxTokens(parseInt(e.target.value))} className="w-full px-2 py-1 text-sm rounded border border-border bg-background" data-testid="pg-max-tokens" />
            </div>
          </div>
          <Button size="sm" onClick={() => generateMutation.mutate()} disabled={generateMutation.isPending} data-testid="pg-generate">
            <Sparkles className="h-4 w-4 mr-1" />
            生成
          </Button>

          {/* 已保存人设 */}
          {savedPersonas.length > 0 && (
            <div className="space-y-1" data-testid="pg-saved-personas">
              <h4 className="text-sm font-medium text-foreground">已保存人设</h4>
              {savedPersonas.map((p, i) => (
                <div key={i} className="text-xs text-muted-foreground">{p.name}</div>
              ))}
            </div>
          )}
        </div>

        {/* 右栏：结果三 tab */}
        <div className="space-y-3" data-testid="pg-result-panel">
          <div className="flex items-center gap-1 border-b pb-2">
            {(['blocks', 'toml', 'raw'] as ResultTab[]).map((tab) => (
              <button
                key={tab}
                onClick={() => setResultTab(tab)}
                data-testid={`pg-tab-${tab}`}
                className={`px-3 py-1 text-sm rounded-t ${resultTab === tab ? 'bg-background border border-border border-b-0 font-medium' : 'text-muted-foreground'}`}
              >
                {tab === 'blocks' ? '配置块' : tab === 'toml' ? 'TOML' : '原始输出'}
              </button>
            ))}
          </div>

          {result ? (
            <>
              <CodeEditor value={result} language={resultTab === 'toml' ? 'toml' : 'json'} height="400px" readOnly />
              <div className="flex items-center gap-2">
                <Button size="sm" onClick={() => injectMutation.mutate()} disabled={injectMutation.isPending} data-testid="pg-inject">
                  <Wand2 className="h-4 w-4 mr-1" />
                  全部注入
                </Button>
                <Button size="sm" variant="outline" onClick={handleSave} data-testid="pg-save">
                  <Save className="h-4 w-4 mr-1" />
                  保存
                </Button>
                <Button size="sm" variant="outline" onClick={handleCopy} data-testid="pg-copy">
                  <Copy className="h-4 w-4 mr-1" />
                  复制
                </Button>
                <Button size="sm" variant="outline" onClick={handleDownload} data-testid="pg-download">
                  <Download className="h-4 w-4 mr-1" />
                  下载
                </Button>
              </div>
            </>
          ) : (
            <div className="flex items-center justify-center h-48 text-muted-foreground" data-testid="pg-empty">
              点击「生成」开始
            </div>
          )}
        </div>
      </div>
    </PageShell>
  )
}
