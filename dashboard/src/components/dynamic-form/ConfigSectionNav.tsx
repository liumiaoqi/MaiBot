import { useState } from 'react'
import { ChevronDown } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { cn } from '@/lib/utils'

export interface ConfigSection {
  key: string
  label: string
  advanced: boolean
  order: number
  dirty?: boolean
}

interface ConfigSectionNavProps {
  sections: ConfigSection[]
  activeKey: string
  onSectionChange: (key: string) => void
  className?: string
}

function ConfigSectionNav({ sections, activeKey, onSectionChange, className }: ConfigSectionNavProps) {
  const [showAdvanced, setShowAdvanced] = useState(false)

  const defaultSections = sections.filter((s) => !s.advanced)
  const advancedSections = sections.filter((s) => s.advanced)
  const visibleSections = showAdvanced ? [...defaultSections, ...advancedSections] : defaultSections
  const hasAdvanced = advancedSections.length > 0

  return (
    <div className={cn('flex h-full flex-col', className)}>
      <ScrollArea className="flex-1">
        <nav className="flex flex-col gap-0.5 p-2">
          {visibleSections.map((section, index) => {
            const isActive = section.key === activeKey
            const isAdvancedStart = showAdvanced && section.advanced && index === defaultSections.length

            return (
              <div key={section.key}>
                {isAdvancedStart && (
                  <div className="my-1.5 flex items-center gap-2 px-2">
                    <div className="bg-border h-px flex-1" />
                    <span className="text-muted-foreground shrink-0 text-[11px] tracking-wider">高级</span>
                    <div className="bg-border h-px flex-1" />
                  </div>
                )}
                <button
                  type="button"
                  onClick={() => onSectionChange(section.key)}
                  className={cn(
                    'group relative flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm transition-colors duration-150',
                    isActive
                      ? 'bg-primary/10 text-primary font-medium'
                      : 'text-foreground/80 hover:bg-muted/60 hover:text-foreground'
                  )}
                >
                  <span className="min-w-0 truncate">{section.label}</span>
                  {section.dirty && (
                    <span
                      className={cn(
                        'h-1.5 w-1.5 shrink-0 rounded-full',
                        isActive ? 'bg-primary' : 'bg-primary/60'
                      )}
                    />
                  )}
                </button>
              </div>
            )
          })}
        </nav>
      </ScrollArea>
      {hasAdvanced && (
        <div className="border-t p-2">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="w-full justify-center gap-1.5 text-xs text-muted-foreground"
            onClick={() => setShowAdvanced((v) => !v)}
          >
            <ChevronDown
              className={cn('h-3.5 w-3.5 transition-transform duration-200', showAdvanced && 'rotate-180')}
            />
            {showAdvanced ? '收起高级' : '显示高级'}
          </Button>
        </div>
      )}
    </div>
  )
}

export { ConfigSectionNav }