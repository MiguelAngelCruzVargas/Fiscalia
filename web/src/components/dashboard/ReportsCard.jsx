import React from 'react'
import { useNavigate } from 'react-router-dom'

export default function ReportsCard() {
  const navigate = useNavigate()
  return (
    <div style={{
      background: 'rgba(16, 185, 129, 0.1)',
      border: '1px solid rgba(16, 185, 129, 0.2)',
      borderRadius: '12px',
      padding: '24px',
      textAlign: 'center'
    }}>
      <h3 style={{ color: '#10b981', marginBottom: '12px' }}>Reportes</h3>
      <p style={{ color: 'rgba(255, 255, 255, 0.7)', marginBottom: '16px' }}>
        ISR, IVA y clasificación
      </p>
      <button onClick={() => navigate('/reports')} style={{
        padding: '8px 16px',
        background: 'rgba(16, 185, 129, 0.2)',
        border: '1px solid #10b981',
        color: '#10b981',
        borderRadius: '6px',
        cursor: 'pointer'
      }}>
        Ver reportes
      </button>
    </div>
  )
}
