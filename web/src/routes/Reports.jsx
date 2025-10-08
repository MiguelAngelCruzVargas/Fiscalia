import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { supabase } from '../lib/supabaseClient'
import { getOrCreateDefaultCompany } from '../lib/company'

export default function Reports() {
  const [loading, setLoading] = useState(true)
  const [rows, setRows] = useState([])
  const [error, setError] = useState('')
  const [source, setSource] = useState('') // 'server' | 'local'
  const [companyId, setCompanyId] = useState('')
  const [persistMsg, setPersistMsg] = useState('')
  const navigate = useNavigate()

  useEffect(() => {
    ;(async () => {
      setLoading(true)
      setError('')
      try {
        const companyId = await getOrCreateDefaultCompany(supabase)
        const backend = import.meta.env.VITE_BACKEND_URL
        if (backend) {
          try {
            const res = await fetch(`${backend.replace(/\/$/,'')}/reports/monthly?company_id=${companyId}`)
            if (res.ok) {
              const out = await res.json()
              setRows(out || [])
              setSource('server')
              setLoading(false)
              setCompanyId(companyId)
              return
            }
          } catch {}
        }
        // Fallback a cálculo en cliente si no hay backend
        const { data: company } = await supabase
          .from('companies')
          .select('rfc')
          .eq('id', companyId)
          .maybeSingle()
        const rfc = (company?.rfc || '').toUpperCase()
        const { data: ingresos } = await supabase
          .from('cfdi')
          .select('fecha, total, impuestos')
          .eq('emisor_rfc', rfc)
        const { data: egresos } = await supabase
          .from('cfdi')
          .select('fecha, total, impuestos')
          .eq('receptor_rfc', rfc)
        const map = new Map()
        const add = (list, sign) => {
          for (const r of (list || [])) {
            const ym = (r.fecha || '').slice(0,7)
            if (!ym) continue
            const prev = map.get(ym) || { ingresos: 0, egresos: 0, iva_cobrado: 0, iva_acreditable: 0 }
            if (sign > 0) prev.ingresos += Number(r.total || 0)
            else prev.egresos += Number(r.total || 0)
            const iva = Number(r.impuestos ?? 0)
            if (sign > 0) prev.iva_cobrado += (iva || (Number(r.total || 0) * 0.16))
            else prev.iva_acreditable += (iva || (Number(r.total || 0) * 0.16))
            map.set(ym, prev)
          }
        }
        add(ingresos, +1)
        add(egresos, -1)
        const out = [...map.entries()].sort(([a],[b]) => a.localeCompare(b)).map(([ym, v]) => ({
          periodo: ym,
          ingresos: v.ingresos,
          egresos: v.egresos,
          iva_cobrado: v.iva_cobrado,
          iva_acreditable: v.iva_acreditable,
          iva_a_pagar: v.iva_cobrado - v.iva_acreditable,
          // isr_base/isr pueden venir del backend; en cálculo local los omitimos para evitar supuestos
        }))
        setRows(out)
        setSource('local')
        setCompanyId(companyId)
      } catch (e) {
        setError(e.message || 'Error al cargar reportes')
      } finally {
        setLoading(false)
      }
    })()
  }, [])

  return (
    <div className="page">
      <div className="card">
        <h1>Reportes</h1>
        <p>
          Resumen mensual (estimado). Valores basados en <code>total</code> de CFDI importados. Ajustaremos con impuestos desglosados en la siguiente iteración.
          {source && (
            <span style={{ marginLeft: 8, fontSize: 12, opacity: .8 }}>Fuente: {source === 'server' ? 'Servidor' : 'Cálculo local'}</span>
          )}
        </p>
        {error && <div className="msg" style={{ color: '#fca5a5' }}>{error}</div>}
        {loading ? (
          <div>Cargando…</div>
        ) : rows.length === 0 ? (
          <div style={{ marginTop: 12, color: 'rgba(255,255,255,0.85)' }}>
            <div style={{ marginBottom: 8 }}>No hay datos para mostrar.</div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <button className="secondary" onClick={() => navigate('/import')}>Sincronizar desde SAT / Subir XML</button>
              {import.meta.env.VITE_BACKEND_URL ? (
                <a className="secondary" href={`${String(import.meta.env.VITE_BACKEND_URL).replace(/\/$/, '')}/health`} target="_blank" rel="noreferrer">Probar backend</a>
              ) : (
                <span style={{ fontSize: 12, opacity: .8 }}>Configura VITE_BACKEND_URL para usar el cálculo del servidor</span>
              )}
            </div>
          </div>
        ) : (
          <>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', justifyContent: 'space-between' }}>
              <div />
              {source === 'server' && import.meta.env.VITE_BACKEND_URL && (
                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  <button
                    className="secondary"
                    onClick={async () => {
                      setPersistMsg('')
                      try {
                        const backend = String(import.meta.env.VITE_BACKEND_URL)
                        const url = `${backend.replace(/\/$/, '')}/reports/monthly?company_id=${companyId}&persist=true`
                        const res = await fetch(url)
                        if (!res.ok) throw new Error(`Error ${res.status}`)
                        setPersistMsg('Guardado en taxes_monthly')
                      } catch (e) {
                        setPersistMsg('No se pudo guardar: ' + (e.message || e))
                      }
                    }}
                  >
                    Guardar en taxes_monthly
                  </button>
                  {persistMsg && <span style={{ fontSize: 12, opacity: .85 }}>{persistMsg}</span>}
                </div>
              )}
            </div>
            <table className="tbl">
              <thead>
                <tr>
                  <th>Periodo</th>
                  <th>Ingresos</th>
                  <th>Egresos</th>
                  <th>IVA cobrado</th>
                  <th>IVA acreditable</th>
                  <th>IVA a pagar</th>
                  <th>ISR base</th>
                  <th>ISR</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={i}>
                    <td>{r.periodo}</td>
                    <td>${Number(r.ingresos || 0).toFixed(2)}</td>
                    <td>${Number(r.egresos || 0).toFixed(2)}</td>
                    <td>${Number(r.iva_cobrado || 0).toFixed(2)}</td>
                    <td>${Number(r.iva_acreditable || 0).toFixed(2)}</td>
                    <td>${Number(r.iva_a_pagar || 0).toFixed(2)}</td>
                    <td>{typeof r.isr_base === 'number' ? `$${r.isr_base.toFixed(2)}` : '—'}</td>
                    <td>{typeof r.isr === 'number' ? `$${r.isr.toFixed(2)}` : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </div>
      <style>{`
        .page{ padding:24px; display:flex; justify-content:center }
        .card{ width:100%; max-width:860px; background:rgba(255,255,255,0.06); border:1px solid rgba(255,255,255,0.1); border-radius:16px; padding:24px; color:#fff }
        .tbl{ width:100%; border-collapse: collapse; margin-top:12px; font-size:14px }
        .tbl th, .tbl td{ border-bottom:1px solid rgba(255,255,255,0.15); padding:8px 10px; text-align:right }
        .tbl th:first-child, .tbl td:first-child{ text-align:left }
        .secondary{ background:transparent; border:1px solid rgba(255,255,255,0.3); color:#fff; padding:8px 12px; border-radius:8px; cursor:pointer }
      `}</style>
    </div>
  )
}
