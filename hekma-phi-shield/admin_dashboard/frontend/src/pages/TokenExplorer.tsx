import { useState, useEffect } from 'react'
import {
  Search,
  Database,
  Calendar,
  ChevronLeft,
  ChevronRight,
  Shield,
  Key,
  Download,
  AlertCircle,
  CheckCircle,
  RefreshCw,
  Lock,
  Unlock,
  Info,
  X,
  Eye,
  EyeOff,
  Copy,
  Check,
} from 'lucide-react'
import { tokenApi, policyApi } from '../lib/api'
import { useOrg } from '../context/OrgContext'
import { format, parseISO } from 'date-fns'
import './TokenExplorer.css'

interface TokenMapping {
  id: string
  org_id?: string
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

interface TokenStats {
  total_mappings: number
  by_entity_type: Record<string, number>
  by_policy: Record<string, number>
  restored_count: number
  expired_count: number
}

export function TokenExplorer() {
  const [mappings, setMappings] = useState<TokenMapping[]>([])
  const [stats, setStats] = useState<TokenStats | null>(null)
  const [entityTypes, setEntityTypes] = useState<string[]>([])
  const [loading, setLoading] = useState(false)
  const [total, setTotal] = useState(0)

  // Pagination & Filters
  const [page, setPage] = useState(1)
  const [pageSize] = useState(15)
  const [searchQuery, setSearchQuery] = useState('')
  const [entityTypeFilter, setEntityTypeFilter] = useState('')
  const [policyFilter, setPolicyFilter] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')

  // Multi-select & Reveal states
  const [selectedTokens, setSelectedTokens] = useState<Set<string>>(new Set())
  const [revealedOriginals, setRevealedOriginals] = useState<Set<string>>(new Set())
  const [copiedToken, setCopiedToken] = useState<string | null>(null)

  // Restore Modal State
  const [showRestoreModal, setShowRestoreModal] = useState(false)
  const [singleTokenToRestore, setSingleTokenToRestore] = useState<string | null>(null)
  const [restorePurpose, setRestorePurpose] = useState<'trial_matching' | 'db_storage' | 'audit' | 'patient_care' | 'research'>('patient_care')
  const [restoreRequester, setRestoreRequester] = useState('admin-user')
  const [restoreIp, setRestoreIp] = useState('127.0.0.1')
  const [restoring, setRestoring] = useState(false)
  const [restoreError, setRestoreError] = useState<string | null>(null)
  const [restoreResults, setRestoreResults] = useState<any[] | null>(null)
  const [exporting, setExporting] = useState(false)

  useEffect(() => {
    fetchMappings()
    fetchMetadata()
  }, [page, entityTypeFilter, policyFilter, dateFrom, dateTo])

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setPage(1)
    fetchMappings()
  }

  const fetchMappings = async () => {
    setLoading(true)
    try {
      const params = {
        org_id: 'all',
        tokenized_value: searchQuery || undefined,
        entity_type: entityTypeFilter || undefined,
        policy_applied: policyFilter || undefined,
        date_from: dateFrom ? new Date(dateFrom).toISOString() : undefined,
        date_to: dateTo ? new Date(dateTo).toISOString() : undefined,
        limit: pageSize,
        offset: (page - 1) * pageSize,
      }
      const response = await tokenApi.search(params)
      setMappings(response.items)
      setTotal(response.total)
    } catch (err) {
      console.error('Failed to fetch token mappings:', err)
    } finally {
      setLoading(false)
    }
  }

  const fetchMetadata = async () => {
    try {
      const [typesRes, statsRes] = await Promise.all([
        policyApi.getEntityTypes().catch(() => ({ entity_types: [], count: 0 })),
        tokenApi.stats('all').catch(() => ({
          total_mappings: 0,
          by_entity_type: {},
          by_policy: {},
          restored_count: 0,
          expired_count: 0,
        })),
      ])
      setEntityTypes(typesRes.entity_types)
      setStats(statsRes)
    } catch (err) {
      console.error('Failed to fetch metadata:', err)
    }
  }

  const handleResetFilters = () => {
    setSearchQuery('')
    setEntityTypeFilter('')
    setPolicyFilter('')
    setDateFrom('')
    setDateTo('')
    setPage(1)
  }

