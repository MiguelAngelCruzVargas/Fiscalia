import { createClient } from '@supabase/supabase-js'

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL
// Soporta el nuevo esquema de claves de Supabase:
// - VITE_SUPABASE_PUBLISHABLE_KEY (nuevo nombre en el dashboard)
// - VITE_SUPABASE_ANON_KEY (nombre anterior)
const supabasePublicKey =
	import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY || import.meta.env.VITE_SUPABASE_ANON_KEY

if (!supabaseUrl || !supabasePublicKey) {
	// Mensaje claro en consola para configurar variables
	// Evita horas perdidas si faltan env vars
	// Instrucciones rápidas:
	// 1) Crea un archivo web/.env.local
	// 2) Define VITE_SUPABASE_URL y VITE_SUPABASE_PUBLISHABLE_KEY
	// 3) Reinicia `npm run dev`
	console.error('[Supabase] Faltan variables de entorno. Define VITE_SUPABASE_URL y VITE_SUPABASE_PUBLISHABLE_KEY (o VITE_SUPABASE_ANON_KEY) en web/.env.local')
}

// Evitar múltiples instancias en HMR/React StrictMode
const getClient = () => {
	if (!globalThis.__supabase_client__) {
		globalThis.__supabase_client__ = createClient(supabaseUrl, supabasePublicKey, {
			auth: {
				// clave estable para el almacenamiento de sesión
				storageKey: 'fiscal-ia-auth'
			}
		})
	}
	return globalThis.__supabase_client__
}

export const supabase = getClient()

// Nombre del bucket para almacenar e.firma; configurable por env
export const FIRMAS_BUCKET = import.meta.env.VITE_FIRMAS_BUCKET || 'fiscalia'
//firmas
// Bucket para XML de CFDI
export const CFDI_BUCKET = import.meta.env.VITE_CFDI_BUCKET || 'cfdi-xml'
