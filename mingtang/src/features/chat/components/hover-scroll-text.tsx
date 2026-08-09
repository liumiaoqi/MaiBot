/**
 * HoverScrollText 横向滚动文本组件（R3-2-1）
 *
 * 文本溢出时 hover 触发横向滚动展示完整内容。
 * 从 dashboard routes/chat-management.tsx 200-265 行搬移。
 */
import type { CSSProperties } from 'react'
import { useEffect, useRef, useState } from 'react'

import { cn } from '@/lib/utils'

interface HoverScrollTextProps {
  className?: string
  maxChars: number
  value: string | null | undefined
}

function HoverScrollText({ className, maxChars, value }: HoverScrollTextProps) {
  const text = value || '-'
  const containerRef = useRef<HTMLSpanElement>(null)
  const textRef = useRef<HTMLSpanElement>(null)
  const [shouldScroll, setShouldScroll] = useState(false)
  const [scrollDurationMs, setScrollDurationMs] = useState(900)

  useEffect(() => {
    const containerElement = containerRef.current
    const textElement = textRef.current
    if (!containerElement || !textElement) return

    const updateOverflowState = () => {
      const overflowWidth = textElement.scrollWidth - containerElement.clientWidth
      const nextShouldScroll = overflowWidth > 1
      setShouldScroll((current) => (current === nextShouldScroll ? current : nextShouldScroll))
      setScrollDurationMs(Math.max(900, Math.min(2800, overflowWidth * 36)))
    }

    updateOverflowState()

    if (typeof ResizeObserver === 'undefined') {
      window.addEventListener('resize', updateOverflowState)
      return () => window.removeEventListener('resize', updateOverflowState)
    }

    const resizeObserver = new ResizeObserver(updateOverflowState)
    resizeObserver.observe(containerElement)
    resizeObserver.observe(textElement)
    return () => resizeObserver.disconnect()
  }, [maxChars, text])

  return (
    <span
      ref={containerRef}
      className={cn('group inline-block overflow-hidden align-bottom', className)}
      style={{ width: `${maxChars}ch` }}
      title={text}
    >
      <span
        ref={textRef}
        className={cn(
          'block max-w-full overflow-hidden text-ellipsis whitespace-nowrap',
          shouldScroll &&
            'group-hover:w-max group-hover:max-w-none group-hover:animate-[chat-management-text-scroll_1s_linear_infinite_alternate] group-hover:overflow-visible'
        )}
        style={
          {
            '--scroll-container-width': `${maxChars}ch`,
            animationDuration: `${scrollDurationMs}ms`,
          } as CSSProperties
        }
      >
        {text}
      </span>
    </span>
  )
}

export { HoverScrollText }