  const handleExport = async () => {
    setExporting(true)
    try {
      const response = await tokenApi.search({
        org_id: 'all',
        tokenized_value: searchQuery || undefined,
        entity_type: entityTypeFilter || undefined,
        policy_applied: policyFilter || undefined,
        date_from: dateFrom ? new Date(dateFrom).toISOString() : undefined,
        date_to: dateTo ? new Date(dateTo).toISOString() : undefined,
        limit: 10000,
        offset: 0,
      })

      const headers = ['Created At', 'Patient/Tenant ID', 'Tokenized Value', 'Original Value', 'Entity Type', 'Policy Applied', 'Confidence', 'Expires At', 'Restored At']
      const rows = response.items.map((m: any) => [
        m.created_at ? format(parseISO(m.created_at), 'yyyy-MM-dd HH:mm:ss') : '',
        m.org_id || 'default-org',
        m.tokenized_value,
        m.original_value,
        m.entity_type,
        m.policy_applied,
        `${(m.confidence * 100).toFixed(1)}%`,
        m.expires_at || 'Never',
        m.restored_at || 'No'
      ])

      const csv = [headers.join(','), ...rows.map((r: any) => r.map((c: any) => `"${String(c).replace(/"/g, '""')}"`).join(','))].join('\n')
      const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
      const link = document.createElement('a')
      link.href = URL.createObjectURL(blob)
      link.download = `token-vault-export-${format(new Date(), 'yyyy-MM-dd')}.csv`
      link.click()
      URL.revokeObjectURL(link.href)
    } catch (err) {
      console.error('Export failed:', err)
    } finally {
      setExporting(false)
    }
  }

