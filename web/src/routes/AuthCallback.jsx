import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { supabase } from '../lib/supabaseClient'

export default function AuthCallback() {
  const [status, setStatus] = useState('Verificando tu cuenta…')
  const [error, setError] = useState('')
  const navigate = useNavigate()

  useEffect(() => {
    async function verify() {
      try {
        // 1) Si el proveedor usa code (PKCE/OAuth), intenta el intercambio
        try {
          await supabase.auth.exchangeCodeForSession(window.location.href)
        } catch (_) {
          // Ignorar si no aplica; email confirm links pueden traer tokens en hash
        }

        // 2) Obtener sesión por si quedó activa tras confirmar
        await supabase.auth.getSession()

        // 3) Forzar experiencia: ir al login SIN sesión activa
        await supabase.auth.signOut().catch(() => {})
        navigate('/login', { replace: true })
      } catch (e) {
        setError(e.message || 'Ocurrió un error al verificar la cuenta.')
      }
    }
    verify()
  }, [navigate])

  return (
    <div className="confirm-container">
      <div className="confirm-card">
        <div className="emoji" aria-hidden>✅</div>
        <h1>{error ? 'Hubo un problema' : 'Correo confirmado'}</h1>
        <p className={error ? 'error' : 'ok'}>
          {error ? error : status}
        </p>
        <p className="hint">Redirigiendo al inicio de sesión…</p>
      </div>

  <style>{`
        .confirm-container {
          min-height: 100vh;
          display: flex;
          align-items: center;
          justify-content: center;
          background: radial-gradient(ellipse at center, #1a1a2e 0%, #0f0f23 100%);
          padding: 16px;
        }
        .confirm-card {
          max-width: 520px;
          width: 100%;
          padding: 28px;
          border-radius: 16px;
          background: rgba(255,255,255,0.08);
          backdrop-filter: blur(16px);
          border: 1px solid rgba(255,255,255,0.12);
          text-align: center;
          color: #fff;
        }
        .emoji { font-size: 42px; margin-bottom: 12px; }
        h1 { margin: 0 0 8px 0; font-size: 1.6rem; }
        p { margin: 6px 0; }
        .ok { color: rgba(255,255,255,0.85); }
        .error { color: #fca5a5; }
        .hint { color: rgba(255,255,255,0.6); font-size: 0.95rem; margin-top: 8px; }
  `}</style>
    </div>
  )
}
