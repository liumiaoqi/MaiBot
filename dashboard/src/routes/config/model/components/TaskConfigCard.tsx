/**
 * 任务配置卡片组件
 */
import React from 'react'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Slider } from '@/components/ui/slider'
import { MultiSelect } from '@/components/ui/multi-select'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import type { TaskConfig } from '../types'

interface TaskConfigCardProps {
  title: string
  description: string
  taskConfig: TaskConfig
  modelNames: string[]
  onChange: (field: keyof TaskConfig, value: string[] | number | string) => void
  hideTemperature?: boolean
  hideMaxTokens?: boolean
  advanced?: boolean
  showAdvancedSettings?: boolean
  dataTour?: string
}

const selectionStrategyOptions = [
  {
    value: 'balance',
    label: '负载均衡（balance）',
    description: '优先选择当前使用次数较少的模型，适合多个同类模型共同承担请求。',
  },
  {
    value: 'random',
    label: '随机选择（random）',
    description: '每次请求从模型列表中随机选择一个模型，适合简单分散请求。',
  },
  {
    value: 'sequential',
    label: '按顺序优先（sequential）',
    description: '优先使用模型列表中靠前的模型，前面的模型不可用时再尝试后面的模型。',
  },
]

export const TaskConfigCard = React.memo(function TaskConfigCard({
  title,
  description,
  taskConfig,
  modelNames,
  onChange,
  hideTemperature = false,
  hideMaxTokens = false,
  advanced = false,
  showAdvancedSettings = false,
  dataTour,
}: TaskConfigCardProps) {
  const handleModelChange = (values: string[]) => {
    onChange('model_list', values)
  }

  return (
    <div
      className={cn(
        "rounded-lg border bg-card p-4 sm:p-6 space-y-4",
        advanced && "border-amber-300 bg-amber-50/40 dark:border-amber-500/50 dark:bg-amber-500/10",
      )}
    >
      <div>
        <h4 className="font-semibold text-base sm:text-lg">{title}</h4>
        <p className="text-xs sm:text-sm text-muted-foreground mt-1">{description}</p>
      </div>

      <div className="grid gap-4">
        {/* 模型列表 */}
        <div className="grid gap-2" data-tour={dataTour}>
          <Label>模型列表</Label>
          <MultiSelect
            options={modelNames.map((name) => ({ label: name, value: name }))}
            selected={taskConfig.model_list || []}
            onChange={handleModelChange}
            placeholder="选择模型..."
            emptyText="暂无可用模型"
          />
        </div>

        {/* 推理参数 */}
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          {!hideTemperature && (
            <div className="grid gap-3">
              <div className="flex items-center justify-between">
                <Label>温度</Label>
                <Input
                  type="number"
                  step="0.1"
                  min="0"
                  max="2"
                  value={taskConfig.temperature ?? 0.7}
                  onChange={(e) => {
                    const value = parseFloat(e.target.value)
                    if (!isNaN(value) && value >= 0 && value <= 2) {
                      onChange('temperature', value)
                    }
                  }}
                  className="w-20 h-8 text-sm"
                />
              </div>
              <Slider
                value={[taskConfig.temperature ?? 0.7]}
                onValueChange={(values) => onChange('temperature', values[0])}
                min={0}
                max={2}
                step={0.1}
                className="w-full"
              />
            </div>
          )}

          {!hideMaxTokens && (
            <div className="grid gap-2">
              <Label>最大 Token</Label>
              <Input
                type="number"
                step="1"
                min="1"
                value={taskConfig.max_tokens ?? 1024}
                onChange={(e) => onChange('max_tokens', parseInt(e.target.value))}
              />
            </div>
          )}

          {/* 模型选择策略 */}
          <div className="grid gap-2">
            <Label>模型选择策略</Label>
            <Select
              value={taskConfig.selection_strategy ?? 'balance'}
              onValueChange={(value) => onChange('selection_strategy', value)}
            >
              <SelectTrigger>
                <SelectValue placeholder="选择模型选择策略" />
              </SelectTrigger>
              <SelectContent>
                <TooltipProvider delayDuration={150}>
                  {selectionStrategyOptions.map((option) => (
                    <Tooltip key={option.value}>
                      <TooltipTrigger asChild>
                        <SelectItem value={option.value} title={option.description}>
                          {option.label}
                        </SelectItem>
                      </TooltipTrigger>
                      <TooltipContent
                        side="right"
                        align="center"
                        className="max-w-72 bg-background text-foreground border shadow-lg"
                      >
                        {option.description}
                      </TooltipContent>
                    </Tooltip>
                  ))}
                </TooltipProvider>
              </SelectContent>
            </Select>
          </div>
        </div>

        {showAdvancedSettings && (
          <div className="grid gap-2 rounded-md border border-amber-200 bg-amber-50/50 p-3 dark:border-amber-500/40 dark:bg-amber-500/10">
            <div className="flex items-center justify-between">
              <Label>慢请求阈值 (秒)</Label>
              <span className="text-xs text-muted-foreground">高级配置</span>
            </div>
            <Input
              type="number"
              step="1"
              min="1"
              value={taskConfig.slow_threshold ?? 15}
              onChange={(e) => {
                const value = parseInt(e.target.value)
                if (!isNaN(value) && value >= 1) {
                  onChange('slow_threshold', value)
                }
              }}
              placeholder="15"
            />
            <p className="text-xs text-muted-foreground">
              模型响应时间超过此阈值将输出警告日志
            </p>
          </div>
        )}

      </div>
    </div>
  )
})
