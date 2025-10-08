import { useEffect, useState } from 'react'
import { useLocation, Navigate } from 'react-router-dom'
import { supabase } from '../lib/supabaseClient'

export default function RequireProfile({ children }) {
  const [loading, setLoading] = useState(true)
  const [ok, setOk] = useState(false)
  const location = useLocation()

  useEffect(() => {
    let ignore = false
    async function check() {
      const { data: { user } } = await supabase.auth.getUser()
      if (!user) { setOk(false); setLoading(false); return }
      const { data, error } = await supabase
        .from('profiles')
        .select('*')
        .eq('user_id', user.id)
        .maybeSingle()
      if (ignore) return
      if (error) { setOk(false); setLoading(false); return }
  // Requisitos mínimos: nombre, apellidos, RFC, CURP y dirección básica
  const hasRfc = !!data?.rfc && String(data.rfc).trim().length >= 12
  const hasFirst = !!data?.first_name && String(data.first_name).trim().length > 1
  const hasLast = !!data?.last_name && String(data.last_name).trim().length > 1
  const hasCurp = !!data?.curp && String(data.curp).trim().length >= 18
  const hasStreet = !!data?.street && String(data.street).trim().length > 1
  const hasPostal = !!data?.postal_code && String(data.postal_code).trim().length === 5
  setOk(Boolean(hasRfc && hasFirst && hasLast && hasCurp && hasStreet && hasPostal))
      setLoading(false)
    }
    check()
    return () => { ignore = true }
  }, [])

  if (loading) return (
    <div style={{ minHeight: '60vh', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff' }}>
      Verificando perfil…
    </div>
  )

  if (!ok) return <Navigate to="/profile" state={{ from: location, reason: 'complete-profile' }} replace />
  return children
}
