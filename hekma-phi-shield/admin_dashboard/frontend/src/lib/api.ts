import axios, { InternalAxiosRequestConfig } from 'axios'

const ADMIN_KEY_STORAGE = 'hekma_admin_key'
const DEFAULT_FALLBACK_KEY = 'hekma_admin_live_1e2f3a4b'

export const getAdminKey = (): string => {
  return (
    localStorage.getItem(ADMIN_KEY_STORAGE) ||
    localStorage.getItem('admin_api_key') ||
    import.meta.env.VITE_ADMIN_KEY ||
    DEFAULT_FALLBACK_KEY
  )
}

export const setAdminKey = (key: string): void => {
  localStorage.setItem(ADMIN_KEY_STORAGE, key.trim())
}

export const clearAdminKey = (): void => {
  localStorage.removeItem(ADMIN_KEY_STORAGE)
  localStorage.removeItem('admin_api_key')
}

const attachInterceptors = (instance: ReturnType<typeof axios.create>) => {
  instance.interceptors.request.use((config: InternalAxiosRequestConfig) => {
    config.headers = config.headers || {}
    config.headers['X-Admin-Key'] = getAdminKey()
    return config
  })

  instance.interceptors.response.use(
    (response) => response.data,
    (error) => {
      const message = error.response?.data?.detail || error.message || 'Request failed'
      if (error.response?.status === 401) {
        window.dispatchEvent(new CustomEvent('hekma:admin-auth-failed', { detail: message }))
      }
      throw new Error(message)
    }
  )
  return instance
}

const createApi = () => {
  const instance = axios.create({
    baseURL: import.meta.env.VITE_API_URL || '',
    headers: {
      'Content-Type': 'application/json',
    },
    timeout: 30000,
  })
  return attachInterceptors(instance)
}

const axiosInstance = createApi()

// Helper to cast axios response (interceptor unwraps at runtime)
const unwrap = <T,>(promise: Promise<any>): Promise<T> => promise as unknown as Promise<T>

// API functions with proper return types (interceptor unwraps response.data at runtime)
export const policyApi = {
  getEntityTypes: (): Promise<{ entity_types: string[]; count: number }> => 
    axiosInstance.get<{ entity_types: string[]; count: number }>('/api/v1/entity-types') as unknown as Promise<{ entity_types: string[]; count: number }>,
  getPresets: () => axiosInstance.get<Record<string, Record<string, string>>>('/api/v1/policy-presets') as unknown as Promise<Record<string, Record<string, string>>>,
  list: (orgId: string) => axiosInstance.get<any[]>(`/api/v1/orgs/${orgId}/policies`) as unknown as Promise<any[]>,
  bulkUpdate: (orgId: string, policies: any[]) => axiosInstance.put<any[]>(`/api/v1/orgs/${orgId}/policies`, { policies }) as unknown as Promise<any[]>,
  applyPreset: (orgId: string, preset: string) => axiosInstance.post<any[]>(`/api/v1/orgs/${orgId}/policies/preset`, { preset, org_id: orgId }) as unknown as Promise<any[]>,
}

export const tokenApi = {
  search: (params: any) => axiosInstance.post<{ items: any[]; total: number; offset: number; limit: number }>('/api/v1/tokens/search', params) as unknown as Promise<{ items: any[]; total: number; offset: number; limit: number }>,
  restore: (payload: any) => axiosInstance.post<any>('/api/v1/tokens/restore', payload) as unknown as Promise<any>,
  stats: (orgId: string) => axiosInstance.get<any>(`/api/v1/tokens/stats/${orgId}`) as unknown as Promise<any>,
}

export const auditApi = {
  search: (params: any) => axiosInstance.post<{ items: any[]; total: number; offset: number; limit: number }>('/api/v1/audit/search', params) as unknown as Promise<{ items: any[]; total: number; offset: number; limit: number }>,
  stats: (orgId: string) => axiosInstance.get<any>(`/api/v1/audit/stats/${orgId}`) as unknown as Promise<any>,
}

