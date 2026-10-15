import { useState, useEffect } from 'react'
import { 
  Search, 
  Download, 
  ChevronLeft, 
  ChevronRight, 
  FileText, 
  AlertCircle, 
  Key, 
  Shield,
  RefreshCw,
  X,
  Code,
  Calendar,
  User,
  Filter,
} from 'lucide-react'
import { auditApi, policyApi } from '../lib/api'
import { format, parseISO } from 'date-fns'
import './AuditLog.css'

interface AuditEntry {
  id: string
  org_id?: string
  action: string
  entity_type: string | null
  tokenized_value: string | null
  performed_by: string
  ip_address: string | null
  metadata: Record<string, any>
  created_at: string
}

interface AuditStats {
  total_events: number
  by_action: Record<string, number>
  by_entity_type: Record<string, number>
  by_user: Record<string, number>
}

export function AuditLog() {
  const [logs, setLogs] = useState<AuditEntry[]>([])
  const [stats, setStats] = useState<AuditStats | null>(null)
  const [loading, setLoading] = useState(false)
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize] = useState(25)
  
  // Filters
  const [actionFilter, setActionFilter] = useState<string>('')
  const [entityTypeFilter, setEntityTypeFilter] = useState<string>('')
  const [userFilter, setUserFilter] = useState<string>('')
  const [dateFrom, setDateFrom] = useState<string>('')
  const [dateTo, setDateTo] = useState<string>('')
  const [entityTypes, setEntityTypes] = useState<string[]>([])
  const [actions, setActions] = useState<string[]>([])
  
  const [exporting, setExporting] = useState(false)
  const [selectedLog, setSelectedLog] = useState<AuditEntry | null>(null)

  useEffect(() => {
    fetchLogs()
    fetchMetadata()
  }, [page, actionFilter, entityTypeFilter, userFilter, dateFrom, dateTo])

  const fetchLogs = async () => {
    setLoading(true)
    try {
      const params = {
        org_id: 'all',
        action: actionFilter || undefined,
        entity_type: entityTypeFilter || undefined,
        performed_by: userFilter || undefined,
        date_from: dateFrom ? new Date(dateFrom).toISOString() : undefined,
        date_to: dateTo ? new Date(dateTo).toISOString() : undefined,
        limit: pageSize,
        offset: (page - 1) * pageSize,
      }
      const response = await auditApi.search(params)
      setLogs(response.items)
      setTotal(response.total)
    } catch (err) {
      console.error('Failed to fetch audit logs:', err)
    } finally {
      setLoading(false)
    }
  }

  const fetchMetadata = async () => {
    try {
      const [typesRes, statsRes] = await Promise.all([
        policyApi.getEntityTypes().catch(() => ({ entity_types: [], count: 0 })),
        auditApi.stats('all').catch(() => ({ total_events: 0, by_action: {}, by_entity_type: {}, by_user: {} })),
      ])
      setEntityTypes(typesRes.entity_types)
      setStats(statsRes)
      setActions(Object.keys(statsRes.by_action || {}))
    } catch (err) {
      console.error('Failed to fetch metadata:', err)
    }
  }

  const handleResetFilters = () => {
    setActionFilter('')
    setEntityTypeFilter('')
    setUserFilter('')
    setDateFrom('')
    setDateTo('')
    setPage(1)
  }

  const handleExport = async () => {
    setExporting(true)
    try {
      const response = await auditApi.search({
        org_id: 'all',
        action: actionFilter || undefined,
        entity_type: entityTypeFilter || undefined,
        performed_by: userFilter || undefined,
        date_from: dateFrom ? new Date(dateFrom).toISOString() : undefined,
        date_to: dateTo ? new Date(dateTo).toISOString() : undefined,
        limit: 10000,
        offset: 0,
      })
      
      const headers = ['Timestamp', 'Patient/Tenant ID', 'Action', 'Entity Type', 'Tokenized Value', 'Performed By', 'IP Address', 'Metadata']
      const rows = response.items.map((log: any) => [
        log.created_at ? format(parseISO(log.created_at), 'yyyy-MM-dd HH:mm:ss') : '',
        log.org_id || 'default-org',
        log.action,
        log.entity_type || '',
        log.tokenized_value || '',
        log.performed_by,
        log.ip_address || '',
        JSON.stringify(log.metadata || {})
      ])
      
      const csv = [headers.join(','), ...rows.map((r: any) => r.map((c: any) => `"${String(c).replace(/"/g, '""')}"`).join(','))].join('\n')
      
      const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
      const link = document.createElement('a')
      link.href = URL.createObjectURL(blob)
      link.download = `audit-log-${format(new Date(), 'yyyy-MM-dd')}.csv`
      link.click()
      URL.revokeObjectURL(link.href)
    } catch (err) {
      console.error('Export failed:', err)
    } finally {
      setExporting(false)
    }
  }

  const getActionBadge = (action: string) => {
    switch (action) {
      case 'tokenize':
        return { label: 'Tokenized', class: 'tokenize', icon: Key }
      case 'restore':
        return { label: 'Restored', class: 'restore', icon: Shield }
      case 'restore_denied':
        return { label: 'Denied', class: 'restore_denied', icon: AlertCircle }
      case 'policy_change':
        return { label: 'Policy Changed', class: 'policy_change', icon: Shield }
      default:
        return { label: action.replace('_', ' ').toUpperCase(), class: 'policy_change', icon: FileText }
    }
  }

  const getTotalPages = () => Math.ceil(total / pageSize) || 1

  return (
    <div className="audit-log-page">
      {/* Header */}
      <div className="audit-header">
        <div>
          <h1>HIPAA Audit & Compliance Trail</h1>
          <p className="audit-subtitle">Immutable compliance trail for all tokenization, detokenization, and policy governance events</p>
        </div>
        
        <button 
          type="button" 
          onClick={handleExport}
          disabled={exporting || logs.length === 0}
          className="btn-outline-sm"
          style={{ padding: '9px 16px', fontSize: '13.5px' }}
        >
          <Download size={15} />
          {exporting ? 'Exporting...' : 'Export Audit CSV'}
        </button>
      </div>

      {/* 4 Stats Metric Cards */}
      <div className="audit-stats-grid">
        <div className="audit-stat-card total-card">
          <span className="audit-stat-num">{stats?.total_events ?? total}</span>
          <span className="audit-stat-label">Total Events</span>
        </div>
        <div className="audit-stat-card token-card">
          <span className="audit-stat-num" style={{ color: '#10b981' }}>
            {stats?.by_action?.['tokenize'] ?? 0}
          </span>
          <span className="audit-stat-label">Ingress Tokenizations</span>
        </div>
        <div className="audit-stat-card restore-card">
          <span className="audit-stat-num" style={{ color: '#4f46e5' }}>
            {stats?.by_action?.['restore'] ?? 0}
          </span>
          <span className="audit-stat-label">Authorized Restores</span>
        </div>
        <div className="audit-stat-card policy-card">
          <span className="audit-stat-num" style={{ color: '#d97706' }}>
            {stats?.by_action?.['policy_change'] ?? 0}
          </span>
          <span className="audit-stat-label">Policy Modifications</span>
        </div>
      </div>

      {/* Filters Card */}
      <div className="audit-filter-card">
        <form onSubmit={e => { e.preventDefault(); setPage(1); fetchLogs(); }}>
          <div className="filter-grid-row">
            <div className="filter-field">
              <label>Action Category</label>
              <select 
                value={actionFilter} 
                onChange={e => { setActionFilter(e.target.value); setPage(1); }}
                className="filter-input"
              >
                <option value="">All Actions</option>
                {actions.map(act => (
                  <option key={act} value={act}>{act.replace('_', ' ').toUpperCase()}</option>
                ))}
              </select>
            </div>

            <div className="filter-field">
              <label>Entity Type</label>
              <select 
                value={entityTypeFilter} 
                onChange={e => { setEntityTypeFilter(e.target.value); setPage(1); }}
                className="filter-input"
              >
                <option value="">All Entity Types</option>
                {entityTypes.map(t => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </div>

            <div className="filter-field">
              <label>Requester / User</label>
              <input 
                type="text"
                value={userFilter}
                onChange={e => { setUserFilter(e.target.value); setPage(1); }}
                placeholder="e.g. admin-user, service-worker"
                className="filter-input"
              />
            </div>

            <div className="filter-field">
              <label>Date From</label>
              <input 
                type="date"
                value={dateFrom}
                onChange={e => { setDateFrom(e.target.value); setPage(1); }}
                className="filter-input"
              />
            </div>

            <div className="filter-field">
              <label>Date To</label>
              <input 
                type="date"
                value={dateTo}
                onChange={e => { setDateTo(e.target.value); setPage(1); }}
                className="filter-input"
              />
            </div>

            <div className="filter-btn-group">
              <button type="submit" className="btn-primary-lg" style={{ padding: '9px 18px', fontSize: '13.5px' }}>
                <Search size={14} /> Filter
              </button>
              <button type="button" onClick={handleResetFilters} className="btn-outline-sm" style={{ padding: '9px 14px' }}>
                Reset
              </button>
            </div>
          </div>
        </form>
      </div>

      {/* Table Card */}
      <div className="audit-table-card">
        <div className="audit-table-header">
          <span className="audit-table-title">Forensic Audit Log Entries</span>
          <span className="audit-table-count">
            Showing {total > 0 ? (page - 1) * pageSize + 1 : 0} - {Math.min(page * pageSize, total)} of {total} events
          </span>
        </div>

        <div className="audit-table-container">
          <table className="audit-table">
            <thead>
              <tr>
                <th>Timestamp</th>
                <th>Patient / Tenant ID</th>
                <th>Action</th>
                <th>Entity Type</th>
                <th>Tokenized Value</th>
                <th>Performed By</th>
                <th>IP Address</th>
                <th style={{ textAlign: 'right' }}>Metadata</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={8} style={{ textAlign: 'center', padding: '40px', color: '#64748b' }}>
                    <RefreshCw size={24} className="animate-spin" style={{ margin: '0 auto 8px', color: '#4f46e5' }} />
                    <p>Loading audit events from PostgreSQL...</p>
                  </td>
                </tr>
              ) : logs.length === 0 ? (
                <tr>
                  <td colSpan={8} style={{ textAlign: 'center', padding: '40px', color: '#64748b' }}>
                    <FileText size={40} style={{ margin: '0 auto 8px', color: '#cbd5e1' }} />
                    <h3>No audit events found</h3>
                    <p>Try resetting filters or adjusting search parameters.</p>
                  </td>
                </tr>
              ) : (
                logs.map(log => {
                  const badge = getActionBadge(log.action)
                  const Icon = badge.icon
                  return (
                    <tr key={log.id}>
                      <td style={{ whiteSpace: 'nowrap', color: '#64748b' }}>
                        {format(parseISO(log.created_at), 'yyyy-MM-dd HH:mm:ss')}
                      </td>
                      <td>
                        <span className="tenant-id-badge">{log.org_id || 'default-org'}</span>
                      </td>
                      <td>
                        <span className={`action-badge ${badge.class}`}>
                          <Icon size={12} />
                          {badge.label}
                        </span>
                      </td>
                      <td>
                        {log.entity_type ? (
                          <span style={{ fontWeight: 600, color: '#334155' }}>{log.entity_type}</span>
                        ) : (
                          <span style={{ color: '#94a3b8' }}>—</span>
                        )}
                      </td>
                      <td>
                        {log.tokenized_value ? (
                          <span className="token-code">{log.tokenized_value}</span>
                        ) : (
                          <span style={{ color: '#94a3b8' }}>—</span>
                        )}
                      </td>
                      <td>
                        <span style={{ fontWeight: 500 }}>{log.performed_by}</span>
                      </td>
                      <td style={{ fontFamily: 'monospace', color: '#64748b' }}>
                        {log.ip_address || '—'}
                      </td>
                      <td style={{ textAlign: 'right' }}>
                        <button 
                          type="button" 
                          onClick={() => setSelectedLog(log)}
                          className="metadata-view-btn"
                        >
                          <Code size={13} /> View JSON ({log.metadata ? Object.keys(log.metadata).length : 0})
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
        <div className="audit-pagination-bar">
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

      {/* JSON Metadata Inspection Modal */}
      {selectedLog && (
        <div className="audit-modal-overlay" onClick={() => setSelectedLog(null)}>
          <div className="audit-modal-card" onClick={e => e.stopPropagation()}>
            <div className="audit-modal-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <Code size={18} color="#4f46e5" />
                <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 700 }}>
                  Audit Event Metadata ({selectedLog.action})
                </h3>
              </div>
              <button 
                type="button" 
                onClick={() => setSelectedLog(null)} 
                className="btn-outline-sm" 
                style={{ padding: '6px 8px' }}
              >
                <X size={16} />
              </button>
            </div>
            <div className="audit-modal-body">
              <div style={{ marginBottom: '14px', fontSize: '13px', color: '#475569', display: 'flex', gap: '16px', flexWrap: 'wrap' }}>
                <div><strong>Event ID:</strong> <code>{selectedLog.id}</code></div>
                <div><strong>Tenant:</strong> <code>{selectedLog.org_id || 'default-org'}</code></div>
                <div><strong>User:</strong> <code>{selectedLog.performed_by}</code></div>
              </div>
              <pre className="audit-json-pre">
                {JSON.stringify(selectedLog.metadata || {}, null, 2)}
              </pre>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
