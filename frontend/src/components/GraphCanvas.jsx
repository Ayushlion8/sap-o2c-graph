import { useEffect, useRef, useState, useCallback } from 'react'
import { Network, DataSet } from 'vis-network/standalone'
import { RotateCcw, ZoomIn, ZoomOut, Maximize2, X } from 'lucide-react'

const API = import.meta.env.VITE_API_URL || ''

const TYPE_COLORS = {
  SalesOrder:       { bg: '#3B82F6', border: '#1D4ED8' },
  Delivery:         { bg: '#10B981', border: '#059669' },
  BillingDocument:  { bg: '#F59E0B', border: '#D97706' },
  JournalEntry:     { bg: '#8B5CF6', border: '#7C3AED' },
  Payment:          { bg: '#EF4444', border: '#DC2626' },
  Customer:         { bg: '#F97316', border: '#EA580C' },
  Product:          { bg: '#06B6D4', border: '#0891B2' },
  Plant:            { bg: '#6B7280', border: '#4B5563' },
}

const IMPORTANT_KEYS = {
  SalesOrder:       ['salesOrder','soldToParty','totalNetAmount','creationDate','overallDeliveryStatus','overallOrdReltdBillgStatus'],
  Delivery:         ['deliveryDocument','creationDate','overallGoodsMovementStatus','overallPickingStatus','shippingPoint'],
  BillingDocument:  ['billingDocument','billingDocumentType','totalNetAmount','creationDate','soldToParty','accountingDocument'],
  JournalEntry:     ['accountingDocument','glAccount','amountInTransactionCurrency','postingDate','referenceDocument'],
  Payment:          ['accountingDocument','customer','amountInTransactionCurrency','clearingDate'],
  Customer:         ['businessPartner','businessPartnerName','businessPartnerGrouping'],
  Product:          ['product','productOldId','productType','productGroup'],
}

function formatKey(k) {
  return k.replace(/([A-Z])/g, ' $1').replace(/^./, s => s.toUpperCase()).substring(0, 20)
}

function formatVal(v) {
  if (!v || v === 'None' || v === 'null') return '—'
  if (typeof v === 'string' && v.includes('T00:00:00.000Z')) return v.replace('T00:00:00.000Z', '')
  if (typeof v === 'string' && v.length > 22) return v.substring(0, 22) + '…'
  if (v === 'True') return '✓'
  if (v === 'False') return '✗'
  return v
}

