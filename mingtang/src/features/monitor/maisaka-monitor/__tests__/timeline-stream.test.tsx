/**
 * TimelineStream 子组件测试
 *
 * 核心验证：
 * - 时间线条目渲染
 * - 自动滚动
 * - 空时间线占位
 */
import { render, screen } from '@testing-library/react'
import { createElement, type RefObject } from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

vi.mock('../components/timeline-entry-item', () => ({
  TimelineEntryItem: ({ entry }: { entry: { id: string } }) =>
    createElement('div', { 'data-testid': 'timeline-item', 'data-id': entry.id }),
  formatRelativeTime: () => ({ key: 'monitor.maisaka.justNow' }),
  formatMs: () => '0ms',
  formatTimestamp: () => '00:00:00',
}))

import { TimelineStream } from '../components/timeline-stream'
import type { TimelineEntry } from '../hooks/persist-monitor'

function makeMessageEntry(id: string, kind: 'ingested' | 'sent' = 'ingested'): TimelineEntry {
  return {
    id,
    type: kind === 'ingested' ? 'message.ingested' : 'message.sent',
    data: {
      session_id: 'sess-1',
      speaker_name: '用户',
      content: '你好',
      message_id: `msg-${id}`,
      timestamp: 1000,
    } as TimelineEntry['data'],
    timestamp: 1000,
    sessionId: 'sess-1',
  }
}

function makeRef(): RefObject<HTMLDivElement | null> {
  return { current: null }
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('TimelineStream', () => {
  it('空时间线显示占位文案', () => {
    render(
      <TimelineStream
        timeline={[]}
        autoScroll={true}
        onAutoScrollChange={vi.fn()}
        viewportRef={makeRef()}
      />,
    )
    expect(screen.getByText('monitor.maisaka.waitingEvents')).toBeInTheDocument()
    expect(screen.getByText('monitor.maisaka.waitingEventsHint')).toBeInTheDocument()
  })

  it('时间线条目渲染（非空时不显示占位）', () => {
    const entries = [makeMessageEntry('e1')]
    render(
      <TimelineStream
        timeline={entries}
        autoScroll={true}
        onAutoScrollChange={vi.fn()}
        viewportRef={makeRef()}
      />,
    )
    expect(screen.queryByText('monitor.maisaka.waitingEvents')).not.toBeInTheDocument()
    expect(screen.getByTestId('timeline-item')).toBeInTheDocument()
  })

  it('多条目按顺序渲染', () => {
    const entries = [makeMessageEntry('e1'), makeMessageEntry('e2'), makeMessageEntry('e3')]
    render(
      <TimelineStream
        timeline={entries}
        autoScroll={true}
        onAutoScrollChange={vi.fn()}
        viewportRef={makeRef()}
      />,
    )
    expect(screen.getAllByTestId('timeline-item')).toHaveLength(3)
  })

  it('autoScroll=true 时调用 viewport.scrollTo', () => {
    const scrollToSpy = vi.spyOn(Element.prototype, 'scrollTo')
    render(
      <TimelineStream
        timeline={[makeMessageEntry('e1')]}
        autoScroll={true}
        onAutoScrollChange={vi.fn()}
        viewportRef={makeRef()}
      />,
    )
    expect(scrollToSpy).toHaveBeenCalled()
    scrollToSpy.mockRestore()
  })
})