export const orgApi = {
  list: (): Promise<OrgResponse[]> => axiosInstance.get<OrgResponse[]>('/api/v1/orgs') as unknown as Promise<OrgResponse[]>,
  get: (orgId: string): Promise<OrgResponse> => axiosInstance.get<OrgResponse>(`/api/v1/orgs/${orgId}`) as unknown as Promise<OrgResponse>,
  update: (orgId: string, data: Partial<OrgResponse>): Promise<OrgResponse> => axiosInstance.put<OrgResponse>(`/api/v1/orgs/${orgId}`, data) as unknown as Promise<OrgResponse>,
  rotateKey: (orgId: string): Promise<{ org_id: string; api_key: string; preview: string; message: string }> => 
    axiosInstance.post<{ org_id: string; api_key: string; preview: string; message: string }>(`/api/v1/orgs/${orgId}/api-key`) as unknown as Promise<{ org_id: string; api_key: string; preview: string; message: string }>,
  purgeExpired: (orgId?: string): Promise<{ purged_count: number; org_id: string; timestamp: string; status: string }> =>
    axiosInstance.post<{ purged_count: number; org_id: string; timestamp: string; status: string }>(`/api/v1/tokens/purge-expired${orgId ? `?org_id=${orgId}` : ''}`) as unknown as Promise<{ purged_count: number; org_id: string; timestamp: string; status: string }>,
}

export interface OrgResponse {
  id: string
  name: string
  contact_email?: string
  api_key?: string
  audit_retention_days: number
  token_ttl_days: number
  settings?: Record<string, any>
  created_at: string
  updated_at: string
}

// Main axios instance for direct calls (with dynamic interceptors)
export const api = createApi()

// Type definitions
export interface EntityTypesResponse {
  entity_types: string[]
  count: number
}

export interface PolicyPresetsResponse {
  [preset: string]: Record<string, string>
}

export interface PolicyResponse {
  id: string
  entity_type: string
  policy_type: string
  anonymize_strategy: string
  custom_replacement: string | null
  applies_to_internal: boolean
  applies_to_external: boolean
  org_id: string
  created_at: string
  updated_at: string
}

export interface TokenSearchParams {
  org_id: string
  tokenized_value?: string
  entity_type?: string
  policy_applied?: string
  date_from?: string
  date_to?: string
  limit?: number
  offset?: number
}

export interface TokenSearchResponse {
  items: TokenMapping[]
  total: number
  offset: number
  limit: number
}

export interface TokenMapping {
  id: string
  tokenized_value: string
  original_value: string
  entity_type: string
  policy_applied: string
  context_hash: string
  confidence: number
  created_at: string
  expires_at: string | null
  restored_at: string | null
  restored_by: string | null
}

export interface RestoreRequest {
  tokenized_values: string[]
  entity_types?: string[]
  org_id: string
  requester_id: string
  ip_address: string
  purpose: 'trial_matching' | 'db_storage' | 'audit' | 'patient_care' | 'research'
}

export interface RestoreResult {
  original_value: string
  tokenized_value: string
  entity_type: string
  restored: boolean
  error?: string
}

export interface RestoreResponse {
  results: RestoreResult[]
}

export interface TokenStatsResponse {
  total_mappings: number
  by_entity_type: Record<string, number>
  by_policy: Record<string, number>
  restored_count: number
  expired_count: number
}

export interface AuditSearchParams {
  org_id: string
  action?: string
  entity_type?: string
  performed_by?: string
  date_from?: string
  date_to?: string
  limit?: number
  offset?: number
}

export interface AuditEntry {
  id: string
  action: string
  entity_type: string | null
  tokenized_value: string | null
  performed_by: string
  ip_address: string | null
  metadata: Record<string, any>
  created_at: string
}

export interface AuditSearchResponse {
  items: AuditEntry[]
  total: number
  offset: number
  limit: number
}

export interface AuditStatsResponse {
  total_events: number
  by_action: Record<string, number>
  by_entity_type: Record<string, number>
  by_user: Record<string, number>
}

export interface TokenStatsResponse {
  total_mappings: number
  by_entity_type: Record<string, number>
  by_policy: Record<string, number>
  restored_count: number
  expired_count: number
}

export interface RestoreTokenRequest {
  tokenized_values: string[]
  entity_types?: string[]
  org_id: string
  requester_id: string
  ip_address: string
  purpose: 'trial_matching' | 'db_storage' | 'audit' | 'patient_care' | 'research'
}

export interface RestoreTokenResponse {
  results: {
    original_value: string
    tokenized_value: string
    entity_type: string
    restored: boolean
    error?: string
  }[]
}

export interface TokenStatsResponse {
  total_mappings: number
  by_entity_type: Record<string, number>
  by_policy: Record<string, number>
  restored_count: number
  expired_count: number
}

export interface RestoreTokenRequest {
  tokenized_values: string[]
  entity_types?: string[]
  org_id: string
  requester_id: string
  ip_address: string
  purpose: 'trial_matching' | 'db_storage' | 'audit' | 'patient_care' | 'research'
}

export interface RestoreTokenResponse {
  results: {
    original_value: string
    tokenized_value: string
    entity_type: string
    restored: boolean
    error?: string
  }[]
}
