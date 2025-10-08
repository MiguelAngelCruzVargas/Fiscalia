import React, { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { supabase } from '../../lib/supabaseClient'

export default function ProfileCard() {
  const navigate = useNavigate()
  const [status, setStatus] = useState({ complete: false, hasFirma: false })

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const { data: { user } } = await supabase.auth.getUser()
        if (!user) return
        const { data } = await supabase
          .from('profiles')
          .select('rfc, first_name, last_name, legal_name, firma_ref')
          .eq('user_id', user.id)
          .maybeSingle()
        if (cancelled) return
        const hasName = Boolean((data?.legal_name || '').trim() || [data?.first_name, data?.last_name].filter(Boolean).join(' ').trim())
        const hasRfc = Boolean((data?.rfc || '').trim())
        const hasFirma = Boolean((data?.firma_ref || '').trim())
        setStatus({ complete: hasName && hasRfc, hasFirma })
      } catch {}
    })()
    return () => { cancelled = true }
  }, [])
  return (
    <div style={{
      background: 'rgba(102, 126, 234, 0.1)',
      border: '1px solid rgba(102, 126, 234, 0.2)',
      borderRadius: '12px',
      padding: '24px',
      textAlign: 'center'
    }}>
      <h3 style={{ color: '#667eea', marginBottom: '12px' }}>Perfil Fiscal</h3>
      <div style={{ color: 'rgba(255, 255, 255, 0.7)', marginBottom: '16px' }}>
        Configura tu RFC y e.firma
        <div style={{ display: 'flex', gap: 8, justifyContent: 'center', marginTop: 8 }}>
          <Badge ok={status.complete} label={status.complete ? 'Perfil completo' : 'Perfil incompleto'} />
          <Badge ok={status.hasFirma} label={status.hasFirma ? 'Firma cargada' : 'Firma faltante'} />
        </div>
      </div>
      <button onClick={() => navigate('/profile')} style={{
        padding: '8px 16px',
        background: 'rgba(102, 126, 234, 0.2)',
        border: '1px solid #667eea',
        color: '#667eea',
        borderRadius: '6px',
        cursor: 'pointer'
      }}>
        Configurar
      </button>
    </div>
  )
}

function Badge({ ok, label }) {
  return (
    <span style={{
      padding: '4px 8px',
      borderRadius: 999,
      fontSize: 12,
      border: `1px solid ${ok ? 'rgba(16,185,129,0.5)' : 'rgba(239,68,68,0.5)'}`,
      color: ok ? '#10b981' : '#f87171',
      background: ok ? 'rgba(16,185,129,0.1)' : 'rgba(239,68,68,0.1)'
    }}>
      {label}
    </span>
  )
}
