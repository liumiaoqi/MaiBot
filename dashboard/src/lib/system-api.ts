import { fetchWithAuth, getAuthHeaders } from './fetch-with-auth'

/**
 * 系统控制 API
 */

/**
 * 重启麦麦主程序
 */
export async function restartMaiBot(): Promise<{ success: boolean; message: string }> {
  const response = await fetchWithAuth('/api/webui/system/restart', {
    method: 'POST',
    headers: getAuthHeaders(),
  })
  
  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || '重启失败')
  }
  
  return await response.json()
}

/**
 * 检查麦麦运行状态
 */
export async function getMaiBotStatus(): Promise<{
  running: boolean
  uptime: number
  version: string
  start_time: string
}> {
  const response = await fetchWithAuth('/api/webui/system/status', {
    method: 'GET',
    headers: getAuthHeaders(),
  })
  
  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || '获取状态失败')
  }
  
  return await response.json()
}

export interface DashboardVersionStatus {
  current_version: string
  latest_version: string | null
  has_update: boolean
  package_name: string
  pypi_url: string
}

/**
 * 检查 WebUI 是否有 PyPI 新版本
 */
export async function getDashboardVersionStatus(
  currentVersion: string
): Promise<DashboardVersionStatus> {
  const params = new URLSearchParams({ current_version: currentVersion })
  const response = await fetchWithAuth(`/api/webui/system/dashboard-version?${params.toString()}`, {
    method: 'GET',
    headers: getAuthHeaders(),
  })

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || '获取 WebUI 版本失败')
  }

  return await response.json()
}
