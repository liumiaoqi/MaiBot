import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { DataTable, type Column } from '@/components/biz/data-table'
import { StatCard } from '@/components/biz/stat-card'
import { FormField } from '@/components/biz/form-field'

interface TestData {
  id: string
  name: string
  age: number
}

const columns: Column<TestData>[] = [
  { key: 'name', header: '姓名', sortable: true },
  { key: 'age', header: '年龄', sortable: true, align: 'right' },
]

const data: TestData[] = [
  { id: '1', name: '张三', age: 25 },
  { id: '2', name: '李四', age: 30 },
  { id: '3', name: '王五', age: 20 },
]

describe('DataTable', () => {
  it('渲染表头和数据行', () => {
    render(<DataTable data={data} columns={columns} rowKey={(r) => r.id} />)
    expect(screen.getByText('姓名')).toBeTruthy()
    expect(screen.getByText('年龄')).toBeTruthy()
    expect(screen.getByText('张三')).toBeTruthy()
    expect(screen.getByText('25')).toBeTruthy()
  })

  it('空数据显示空状态', () => {
    render(<DataTable data={[]} columns={columns} rowKey={(r) => r.id} />)
    expect(screen.getByText('暂无数据')).toBeTruthy()
  })

  it('自定义空状态', () => {
    render(
      <DataTable
        data={[]}
        columns={columns}
        rowKey={(r) => r.id}
        emptyState="没有找到结果"
      />
    )
    expect(screen.getByText('没有找到结果')).toBeTruthy()
  })

  it('点击排序列切换排序方向', () => {
    render(<DataTable data={data} columns={columns} rowKey={(r) => r.id} />)
    const nameHeader = screen.getByText('姓名')

    // 点击 → 升序
    fireEvent.click(nameHeader)
    const rows = screen.getAllByRole('row')
    // 第一行是表头，第二行应该是第一个按名字排序的
    expect(rows[1].textContent).toContain('张三')

    // 再点击 → 降序
    fireEvent.click(nameHeader)
    const rowsDesc = screen.getAllByRole('row')
    expect(rowsDesc[1].textContent).toContain('王五')
  })

  it('分页功能', () => {
    const manyData = Array.from({ length: 25 }, (_, i) => ({
      id: String(i),
      name: `用户${i}`,
      age: i,
    }))
    render(
      <DataTable
        data={manyData}
        columns={columns}
        rowKey={(r) => r.id}
        pageSize={10}
      />
    )
    // 第一页 10 条
    expect(screen.getByText(/共 25 条/)).toBeTruthy()
    const nextButton = screen.getByText('下一页')
    fireEvent.click(nextButton)
    // 第二页
    expect(screen.getByText(/第 2 \/ 3 页/)).toBeTruthy()
  })

  it('行点击回调', () => {
    const onRowClick = vi.fn()
    render(
      <DataTable
        data={data}
        columns={columns}
        rowKey={(r) => r.id}
        onRowClick={onRowClick}
      />
    )
    fireEvent.click(screen.getByText('张三').closest('tr')!)
    expect(onRowClick).toHaveBeenCalledWith({ id: '1', name: '张三', age: 25 })
  })
})

describe('StatCard', () => {
  it('渲染基本属性', () => {
    render(
      <StatCard
        title="在线用户"
        value={42}
        unit="人"
        description="较昨日"
      />
    )
    expect(screen.getByText('在线用户')).toBeTruthy()
    expect(screen.getByText('42')).toBeTruthy()
    expect(screen.getByText('人')).toBeTruthy()
    expect(screen.getByText('较昨日')).toBeTruthy()
  })

  it('渲染正趋势', () => {
    render(<StatCard title="收入" value={1000} trend={15.5} />)
    expect(screen.getByText(/↑/)).toBeTruthy()
    expect(screen.getByText(/15\.5%/)).toBeTruthy()
  })

  it('渲染负趋势', () => {
    render(<StatCard title="错误" value={5} trend={-8.3} />)
    expect(screen.getByText(/↓/)).toBeTruthy()
    expect(screen.getByText(/8\.3%/)).toBeTruthy()
  })
})

describe('FormField', () => {
  it('渲染标签和子元素', () => {
    render(
      <FormField name="username" label="用户名">
        <input type="text" />
      </FormField>
    )
    expect(screen.getByText('用户名')).toBeTruthy()
    expect(screen.getByRole('textbox')).toBeTruthy()
  })

  it('必填标记', () => {
    render(
      <FormField name="email" label="邮箱" required>
        <input type="email" />
      </FormField>
    )
    expect(screen.getByText('*')).toBeTruthy()
  })

  it('高级标记', () => {
    render(
      <FormField name="timeout" label="超时" advanced>
        <input type="number" />
      </FormField>
    )
    expect(screen.getByText('高级')).toBeTruthy()
  })

  it('错误提示', () => {
    render(
      <FormField name="pass" label="密码" error="密码至少 8 位">
        <input type="password" />
      </FormField>
    )
    expect(screen.getByText('密码至少 8 位')).toBeTruthy()
  })

  it('提示文本', () => {
    render(
      <FormField name="nick" label="昵称" hint="2-20 个字符">
        <input type="text" />
      </FormField>
    )
    expect(screen.getByText('2-20 个字符')).toBeTruthy()
  })
})