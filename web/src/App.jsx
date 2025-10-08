import { Routes, Route, Link, Navigate, useLocation } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { supabase } from './lib/supabaseClient'
import Login from './routes/Login'
import Register from './routes/Register'
import Dashboard from './routes/Dashboard'
import AuthCallback from './routes/AuthCallback'
import Profile from './routes/Profile'
import ImportXml from './routes/Import'
import RequireProfile from './routes/RequireProfile'
import Reports from './routes/Reports'

function ProtectedRoute({ children }) {
  const [session, setSession] = useState(null)
  const [loading, setLoading] = useState(true)
  const location = useLocation()

  useEffect(() => {
    let ignore = false
    supabase.auth.getSession().then(({ data }) => {
      if (!ignore) {
        setSession(data.session)
        setLoading(false)
      }
    })
    const { data: sub } = supabase.auth.onAuthStateChange((_event, sess) => {
      setSession(sess)
    })
    return () => {
      ignore = true
      sub.subscription.unsubscribe()
    }
  }, [])

  if (loading) return (
    <div style={{ 
      minHeight: '100vh', 
      display: 'flex', 
      justifyContent: 'center', 
      alignItems: 'center',
      color: 'rgba(255, 255, 255, 0.8)'
    }}>
      Cargando…
    </div>
  )
  if (!session) return <Navigate to="/login" state={{ from: location }} replace />
  return children
}

export default function App() {
  const [session, setSession] = useState(null)

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => setSession(data.session))
    const { data: sub } = supabase.auth.onAuthStateChange((_event, sess) => setSession(sess))
    return () => sub.subscription.unsubscribe()
  }, [])

  return (
    <div style={{ fontFamily: 'Inter, system-ui, -apple-system, Segoe UI, Roboto, Ubuntu, Cantarell, Noto Sans, sans-serif' }}>
      <nav style={{ 
        display: 'flex', 
        alignItems: 'center',
        gap: 24, 
        padding: '16px 24px', 
        background: 'rgba(255, 255, 255, 0.05)',
        backdropFilter: 'blur(10px)',
        borderBottom: '1px solid rgba(255, 255, 255, 0.1)'
      }}>
        <Link to="/" style={{ 
          color: 'white', 
          textDecoration: 'none', 
          fontWeight: '600',
          fontSize: '18px'
        }}>
          Fiscal-IA
        </Link>
        {session ? (
          <>
            <Link to="/dashboard" style={{ 
              color: 'rgba(255, 255, 255, 0.8)', 
              textDecoration: 'none',
              padding: '8px 16px',
              borderRadius: '6px',
              transition: 'all 0.2s'
            }}>
              Dashboard
            </Link>
            <Link to="/profile" style={{ 
              color: 'rgba(255, 255, 255, 0.8)', 
              textDecoration: 'none',
              padding: '8px 16px',
              borderRadius: '6px',
              transition: 'all 0.2s'
            }}>
              Perfil
            </Link>
            <Link to="/import" style={{ 
              color: 'rgba(255, 255, 255, 0.8)', 
              textDecoration: 'none',
              padding: '8px 16px',
              borderRadius: '6px',
              transition: 'all 0.2s'
            }}>
              Importar XML
            </Link>
            <Link to="/reports" style={{ 
              color: 'rgba(255, 255, 255, 0.8)', 
              textDecoration: 'none',
              padding: '8px 16px',
              borderRadius: '6px',
              transition: 'all 0.2s'
            }}>
              Reportes
            </Link>
            <button 
              onClick={() => supabase.auth.signOut()} 
              style={{ 
                marginLeft: 'auto',
                padding: '8px 16px',
                border: '1px solid rgba(255, 255, 255, 0.2)',
                background: 'transparent',
                color: 'rgba(255, 255, 255, 0.8)',
                borderRadius: '6px',
                cursor: 'pointer',
                fontSize: '14px'
              }}
            >
              Salir
            </button>
          </>
        ) : (
          <>
            <Link to="/login" style={{ 
              color: 'rgba(255, 255, 255, 0.8)', 
              textDecoration: 'none',
              marginLeft: 'auto',
              padding: '8px 16px',
              borderRadius: '6px'
            }}>
              Entrar
            </Link>
            <Link to="/register" style={{ 
              color: 'white', 
              textDecoration: 'none',
              background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
              padding: '8px 16px',
              borderRadius: '6px'
            }}>
              Registro
            </Link>
          </>
        )}
      </nav>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
  <Route path="/auth/callback" element={<AuthCallback />} />
  <Route path="/profile" element={<ProtectedRoute><Profile /></ProtectedRoute>} />
  <Route path="/import" element={<ProtectedRoute><RequireProfile><ImportXml /></RequireProfile></ProtectedRoute>} />
  <Route path="/dashboard" element={<ProtectedRoute><RequireProfile><Dashboard /></RequireProfile></ProtectedRoute>} />
  <Route path="/reports" element={<ProtectedRoute><RequireProfile><Reports /></RequireProfile></ProtectedRoute>} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </div>
  )
}