  const handleSelectAll = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.checked) {
      const allOnPage = new Set(selectedTokens)
      mappings.forEach(m => allOnPage.add(m.tokenized_value))
      setSelectedTokens(allOnPage)
    } else {
      const nextSelected = new Set(selectedTokens)
      mappings.forEach(m => nextSelected.delete(m.tokenized_value))
      setSelectedTokens(nextSelected)
    }
  }

  const handleSelectRow = (tokenizedValue: string, checked: boolean) => {
    const nextSelected = new Set(selectedTokens)
    if (checked) {
      nextSelected.add(tokenizedValue)
    } else {
      nextSelected.delete(tokenizedValue)
    }
    setSelectedTokens(nextSelected)
  }

  const toggleRevealOriginal = (tokenizedValue: string) => {
    const nextRevealed = new Set(revealedOriginals)
    if (nextRevealed.has(tokenizedValue)) {
      nextRevealed.delete(tokenizedValue)
    } else {
      nextRevealed.add(tokenizedValue)
    }
    setRevealedOriginals(nextRevealed)
  }

  const handleCopyToken = (val: string) => {
    navigator.clipboard.writeText(val)
    setCopiedToken(val)
    setTimeout(() => setCopiedToken(null), 2000)
  }

  // Restore Modal handlers
  const openRestoreModalForSingle = (tokenizedValue: string) => {
    setSingleTokenToRestore(tokenizedValue)
    setShowRestoreModal(true)
    setRestoreResults(null)
    setRestoreError(null)
  }

  const openRestoreModalForBulk = () => {
    setSingleTokenToRestore(null)
    setShowRestoreModal(true)
    setRestoreResults(null)
    setRestoreError(null)
  }

  const handleRestoreSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setRestoring(true)
    setRestoreError(null)
    setRestoreResults(null)

    const tokensToRestore = singleTokenToRestore 
      ? [singleTokenToRestore] 
      : Array.from(selectedTokens)

    if (tokensToRestore.length === 0) {
      setRestoreError('No tokens selected for restoration.')
      setRestoring(false)
      return
    }

    try {
      const payload = {
        tokenized_values: tokensToRestore,
        org_id: 'default-org',
        purpose: restorePurpose,
        requester_id: restoreRequester,
        ip_address: restoreIp
      }

      const response = await tokenApi.restore(payload)
      setRestoreResults(response.results)
      setSelectedTokens(new Set())
      fetchMappings()
      fetchMetadata()
    } catch (err: any) {
      setRestoreError(err.message || 'An error occurred during restoration.')
    } finally {
      setRestoring(false)
    }
  }

  const getTotalPages = () => Math.ceil(total / pageSize) || 1
  const isAllPageSelected = () => mappings.length > 0 && mappings.every(m => selectedTokens.has(m.tokenized_value))

  return (
    <div className="token-explorer-page">
      {/* Header */}
      <div className="token-page-header">
        <div>
          <h1>Token Vault Explorer</h1>
          <p className="token-subtitle">Browse, securely decrypt, and manage format-preserving surrogate tokens in PostgreSQL</p>
        </div>
        <div style={{ display: 'flex', gap: '10px' }}>
          <button 
            type="button" 
            onClick={fetchMappings} 
            className="btn-outline-sm"
            style={{ padding: '9px 14px' }}
          >
            <RefreshCw size={15} className={loading ? 'animate-spin' : ''} /> Refresh
          </button>
          <button 
            type="button" 
            onClick={handleExport}
            disabled={exporting || mappings.length === 0}
            className="btn-primary"
            style={{ padding: '9px 18px', fontSize: '13.5px' }}
          >
            <Download size={15} />
            {exporting ? 'Exporting...' : 'Export Vault CSV'}
          </button>
        </div>
      </div>

      {/* 4-Stat Metric Cards */}
      <div className="token-stats-grid">
        <div className="token-stat-card total-card">
          <span className="token-stat-num">{stats?.total_mappings ?? total}</span>
          <span className="token-stat-label">Total Vault Tokens</span>
        </div>
        <div className="token-stat-card active-card">
          <span className="token-stat-num" style={{ color: '#10b981' }}>
            {(stats?.total_mappings ?? total) - (stats?.expired_count ?? 0)}
          </span>
          <span className="token-stat-label">Active Protected Tokens</span>
        </div>
        <div className="token-stat-card restore-card">
          <span className="token-stat-num" style={{ color: '#7958A5' }}>
            {stats?.restored_count ?? 0}
          </span>
          <span className="token-stat-label">Detokenized Restores</span>
        </div>
        <div className="token-stat-card entity-card">
          <span className="token-stat-num" style={{ color: '#f59e0b' }}>
            {Object.keys(stats?.by_entity_type || {}).length || 6}
          </span>
          <span className="token-stat-label">Distinct Entity Types</span>
        </div>
      </div>

      {/* Filter Card */}
      <div className="token-filter-card">
        <form onSubmit={handleSearchSubmit}>
          <div className="token-filter-row">
            <div className="token-filter-field" style={{ gridColumn: 'span 2' }}>
              <label>Search Tokens / Plaintext</label>
              <div style={{ position: 'relative' }}>
                <Search size={16} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: '#94a3b8' }} />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={e => setSearchQuery(e.target.value)}
                  placeholder="Search token (e.g. PAT_..., CITY_...) or decrypted values..."
                  className="token-filter-input"
                  style={{ paddingLeft: '38px' }}
                />
              </div>
            </div>

            <div className="token-filter-field">
              <label>Entity Category</label>
              <select
                value={entityTypeFilter}
                onChange={e => { setEntityTypeFilter(e.target.value); setPage(1); }}
                className="token-filter-input"
              >
                <option value="">All Entity Types</option>
                {entityTypes.map(t => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </div>

            <div className="token-filter-field">
              <label>Policy Strategy</label>
              <select
                value={policyFilter}
                onChange={e => { setPolicyFilter(e.target.value); setPage(1); }}
                className="token-filter-input"
              >
                <option value="">All Policies</option>
                <option value="anonymize">Anonymize / Normalize</option>
                <option value="redact">Redact</option>
                <option value="ignore">Ignore</option>
              </select>
            </div>

            <div className="token-filter-field">
              <label>Created From</label>
              <input
                type="date"
                value={dateFrom}
                onChange={e => { setDateFrom(e.target.value); setPage(1); }}
                className="token-filter-input"
              />
            </div>

            <div className="token-filter-field">
              <label>Created To</label>
              <input
                type="date"
                value={dateTo}
                onChange={e => { setDateTo(e.target.value); setPage(1); }}
                className="token-filter-input"
              />
            </div>

            <div style={{ display: 'flex', gap: '8px' }}>
              <button type="submit" className="btn-primary" style={{ padding: '10px 18px', fontSize: '13.5px' }}>
                <Search size={14} /> Filter
              </button>
              <button type="button" onClick={handleResetFilters} className="btn-outline-sm" style={{ padding: '10px 14px' }}>
                Reset
              </button>
            </div>
          </div>
        </form>
      </div>

      {/* Bulk Action Bar */}
      {selectedTokens.size > 0 && (
        <div className="bulk-selection-bar">
          <span className="bulk-count">
            ✓ {selectedTokens.size} token(s) selected across current view
          </span>
          <div style={{ display: 'flex', gap: '10px' }}>
            <button
              type="button"
              className="btn-primary"
              onClick={openRestoreModalForBulk}
              style={{ padding: '8px 16px', fontSize: '13px' }}
            >
              <Key size={14} /> Authorize & Restore Selected ({selectedTokens.size})
            </button>
            <button
              type="button"
              className="btn-outline-sm"
              onClick={() => setSelectedTokens(new Set())}
              style={{ padding: '8px 14px', fontSize: '13px' }}
            >
              Cancel Selection
            </button>
          </div>
        </div>
      )}

      {/* Table Card */}
      <div className="token-table-card">
        <div className="token-table-header">
          <span className="token-table-title">Live Vault Token Mappings</span>
          <span className="token-table-count">
            Showing {total > 0 ? (page - 1) * pageSize + 1 : 0} - {Math.min(page * pageSize, total)} of {total} tokens
          </span>
        </div>

        <div className="token-table-container">
          <table className="token-table">
            <thead>
              <tr>
                <th style={{ width: '40px', textAlign: 'center' }}>
                  <input
                    type="checkbox"
                    checked={isAllPageSelected()}
                    onChange={handleSelectAll}
                  />
                </th>
                <th>Patient / Tenant ID</th>
                <th>Tokenized Value</th>
                <th>Original Value (Decrypted Preview)</th>
                <th>Entity Type</th>
                <th>Policy Applied</th>
                <th>Confidence</th>
                <th>Created At (Latest ↓)</th>
                <th>Expires At</th>
                <th>Status</th>
                <th style={{ textAlign: 'right' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={11} style={{ textAlign: 'center', padding: '40px', color: '#64748b' }}>
                    <RefreshCw size={24} className="animate-spin" style={{ margin: '0 auto 8px', color: '#ED248F' }} />
                    <p>Loading encrypted token mappings from PostgreSQL...</p>
                  </td>
                </tr>
              ) : mappings.length === 0 ? (
                <tr>
                  <td colSpan={11} style={{ textAlign: 'center', padding: '40px', color: '#64748b' }}>
                    <Database size={40} style={{ margin: '0 auto 8px', color: '#cbd5e1' }} />
                    <h3>No token mappings found</h3>
                    <p>Try refining your search query or adjusting your filters.</p>
                  </td>
                </tr>
              ) : (
                mappings.map(mapping => {
                  const isSelected = selectedTokens.has(mapping.tokenized_value)
                  const isRevealed = revealedOriginals.has(mapping.tokenized_value)
                  const isCopied = copiedToken === mapping.tokenized_value

                  return (
                    <tr key={mapping.id} className={isSelected ? 'selected-row' : ''}>
                      <td style={{ textAlign: 'center' }}>
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={e => handleSelectRow(mapping.tokenized_value, e.target.checked)}
                        />
                      </td>
                      <td>
                        <span className="tenant-id-pill">
                          {mapping.org_id || 'default-org'}
                        </span>
                      </td>
                      <td>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                          <span className="token-badge">{mapping.tokenized_value}</span>
                          <button
                            type="button"
                            onClick={() => handleCopyToken(mapping.tokenized_value)}
                            className="btn-ghost"
                            style={{ padding: '3px' }}
                            title="Copy token to clipboard"
                          >
                            {isCopied ? <Check size={13} color="#10b981" /> : <Copy size={13} color="#94a3b8" />}
                          </button>
                        </div>
                      </td>
                      <td>
                        <div className="decrypted-value-cell">
                          {isRevealed ? (
                            <span className="revealed-text">{mapping.original_value}</span>
                          ) : (
                            <span className="masked-dots">••••••••••••</span>
                          )}
                          <button
                            type="button"
                            className="btn-ghost"
                            onClick={() => toggleRevealOriginal(mapping.tokenized_value)}
                            style={{ padding: '3px' }}
                            title={isRevealed ? 'Mask original value' : 'Decrypt & reveal preview'}
                          >
                            {isRevealed ? <EyeOff size={14} color="#64748b" /> : <Eye size={14} color="#7958A5" />}
                          </button>
                        </div>
                      </td>
                      <td>
                        <span className="entity-pill">{mapping.entity_type}</span>
                      </td>
                      <td>
                        <span className={`policy-chip ${mapping.policy_applied === 'anonymize' ? 'anonymize' : mapping.policy_applied === 'redact' ? 'redact' : 'ignore'}`}>
                          {mapping.policy_applied}
                        </span>
                      </td>
                      <td>
                        <span style={{ fontWeight: 700, color: '#334155' }}>
                          {(mapping.confidence * 100).toFixed(0)}%
                        </span>
                      </td>
                      <td style={{ whiteSpace: 'nowrap', color: '#64748b' }}>
                        {format(parseISO(mapping.created_at), 'yyyy-MM-dd HH:mm')}
                      </td>
                      <td style={{ color: '#64748b' }}>
                        {mapping.expires_at ? format(parseISO(mapping.expires_at), 'yyyy-MM-dd') : 'Permanent (HIPAA)'}
                      </td>
                      <td>
                        {mapping.restored_at ? (
                          <span style={{ background: '#e0e7ff', color: '#4338ca', padding: '3px 8px', borderRadius: '6px', fontSize: '11.5px', fontWeight: 700 }}>
                            Restored
                          </span>
                        ) : (
                          <span style={{ background: '#dcfce7', color: '#15803d', padding: '3px 8px', borderRadius: '6px', fontSize: '11.5px', fontWeight: 700 }}>
                            Active
                          </span>
                        )}
                      </td>
                      <td style={{ textAlign: 'right' }}>
                        <button
                          type="button"
                          className="btn-restore-action"
                          onClick={() => openRestoreModalForSingle(mapping.tokenized_value)}
                          title="Authorize Detokenization (Reverse to Plaintext)"
                        >
                          <Key size={13} /> Restore
                        </button>
                      </td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        <div className="token-pagination-bar">
          <span style={{ fontSize: '13px', color: '#64748b' }}>
            Page {page} of {getTotalPages()}
          </span>
          <div style={{ display: 'flex', gap: '8px' }}>
            <button
              type="button"
              onClick={() => setPage(p => Math.max(1, p - 1))}
              disabled={page === 1}
              className="btn-outline-sm"
            >
              <ChevronLeft size={15} /> Previous
            </button>
            <button
              type="button"
              onClick={() => setPage(p => Math.min(getTotalPages(), p + 1))}
              disabled={page === getTotalPages()}
              className="btn-outline-sm"
            >
              Next <ChevronRight size={15} />
            </button>
          </div>
        </div>
      </div>

      {/* Detokenization Restore Modal */}
      {showRestoreModal && (
        <div className="token-modal-overlay" onClick={() => setShowRestoreModal(false)}>
          <div className="token-modal-card" onClick={e => e.stopPropagation()}>
            <div className="token-modal-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <Key size={18} color="#ED248F" />
                <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 800 }}>
                  Authorize HIPAA Reverse Detokenization
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setShowRestoreModal(false)}
                className="btn-outline-sm"
                style={{ padding: '6px 8px' }}
              >
                <X size={16} />
              </button>
            </div>

            <div className="token-modal-body">
              {!restoreResults ? (
                <form onSubmit={handleRestoreSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                  <div className="compliance-alert-box">
                    <AlertCircle size={20} style={{ flexShrink: 0, marginTop: '2px' }} />
                    <div style={{ fontSize: '12.5px', lineHeight: 1.4 }}>
                      <strong style={{ display: 'block', marginBottom: '2px', fontSize: '13px' }}>
                        HIPAA § 164.312 Regulatory Notice
                      </strong>
                      Restoring vaulted tokens reveals raw Protected Health Information (PHI). This action is cryptographically signed and permanently logged in the PostgreSQL compliance audit trail.
                    </div>
                  </div>

                  <div style={{ background: '#f8fafc', padding: '12px 14px', borderRadius: '8px', border: '1px dashed #cbd5e1', fontSize: '13px' }}>
                    <strong>Target Token(s):</strong>{' '}
                    <code style={{ color: '#7958A5', fontWeight: 700 }}>
                      {singleTokenToRestore || `${selectedTokens.size} bulk tokens selected`}
                    </code>
                  </div>

                  <div className="token-filter-field">
                    <label>Purpose of Restoration (Required)</label>
                    <select
                      value={restorePurpose}
                      onChange={e => setRestorePurpose(e.target.value as any)}
                      className="token-filter-input"
                    >
                      <option value="patient_care">Direct Patient Care / Clinical Encounter</option>
                      <option value="trial_matching">Clinical Trial Matching</option>
                      <option value="audit">Regulatory Audit / Legal Request</option>
                      <option value="research">IRB Approved Clinical Research</option>
                      <option value="db_storage">Database Storage Synchronization</option>
                    </select>
                  </div>

                  <div className="token-filter-field">
                    <label>Authorized Clinician / User ID</label>
                    <input
                      type="text"
                      value={restoreRequester}
                      onChange={e => setRestoreRequester(e.target.value)}
                      className="token-filter-input"
                      placeholder="e.g. dr_smith, admin_user"
                    />
                  </div>

                  {restoreError && (
                    <div style={{ background: '#fff1f2', border: '1px solid #fecdd3', color: '#9f1239', padding: '10px 14px', borderRadius: '8px', fontSize: '13px' }}>
                      {restoreError}
                    </div>
                  )}

                  <div className="token-modal-footer" style={{ margin: '0 -22px -22px', padding: '16px 22px' }}>
                    <button
                      type="button"
                      onClick={() => setShowRestoreModal(false)}
                      className="btn-outline-sm"
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      disabled={restoring}
                      className="btn-primary"
                    >
                      {restoring ? <RefreshCw size={15} className="animate-spin" /> : <Key size={15} />}
                      {restoring ? 'Decrypted from Vault...' : 'Authorize & Detokenize'}
                    </button>
                  </div>
                </form>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                  <div style={{ textAlign: 'center', padding: '10px 0' }}>
                    <CheckCircle size={36} color="#10b981" style={{ margin: '0 auto 8px' }} />
                    <h4 style={{ margin: 0, fontSize: '16px', fontWeight: 800 }}>
                      Tokens Successfully Restored
                    </h4>
                    <p style={{ color: '#64748b', fontSize: '13px', margin: '4px 0 0' }}>
                      Decrypted securely and logged in HIPAA compliance trail
                    </p>
                  </div>

                  <div style={{ maxHeight: '220px', overflowY: 'auto', border: '1px solid #e2e8f0', borderRadius: '8px' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
                      <thead>
                        <tr style={{ background: '#f8fafc', borderBottom: '1px solid #e2e8f0' }}>
                          <th style={{ padding: '8px 12px', textAlign: 'left' }}>Token</th>
                          <th style={{ padding: '8px 12px', textAlign: 'left' }}>Restored Value</th>
                        </tr>
                      </thead>
                      <tbody>
                        {restoreResults.map((r, i) => (
                          <tr key={i} style={{ borderBottom: '1px solid #f1f5f9' }}>
                            <td style={{ padding: '8px 12px', fontFamily: 'monospace', color: '#7958A5' }}>
                              {r.tokenized_value}
                            </td>
                            <td style={{ padding: '8px 12px', fontFamily: 'monospace', fontWeight: 700, color: '#10b981' }}>
                              {r.original_value}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>

                  <div className="token-modal-footer" style={{ margin: '0 -22px -22px', padding: '16px 22px' }}>
                    <button
                      type="button"
                      onClick={() => setShowRestoreModal(false)}
                      className="btn-primary"
                    >
                      Close Window
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
