import { backendApi } from '@/lib/http'

const API_BASE = '/api/webui/agents/migration'

export interface MigrationState {
  plugin_id: string
  plugin_name: string
  current_phase: string
  previous_phase: string
  last_updated: number
  notes: string
}

export interface MigrationAdvanceResult {
  success: boolean
  plugin_id: string
  current_phase: string
  previous_phase: string
}

export async function getMigrationStates(): Promise<MigrationState[]> {
  return backendApi.get<MigrationState[]>(API_BASE + '/states')
}

export async function advanceMigration(pluginId: string): Promise<MigrationAdvanceResult> {
  return backendApi.post<MigrationAdvanceResult>(API_BASE + `/${pluginId}/advance`)
}