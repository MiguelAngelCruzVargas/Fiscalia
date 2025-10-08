import { useEffect, useState, useRef } from 'react'
import { supabase } from '../lib/supabaseClient'
import { getOrCreateDefaultCompany } from '../lib/company'
import ProfileCard from '../components/dashboard/ProfileCard'
import CfdiCard from '../components/dashboard/CfdiCard'
import ReportsCard from '../components/dashboard/ReportsCard'

export default function Dashboard() {
  const [displayName, setDisplayName] = useState('')
  const [stats, setStats] = useState({ cfdi: 0 })
  const autoSyncStarted = useRef(false)

  useEffect(() => {
    supabase.auth.getUser().then(async ({ data }) => {
      const user = data.user
      if (!user) return
      // Cargar nombre desde profiles; fallback al email si no hay nombre
      try {
        const { data: profile } = await supabase
          .from('profiles')
          .select('first_name, last_name, legal_name')
          .eq('user_id', user.id)
          .maybeSingle()
        const fullName = profile?.legal_name?.trim() || [profile?.first_name, profile?.last_name].filter(Boolean).join(' ').trim()
        setDisplayName(fullName || user.email || 'Usuario')
      } catch {
        setDisplayName(user.email || 'Usuario')
      }
    })
    ;(async () => {
      try {
        const companyId = await getOrCreateDefaultCompany(supabase)
        const { count } = await supabase
          .from('cfdi')
          .select('id', { count: 'exact', head: true })
          .eq('company_id', companyId)
        setStats({ cfdi: count || 0 })

        // Si no hay CFDI y tenemos backend, iniciar sincronización automática (mock SAT)
        const backend = import.meta.env.VITE_BACKEND_URL
  const isDemo = String(import.meta.env.VITE_DEMO_MODE).toLowerCase() === 'true'
  if (!autoSyncStarted.current && isDemo && (count || 0) === 0 && backend) {
          autoSyncStarted.current = true
          try {
            const { data: auth } = await supabase.auth.getUser()
            const user = auth?.user
            if (!user) return

            // Rango por defecto: mes actual
            const now = new Date()
            const first = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 1))
            const df = first.toISOString().slice(0, 10)
            const dt = new Date().toISOString().slice(0, 10)

            const postSync = async (kind) => {
              const res = await fetch(`${backend.replace(/\/$/, '')}/sat/sync`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                  user_id: user.id,
                  company_id: companyId,
                  kind,
                  date_from: df,
                  date_to: dt,
                }),
              })
              if (!res.ok) throw new Error(`sync ${kind} failed`)
              return res.json()
            }

            const jobs = []
            for (const kind of ['recibidos', 'emitidos']) {
              try {
                const j = await postSync(kind)
                if (j?.id) jobs.push(j.id)
              } catch {}
            }

            const pollJob = async (jobId) => {
              const url = `${backend.replace(/\/$/, '')}/sat/jobs/${jobId}`
              for (let i = 0; i < 20; i++) {
                const r = await fetch(url)
                if (r.ok) {
                  const job = await r.json()
                  if (job?.status === 'success' || job?.status === 'error') return job?.status
                }
                await new Promise(res => setTimeout(res, 1000))
              }
              return 'timeout'
            }

            // Esperar jobs (si hay)
            await Promise.all(jobs.map(pollJob))

            // Refrescar conteo
            const { count: count2 } = await supabase
              .from('cfdi')
              .select('id', { count: 'exact', head: true })
              .eq('company_id', companyId)
            setStats({ cfdi: count2 || 0 })
          } catch {
            // silencioso; el dashboard seguirá funcionando
          }
        }
      } catch {}
    })()
  }, [])

  return (
    <div style={{ 
      padding: '24px',
      minHeight: '90vh'
    }}>
      <div style={{
        background: 'rgba(255, 255, 255, 0.05)',
        backdropFilter: 'blur(10px)',
        border: '1px solid rgba(255, 255, 255, 0.1)',
        borderRadius: '16px',
        padding: '32px',
        maxWidth: '800px',
        margin: '0 auto'
      }}>
        <div style={{ textAlign: 'center', marginBottom: '32px' }}>
          <h1 style={{ 
            fontSize: '2.5rem', 
            fontWeight: 'bold', 
            background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)', 
            WebkitBackgroundClip: 'text', 
            WebkitTextFillColor: 'transparent',
            backgroundClip: 'text',
            color: 'transparent',
            marginBottom: '8px'
          }}>
            Dashboard
          </h1>
          <p style={{ color: 'rgba(255, 255, 255, 0.8)', fontSize: '1.1rem' }}>
              Bienvenido, {displayName || 'Usuario'}
          </p>
          {String(import.meta.env.VITE_DEMO_MODE).toLowerCase() === 'true' && (
            <div style={{
              display:'inline-block',
              marginTop:'8px',
              padding:'4px 10px',
              borderRadius:'999px',
              background:'rgba(16,185,129,0.18)',
              border:'1px solid rgba(16,185,129,0.35)',
              color:'#a7f3d0',
              fontSize:'12px'
            }}>Datos de prueba (demo)</div>
          )}
        </div>
        
        <div style={{ display: 'grid', gap: '20px', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))' }}>
          <ProfileCard />
          <CfdiCard count={stats.cfdi} />
          <ReportsCard />
        </div>
        
        <div style={{ 
          marginTop: '32px', 
          textAlign: 'center',
          color: 'rgba(255, 255, 255, 0.6)'
        }}>
          <p>Próximamente: descarga automática del SAT, clasificación con IA y cálculos avanzados.</p>
        </div>
      </div>
    </div>
  )
}
