import { useState } from 'react'
import { useNavigate, useLocation, Link } from 'react-router-dom'
import { supabase } from '../lib/supabaseClient'

export default function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()
  const from = location.state?.from?.pathname || '/dashboard'

  async function onSubmit(e) {
    e.preventDefault()
    setError('')
    setLoading(true)
    const { error } = await supabase.auth.signInWithPassword({ email, password })
    setLoading(false)
    if (error) {
      setError(error.message)
    } else {
      navigate(from, { replace: true })
    }
  }

  return (
    <div className="login-container">
      <div className="login-content">
        {/* Compact header */}
        <div className="login-header">
          <div className="logo-section">
            <div className="logo-icon">�</div>
            <h1 className="logo-text">Fiscal-IA</h1>
          </div>
        </div>

        {/* Login form card */}
        <div className="login-card">
          <form onSubmit={onSubmit} className="login-form">
            <div className="form-group">
              <label htmlFor="email">Email</label>
              <input
                id="email"
                type="email"
                placeholder="tu@email.com"
                value={email}
                onChange={e => setEmail(e.target.value)}
                required
                className="form-input"
              />
            </div>

            <div className="form-group">
              <label htmlFor="password">Contraseña</label>
              <input
                id="password"
                type="password"
                placeholder="••••••••"
                value={password}
                onChange={e => setPassword(e.target.value)}
                required
                className="form-input"
              />
            </div>

            {error && (
              <div className="error-message">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="login-button"
            >
              {loading ? 'Iniciando...' : 'Entrar'}
            </button>
          </form>

          <div className="card-footer">
            <p>¿No tienes cuenta? <Link to="/register" className="register-link">Crear cuenta</Link></p>
          </div>
        </div>
      </div>

  <style>{`
        .login-container {
          min-height: 100vh;
          display: flex;
          align-items: center;
          justify-content: center;
          padding: 1rem;
          background: linear-gradient(135deg, #0f0f23 0%, #1a1a2e 100%);
        }

        .login-content {
          width: 100%;
          max-width: 380px;
        }

        .login-header {
          text-align: center;
          margin-bottom: 1.5rem;
        }

        .logo-section {
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 0.5rem;
        }

        .logo-icon {
          font-size: 1.8rem;
          background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
          padding: 0.6rem;
          border-radius: 10px;
          box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3);
        }

        .logo-text {
          font-size: 1.6rem;
          font-weight: 700;
          background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
          -webkit-background-clip: text;
          -webkit-text-fill-color: transparent;
          background-clip: text;
          margin: 0;
        }

        .login-card {
          background: rgba(255, 255, 255, 0.08);
          backdrop-filter: blur(20px);
          border: 1px solid rgba(255, 255, 255, 0.15);
          border-radius: 16px;
          padding: 1.8rem;
          box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
        }

        .login-form {
          display: flex;
          flex-direction: column;
          gap: 1.2rem;
        }

        .form-group {
          display: flex;
          flex-direction: column;
          gap: 0.4rem;
        }

        .form-group label {
          color: rgba(255, 255, 255, 0.9);
          font-weight: 500;
          font-size: 0.85rem;
        }

        .form-input {
          width: 100%;
          padding: 0.9rem 1rem;
          border: 2px solid rgba(255, 255, 255, 0.1);
          border-radius: 8px;
          background: rgba(255, 255, 255, 0.05);
          color: white;
          font-size: 0.95rem;
          transition: all 0.3s ease;
          outline: none;
        }

        .form-input:focus {
          border-color: #667eea;
          background: rgba(255, 255, 255, 0.08);
          box-shadow: 0 0 0 2px rgba(102, 126, 234, 0.1);
        }

        .form-input::placeholder {
          color: rgba(255, 255, 255, 0.4);
        }

        .error-message {
          padding: 0.6rem 0.8rem;
          background: rgba(239, 68, 68, 0.1);
          border: 1px solid rgba(239, 68, 68, 0.2);
          border-radius: 6px;
          color: #fca5a5;
          font-size: 0.8rem;
        }

        .login-button {
          width: 100%;
          padding: 0.9rem;
          border: none;
          border-radius: 8px;
          background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
          color: white;
          font-size: 0.95rem;
          font-weight: 600;
          cursor: pointer;
          transition: all 0.3s ease;
          margin-top: 0.3rem;
        }

        .login-button:hover:not(:disabled) {
          transform: translateY(-1px);
          box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
        }

        .login-button:disabled {
          opacity: 0.7;
          cursor: not-allowed;
        }

        .card-footer {
          text-align: center;
          margin-top: 1.2rem;
          padding-top: 1.2rem;
          border-top: 1px solid rgba(255, 255, 255, 0.1);
        }

        .card-footer p {
          color: rgba(255, 255, 255, 0.7);
          margin: 0;
          font-size: 0.85rem;
        }

        .register-link {
          color: #667eea;
          text-decoration: none;
          font-weight: 600;
        }

        .register-link:hover {
          color: #4facfe;
        }

        /* Responsive design */
        @media (max-width: 480px) {
          .login-container {
            padding: 0.5rem;
          }

          .login-card {
            padding: 1.5rem;
          }

          .logo-text {
            font-size: 1.4rem;
          }

          .logo-icon {
            font-size: 1.6rem;
            padding: 0.5rem;
          }
        }

        @media (max-height: 700px) {
          .login-container {
            min-height: auto;
            padding: 0.5rem;
          }
          
          .login-header {
            margin-bottom: 1rem;
          }
          
          .login-card {
            padding: 1.5rem;
          }
        }
  `}</style>
    </div>
  )
}
