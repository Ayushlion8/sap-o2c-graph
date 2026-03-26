import { useState, useEffect, useRef } from 'react'
import GraphCanvas from './components/GraphCanvas'
import ChatPanel from './components/ChatPanel'

const API = import.meta.env.VITE_API_URL || ''

export default function App() {
  const [stats, setStats] = useState(null)
  const [llmReady, setLlmReady] = useState(false)
  const highlightNodesRef = useRef(null)

  useEffect(() => {
    const fetchHealth = async () => {
      try {
        const res = await fetch(`${API}/api/health`)
        const data = await res.json()
        setLlmReady(data.llm_ready)
        setStats(data.entity_counts)
      } catch (e) {
        console.error('Health check failed:', e)
      }
    }

    fetchHealth()
    const interval = setInterval(fetchHealth, 30000)
    return () => clearInterval(interval)
  }, [])

  const statItems = stats ? [
    { label: 'Sales Orders', value: stats.so_headers || 0, color: '#3B82F6' },
    { label: 'Deliveries', value: stats.delivery_headers || 0, color: '#10B981' },
    { label: 'Billing Docs', value: stats.bd_headers || 0, color: '#F59E0B' },
    { label: 'Customers', value: stats.business_partners || 0, color: '#F97316' },
  ] : []

  return (
    <div className="app-layout">
      {/* Header */}
      <header className="header">
        <div className="header-left">
          <div className="header-logo">🔗</div>
          <div>
            <h1>SAP O2C Graph Explorer</h1>
            <div className="header-subtitle">Order-to-Cash — Graph-Based Data Intelligence</div>
          </div>
        </div>

        <div className="header-stats">
          {statItems.map(s => (
            <div key={s.label} className="stat-pill">
              <div className="dot" style={{ background: s.color }} />
              <span style={{ color: 'var(--text-primary)', fontWeight: 600 }}>{s.value}</span>
              <span>{s.label}</span>
            </div>
          ))}
          {llmReady && (
            <div className="stat-pill" style={{ borderColor: '#10B981' }}>
              <div className="dot" style={{ background: '#10B981' }} />
              <span style={{ color: '#10B981' }}>AI Ready</span>
            </div>
          )}
        </div>
      </header>

      {/* Main layout */}
      <div className="main-content">
        {/* Graph panel */}
        <div className="graph-panel">
          <GraphCanvas onHighlightNodes={highlightNodesRef} />
        </div>

        {/* Chat panel */}
        <ChatPanel llmReady={llmReady} />
      </div>
    </div>
  )
}
