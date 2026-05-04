/**
 * PendingAllocationPage — ARS_PEND_ALC overview
 * Shows approved-but-not-yet-DO'd quantities from the ARS allocation system.
 * Deducted from MSA available stock to prevent double allocation.
 */
import { useState, useEffect, useCallback } from 'react'
import { pendAlcAPI } from '@/services/api'
import toast from 'react-hot-toast'
import { RefreshCw, Package, CheckCircle, Clock, TrendingDown } from 'lucide-react'

const C = {
  primary: '#4f46e5', blue: '#0891b2', green: '#16a34a',
  amber: '#d97706', red: '#dc2626', text: '#1e293b',
  textSub: '#64748b', textMuted: '#94a3b8', border: '#e2e8f0',
  bg: '#f8fafc', card: '#ffffff',
}

function Tile({ label, value, sub, accent }) {
  return (
    <div style={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 8,
                  padding: '12px 16px', borderLeft: `3px solid ${accent}` }}>
      <div style={{ fontSize: 9, fontWeight: 700, color: C.textSub,
                    letterSpacing: '.06em', marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 20, fontWeight: 800, color: C.text,
                    lineHeight: 1 }}>{value ?? '—'}</div>
      {sub && <div style={{ fontSize: 9, color: C.textMuted, marginTop: 3 }}>{sub}</div>}
    </div>
  )
}

function fmt(n) { return typeof n === 'number' ? n.toLocaleString(undefined, { maximumFractionDigits: 0 }) : '—' }

