import React, { createContext, useContext, useState, useEffect } from 'react'
import { orgApi, OrgResponse } from '../lib/api'

interface OrgContextType {
  selectedOrgId: string
  setSelectedOrgId: (id: string) => void
  organizations: OrgResponse[]
  currentOrg: OrgResponse | null
  loadingOrgs: boolean
  refreshOrgs: () => Promise<void>
}

const OrgContext = createContext<OrgContextType | undefined>(undefined)

const STORAGE_KEY = 'hekma_admin_selected_org'

const GLOBAL_ALL_ORG: OrgResponse = {
  id: 'all',
  name: '🌐 All Tenants (Global Vault)',
  contact_email: 'admin@hekma.ai',
  api_key: 'org_sk_live_••••••••••••••••',
  audit_retention_days: 0,
  token_ttl_days: 0,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
}

export const OrgProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [selectedOrgId, setSelectedOrgIdState] = useState<string>(() => {
    return localStorage.getItem(STORAGE_KEY) || 'all'
  })
  const [organizations, setOrganizations] = useState<OrgResponse[]>([GLOBAL_ALL_ORG])
  const [loadingOrgs, setLoadingOrgs] = useState<boolean>(true)

  const refreshOrgs = async () => {
    try {
      setLoadingOrgs(true)
      const list = await orgApi.list()
      const combined = [GLOBAL_ALL_ORG, ...list]
      setOrganizations(combined)
      
      // If selectedOrgId is not in the list, default to 'all'
      if (!combined.some(o => o.id === selectedOrgId)) {
        setSelectedOrgIdState('all')
        localStorage.setItem(STORAGE_KEY, 'all')
      }
    } catch (err) {
      console.error('Failed to load organizations from database:', err)
    } finally {
      setLoadingOrgs(false)
    }
  }

  useEffect(() => {
    refreshOrgs()
  }, [])

  const setSelectedOrgId = (id: string) => {
    setSelectedOrgIdState(id)
    localStorage.setItem(STORAGE_KEY, id)
  }

  const currentOrg = organizations.find(o => o.id === selectedOrgId) || (
    organizations.length > 0 ? organizations[0] : null
  )

  return (
    <OrgContext.Provider
      value={{
        selectedOrgId,
        setSelectedOrgId,
        organizations,
        currentOrg,
        loadingOrgs,
        refreshOrgs,
      }}
    >
      {children}
    </OrgContext.Provider>
  )
}

export const useOrg = (): OrgContextType => {
  const context = useContext(OrgContext)
  if (!context) {
    throw new Error('useOrg must be used within an OrgProvider')
  }
  return context
}
