import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { supabase } from '../lib/supabaseClient'

export default function Register() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()

  async function onSubmit(e) {
    e.preventDefault()
    setError('')
    setMessage('')
    setLoading(true)
    const { data, error } = await supabase.auth.signUp(
      { email, password },
      {
        emailRedirectTo: `${window.location.origin}/auth/callback`
      }
    )
    setLoading(false)
    if (error) {
      setError(error.message)
    } else {
      if (data.user && !data.session) {
        setMessage('Revisa tu correo para confirmar tu cuenta.')
      } else {
        navigate('/dashboard')
      }
    }
  }

  return (
    <div className="register-container">
      <div className="register-content">
        {/* Compact header */}
        <div className="register-header">
          <div className="logo-section">
            <div className="logo-icon">�</div>
            <h1 className="logo-text">Fiscal-IA</h1>
          </div>
        </div>

        {/* Register form card */}
        <div className="register-card">
          <form onSubmit={onSubmit} className="register-form">
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
                placeholder="Mínimo 6 caracteres"
                value={password}
                onChange={e => setPassword(e.target.value)}
                required
                minLength={6}
                className="form-input"
              />
            </div>

            {error && (
              <div className="error-message">
                {error}
              </div>
            )}

            {message && (
              <div className="success-message">
                {message}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="register-button"
            >
              {loading ? 'Creando...' : 'Crear cuenta'}
            </button>
          </form>

          <div className="card-footer">
            <p>¿Ya tienes cuenta? <Link to="/login" className="login-link">Iniciar sesión</Link></p>
          </div>
        </div>
      </div>

  <style>{`
        .register-container {
          min-height: 100vh;
          display: flex;
          align-items: center;
          justify-content: center;
          padding: 1rem;
          background: linear-gradient(135deg, #0f0f23 0%, #1a1a2e 100%);
        }

        .register-content {
          width: 100%;
          max-width: 380px;
        }

        .register-header {
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
          background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
          padding: 0.6rem;
          border-radius: 10px;
          box-shadow: 0 4px 12px rgba(240, 147, 251, 0.3);
        }

        .logo-text {
          font-size: 1.6rem;
          font-weight: 700;
          background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
          -webkit-background-clip: text;
          -webkit-text-fill-color: transparent;
          background-clip: text;
          margin: 0;
        }

        .register-card {
          background: rgba(255, 255, 255, 0.08);
          backdrop-filter: blur(20px);
          border: 1px solid rgba(255, 255, 255, 0.15);
          border-radius: 16px;
          padding: 1.8rem;
          box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
        }

        .register-form {
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
          border-color: #f093fb;
          background: rgba(255, 255, 255, 0.08);
          box-shadow: 0 0 0 2px rgba(240, 147, 251, 0.1);
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

        .success-message {
          padding: 0.6rem 0.8rem;
          background: rgba(16, 185, 129, 0.1);
          border: 1px solid rgba(16, 185, 129, 0.2);
          border-radius: 6px;
          color: #6ee7b7;
          font-size: 0.8rem;
        }

        .register-button {
          width: 100%;
          padding: 0.9rem;
          border: none;
          border-radius: 8px;
          background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
          color: white;
          font-size: 0.95rem;
          font-weight: 600;
          cursor: pointer;
          transition: all 0.3s ease;
          margin-top: 0.3rem;
        }

        .register-button:hover:not(:disabled) {
          transform: translateY(-1px);
          box-shadow: 0 4px 12px rgba(240, 147, 251, 0.4);
        }

        .register-button:disabled {
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

        .login-link {
          color: #f093fb;
          text-decoration: none;
          font-weight: 600;
        }

        .login-link:hover {
          color: #4facfe;
        }

        /* Responsive design */
        @media (max-width: 480px) {
          .register-container {
            padding: 0.5rem;
          }

          .register-card {
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
          .register-container {
            min-height: auto;
            padding: 0.5rem;
          }
          
          .register-header {
            margin-bottom: 1rem;
          }
          
          .register-card {
            padding: 1.5rem;
          }
        }
  `}</style>
    </div>
  )
}
