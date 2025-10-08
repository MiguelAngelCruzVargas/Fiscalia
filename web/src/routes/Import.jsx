import { useCallback, useEffect, useState } from 'react'
import { supabase, CFDI_BUCKET } from '../lib/supabaseClient'
import { getOrCreateDefaultCompany } from '../lib/company'

export default function ImportXml() {
  const [logs, setLogs] = useState([])
  const [loading, setLoading] = useState(false)
  const [pickerKey, setPickerKey] = useState(0)
  const [summary, setSummary] = useState({ total: 0, ok: 0, skipped: 0, storageFailed: 0, dbFailed: 0 })
  const [satLoading, setSatLoading] = useState(false)
  const [authLoading, setAuthLoading] = useState(false)
  const [satDates, setSatDates] = useState({ from: '', to: '' })
  const [satKind, setSatKind] = useState('recibidos')
  const [satJob, setSatJob] = useState({ id: '', status: '' })
  const [satPass, setSatPass] = useState('')
  const [selfCheckMsg, setSelfCheckMsg] = useState('')
  const [satMode, setSatMode] = useState('unknown') // mock | soap | unknown
  const [demoMode, setDemoMode] = useState(false)
  const [backendOk, setBackendOk] = useState(!!import.meta.env.VITE_BACKEND_URL)
  const [firmaMsg, setFirmaMsg] = useState('')
  const [authMsg, setAuthMsg] = useState('')
  const backend = import.meta.env.VITE_BACKEND_URL

  // Pequeño helper para evitar que un fetch quede colgado indefinidamente
  const fetchWithTimeout = useCallback(async (url, options = {}, timeoutMs = 15000) => {
    const controller = new AbortController()
    const t = setTimeout(() => controller.abort(), timeoutMs)
    try {
      return await fetch(url, { ...options, signal: controller.signal })
    } finally {
      clearTimeout(t)
    }
  }, [])

  // Preflight helper para poder reintentar desde UI
  const runPreflight = useCallback(async () => {
    try {
      setSelfCheckMsg('')
      if (!backend) {
        setBackendOk(false)
        setSelfCheckMsg('Falta VITE_BACKEND_URL en web/.env.local')
        return
      }
      setBackendOk(true)
      const res = await fetch(`${String(backend).replace(/\/$/, '')}/sat/self-check`)
      const out = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(out?.detail || res.status)
      setSatMode(String(out?.sat_mode || 'unknown'))
      setDemoMode(Boolean(out?.demo_mode === true || String(out?.demo_mode).toLowerCase() === 'true'))
      // Intentar inspección de e.firma para dar feedback temprano (no requiere contraseña)
      try {
        const { data: { user } } = await supabase.auth.getUser()
        if (!user) throw new Error('Sesión no encontrada')
        const ir = await fetch(`${String(backend).replace(/\/$/, '')}/sat/inspect`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ user_id: user.id })
        })
        const info = await ir.json().catch(() => ({}))
        if (ir.ok) {
          const exp = info?.valid_to ? new Date(info.valid_to).toISOString().slice(0, 10) : null
          const csdWarn = info?.is_probably_csd ? ' · Posible CSD: se requiere e.firma (FIEL)' : ''
          setFirmaMsg(`Certificado OK${exp ? ' (vence ' + exp + ')' : ''}${csdWarn}`)
        } else {
          setFirmaMsg(info?.detail ? `e.firma: ${info.detail}` : 'e.firma no lista')
        }
      } catch (e) {
        setFirmaMsg(String(e?.message || e))
      }
      setSelfCheckMsg('Núcleo OK')
    } catch (e) {
      setSelfCheckMsg('Error: ' + (e.message || e))
    }
  }, [backend, supabase])

  // Preflight: detectar backend, modo SAT y disponibilidad de e.firma
  useEffect(() => {
    (async () => {
      try {
        await runPreflight()
      } catch {}
    })()
  }, [runPreflight])

  const onDrop = useCallback(async (e) => {
    e.preventDefault()
  const files = [...(e.dataTransfer?.files || [])].filter(f => f.name.toLowerCase().endsWith('.xml'))
    if (!files.length) return
    setLoading(true)
  setSummary({ total: files.length, ok: 0, skipped: 0, storageFailed: 0, dbFailed: 0 })
    const { data: { user } } = await supabase.auth.getUser()
    if (!user) return

    // Obtener o crear empresa por defecto del usuario
    let company_id = null
    try { company_id = await getOrCreateDefaultCompany(supabase) } catch (err) { setLogs(l => [...l, `Empresa: ${err.message}`]) }

    for (const file of files) {
      try {
        const text = await file.text()
        // Parse un poco más robusto (3.3/4.0)
        const uuid = /UUID="([^"]+)"/i.exec(text)?.[1] || null
        const tipo = /TipoDeComprobante="([IEP])"/i.exec(text)?.[1] || null
        const emisor_rfc = (/Emisor[^>]*Rfc="([^"]+)"/i.exec(text)?.[1] || '').toUpperCase() || null
        const receptor_rfc = (/Receptor[^>]*Rfc="([^"]+)"/i.exec(text)?.[1] || '').toUpperCase() || null
        const fecha = /Fecha="([0-9T:\-]+)"/i.exec(text)?.[1]?.slice(0,10) || null
        const subtotal = /SubTotal="([0-9\.]+)"/i.exec(text)?.[1] || null
        const total = /Total="([0-9\.]+)"/i.exec(text)?.[1] || null
        // IVA (Impuesto=002). Sumamos importes de traslados IVA si existen
        let iva = null
        try {
          const ivaMatches = [...text.matchAll(/Traslados?[^>]*Impuesto=\"002\"[^>]*Importe=\"([0-9\.]+)\"/gi)]
          if (ivaMatches.length) {
            iva = ivaMatches.reduce((acc, m) => acc + Number(m[1] || 0), 0)
          }
        } catch {}

        if (!uuid) {
          setLogs(l => [...l, `${file.name}: sin UUID`] )
          setSummary(s => ({ ...s, skipped: s.skipped + 1 }))
          continue
        }

        // Subir XML a Storage bajo {uid}/{company}/{uuid}.xml
        const key = `${user.id}/${company_id || 'default'}/${uuid}.xml`
        const up = await supabase.storage.from(CFDI_BUCKET).upload(key, file, { contentType: 'application/xml', upsert: true })
        if (up.error) {
          setSummary(s => ({ ...s, storageFailed: s.storageFailed + 1 }))
          throw up.error
        }

        // Upsert por UUID
        const { error } = await supabase
          .from('cfdi')
          .upsert({
            company_id,
            uuid,
            tipo,
            emisor_rfc,
            receptor_rfc,
            fecha,
            subtotal: subtotal ? Number(subtotal) : null,
            impuestos: iva != null ? Number(iva) : null,
            total: total ? Number(total) : null,
            xml_ref: key,
            status: 'imported'
          }, { onConflict: 'uuid' })

        setLogs(l => [...l, `${file.name}: ${error ? error.message : 'OK'}`])
        setSummary(s => error ? { ...s, dbFailed: s.dbFailed + 1 } : { ...s, ok: s.ok + 1 })
      } catch (err) {
        setLogs(l => [...l, `${file.name}: ${err.message}`])
      }
    }
    setLoading(false)
  }, [])

  return (
    <div className="page" onDragOver={e => e.preventDefault()} onDrop={onDrop}>
      <div className="card">
        <h1>Importar CFDI (XML)</h1>
        <p>Arrastra y suelta tus archivos .xml aquí. Este es un parser básico de MVP.</p>
        <div className="sat-sync" style={{ marginTop: 8, padding: 12, border: '1px dashed rgba(255,255,255,0.2)', borderRadius: 8 }}>
          <div style={{ marginBottom: 6, fontWeight: 600 }}>Sincronizar desde SAT (beta)</div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
            <label>Tipo:
              <select value={satKind} onChange={e => setSatKind(e.target.value)} style={{ marginLeft: 6 }}>
                <option value="recibidos">Recibidos</option>
                <option value="emitidos">Emitidos</option>
              </select>
            </label>
            <label>Desde:
              <input type="date" value={satDates.from} onChange={e => setSatDates(s => ({ ...s, from: e.target.value }))} style={{ marginLeft: 6 }} />
            </label>
            <label>Hasta:
              <input type="date" value={satDates.to} onChange={e => setSatDates(s => ({ ...s, to: e.target.value }))} style={{ marginLeft: 6 }} />
            </label>
            <label>Contraseña e.firma:
              <input type="password" value={satPass} onChange={e => setSatPass(e.target.value)} placeholder="••••••" style={{ marginLeft: 6 }} />
              <span style={{ marginLeft: 8, fontSize: 12, opacity: .75 }}>{(satPass && satPass.trim().length > 0) ? 'capturada' : 'no capturada'}</span>
            </label>
            <div style={{ fontSize: 12, opacity: .85, display: 'flex', alignItems: 'center', gap: 8 }}>
              <span>Estado: {backendOk ? 'Backend OK' : 'Backend no configurado'}{satMode !== 'unknown' ? ` · Modo ${satMode}${demoMode ? ' (demo)' : ''}` : ''}{firmaMsg ? ` · ${firmaMsg}` : ''}</span>
              <button type="button" className="secondary" style={{ padding: '4px 8px' }} onClick={() => runPreflight()}>Reintentar estado</button>
            </div>
            {(() => {
              const disabled = satLoading || !backendOk || (satMode === 'soap' && !demoMode && !(satPass && satPass.trim().length > 0))
              let reason = ''
              if (disabled) {
                if (satLoading) reason = 'Procesando anterior solicitud…'
                else if (!backendOk) reason = 'Falta VITE_BACKEND_URL'
                else if (satMode === 'soap' && !demoMode && !(satPass && satPass.trim().length > 0)) reason = 'Escribe la contraseña de la e.firma'
              }
              return (
                <div style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                  <button disabled={disabled} onClick={async () => {
              try {
                setSatLoading(true)
                const { data: { user } } = await supabase.auth.getUser()
                if (!user) throw new Error('Debes iniciar sesión')
                const company_id = await getOrCreateDefaultCompany(supabase)
                if (!backend) throw new Error('Configura VITE_BACKEND_URL para habilitar la sincronización')
                let res
                try {
                  res = await fetchWithTimeout(`${String(backend).replace(/\/$/, '')}/sat/sync`, {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ user_id: user.id, company_id, kind: satKind, date_from: satDates.from, date_to: satDates.to, passphrase: satPass || undefined })
                  }, 20000)
                } catch (netErr) {
                  throw new Error('No se pudo contactar al backend (¿se reinició o está caído?). Detalle: ' + (netErr?.message || netErr))
                }
                if (!res.ok) {
                  let detail = ''
                  try { detail = (await res.json())?.detail || '' } catch {}
                  throw new Error(`Backend respondió ${res.status}${detail ? ': ' + detail : ''}`)
                }
                const out = await res.json().catch(() => ({}))
                const jobId = out.id
                setSatJob({ id: jobId || '', status: 'queued' })
                setLogs(l => [...l, `SAT sync encolado: ${jobId || 'OK'}`])

                // Polling de estado del job
                if (jobId) {
                    const jobUrl = `${String(backend).replace(/\/$/, '')}/sat/jobs/${jobId}`
                  for (let i = 0; i < 30; i++) { // ~30s
                    await new Promise(r => setTimeout(r, 1000))
                    let jr
                    try { jr = await fetchWithTimeout(jobUrl, {}, 3000) } catch (pollErr) { continue }
                    if (!jr.ok) continue
                    const j = await jr.json().catch(() => ({}))
                    if (j?.status) setSatJob({ id: jobId, status: j.status })
                    if (j?.status === 'success') {
                      const td = (j && typeof j.total_downloaded !== 'undefined') ? j.total_downloaded : 0
                      setLogs(l => [...l, `SAT job ${jobId}: success (descargados ${td})`])
                      break
                    }
                    if (j?.status === 'error') {
                      setLogs(l => [...l, `SAT job ${jobId}: error ${j.error || ''}`])
                      break
                    }
                  }
                }
              } catch (e) {
                setLogs(l => [...l, `SAT sync: ${e.message}`])
              } finally {
                setSatLoading(false)
              }
            }}>{satLoading ? 'Sincronizando…' : 'Sincronizar desde SAT'}</button>
                  {reason && <span style={{ fontSize: 12, opacity: .75 }}>{reason}</span>}
                </div>
              )
            })()}
            {(backendOk) && (
              <div style={{ marginTop: 6, display: 'flex', gap: 8, alignItems: 'center' }}>
                <button className="secondary" type="button" disabled={!backendOk || !satPass || authLoading} onClick={async () => {
                  try {
                    setAuthLoading(true)
                    setAuthMsg('Probando…')
                    const backend = import.meta.env.VITE_BACKEND_URL
                    if (!backend) { setAuthMsg('Falta VITE_BACKEND_URL'); return }
                    const { data: { user } } = await supabase.auth.getUser()
                    if (!user) { setAuthMsg('Debes iniciar sesión'); return }
                    const res = await fetchWithTimeout(`${String(backend).replace(/\/$/, '')}/sat/auth`, {
                      method: 'POST', headers: { 'Content-Type': 'application/json' },
                      body: JSON.stringify({ user_id: user.id, passphrase: satPass })
                    }, 20000)
                    const out = await res.json().catch(() => ({}))
                    if (!res.ok) throw new Error(out?.detail || `Error ${res.status}`)
                    setAuthMsg(`Autenticación SAT OK (token_len=${out?.token_len ?? 'N/A'})`)
                  } catch (e) {
                    setAuthMsg('Auth error: ' + (e.message || e))
                  } finally {
                    setAuthLoading(false)
                  }
                }}>{authLoading ? 'Probando…' : 'Probar autenticación'}</button>
                {authMsg && <span style={{ fontSize: 12, opacity: .85 }}>{authMsg}</span>}
              </div>
            )}
            <button className="secondary" type="button" onClick={async () => {
              try {
                setSelfCheckMsg('')
                const backend = import.meta.env.VITE_BACKEND_URL
                if (!backend) { setSelfCheckMsg('Falta VITE_BACKEND_URL en web/.env.local'); return }
                const res = await fetch(`${backend.replace(/\/$/, '')}/sat/self-check`)
                const out = await res.json().catch(() => ({}))
                if (!res.ok) throw new Error(out?.detail || res.status)
                const tab = out?.tables || {}
                const bkt = out?.buckets || {}
                const missingTables = Object.entries(tab).filter(([,v]) => !v.exists).map(([k]) => k)
                const missingBuckets = Object.entries(bkt).filter(([,v]) => !v.exists).map(([k]) => k)
                if (missingTables.length || missingBuckets.length) {
                  setSelfCheckMsg(`Faltan: tablas [${missingTables.join(', ')}] ${missingBuckets.length ? ' y buckets [' + missingBuckets.join(', ') + ']' : ''}`)
                } else {
                  const mode = String(out?.sat_mode || 'unknown')
                  const demo = Boolean(out?.demo_mode === true || String(out?.demo_mode).toLowerCase() === 'true')
                  let modeMsg = 'modo desconocido'
                  if (mode === 'mock') modeMsg = 'modo mock'
                  else if (mode === 'soap') modeMsg = demo ? 'modo soap (demo)' : 'modo soap (real)'
                  setSelfCheckMsg(`Núcleo OK (${modeMsg})`)
                }
              } catch (e) {
                setSelfCheckMsg('Error: ' + (e.message || e))
              }
            }}>Probar núcleo</button>
          </div>
          <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.7)', marginTop: 6 }}>
            Requiere backend configurado (VITE_BACKEND_URL). {String(import.meta.env.VITE_DEMO_MODE).toLowerCase() === 'true' ? 'Modo demo activo: no se requiere e.firma.' : 'En modo SAT real se requiere e.firma (.cer/.key) cargada y contraseña.'}
            {selfCheckMsg ? (<div style={{ marginTop: 4 }}>Self-check: {selfCheckMsg}</div>) : null}
            {satJob.id ? (<div style={{ marginTop: 4 }}>Job: <code>{satJob.id}</code> – Estado: <strong>{satJob.status || '...'}</strong></div>) : null}
          </div>
        </div>
        <div style={{ marginTop: 8 }}>
          <input
            key={pickerKey}
            type="file"
            accept=".xml"
            multiple
            onChange={async (e) => {
              const files = [...(e.target.files || [])].filter(f => f.name.toLowerCase().endsWith('.xml'))
              if (!files.length) return
              // Reutilizamos la lógica del drop
              const dt = new DataTransfer()
              files.forEach(f => dt.items.add(f))
              const fakeEvent = { preventDefault: () => {}, dataTransfer: dt } 
              await onDrop(fakeEvent)
              // Reset para permitir re-selección del mismo archivo
              setPickerKey(k => k + 1)
            }}
          />
        </div>
        <div className={`drop ${loading ? 'loading' : ''}`}>
          {loading ? 'Procesando…' : 'Suelta aquí tus XML'}
        </div>
        <div className="summary">
          <strong>Resumen:</strong>
          <span style={{ marginLeft: 8 }}>Total: {summary.total}</span>
          <span style={{ marginLeft: 8, color: '#86efac' }}>OK: {summary.ok}</span>
          <span style={{ marginLeft: 8, color: '#fde68a' }}>Sin UUID: {summary.skipped}</span>
          <span style={{ marginLeft: 8, color: '#fca5a5' }}>Storage err: {summary.storageFailed}</span>
          <span style={{ marginLeft: 8, color: '#fca5a5' }}>DB err: {summary.dbFailed}</span>
        </div>
        <ul className="logs">
          {logs.map((x, i) => <li key={i}>{x}</li>)}
        </ul>
      </div>
  <style>{`
        .page{ padding:24px; display:flex; justify-content:center }
        .card{ width:100%; max-width:720px; background:rgba(255,255,255,0.06); border:1px solid rgba(255,255,255,0.1); border-radius:16px; padding:24px; color:#fff }
        .drop{ margin-top:12px; height:160px; border:2px dashed rgba(255,255,255,0.3); border-radius:12px; display:flex; align-items:center; justify-content:center; color:rgba(255,255,255,0.85) }
        .drop.loading{ opacity:.7 }
        .summary{ margin-top:10px; font-size:13px; color:rgba(255,255,255,0.9) }
        .logs{ margin-top:12px; padding-left:18px; color:rgba(255,255,255,0.9) }
  `}</style>
    </div>
  )
}