export default function PendingAllocationPage() {
  const [summary, setSummary]     = useState(null)
  const [loading, setLoading]     = useState(false)
  const [tab, setTab]             = useState('majcat') // 'majcat' | 'detail'
  const [detail, setDetail]       = useState(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [sessionFilter, setSessionFilter] = useState('')
  const [majCatFilter, setMajCatFilter]   = useState('')
  const [showClosed, setShowClosed]       = useState(false)

  const loadSummary = useCallback(async () => {
    setLoading(true)
    try {
      const { data } = await pendAlcAPI.summary()
      setSummary(data?.data || null)
    } catch {
      toast.error('Failed to load pending allocation summary')
    } finally {
      setLoading(false)
    }
  }, [])

  const loadDetail = useCallback(async () => {
    setDetailLoading(true)
    try {
      const params = {}
      if (sessionFilter) params.session_id = sessionFilter
      if (majCatFilter)  params.maj_cat = majCatFilter
      if (!showClosed)   params.closed = false
      const { data } = await pendAlcAPI.detail(params)
      setDetail(data?.data || [])
    } catch {
      toast.error('Failed to load detail')
    } finally {
      setDetailLoading(false)
    }
  }, [sessionFilter, majCatFilter, showClosed])

  useEffect(() => { loadSummary() }, [loadSummary])
  useEffect(() => { if (tab === 'detail') loadDetail() }, [tab, loadDetail])

  const t = summary?.totals

  const _btn = (active) => ({
    fontSize: 10, fontWeight: active ? 700 : 400, padding: '4px 12px',
    borderRadius: 4, border: `1px solid ${active ? C.primary : C.border}`,
    background: active ? C.primary : 'transparent',
    color: active ? '#fff' : C.textSub, cursor: 'pointer',
  })

  return (
    <div style={{ padding: '16px 20px', fontFamily: 'Inter,system-ui,sans-serif',
                  fontSize: 11, color: C.text, background: C.bg, minHeight: '100vh' }}>

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
        <Package size={16} color={C.primary}/>
        <div style={{ fontSize: 13, fontWeight: 800, color: C.text }}>
          Pending Allocation
        </div>
        <div style={{ fontSize: 10, color: C.textMuted, marginLeft: 4 }}>
          Approved quantities awaiting SAP Delivery Order
        </div>
        <div style={{ flex: 1 }}/>
        <button onClick={loadSummary} disabled={loading}
          style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 10,
                   padding: '4px 10px', borderRadius: 4, border: `1px solid ${C.border}`,
                   background: '#fff', cursor: 'pointer', color: C.textSub }}>
          <RefreshCw size={11} style={{ animation: loading ? 'spin 1s linear infinite' : 'none' }}/>
          Refresh
        </button>
      </div>

      {/* Tiles */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5,1fr)', gap: 8, marginBottom: 14 }}>
        <Tile label="TOTAL ALLOC QTY"   value={fmt(t?.total_alloc)}  accent={C.primary}/>
        <Tile label="DO QTY (ISSUED)"   value={fmt(t?.total_do)}     accent={C.green}/>
        <Tile label="PENDING QTY"       value={fmt(t?.total_pend)}   accent={C.amber}
              sub={t?.total_alloc ? `${(100*t.total_pend/t.total_alloc).toFixed(1)}% of alloc` : undefined}/>
        <Tile label="OPEN ROWS"         value={fmt(t?.open_rows)}    accent={C.blue}/>
        <Tile label="CLOSED %"          value={t?.pct_closed != null ? `${t.pct_closed}%` : '—'}
              accent={C.textMuted} sub={`${fmt(t?.closed_rows)} rows fully DO'd`}/>
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 6, marginBottom: 10 }}>
        <button style={_btn(tab === 'majcat')} onClick={() => setTab('majcat')}>
          By MAJ_CAT
        </button>
        <button style={_btn(tab === 'detail')} onClick={() => setTab('detail')}>
          Row Detail
        </button>
      </div>

      {/* MAJ_CAT breakdown */}
      {tab === 'majcat' && (
        <div style={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 8, overflow: 'hidden' }}>
          {loading ? (
            <div style={{ padding: 40, textAlign: 'center', color: C.textMuted }}>Loading…</div>
          ) : !summary?.by_majcat?.length ? (
            <div style={{ padding: 40, textAlign: 'center', color: C.textMuted }}>
              No open pending quantities.
            </div>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 10 }}>
              <thead>
                <tr style={{ background: C.bg }}>
                  {['MAJ_CAT','ALLOC QTY','DO QTY','PEND QTY','ROWS'].map(h => (
                    <th key={h} style={{ padding: '7px 12px', textAlign: h === 'MAJ_CAT' ? 'left' : 'right',
                                        fontSize: 9, fontWeight: 700, color: C.textSub,
                                        letterSpacing: '.05em', borderBottom: `1px solid ${C.border}` }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {summary.by_majcat.map((r, i) => (
                  <tr key={r.maj_cat || i}
                    style={{ borderBottom: `1px solid ${C.border}`, background: i % 2 === 0 ? '#fff' : C.bg }}>
                    <td style={{ padding: '6px 12px', fontWeight: 600 }}>{r.maj_cat || '—'}</td>
                    <td style={{ padding: '6px 12px', textAlign: 'right' }}>{fmt(r.alloc_qty)}</td>
                    <td style={{ padding: '6px 12px', textAlign: 'right', color: C.green }}>{fmt(r.do_qty)}</td>
                    <td style={{ padding: '6px 12px', textAlign: 'right', fontWeight: 700,
                                  color: r.pend_qty > 0 ? C.amber : C.green }}>{fmt(r.pend_qty)}</td>
                    <td style={{ padding: '6px 12px', textAlign: 'right', color: C.textMuted }}>{r.rows}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* Detail rows */}
      {tab === 'detail' && (
        <>
          <div style={{ display: 'flex', gap: 8, marginBottom: 8, alignItems: 'center' }}>
            <input value={sessionFilter} onChange={e => setSessionFilter(e.target.value)}
              placeholder="Filter by session ID…"
              style={{ fontSize: 10, padding: '4px 8px', border: `1px solid ${C.border}`,
                       borderRadius: 4, width: 200 }}/>
            <input value={majCatFilter} onChange={e => setMajCatFilter(e.target.value)}
              placeholder="Filter by MAJ_CAT…"
              style={{ fontSize: 10, padding: '4px 8px', border: `1px solid ${C.border}`,
                       borderRadius: 4, width: 160 }}/>
            <label style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 10, cursor: 'pointer' }}>
              <input type="checkbox" checked={showClosed} onChange={e => setShowClosed(e.target.checked)}
                style={{ accentColor: C.primary }}/>
              Include closed
            </label>
            <button onClick={loadDetail} disabled={detailLoading}
              style={{ ..._btn(false), display: 'flex', alignItems: 'center', gap: 4 }}>
              <RefreshCw size={10}/> Load
            </button>
          </div>
          <div style={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 8, overflow: 'auto' }}>
            {detailLoading ? (
              <div style={{ padding: 40, textAlign: 'center', color: C.textMuted }}>Loading…</div>
            ) : !detail?.length ? (
              <div style={{ padding: 40, textAlign: 'center', color: C.textMuted }}>
                No data — click Load to fetch rows.
              </div>
            ) : (
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 10 }}>
                <thead>
                  <tr style={{ background: C.bg }}>
                    {['SESSION','RDC','ARTICLE','MAJ_CAT','ALLOC','DO','PEND','APPROVED','LAST DO','STATUS'].map(h => (
                      <th key={h} style={{ padding: '7px 10px', textAlign: 'left', fontSize: 9,
                                          fontWeight: 700, color: C.textSub, letterSpacing: '.05em',
                                          borderBottom: `1px solid ${C.border}`, whiteSpace: 'nowrap' }}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {detail.map((r, i) => (
                    <tr key={r.id}
                      style={{ borderBottom: `1px solid ${C.border}`,
                               background: r.is_closed ? '#f0fdf4' : (i % 2 === 0 ? '#fff' : C.bg) }}>
                      <td style={{ padding: '5px 10px', fontFamily: 'monospace', fontSize: 9,
                                   color: C.textSub, maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {r.session_id}
                      </td>
                      <td style={{ padding: '5px 10px' }}>{r.rdc}</td>
                      <td style={{ padding: '5px 10px', fontFamily: 'monospace', fontSize: 9 }}>{r.article_number}</td>
                      <td style={{ padding: '5px 10px' }}>{r.maj_cat || '—'}</td>
                      <td style={{ padding: '5px 10px', textAlign: 'right' }}>{fmt(r.alloc_qty)}</td>
                      <td style={{ padding: '5px 10px', textAlign: 'right', color: C.green }}>{fmt(r.do_qty)}</td>
                      <td style={{ padding: '5px 10px', textAlign: 'right', fontWeight: 700,
                                   color: r.pend_qty > 0 ? C.amber : C.green }}>{fmt(r.pend_qty)}</td>
                      <td style={{ padding: '5px 10px', fontSize: 9, color: C.textMuted, whiteSpace: 'nowrap' }}>
                        {r.approved_at ? r.approved_at.slice(0, 16).replace('T', ' ') : '—'}
                      </td>
                      <td style={{ padding: '5px 10px', fontSize: 9, color: C.textMuted, whiteSpace: 'nowrap' }}>
                        {r.last_do_at ? r.last_do_at.slice(0, 16).replace('T', ' ') : '—'}
                      </td>
                      <td style={{ padding: '5px 10px' }}>
                        <span style={{ fontSize: 8, fontWeight: 700, padding: '2px 6px', borderRadius: 3,
                                       background: r.is_closed ? '#dcfce7' : '#fef3c7',
                                       color: r.is_closed ? C.green : C.amber }}>
                          {r.is_closed ? 'CLOSED' : 'OPEN'}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}

      <style>{`@keyframes spin { to { transform: rotate(360deg) } }`}</style>
    </div>
  )
}
