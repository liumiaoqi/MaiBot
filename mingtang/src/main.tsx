import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClientProvider } from '@tanstack/react-query'
import { RouterProvider } from '@tanstack/react-router'
import { router } from './app/router'
import { queryClient } from './app/query-client'
import { ThemeProvider } from './app/theme-provider'
import './i18n'
import './styles/index.css'

const root = document.getElementById('root')
if (!root) {
  throw new Error('根元素 #root 不存在')
}

createRoot(root).render(
  <StrictMode>
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </ThemeProvider>
  </StrictMode>,
)