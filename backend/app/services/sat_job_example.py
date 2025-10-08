# Ejemplo de cómo se invocaría el inicio de una descarga desde una API.
# Este archivo es el "mesero": rápido y no bloqueante.

from typing import Optional, Dict, Any
from ..supabase_client import get_supabase
from .sat_provider import SatProvider, SatKind

class SatJobOrchestrator:
    """
    Esta clase orquesta el INICIO de los trabajos de sincronización con el SAT.
    Su única responsabilidad es validar la solicitud y ponerla en una cola de trabajo.
    """
    def __init__(self):
        self.sb = get_supabase()

    def start_sync_job(
        self,
        user_id: str,
        company_id: str,
        kind: str = 'recibidos',
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Paso 1: Encola un nuevo trabajo de sincronización de CFDI.

        Esta función es la que sería llamada por tu API web. Es muy rápida.
        1. Valida los parámetros de entrada.
        2. Llama a `provider.enqueue_sync` para crear un registro en la tabla `sat_jobs`.
        3. Devuelve inmediatamente el ID del trabajo para que el frontend pueda empezar a monitorear.
        
        NO ejecuta el proceso de descarga directamente para evitar timeouts.
        """
        # Validación de tipo
        try:
            k = SatKind(kind)
        except Exception:
            raise ValueError("kind debe ser 'recibidos' o 'emitidos'")

        provider = SatProvider()
        
        # 1) Encolar el job (esto valida perfil/firma si no está en DEMO y es muy rápido)
        job_id = provider.enqueue_sync(
            user_id=user_id,
            company_id=company_id,
            kind=k,
            date_from=date_from,
            date_to=date_to,
        )

        # 2) Devolver el ID del job para que el frontend pueda monitorear su estado.
        # El procesamiento real lo hará un 'worker' en segundo plano.
        return {
            'message': 'Job enqueued successfully.',
            'job_id': job_id,
        }
