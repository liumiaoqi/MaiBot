/**
 * DashboardTabs 测试（R4-1-2-3 测试先行）
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { DashboardTabBar, DashboardTabTrigger } from '../dashboard-tabs'
import { Tabs, TabsContent } from '../tabs'

function renderTabs(props: { variant?: 'grid' | 'scroll' } = {}) {
  return render(
    <Tabs defaultValue="tab1">
      <DashboardTabBar variant={props.variant}>
        <DashboardTabTrigger value="tab1">标签1</DashboardTabTrigger>
        <DashboardTabTrigger value="tab2">标签2</DashboardTabTrigger>
      </DashboardTabBar>
      <TabsContent value="tab1">内容1</TabsContent>
      <TabsContent value="tab2">内容2</TabsContent>
    </Tabs>
  )
}

describe('DashboardTabs 统计 Tabs 网格布局', () => {
  it('渲染 Tabs 标签', () => {
    renderTabs()
    expect(screen.getByText('标签1')).toBeInTheDocument()
    expect(screen.getByText('标签2')).toBeInTheDocument()
  })

  it('variant=grid 时无滚动包装', () => {
    const { container } = renderTabs({ variant: 'grid' })
    expect(container.querySelector('[data-dashboard-tab-scroll="true"]')).not.toBeTruthy()
  })

  it('variant=scroll 时有滚动包装', () => {
    const { container } = renderTabs({ variant: 'scroll' })
    expect(container.querySelector('[data-dashboard-tab-scroll="true"]')).toBeTruthy()
  })
})