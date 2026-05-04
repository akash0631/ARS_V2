/**
 * PendingDeliveryOrderPage — Daily DO qty entry tool
 * Upload a CSV or enter rows manually to record DO quantities issued by SAP.
 * Deducts from ARS_PEND_ALC and closes hold tracking rows.
 */
import { useState, useEffect, useCallback, useRef } from 'react'
import { pendAlcAPI } from '@/services/api'
import toast from 'react-hot-toast'
import { Upload, Plus, Trash2, Send, RefreshCw, CheckCircle, Truck } from 'lucide-react'

const C = {
  primary: '#4f46e5', blue: '#0891b2', green: '#16a34a',
  amber: '#d97706', red: '#dc2626', text: '#1e293b',
  textSub: '#64748b', textMuted: '#94a3b8', border: '#e2e8f0',
  bg: '#f8fafc', card: '#ffffff',
}

const EMPTY_ROW = { rdc: '', article_number: '', do_qty: '' }

function parseCsv(text) {
  const lines = text.trim().split('\n')
  if (lines.length < 2) return []
  const hdr = lines[0].split(',').map(h => h.trim().toLowerCase())
  const rdcIdx  = hdr.findIndex(h => ['rdc','receiving store','werks'].includes(h))
  const artIdx  = hdr.findIndex(h => ['article_number','material no','material','matnr'].includes(h))
  const qtyIdx  = hdr.findIndex(h => ['do_qty','do qty','qty','quantity'].includes(h))
  if (rdcIdx < 0 || artIdx < 0 || qtyIdx < 0) return null
  return lines.slice(1).map(l => {
    const cols = l.split(',')
    return {
      rdc:            (cols[rdcIdx]  || '').trim(),
      article_number: (cols[artIdx]  || '').trim(),
      do_qty:         (cols[qtyIdx]  || '').trim(),
    }
  }).filter(r => r.rdc && r.article_number && parseFloat(r.do_qty) > 0)
}

