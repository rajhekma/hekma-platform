import React from 'react'
import { Routes, Route, Navigate, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { 
  Shield, 
  Database, 
  FileText, 
  Building2,
  ChevronLeft,
  Menu,
  User,
} from 'lucide-react'
import { PolicyConfig } from './pages/PolicyConfig'
import { TokenExplorer } from './pages/TokenExplorer'
import { AuditLog } from './pages/AuditLog'
import { OrgSettings } from './pages/OrgSettings'
import { api } from './lib/api'

import { useOrg } from './context/OrgContext'
import { HekmaLogo } from './components/HekmaLogo'

const NAV_ITEMS = [
  { path: '/policies', label: 'Policy Config', icon: Shield, description: 'Per-entity PII policies' },
  { path: '/tokens', label: 'Token Explorer', icon: Database, description: 'Browse & restore tokens' },
  { path: '/audit', label: 'Audit Log', icon: FileText, description: 'Compliance trail' },
  { path: '/settings', label: 'Organization', icon: Building2, description: 'Org settings & API keys' },
]

function Sidebar() {
  const location = useLocation()
  const navigate = useNavigate()
  const [collapsed, setCollapsed] = React.useState(false)
  
  return (
    <aside className={`sidebar ${collapsed ? 'collapsed' : ''}`}>
      <div className="sidebar-header" style={{ justifyContent: 'space-between', padding: collapsed ? '0 10px' : '0 16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', overflow: 'hidden' }}>
          <HekmaLogo collapsed={collapsed} height={collapsed ? 32 : 38} />
        </div>
        <button 
          className="btn-ghost" 
          onClick={() => setCollapsed(!collapsed)}
          style={{ padding: 6 }}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? <Menu size={18} /> : <ChevronLeft size={18} />}
        </button>
      </div>
      
      <nav className="sidebar-nav">
        {NAV_ITEMS.map(item => (
          <button
            key={item.path}
            className={`nav-item ${location.pathname === item.path ? 'active' : ''}`}
            onClick={() => navigate(item.path)}
          >
            <item.icon size={20} />
            {!collapsed && <span>{item.label}</span>}
          </button>
        ))}
      </nav>
      
      <div className="sidebar-footer">
        <div className="org-selector" style={{ padding: '8px 12px', fontSize: '12.5px', color: '#64748b', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Database size={15} color="#4f46e5" />
          {!collapsed && <span>PostgreSQL Live Vault</span>}
        </div>
      </div>
    </aside>
  )
}

function Header() {
  const location = useLocation()
  const currentPage = NAV_ITEMS.find(item => location.pathname.startsWith(item.path))
  
  return (
    <header className="header">
      <div className="header-left">
        <h1 className="page-title">{currentPage?.label || 'Dashboard'}</h1>
      </div>
      <div className="header-right">
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', background: 'rgba(237, 36, 143, 0.06)', border: '1px solid rgba(237, 36, 143, 0.2)', padding: '6px 14px', borderRadius: '9999px', fontSize: '13px', color: '#7958A5', fontWeight: 600 }}>
          <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#10b981', display: 'inline-block', boxShadow: '0 0 6px #10b981' }}></span>
          <Database size={14} color="#ED248F" />
          <span>PostgreSQL Live Vault</span>
        </div>
        <div className="user-menu">
          <User size={16} color="#7958A5" />
          <span>Admin User</span>
        </div>
      </div>
    </header>
  )
}

function Layout() {
  return (
    <div className="container">
      <Sidebar />
      <main className="main-content">
        <Header />
        <div className="page-content">
          <Outlet />
        </div>
      </main>
    </div>
  )
}

function App() {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<Navigate to="/policies" replace />} />
        <Route path="policies" element={<PolicyConfig />} />
        <Route path="tokens" element={<TokenExplorer />} />
        <Route path="audit" element={<AuditLog />} />
        <Route path="settings" element={<OrgSettings />} />
      </Route>
    </Routes>
  )
}

export default App
