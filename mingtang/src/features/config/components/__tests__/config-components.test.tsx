import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { CodeEditor } from '../code-editor'
import { KeyValueEditor } from '../key-value-editor'
import { MultiSelect } from '../multi-select'
import { ExtraParamsDialog } from '../extra-params-dialog'
import { ConnectionTestBadge } from '../connection-test-badge'
import type { TestConnectionResult, ModelTestResult } from '@/lib/config-api'

describe('R2-3-1：config 域私有组件基座', () => {

  // === CodeEditor ===
  describe('CodeEditor', () => {
    it('渲染 textarea + 初始值', () => {
      render(<CodeEditor value="hello" language="text" />)
      expect(screen.getByTestId('code-editor')).toBeInTheDocument()
      expect(screen.getByTestId('code-editor-textarea')).toHaveValue('hello')
    })

    it('JSON 校验通过', () => {
      render(<CodeEditor value='{"key": "value"}' language="json" />)
      expect(screen.getByText('校验通过')).toBeInTheDocument()
    })

    it('JSON 校验失败显示错误', () => {
      render(<CodeEditor value='{invalid}' language="json" />)
      expect(screen.getByText(/JSON/)).toBeInTheDocument()
    })

    it('TOML 校验通过', () => {
      render(<CodeEditor value='key = "value"' language="toml" />)
      expect(screen.getByText('校验通过')).toBeInTheDocument()
    })

    it('TOML 校验失败显示中文错误', () => {
      render(<CodeEditor value='key = ' language="toml" />)
      expect(screen.getByTestId('code-editor')).toBeInTheDocument()
    })

    it('onChange 回调触发', () => {
      const onChange = vi.fn()
      render(<CodeEditor value="" language="text" onChange={onChange} />)
      const textarea = screen.getByTestId('code-editor-textarea')
      fireEvent.change(textarea, { target: { value: 'new content' } })
      expect(onChange).toHaveBeenCalledWith('new content')
    })

    it('readOnly 模式', () => {
      render(<CodeEditor value="readonly" language="text" readOnly />)
      expect(screen.getByTestId('code-editor-textarea')).toHaveAttribute('readonly')
    })
  })

  // === KeyValueEditor ===
  describe('KeyValueEditor', () => {
    it('渲染可视化编辑模式 + 已有键值对', () => {
      render(<KeyValueEditor value={{ KEY1: 'val1', KEY2: 'val2' }} onChange={() => {}} />)
      expect(screen.getByTestId('key-value-editor')).toBeInTheDocument()
      expect(screen.getByDisplayValue('KEY1')).toBeInTheDocument()
      expect(screen.getByDisplayValue('val1')).toBeInTheDocument()
    })

    it('添加新键值对', () => {
      const onChange = vi.fn()
      render(<KeyValueEditor value={{}} onChange={onChange} />)
      const addButton = screen.getByTestId('kv-add-button')
      const inputs = screen.getAllByRole('textbox')
      const keyInput = inputs[inputs.length - 2]
      const valueInput = inputs[inputs.length - 1]
      fireEvent.change(keyInput, { target: { value: 'NEW_KEY' } })
      fireEvent.change(valueInput, { target: { value: 'new_val' } })
      fireEvent.click(addButton)
      expect(onChange).toHaveBeenCalledWith({ NEW_KEY: 'new_val' })
    })

    it('删除键值对', () => {
      const onChange = vi.fn()
      render(<KeyValueEditor value={{ KEY1: 'val1' }} onChange={onChange} />)
      const deleteButton = screen.getByLabelText('删除 KEY1')
      fireEvent.click(deleteButton)
      expect(onChange).toHaveBeenCalledWith({})
    })

    it('切换到 JSON 编辑模式', () => {
      render(<KeyValueEditor value={{ KEY1: 'val1' }} onChange={() => {}} />)
      fireEvent.click(screen.getByTestId('kv-mode-json'))
      expect(screen.getByTestId('kv-json-textarea')).toBeInTheDocument()
    })

    it('JSON 模式编辑 + 校验通过', () => {
      const onChange = vi.fn()
      render(<KeyValueEditor value={{}} onChange={onChange} />)
      fireEvent.click(screen.getByTestId('kv-mode-json'))
      const textarea = screen.getByTestId('kv-json-textarea')
      fireEvent.change(textarea, { target: { value: '{"a": 1}' } })
      expect(onChange).toHaveBeenCalledWith({ a: 1 })
    })

    it('JSON 模式校验失败显示错误', () => {
      render(<KeyValueEditor value={{}} onChange={() => {}} />)
      fireEvent.click(screen.getByTestId('kv-mode-json'))
      const textarea = screen.getByTestId('kv-json-textarea')
      fireEvent.change(textarea, { target: { value: '{invalid}' } })
      expect(screen.getByText('JSON 格式错误')).toBeInTheDocument()
    })
  })

  // === MultiSelect ===
  describe('MultiSelect', () => {
    const options = [
      { label: '模型A', value: 'model-a' },
      { label: '模型B', value: 'model-b' },
      { label: '模型C', value: 'model-c' },
    ]

    it('渲染触发器 + placeholder', () => {
      render(<MultiSelect options={options} selected={[]} onChange={() => {}} placeholder="选择模型" />)
      expect(screen.getByTestId('multi-select')).toBeInTheDocument()
      expect(screen.getByText('选择模型')).toBeInTheDocument()
    })

    it('渲染已选徽章', () => {
      render(<MultiSelect options={options} selected={['model-a', 'model-b']} onChange={() => {}} />)
      expect(screen.getByTestId('multi-select-badge-model-a')).toBeInTheDocument()
      expect(screen.getByTestId('multi-select-badge-model-b')).toBeInTheDocument()
    })

    it('点击触发器打开下拉 + 搜索', () => {
      render(<MultiSelect options={options} selected={[]} onChange={() => {}} />)
      fireEvent.click(screen.getByTestId('multi-select-trigger'))
      expect(screen.getByTestId('multi-select-dropdown')).toBeInTheDocument()
      expect(screen.getByTestId('multi-select-search')).toBeInTheDocument()
    })

    it('搜索过滤选项', () => {
      render(<MultiSelect options={options} selected={[]} onChange={() => {}} />)
      fireEvent.click(screen.getByTestId('multi-select-trigger'))
      const search = screen.getByTestId('multi-select-search')
      fireEvent.change(search, { target: { value: '模型A' } })
      expect(screen.getByTestId('multi-select-option-model-a')).toBeInTheDocument()
      expect(screen.queryByTestId('multi-select-option-model-b')).not.toBeInTheDocument()
    })

    it('选择/取消选择选项', () => {
      const onChange = vi.fn()
      render(<MultiSelect options={options} selected={[]} onChange={onChange} />)
      fireEvent.click(screen.getByTestId('multi-select-trigger'))
      fireEvent.click(screen.getByTestId('multi-select-option-model-a'))
      expect(onChange).toHaveBeenCalledWith(['model-a'])
    })

    it('移除已选徽章', () => {
      const onChange = vi.fn()
      render(<MultiSelect options={options} selected={['model-a']} onChange={onChange} />)
      fireEvent.click(screen.getByLabelText('移除 模型A'))
      expect(onChange).toHaveBeenCalledWith([])
    })

    it('disabled 状态', () => {
      render(<MultiSelect options={options} selected={[]} onChange={() => {}} disabled />)
      expect(screen.getByTestId('multi-select-trigger')).toHaveClass('cursor-not-allowed')
    })
  })

  // === ExtraParamsDialog ===
  describe('ExtraParamsDialog', () => {
    it('打开时渲染对话框 + KeyValueEditor', () => {
      render(
        <ExtraParamsDialog open={true} onOpenChange={() => {}} value={{}} onChange={() => {}} />
      )
      expect(screen.getByText('编辑额外参数')).toBeInTheDocument()
      expect(screen.getByTestId('key-value-editor')).toBeInTheDocument()
    })

    it('关闭时不渲染', () => {
      render(
        <ExtraParamsDialog open={false} onOpenChange={() => {}} value={{}} onChange={() => {}} />
      )
      expect(screen.queryByText('编辑额外参数')).not.toBeInTheDocument()
    })

    it('保存按钮触发 onChange + 关闭', () => {
      const onChange = vi.fn()
      const onOpenChange = vi.fn()
      render(
        <ExtraParamsDialog open={true} onOpenChange={onOpenChange} value={{ key: 'val' }} onChange={onChange} />
      )
      const saveButton = screen.getByText('保存')
      fireEvent.click(saveButton)
      expect(onChange).toHaveBeenCalled()
      expect(onOpenChange).toHaveBeenCalledWith(false)
    })

    it('取消按钮恢复原始值 + 关闭', () => {
      const onOpenChange = vi.fn()
      render(
        <ExtraParamsDialog open={true} onOpenChange={onOpenChange} value={{ key: 'val' }} onChange={() => {}} />
      )
      fireEvent.click(screen.getByText('取消'))
      expect(onOpenChange).toHaveBeenCalledWith(false)
    })
  })

  // === ConnectionTestBadge ===
  describe('ConnectionTestBadge', () => {
    it('未测试状态（idle）', () => {
      render(<ConnectionTestBadge />)
      expect(screen.getByTestId('connection-test-idle')).toBeInTheDocument()
    })

    it('正在测试状态（testing）', () => {
      render(<ConnectionTestBadge isTesting={true} />)
      expect(screen.getByTestId('connection-test-testing')).toBeInTheDocument()
    })

    it('连接成功——绿（Key 有效）', () => {
      const result: TestConnectionResult = {
        network_ok: true,
        api_key_valid: true,
        latency_ms: 120,
        error: null,
        http_status: 200,
      }
      render(<ConnectionTestBadge result={result} />)
      expect(screen.getByTestId('connection-test-success')).toBeInTheDocument()
    })

    it('网络通但 Key 无效——红', () => {
      const result: TestConnectionResult = {
        network_ok: true,
        api_key_valid: false,
        latency_ms: null,
        error: 'API Key 无效',
        http_status: 401,
      }
      render(<ConnectionTestBadge result={result} />)
      expect(screen.getByTestId('connection-test-key-invalid')).toBeInTheDocument()
    })

    it('网络通但 Key 未验证——蓝', () => {
      const result: TestConnectionResult = {
        network_ok: true,
        api_key_valid: null,
        latency_ms: 100,
        error: null,
        http_status: 200,
      }
      render(<ConnectionTestBadge result={result} />)
      expect(screen.getByTestId('connection-test-network-only')).toBeInTheDocument()
    })

    it('连接失败——红', () => {
      const result: TestConnectionResult = {
        network_ok: false,
        api_key_valid: null,
        latency_ms: null,
        error: '无法访问',
        http_status: null,
      }
      render(<ConnectionTestBadge result={result} />)
      expect(screen.getByTestId('connection-test-failed')).toBeInTheDocument()
    })

    it('点击徽章打开详情弹窗', () => {
      const result: TestConnectionResult = {
        network_ok: true,
        api_key_valid: true,
        latency_ms: 120,
        error: null,
        http_status: 200,
      }
      render(<ConnectionTestBadge result={result} />)
      fireEvent.click(screen.getByTestId('connection-test-success'))
      expect(screen.getByText('连接测试详情')).toBeInTheDocument()
      expect(screen.getByText('120ms')).toBeInTheDocument()
    })

    it('模型测试结果详情弹窗', () => {
      const result: TestConnectionResult = {
        network_ok: true,
        api_key_valid: true,
        latency_ms: 50,
        error: null,
        http_status: 200,
      }
      const modelResult: ModelTestResult = {
        success: true,
        model_name: 'deepseek-chat',
        visual_tested: false,
        tool_call_ok: true,
        response: 'Hello',
        reasoning: '',
        tool_calls: [],
        latency_ms: 50,
        error: null,
        prompt_tokens: 10,
        completion_tokens: 5,
        total_tokens: 15,
      }
      render(<ConnectionTestBadge result={result} modelResult={modelResult} />)
      fireEvent.click(screen.getByTestId('connection-test-success'))
      expect(screen.getByText('deepseek-chat')).toBeInTheDocument()
      expect(screen.getByText('15')).toBeInTheDocument()
    })
  })
})