function Home() {
  return (
    <div className="home-container">
      {/* Background elements - simplified */}
      <div className="bg-animation">
        <div className="floating-shape shape-1"></div>
        <div className="floating-shape shape-2"></div>
      </div>

      {/* Main content */}
      <div className="hero-section">
        <div className="hero-content">
          {/* Logo and title section */}
          <div className="brand-section">
            <div className="logo-container">
              <div className="logo-icon">📊</div>
            </div>
            <h1 className="hero-title">
              <span className="title-fiscal">Fiscal</span>
              <span className="title-separator">-</span>
              <span className="title-ia">IA</span>
            </h1>
          </div>

          {/* Subtitle and description */}
          <div className="hero-description">
            <p className="hero-subtitle">
              Automatización fiscal inteligente
            </p>
            <p className="hero-text">
              Descarga CFDI, clasifica gastos y calcula impuestos automáticamente con IA.
            </p>
          </div>

          {/* Call-to-action buttons */}
          <div className="cta-section">
            <Link to="/register" className="cta-primary">
              <span className="cta-text">Comenzar Gratis</span>
              <span className="cta-arrow">→</span>
            </Link>
            <Link to="/login" className="cta-secondary">
              <span className="cta-text">Iniciar Sesión</span>
            </Link>
          </div>
        </div>
      </div>

  <style>{`
        .home-container {
          min-height: 85vh;
          display: flex;
          align-items: center;
          justify-content: center;
          padding: 1rem;
          position: relative;
          overflow: hidden;
          background: radial-gradient(ellipse at center, #1a1a2e 0%, #0f0f23 100%);
        }

        .bg-animation {
          position: absolute;
          top: 0;
          left: 0;
          width: 100%;
          height: 100%;
          pointer-events: none;
          z-index: 0;
        }

        .floating-shape {
          position: absolute;
          border-radius: 50%;
          filter: blur(80px);
          opacity: 0.08;
          animation: float 12s ease-in-out infinite;
        }

        .shape-1 {
          width: 300px;
          height: 300px;
          background: linear-gradient(135deg, #667eea, #764ba2);
          top: 20%;
          left: -10%;
          animation-delay: -4s;
        }

        .shape-2 {
          width: 250px;
          height: 250px;
          background: linear-gradient(135deg, #f093fb, #f5576c);
          bottom: 20%;
          right: -5%;
          animation-delay: -8s;
        }

        @keyframes float {
          0%, 100% { transform: translateY(0px) rotate(0deg); }
          50% { transform: translateY(-20px) rotate(180deg); }
        }

        .hero-section {
          position: relative;
          z-index: 1;
          max-width: 700px;
          width: 100%;
        }

        .hero-content {
          text-align: center;
        }

        .brand-section {
          margin-bottom: 2rem;
        }

        .logo-container {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          margin-bottom: 1.5rem;
        }

        .logo-icon {
          font-size: 3rem;
          background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
          padding: 1rem;
          border-radius: 20px;
          box-shadow: 0 10px 30px rgba(102, 126, 234, 0.3);
          animation: logo-pulse 4s ease-in-out infinite;
        }

        @keyframes logo-pulse {
          0%, 100% { 
            box-shadow: 0 10px 30px rgba(102, 126, 234, 0.3);
            transform: scale(1);
          }
          50% { 
            box-shadow: 0 15px 40px rgba(102, 126, 234, 0.5);
            transform: scale(1.02);
          }
        }

        .hero-title {
          font-size: clamp(3.5rem, 10vw, 6rem);
          font-weight: 900;
          margin: 0;
          line-height: 0.95;
          letter-spacing: -0.02em;
        }

        .title-fiscal {
          background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
          -webkit-background-clip: text;
          -webkit-text-fill-color: transparent;
          background-clip: text;
        }

        .title-separator {
          color: rgba(255, 255, 255, 0.4);
          margin: 0 0.05em;
        }

        .title-ia {
          background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
          -webkit-background-clip: text;
          -webkit-text-fill-color: transparent;
          background-clip: text;
        }

        .hero-description {
          margin-bottom: 2.5rem;
        }

        .hero-subtitle {
          font-size: 1.3rem;
          font-weight: 600;
          color: rgba(255, 255, 255, 0.9);
          margin: 0 0 1rem 0;
        }

        .hero-text {
          font-size: 1.1rem;
          color: rgba(255, 255, 255, 0.75);
          line-height: 1.6;
          margin: 0 auto;
          max-width: 500px;
        }

        .cta-section {
          display: flex;
          gap: 1rem;
          justify-content: center;
          flex-wrap: wrap;
        }

        .cta-primary {
          display: inline-flex;
          align-items: center;
          gap: 0.5rem;
          padding: 1rem 2rem;
          background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
          color: white;
          text-decoration: none;
          border-radius: 12px;
          font-weight: 600;
          font-size: 1rem;
          transition: all 0.3s ease;
          box-shadow: 0 6px 20px rgba(102, 126, 234, 0.3);
        }

        .cta-primary:hover {
          transform: translateY(-2px);
          box-shadow: 0 8px 25px rgba(102, 126, 234, 0.4);
        }

        .cta-primary:hover .cta-arrow {
          transform: translateX(4px);
        }

        .cta-secondary {
          display: inline-flex;
          align-items: center;
          gap: 0.5rem;
          padding: 1rem 2rem;
          border: 2px solid rgba(255, 255, 255, 0.2);
          background: rgba(255, 255, 255, 0.05);
          backdrop-filter: blur(10px);
          color: rgba(255, 255, 255, 0.9);
          text-decoration: none;
          border-radius: 12px;
          font-weight: 600;
          font-size: 1rem;
          transition: all 0.3s ease;
        }

        .cta-secondary:hover {
          transform: translateY(-2px);
          border-color: rgba(255, 255, 255, 0.3);
          background: rgba(255, 255, 255, 0.1);
        }

        .cta-arrow {
          transition: transform 0.3s ease;
          font-size: 1.2rem;
        }

        /* Responsive design */
        @media (max-width: 768px) {
          .home-container {
            min-height: 80vh;
            padding: 0.5rem;
          }

          .logo-icon {
            font-size: 2.5rem;
            padding: 0.8rem;
          }

          .hero-title {
            font-size: clamp(2.5rem, 12vw, 4.5rem);
          }

          .hero-subtitle {
            font-size: 1.2rem;
          }

          .hero-text {
            font-size: 1rem;
          }

          .cta-section {
            flex-direction: column;
            align-items: center;
          }

          .cta-primary, .cta-secondary {
            width: 100%;
            max-width: 280px;
            justify-content: center;
          }
        }

        @media (max-width: 480px) {
          .brand-section {
            margin-bottom: 1.5rem;
          }

          .hero-description {
            margin-bottom: 2rem;
          }

          .hero-subtitle {
            font-size: 1.1rem;
          }

          .hero-text {
            font-size: 0.95rem;
          }
        }
  `}</style>
    </div>
  )
}
