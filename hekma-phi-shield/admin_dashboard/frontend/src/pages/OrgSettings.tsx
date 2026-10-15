import { useState, useEffect } from 'react'
import { 
  Building2, 
  Save, 
  Key, 
  Copy, 
  Check, 
  AlertCircle,
  RefreshCw,
  Eye,
  EyeOff,
  Shield,
  Mail,
  Clock,
  Trash2,
  Database,
  Lock,
  Activity,
} from 'lucide-react'
import { useOrg } from '../context/OrgContext'
import { orgApi, tokenApi, policyApi, OrgResponse } from '../lib/api'
import './OrgSettings.css'

export function OrgSettings() {
  const { selectedOrgId, refreshOrgs } = useOrg()
  const [org, setOrg] = useState<OrgResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [showKey, setShowKey] = useState(false)
  const [copied, setCopied] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [purging, setPurging] = useState(false)
  const [purgeResult, setPurgeResult] = useState<string | null>(null)

  // Live Metrics
  const [tokenStats, setTokenStats] = useState({ total: 0, restored: 0, expired: 0 })
  const [policyCount, setPolicyCount] = useState(0)

  // Form State
  const [name, setName] = useState('')
  const [contactEmail, setContactEmail] = useState('')
  const [auditRetentionDays, setAuditRetentionDays] = useState<number>(0)
  const [tokenTtlDays, setTokenTtlDays] = useState<number>(0)
  const [rawApiKey, setRawApiKey] = useState<string | null>(null)

  useEffect(() => {
    loadOrgData()
  }, [selectedOrgId])

  const loadOrgData = async () => {
    setLoading(true)
    setError(null)
    setSuccess(null)
    setPurgeResult(null)
    try {
      const [orgData, statsData, policiesData] = await Promise.all([
        orgApi.get(selectedOrgId),
        tokenApi.stats(selectedOrgId).catch(() => ({ total_mappings: 0, restored_count: 0, expired_count: 0 })),
        policyApi.list(selectedOrgId).catch(() => []),
      ])

      setOrg(orgData)
      setName(orgData.name || '')
      setContactEmail(orgData.contact_email || 'admin@hekma.ai')
      setAuditRetentionDays(orgData.audit_retention_days ?? 0)
      setTokenTtlDays(orgData.token_ttl_days ?? 0)
      setRawApiKey(null) // Reset temporary revealed rotated key

      setTokenStats({
        total: statsData.total_mappings || 0,
        restored: statsData.restored_count || 0,
        expired: statsData.expired_count || 0,
      })
      setPolicyCount(Array.isArray(policiesData) ? policiesData.length : 0)
    } catch (err: any) {
      console.error('Failed to load organization settings:', err)
      setError(err.message || 'Failed to load organization settings from PostgreSQL.')
    } finally {
      setLoading(false)
    }
  }

  const handleSave = async () => {
    setSaving(true)
    setError(null)
    setSuccess(null)
    try {
      const updated = await orgApi.update(selectedOrgId, {
        name,
        contact_email: contactEmail,
        audit_retention_days: auditRetentionDays,
        token_ttl_days: tokenTtlDays,
      })
      setOrg(updated)
      await refreshOrgs()
      setSuccess('Organization profile and governance settings saved to PostgreSQL!')
      setTimeout(() => setSuccess(null), 4000)
    } catch (err: any) {
      setError(err.message || 'Failed to save organization settings.')
    } finally {
      setSaving(false)
    }
  }

  const handleRotateKey = async () => {
    if (!window.confirm('Are you sure you want to rotate the API key for this organization? The old key will immediately be invalidated.')) {
      return
    }
    try {
      const res = await orgApi.rotateKey(selectedOrgId)
      setRawApiKey(res.api_key)
      setShowKey(true)
      setSuccess(`New API Key generated: ${res.api_key}. Please copy and save it securely!`)
    } catch (err: any) {
      setError(err.message || 'Failed to rotate API key.')
    }
  }

  const handleCopyKey = () => {
    const keyToCopy = rawApiKey || org?.api_key || ''
    navigator.clipboard.writeText(keyToCopy)
    setCopied(true)
    setTimeout(() => setCopied(false), 2500)
  }

  const handlePurgeExpired = async () => {
    setPurging(true)
    setPurgeResult(null)
    try {
      const res = await orgApi.purgeExpired(selectedOrgId)
      setPurgeResult(`Purged ${res.purged_count} expired tokens from database.`)
      // Refresh stats
      const stats = await tokenApi.stats(selectedOrgId)
      setTokenStats({
        total: stats.total_mappings || 0,
        restored: stats.restored_count || 0,
        expired: stats.expired_count || 0,
      })
    } catch (err: any) {
      setError(err.message || 'Failed to purge expired tokens.')
    } finally {
      setPurging(false)
    }
  }

  if (loading) {
    return (
      <div className="org-settings-container" style={{ textAlign: 'center', padding: '60px 0' }}>
        <RefreshCw size={28} className="animate-spin" style={{ color: '#4f46e5', margin: '0 auto 16px' }} />
        <p style={{ color: '#64748b', fontSize: '15px' }}>Loading organization settings from PostgreSQL...</p>
      </div>
    )
  }

  const displayedApiKey = rawApiKey || org?.api_key || 'org_sk_live_••••••••••••••••'

  return (
    <div className="org-settings-container">
      {/* Header */}
      <header className="org-settings-header">
        <div>
          <h1>Organization & Governance Settings</h1>
          <p className="org-settings-subtitle">Manage tenant metadata, API security credentials, and HIPAA data retention rules</p>
        </div>
        <div className="org-tenant-badge">
          <Building2 size={16} color="#4f46e5" />
          <span>Active Tenant:</span>
          <span className="id">{selectedOrgId}</span>
        </div>
      </header>

      {/* Success Notification */}
      {success && (
        <div className="toast-success">
          <Check size={18} />
          <span>{success}</span>
        </div>
      )}

      {/* Error Notification */}
      {error && (
        <div className="alert alert-error" style={{ marginBottom: 20 }}>
          <AlertCircle size={18} />
          <span>{error}</span>
        </div>
      )}

      {/* 2x2 Modern Card Grid */}
      <div className="org-settings-grid">
        
        {/* Card 1: Organization Profile */}
        <div className="settings-card">
          <div className="settings-card-header">
            <div className="card-title-group">
              <div className="card-icon">
                <Building2 size={18} />
              </div>
              <h3 className="card-title">Tenant Identity & Profile</h3>
            </div>
            <span style={{ fontSize: '12px', color: '#64748b', fontWeight: 500 }}>PostgreSQL Backed</span>
          </div>
          <div className="settings-card-body">
            <div className="form-field">
              <label>Organization Identifier (Primary Key)</label>
              <input 
                type="text" 
                value={selectedOrgId} 
                disabled 
                className="form-input" 
                style={{ background: '#f8fafc', color: '#64748b', fontFamily: 'monospace' }}
              />
              <span className="form-hint">Unique tenant / patient ID scoping all Token Vault tables.</span>
            </div>

            <div className="form-field">
              <label>Display Name</label>
              <input 
                type="text" 
                value={name} 
                onChange={e => setName(e.target.value)}
                placeholder="e.g. Hekma Health System"
                className="form-input" 
              />
            </div>

            <div className="form-field">
              <label>Security & Compliance Email</label>
              <input 
                type="email" 
                value={contactEmail} 
                onChange={e => setContactEmail(e.target.value)}
                placeholder="security@hospital.org"
                className="form-input" 
              />
            </div>

            <div style={{ display: 'flex', gap: '16px', borderTop: '1px solid #f1f5f9', paddingTop: '12px', fontSize: '12.5px', color: '#64748b' }}>
              <div><strong>Created:</strong> {org?.created_at ? new Date(org.created_at).toLocaleDateString() : 'N/A'}</div>
              <div><strong>Last Synced:</strong> {org?.updated_at ? new Date(org.updated_at).toLocaleTimeString() : 'N/A'}</div>
            </div>
          </div>
        </div>

        {/* Card 2: API Keys & Microservice Security */}
        <div className="settings-card">
          <div className="settings-card-header">
            <div className="card-title-group">
              <div className="card-icon key-icon">
                <Key size={18} />
              </div>
              <h3 className="card-title">API Access Credentials</h3>
            </div>
            <span style={{ fontSize: '12px', color: '#b45309', fontWeight: 500 }}>X-Admin-Key</span>
          </div>
          <div className="settings-card-body">
            <div className="form-field">
              <label>Secret API Key (Microservice Integration)</label>
              <div className="api-key-group">
                <input 
                  type={showKey ? 'text' : 'password'}
                  value={displayedApiKey}
                  readOnly
                  className="form-input api-key-input"
                />
                <button 
                  type="button" 
                  onClick={() => setShowKey(!showKey)} 
                  className="btn-outline-sm"
                  title={showKey ? 'Hide key' : 'Reveal key'}
                >
                  {showKey ? <EyeOff size={15} /> : <Eye size={15} />}
                </button>
                <button 
                  type="button" 
                  onClick={handleCopyKey} 
                  className="btn-outline-sm"
                  title="Copy API key"
                >
                  {copied ? <Check size={15} color="#16a34a" /> : <Copy size={15} />}
                </button>
              </div>
              <span className="form-hint">Used in <code>X-Admin-Key</code> header for high-throughput ingress anonymization.</span>
            </div>

            <div style={{ background: '#fffbeb', border: '1px solid #fef3c7', borderRadius: '8px', padding: '12px', fontSize: '13px', color: '#92400e' }}>
              🔒 <strong>SHA-256 Hashed:</strong> Plaintext keys are never stored directly in the database.
            </div>

            <div style={{ marginTop: 'auto', paddingTop: '10px' }}>
              <button 
                type="button" 
                onClick={handleRotateKey} 
                className="btn-outline-sm"
                style={{ width: '100%', justifyContent: 'center' }}
              >
                <RefreshCw size={14} /> Rotate API Key
              </button>
            </div>
          </div>
        </div>

        {/* Card 3: Data Retention & Lifecycle Governance */}
        <div className="settings-card">
          <div className="settings-card-header">
            <div className="card-title-group">
              <div className="card-icon shield-icon">
                <Shield size={18} />
              </div>
              <h3 className="card-title">Data Retention & Governance</h3>
            </div>
            <span style={{ fontSize: '12px', color: '#15803d', fontWeight: 500 }}>HIPAA Rule § 164.312</span>
          </div>
          <div className="settings-card-body">
            
            {/* Audit Retention */}
            <div className={`gov-option-card ${auditRetentionDays === 0 ? 'enabled' : ''}`}>
              <div className="gov-header">
                <span className="gov-title">Audit Log Retention</span>
                <span className={`gov-status-badge ${auditRetentionDays === 0 ? 'permanent' : 'custom'}`}>
                  {auditRetentionDays === 0 ? '🛡️ Permanent' : `${auditRetentionDays} Days`}
                </span>
              </div>
              <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13.5px', color: '#334155', cursor: 'pointer', marginBottom: '8px' }}>
                <input 
                  type="checkbox"
                  checked={auditRetentionDays === 0}
                  onChange={e => setAuditRetentionDays(e.target.checked ? 0 : 365)}
                  style={{ accentColor: '#4f46e5', width: 16, height: 16, cursor: 'pointer' }}
                />
                <strong>Never Expire Audit Logs (Recommended for HIPAA Compliance)</strong>
              </label>
              {auditRetentionDays > 0 && (
                <div style={{ marginTop: 8 }}>
                  <input 
                    type="number"
                    min="30"
                    max="2555"
                    value={auditRetentionDays}
                    onChange={e => setAuditRetentionDays(Math.max(30, parseInt(e.target.value) || 30))}
                    className="form-input"
                    style={{ width: 120, display: 'inline-block', marginRight: 8 }}
                  />
                  <span style={{ fontSize: '13px', color: '#64748b' }}>days retention window</span>
                </div>
              )}
            </div>

            {/* Token TTL */}
            <div className={`gov-option-card ${tokenTtlDays === 0 ? 'enabled' : ''}`}>
              <div className="gov-header">
                <span className="gov-title">Token TTL (Time-To-Live)</span>
                <span className={`gov-status-badge ${tokenTtlDays === 0 ? 'permanent' : 'custom'}`}>
                  {tokenTtlDays === 0 ? '🔐 Permanent' : `${tokenTtlDays} Days`}
                </span>
              </div>
              <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13.5px', color: '#334155', cursor: 'pointer', marginBottom: '8px' }}>
                <input 
                  type="checkbox"
                  checked={tokenTtlDays === 0}
                  onChange={e => setTokenTtlDays(e.target.checked ? 0 : 90)}
                  style={{ accentColor: '#4f46e5', width: 16, height: 16, cursor: 'pointer' }}
                />
                <strong>Never Expire Token Mappings (Permanent Clinical Care Tokens)</strong>
              </label>
              {tokenTtlDays > 0 && (
                <div style={{ marginTop: 8 }}>
                  <input 
                    type="number"
                    min="1"
                    max="365"
                    value={tokenTtlDays}
                    onChange={e => setTokenTtlDays(Math.max(1, parseInt(e.target.value) || 1))}
                    className="form-input"
                    style={{ width: 120, display: 'inline-block', marginRight: 8 }}
                  />
                  <span style={{ fontSize: '13px', color: '#64748b' }}>days before auto-expiry</span>
                </div>
              )}
            </div>

            {/* Purge Expired Action */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderTop: '1px solid #f1f5f9', paddingTop: '10px' }}>
              <div>
                <div style={{ fontSize: '13px', fontWeight: 600, color: '#334155' }}>Lapsed Tokens Purge</div>
                <div style={{ fontSize: '12px', color: '#64748b' }}>{purgeResult || 'Manually clean expired mappings.'}</div>
              </div>
              <button 
                type="button" 
                onClick={handlePurgeExpired} 
                disabled={purging}
                className="btn-danger-outline"
              >
                <Trash2 size={14} /> {purging ? 'Purging...' : 'Purge Expired'}
              </button>
            </div>
          </div>
        </div>

        {/* Card 4: Live Storage & Metrics */}
        <div className="settings-card">
          <div className="settings-card-header">
            <div className="card-title-group">
              <div className="card-icon metrics-icon">
                <Activity size={18} />
              </div>
              <h3 className="card-title">Live Token Vault Metrics</h3>
            </div>
            <span style={{ fontSize: '12px', color: '#6d28d9', fontWeight: 500 }}>Real-Time DB</span>
          </div>
          <div className="settings-card-body">
            <div className="metrics-stat-grid">
              <div className="stat-box">
                <div className="stat-box-num">{tokenStats.total}</div>
                <div className="stat-box-label">Token Mappings</div>
              </div>
              <div className="stat-box">
                <div className="stat-box-num" style={{ color: '#16a34a' }}>{tokenStats.restored}</div>
                <div className="stat-box-label">Restored</div>
              </div>
              <div className="stat-box">
                <div className="stat-box-num" style={{ color: '#4f46e5' }}>{policyCount}</div>
                <div className="stat-box-label">Active Policies</div>
              </div>
            </div>

            <div style={{ background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: '8px', padding: '14px', fontSize: '13px', color: '#475569' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
                <Database size={15} color="#4f46e5" />
                <strong>PostgreSQL Host:</strong> <code>87.106.50.234:5432/hekmaai</code>
              </div>
              <div>All surrogate tokens and audit logs for <strong>{selectedOrgId}</strong> are partitioned with tenant isolation.</div>
            </div>

            <div style={{ marginTop: 'auto', textAlign: 'center' }}>
              <button 
                type="button" 
                onClick={loadOrgData} 
                className="btn-outline-sm"
                style={{ width: '100%', justifyContent: 'center' }}
              >
                <RefreshCw size={14} /> Refresh Live Database Stats
              </button>
            </div>
          </div>
        </div>

      </div>

      {/* Bottom Save Action */}
      <div className="org-bottom-actions">
        <button 
          type="button" 
          onClick={handleSave} 
          disabled={saving} 
          className="btn-primary-lg"
        >
          {saving ? (
            <>
              <RefreshCw size={16} className="animate-spin" /> Saving Changes...
            </>
          ) : (
            <>
              <Save size={16} /> Save Organization Settings
            </>
          )}
        </button>
      </div>
    </div>
  )
}