export default function GraphCanvas({ onHighlightNodes }) {
  const canvasRef   = useRef(null)
  const networkRef  = useRef(null)
  const nodesDS     = useRef(new DataSet([]))
  const edgesDS     = useRef(new DataSet([]))
  const expandedRef = useRef(new Set())

  const [loading, setLoading]     = useState(false)
  const [selected, setSelected]   = useState(null)
  const [search, setSearch]       = useState('')
  const [searchRes, setSearchRes] = useState([])

  const merge = useCallback((nodes, edges) => {
    const existN = new Set(nodesDS.current.getIds())
    nodesDS.current.add(nodes.filter(n => !existN.has(n.id)))
    nodesDS.current.update(nodes.filter(n => existN.has(n.id)))
    const existE = new Set(edgesDS.current.getIds())
    edgesDS.current.add(edges.filter(e => !existE.has(e.id)))
  }, [])

  // Keep stable refs to these so ResizeObserver callback can call them
  const loadOverviewRef  = useRef(null)
  const expandTypeRef    = useRef(null)
  const expandEntityRef  = useRef(null)

  useEffect(() => {
    let initialized = false

    const init = () => {
      if (!canvasRef.current || initialized) return
      const { offsetWidth, offsetHeight } = canvasRef.current
      if (offsetWidth === 0 || offsetHeight === 0) return

      initialized = true
      observer.disconnect()

      const options = {
        physics: {
          enabled: true,
          solver: 'forceAtlas2Based',
          forceAtlas2Based: {
            gravitationalConstant: -60,
            centralGravity: 0.008,
            springLength: 130,
            springConstant: 0.04,
            damping: 0.5,
          },
          stabilization: { iterations: 150, updateInterval: 30 },
        },
        interaction: { hover: true, tooltipDelay: 300, zoomView: true, dragView: true },
        edges: { smooth: { type: 'dynamic' }, width: 1.5, selectionWidth: 3 },
        nodes: {
          borderWidth: 2,
          size: 30,
          font: { size: 11, color: '#F1F5F9', face: 'system-ui,sans-serif' },
          shadow: { enabled: true, size: 6, x: 2, y: 2, color: 'rgba(0,0,0,0.5)' },
        },
      }

      networkRef.current = new Network(
        canvasRef.current,
        { nodes: nodesDS.current, edges: edgesDS.current },
        options
      )

      networkRef.current.on('click', params => {
        if (!params.nodes.length) { setSelected(null); return }
        const node = nodesDS.current.get(params.nodes[0])
        if (node) setSelected(node)
      })

      networkRef.current.on('doubleClick', params => {
        if (!params.nodes.length) return
        const node = nodesDS.current.get(params.nodes[0])
        if (!node) return
        const data = node.data || {}
        if (data.isTypeNode) {
          expandTypeRef.current?.(node.nodeType)
        } else {
          const eid = data.salesOrder || data.deliveryDocument || data.billingDocument ||
            data.businessPartner || data.product || data.accountingDocument
          if (eid && !expandedRef.current.has(node.id)) {
            expandedRef.current.add(node.id)
            expandEntityRef.current?.(node.nodeType, eid)
          }
        }
      })

      loadOverviewRef.current?.()
    }

    const observer = new ResizeObserver(init)
    if (canvasRef.current) observer.observe(canvasRef.current)
    const t = setTimeout(init, 300)

    return () => {
      clearTimeout(t)
      observer.disconnect()
      networkRef.current?.destroy()
    }
  }, [])

  useEffect(() => {
    if (onHighlightNodes) {
      onHighlightNodes.current = ids =>
        networkRef.current?.selectNodes(ids.filter(id => nodesDS.current.get(id)))
    }
  }, [onHighlightNodes])

  const loadOverview = useCallback(async () => {
    setLoading(true)
    try {
      const r = await fetch(`${API}/api/graph/overview`)
      const d = await r.json()
      nodesDS.current.clear()
      edgesDS.current.clear()
      expandedRef.current.clear()
      merge(d.nodes, d.edges)
      setTimeout(() => networkRef.current?.fit({ animation: { duration: 700, easingFunction: 'easeInOutQuad' } }), 400)
    } catch (e) { console.error(e) }
    finally { setLoading(false) }
  }, [merge])

  const expandType = useCallback(async (entityType) => {
    if (expandedRef.current.has(`type_${entityType}`)) return
    expandedRef.current.add(`type_${entityType}`)
    setLoading(true)
    try {
      const r = await fetch(`${API}/api/graph/expand?type=${entityType}`)
      const d = await r.json()
      merge(d.nodes, d.edges)
      setTimeout(() => networkRef.current?.stabilize(80), 150)
    } catch (e) { console.error(e) }
    finally { setLoading(false) }
  }, [merge])

  const expandEntity = useCallback(async (nodeType, nodeId) => {
    setLoading(true)
    try {
      const r = await fetch(`${API}/api/graph/expand?type=${nodeType}&id=${nodeId}`)
      const d = await r.json()
      merge(d.nodes, d.edges)
      setTimeout(() => networkRef.current?.stabilize(80), 150)
    } catch (e) { console.error(e) }
    finally { setLoading(false) }
  }, [merge])

  // Keep refs in sync so the ResizeObserver/doubleClick callbacks always call latest version
  useEffect(() => { loadOverviewRef.current  = loadOverview  }, [loadOverview])
  useEffect(() => { expandTypeRef.current    = expandType    }, [expandType])
  useEffect(() => { expandEntityRef.current  = expandEntity  }, [expandEntity])

  const handleSearch = async (q) => {
    setSearch(q)
    if (!q.trim()) { setSearchRes([]); return }
    try {
      const r = await fetch(`${API}/api/graph/search?q=${encodeURIComponent(q)}`)
      const d = await r.json()
      setSearchRes(d.results || [])
    } catch (e) { console.error(e) }
  }

  const focusNode = (type, id) => {
    if (!expandedRef.current.has(`type_${type}`)) {
      expandType(type).then(() => {
        setTimeout(() => {
          const found = nodesDS.current.getIds().find(x => x.includes(id))
          if (found) networkRef.current?.focus(found, { animation: true, scale: 1.5 })
        }, 1200)
      })
    } else {
      const found = nodesDS.current.getIds().find(x => x.includes(id))
      if (found) networkRef.current?.focus(found, { animation: true, scale: 1.5 })
    }
    setSearch(''); setSearchRes([])
  }

  const typeColor = selected ? TYPE_COLORS[selected.nodeType] : null
  const fields    = selected ? (IMPORTANT_KEYS[selected.nodeType] || []) : []
  const nodeData  = selected?.data || {}

  return (
    <div style={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0, position: 'relative' }}>

      {/* Toolbar */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 6, padding: '7px 10px',
        background: 'var(--bg-secondary)', borderBottom: '1px solid var(--border)', flexShrink: 0,
      }}>
        <button className="toolbar-btn" onClick={loadOverview}><RotateCcw size={13} /> Reset</button>
        <button className="toolbar-btn" onClick={() => networkRef.current?.zoomIn(0.3)}><ZoomIn size={13} /></button>
        <button className="toolbar-btn" onClick={() => networkRef.current?.zoomOut(0.3)}><ZoomOut size={13} /></button>
        <button className="toolbar-btn" onClick={() => networkRef.current?.fit({ animation: true })}><Maximize2 size={13} /> Fit</button>

        <div style={{ position: 'relative', flex: 1, maxWidth: 300 }}>
          <input
            className="search-input"
            placeholder="🔍 Search by ID or name…"
            value={search}
            onChange={e => handleSearch(e.target.value)}
            style={{ width: '100%' }}
          />
          {search && (
            <button
              onClick={() => { setSearch(''); setSearchRes([]) }}
              style={{ position: 'absolute', right: 6, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)' }}
            >
              <X size={12} />
            </button>
          )}
          {searchRes.length > 0 && (
            <div style={{
              position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 200,
              background: 'var(--bg-secondary)', border: '1px solid var(--border)',
              borderRadius: 'var(--radius)', marginTop: 3, maxHeight: 180, overflowY: 'auto',
            }}>
              {searchRes.map((r, i) => (
                <div key={i} onClick={() => focusNode(r.type, r.id)}
                  style={{ padding: '6px 10px', cursor: 'pointer', fontSize: 12, borderBottom: '1px solid var(--border)', display: 'flex', gap: 8 }}
                  onMouseEnter={e => e.currentTarget.style.background = 'var(--bg-tertiary)'}
                  onMouseLeave={e => e.currentTarget.style.background = ''}
                >
                  <span style={{ color: TYPE_COLORS[r.type]?.bg || '#64748B', fontWeight: 600 }}>{r.type}</span>
                  <span style={{ color: 'var(--text-primary)' }}>{r.id}</span>
                  <span style={{ color: 'var(--text-muted)', flex: 1, textAlign: 'right' }}>{r.detail}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Canvas area — fills all remaining height */}
      <div style={{ flex: 1, minHeight: 0, position: 'relative', background: 'var(--bg-primary)' }}>

        {/* vis-network mount point — must be absolute fill */}
        <div ref={canvasRef} style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0 }} />

        {/* Legend */}
        <div style={{
          position: 'absolute', top: 10, left: 10, zIndex: 5, pointerEvents: 'none',
          background: 'rgba(30,41,59,0.92)', backdropFilter: 'blur(8px)',
          border: '1px solid var(--border)', borderRadius: 'var(--radius)', padding: '8px 12px', fontSize: 11,
        }}>
          <div style={{ color: 'var(--text-muted)', fontWeight: 600, marginBottom: 5, textTransform: 'uppercase', letterSpacing: '0.5px', fontSize: 10 }}>
            Entity Types
          </div>
          {Object.entries(TYPE_COLORS).slice(0, 6).map(([t, c]) => (
            <div key={t} style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 3, color: 'var(--text-secondary)' }}>
              <div style={{ width: 10, height: 10, borderRadius: 2, background: c.bg, flexShrink: 0 }} />
              {t}
            </div>
          ))}
        </div>

        {/* Hint */}
        <div style={{
          position: 'absolute', bottom: 10, left: '50%', transform: 'translateX(-50%)',
          background: 'rgba(30,41,59,0.82)', border: '1px solid var(--border)',
          borderRadius: 20, padding: '5px 14px', fontSize: 11, color: 'var(--text-muted)',
          pointerEvents: 'none', whiteSpace: 'nowrap', zIndex: 5,
        }}>
          Double-click a node to expand • Single-click to inspect
        </div>

        {/* Loading overlay */}
        {loading && (
          <div style={{
            position: 'absolute', inset: 0, zIndex: 10, backdropFilter: 'blur(2px)',
            background: 'rgba(15,23,42,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10 }}>
              <div className="spinner" />
              <span style={{ color: 'var(--text-secondary)', fontSize: 13 }}>Loading graph…</span>
            </div>
          </div>
        )}

        {/* Node detail panel */}
        {selected && (
          <div style={{
            position: 'absolute', top: 10, right: 10, width: 230, zIndex: 5,
            background: 'rgba(30,41,59,0.96)', backdropFilter: 'blur(8px)',
            border: '1px solid var(--border)', borderRadius: 'var(--radius)',
            padding: 12, fontSize: 12, maxHeight: 'calc(100% - 20px)', overflowY: 'auto',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
              <span style={{ fontWeight: 700, fontSize: 13 }}>{selected.nodeType}</span>
              <button onClick={() => setSelected(null)}
                style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}>
                <X size={13} />
              </button>
            </div>
            <div style={{
              display: 'inline-block', padding: '2px 8px', borderRadius: 12, marginBottom: 8,
              fontSize: 10, fontWeight: 600, textTransform: 'uppercase',
              background: typeColor?.bg + '22', color: typeColor?.bg,
            }}>{selected.nodeType}</div>

            {fields.map(k => {
              const v = nodeData[k]
              if (!v || v === 'null' || v === 'None') return null
              return (
                <div key={k} style={{ display: 'flex', justifyContent: 'space-between', padding: '3px 0', borderBottom: '1px solid rgba(51,65,85,0.5)', gap: 8 }}>
                  <span style={{ color: 'var(--text-muted)', flexShrink: 0, maxWidth: 100, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{formatKey(k)}</span>
                  <span style={{ color: 'var(--text-secondary)', textAlign: 'right', wordBreak: 'break-all' }}>{formatVal(String(v))}</span>
                </div>
              )
            })}

            {nodeData.isTypeNode
              ? <button className="detail-expand-btn" onClick={() => expandType(selected.nodeType)}>↗ Show Records</button>
              : <button className="detail-expand-btn" onClick={() => {
                  const eid = nodeData.salesOrder || nodeData.deliveryDocument || nodeData.billingDocument ||
                    nodeData.businessPartner || nodeData.product || nodeData.accountingDocument
                  if (eid) expandEntity(selected.nodeType, eid)
                }}>↗ Expand Connections</button>
            }
          </div>
        )}
      </div>
    </div>
  )
}