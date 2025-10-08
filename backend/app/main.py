from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routers import sat, reports
from dotenv import load_dotenv
import os
from pathlib import Path
from datetime import datetime
from .supabase_client import get_supabase
from .services.sat_sat20 import XMLSEC_AVAILABLE, WSDL_AUTENTICACION, WSDL_SOLICITUD

# Cargar variables de entorno desde backend/.env de forma robusta (independiente del CWD)
_ENV_PATH = (Path(__file__).resolve().parents[1] / '.env')
# Primero intentamos cargar el .env específico del backend
load_dotenv(dotenv_path=_ENV_PATH, override=False)
# Luego permitimos además variables del CWD si el proceso se lanzó ahí
load_dotenv(override=False)

# Nota: Cambio no funcional para forzar recarga al ajustar .env
app = FastAPI(title="Fiscal-IA Backend")
# Note: Reloading this file forces re-reading backend/.env via python-dotenv

# Configuración de CORS para permitir que el frontend se comunique con esta API
# Configuración CORS dinámica a partir de CORS_ORIGINS (lista separada por comas)
_cors_env = os.environ.get('CORS_ORIGINS', '*')
_cors_list = [c.strip() for c in _cors_env.split(',') if c.strip()]
if not _cors_list:
    _cors_list = ['*']
allow_origins = ['*'] if _cors_list == ['*'] else _cors_list

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Incluye los diferentes grupos de rutas (endpoints) de la aplicación
app.include_router(sat.router, prefix="/sat", tags=["SAT"])
app.include_router(reports.router, prefix="/reports", tags=["Reports"])

# --- Diagnóstico de versión cargada ---
import hashlib, inspect

def _hash_file(path: str) -> str:
    try:
        with open(path,'rb') as fh:
            return hashlib.sha1(fh.read()).hexdigest()[:12]
    except Exception:
        return 'unavailable'

@app.on_event("startup")
async def _log_loaded_modules():  # pragma: no cover
    try:
        sat_path = inspect.getfile(sat)
        print(f"[build-info] sat.py path={sat_path} sha1={_hash_file(sat_path)}")
    except Exception as e:
        print(f"[build-info][error] {e}")

@app.get("/build-info")
def build_info():  # pragma: no cover
    try:
        sat_path = inspect.getfile(sat)
    except Exception:
        sat_path = None
    return {
        'sat_file': sat_path,
        'sat_sha1_12': _hash_file(sat_path) if sat_path else None,
    }

@app.get("/health")
def health():
    """
    Endpoint simple para verificar que el servicio está vivo y respondiendo.
    """
    return {"ok": True}


@app.get("/diag")
def diag():
    """
    Endpoint de diagnóstico para revisar la configuración y las conexiones críticas.
    """
    data = {
        'sat_mode': os.environ.get('SAT_MODE', 'mock'),
        'demo_mode': os.environ.get('DEMO_MODE', 'false'),
        'supabase_env': bool(os.environ.get('SUPABASE_URL') and os.environ.get('SUPABASE_SERVICE_ROLE')),
        'env_path_used': str(_ENV_PATH),
        'env_path_exists': _ENV_PATH.exists(),
        'xmlsec_available': XMLSEC_AVAILABLE,
        'wsdl_auth': WSDL_AUTENTICACION,
        'wsdl_solicitud': WSDL_SOLICITUD,
    }
    # Probar instanciación de supabase
    try:
        _ = get_supabase()
        data['supabase_ok'] = True
    except Exception as e:
        data['supabase_ok'] = False
        data['supabase_error'] = str(e)
    return data


@app.get("/diag/time")
def diag_time():
    """
    Endpoint para verificar la hora del servidor (UTC), útil para depurar problemas
    de autenticación con el SAT que son sensibles al tiempo.
    """
    return { 'utc': datetime.utcnow().isoformat() }
