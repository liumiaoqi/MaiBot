import type { ComponentType, ReactNode } from 'react'
import type { LucideProps } from 'lucide-react'

export interface LayoutProps {
  children: ReactNode
}

export type WorkspaceMode = 'settings' | 'chat'

export interface MenuItem {
  icon: ComponentType<LucideProps>
  label: string
  path: string
  searchDescription?: string
  tourId?: string
}

export interface MenuSection {
  title: string
  items: MenuItem[]
}
