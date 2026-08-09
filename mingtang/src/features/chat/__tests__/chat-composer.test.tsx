/**
 * ChatComposer 聊天输入区测试（R3-1-3 测试先行）
 */
import { describe, it, expect, vi } from 'vitest'
import { render, fireEvent } from '@testing-library/react'
import { createElement } from 'react'

import { ChatComposer } from '../components/chat-composer'
import type { ChatImageAttachment } from '../types'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => {
      if (opts && typeof opts === 'object' && 'defaultValue' in opts) {
        return String(opts.defaultValue)
      }
      return key
    },
  }),
}))

const baseProps = {
  value: '',
  onChange: () => {},
  onSend: () => {},
  onAddImages: () => {},
  onRemoveImage: () => {},
  disabled: false,
  images: [] as ChatImageAttachment[],
  isConnected: true,
}

describe('R3-1-3：ChatComposer 聊天输入区', () => {
  it('渲染 Textarea + 发送按钮 + 图片按钮', () => {
    const { container } = render(createElement(ChatComposer, baseProps))
    expect(container.querySelector('textarea')).not.toBeNull()
    expect(container.querySelector('button[aria-label="chat.actions.send"]')).not.toBeNull()
    expect(container.querySelector('button[aria-label="chat.actions.addImage"]')).not.toBeNull()
  })

  it('未连接态 → Textarea + 图片按钮禁用', () => {
    const { container } = render(
      createElement(ChatComposer, { ...baseProps, isConnected: false })
    )
    expect(container.querySelector('textarea')?.hasAttribute('disabled')).toBe(true)
  })

  it('Enter 键触发 onSend（非 composing）', () => {
    const onSend = vi.fn()
    const { container } = render(
      createElement(ChatComposer, { ...baseProps, value: '测试', onSend })
    )
    const textarea = container.querySelector('textarea')!
    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false, nativeEvent: { isComposing: false } })
    expect(onSend).toHaveBeenCalledTimes(1)
  })

  it('Shift+Enter 不触发 onSend（换行）', () => {
    const onSend = vi.fn()
    const { container } = render(
      createElement(ChatComposer, { ...baseProps, value: '测试', onSend })
    )
    const textarea = container.querySelector('textarea')!
    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: true, nativeEvent: { isComposing: false } })
    expect(onSend).not.toHaveBeenCalled()
  })


  it('disabled 时 Enter 不触发 onSend', () => {
    const onSend = vi.fn()
    const { container } = render(
      createElement(ChatComposer, { ...baseProps, value: '测试', disabled: true, onSend })
    )
    const textarea = container.querySelector('textarea')!
    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false, nativeEvent: { isComposing: false } })
    expect(onSend).not.toHaveBeenCalled()
  })

  it('图片预览条渲染（images 非空）', () => {
    const images: ChatImageAttachment[] = [
      { id: 'img1', name: 'a.png', mime_type: 'image/png', base64: '', data_url: 'http://x/a.png' },
    ]
    const { container } = render(
      createElement(ChatComposer, { ...baseProps, images })
    )
    expect(container.querySelector('img[src="http://x/a.png"]')).not.toBeNull()
  })

  it('点击图片移除按钮触发 onRemoveImage', () => {
    const onRemoveImage = vi.fn()
    const images: ChatImageAttachment[] = [
      { id: 'img1', name: 'a.png', mime_type: 'image/png', base64: '', data_url: 'http://x/a.png' },
    ]
    const { container } = render(
      createElement(ChatComposer, { ...baseProps, images, onRemoveImage })
    )
    const removeBtn = container.querySelector('button[aria-label="chat.actions.removeImage"]')!
    fireEvent.click(removeBtn)
    expect(onRemoveImage).toHaveBeenCalledWith('img1')
  })

  it('onChange 在输入时触发', () => {
    const onChange = vi.fn()
    const { container } = render(
      createElement(ChatComposer, { ...baseProps, onChange })
    )
    const textarea = container.querySelector('textarea')!
    fireEvent.change(textarea, { target: { value: '新内容' } })
    expect(onChange).toHaveBeenCalledWith('新内容')
  })
})