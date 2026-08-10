/**
 * MultiSelect 测试（R4-1-2-3 测试先行）
 *
 * 验证多选行为：选择/取消/搜索过滤/标签展示
 */
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { MultiSelect, type MultiSelectOption } from '../multi-select'

const options: MultiSelectOption[] = [
  { label: '聊天A', value: 'a' },
  { label: '聊天B', value: 'b' },
  { label: '聊天C', value: 'c' },
]

describe('MultiSelect 多选下拉框', () => {
  describe('渲染', () => {
    it('渲染 placeholder（无选中时）', () => {
      render(
        <MultiSelect options={options} selected={[]} onChange={() => {}} placeholder="选择聊天" />
      )

      expect(screen.getByText('选择聊天')).toBeInTheDocument()
    })

    it('渲染选中项标签', () => {
      render(
        <MultiSelect options={options} selected={['a', 'b']} onChange={() => {}} />
      )

      expect(screen.getByText('聊天A')).toBeInTheDocument()
      expect(screen.getByText('聊天B')).toBeInTheDocument()
    })
  })

  describe('选择/取消', () => {
    it('点击选项触发 onChange 添加选择', async () => {
      const onChange = vi.fn()
      render(<MultiSelect options={options} selected={[]} onChange={onChange} />)

      const combobox = screen.getByRole('combobox')
      fireEvent.click(combobox)

      const optionA = await screen.findByText('聊天A')
      fireEvent.click(optionA)
      expect(onChange).toHaveBeenCalledWith(['a'])
    })

    it('点击已选项触发 onChange 取消选择', async () => {
      const onChange = vi.fn()
      render(<MultiSelect options={options} selected={['a']} onChange={onChange} />)

      const combobox = screen.getByRole('combobox')
      fireEvent.click(combobox)

      const allA = await screen.findAllByText('聊天A')
      const dropdownOption = allA[allA.length - 1]
      fireEvent.click(dropdownOption)
      expect(onChange).toHaveBeenCalledWith([])
    })

    it('点击标签 X 按钮移除选择', () => {
      const onChange = vi.fn()
      render(<MultiSelect options={options} selected={['a', 'b']} onChange={onChange} />)

      const removeButtons = screen.getAllByRole('button', { name: '' })
      fireEvent.click(removeButtons[0])
      expect(onChange).toHaveBeenCalledWith(['b'])
    })
  })

  describe('搜索过滤', () => {
    it('输入搜索文本过滤选项', async () => {
      render(<MultiSelect options={options} selected={[]} onChange={() => {}} />)

      const combobox = screen.getByRole('combobox')
      fireEvent.click(combobox)

      const searchInput = await screen.findByPlaceholderText('搜索...')
      fireEvent.change(searchInput, { target: { value: 'A' } })

      expect(screen.getByText('聊天A')).toBeInTheDocument()
      expect(screen.queryByText('聊天B')).not.toBeInTheDocument()
      expect(screen.queryByText('聊天C')).not.toBeInTheDocument()
    })
  })

  describe('禁用状态', () => {
    it('disabled=true 时 combobox 禁用', () => {
      render(<MultiSelect options={options} selected={[]} onChange={() => {}} disabled />)

      const combobox = screen.getByRole('combobox')
      expect(combobox).toBeDisabled()
    })
  })
})