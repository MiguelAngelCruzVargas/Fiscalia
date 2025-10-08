import React from 'react'
import { useNavigate } from 'react-router-dom'

export default function CfdiCard({ count = 0 }) {
  const navigate = useNavigate()
  return (
    <div style={{
      background: 'rgba(240, 147, 251, 0.1)',
      border: '1px solid rgba(240, 147, 251, 0.2)',
      borderRadius: '12px',
      padding: '24px',
      textAlign: 'center'
    }}>
      <h3 style={{ color: '#f093fb', marginBottom: '12px' }}>CFDI</h3>
      <p style={{ color: 'rgba(255, 255, 255, 0.7)', marginBottom: '16px' }}>
        Sincroniza automáticamente desde SAT o sube XML. Cargados: <strong>{count}</strong>
      </p>
      <div style={{ display:'flex', gap:8, justifyContent:'center', flexWrap:'wrap' }}>
        <button onClick={() => navigate('/import')} style={{
          padding: '8px 16px',
          background: 'rgba(240, 147, 251, 0.2)',
          border: '1px solid #f093fb',
          color: '#f093fb',
          borderRadius: '6px',
          cursor: 'pointer'
        }}>
          Sincronizar SAT
        </button>
        <button onClick={() => navigate('/import')} style={{
          padding: '8px 16px',
          background: 'transparent',
          border: '1px solid rgba(255,255,255,0.35)',
          color: '#fff',
          borderRadius: '6px',
          cursor: 'pointer'
        }}>
          Subir XML
        </button>
      </div>
    </div>
  )
}
