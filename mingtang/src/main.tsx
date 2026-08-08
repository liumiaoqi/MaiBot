import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider } from '@tanstack/react-router'
import { router } from './app/router'
import './i18n'
import './styles/index.css'

const root = document.getElementById('root')
if (!root) {
  throw new Error('根元素 #root 不存在')
}

createRoot(root).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
)