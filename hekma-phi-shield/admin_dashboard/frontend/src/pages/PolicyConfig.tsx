import { useState, useEffect, useMemo } from 'react'
import { 
  Shield, 
  Search, 
  Check, 
  AlertCircle, 
  RotateCcw, 
  Save, 
  Sparkles,
  Lock,
  Layers,
  HeartPulse,
  MapPin,
  CreditCard,
  Eye,
  RefreshCw,
} from 'lucide-react'
import { policyApi } from '../lib/api'
import { useOrg } from '../context/OrgContext'
import './PolicyConfig.css'

const POLICY_OPTIONS = [
  { 
    value: 'anonymize', 
    label: 'Anonymize / Normalize', 
    description: 'Format-preserving deterministic surrogate vaulted in PostgreSQL.',
    badgeClass: 'anonymize',
  },
  { 
    value: 'redact', 
    label: 'Redact', 
    description: 'Mask permanently with character placeholders ([REDACTED] or XXXX).',
    badgeClass: 'redact',
  },
  { 
    value: 'ignore', 
    label: 'Ignore', 
    description: 'Pass through unchanged without anonymization.',
    badgeClass: 'ignore',
  },
]

const PRESET_LIST = [
  { id: 'HIPAA', label: 'HIPAA Safe Harbor', icon: Shield, desc: 'Healthcare PHI protection (names, dates, IDs)' },
  { id: 'GDPR', label: 'GDPR', icon: Lock, desc: 'EU personal data protection (PII, emails, IPs)' },
  { id: 'PCI', label: 'PCI DSS', icon: CreditCard, desc: 'Payment card data (credit cards, CVV)' },
  { id: 'MINIMAL', label: 'Minimal', icon: Sparkles, desc: 'Only highest-risk identifiers' },
]

const CATEGORY_MAP: Record<string, string[]> = {
  'phi': [
    'PERSON', 'PATIENT_NAME', 'PATIENT_ID', 'DATE_OF_BIRTH', 'GENDER', 'RACE', 
    'AGE_OVER_89', 'PHOTO_IDENTIFIER', 'BIOMETRIC_IDENTIFIER', 'PROVIDER_NAME', 'TITLE'
  ],
  'clinical': [
    'DIAGNOSIS', 'CONDITION', 'MEDICATION', 'PROCEDURE', 'TREATMENT', 'LAB_RESULT', 
    'FACILITY_NAME', 'ADMISSION_DATE', 'DISCHARGE_DATE', 'MEDICAL_LICENSE'
  ],
  'contact': [
    'PHONE_NUMBER', 'PHONE', 'EMAIL_ADDRESS', 'EMAIL', 'LOCATION', 'CITY', 'ZIP_CODE', 
    'ADDRESS', 'GEOGRAPHIC_LOCATION', 'GPS_LOCATION', 'FAX_NUMBER', 'HANDLE', 'HASHTAG'
  ],
  'financial': [
    'SSN', 'US_SSN', 'SOCIAL_SECURITY_NUMBER', 'CREDIT_CARD', 'CVV', 'PASSPORT', 
    'US_PASSPORT', 'IBAN_CODE', 'ACCOUNT_NUMBER', 'US_BANK_NUMBER', 'US_DRIVER_LICENSE', 
    'MEDICAL_RECORD_NUMBER', 'HEALTH_PLAN_NUMBER', 'HEALTH_PLAN_BENEFICIARY_NUMBER', 
    'CERTIFICATE_LICENSE_NUMBER', 'OTHER_UNIQUE_IDENTIFIER', 'DEVICE_IDENTIFIER', 
    'DEVICE_ID', 'IP_ADDRESS', 'URL', 'LICENSE_PLATE', 'VEHICLE_IDENTIFIER', 'CRYPTO', 'CURRENCY'
  ],
}