export default function PendingDeliveryOrderPage() {
  const [rows, setRows]             = useState([{ ...EMPTY_ROW }])
  const [submitting, setSubmitting] = useState(false)
  const [result, setResult]         = useState(null)
  const [history, setHistory]       = useState([])
  const [histLoading, setHistLoading] = useState(false)
  const fileRef = useRef()

  const loadHistory = useCallback(async () => {
    setHistLoading(true)
    try {
      const { data } = await pendAlcAPI.doHistory(50)
      setHistory(data?.data || [])
    } catch { /* silent */ }
    finally { setHistLoading(false) }
  }, [])

  useEffect(() => { loadHistory() }, [loadHistory])

  const setRow = (i, field, val) => {
    setRows(prev => prev.map((r, idx) => idx === i ? { ...r, [field]: val } : r))
  }

  const addRow = () => setRows(prev => [...prev, { ...EMPTY_ROW }])

  const removeRow = (i) => setRows(prev => prev.filter((_, idx) => idx !== i))

  const handleFile = (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = ev => {
      const parsed = parseCsv(ev.target.result)
      if (!parsed) {
        toast.error('CSV must have columns: RDC (or "Receiving Store"), Article_Number (or "Material No"), DO_QTY')
        return
      }
      if (parsed.length === 0) {
        toast.error('No valid rows found in CSV')
        return
      }
      setRows(parsed)
      toast.success(`Loaded ${parsed.length} rows from CSV`)
    }
    reader.readAsText(file)
    e.target.value = ''
  }

  const handleSubmit = async () => {
    const valid = rows.filter(r => r.rdc && r.article_number && parseFloat(r.do_qty) > 0)
    if (!valid.length) {
      toast.error('No valid rows to submit (check RDC, Article Number, and DO QTY > 0)')
      return
    }
    setSubmitting(true)
    setResult(null)
    try {
      const payload = valid.map(r => ({
        rdc:            r.rdc.trim(),
        article_number: r.article_number.trim(),
        do_qty:         parseFloat(r.do_qty),
      }))
      const { data } = await pendAlcAPI.doUpdate(payload)
      setResult({ submitted: valid.length, updated: data.updated_rows })
      toast.success(`DO update applied — ${data.updated_rows} ARS_PEND_ALC rows updated`)
      setRows([{ ...EMPTY_ROW }])
      loadHistory()
    } catch (e) {
      toast.error(e.response?.data?.detail || 'DO update failed')
    } finally {
      setSubmitting(false)
    }
  }

  const fmt = (n) => typeof n === 'number'
    ? n.toLocaleString(undefined, { maximumFractionDigits: 0 }) : '—'

  const _inp = {
    fontSize: 10, padding: '4px 7px', border: `1px solid ${C.border}`,
    borderRadius: 4, width: '100%', outline: 'none',
  }

  return (
    <div style={{ padding: '16px 20px', fontFamily: 'Inter,system-ui,sans-serif',
                  fontSize: 11, color: C.text, background: C.bg, minHeight: '100vh' }}>

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
        <Truck size={16} color={C.primary}/>
        <div style={{ fontSize: 13, fontWeight: 800, color: C.text }}>Daily DO Entry</div>
        <div style={{ fontSize: 10, color: C.textMuted }}>
          Record SAP Delivery Order quantities to update pending allocation balances
        </div>
      </div>

      {/* Upload CSV */}
      <div style={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 8,
                    padding: 12, marginBottom: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
          <div style={{ fontSize: 10, fontWeight: 700, color: C.textSub, letterSpacing: '.05em' }}>
            IMPORT FROM CSV
          </div>
          <div style={{ fontSize: 9, color: C.textMuted }}>
            Required columns: RDC, Article_Number, DO_QTY (aliases accepted)
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <button onClick={() => fileRef.current?.click()}
            style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 10,
                     padding: '5px 12px', borderRadius: 4, border: `1px solid ${C.primary}`,
                     background: '#fff', color: C.primary, cursor: 'pointer', fontWeight: 600 }}>
            <Upload size={12}/> Choose CSV
          </button>
          <div style={{ fontSize: 9, color: C.textMuted }}>
            or enter rows manually below
          </div>
          <input ref={fileRef} type="file" accept=".csv" onChange={handleFile}
            style={{ display: 'none' }}/>
        </div>
      </div>

      {/* Manual entry table */}
      <div style={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 8,
                    padding: 12, marginBottom: 12 }}>
        <div style={{ fontSize: 10, fontWeight: 700, color: C.textSub,
                      letterSpacing: '.05em', marginBottom: 8 }}>DELIVERY ORDER ROWS</div>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ background: C.bg }}>
              {['RDC / Receiving Store', 'Article Number', 'DO Qty', ''].map((h, i) => (
                <th key={i} style={{ padding: '6px 8px', textAlign: 'left', fontSize: 9,
                                     fontWeight: 700, color: C.textSub, letterSpacing: '.05em',
                                     borderBottom: `1px solid ${C.border}` }}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i} style={{ borderBottom: `1px solid ${C.border}` }}>
                <td style={{ padding: '4px 6px', width: '30%' }}>
                  <input value={r.rdc} onChange={e => setRow(i, 'rdc', e.target.value)}
                    placeholder="e.g. DC01" style={_inp}/>
                </td>
                <td style={{ padding: '4px 6px', width: '40%' }}>
                  <input value={r.article_number}
                    onChange={e => setRow(i, 'article_number', e.target.value)}
                    placeholder="e.g. 1234567890" style={{ ..._inp, fontFamily: 'monospace' }}/>
                </td>
                <td style={{ padding: '4px 6px', width: '20%' }}>
                  <input type="number" min="0" step="1"
                    value={r.do_qty} onChange={e => setRow(i, 'do_qty', e.target.value)}
                    placeholder="0" style={{ ..._inp, textAlign: 'right' }}/>
                </td>
                <td style={{ padding: '4px 6px', textAlign: 'center' }}>
                  {rows.length > 1 && (
                    <button onClick={() => removeRow(i)}
                      style={{ background: 'none', border: 'none', cursor: 'pointer',
                               color: C.red, padding: 2 }}>
                      <Trash2 size={12}/>
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <div style={{ display: 'flex', gap: 8, marginTop: 10, alignItems: 'center' }}>
          <button onClick={addRow}
            style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 10,
                     padding: '4px 10px', borderRadius: 4, border: `1px solid ${C.border}`,
                     background: '#fff', color: C.textSub, cursor: 'pointer' }}>
            <Plus size={11}/> Add Row
          </button>
          <div style={{ flex: 1 }}/>
          <button onClick={handleSubmit} disabled={submitting}
            style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11, fontWeight: 700,
                     padding: '6px 18px', borderRadius: 5, border: 'none',
                     background: submitting ? C.textMuted : C.primary,
                     color: '#fff', cursor: submitting ? 'not-allowed' : 'pointer' }}>
            {submitting
              ? <><RefreshCw size={12} style={{ animation: 'spin 1s linear infinite' }}/> Updating…</>
              : <><Send size={12}/> Submit DO Update</>}
          </button>
        </div>
      </div>

      {/* Result banner */}
      {result && (
        <div style={{ background: '#f0fdf4', border: `1px solid #bbf7d0`, borderRadius: 8,
                      padding: '10px 14px', marginBottom: 12,
                      display: 'flex', alignItems: 'center', gap: 8 }}>
          <CheckCircle size={14} color={C.green}/>
          <span style={{ fontSize: 10, fontWeight: 600, color: C.green }}>
            DO update applied — {result.submitted} rows submitted,&nbsp;
            {result.updated} ARS_PEND_ALC rows updated
          </span>
        </div>
      )}

      {/* History */}
      <div style={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 8,
                    padding: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
          <div style={{ fontSize: 10, fontWeight: 700, color: C.textSub, letterSpacing: '.05em' }}>
            RECENT DO DEDUCTIONS
          </div>
          <button onClick={loadHistory} disabled={histLoading}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: C.textMuted }}>
            <RefreshCw size={11} style={{ animation: histLoading ? 'spin 1s linear infinite' : 'none' }}/>
          </button>
        </div>
        {histLoading ? (
          <div style={{ padding: 20, textAlign: 'center', color: C.textMuted }}>Loading…</div>
        ) : !history.length ? (
          <div style={{ padding: 20, textAlign: 'center', color: C.textMuted }}>
            No DO deductions recorded yet.
          </div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 10 }}>
            <thead>
              <tr style={{ background: C.bg }}>
                {['RDC','ARTICLE','MAJ_CAT','ALLOC','DO QTY','PEND','STATUS','LAST DO'].map(h => (
                  <th key={h} style={{ padding: '6px 10px', textAlign: 'left', fontSize: 9,
                                       fontWeight: 700, color: C.textSub, letterSpacing: '.05em',
                                       borderBottom: `1px solid ${C.border}` }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {history.map((r, i) => (
                <tr key={i} style={{ borderBottom: `1px solid ${C.border}`,
                                     background: r.is_closed ? '#f0fdf4' : (i % 2 === 0 ? '#fff' : C.bg) }}>
                  <td style={{ padding: '5px 10px' }}>{r.rdc}</td>
                  <td style={{ padding: '5px 10px', fontFamily: 'monospace', fontSize: 9 }}>
                    {r.article_number}
                  </td>
                  <td style={{ padding: '5px 10px' }}>{r.maj_cat || '—'}</td>
                  <td style={{ padding: '5px 10px', textAlign: 'right' }}>{fmt(r.alloc_qty)}</td>
                  <td style={{ padding: '5px 10px', textAlign: 'right', color: C.green }}>
                    {fmt(r.do_qty)}
                  </td>
                  <td style={{ padding: '5px 10px', textAlign: 'right', fontWeight: 700,
                               color: r.pend_qty > 0 ? C.amber : C.green }}>
                    {fmt(r.pend_qty)}
                  </td>
                  <td style={{ padding: '5px 10px' }}>
                    <span style={{ fontSize: 8, fontWeight: 700, padding: '2px 6px', borderRadius: 3,
                                   background: r.is_closed ? '#dcfce7' : '#fef3c7',
                                   color: r.is_closed ? C.green : C.amber }}>
                      {r.is_closed ? 'CLOSED' : 'OPEN'}
                    </span>
                  </td>
                  <td style={{ padding: '5px 10px', fontSize: 9, color: C.textMuted, whiteSpace: 'nowrap' }}>
                    {r.last_do_at ? r.last_do_at.slice(0, 16).replace('T', ' ') : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <style>{`@keyframes spin { to { transform: rotate(360deg) } }`}</style>
    </div>
  )
}
