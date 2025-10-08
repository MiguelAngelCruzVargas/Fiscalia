import os
from typing import Optional
from supabase import create_client, Client

# Python 3.9 compat: usar Optional en lugar de operador '|'
_supabase: Optional[Client] = None

def get_supabase() -> Client:
    global _supabase
    if _supabase is None:
        url = os.environ.get('SUPABASE_URL')
        key = os.environ.get('SUPABASE_SERVICE_ROLE')
        if not url or not key:
            raise RuntimeError('Faltan SUPABASE_URL o SUPABASE_SERVICE_ROLE en el entorno')
        _supabase = create_client(url, key)
    # para el tipo, mypy/linters pueden requerir aserción
    return _supabase  # type: ignore[return-value]
