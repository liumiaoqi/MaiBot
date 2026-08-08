import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { PageShell } from '../biz/page-shell'
import { LoadingSkeleton } from '../biz/loading-skeleton'
import { ErrorState } from '../biz/error-state'
import { EmptyState } from '../biz/empty-state'

describe('R1-2-9：三态组件 + PageShell', () => {
  describe('LoadingSkeleton', () => {
    it('渲染骨架占位', () => {
      render(<LoadingSkeleton />)
      expect(screen.getByTestId('loading-skeleton')).toBeInTheDocument()
    })

    it('渲染指定行数', () => {
      const { container } = render(<LoadingSkeleton rows={5} />)
      const skeletons = container.querySelectorAll('.animate-pulse')
      expect(skeletons).toHaveLength(5)
    })

    it('渲染自定义消息', () => {
      render(<LoadingSkeleton message="正在加载配置…" />)
      expect(screen.getByText('正在加载配置…')).toBeInTheDocument()
    })
  })

  describe('ErrorState', () => {
    it('渲染 Error 的 message', () => {
      render(<ErrorState error={new Error('网络请求失败')} />)
      expect(screen.getByText('网络请求失败')).toBeInTheDocument()
    })

    it('渲染非 Error 的字符串', () => {
      render(<ErrorState error="未知错误" />)
      expect(screen.getByText('未知错误')).toBeInTheDocument()
    })

    it('有 onRetry 时渲染重试按钮', () => {
      render(<ErrorState error={new Error('test')} onRetry={() => {}} />)
      expect(screen.getByText('重试')).toBeInTheDocument()
    })

    it('无 onRetry 时不渲染重试按钮', () => {
      render(<ErrorState error={new Error('test')} />)
      expect(screen.queryByText('重试')).not.toBeInTheDocument()
    })
  })

  describe('EmptyState', () => {
    it('渲染默认消息', () => {
      render(<EmptyState />)
      expect(screen.getByText('暂无数据')).toBeInTheDocument()
    })

    it('渲染自定义消息', () => {
      render(<EmptyState message="暂无插件" />)
      expect(screen.getByText('暂无插件')).toBeInTheDocument()
    })
  })

  describe('PageShell', () => {
    it('渲染标题', () => {
      render(<PageShell title="插件管理">内容</PageShell>)
      expect(screen.getByText('插件管理')).toBeInTheDocument()
    })

    it('渲染内容区', () => {
      render(<PageShell title="测试">内容区文本</PageShell>)
      expect(screen.getByText('内容区文本')).toBeInTheDocument()
    })

    it('渲染面包屑', () => {
      render(
        <PageShell title="详情页" breadcrumb={['插件', '列表', '详情']}>
          内容
        </PageShell>
      )
      const nav = screen.getByRole('navigation', { name: '面包屑' })
      expect(nav).toHaveTextContent('插件')
      expect(nav).toHaveTextContent('列表')
      expect(nav).toHaveTextContent('详情')
    })

    it('无面包屑时不渲染 nav', () => {
      const { container } = render(<PageShell title="测试">内容</PageShell>)
      expect(container.querySelector('nav')).toBeNull()
    })

    it('渲染右侧操作区', () => {
      render(
        <PageShell title="测试" actions={<button>新增</button>}>
          内容
        </PageShell>
      )
      expect(screen.getByText('新增')).toBeInTheDocument()
    })
  })

  describe('三态切换', () => {
    it('isLoading → LoadingSkeleton', () => {
      render(<LoadingSkeleton />)
      expect(screen.getByTestId('loading-skeleton')).toBeInTheDocument()
    })

    it('isError → ErrorState', () => {
      render(<ErrorState error={new Error('失败')} />)
      expect(screen.getByTestId('error-state')).toBeInTheDocument()
    })

    it('isEmpty → EmptyState', () => {
      render(<EmptyState />)
      expect(screen.getByTestId('empty-state')).toBeInTheDocument()
    })
  })
})