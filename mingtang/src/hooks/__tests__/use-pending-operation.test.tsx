/**
 * usePendingOperation hook 测试
 */
import { renderHook, act } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { usePendingOperation } from '../usePendingOperation'

describe('usePendingOperation', () => {
  it('初始状态：pending null + isWaiting false + isConfirming false', () => {
    const { result } = renderHook(() => usePendingOperation({ onConfirm: vi.fn() }))
    expect(result.current.pending).toBeNull()
    expect(result.current.isWaiting).toBe(false)
    expect(result.current.isConfirming).toBe(false)
  })

  it('submit 暂存操作 + isWaiting true', () => {
    const { result } = renderHook(() => usePendingOperation({ onConfirm: vi.fn() }))
    act(() => {
      result.current.submit({ value: 42 })
    })
    expect(result.current.pending).toEqual({ value: 42 })
    expect(result.current.isWaiting).toBe(true)
  })

  it('cancel 放弃待定 + isWaiting false', () => {
    const { result } = renderHook(() => usePendingOperation({ onConfirm: vi.fn() }))
    act(() => {
      result.current.submit({ value: 42 })
    })
    act(() => {
      result.current.cancel()
    })
    expect(result.current.pending).toBeNull()
    expect(result.current.isWaiting).toBe(false)
  })

  it('confirm 执行 onConfirm + 成功后清空待定', async () => {
    const onConfirm = vi.fn().mockResolvedValue(undefined)
    const { result } = renderHook(() => usePendingOperation({ onConfirm }))
    act(() => {
      result.current.submit({ value: 42 })
    })
    await act(async () => {
      await result.current.confirm()
    })
    expect(onConfirm).toHaveBeenCalledWith({ value: 42 })
    expect(result.current.pending).toBeNull()
    expect(result.current.isConfirming).toBe(false)
  })

  it('confirm 失败保留待定态', async () => {
    const onConfirm = vi.fn().mockRejectedValue(new Error('失败'))
    const { result } = renderHook(() => usePendingOperation({ onConfirm }))
    act(() => {
      result.current.submit({ value: 42 })
    })
    await act(async () => {
      await expect(result.current.confirm()).rejects.toThrow('失败')
    })
    expect(result.current.pending).toEqual({ value: 42 })
    expect(result.current.isConfirming).toBe(false)
  })

  it('confirm 无待定时 no-op', async () => {
    const onConfirm = vi.fn()
    const { result } = renderHook(() => usePendingOperation({ onConfirm }))
    await act(async () => {
      await result.current.confirm()
    })
    expect(onConfirm).not.toHaveBeenCalled()
  })
})