export function PolicyConfig() {
  const { selectedOrgId: orgId } = useOrg()
  const [policies, setPolicies] = useState<Record<string, any>>({})
  const [entityTypes, setEntityTypes] = useState<string[]>([])
  const [presets, setPresets] = useState<any>({})
  const [selectedPreset, setSelectedPreset] = useState<string>('HIPAA')
  const [searchQuery, setSearchQuery] = useState<string>('')
  const [selectedCategory, setSelectedCategory] = useState<string>('all')
  
  const [saving, setSaving] = useState(false)
  const [successMsg, setSuccessMsg] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadData()
  }, [orgId])

  const loadData = async () => {
    setLoading(true)
    try {
      setError(null)
      const [typesRes, presetsRes, policiesRes] = await Promise.all([
        policyApi.getEntityTypes(),
        policyApi.getPresets(),
        policyApi.list('default-org').catch(() => []),
      ])
      
      setEntityTypes(typesRes.entity_types)
      setPresets(presetsRes)
      
      const hipaaPreset = presetsRes['HIPAA'] || {}
      const policyMap: Record<string, any> = {}
      
      if (Array.isArray(policiesRes) && policiesRes.length > 0) {
        policiesRes.forEach((p: any) => {
          policyMap[p.entity_type] = p
        })
      }
      
      typesRes.entity_types.forEach((et: string) => {
        if (!policyMap[et]) {
          policyMap[et] = {
            entity_type: et,
            policy_type: hipaaPreset[et] || 'anonymize',
            anonymize_strategy: 'randomized',
            applies_to_internal: true,
            applies_to_external: true,
          }
        }
      })
      
      setPolicies(policyMap)
      setSelectedPreset('HIPAA')
    } catch (err: any) {
      console.error('Failed to load policies:', err)
      setError(err.message || 'Failed to load policy rules from database.')
    } finally {
      setLoading(false)
    }
  }

  const handlePolicyChange = (entityType: string, policyType: string) => {
    setPolicies(prev => ({
      ...prev,
      [entityType]: { 
        ...prev[entityType], 
        policy_type: policyType,
      }
    }))
  }

  const handlePresetApply = (presetId: string) => {
    const preset = presets[presetId]
    if (!preset) return
    
    setPolicies(prev => {
      const updated = { ...prev }
      entityTypes.forEach(et => {
        updated[et] = {
          ...updated[et],
          entity_type: et,
          policy_type: preset[et] || (presetId === 'HIPAA' ? 'anonymize' : 'ignore'),
        }
      })
      return updated
    })
    setSelectedPreset(presetId)
    setSuccessMsg(`Preset ${presetId} applied. Click "Save Policy Configuration" to persist to PostgreSQL.`)
    setTimeout(() => setSuccessMsg(null), 3500)
  }

  const handleSave = async () => {
    setSaving(true)
    setError(null)
    setSuccessMsg(null)
    try {
      const policyList = Object.values(policies)
      await policyApi.bulkUpdate('default-org', policyList)
      setSuccessMsg('✅ Policy configuration successfully saved and synchronized across all ingress workers!')
      setTimeout(() => setSuccessMsg(null), 4000)
    } catch (err: any) {
      setError(err.message || 'Failed to save policies.')
    } finally {
      setSaving(false)
    }
  }

  // Filter entities
  const filteredEntities = useMemo(() => {
    return entityTypes.filter(et => {
      const matchesSearch = !searchQuery || et.toLowerCase().includes(searchQuery.toLowerCase())
      let matchesCat = true
      if (selectedCategory !== 'all') {
        const catList = CATEGORY_MAP[selectedCategory] || []
        matchesCat = catList.includes(et)
      }
      return matchesSearch && matchesCat
    })
  }, [entityTypes, searchQuery, selectedCategory])

  // Compute Summary Counters
  const summaryCounts = useMemo(() => {
    let anonymize = 0
    let redact = 0
    let ignore = 0
    Object.values(policies).forEach((p: any) => {
      if (p.policy_type === 'anonymize') anonymize++
      else if (p.policy_type === 'redact') redact++
      else if (p.policy_type === 'ignore') ignore++
    })
    return { anonymize, redact, ignore, total: entityTypes.length }
  }, [policies, entityTypes])

  const getPreviewText = (et: string, pType: string) => {
    if (pType === 'anonymize') {
      if (et.includes('NAME') || et === 'PERSON') return 'GIVEN_dfeb30a0'
      if (et.includes('PATIENT')) return 'PAT_eba23543dc'
      if (et.includes('CITY')) return 'CITY_de17497d'
      if (et.includes('ZIP')) return '021XX'
      return `${et.substring(0, 4)}_39f3bb20`
    }
    if (pType === 'redact') {
      return '[REDACTED]'
    }
    return 'Raw Plaintext'
  }

  if (loading) {
    return (
      <div className="policy-config-page" style={{ textAlign: 'center', padding: '60px 0' }}>
        <RefreshCw size={28} className="animate-spin" style={{ color: '#4f46e5', margin: '0 auto 16px' }} />
        <p style={{ color: '#64748b', fontSize: '15px' }}>Loading policy governance rules from PostgreSQL...</p>
      </div>
    )
  }

  return (
    <div className="policy-config-page">
      {/* Header */}
      <div className="policy-page-header">
        <div>
          <h1>PII & PHI Policy Configuration</h1>
          <p className="policy-subtitle">Configure per-entity privacy rules and anonymization strategies (Diagram A Architecture)</p>
        </div>
        <button 
          type="button" 
          onClick={handleSave} 
          disabled={saving} 
          className="btn-primary"
          style={{ padding: '10px 20px', fontSize: '14.5px', gap: '8px' }}
        >
          {saving ? <RefreshCw size={16} className="animate-spin" /> : <Save size={16} />}
          {saving ? 'Saving to Database...' : 'Save Policy Configuration'}
        </button>
      </div>

      {/* Success Toast */}
      {successMsg && (
        <div className="toast-success">
          <Check size={18} />
          <span>{successMsg}</span>
        </div>
      )}

      {/* Error Toast */}
      {error && (
        <div className="alert alert-error">
          <AlertCircle size={18} />
          <span>{error}</span>
        </div>
      )}

      {/* Controls & Preset Card */}
      <div className="policy-controls-card">
        <div className="preset-bar-top">
          <div className="preset-pills-group">
            <span className="preset-label">Compliance Presets:</span>
            {PRESET_LIST.map(p => {
              const Icon = p.icon
              const isActive = selectedPreset === p.id
              return (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => handlePresetApply(p.id)}
                  className={`preset-pill-btn ${isActive ? 'active' : ''}`}
                  title={p.desc}
                >
                  <Icon size={14} />
                  <span>{p.label}</span>
                </button>
              )
            })}
          </div>

          <button 
            type="button" 
            onClick={() => handlePresetApply('HIPAA')} 
            className="btn-outline-sm"
          >
            <RotateCcw size={14} /> Reset to Default HIPAA
          </button>
        </div>

        {/* Filter & Search Row */}
        <div className="filter-search-row">
          <div className="search-input-wrapper">
            <Search size={16} className="search-input-icon" />
            <input 
              type="text"
              placeholder="Search entity rules (e.g. ssn, patient, date, email)..."
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
            />
          </div>

          <div className="category-tabs">
            <button 
              type="button" 
              onClick={() => setSelectedCategory('all')} 
              className={`category-tab-btn ${selectedCategory === 'all' ? 'active' : ''}`}
            >
              All ({entityTypes.length})
            </button>
            <button 
              type="button" 
              onClick={() => setSelectedCategory('phi')} 
              className={`category-tab-btn ${selectedCategory === 'phi' ? 'active' : ''}`}
            >
              🏥 Patient PHI
            </button>
            <button 
              type="button" 
              onClick={() => setSelectedCategory('clinical')} 
              className={`category-tab-btn ${selectedCategory === 'clinical' ? 'active' : ''}`}
            >
              🩺 Clinical Data
            </button>
            <button 
              type="button" 
              onClick={() => setSelectedCategory('contact')} 
              className={`category-tab-btn ${selectedCategory === 'contact' ? 'active' : ''}`}
            >
              📍 Contact & Location
            </button>
            <button 
              type="button" 
              onClick={() => setSelectedCategory('financial')} 
              className={`category-tab-btn ${selectedCategory === 'financial' ? 'active' : ''}`}
            >
              💳 IDs & Numbers
            </button>
          </div>
        </div>
      </div>

      {/* Summary Stats Chips */}
      <div className="policy-summary-bar">
        <div className="policy-stat-chip anonymize-chip">
          <span>🛡️ Anonymized (Surrogate Vault):</span>
          <strong>{summaryCounts.anonymize} entities</strong>
        </div>
        <div className="policy-stat-chip redact-chip">
          <span>🛑 Redacted ([REDACTED]):</span>
          <strong>{summaryCounts.redact} entities</strong>
        </div>
        <div className="policy-stat-chip ignore-chip">
          <span>⚪ Passed Through (Ignore):</span>
          <strong>{summaryCounts.ignore} entities</strong>
        </div>
      </div>

      {/* Entity Cards Grid */}
      <div className="policy-cards-grid">
        {filteredEntities.map(et => {
          const policy = policies[et] || { policy_type: 'anonymize' }
          const pType = policy.policy_type || 'anonymize'

          return (
            <div key={et} className={`policy-card card-${pType}`}>
              <div className="policy-card-header">
                <div className="policy-card-title">
                  <span className="entity-name-badge">{et}</span>
                </div>
                <span className={`policy-status-pill ${pType}`}>
                  {pType}
                </span>
              </div>

              <div className="policy-card-body">
                <div className="policy-options-group">
                  {POLICY_OPTIONS.map(opt => {
                    const isSelected = pType === opt.value
                    return (
                      <label 
                        key={opt.value} 
                        className={`policy-option-item ${isSelected ? 'selected' : ''}`}
                      >
                        <input 
                          type="radio"
                          name={`policy-${et}`}
                          value={opt.value}
                          checked={isSelected}
                          onChange={() => handlePolicyChange(et, opt.value)}
                        />
                        <div className="option-text-group">
                          <span className="option-name">{opt.label}</span>
                          <span className="option-desc">{opt.description}</span>
                        </div>
                      </label>
                    )
                  })}
                </div>

                <div className="policy-preview-box">
                  <span>Transformation Preview:</span>
                  <code>{getPreviewText(et, pType)}</code>
                </div>
              </div>
            </div>
          )
        })}
      </div>

      {filteredEntities.length === 0 && (
        <div style={{ textAlign: 'center', padding: '40px', background: '#fff', borderRadius: '10px', border: '1px solid #e2e8f0' }}>
          <p style={{ color: '#64748b', fontSize: '15px' }}>No entity rules found matching "<strong>{searchQuery}</strong>".</p>
        </div>
      )}
    </div>
  )
}
