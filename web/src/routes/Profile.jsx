import { useEffect, useState } from 'react'
import { supabase, FIRMAS_BUCKET } from '../lib/supabaseClient'
import { syncCompanyFromProfile } from '../lib/company'
import { parseCurp, rfcBaseFromCurp } from '../lib/curp'

export default function Profile() {
  const [form, setForm] = useState({
    rfc: '',
    persona_moral: null,
    legal_name: '',
    regime: '',
    first_name: '',
    last_name: '',
    curp: '',
    street: '',
    ext_number: '',
    int_number: '',
    neighborhood: '',
    city: '',
    state: '',
    postal_code: '',
    firma_ref: ''
  })
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  const [cerFile, setCerFile] = useState(null)
  const [keyFile, setKeyFile] = useState(null)
  const [passphrase, setPassphrase] = useState('')
  const [uploading, setUploading] = useState(false)
  const [companyInfo, setCompanyInfo] = useState(null)
  const [syncingCompany, setSyncingCompany] = useState(false)
  const [firmaFiles, setFirmaFiles] = useState({ hasCer: false, hasKey: false })
  const [suggesting, setSuggesting] = useState(false)
  const [verifying, setVerifying] = useState(false)
  const [verifyInfo, setVerifyInfo] = useState(null)
  const [autoCompleting, setAutoCompleting] = useState(false)

  useEffect(() => {
    let ignore = false
    async function load() {
      const { data: { user } } = await supabase.auth.getUser()
      if (!user) return
      let { data, error } = await supabase
        .from('profiles')
        .select('rfc, persona_moral, legal_name, regime, first_name, last_name, curp, street, ext_number, int_number, neighborhood, city, state, postal_code, birth_date, gender, birth_state, firma_ref')
        .eq('user_id', user.id)
        .maybeSingle()
      // Si no existe perfil lo creamos vacío para evitar que "desaparezca" tras limpieza.
      if (!error && !data) {
        try {
          const ins = await supabase.from('profiles').insert({ user_id: user.id, updated_at: new Date().toISOString() }).select('rfc, persona_moral, legal_name, regime, first_name, last_name, curp, street, ext_number, int_number, neighborhood, city, state, postal_code, birth_date, gender, birth_state, firma_ref').maybeSingle()
          if (!ignore && ins.data) data = ins.data
        } catch {}
      }
      if (!ignore && data) {
        const rfcUpper = (data.rfc || '').toUpperCase()
        const pm = (typeof data.persona_moral === 'boolean') ? data.persona_moral : (rfcUpper ? (rfcUpper.length === 12 ? true : (rfcUpper.length === 13 ? false : null)) : null)
        setForm({
        rfc: (data.rfc || '').toUpperCase(),
        persona_moral: pm,
        legal_name: data.legal_name || '',
        regime: data.regime || '',
        first_name: data.first_name || '',
        last_name: data.last_name || '',
        curp: data.curp || '',
        street: data.street || '',
        ext_number: data.ext_number || '',
        int_number: data.int_number || '',
        neighborhood: data.neighborhood || '',
        city: data.city || '',
        state: data.state || '',
        postal_code: data.postal_code || '',
        birth_date: data.birth_date || '',
        gender: data.gender || '',
        birth_state: data.birth_state || '',
        firma_ref: data.firma_ref || ''
      })
      }
      // Actualizar estado de archivos de e.firma (dentro de load para poder usar await)
      try {
        const base = (data?.firma_ref || '').trim()
        if (base) {
          const { data: list, error } = await supabase.storage.from(FIRMAS_BUCKET).list(base)
          if (!ignore && !error) {
            const names = (list || []).map(x => x.name?.toLowerCase?.() || '')
            const hasCer = names.includes('cert.cer')
            const hasKey = names.includes('key.key')
            setFirmaFiles({ hasCer, hasKey })
            // Auto-sugerir si ambos existen y aún no hay RFC ni nombre cargado
            if (hasCer && (!form.rfc || !form.first_name) && !suggesting) {
              autoSuggestFromFirma(user.id, base, { skipIfRfc: !!form.rfc })
            }
          }
        } else if (!ignore) {
          setFirmaFiles({ hasCer: false, hasKey: false })
        }
      } catch {}
      // Cargar empresa existente si hay
      try {
        const { data: comp } = await supabase
          .from('companies')
          .select('id, name, rfc')
          .eq('owner_id', user.id)
          .limit(1)
        if (!ignore && comp && comp.length) setCompanyInfo(comp[0])
      } catch {}
    }
    load()
    return () => { ignore = true }
  }, [])

  async function onSubmit(e) {
    e.preventDefault()
    setSaving(true)
    setMessage('')
    const { data: { user } } = await supabase.auth.getUser()
    if (!user) return
    // Validación mínima
    const rfcOk = /^[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}$/.test((form.rfc || '').toUpperCase())
    const curpOk = form.curp ? /^[A-Z]{4}\d{6}[HM][A-Z]{5}[A-Z0-9]{2}$/.test((form.curp || '').toUpperCase()) : true
    const postalOk = form.postal_code ? /^\d{5}$/.test(form.postal_code) : true
    const isMoral = form.persona_moral === true || (form.rfc && form.rfc.length === 12)
    if ((!isMoral && (!form.first_name || !form.last_name)) || (isMoral && !form.legal_name) || !rfcOk) {
      setSaving(false)
      setMessage(isMoral ? 'Revisa: razón social y RFC válido son obligatorios' : 'Revisa: nombre, apellidos y RFC válido son obligatorios')
      return
    }
    if (!curpOk || !postalOk) {
      setSaving(false)
      setMessage('Revisa: CURP o CP inválidos')
      return
    }

  const payload = {
    ...form,
    persona_moral: typeof form.persona_moral === 'boolean' ? form.persona_moral : (form.rfc ? form.rfc.length === 12 : null),
    rfc: (form.rfc || '').toUpperCase(),
    curp: form.curp?.toUpperCase() || null,
    updated_at: new Date().toISOString()
  }
    const { error } = await supabase
      .from('profiles')
      .upsert({ user_id: user.id, ...payload }, { onConflict: 'user_id' })
    setSaving(false)
    setMessage(error ? error.message : 'Perfil guardado')
  }

  async function uploadFirma() {
    setMessage('')
    if (!cerFile || !keyFile) {
      setMessage('Selecciona archivo .cer y .key')
      return
    }
    // Validaciones rápidas en cliente
    const maxSize = 2 * 1024 * 1024; // 2 MB
    const cerOk = cerFile.name.toLowerCase().endsWith('.cer') && cerFile.size <= maxSize
    const keyOk = keyFile.name.toLowerCase().endsWith('.key') && keyFile.size <= maxSize
    if (!cerOk || !keyOk) {
      const reasons = []
      if (!cerFile.name.toLowerCase().endsWith('.cer')) reasons.push('el .cer debe tener extensión .cer')
      if (!keyFile.name.toLowerCase().endsWith('.key')) reasons.push('el .key debe tener extensión .key')
      if (cerFile.size > maxSize) reasons.push('el .cer supera 2MB')
      if (keyFile.size > maxSize) reasons.push('el .key supera 2MB')
      setMessage('Archivos inválidos: ' + reasons.join(' · '))
      return
    }
    setUploading(true)
    try {
      const { data: { user } } = await supabase.auth.getUser()
      if (!user) throw new Error('Sesión no encontrada')

      // Ruta dentro del bucket (sin prefijar con el nombre del bucket)
      const basePath = `${user.id}/${Date.now()}`
      // NOTA: Para MVP no ciframos en cliente. En producción, cifrar antes de subir.
      const up1 = await supabase.storage.from(FIRMAS_BUCKET).upload(`${basePath}/cert.cer`, cerFile, {
        contentType: 'application/x-x509-ca-cert'
      })
      if (up1.error) throw up1.error
      const up2 = await supabase.storage.from(FIRMAS_BUCKET).upload(`${basePath}/key.key`, keyFile, {
        contentType: 'application/octet-stream'
      })
      if (up2.error) throw up2.error

      // Guardar referencia del folder en profiles.firma_ref (según esquema)
      const { error } = await supabase
        .from('profiles')
        .upsert({ user_id: user.id, firma_ref: basePath, updated_at: new Date().toISOString() }, { onConflict: 'user_id' })
      if (error) throw error
      setForm(prev => ({ ...prev, firma_ref: basePath }))
      // Refrescar estado de archivos
      try {
        const { data: list } = await supabase.storage.from(FIRMAS_BUCKET).list(basePath)
        const names = (list || []).map(x => x.name?.toLowerCase?.() || '')
        setFirmaFiles({ hasCer: names.includes('cert.cer'), hasKey: names.includes('key.key') })
      } catch {}
      setMessage('e.firma subida y guardada')
      // Intentar sugerir automáticamente tras subida
      try {
        const backend = import.meta.env.VITE_BACKEND_URL || 'http://127.0.0.1:8000'
        const res = await fetch(`${backend.replace(/\/$/, '')}/sat/inspect`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ user_id: user.id })
        })
        if (res.ok) {
          const out = await res.json().catch(() => ({}))
          applySuggestions(out, { replaceExisting: false })
        }
      } catch {}
    } catch (err) {
      const msg = String(err?.message || err)
      // Tips más claros para errores comunes de Storage/RLS
      if (msg.toLowerCase().includes('row-level security')) {
        setMessage('No tienes permisos para escribir en el bucket. Aplica las políticas RLS de Storage para el bucket y ruta "' + FIRMAS_BUCKET + '/{auth.uid()}/…" (ver docs).')
      } else if (msg.toLowerCase().includes('bucket') && msg.toLowerCase().includes('not found')) {
        setMessage(`El bucket "${FIRMAS_BUCKET}" no existe. Crea un bucket PRIVADO con ese nombre en Supabase Storage o ajusta VITE_FIRMAS_BUCKET.`)
      } else {
        setMessage(msg || 'Error al subir e.firma')
      }
    } finally {
      setUploading(false)
    }
  }

  async function fetchAndApplySuggestions(userId, opts = { replaceExisting: false }) {
    const backend = import.meta.env.VITE_BACKEND_URL || 'http://127.0.0.1:8000'
    const res = await fetch(`${backend.replace(/\/$/, '')}/sat/inspect`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ user_id: userId })
    })
    const out = await res.json().catch(() => ({}))
    if (!res.ok) throw new Error(out?.detail || `Error ${res.status}`)
    applySuggestions(out, { replaceExisting: opts.replaceExisting })
    return out
  }

  async function autoCompleteFromFirma() {
    try {
      setMessage('')
      setAutoCompleting(true)
      const { data: { user } } = await supabase.auth.getUser()
      if (!user) throw new Error('Debes iniciar sesión')
      // Si aún no se subieron archivos pero están seleccionados localmente: subir primero
      if (!form.firma_ref) {
        if (!cerFile || !keyFile) throw new Error('Selecciona y sube primero tu .cer y .key')
        await uploadFirma()
      } else {
        // Verificar que realmente existan en Storage (si borrados servidor-side)
        try {
          const { data: list } = await supabase.storage.from(FIRMAS_BUCKET).list(form.firma_ref)
          const names = (list || []).map(x => x.name?.toLowerCase?.() || '')
          if (!(names.includes('cert.cer') && names.includes('key.key'))) {
            throw new Error('Faltan archivos en Storage; vuelve a subir la e.firma')
          }
        } catch (err) {
          throw new Error(err.message || 'No se pudo listar la carpeta de e.firma')
        }
      }
      const out = await fetchAndApplySuggestions(user.id, { replaceExisting: false })
      const bits = []
      if (out?.rfc) bits.push(`RFC ${String(out.rfc).toUpperCase()}`)
      if (typeof out?.persona_moral === 'boolean') bits.push(out.persona_moral ? 'Persona moral' : 'Persona física')
      if (out?.valid_to) bits.push(`vence ${String(out.valid_to).slice(0,10)}`)
      setMessage(`Autocompletado desde e.firma${bits.length ? ' (' + bits.join(' · ') + ')' : ''}`)
    } catch (err) {
      setMessage(err.message || 'No se pudo autocompletar')
    } finally {
      setAutoCompleting(false)
    }
  }

  function applySuggestions(out, { replaceExisting }) {
    if (!out) return
    setForm(prev => {
      const next = { ...prev }
      if (out.rfc && (!prev.rfc || replaceExisting)) next.rfc = String(out.rfc).toUpperCase()
      if (typeof out.persona_moral === 'boolean') next.persona_moral = out.persona_moral
      const cn = (out.subject_common_name || '').trim()
      const full = (out.full_name || cn).trim()
      if (next.persona_moral === true) {
        if (out.legal_name && (replaceExisting || !next.legal_name)) next.legal_name = out.legal_name
        if (!next.legal_name && cn) next.legal_name = cn
      } else if (next.persona_moral === false) {
        if (full) {
          const parts = full.split(/\s+/)
          if (parts.length >= 2) {
            if (replaceExisting || !next.first_name) next.first_name = parts.slice(0, parts.length - 1).join(' ')
            if (replaceExisting || !next.last_name) next.last_name = parts[parts.length - 1]
          } else if (replaceExisting || !next.first_name) {
            next.first_name = full
          }
        }
      }
      return next
    })
  }

  async function autoSuggestFromFirma(userId, basePath, { skipIfRfc }) {
    try {
      if (skipIfRfc && form.rfc) return
      const backend = import.meta.env.VITE_BACKEND_URL || 'http://127.0.0.1:8000'
      const res = await fetch(`${backend.replace(/\/$/, '')}/sat/inspect`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ user_id: userId })
      })
      const out = await res.json().catch(() => ({}))
      if (res.ok) {
        applySuggestions(out, { replaceExisting: false })
        const bits = []
        if (out?.rfc) bits.push(`RFC ${String(out.rfc).toUpperCase()}`)
        if (out?.valid_to) bits.push(`vence ${String(out.valid_to).slice(0,10)}`)
        setMessage(`Sugerencias aplicadas automáticamente${bits.length ? ' (' + bits.join(' · ') + ')' : ''}`)
      }
    } catch {}
  }

  async function deleteFirma() {
    try {
      setMessage('')
      const { data: { user } } = await supabase.auth.getUser()
      if (!user) throw new Error('Sesión no encontrada')
      if (!form.firma_ref) throw new Error('No hay e.firma asociada')
      const base = form.firma_ref
      // Intentar borrar ambos archivos; ignorar si alguno no existe
      const rm = await supabase.storage.from(FIRMAS_BUCKET).remove([
        `${base}/cert.cer`,
        `${base}/key.key`
      ])
      if (rm.error) throw rm.error
      // Limpiar referencia en perfil
      const { error } = await supabase
        .from('profiles')
        .upsert({ user_id: user.id, firma_ref: null, updated_at: new Date().toISOString() }, { onConflict: 'user_id' })
      if (error) throw error
      setForm(prev => ({ ...prev, firma_ref: '' }))
      setFirmaFiles({ hasCer: false, hasKey: false })
      setMessage('e.firma eliminada')
    } catch (err) {
      setMessage(err.message || 'Error al eliminar e.firma')
    }
  }

  async function downloadCert() {
    try {
      setMessage('')
      if (!form.firma_ref) throw new Error('No hay e.firma asociada al perfil')
      const path = `${form.firma_ref}/cert.cer`
  const { data, error } = await supabase.storage.from(FIRMAS_BUCKET).download(path)
      if (error) throw error
      const blobUrl = URL.createObjectURL(data)
      const a = document.createElement('a')
      a.href = blobUrl
      a.download = 'cert.cer'
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(blobUrl)
      setMessage('Certificado descargado')
    } catch (err) {
      setMessage(err.message || 'Error descargando certificado')
    }
  }

  async function downloadKey() {
    try {
      setMessage('')
      if (!form.firma_ref) throw new Error('No hay e.firma asociada al perfil')
      const path = `${form.firma_ref}/key.key`
      const { data, error } = await supabase.storage.from(FIRMAS_BUCKET).download(path)
      if (error) throw error
      const blobUrl = URL.createObjectURL(data)
      const a = document.createElement('a')
      a.href = blobUrl
      a.download = 'key.key'
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(blobUrl)
      setMessage('Llave descargada')
    } catch (err) {
      setMessage(err.message || 'Error descargando llave')
    }
  }

  // Acciones de depuración removidas: URL firmada temporal y prueba de acceso al bucket

  return (
    <div className="page">
      <div className="card">
        <h1>Perfil fiscal</h1>
        <form onSubmit={onSubmit} className="form">
          <label>RFC
            <input value={form.rfc} onChange={e => setForm({ ...form, rfc: e.target.value.toUpperCase() })} required maxLength={13} style={{ textTransform: 'uppercase' }} />
          </label>
          <div className="actions" style={{ gap: 12 }}>
            <span style={{ opacity: .85 }}>Tipo de persona:</span>
            <label style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
              <input type="radio" name="persona" checked={form.persona_moral === false} onChange={() => setForm({ ...form, persona_moral: false })} /> Física
            </label>
            <label style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
              <input type="radio" name="persona" checked={form.persona_moral === true} onChange={() => setForm({ ...form, persona_moral: true })} /> Moral
            </label>
            <span style={{ fontSize: 12, opacity: .7 }}>Se detecta al sugerir desde e.firma; puedes ajustarlo.</span>
          </div>
          <div className="grid2">
            <label>Nombres
              <input value={form.first_name} onChange={e => setForm({ ...form, first_name: e.target.value })} required={!form.persona_moral} disabled={form.persona_moral === true} />
            </label>
            <label>Apellidos
              <input value={form.last_name} onChange={e => setForm({ ...form, last_name: e.target.value })} required={!form.persona_moral} disabled={form.persona_moral === true} />
            </label>
          </div>
          <label>Razón social (si aplica)
            <input value={form.legal_name} onChange={e => setForm({ ...form, legal_name: e.target.value })} required={form.persona_moral === true} />
          </label>
          <label>Régimen
            <input value={form.regime} onChange={e => setForm({ ...form, regime: e.target.value })} />
          </label>
          <label>CURP
            <input
              value={form.curp}
              onChange={e => {
                const curp = e.target.value
                const parsed = parseCurp(curp)
                if (parsed) {
                  const base = parsed.rfc_base || rfcBaseFromCurp(curp)
                  const currentRfc = (form.rfc || '').toUpperCase()
                  const nextRfc = currentRfc && currentRfc.length >= 10 ? currentRfc : base || currentRfc
                  setForm({ ...form, curp, birth_date: parsed.birth_date, gender: parsed.gender, birth_state: parsed.birth_state, rfc: nextRfc || '' })
                } else {
                  setForm({ ...form, curp })
                }
              }}
              maxLength={18}
            />
          </label>
          <div className="grid3">
            <label>Fecha nacimiento
              <input value={form.birth_date || ''} onChange={e => setForm({ ...form, birth_date: e.target.value })} placeholder="YYYY-MM-DD" />
            </label>
            <label>Sexo
              <input value={form.gender || ''} onChange={e => setForm({ ...form, gender: e.target.value })} placeholder="Hombre/Mujer" />
            </label>
            <label>Entidad nacimiento
              <input value={form.birth_state || ''} onChange={e => setForm({ ...form, birth_state: e.target.value })} />
            </label>
          </div>
          <div className="grid2">
            <label>Calle
              <input value={form.street} onChange={e => setForm({ ...form, street: e.target.value })} />
            </label>
            <label>No. Ext.
              <input value={form.ext_number} onChange={e => setForm({ ...form, ext_number: e.target.value })} />
            </label>
          </div>
          <div className="grid2">
            <label>No. Int.
              <input value={form.int_number} onChange={e => setForm({ ...form, int_number: e.target.value })} />
            </label>
            <label>Colonia
              <input value={form.neighborhood} onChange={e => setForm({ ...form, neighborhood: e.target.value })} />
            </label>
          </div>
          <div className="grid3">
            <label>Ciudad
              <input value={form.city} onChange={e => setForm({ ...form, city: e.target.value })} />
            </label>
            <label>Estado
              <input value={form.state} onChange={e => setForm({ ...form, state: e.target.value })} />
            </label>
            <label>CP
              <input value={form.postal_code} onChange={e => setForm({ ...form, postal_code: e.target.value })} maxLength={5} />
            </label>
          </div>
          <div className="grid2">
            <label>Archivo .cer
              <input type="file" accept=".cer" onChange={e => setCerFile(e.target.files?.[0] || null)} />
            </label>
            <label>Archivo .key
              <input type="file" accept=".key" onChange={e => setKeyFile(e.target.files?.[0] || null)} />
            </label>
          </div>
          <label>Contraseña de la e.firma (no se guarda, solo para pruebas futuras)
            <input type="password" value={passphrase} onChange={e => setPassphrase(e.target.value)} placeholder="••••••••" />
          </label>
          {message && <div className="msg">{message}</div>}
          <div className="actions">
            <button type="submit" disabled={saving}>{saving ? 'Guardando…' : 'Guardar'}</button>
            <button type="button" onClick={uploadFirma} disabled={uploading} className="secondary">{uploading ? 'Subiendo…' : 'Subir e.firma'}</button>
            <button type="button" onClick={autoCompleteFromFirma} disabled={autoCompleting} className="secondary">
              {autoCompleting ? 'Autocompletando…' : 'Autocompletar con e.firma'}
            </button>
          </div>
          {form.firma_ref && (
            <div className="actions" style={{ marginTop: 4 }}>
              <button type="button" className="secondary" onClick={downloadCert}>Descargar cert</button>
              <button type="button" className="secondary" onClick={downloadKey}>Descargar key</button>
              <button type="button" className="secondary" onClick={deleteFirma}>Eliminar e.firma</button>
            </div>
          )}
          
          {form.firma_ref && (
            <div className="actions" style={{ marginTop: 4, gap: 8 }}>
              <span className="badge" style={{
                padding: '4px 8px', borderRadius: 999, fontSize: 12,
                border: `1px solid ${firmaFiles.hasCer ? 'rgba(16,185,129,0.5)' : 'rgba(239,68,68,0.5)'}`,
                color: firmaFiles.hasCer ? '#10b981' : '#f87171',
                background: firmaFiles.hasCer ? 'rgba(16,185,129,0.1)' : 'rgba(239,68,68,0.1)'
              }}>
                {firmaFiles.hasCer ? 'cert.cer encontrado' : 'cert.cer faltante'}
              </span>
              <span className="badge" style={{
                padding: '4px 8px', borderRadius: 999, fontSize: 12,
                border: `1px solid ${firmaFiles.hasKey ? 'rgba(16,185,129,0.5)' : 'rgba(239,68,68,0.5)'}`,
                color: firmaFiles.hasKey ? '#10b981' : '#f87171',
                background: firmaFiles.hasKey ? 'rgba(16,185,129,0.1)' : 'rgba(239,68,68,0.1)'
              }}>
                {firmaFiles.hasKey ? 'key.key encontrada' : 'key.key faltante'}
              </span>
              {firmaFiles.hasCer ? (
                <button
                  type="button"
                  className="secondary"
                  disabled={suggesting}
                  onClick={async () => {
                    try {
                      setMessage('')
                      setSuggesting(true)
                      const backend = import.meta.env.VITE_BACKEND_URL || 'http://127.0.0.1:8000'
                      const { data: { user } } = await supabase.auth.getUser()
                      if (!user) throw new Error('Debes iniciar sesión')
                      const res = await fetch(`${backend.replace(/\/$/, '')}/sat/inspect`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ user_id: user.id })
                      })
                      const out = await res.json().catch(() => ({}))
                      if (!res.ok) {
                        let msg = 'Error ' + res.status
                        if (out && out.detail) {
                          if (typeof out.detail === 'string') msg = out.detail
                          else if (out.detail.message) msg = out.detail.message + (out.detail.code ? ` (${out.detail.code})` : '')
                        }
                        throw new Error(msg)
                      }
                      applySuggestions(out, { replaceExisting: false })
                      const bits = []
                      if (out?.rfc) bits.push(`RFC ${String(out.rfc).toUpperCase()}`)
                      if (out?.valid_to) bits.push(`vence ${String(out.valid_to).slice(0,10)}`)
                      if (out?.issuer) bits.push(`emisor: ${out.issuer}`)
                      setMessage(`Sugerencias aplicadas${bits.length ? ' (' + bits.join(' · ') + ')' : ''}`)
                    } catch (err) {
                      setMessage(err.message || 'No se pudo obtener sugerencias desde e.firma')
                    } finally {
                      setSuggesting(false)
                    }
                  }}
                  style={{ marginLeft: 'auto' }}
                >
                  {suggesting ? 'Analizando…' : 'Sugerir desde e.firma'}
                </button>
              ) : (
                <span style={{ marginLeft: 'auto', fontSize: 12, opacity: 0.8 }}>
                  Sube tu cert.cer para habilitar sugerencias
                </span>
              )}
            </div>
          )}

          {form.firma_ref && (
            <div className="actions" style={{ marginTop: 8 }}>
              <button
                type="button"
                className="secondary"
                disabled={verifying}
                onClick={async () => {
                  try {
                    setMessage('')
                    setVerifyInfo(null)
                    if (!passphrase) { setMessage('Ingresa la contraseña de la e.firma para validarla'); return }
                    const backend = import.meta.env.VITE_BACKEND_URL
                    if (!backend) { setMessage('Configura VITE_BACKEND_URL'); return }
                    setVerifying(true)
                    const { data: { user } } = await supabase.auth.getUser()
                    if (!user) throw new Error('Debes iniciar sesión')
                    const res = await fetch(`${backend.replace(/\/$/, '')}/sat/verify`, {
                      method: 'POST', headers: { 'Content-Type': 'application/json' },
                      body: JSON.stringify({ user_id: user.id, passphrase })
                    })
                    const out = await res.json().catch(() => ({}))
                    if (!res.ok) throw new Error(out?.detail || `Error ${res.status}`)
                    setVerifyInfo(out)
                    const vence = out?.valid_to ? String(out.valid_to).slice(0,10) : ''
                    setMessage(`e.firma válida${vence ? ' · vence ' + vence : ''}`)
                  } catch (err) {
                    setMessage(err.message || 'No se pudo validar la e.firma')
                  } finally {
                    setVerifying(false)
                  }
                }}
              >
                {verifying ? 'Validando…' : 'Validar e.firma'}
              </button>
            </div>
          )}

          {verifyInfo && (
            <div className="msg" style={{ marginTop: 6, lineHeight: 1.4 }}>
              CN: <strong>{verifyInfo.subject_common_name || '—'}</strong>
              {' · '}Issuer: <span>{verifyInfo.issuer || '—'}</span>
              {' · '}Vigencia: <span>{(verifyInfo.valid_from || '').slice(0,10)} → {(verifyInfo.valid_to || '').slice(0,10)}</span>
              {' · '}Serie: <span>{verifyInfo.serial_hex || '—'}</span>
            </div>
          )}
          
          <div className="actions" style={{ marginTop: 8 }}>
            <button
              type="button"
              className="secondary"
              disabled={syncingCompany}
              onClick={async () => {
                setMessage('')
                setSyncingCompany(true)
                try {
                  const company = await syncCompanyFromProfile(supabase)
                  setCompanyInfo(company)
                  setMessage('Empresa sincronizada')
                } catch (err) {
                  setMessage(err.message || 'Error al sincronizar empresa')
                } finally {
                  setSyncingCompany(false)
                }
              }}
            >
              {syncingCompany ? 'Sincronizando…' : 'Crear/actualizar empresa'}
            </button>
          </div>
          {companyInfo && (
            <div className="msg" style={{ marginTop: 8 }}>
              Empresa actual: <strong>{companyInfo.name}</strong> · RFC: <strong>{companyInfo.rfc}</strong>
            </div>
          )}
        </form>
      </div>
  <style>{`
        .page{ padding:24px; display:flex; justify-content:center }
  .card{ width:100%; max-width:900px; background:rgba(255,255,255,0.06); border:1px solid rgba(255,255,255,0.1); border-radius:16px; padding:24px }
        h1{ margin:0 0 16px 0 }
        .form{ display:grid; gap:12px }
        label{ display:grid; gap:6px; color:rgba(255,255,255,0.9) }
        input{ padding:10px 12px; border-radius:8px; border:1px solid rgba(255,255,255,0.2); background:rgba(255,255,255,0.04); color:white }
        .msg{ color:#a7f3d0 }
        .actions{ display:flex; gap:12px; align-items:center; margin-top:8px }
        button{ padding:10px 14px; border-radius:8px; border:none; background:linear-gradient(135deg,#667eea,#764ba2); color:#fff; font-weight:600; cursor:pointer }
        .secondary{ background:transparent; border:1px solid rgba(255,255,255,0.3) }
        button[disabled]{ opacity:.7; cursor:not-allowed }
        .grid2{ display:grid; grid-template-columns:1fr; gap:12px }
        .grid3{ display:grid; grid-template-columns:1fr; gap:12px }
        @media (min-width: 640px){
          .grid2{ grid-template-columns:1fr 1fr }
        }
        @media (min-width: 900px){
          .grid3{ grid-template-columns:1fr 1fr 1fr }
        }
  `}</style>
    </div>
  )
}
